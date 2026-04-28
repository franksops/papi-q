"""OneFS API client wrapper for SmartQuota Manager."""

import urllib3
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

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
        url = input_url.strip().lower()
        if not url.startswith("http"):
            url = f"https://{url}"
        if ":" not in url.split("//")[-1]:
            url = f"{url}:8080"
        return url

    def __init__(self, cluster_url: str, username: str, password: str, verify_ssl: bool = True):
        self.cluster_url = self.format_url(cluster_url)
        try:
            try:
                import isi_sdk as sdk_module
            except ImportError:
                import isilon_sdk as sdk_module
            
            self.sdk = sdk_module
            # Dynamically load models
            try:
                # Try v9_12_0 path first
                from sdk_module.v9_12_0.models.quota_entry import QuotaEntry as SDKQuotaEntry
                from sdk_module.v9_12_0.models.quota_limits import QuotaLimits
                from sdk_module.v9_12_0.models.quota_quota import QuotaQuota
                self._models = {"entry": SDKQuotaEntry, "limits": QuotaLimits, "quota": QuotaQuota}
            except ImportError:
                # Fallback to base models
                SDKQuotaEntry = getattr(sdk_module.models.quota_entry, "QuotaEntry")
                QuotaLimits = getattr(sdk_module.models.quota_limits, "QuotaLimits")
                QuotaQuota = getattr(sdk_module.models.quota_quota, "QuotaQuota")
                self._models = {"entry": SDKQuotaEntry, "limits": QuotaLimits, "quota": QuotaQuota}
        except Exception as e:
            raise ImportError(f"isilon-sdk is installed but modules (isi_sdk/isilon_sdk) are inaccessible: {e}")
        
        self.configuration = self.sdk.Configuration()
        self.configuration.host = self.cluster_url
        self.configuration.username = username
        self.configuration.password = password
        self.configuration.verify_ssl = self.verify_ssl
        
        api_client = self.sdk.ApiClient(self.configuration)
        self.quota_api = self.sdk.QuotaApi(api_client)
        self.shares_api = self.sdk.SharesApi(api_client)
        self.namespaces_api = self.sdk.NamespaceApi(api_client)
        self.protocols_api = self.sdk.ProtocolsApi(api_client)
        self.snapshot_api = self.sdk.SnapshotApi(api_client)

    def _map_quota_response(self, q: Any) -> QuotaEntry:
        # Robust mapping for nested PAPI objects
        lims = getattr(q, "limits", None)
        usage = getattr(q, "usage", None)
        return QuotaEntry(
            id=q.id, path=q.path,
            hard_limit_bytes=getattr(lims, "hard", 0) or 0,
            soft_limit_bytes=getattr(lims, "soft", 0) or 0,
            usage_bytes=getattr(usage, "inclusive", 0) or 0,
            users=getattr(q, "users", []) or [],
            groups=getattr(q, "groups", []) or [],
            access_zone=getattr(q, "zone", "System") or "System",
            comment=getattr(q, "comment", ""),
        )

    def get_protocol_mapping(self, access_zone: str = "System") -> Dict[str, str]:
        mapping = {}
        try:
            smb = self.shares_api.list_smb_shares(zone=access_zone)
            for s in smb.shares: mapping[s.path] = "SMB"
            nfs = self.protocols_api.list_nfs_exports(zone=access_zone)
            for e in nfs.exports:
                for p in e.paths: mapping[p] = (mapping.get(p, "") + ", NFS").lstrip(", ")
        except Exception: pass
        return mapping

    def list_quotas(self, path: Optional[str] = None, access_zone: Optional[str] = None, limit: int = 1000, token: Optional[str] = None) -> Tuple[List[QuotaEntry], Optional[str]]:
        try:
            params = {"limit": limit}
            if path: params["path"] = path
            if access_zone: params["zones"] = access_zone
            if token: params["continue"] = token
            resp = self.quota_api.list_quotas(**params)
            return [self._map_quota_response(q) for q in resp.quotas], getattr(resp, "continue", None)
        except Exception as e:
            raise RuntimeError(f"API Error: {e}")

    def list_all_quotas(self, path: Optional[str] = None, access_zone: Optional[str] = None) -> List[QuotaEntry]:
        all_q, token = [], None
        while True:
            qs, token = self.list_quotas(path, access_zone, token=token)
            all_q.extend(qs)
            if not token or len(all_q) > 10000: break
        return all_q

    def get_raw_quota(self, quota_id: str) -> Dict[str, Any]:
        """Fetch raw quota dictionary for the Dynamic Grid."""
        try:
            resp = self.quota_api.get_quota_entry(quota_id)
            return resp.to_dict() if hasattr(resp, "to_dict") else {}
        except Exception as e:
            raise RuntimeError(f"Fetch failed: {e}")

    def update_quota_dynamic(self, quota_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            update_obj = self._models["entry"]()
            for k, v in payload.items():
                if k == "limits" and isinstance(v, dict):
                    lims = self._models["limits"]()
                    for lk, lv in v.items():
                        if hasattr(lims, lk): setattr(lims, lk, int(float(lv)))
                    setattr(update_obj, k, lims)
                elif hasattr(update_obj, k):
                    setattr(update_obj, k, v)
            resp = self.quota_api.update_quota_entry(quota_id, update_obj)
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
            
            q_body = self._models["quota"](
                path=path, type=q_type, limits=q_limits, 
                enforced=enforced, include_snapshots=snapshots, zone=access_zone
            )
            resp = self.quota_api.create_quota(q_body)
            return resp.id
        except Exception as e:
            raise RuntimeError(f"Create Failed: {e}")

    def delete_quota(self, quota_id: str) -> bool:
        try:
            self.quota_api.delete_quota_entry(quota_id)
            return True
        except Exception as e:
            raise RuntimeError(f"Delete Failed: {e}")

    def get_snapshots_for_path(self, path: str) -> List[Dict[str, Any]]:
        """List snapshots, sorted newest first."""
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
        try:
            ifs_path = path if path.startswith("/ifs") else f"/ifs/{path.lstrip('/')}"
            resp = self.namespaces_api.get_acl(ifs_path, zone=zone)
            return resp.to_dict() if hasattr(resp, "to_dict") else {}
        except Exception as e: return {"error": str(e)}

    def list_access_zones(self) -> List[str]:
        try:
            resp = self.namespaces_api.get_access_zones()
            return [z.name for z in resp.access_zones]
        except Exception: return ["System"]
