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

            log_info(f"SDK connected to {self.cluster_url} for user {username}")

        except Exception as e:
            log_error("SDK Initialization Failed", e)
            raise ImportError(f"SDK Error: {e}")

    def _map_quota_response(self, q: Any) -> QuotaEntry:
        # Robust mapping for nested PAPI objects (0.7.0 uses 'thresholds', older uses 'limits')
        lims = getattr(q, "thresholds", None) or getattr(q, "limits", None)
        usage = getattr(q, "usage", None)
        return QuotaEntry(
            id=q.id, path=q.path,
            hard_limit_bytes=getattr(lims, "hard", 0) or 0,
            soft_limit_bytes=getattr(lims, "soft", 0) or 0,
            usage_bytes=getattr(usage, "logical", 0) or getattr(usage, "inclusive", 0) or 0,
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
                                mapping[s.path] = "SMB"
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
                                    current = mapping.get(p, "")
                                    mapping[p] = "SMB, NFS" if current == "SMB" else "NFS"
                    except Exception as e:
                        log_warning(f"NFS mapping failed for zone {zone}: {e}")
        except Exception as e:
            log_warning(f"Protocol mapping failed: {e}")
        return mapping

    def list_quotas(self, path: Optional[str] = None, limit: int = 1000, token: Optional[str] = None) -> Tuple[List[QuotaEntry], Optional[str]]:
        try:
            params = {"limit": limit}
            if path: params["path"] = path
            if token: params["continue"] = token
            
            # 0.7.0 uses list_quota_quotas, older uses list_quotas
            method = getattr(self.quota_api, "list_quota_quotas", None) or getattr(self.quota_api, "list_quotas")
            resp = method(**params)
            
            return [self._map_quota_response(q) for q in resp.quotas], getattr(resp, "continue", None)
        except Exception as e:
            raise RuntimeError(f"API Error: {e}")

    def list_all_quotas(self, path: Optional[str] = None, access_zone: Optional[str] = None) -> List[QuotaEntry]:
        """Fetch all quotas cluster-wide and map them to their respective Access Zones."""
        all_q, token = [], None
        while True:
            qs, token = self.list_quotas(path, token=token)
            all_q.extend(qs)
            if not token or len(all_q) > 10000: break
        
        # Enrich quotas with Zone info based on path
        zones_info = self.get_access_zones_info()
        # Sort zones by path length descending to match most specific path first
        sorted_zones = sorted(zones_info.items(), key=lambda x: len(x[1]), reverse=True)
        
        for q in all_q:
            # Only override if it's currently 'System' or the API didn't provide it
            if q.access_zone == "System":
                for zone_name, zone_path in sorted_zones:
                    if q.path.startswith(zone_path):
                        q.access_zone = zone_name
                        break
        
        # Manual filtering if access_zone was requested
        if access_zone and access_zone != "All":
            all_q = [q for q in all_q if q.access_zone == access_zone]
            
        return all_q

    def get_access_zones_info(self) -> Dict[str, str]:
        """Returns a mapping of Zone Name -> Base Path."""
        if not self.namespaces_api: return {"System": "/ifs"}
        try:
            resp = self.namespaces_api.get_access_zones()
            return {z.name: z.path for z in resp.access_zones}
        except Exception: return {"System": "/ifs"}

    def list_access_zones(self) -> List[str]:
        return list(self.get_access_zones_info().keys())
