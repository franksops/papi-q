"""OneFS API client wrapper for SmartQuota Manager."""

import urllib3
import importlib
import pkgutil
import re
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from urllib.parse import urlparse
from src.logger import log_info, log_error, log_warning

# Suppress urllib3 warnings for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Status(Enum):
    """Quota status based on usage percentage."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class QuotaEntry:
    """Represents a single quota entry from OneFS."""
    id: str
    path: str
    hard_limit_bytes: int
    soft_limit_bytes: int
    usage_bytes: int
    users: List[str]
    groups: List[str]
    access_zone: str
    comment: str = ""
    
    @property
    def usage_percent(self) -> float:
        if not self.hard_limit_bytes: return 0.0
        return (self.usage_bytes / self.hard_limit_bytes) * 100
    
    @property
    def status(self) -> Status:
        pct = self.usage_percent
        if pct > 95: return Status.CRITICAL
        if pct >= 80: return Status.WARNING
        return Status.HEALTHY
    
    @property
    def hard_limit_gb(self) -> float:
        return self.hard_limit_bytes / (1024 ** 3)
    
    @property
    def soft_limit_gb(self) -> float:
        return self.soft_limit_bytes / (1024 ** 3)
    
    @property
    def usage_gb(self) -> float:
        return self.usage_bytes / (1024 ** 3)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "hard_limit_gb": round(self.hard_limit_gb, 2),
            "soft_limit_gb": round(self.soft_limit_gb, 2),
            "usage_gb": round(self.usage_gb, 2),
            "usage_percent": round(self.usage_percent, 1),
            "status": self.status.value,
            "users": "; ".join(self.users) if self.users else "-",
            "groups": "; ".join(self.groups) if self.groups else "-",
            "access_zone": self.access_zone,
            "comment": self.comment,
        }


def _match_path_to_zone(path: str, zones_info: Dict[str, str]) -> str:
    """
    Match a quota path to the correct access zone based on longest path prefix match.
    
    OneFS zones have base paths like:
    - System: /ifs
    - Zone1: /ifs/data/zone1
    - Zone2: /ifs/data/zone2
    
    A quota path like /ifs/data/zone1/project1 should match Zone1.
    """
    # Normalize the path
    norm_path = path.rstrip("/")
    if not norm_path.startswith("/ifs"):
        norm_path = f"/ifs/{norm_path.lstrip('/')}"
    
    # Build sorted zones list (longest path first for best match)
    sorted_zones = []
    for name, zone_base in zones_info.items():
        norm_base = zone_base.rstrip("/")
        if not norm_base.startswith("/ifs"):
            norm_base = f"/ifs/{norm_base.lstrip('/')}"
        sorted_zones.append((name, norm_base))
    sorted_zones.sort(key=lambda x: len(x[1]), reverse=True)
    
    # Find best matching zone (longest prefix match)
    for zone_name, zone_path in sorted_zones:
        # Exact match or path is under zone's base path
        if norm_path == zone_path or norm_path.startswith(f"{zone_path}/"):
            return zone_name
    
    # Default to System
    return "System"


class IsilonAPI:
    """Wrapper for Isilon SDK API interactions."""
    
    @staticmethod
    def format_url(input_url: str) -> str:
        """Construct a full OneFS API URL from IP, hostname, or partial URL."""
        if not input_url: return ""
        # Clean the input: remove leading slashes/colons and browser paths
        url = input_url.strip()
        url = re.sub(r'^[:/]+', '', url)
        
        if not url.lower().startswith("http"):
            url = f"https://{url}"
        
        # Parse and reconstruct to ensure only scheme://host:port
        p = urlparse(url)
        host_part = p.netloc or p.path.split('/')[0]
        
        # Ensure port 8080 if none specified
        if ":" not in host_part:
            host_part = f"{host_part}:8080"
            
        return f"{p.scheme or 'https'}://{host_part}"

    def __init__(self, cluster_url: str, username: str, password: str, verify_ssl: bool = True):
        self.cluster_url = self.format_url(cluster_url)
        self.verify_ssl = verify_ssl
        
        try:
            # 1. Resolve base SDK package
            try:
                import isi_sdk as sdk_base
            except ImportError:
                import isilon_sdk as sdk_base
            
            # 2. Check for versioned subpackages (typical in 0.7.0+)
            sdk = sdk_base
            for loader, mod_name, is_pkg in pkgutil.iter_modules(sdk_base.__path__, sdk_base.__name__ + '.'):
                if 'v9_' in mod_name or 'v8_' in mod_name:
                    try:
                        sdk = importlib.import_module(mod_name)
                        log_info(f"Using versioned SDK subpackage: {mod_name}")
                        break
                    except: continue

            self._models = {}
            
            # 3. Universal Component Discovery
            # We search for classes in the current sdk module and its models/api subpackages
            def find_component(name_patterns: List[str]):
                """Search package submodules for a class matching patterns."""
                # Check current sdk module first
                for p in name_patterns:
                    if hasattr(sdk, p): return getattr(sdk, p)
                
                # Search common subpackage locations
                subpkgs = ['models', 'api', 'rest']
                for sub in subpkgs:
                    try:
                        m = importlib.import_module(f"{sdk.__name__}.{sub}")
                        for p in name_patterns:
                            if hasattr(m, p): return getattr(m, p)
                    except: continue
                
                # Last resort: Deep walk (only if not found yet)
                for loader, mod_name, is_pkg in pkgutil.walk_packages(sdk.__path__, sdk.__name__ + '.'):
                    if 'models' in mod_name or 'api' in mod_name:
                        try:
                            m = importlib.import_module(mod_name)
                            for p in name_patterns:
                                if hasattr(m, p): return getattr(m, p)
                        except: continue
                return None

            # Find Models (Expanded patterns for 0.7.0 and older versions)
            self._models["entry"] = find_component(["QuotaQuota", "QuotaEntry", "QuotaQuotaEntry"])
            self._models["limits"] = find_component(["QuotaQuotaThresholds", "QuotaThresholds", "QuotaLimits"])
            self._models["quota"] = find_component(["QuotaQuotaCreateParams", "QuotaQuota", "QuotaQuotaCreate"])
            
            if not all(self._models.values()):
                missing = [k for k, v in self._models.items() if not v]
                raise ImportError(f"Missing SDK Models: {missing}. Checked in {sdk.__name__}")

            # Find APIs & Config
            ConfigClass = find_component(["Configuration"])
            ApiClientClass = find_component(["ApiClient"])
            QuotaApiClass = find_component(["QuotaApi"])
            SharesApiClass = find_component(["SharesApi"])
            NamespaceApiClass = find_component(["NamespaceApi"])
            ProtocolsApiClass = find_component(["ProtocolsApi"])
            SnapshotApiClass = find_component(["SnapshotApi"])
            ZonesApiClass = find_component(["ZonesApi"])

            if not all([ConfigClass, ApiClientClass, QuotaApiClass]):
                raise ImportError(f"Could not locate core SDK API classes in {sdk.__name__}")

            # Initialize
            self.configuration = ConfigClass()
            self.configuration.host = self.cluster_url
            self.configuration.username = username
            self.configuration.password = password
            self.configuration.verify_ssl = self.verify_ssl
            
            api_client = ApiClientClass(self.configuration)
            self.quota_api = QuotaApiClass(api_client)
            self.shares_api = SharesApiClass(api_client) if SharesApiClass else None
            self.namespaces_api = NamespaceApiClass(api_client) if NamespaceApiClass else None
            self.protocols_api = ProtocolsApiClass(api_client) if ProtocolsApiClass else None
            self.snapshot_api = SnapshotApiClass(api_client) if SnapshotApiClass else None
            self.zones_api = ZonesApiClass(api_client) if ZonesApiClass else None

            # --- AUTH VERIFICATION ---
            # Perform a lightweight call to verify credentials immediately
            try:
                # Try getting cluster identity or a simple quota list limit 1
                method = getattr(self.quota_api, "list_quota_quotas", None) or getattr(self.quota_api, "list_quotas")
                method(limit=1)
                log_info(f"SDK connected and verified for user {username}")
            except Exception as e:
                if "401" in str(e) or "Unauthorized" in str(e):
                    raise ValueError("Authentication Failed: Username or password incorrect.")
                raise RuntimeError(f"Connection verification failed: {e}")

        except Exception as e:
            log_error("SDK Initialization Failed", e)
            raise

    def _map_quota_response(self, q: Any, default_zone: Optional[str] = None) -> QuotaEntry:
        # Robust mapping for nested PAPI objects (0.7.0 uses 'thresholds', older uses 'limits')
        lims = getattr(q, "thresholds", None) or getattr(q, "limits", None)
        usage_obj = getattr(q, "usage", None)
        
        # Determine usage: try fslogical first (often most accurate for users), then logical, then physical
        usage_val = 0
        if usage_obj:
            # Check for various PAPI usage fields
            usage_val = (getattr(usage_obj, "fslogical", 0) or 
                         getattr(usage_obj, "logical", 0) or 
                         getattr(usage_obj, "physical", 0) or 0)
        
        # Extract zone - try multiple attribute names and locations
        zone = (getattr(q, "zone", None) or 
                getattr(q, "access_zone", None) or 
                getattr(q, "zone_name", None) or
                getattr(q, "az", None) or
                getattr(q, "_zone", None) or
                default_zone)
        
        # If still no zone, try to extract from nested objects
        if not zone:
            # Some SDKs nest zone info
            for attr in ["properties", "attrs", "metadata", "info"]:
                nested = getattr(q, attr, None)
                if nested:
                    zone = (getattr(nested, "zone", None) or 
                           getattr(nested, "access_zone", None))
                    if zone: break
        
        # If no zone found, leave as System for now - will be corrected in list_all_quotas
        zone = zone or "System"
        
        # Debug: log raw quota attributes if zone looks wrong
        if zone == "System":
            # Check if there's zone info hidden elsewhere
            all_attrs = [a for a in dir(q) if not a.startswith('_')]
            zone_attrs = [a for a in all_attrs if 'zone' in a.lower()]
            if zone_attrs:
                for za in zone_attrs[:3]:  # Log first 3
                    val = getattr(q, za, None)
                    if val and val != "System":
                        log_info(f"Found zone attribute '{za}' = '{val}' on quota {q.id}")
                        zone = val
                        break
                         
        return QuotaEntry(
            id=q.id, path=q.path,
            hard_limit_bytes=getattr(lims, "hard", 0) or 0,
            soft_limit_bytes=getattr(lims, "soft", 0) or 0,
            usage_bytes=usage_val,
            users=getattr(q, "users", []) or [],
            groups=getattr(q, "groups", []) or [],
            access_zone=zone,
            comment=getattr(q, "comment", ""),
        )

    def get_all_paths(self) -> Dict[str, Dict[str, Any]]:
        """
        Get ALL filesystem paths from SMB shares and NFS exports across ALL zones.
        Returns a dict mapping path -> {protocol, zone, quota_info}.
        """
        all_paths = {}  # path -> {protocol, zone, quota_info}
        
        zones = self.list_access_zones()
        log_info(f"Getting all paths from {len(zones)} zones")
        
        for zone in zones:
            # SMB Shares - try both method names
            if self.shares_api:
                smb_success = False
                for method_name in ["list_smb_shares", "list_smb_share"]:
                    method = getattr(self.shares_api, method_name, None)
                    if method:
                        try:
                            resp = method(zone=zone)
                            shares = getattr(resp, "shares", None) or resp
                            for s in shares:
                                path = (getattr(s, "path", None) or getattr(s, "name", "") or "").rstrip("/")
                                if path:
                                    if path not in all_paths:
                                        all_paths[path] = {"protocol": "", "zone": zone, "quota": None, "quota_id": None}
                                    current = all_paths[path]["protocol"]
                                    all_paths[path]["protocol"] = "SMB" if not current else f"{current}, SMB"
                            smb_success = True
                            break  # Success, no need to try other method
                        except Exception:
                            continue  # Try next method name
                if not smb_success:
                    log_warning(f"SMB listing failed for zone {zone}: no working method found")
            
            # NFS Exports - try both method names
            if self.protocols_api:
                nfs_success = False
                for method_name in ["list_nfs_exports", "list_nfs_export"]:
                    method = getattr(self.protocols_api, method_name, None)
                    if method:
                        try:
                            resp = method(zone=zone)
                            exports = getattr(resp, "exports", None) or resp
                            for e in exports:
                                paths = getattr(e, "paths", []) or []
                                for p in paths:
                                    path = p.rstrip("/")
                                    if path:
                                        if path not in all_paths:
                                            all_paths[path] = {"protocol": "", "zone": zone, "quota": None, "quota_id": None}
                                        current = all_paths[path]["protocol"]
                                        all_paths[path]["protocol"] = "NFS" if not current else f"{current}, NFS"
                            nfs_success = True
                            break  # Success, no need to try other method
                        except Exception:
                            continue  # Try next method name
                if not nfs_success:
                    log_warning(f"NFS listing failed for zone {zone}: no working method found")
        
        log_info(f"Found {len(all_paths)} unique paths across all zones")
        return all_paths

    def list_quotas(self, path: Optional[str] = None, access_zone: Optional[str] = None, limit: int = 1000, token: Optional[str] = None) -> Tuple[List[QuotaEntry], Optional[str]]:
        try:
            params = {"limit": limit}
            if path: params["path"] = path
            if token: params["continue"] = token
            
            # 0.7.0 uses list_quota_quotas, older uses list_quotas
            method = getattr(self.quota_api, "list_quota_quotas", None) or getattr(self.quota_api, "list_quotas")
            
            # Track whether zone filtering was successfully applied
            zone_filtered = False
            zone_param_used = None
            
            # Try to pass zone parameter - different SDKs use different names
            zone_params_to_try = ["zone", "zones", "zone_name", "access_zone", "az"]
            
            for zone_param in zone_params_to_try:
                try:
                    p = params.copy()
                    if access_zone and access_zone != "All": p[zone_param] = access_zone
                    resp = method(**p)
                    zone_filtered = True
                    zone_param_used = zone_param
                    break
                except TypeError:
                    continue
            
            if not zone_filtered:
                # No zone parameter supported by this API version
                resp = method(**params)
                log_warning(f"Zone parameter not supported by quota API, fetching all quotas without zone filter")
            else:
                log_info(f"Zone filtering used: param={zone_param_used}, zone={access_zone}")
            
            # Pass the requested zone to _map_quota_response so it can use it as fallback
            effective_zone = access_zone if zone_filtered else None
            return [self._map_quota_response(q, default_zone=effective_zone) for q in resp.quotas], getattr(resp, "continue", None)
        except Exception as e:
            raise RuntimeError(f"API Error: {e}")

    def list_all_quotas(self, path: Optional[str] = None, access_zone: Optional[str] = None) -> List[QuotaEntry]:
        """Fetch all quotas. Iterates through all zones if access_zone is 'All' or None."""
        all_q = []
        seen_ids = set()  # Track seen quota IDs to avoid duplicates
        
        # Determine which zones to query
        zones_info = self.get_access_zones_info()
        log_info(f"Discovered zones: {zones_info}")
        
        if access_zone and access_zone != "All":
            zones_to_query = [access_zone]
        else:
            zones_to_query = list(zones_info.keys())

        log_info(f"Fetching quotas from zones: {zones_to_query}")

        # Aggregate quotas from all zones
        for zone in zones_to_query:
            token = None
            zone_quotas = []
            iteration = 0
            max_iterations = 100  # Safety limit for pagination
            
            while iteration < max_iterations:
                iteration += 1
                try:
                    qs, token = self.list_quotas(path, access_zone=zone, token=token)
                    
                    for q in qs:
                        # Skip duplicates
                        if q.id in seen_ids:
                            continue
                        seen_ids.add(q.id)
                        
                        # Ensure zone is set correctly for each quota
                        # Use the zone from API response if valid, otherwise use path-based matching
                        q_zone = q.access_zone
                        
                        # If zone is System or not in known zones, use path-based matching
                        if q_zone == "System" or q_zone not in zones_info:
                            q_zone = _match_path_to_zone(q.path, zones_info)
                        
                        q.access_zone = q_zone
                        zone_quotas.append(q)
                        
                except Exception as e:
                    log_warning(f"Failed to fetch quotas for zone {zone}: {e}")
                    break
                
                if not token:
                    break
            
            log_info(f"Fetched {len(zone_quotas)} quotas from zone {zone}")
            all_q.extend(zone_quotas)

        # Final pass: ensure all quotas have correct zone assignment using path matching
        inferred_count = 0
        for q in all_q:
            if q.access_zone == "System":
                q_zone = _match_path_to_zone(q.path, zones_info)
                if q_zone != "System":
                    q.access_zone = q_zone
                    inferred_count += 1
        
        if inferred_count:
            log_info(f"Inferred {inferred_count} zones from paths via path matching")
        
        # Also check if any quota has zone info that we can use to infer zone paths
        # This helps if zones were discovered but paths were wrong
        quota_zones = set(q.access_zone for q in all_q if q.access_zone != "System")
        if quota_zones:
            log_info(f"Zones found in quota data: {quota_zones}")
        
        log_info(f"Total quotas fetched: {len(all_q)}")
        return all_q

    def get_access_zones_info(self) -> Dict[str, str]:
        """Returns a mapping of Zone Name -> Base Path. Tries multiple API paths for discovery."""
        data = {"System": "/ifs"}
        
        # Helper to extract zone name and path from various object types
        def extract_zone(obj) -> Tuple[Optional[str], Optional[str]]:
            # Try different attribute patterns for zone name
            name = getattr(obj, "name", None) or getattr(obj, "zonename", None) or getattr(obj, "zone_name", None)
            if not name: return None, None
            
            # Try different attribute patterns for zone path
            path = (getattr(obj, "path", None) or 
                    getattr(obj, "base_path", None) or
                    getattr(obj, "basepath", None) or
                    getattr(obj, "zone_path", None) or
                    getattr(obj, "ifs_path", None))
            return name, path
        
        def merge_zones(zones_iterable):
            """Merge zone entries into data dict, handling duplicates."""
            if not zones_iterable: return
            for z in zones_iterable:
                name, path = extract_zone(z)
                if name and path:
                    if name == "System" and (not path or path == "/"): path = "/ifs"
                    data[name] = path
        
        # 1. Try Zones API (Modern OneFS 8.x/9.x)
        if self.zones_api:
            try:
                # v9.x uses list_zones, get_zones, or list_access_zones
                for method_name in ["list_zones", "get_zones", "list_access_zones", "get_access_zones"]:
                    method = getattr(self.zones_api, method_name, None)
                    if method:
                        try:
                            resp = method()
                            # Response can be { "zones": [...] } or { "access_zones": [...] }
                            # or direct list/array response
                            zones = (getattr(resp, "zones", None) or 
                                    getattr(resp, "access_zones", None) or
                                    getattr(resp, "items", None) or
                                    resp if isinstance(resp, (list, tuple)) else None)
                            if zones:
                                merge_zones(zones)
                                if len(data) > 1:  # Found real zones, no need for fallbacks
                                    break
                        except Exception:
                            continue
            except Exception as e:
                log_warning(f"Zones API discovery failed: {e}")

        # 2. Try Namespaces API (Legacy/Specific Versions)
        if self.namespaces_api:
            try:
                for method_name in ["get_access_zones", "list_access_zones", "get_zones", "list_zones"]:
                    method = getattr(self.namespaces_api, method_name, None)
                    if method:
                        try:
                            resp = method()
                            zones = (getattr(resp, "access_zones", None) or 
                                    getattr(resp, "zones", None) or
                                    getattr(resp, "items", None) or
                                    resp if isinstance(resp, (list, tuple)) else None)
                            if zones:
                                merge_zones(zones)
                                if len(data) > 1:
                                    break
                        except Exception:
                            continue
            except Exception as e:
                log_warning(f"Namespaces zone discovery failed: {e}")

        # 3. Try Protocols API (often has access to zone list)
        if self.protocols_api:
            try:
                for method_name in ["list_access_zones", "get_access_zones", "list_zones", "get_zones"]:
                    method = getattr(self.protocols_api, method_name, None)
                    if method:
                        try:
                            resp = method()
                            zones = (getattr(resp, "zones", []) or 
                                    getattr(resp, "access_zones", []) or
                                    getattr(resp, "items", []) or
                                    resp if isinstance(resp, (list, tuple)) else [])
                            if zones:
                                merge_zones(zones)
                                if len(data) > 1:
                                    break
                        except Exception:
                            continue
            except Exception as e:
                log_warning(f"Protocols zone discovery failed: {e}")

        # 4. Try Quota API - extract zones from quota responses (ALWAYS run as supplement)
        try:
            method = getattr(self.quota_api, "list_quota_quotas", None) or getattr(self.quota_api, "list_quotas", None)
            if method:
                # Try without zone filter to see all zones
                resp = method(limit=100)
                if hasattr(resp, "quotas") and resp.quotas:
                    # First pass: extract zones from quota zone attributes
                    zone_names = set()
                    for q in resp.quotas:
                        zone = (getattr(q, "zone", None) or 
                               getattr(q, "access_zone", None) or
                               getattr(q, "zone_name", None))
                        if zone and zone != "System" and zone != "":
                            zone_names.add(zone)
                    
                    # Second pass: extract potential zones from paths
                    # e.g., /ifs/zone1/data -> zone1
                    path_zones = set()
                    for q in resp.quotas:
                        q_path = getattr(q, "path", "") or ""
                        if q_path.startswith("/ifs/"):
                            # Extract second path component as potential zone
                            # /ifs/zone1/data -> zone1
                            parts = q_path.strip("/").split("/")
                            if len(parts) >= 2 and parts[0] == "ifs":
                                potential_zone = parts[1]
                                # Only add if it's not a common directory name
                                # Being conservative - only exclude very common ones
                                if potential_zone not in ["ifs", "data"]:
                                    path_zones.add(potential_zone)
                    
                    # Merge discovered zones (only add if not already in data)
                    all_discovered = zone_names | path_zones
                    for z in all_discovered:
                        if z and z != "System":
                            # Use existing path if available, otherwise construct from zone name
                            if z not in data:
                                data[z] = f"/ifs/{z}"
        except Exception as e:
            log_warning(f"Quota-based zone discovery failed: {e}")

        return data

    def list_access_zones(self) -> List[str]:
        return list(self.get_access_zones_info().keys())

    def debug_zone_discovery(self) -> Dict[str, Any]:
        """Debug function to understand zone discovery. Returns raw data for diagnosis."""
        debug_info = {
            "zones_api_available": self.zones_api is not None,
            "namespaces_api_available": self.namespaces_api is not None,
            "protocols_api_available": self.protocols_api is not None,
            "quota_api_available": self.quota_api is not None,
            "zones_info": {},
            "sample_quotas": [],
        }
        
        # Try Zones API
        if self.zones_api:
            for method_name in ["list_zones", "get_zones", "list_access_zones", "get_access_zones"]:
                method = getattr(self.zones_api, method_name, None)
                if method:
                    try:
                        resp = method()
                        zones = (getattr(resp, "zones", None) or 
                                getattr(resp, "access_zones", None) or
                                getattr(resp, "items", None) or
                                resp if isinstance(resp, (list, tuple)) else None)
                        if zones:
                            debug_info["zones_api_method"] = method_name
                            debug_info["zones_api_response"] = str(zones)[:1000]
                            break
                    except Exception as e:
                        debug_info[f"zones_api_{method_name}_error"] = str(e)
        
        # Try Quota API - get sample quotas
        try:
            method = getattr(self.quota_api, "list_quota_quotas", None) or getattr(self.quota_api, "list_quotas")
            resp = method(limit=5)
            if hasattr(resp, "quotas") and resp.quotas:
                for q in list(resp.quotas)[:3]:
                    sample = {
                        "id": getattr(q, "id", "N/A"),
                        "path": getattr(q, "path", "N/A"),
                        "zone_attr": getattr(q, "zone", "NOT_FOUND"),
                        "access_zone_attr": getattr(q, "access_zone", "NOT_FOUND"),
                        "zone_name_attr": getattr(q, "zone_name", "NOT_FOUND"),
                        "raw_attrs": {a: str(getattr(q, a, "N/A"))[:100] for a in dir(q) if not a.startswith('_') and 'zone' in a.lower()[:200]}
                    }
                    debug_info["sample_quotas"].append(sample)
        except Exception as e:
            debug_info["quota_sample_error"] = str(e)
        
        # Get final zones_info
        debug_info["zones_info"] = self.get_access_zones_info()
        
        return debug_info

    def get_raw_quota(self, quota_id: str) -> Dict[str, Any]:
        """Fetch raw quota dictionary for the Dynamic Grid."""
        try:
            # 0.7.0 uses get_quota_quota, older uses get_quota_entry
            method = getattr(self.quota_api, "get_quota_quota", None) or getattr(self.quota_api, "get_quota_entry")
            resp = method(quota_id)
            return resp.to_dict() if hasattr(resp, "to_dict") else {}
        except Exception as e:
            raise RuntimeError(f"Fetch failed: {e}")

    def update_quota_dynamic(self, quota_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            update_obj = self._models["entry"]()
            for k, v in payload.items():
                # Handle thresholds vs limits
                if (k == "limits" or k == "thresholds") and isinstance(v, dict):
                    lims = self._models["limits"]()
                    for lk, lv in v.items():
                        if hasattr(lims, lk): setattr(lims, lk, int(float(lv)))
                    setattr(update_obj, k, lims)
                elif hasattr(update_obj, k):
                    setattr(update_obj, k, v)
            
            # 0.7.0 uses update_quota_quota, older uses update_quota_entry
            method = getattr(self.quota_api, "update_quota_quota", None) or getattr(self.quota_api, "update_quota_entry")
            resp = method(quota_id, update_obj)
            return resp.to_dict() if hasattr(resp, "to_dict") else {}
        except Exception as e:
            raise RuntimeError(f"Update Failed: {e}")

    def create_quota(self, path: str, q_type: str, limits: Dict[str, float], access_zone: str = "System", enforced: bool = True, snapshots: bool = False) -> str:
        """Create new quota. Only sets non-zero limits to avoid unintended overwrites."""
        try:
            q_limits = self._models["limits"]()
            if limits.get("hard"): q_limits.hard = int(round(limits["hard"] * (1024**3)))
            if limits.get("soft"): q_limits.soft = int(round(limits["soft"] * (1024**3)))
            if limits.get("advisory"): q_limits.advisory = int(round(limits["advisory"] * (1024**3)))
            
            # 0.7.0 uses 'thresholds', older uses 'limits'
            params = {
                "path": path, "type": q_type, 
                "enforced": enforced, "include_snapshots": snapshots, "zone": access_zone
            }
            if hasattr(self._models["quota"](), "thresholds"):
                params["thresholds"] = q_limits
            else:
                params["limits"] = q_limits
                
            q_body = self._models["quota"](**params)
            
            # 0.7.0 uses create_quota_quota, older uses create_quota
            method = getattr(self.quota_api, "create_quota_quota", None) or getattr(self.quota_api, "create_quota")
            resp = method(q_body)
            return resp.id
        except Exception as e:
            raise RuntimeError(f"Create Failed: {e}")

    def delete_quota(self, quota_id: str) -> bool:
        try:
            # 0.7.0 uses delete_quota_quota, older uses delete_quota_entry
            method = getattr(self.quota_api, "delete_quota_quota", None) or getattr(self.quota_api, "delete_quota_entry")
            method(quota_id)
            return True
        except Exception as e:
            raise RuntimeError(f"Delete Failed: {e}")

    def get_snapshots_for_path(self, path: str) -> List[Dict[str, Any]]:
        """List snapshots, sorted newest first."""
        if not self.snapshot_api: return []
        try:
            resp = self.snapshot_api.list_snapshots(path=path)
            snaps = [{
                "id": s.id, "name": s.name, "created_epoch": s.created,
                "created": datetime.fromtimestamp(s.created).strftime('%Y-%m-%d %H:%M:%S') if s.created else "N/A",
                "size": getattr(s, "size", 0)
            } for s in resp.snapshots]
            snaps.sort(key=lambda x: x["created_epoch"] or 0, reverse=True)
            return snaps
        except Exception: return []

    def get_acl_for_path(self, path: str, zone: str = "System") -> Dict[str, Any]:
        """Fetch ACL from Namespace API with explicit zone support."""
        if not self.namespaces_api: return {"error": "Namespace API not available"}
        try:
            ifs_path = path if path.startswith("/ifs") else f"/ifs/{path.lstrip('/')}"
            resp = self.namespaces_api.get_acl(ifs_path, zone=zone)
            return resp.to_dict() if hasattr(resp, "to_dict") else {}
        except Exception as e: return {"error": str(e)}
