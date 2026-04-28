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
    HEALTHY = "healthy"      # <80%
    WARNING = "warning"      # 80-95%
    CRITICAL = "critical"    # >95%


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
        """Calculate usage percentage."""
        if self.hard_limit_bytes == 0:
            return 0.0
        return (self.usage_bytes / self.hard_limit_bytes) * 100
    
    @property
    def status(self) -> Status:
        """Determine quota status."""
        pct = self.usage_percent
        if pct > 95:
            return Status.CRITICAL
        elif pct >= 80:
            return Status.WARNING
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
        """Convert to dictionary for UI display."""
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
    
    def __init__(
        self,
        cluster_url: str,
        username: str,
        password: str,
        verify_ssl: bool = True,
    ):
        self.cluster_url = cluster_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        
        try:
            import isi_sdk
            self.sdk = isi_sdk
            # Target v9_12_0 models specifically
            try:
                from isi_sdk.v9_12_0.models.quota_entry import QuotaEntry as SDKQuotaEntry
                from isi_sdk.v9_12_0.models.quota_limits import QuotaLimits
                from isi_sdk.v9_12_0.models.quota_quota import QuotaQuota
                self._models = {"entry": SDKQuotaEntry, "limits": QuotaLimits, "quota": QuotaQuota}
            except ImportError:
                from isi_sdk.models.quota_entry import QuotaEntry as SDKQuotaEntry
                from isi_sdk.models.quota_limits import QuotaLimits
                from isi_sdk.models.quota_quota import QuotaQuota
                self._models = {"entry": SDKQuotaEntry, "limits": QuotaLimits, "quota": QuotaQuota}
        except ImportError:
            raise ImportError("isilon-sdk not installed. Run: pip install isilon-sdk")
        
        self.configuration = self.sdk.Configuration()
        self.configuration.host = self.cluster_url
        self.configuration.username = self.username
        self.configuration.password = self.password
        self.configuration.verify_ssl = self.verify_ssl
        
        api_client = self.sdk.ApiClient(self.configuration)
        self.quota_api = self.sdk.QuotaApi(api_client)
        self.shares_api = self.sdk.SharesApi(api_client)
        self.namespaces_api = self.sdk.NamespaceApi(api_client)
        self.protocols_api = self.sdk.ProtocolsApi(api_client)
        self.snapshot_api = self.sdk.SnapshotApi(api_client)

    def _map_quota_response(self, q: Any) -> QuotaEntry:
        """Helper to map PAPI quota response to internal QuotaEntry."""
        return QuotaEntry(
            id=q.id,
            path=q.path,
            hard_limit_bytes=q.limits.hard or 0,
            soft_limit_bytes=q.limits.soft or 0,
            usage_bytes=q.usage.inclusive or 0,
            users=q.users or [],
            groups=q.groups or [],
            access_zone=q.zone or "System",
            comment=getattr(q, "comment", ""),
        )

    def get_protocol_mapping(self, access_zone: str = "System") -> Dict[str, str]:
        """Map paths to protocols (SMB/NFS)."""
        mapping = {}
        try:
            smb = self.shares_api.list_smb_shares(zone=access_zone)
            for s in smb.shares:
                mapping[s.path] = "SMB"
            
            nfs = self.protocols_api.list_nfs_exports(zone=access_zone)
            for e in nfs.exports:
                for p in e.paths:
                    mapping[p] = (mapping.get(p, "") + ", NFS").lstrip(", ")
        except Exception:
            pass
        return mapping

    def list_quotas(
        self,
        path: Optional[str] = None,
        access_zone: Optional[str] = None,
        limit: int = 1000,
        continue_token: Optional[str] = None,
    ) -> Tuple[List[QuotaEntry], Optional[str]]:
        """List quotas with pagination."""
        try:
            params = {"limit": limit}
            if path: params["path"] = path
            if access_zone: params["zones"] = access_zone
            if continue_token: params["continue"] = continue_token
            
            resp = self.quota_api.list_quotas(**params)
            return [self._map_quota_response(q) for q in resp.quotas], getattr(resp, "continue", None)
        except Exception as e:
            raise RuntimeError(f"API Error: {e}")

    def list_all_quotas(self, path: Optional[str] = None, access_zone: Optional[str] = None) -> List[QuotaEntry]:
        """Fetch all quotas following continue tokens."""
        all_q = []
        token = None
        while True:
            qs, token = self.list_quotas(path, access_zone, continue_token=token)
            all_q.extend(qs)
            if not token or len(all_q) > 10000: break # Safety cap
        return all_q

    def update_quota_dynamic(self, quota_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update any quota field dynamically."""
        try:
            update_obj = self._models["entry"]()
            for k, v in payload.items():
                if k == "limits" and isinstance(v, dict):
                    lims = self._models["limits"]()
                    for lk, lv in v.items():
                        if hasattr(lims, lk): setattr(lims, lk, int(lv))
                    setattr(update_obj, k, lims)
                elif hasattr(update_obj, k):
                    setattr(update_obj, k, v)
            
            resp = self.quota_api.update_quota_entry(quota_id, update_obj)
            return resp.to_dict() if hasattr(resp, "to_dict") else {}
        except Exception as e:
            raise RuntimeError(f"Dynamic Update Failed: {e}")

    def create_quota(self, path: str, type: str, hard_gb: float, access_zone: str = "System") -> str:
        """Create new quota."""
        try:
            lims = self._models["limits"](hard=int(round(hard_gb * (1024**3))))
            q = self._models["quota"](path=path, type=type, limits=lims, enforced=True, zone=access_zone)
            resp = self.quota_api.create_quota(q)
            return resp.id
        except Exception as e:
            raise RuntimeError(f"Create Failed: {e}")

    def delete_quota(self, quota_id: str) -> bool:
        """Delete quota entry."""
        try:
            self.quota_api.delete_quota_entry(quota_id)
            return True
        except Exception as e:
            raise RuntimeError(f"Delete Failed: {e}")

    def get_snapshots_for_path(self, path: str) -> List[Dict[str, Any]]:
        """List associated snapshots."""
        try:
            resp = self.snapshot_api.list_snapshots(path=path)
            return [{
                "id": s.id, "name": s.name, 
                "created": datetime.fromtimestamp(s.created).strftime('%Y-%m-%d %H:%M:%S'),
                "size": getattr(s, "size", 0)
            } for s in resp.snapshots]
        except Exception:
            return []

    def get_acl_for_path(self, path: str) -> Dict[str, Any]:
        """Fetch ACL from Namespace API."""
        try:
            ifs_path = path if path.startswith("/ifs") else f"/ifs/{path.lstrip('/')}"
            resp = self.namespaces_api.get_acl(ifs_path)
            return resp.to_dict() if hasattr(resp, "to_dict") else {}
        except Exception as e:
            return {"error": str(e)}

    def list_access_zones(self) -> List[str]:
        """List cluster access zones."""
        try:
            resp = self.namespaces_api.get_access_zones()
            return [z.name for z in resp.access_zones]
        except Exception:
            return ["System"]
