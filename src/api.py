"""OneFS API client wrapper for SmartQuota Manager."""

import urllib3
import importlib
import pkgutil
import os
import re
import sys
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

            self.sdk = sdk
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

    def _map_quota_response(self, q: Any) -> QuotaEntry:
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
                         
        return QuotaEntry(
            id=q.id, path=q.path,
            hard_limit_bytes=getattr(lims, "hard", 0) or 0,
            soft_limit_bytes=getattr(lims, "soft", 0) or 0,
            usage_bytes=usage_val,
            users=getattr(q, "users", []) or [],
            groups=getattr(q, "groups", []) or [],
            access_zone=getattr(q, "zone", "System") or "System",
            comment=getattr(q, "comment", ""),
        )

    def get_protocol_mapping(self) -> Dict[str, str]:
        """Fetch all SMB shares and NFS exports from ALL zones and map paths to protocols."""
        mapping = {}
        try:
            zones = self.list_access_zones()
            for zone in zones:
                # Map SMB Shares
                if self.shares_api:
                    try:
                        # Some versions might require different arguments or have different response formats
                        method = getattr(self.shares_api, "list_smb_shares", None)
                        if method:
                            smb = method(zone=zone)
                            for s in smb.shares:
                                mapping[s.path.rstrip("/")] = "SMB"
                    except Exception as e:
                        log_warning(f"SMB mapping failed for zone {zone}: {e}")
                
                # Map NFS Exports
                if self.protocols_api:
                    try:
                        method = getattr(self.protocols_api, "list_nfs_exports", None)
                        if method:
                            nfs = method(zone=zone)
                            for e in nfs.exports:
                                for p in e.paths:
                                    normalized_p = p.rstrip("/")
                                    current = mapping.get(normalized_p, "")
                                    mapping[normalized_p] = "SMB, NFS" if current == "SMB" else "NFS"
                    except Exception as e:
                        log_warning(f"NFS mapping failed for zone {zone}: {e}")
        except Exception as e:
            log_warning(f"Protocol mapping failed: {e}")
        return mapping

    def list_quotas(self, path: Optional[str] = None, access_zone: Optional[str] = None, limit: int = 1000, token: Optional[str] = None) -> Tuple[List[QuotaEntry], Optional[str]]:
        try:
            params = {"limit": limit}
            if path: params["path"] = path
            if token: params["continue"] = token
            
            # 0.7.0 uses list_quota_quotas, older uses list_quotas
            method = getattr(self.quota_api, "list_quota_quotas", None) or getattr(self.quota_api, "list_quotas")
            
            # Try to pass zone parameter - try multiple names as SDKs vary
            try:
                # Attempt 1: 'zone' (common in 0.7.0+)
                p = params.copy()
                if access_zone and access_zone != "All": p["zone"] = access_zone
                resp = method(**p)
            except TypeError:
                try:
                    # Attempt 2: 'zones' (sometimes used for multi-zone query)
                    p = params.copy()
                    if access_zone and access_zone != "All": p["zones"] = access_zone
                    resp = method(**p)
                except TypeError:
                    # Attempt 3: No zone parameter supported, fallback to System
                    resp = method(**params)
            
            # Map with fallback zone info
            fallback = access_zone if access_zone and access_zone != "All" else "System"
            return [self._map_quota_response(q) for q in resp.quotas], getattr(resp, "continue", None)
        except Exception as e:
            raise RuntimeError(f"API Error: {e}")

    def list_all_quotas(self, path: Optional[str] = None, access_zone: Optional[str] = None) -> List[QuotaEntry]:
        """Fetch all quotas. Iterates through all zones if access_zone is 'All' or None."""
        all_q = []
        
        # Determine which zones to query
        zones_info = self.get_access_zones_info()
        if access_zone and access_zone != "All":
            zones_to_query = [access_zone]
        else:
            zones_to_query = list(zones_info.keys())

        # Aggregate quotas from all zones
        for zone in zones_to_query:
            token = None
            zone_quotas = []
            while True:
                try:
                    qs, token = self.list_quotas(path, access_zone=zone, token=token)
                    # Manually ensure zone is set correctly for mapping
                    for q in qs:
                        if q.access_zone == "System" and zone != "System":
                            q.access_zone = zone
                    zone_quotas.extend(qs)
                except Exception as e:
                    log_warning(f"Failed to fetch quotas for zone {zone}: {e}")
                    break
                if not token or len(zone_quotas) > 10000: break
            all_q.extend(zone_quotas)
        
        # Deduplicate by ID just in case
        unique_q = {q.id: q for q in all_q}
        all_q = list(unique_q.values())

        # Enrichment step for any that still say System but match a sub-path
        sorted_zones = []
        for name, p in zones_info.items():
            norm_p = p.rstrip("/")
            if not norm_p.startswith("/ifs"): norm_p = f"/ifs/{norm_p.lstrip('/')}"
            sorted_zones.append((name, norm_p))
        sorted_zones.sort(key=lambda x: len(x[1]), reverse=True)
        
        for q in all_q:
            if q.access_zone == "System":
                q_path = q.path.rstrip("/")
                if not q_path.startswith("/ifs"): q_path = f"/ifs/{q_path.lstrip('/')}"
                for zone_name, zone_path in sorted_zones:
                    if q_path == zone_path or q_path.startswith(f"{zone_path}/"):
                        q.access_zone = zone_name
                        break
            
        return all_q

    def get_access_zones_info(self) -> Dict[str, str]:
        """Returns a mapping of Zone Name -> Base Path. Tries multiple API paths for discovery."""
        data = {"System": "/ifs"}
        
        # 1. Try Zones API (Modern OneFS 8.x/9.x)
        if self.zones_api:
            try:
                # v9.x uses list_zones or get_zones
                method = getattr(self.zones_api, "list_zones", None) or getattr(self.zones_api, "get_zones", None)
                if method:
                    resp = method()
                    # Response can be { "zones": [...] } or { "access_zones": [...] }
                    zones = getattr(resp, "zones", None) or getattr(resp, "access_zones", None)
                    if zones:
                        for z in zones:
                            path = getattr(z, "path", "")
                            if z.name == "System" and (not path or path == "/"): path = "/ifs"
                            if z.name and path: data[z.name] = path
            except Exception as e:
                log_warning(f"Zones discovery failed: {e}")

        # 2. Try Namespaces API (Legacy/Specific Versions)
        if len(data) <= 1 and self.namespaces_api:
            try:
                method = getattr(self.namespaces_api, "get_access_zones", None) or getattr(self.namespaces_api, "list_access_zones", None)
                if method:
                    resp = method()
                    zones = getattr(resp, "access_zones", None) or getattr(resp, "zones", None)
                    if zones:
                        for z in zones:
                            path = getattr(z, "path", "")
                            if z.name == "System" and (not path or path == "/"): path = "/ifs"
                            if z.name and path: data[z.name] = path
            except Exception as e:
                log_warning(f"Namespaces zone discovery failed: {e}")

        # 3. Try Protocols API (often has access to zone list via a different path)
        if len(data) <= 1 and self.protocols_api:
            try:
                # Some SDK versions have list_access_zones here
                method = getattr(self.protocols_api, "list_access_zones", None) or getattr(self.protocols_api, "get_access_zones", None)
                if method:
                    resp = method()
                    zones = getattr(resp, "zones", []) or getattr(resp, "access_zones", [])
                    for z in zones:
                        path = getattr(z, "path", "")
                        if z.name == "System" and (not path or path == "/"): path = "/ifs"
                        if z.name and path: data[z.name] = path
            except Exception as e:
                log_warning(f"Protocols zone discovery failed: {e}")

        return data

    def list_access_zones(self) -> List[str]:
        return list(self.get_access_zones_info().keys())

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
