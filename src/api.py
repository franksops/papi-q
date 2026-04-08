"""OneFS API client wrapper for SmartQuota Manager."""

import urllib3
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

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
            return 100.0
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
        """Get hard limit in GB."""
        return self.hard_limit_bytes / (1024 ** 3)
    
    @property
    def soft_limit_gb(self) -> float:
        """Get soft limit in GB."""
        return self.soft_limit_bytes / (1024 ** 3)
    
    @property
    def usage_gb(self) -> float:
        """Get current usage in GB."""
        return self.usage_bytes / (1024 ** 3)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for UI display."""
        return {
            "id": self.id,
            "path": self.path,
            "hard_limit_gb": round(self.hard_limit_gb, 2),
            "soft_limit_gb": round(self.soft_limit_gb, 2),
            "usage_gb": round(self.usage_gb, 2),
            "usage_percent": round(self.usage_percent, 2),
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
        max_retries: int = 3,
    ):
        """
        Initialize the API client.
        
        Args:
            cluster_url: Base URL of the cluster (e.g., https://cluster.example.com:8080)
            username: AD or local cluster username
            password: Cluster password
            verify_ssl: Whether to validate SSL certificates
            max_retries: Maximum retry attempts for failed requests
        """
        self.cluster_url = cluster_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.max_retries = max_retries
        
        # ImportOneFS SDK here to handle missing dependency gracefully
        try:
            import isi_sdk
        except ImportError:
            raise ImportError(
                "isilon-sdk not installed. Run: pip install isilon-sdk"
            )
        
        # Configure SDK client
        self.configuration = isi_sdk.Configuration()
        self.configuration.host = self.cluster_url
        self.configuration.username = self.username
        self.configuration.password = self.password
        self.configuration.verify_ssl = self.verify_ssl
        self.configuration.ssl_ca_cert = None  # No CA cert by default
        
        # Initialize API clients
        self.quota_api = isi_sdk.QuotaApi(isi_sdk.ApiClient(self.configuration))
        self.shares_api = isi_sdk.SharesApi(isi_sdk.ApiClient(self.configuration))
        self.namespaces_api = isi_sdk.NamespaceApi(isi_sdk.ApiClient(self.configuration))
    
    def get_quota_for_path(self, path: str, access_zone: str = "system") -> Optional[QuotaEntry]:
        """
        Get quota information for a specific path.
        
        Args:
            path: The filesystem path to query
            access_zone: The access zone (default: "system")
        
        Returns:
            QuotaEntry if found, None otherwise
        """
        try:
            # List quotas for the path
            response = self.quota_api.list_quotas(
                path=path,
                zones=access_zone,
            )
            
            if response and response.quotas:
                quota = response.quotas[0]
                return QuotaEntry(
                    id=quota.id,
                    path=quota.path,
                    hard_limit_bytes=quota.limits.hard or 0,
                    soft_limit_bytes=quota.limits.soft or 0,
                    usage_bytes=quota.usage.inclusive or 0,
                    users=quota.users or [],
                    groups=quota.groups or [],
                    access_zone=quota.zone or "system",
                    comment=quota.comment or "",
                )
            return None
        except Exception as e:
            raise RuntimeError(f"Failed to get quota for path {path}: {e}")
    
    def get_quota_by_id(self, quota_id: str) -> Optional[QuotaEntry]:
        """
        Get quota information by ID.
        
        Args:
            quota_id: The quota entry ID
        
        Returns:
            QuotaEntry if found, None otherwise
        """
        try:
            response = self.quota_api.get_quota_entry(quota_id)
            if response:
                return QuotaEntry(
                    id=response.id,
                    path=response.path,
                    hard_limit_bytes=response.limits.hard or 0,
                    soft_limit_bytes=response.limits.soft or 0,
                    usage_bytes=response.usage.inclusive or 0,
                    users=response.users or [],
                    groups=response.groups or [],
                    access_zone=response.zone or "system",
                    comment=response.comment or "",
                )
            return None
        except Exception as e:
            raise RuntimeError(f"Failed to get quota {quota_id}: {e}")
    
    def list_quotas(
        self,
        path: Optional[str] = None,
        access_zone: Optional[str] = None,
        limit: int = 1000,
        continue_token: Optional[str] = None,
    ) -> Tuple[List[QuotaEntry], Optional[str]]:
        """
        List quotas with pagination support.
        
        Args:
            path: Filter by path prefix
            access_zone: Filter by access zone
            limit: Maximum entries to return
            continue_token: Token for next page (from previous response)
        
        Returns:
            Tuple of (quotas list, next continue token)
        """
        try:
            # Build query parameters
            params = {"limit": limit}
            if path:
                params["path"] = path
            if access_zone:
                params["zones"] = access_zone
            if continue_token:
                params["continue"] = continue_token
            
            response = self.quota_api.list_quotas(**params)
            
            quotas = []
            for q in response.quotas:
                quotas.append(QuotaEntry(
                    id=q.id,
                    path=q.path,
                    hard_limit_bytes=q.limits.hard or 0,
                    soft_limit_bytes=q.limits.soft or 0,
                    usage_bytes=q.usage.inclusive or 0,
                    users=q.users or [],
                    groups=q.groups or [],
                    access_zone=q.zone or "system",
                    comment=q.comment or "",
                ))
            
            next_token = getattr(response, "continue", None)
            return quotas, next_token
        except Exception as e:
            raise RuntimeError(f"Failed to list quotas: {e}")
    
    def get_share_path(self, share_name: str, access_zone: str = "system") -> Optional[str]:
        """
        Get the filesystem path for a share.
        
        Args:
            share_name: The SMB/NFS share name
            access_zone: The access zone (default: "system")
        
        Returns:
            Filesystem path if found, None otherwise
        """
        try:
            response = self.shares_api.get_smb_shares(
                zones=access_zone,
                names=[share_name],
            )
            if response and response.shares:
                return response.shares[0].path
            return None
        except Exception as e:
            raise RuntimeError(f"Failed to get share {share_name}: {e}")
    
    def update_quota(
        self,
        quota_id: str,
        hard_limit_gb: Optional[float] = None,
        soft_limit_gb: Optional[float] = None,
        apply_to_children: bool = False,
    ) -> QuotaEntry:
        """
        Update a quota entry.
        
        Args:
            quota_id: The quota entry ID
            hard_limit_gb: New hard limit in GB (optional)
            soft_limit_gb: New soft limit in GB (optional)
            apply_to_children: Whether to apply to child quotas
        
        Returns:
            Updated QuotaEntry
        """
        try:
            # Import SDK types
            import isi_sdk
            from isi_sdk.v9_12_0.models.quota_entry import QuotaEntry as SDKQuotaEntry
            from isi_sdk.v9_12_0.models.quota_limits import QuotaLimits
            
            # Build limits object
            limits = QuotaLimits()
            if hard_limit_gb is not None:
                limits.hard = int(hard_limit_gb * (1024 ** 3))
            if soft_limit_gb is not None:
                limits.soft = int(soft_limit_gb * (1024 ** 3))
            
            # Build quota entry
            quota = SDKQuotaEntry(limits=limits)
            
            # Update the quota
            response = self.quota_api.update_quota_entry(
                quota_id,
                quota,
                recursive=apply_to_children,
            )
            
            return QuotaEntry(
                id=response.id,
                path=response.path,
                hard_limit_bytes=response.limits.hard or 0,
                soft_limit_bytes=response.limits.soft or 0,
                usage_bytes=response.usage.inclusive or 0,
                users=response.users or [],
                groups=response.groups or [],
                access_zone=response.zone or "system",
                comment=response.comment or "",
            )
        except Exception as e:
            raise RuntimeError(f"Failed to update quota {quota_id}: {e}")
    
    def list_access_zones(self) -> List[str]:
        """
        Get list of available access zones.
        
        Returns:
            List of access zone names
        """
        try:
            response = self.namespaces_api.get_access_zones()
            if response:
                return [zone.name for zone in response.access_zones]
            return ["system", "local"]
        except Exception:
            # Default zones if API fails
            return ["system", "local"]
