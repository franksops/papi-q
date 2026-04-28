#!/usr/bin/env python3
"""
SmartQuota Manager - Universal Single-File Distribution
OneFS 9.12.0.1 Optimized
"""
import sys
import os
import subprocess
import platform
import shutil
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import csv
import time
from datetime import datetime
from pathlib import Path

def run_command(cmd, shell=False):
    """Run a shell command and return success."""
    try:
        subprocess.check_call(cmd, shell=shell)
        return True
    except subprocess.CalledProcessError:
        return False

def bootstrap():
    """Ensure all system and python dependencies are met."""
    system = platform.system().lower()
    missing_deps = []
    
    try:
        import streamlit
        import isi_sdk
        import pandas
        import urllib3
    except ImportError:
        missing_deps = ["isilon-sdk", "streamlit", "pandas", "urllib3", "python-dotenv"]

    if not missing_deps:
        return True

    print(f"\n[!] Missing Python dependencies: {', '.join(missing_deps)}")
    choice = input("Would you like to attempt auto-installation? [y/N]: ").lower()
    if choice != 'y':
        print("Installation cancelled. Please run: pip install " + " ".join(missing_deps))
        sys.exit(1)

    # 1. System Level Installation
    if system == "darwin": # macOS
        if not shutil.which("brew"):
            print("[*] Homebrew not found. Please install Homebrew: https://brew.sh/")
        else:
            print("[*] macOS detected. Ensuring python3 is available via brew...")
            run_command(["brew", "install", "python"])
    
    elif system == "linux":
        if shutil.which("apt-get"):
            print("[*] Debian/Ubuntu detected. Installing pip...")
            run_command(["sudo", "apt-get", "update", "-y"])
            run_command(["sudo", "apt-get", "install", "-y", "python3-pip"])
        elif shutil.which("dnf"):
            print("[*] RHEL/CentOS/Fedora detected. Installing pip...")
            run_command(["sudo", "dnf", "install", "-y", "python3-pip"])
        elif shutil.which("yum"):
            print("[*] Older RHEL/CentOS detected. Installing pip...")
            run_command(["sudo", "yum", "install", "-y", "python3-pip"])

    # 2. Python Level Installation
    print("[*] Installing python dependencies via pip...")
    pip_cmd = [sys.executable, "-m", "pip", "install"] + missing_deps
    if not run_command(pip_cmd):
        print("[!] Pip installation failed. Trying with --user...")
        run_command(pip_cmd + ["--user"])

    print("\n[+] Dependencies installed successfully. Re-launching...\n")
    return True

# Run Bootstrapper
if "__main__" == __name__ and not os.environ.get("STREAMLIT_RUNNING"):
    bootstrap()
    os.environ["STREAMLIT_RUNNING"] = "1"
    # Ensure we use the streamlit module to run the script
    subprocess.run([sys.executable, "-m", "streamlit", "run", __file__])
    sys.exit(0)

# Import dependencies after bootstrap
import streamlit as st
import pandas as pd
import urllib3
try:
    import isi_sdk
except ImportError:
    pass # Handled by bootstrap, but needed for type hinting/imports in main body

# --- APP LOGIC START ---

# --- Source: src/config.py ---


import json
import os
from pathlib import Path
from typing import Dict, Any, Optional


# Default paths
DEFAULT_CONFIG_DIR = Path.home() / ".papi-q"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_CLUSTERS_FILE = DEFAULT_CONFIG_DIR / "clusters.json"
DEFAULT_AUDIT_LOG = Path.home() / "isilon_admin_audit.csv"


def ensure_config_dir() -> Path:
    """Create the config directory if it doesn't exist."""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_CONFIG_DIR


def load_config() -> Dict[str, Any]:
    """Load configuration from config.json, creating defaults if missing."""
    ensure_config_dir()
    
    config = {
        "verify_ssl": False,
        "log_file": str(DEFAULT_AUDIT_LOG),
        "max_retries": 3,
        "cache_ttl_seconds": 60,
    }
    
    if DEFAULT_CONFIG_FILE.exists():
        try:
            with open(DEFAULT_CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                config.update(loaded)
        except json.JSONDecodeError:
            # Corrupt config, use defaults
            pass
    
    return config


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to config.json."""
    ensure_config_dir()
    with open(DEFAULT_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def load_clusters() -> Dict[str, str]:
    """Load cluster definitions from clusters.json."""
    if not DEFAULT_CLUSTERS_FILE.exists():
        return {}
    
    try:
        with open(DEFAULT_CLUSTERS_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def save_clusters(clusters: Dict[str, str]) -> None:
    """Save cluster definitions to clusters.json."""
    ensure_config_dir()
    with open(DEFAULT_CLUSTERS_FILE, "w") as f:
        json.dump(clusters, f, indent=2)


def get_cluster_url(cluster_name: str) -> Optional[str]:
    """Get the API URL for a cluster by name."""
    clusters = load_clusters()
    return clusters.get(cluster_name)


def add_cluster(name: str, url: str) -> bool:
    """Add a new cluster to the configuration."""
    clusters = load_clusters()
    clusters[name] = url
    save_clusters(clusters)
    return True


def remove_cluster(name: str) -> bool:
    """Remove a cluster from the configuration."""
    clusters = load_clusters()
    if name in clusters:
        del clusters[name]
        save_clusters(clusters)
        return True
    return False


# --- Source: src/api.py ---


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
        
        # Import OneFS SDK here to handle missing dependency gracefully
        try:
            import isi_sdk
            # We specifically target v9_12_0 models if available, but fallback to base if not
            try:
                from isi_sdk.v9_12_0.models.quota_entry import QuotaEntry as SDKQuotaEntry
                from isi_sdk.v9_12_0.models.quota_limits import QuotaLimits
                self._sdk_models_version = "v9_12_0"
            except ImportError:
                # Fallback to standard models if version-specific ones aren't found
                from isi_sdk.models.quota_entry import QuotaEntry as SDKQuotaEntry
                from isi_sdk.models.quota_limits import QuotaLimits
                self._sdk_models_version = "default"
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
        self.protocols_api = isi_sdk.ProtocolsApi(isi_sdk.ApiClient(self.configuration))
        self.snapshot_api = isi_sdk.SnapshotApi(isi_sdk.ApiClient(self.configuration))
    
    def get_protocol_mapping(self, access_zone: str = "system") -> Dict[str, str]:
        """
        Get a mapping of paths to protocols (SMB/NFS).
        
        Returns:
            Dictionary mapping path -> protocol string (e.g. "SMB", "NFS", "SMB, NFS")
        """
        mapping = {}
        try:
            # Get SMB shares
            smb_response = self.shares_api.list_smb_shares(zone=access_zone)
            for share in smb_response.shares:
                path = share.path
                mapping[path] = "SMB"
            
            # Get NFS exports
            nfs_response = self.protocols_api.list_nfs_exports(zone=access_zone)
            for export in nfs_response.exports:
                for path in export.paths:
                    if path in mapping:
                        mapping[path] += ", NFS"
                    else:
                        mapping[path] = "NFS"
        except Exception:
            pass # Gracefully handle if some protocols aren't licensed/accessible
        return mapping
    
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
    
    def list_all_quotas(
        self,
        path: Optional[str] = None,
        access_zone: Optional[str] = None,
        max_entries: int = 5000,
    ) -> List[QuotaEntry]:
        """
        List all quotas by automatically following continue tokens.
        
        Args:
            path: Filter by path prefix
            access_zone: Filter by access zone
            max_entries: Safety cap for total entries
        
        Returns:
            List of all QuotaEntry objects
        """
        all_quotas = []
        continue_token = None
        
        while len(all_quotas) < max_entries:
            quotas, continue_token = self.list_quotas(
                path=path,
                access_zone=access_zone,
                limit=1000,
                continue_token=continue_token
            )
            all_quotas.extend(quotas)
            
            if not continue_token:
                break
        
        return all_quotas
    
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
            # We use the models imported or defined during __init__
            import isi_sdk
            
            # Use appropriate model based on version
            if self._sdk_models_version == "v9_12_0":
                from isi_sdk.v9_12_0.models.quota_entry import QuotaEntry as SDKQuotaEntry
                from isi_sdk.v9_12_0.models.quota_limits import QuotaLimits
            else:
                from isi_sdk.models.quota_entry import QuotaEntry as SDKQuotaEntry
                from isi_sdk.models.quota_limits import QuotaLimits
            
            # Build limits object
            limits = QuotaLimits()
            if hard_limit_gb is not None:
                # Ensure integer bytes for PAPI compatibility
                limits.hard = int(round(hard_limit_gb * (1024 ** 3)))
            if soft_limit_gb is not None:
                limits.soft = int(round(soft_limit_gb * (1024 ** 3)))
            
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
    
    def get_raw_quota(self, quota_id: str) -> Dict[str, Any]:
        """Get the full raw dictionary representation of a quota."""
        try:
            response = self.quota_api.get_raw_quota_entry(quota_id)
            # The SDK might return a model, convert to dict
            if hasattr(response, "to_dict"):
                return response.to_dict()
            return response
        except Exception as e:
            # Fallback if get_raw_quota_entry is not available in this SDK version
            try:
                response = self.quota_api.get_quota_entry(quota_id)
                return response.to_dict() if hasattr(response, "to_dict") else response
            except Exception:
                raise RuntimeError(f"Failed to get raw quota {quota_id}: {e}")

    def get_snapshots_for_path(self, path: str) -> List[Dict[str, Any]]:
        """List snapshots associated with a specific path."""
        try:
            # PAPI list_snapshots can filter by path
            response = self.snapshot_api.list_snapshots(path=path)
            snapshots = []
            for s in response.snapshots:
                snapshots.append({
                    "id": s.id,
                    "name": s.name,
                    "created": datetime.fromtimestamp(s.created).strftime('%Y-%m-%d %H:%M:%S') if hasattr(s, "created") else "N/A",
                    "path": s.path,
                    "size": getattr(s, "size", 0),
                })
            return snapshots
        except Exception as e:
            # Silently return empty if Snapshot API fails (e.g. no permissions)
            return []

    def get_acl_for_path(self, path: str, access_zone: str = "system") -> Dict[str, Any]:
        """Get the Access Control List for a path."""
        try:
            # Use Namespace API to get ACL
            # Path usually needs to be formatted or relative to /ifs
            ifs_path = path if path.startswith("/ifs") else f"/ifs/{path.lstrip('/')}"
            response = self.namespaces_api.get_acl(ifs_path)
            if hasattr(response, "to_dict"):
                return response.to_dict()
            return response
        except Exception as e:
            return {"error": str(e), "note": "ACL retrieval requires Namespace API access"}

    def update_quota_dynamic(self, quota_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update a quota using a dynamic dictionary of properties."""
        try:
            import isi_sdk
            # Dynamically determine the model
            if self._sdk_models_version == "v9_12_0":
                from isi_sdk.v9_12_0.models.quota_entry import QuotaEntry as SDKQuotaEntry
            else:
                from isi_sdk.models.quota_entry import QuotaEntry as SDKQuotaEntry
            
            # Create a blank update object
            update_obj = SDKQuotaEntry()
            
            # Map dictionary keys to object attributes
            for key, value in payload.items():
                if hasattr(update_obj, key):
                    # Handle nested objects like 'limits' if they are dicts
                    if key == "limits" and isinstance(value, dict):
                        if self._sdk_models_version == "v9_12_0":
                            from isi_sdk.v9_12_0.models.quota_limits import QuotaLimits
                        else:
                            from isi_sdk.models.quota_limits import QuotaLimits
                        limits_obj = QuotaLimits()
                        for l_key, l_val in value.items():
                            if hasattr(limits_obj, l_key):
                                setattr(limits_obj, l_key, l_val)
                        setattr(update_obj, key, limits_obj)
                    else:
                        setattr(update_obj, key, value)
            
            response = self.quota_api.update_quota_entry(quota_id, update_obj)
            return response.to_dict() if hasattr(response, "to_dict") else response
        except Exception as e:
            raise RuntimeError(f"Dynamic update failed: {e}")

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

    def create_quota(
        self,
        path: str,
        type: str = "directory",
        hard_limit_gb: float = 0,
        soft_limit_gb: float = 0,
        access_zone: str = "system",
        enforced: bool = True,
        include_snapshots: bool = False,
    ) -> str:
        """Create a new quota and return its ID."""
        try:
            import isi_sdk
            # Dynamically determine the model
            if self._sdk_models_version == "v9_12_0":
                from isi_sdk.v9_12_0.models.quota_quota import QuotaQuota
                from isi_sdk.v9_12_0.models.quota_limits import QuotaLimits
            else:
                from isi_sdk.models.quota_quota import QuotaQuota
                from isi_sdk.models.quota_limits import QuotaLimits

            limits = QuotaLimits(
                hard=int(round(hard_limit_gb * (1024**3))),
                soft=int(round(soft_limit_gb * (1024**3)))
            )
            
            quota = QuotaQuota(
                path=path,
                type=type,
                limits=limits,
                enforced=enforced,
                include_snapshots=include_snapshots,
                zone=access_zone
            )
            
            response = self.quota_api.create_quota(quota)
            return response.id
        except Exception as e:
            raise RuntimeError(f"Failed to create quota on {path}: {e}")

    def delete_quota(self, quota_id: str) -> bool:
        """Delete a quota entry."""
        try:
            self.quota_api.delete_quota_entry(quota_id)
            return True
        except Exception as e:
            raise RuntimeError(f"Failed to delete quota {quota_id}: {e}")


# --- Source: src/audit.py ---


import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional




AUDIT_FIELDS = [
    "timestamp",
    "admin",
    "cluster",
    "action",
    "share_name",
    "path",
    "old_limit_gb",
    "new_limit_gb",
]


def write_audit_entry(
    admin: str,
    cluster: str,
    action: str,
    share_name: str,
    path: str,
    old_limit_gb: float,
    new_limit_gb: float,
    log_file: Optional[str] = None,
) -> bool:
    """
    Write an audit log entry for a quota modification.
    """
    if log_file is None:
        # Create cluster-specific audit log file in the config directory
        from src.config import DEFAULT_CONFIG_DIR
        safe_cluster_name = "".join([c if c.isalnum() else "_" for c in cluster])
        datestamp = datetime.now().strftime("%m%d%Y")
        log_file = str(DEFAULT_CONFIG_DIR / f"{safe_cluster_name}_{datestamp}.csv")
    
    log_path = Path(log_file)
    
    # Ensure parent directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Build entry
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "admin": admin,
        "cluster": cluster,
        "action": action,
        "share_name": share_name,
        "path": path,
        "old_limit_gb": old_limit_gb,
        "new_limit_gb": new_limit_gb,
    }
    
    try:
        file_exists = log_path.exists()
        with open(log_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=AUDIT_FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(entry)
        return True
    except Exception as e:
        # Log to stderr for visibility
        print(f"AUDIT ERROR: {e}", flush=True)
        return False


def read_audit_log(
    cluster: Optional[str] = None,
    share_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    log_file: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Read audit log entries. Since logs are now daily, this reads the current day's log by default.
    """
    if log_file is None:
        if cluster:
            from src.config import DEFAULT_CONFIG_DIR
            safe_cluster_name = "".join([c if c.isalnum() else "_" for c in cluster])
            datestamp = datetime.now().strftime("%m%d%Y")
            log_file = str(DEFAULT_CONFIG_DIR / f"{safe_cluster_name}_{datestamp}.csv")
        else:
            log_file = load_config().get("log_file", str(DEFAULT_AUDIT_LOG))
    
    log_path = Path(log_file)
    if not log_path.exists():
        return []
    
    results = []
    try:
        with open(log_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Apply filters
                if cluster and row.get("cluster") and row["cluster"] != cluster:
                    continue
                if share_name and row.get("share_name") and share_name.lower() not in row["share_name"].lower():
                    continue
                
                # Convert numeric fields
                row["old_limit_gb"] = float(row["old_limit_gb"]) if row.get("old_limit_gb") else 0.0
                row["new_limit_gb"] = float(row["new_limit_gb"]) if row.get("new_limit_gb") else 0.0
                
                results.append(row)
        
        # Sort by timestamp (newest first for reading)
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results
    except Exception as e:
        print(f"READ AUDIT ERROR: {e}", flush=True)
        return []


def get_top_modifications(
    limit: int = 10,
    log_file: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get the most recent modifications from the audit log.
    
    Args:
        limit: Maximum number of entries to return
        log_file: Path to audit log file
    
    Returns:
        List of most recent audit entries
    """
    entries = read_audit_log(log_file=log_file)
    return entries[-limit:] if entries else []


# --- Source: src/utils.py ---


import re
from typing import List, Dict, Any, Optional, Tuple




def filter_quotas(
    quotas: List[QuotaEntry],
    share_name: Optional[str] = None,
    access_zone: Optional[str] = None,
    min_usage: Optional[float] = None,
    max_usage: Optional[float] = None,
) -> List[QuotaEntry]:
    """
    Filter quotas by various criteria.
    
    Args:
        quotas: List of QuotaEntry objects
        share_name: Filter by share name (partial match)
        access_zone: Filter by access zone (exact match)
        min_usage: Minimum usage percentage
        max_usage: Maximum usage percentage
    
    Returns:
        Filtered list of quotas
    """
    results = quotas
    
    if share_name:
        # Partial match on path (which contains share name)
        share_lower = share_name.lower()
        results = [q for q in results if share_lower in q.path.lower()]
    
    if access_zone:
        results = [q for q in results if q.access_zone == access_zone]
    
    if min_usage is not None:
        results = [q for q in results if q.usage_percent >= min_usage]
    
    if max_usage is not None:
        results = [q for q in results if q.usage_percent <= max_usage]
    
    return results


def get_top_offenders(
    quotas: List[QuotaEntry],
    thresholds: Tuple[int, int, int] = (90, 80, 70),
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group quotas by usage thresholds.
    
    Args:
        quotas: List of QuotaEntry objects
        thresholds: Tuple of threshold percentages (highest, middle, lowest)
    
    Returns:
        Dictionary mapping status categories to quota details
    """
    critical, warning, notice = thresholds
    
    categories = {
        "critical": [],  # > critical%
        "warning": [],   # warning%-critical%
        "notice": [],    # notice%-warning%
    }
    
    for quota in quotas:
        pct = quota.usage_percent
        detail = {
            "share_name": quota.path.split("/")[-1],
            "path": quota.path,
            "usage_percent": round(pct, 2),
            "hard_limit_gb": round(quota.hard_limit_gb, 2),
            "soft_limit_gb": round(quota.soft_limit_gb, 2),
        }
        
        if pct > critical:
            categories["critical"].append(detail)
        elif pct > warning:
            categories["warning"].append(detail)
        elif pct > notice:
            categories["notice"].append(detail)
    
    # Sort each category by usage percentage (descending)
    for cat in categories:
        categories[cat].sort(key=lambda x: x["usage_percent"], reverse=True)
    
    return categories


def paginate_list(
    items: List[Any],
    page: int = 1,
    page_size: int = 25,
) -> Tuple[List[Any], int]:
    """
    Paginate a list of items.
    
    Args:
        items: Full list of items
        page: Page number (1-indexed)
        page_size: Items per page
    
    Returns:
        Tuple of (page items, total pages)
    """
    if page < 1:
        page = 1
    
    start = (page - 1) * page_size
    end = start + page_size
    
    paginated = items[start:end]
    total_pages = (len(items) + page_size - 1) // page_size if items else 1
    
    return paginated, total_pages


def bytes_to_gb(value: int) -> float:
    """Convert bytes to GB."""
    return round(value / (1024 ** 3), 2)


def bytes_to_tb(value: int) -> float:
    """Convert bytes to TB."""
    return round(value / (1024 ** 4), 2)


def format_size(value: int) -> str:
    """Format byte value as human-readable string."""
    if value >= (1024 ** 4):  # TB
        return f"{bytes_to_tb(value):,.2f} TB"
    elif value >= (1024 ** 3):  # GB
        return f"{bytes_to_gb(value):,.2f} GB"
    elif value >= (1024 ** 2):  # MB
        return f"{round(value / (1024 ** 2), 2):,.2f} MB"
    elif value >= 1024:  # KB
        return f"{round(value / 1024, 2):,.2f} KB"
    else:
        return f"{value} bytes"


def escape_share_name(name: str) -> str:
    """
    Escape share name for path queries.
    Some characters need escaping in OneFS paths.
    """
    # Common share name issues
    escaped = name.replace("\\", "\\\\")
    return escaped


def parse_gb_to_bytes(value: float) -> int:
    """Parse GB value to bytes for API."""
    return int(value * (1024 ** 3))


def get_status_badge(status: Status) -> str:
    """Get status emoji for UI display."""
    mapping = {
        Status.HEALTHY: "🟢",
        Status.WARNING: "🟡",
        Status.CRITICAL: "🔴",
    }
    return mapping.get(status, "⚪")


# --- Source: src/ui/session.py ---


import streamlit as st
from typing import Optional, Dict, Any


def init_session() -> None:
    """Initialize session state variables."""
    if "api_client" not in st.session_state:
        st.session_state.api_client = None
    
    if "_clusters" not in st.session_state:
        st.session_state.clusters = {}
    
    if "current_cluster" not in st.session_state:
        st.session_state.current_cluster = None
    
    if "last_quota_list" not in st.session_state:
        st.session_state.last_quota_list = []
    
    if "selected_quotas" not in st.session_state:
        st.session_state.selected_quotas = []
    
    if "quota_cache" not in st.session_state:
        st.session_state.quota_cache = {}
    
    if "audit_log" not in st.session_state:
        st.session_state.audit_log = []
    
    if "admin_user" not in st.session_state:
        st.session_state.admin_user = None
    
    if "clusters_modified" not in st.session_state:
        st.session_state.clusters_modified = False


def get_api_client() -> Optional[Any]:
    """Get the current API client from session state."""
    return st.session_state.api_client


def set_api_client(client: Any) -> None:
    """Set the API client in session state."""
    st.session_state.api_client = client


def clear_api_client() -> None:
    """Clear the API client (logout)."""
    st.session_state.api_client = None
    st.session_state.current_cluster = None
    st.session_state.admin_user = None
    st.session_state.last_quota_list = []
    st.session_state.selected_quotas = []


def handle_api_error(error: Exception) -> bool:
    """
    Handle API errors, specifically 401 Unauthorized.
    Returns True if session was cleared.
    """
    error_str = str(error).lower()
    if "401" in error_str or "unauthorized" in error_str or "invalid credentials" in error_str:
        clear_api_client()
        st.error("🔒 Session expired or unauthorized. Please login again.")
        st.rerun()
        return True
    return False


def get_selected_quotas() -> list:
    """Get currently selected quotas."""
    return st.session_state.selected_quotas


def set_selected_quotas(quotas: list) -> None:
    """Set selected quotas."""
    st.session_state.selected_quotas = quotas


def get_cluster_name() -> Optional[str]:
    """Get current cluster name from URL."""
    if st.session_state.current_cluster:
        return st.session_state.current_cluster.split("://")[-1]
    return None


# --- Source: src/ui/components.py ---


import streamlit as st



import pandas as pd
from typing import List, Dict, Any


def status_badge(status: Status) -> str:
    """Get status emoji for UI display."""
    mapping = {
        Status.HEALTHY: "🟢",
        Status.WARNING: "🟡",
        Status.CRITICAL: "🔴",
    }
    return mapping.get(status, "⚪")


def color_for_status(status: Status) -> str:
    """Get color code for status."""
    mapping = {
        Status.HEALTHY: "#006837",  # Green (Pantone 3435)
        Status.WARNING: "#F58513",   # Orange (Pantone 158)
        Status.CRITICAL: "#D72638",  # Red for critical
    }
    return mapping.get(status, "#666666")


def format_bytes(bytes_val: int) -> str:
    """Format byte value as human-readable string."""
    if bytes_val >= (1024 ** 4):
        return f"{bytes_val / (1024 ** 4):,.2f} TB"
    elif bytes_val >= (1024 ** 3):
        return f"{bytes_val / (1024 ** 3):,.2f} GB"
    elif bytes_val >= (1024 ** 2):
        return f"{bytes_val / (1024 ** 2):,.2f} MB"
    elif bytes_val >= 1024:
        return f"{bytes_val / 1024:,.2f} KB"
    else:
        return f"{bytes_val} B"


def create_quota_table(
    quotas: List[QuotaEntry],
    key_prefix: str = "quota_table",
) -> List[QuotaEntry]:
    """
    Create a st.dataframe for quota entries with interactive features.
    
    Args:
        quotas: List of QuotaEntry objects
        key_prefix: Prefix for streamlit elements
    
    Returns:
        List of selected quota entries
    """
    if not quotas:
        st.info("No quotas found matching your criteria.")
        return []
    
    # Prepare data for DataFrame
    data = []
    for quota in quotas:
        data.append({
            "Share Name": quota.path.split("/")[-1],
            "Access Zone": quota.access_zone,
            "Path": quota.path,
            "Hard Limit (GB)": f"{quota.hard_limit_gb:.2f}",
            "Soft Limit (GB)": f"{quota.soft_limit_gb:.2f}",
            "Usage (GB)": f"{quota.usage_gb:.2f}",
            "Usage %": f"{quota.usage_percent:.1f}",
            "Status": f"{status_badge(quota.status)} {quota.status.value.upper()}",
        })
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Configure column settings
    column_config = {
        "Share Name": st.column_config.TextColumn("Share Name"),
        "Access Zone": st.column_config.TextColumn("Zone"),
        "Path": st.column_config.TextColumn("Path"),
        "Hard Limit (GB)": st.column_config.TextColumn("Hard Limit"),
        "Soft Limit (GB)": st.column_config.TextColumn("Soft Limit"),
        "Usage (GB)": st.column_config.TextColumn("Usage"),
        "Usage %": st.column_config.TextColumn("%"),
        "Status": st.column_config.TextColumn("Status"),
    }
    
    # Display table with selection
    selected = st.dataframe(
        df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        on_select="rows",
        selection_mode="multi",
        key=f"{key_prefix}_table",
    )
    
    # Return selected indices (caller will map back to quotas)
    return selected.get("selected_rows", [])


def create_quota_viewer(
    quota: QuotaEntry,
    key_prefix: str = "quota_detail",
) -> Dict[str, Any]:
    """
    Create a detailed view of a single quota.
    
    Args:
        quota: The QuotaEntry to display
        key_prefix: Prefix for streamlit element keys
    
    Returns:
        Dictionary with form values if modified, else empty dict
    """
    st.subheader(f"Quota Details: {quota.path}")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Usage %", f"{quota.usage_percent:.1f}%")
        status = status_badge(quota.status) + " " + quota.status.value.upper()
        st.metric("Status", status)
    
    with col2:
        st.metric("Hard Limit", f"{quota.hard_limit_gb:.2f} GB")
        st.metric("Soft Limit", f"{quota.soft_limit_gb:.2f} GB")
    
    with col3:
        st.metric("Current Usage", f"{quota.usage_gb:.2f} GB")
        st.metric("Days at Current Rate", "N/A")  # Future enhancement
    
    # Show access zone
    st.text(f"Access Zone: {quota.access_zone}")
    
    # Show comment if exists
    if quota.comment:
        st.text(f"Comment: {quota.comment}")
    
    # Show users and groups
    if quota.users:
        st.text(f"Users: {', '.join(quota.users[:5])}{'...' if len(quota.users) > 5 else ''}")
    if quota.groups:
        st.text(f"Groups: {', '.join(quota.groups[:5])}{'...' if len(quota.groups) > 5 else ''}")
    
    return {}


def render_dynamic_grid(obj: Dict[str, Any], key_prefix: str = "dynamic") -> Dict[str, Any]:
    """
    Render an editable grid for any dictionary object.
    Returns a dictionary of modified fields.
    """
    st.markdown("### 🔧 Dynamic Property Editor")
    st.caption("Editable fields are shown as inputs. Complex objects are read-only.")
    
    modified_payload = {}
    
    # Sort keys for consistent UI
    for key in sorted(obj.keys()):
        val = obj[key]
        
        # Skip internal ID or system fields we shouldn't edit directly in the grid
        if key in ["id", "usage", "persona"]:
            st.text(f"{key}: {val}")
            continue
            
        if isinstance(val, bool):
            new_val = st.checkbox(f"{key}", value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, (int, float)):
            # Special handling for limits to show GB in label but keep bytes in value
            label = f"{key}"
            if "limit" in key.lower():
                gb_val = val / (1024**3)
                st.info(f"💡 {key} is approx {gb_val:.2f} GB")
            
            new_val = st.number_input(label, value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, str):
            new_val = st.text_input(f"{key}", value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, dict):
            with st.expander(f"📁 {key} (Nested)"):
                # Recursively render nested if it's 'limits', otherwise just show JSON
                if key == "limits":
                    nested_mods = render_dynamic_grid(val, key_prefix=f"{key_prefix}_{key}")
                    if nested_mods:
                        modified_payload[key] = nested_mods
                else:
                    st.json(val)
        elif isinstance(val, list):
            st.text(f"📝 {key}: {', '.join(map(str, val)) if val else '[]'}")
            
    return modified_payload


def render_snapshot_viewer(snapshots: List[Dict[str, Any]]):
    """Render a table of snapshots."""
    st.markdown("### 📸 Associated Snapshots")
    if not snapshots:
        st.info("No snapshots found for this path.")
        return
        
    df = pd.DataFrame(snapshots)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_acl_viewer(acl: Dict[str, Any]):
    """Render the ACL/Permissions view."""
    st.markdown("### 🔒 Filesystem Permissions (ACL)")
    
    if "error" in acl:
        st.error(f"Could not retrieve ACL: {acl['error']}")
        st.info(acl.get("note", ""))
        return
        
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Owner", acl.get("owner", "N/A"))
    with col2:
        st.metric("Group", acl.get("group", "N/A"))
        
    st.write("**Access Control Entries:**")
    aces = acl.get("acl", [])
    if not aces:
        st.text("No explicit ACEs found (Inherited or POSIX only)")
    else:
        for ace in aces:
            trustee = ace.get("trustee", {}).get("name", "Unknown")
            type_ = ace.get("type", "unknown")
            access = ace.get("accessdesc", "N/A")
            st.markdown(f"**{trustee}** ({type_}): `{access}`")


def create_modification_form(
    quota: QuotaEntry,
    key_prefix: str = "modify_form",
) -> Dict[str, Any]:
    """
    Create a form to modify quota limits.
    
    Args:
        quota: The QuotaEntry to modify
        key_prefix: Prefix for streamlit element keys
    
    Returns:
        Dictionary with modification values if form submitted, else None
    """
    st.subheader(f"Modify Quota: {quota.path}")
    
    with st.form(key=f"{key_prefix}_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            new_hard = st.number_input(
                "New Hard Limit (GB)",
                min_value=0.0,
                value=quota.hard_limit_gb,
                step=1.0,
                format="%.2f",
            )
            if new_hard > 0 and new_hard < quota.usage_gb:
                st.error(f"⚠️ Warning: New limit ({new_hard:.2f} GB) is below current usage ({quota.usage_gb:.2f} GB)")
        
        with col2:
            new_soft = st.number_input(
                "New Soft Limit (GB)",
                min_value=0.0,
                value=quota.soft_limit_gb,
                step=1.0,
                format="%.2f",
            )
        
        # Warning if values are decreasing
        if new_hard < quota.hard_limit_gb:
            st.warning(f"↓ Hard limit decreased from {quota.hard_limit_gb:.2f} GB")
        if new_soft < quota.soft_limit_gb:
            st.warning(f"↓ Soft limit decreased from {quota.soft_limit_gb:.2f} GB")
        
        # Apply to children
        apply_to_children = st.checkbox(
            "Apply to entire quota tree (all children)",
            value=False,
        )
        
        # Confirmation
        confirm = st.checkbox(
            "CAUTION: I confirm this modification",
            value=False,
        )
        
        submitted = st.form_submit_button("Modify Quota", use_container_width=True)
    
    if submitted and confirm:
        return {
            "hard_limit_gb": new_hard,
            "soft_limit_gb": new_soft,
            "apply_to_children": apply_to_children,
        }
    
    return None


# --- Source: src/main.py ---


import streamlit as st
from streamlit import session_state as state

# Import our modules (using relative imports for package structure)





    create_modification_form, 
    status_badge, 
    color_for_status,
    render_dynamic_grid,
    render_snapshot_viewer,
    render_acl_viewer
)

import pandas as pd

# Set page config with custom title and icon
st.set_page_config(
    page_title="SmartQuota Manager",
    page_icon="📊",
    layout="wide",
)

# Initialize session state
init_session()


# Custom CSS for orange/green theme
st.markdown("""
<style>
    :root {
        --primary-orange: #F58513;
        --primary-green: #006837;
        --primary-orange-light: #FFA54D;
        --primary-green-light: #339966;
    }
    
    .stApp {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    
    .stAlert {
        border-radius: 0.5rem;
        border-left: 4px solid var(--primary-orange);
    }
    
    .stAlert.warning {
        border-left-color: var(--primary-orange);
    }
    
    .stAlert.success {
        border-left-color: var(--primary-green);
    }
    
    .status-badge {
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
        color: white;
    }
    
    .status-critical { background-color: #D72638; }
    .status-warning { background-color: #F58513; }
    .status-healthy { background-color: #006837; }
    
    .quota-section {
        background-color: #f8f9fa;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    
    h1, h2, h3 {
        color: var(--primary-green);
    }
    
    .stMetric [data-testid="stMetricValue"] {
        color: var(--primary-orange) !important;
    }
    
    .stMetric [data-testid="stMetricLabel"] {
        color: #666;
    }
</style>
""", unsafe_allow_html=True)


def login_section():
    """Login form - only show if no client is active."""
    st.sidebar.header("🔐 Login")
    
    clusters = load_clusters()
    if not clusters:
        st.sidebar.warning("No clusters configured. Add one to continue.")
        return
    
    # Cluster selector
    cluster_names = list(clusters.keys())
    selected_cluster = st.sidebar.selectbox(
        "Select Cluster",
        options=cluster_names + ["Custom URL..."],
        key="selected_cluster",
    )
    
    custom_url = ""
    if selected_cluster == "Custom URL...":
        custom_url = st.sidebar.text_input("Isilon URL", placeholder="https://isilon.local:8080")
    
    # Credentials
    username = st.sidebar.text_input("Username", key="login_username", placeholder="domain\\user or user")
    password = st.sidebar.text_input("Password", type="password", key="login_password")
    
    # SSL setting
    ssl_warning = st.sidebar.checkbox(
        "Ignore SSL Certificate",
        value=True,
        key="ssl_setting",
    )
    
    # Login button
    if st.sidebar.button("Login", use_container_width=True):
        if not username or not password:
            st.sidebar.error("Username and password are required")
            return
        
        cluster_url = ""
        cluster_display_name = ""
        
        if selected_cluster == "Custom URL...":
            if not custom_url:
                st.sidebar.error("Please enter a custom URL")
                return
            cluster_url = custom_url
            # Derive a clean name from the URL
            cluster_display_name = custom_url.split("//")[-1].split(":")[0].replace(".", "_")
        else:
            cluster_url = clusters[selected_cluster]
            cluster_display_name = selected_cluster
        
        try:
            # Create API client
            api = IsilonAPI(
                cluster_url=cluster_url,
                username=username,
                password=password,
                verify_ssl=not ssl_warning,
            )
            set_api_client(api)
            
            # If it was a custom URL, save it to clusters.json for next time
            if selected_cluster == "Custom URL...":
                add_cluster(cluster_display_name, cluster_url)
            
            # Store additional session state
            state.selected_cluster = cluster_display_name
            state.admin_user = username
            
            st.success(f"✅ Connected to {cluster_display_name}")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Connection failed: {e}")


def logout_button():
    """Logout button - only show if client is active."""
    if state.api_client:
        st.sidebar.header(f"Connected: {state.selected_cluster}")
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            clear_api_client()
            st.rerun()
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            clear_api_client()
            st.rerun()


def cluster_management():
    """Cluster management panel."""
    with st.sidebar.expander("⚙️ Cluster Management", expanded=False):
        st.subheader("Clusters")
        
        clusters = load_clusters()
        for name, url in clusters.items():
            col1, col2 = st.columns([3, 1])
            col1.text(f"• {name}: {url}")
            if col2.button("🗑️", key=f"del_{name}"):
                remove_cluster(name)
                st.rerun()
        
        st.divider()
        
        st.subheader("Add New Cluster")
        new_name = st.text_input("Name", key="new_cluster_name")
        new_url = st.text_input("URL", placeholder="https://cluster.fqdn.local:8080", key="new_cluster_url")
        
        if st.button("Add Cluster"):
            if new_name and new_url:
                add_cluster(new_name, new_url)
                st.success(f"Added: {new_name}")
                st.rerun()
            else:
                st.error("Name and URL required")


def main_view():
    """Main content area."""
    if not state.api_client:
        st.title("📊 SmartQuota Manager")
        st.markdown("Welcome! Please login to manage your PowerScale clusters.")
        st.markdown("---")
        st.header("Quick Start")
        st.info("""
        1. **Login** using the sidebar
        2. **View** top offenders on the current cluster
        3. **Search** by share name or access zone
        4. **Modify** quotas and monitor usage
        """)
        return
    
    st.title(f"📊 SmartQuota Manager - {state.selected_cluster}")
    
    tabs = st.tabs(["📈 Monitoring", "🔧 Modify", "➕ Create", "📜 Audit Log", "📥 Export"])
    
    with tabs[0]:
        monitoring_tab()
    
    with tabs[1]:
        modify_tab()
        
    with tabs[2]:
        create_tab()
    
    with tabs[3]:
        audit_tab()
        
    with tabs[4]:
        export_tab()


def create_tab():
    """Tab for creating new quotas."""
    st.header("Provision New Quota ➕")
    
    # Official Documentation Link
    st.info("📖 [Official Dell Documentation: Creating Quotas](https://developer.dell.com/apis/4357/versions/9.12.0/docs/Introduction.md)")
    
    if not state.api_client:
        st.warning("Login required")
        return
        
    api = state.api_client
    
    with st.form("create_quota_form"):
        path = st.text_input("Filesystem Path", placeholder="/ifs/data/...")
        
        col1, col2 = st.columns(2)
        with col1:
            q_type = st.selectbox("Quota Type", ["directory", "user", "group", "default-user", "default-group"])
            access_zone = st.selectbox("Access Zone", api.list_access_zones())
        
        with col2:
            hard_limit = st.number_input("Hard Limit (GB)", min_value=0.0, step=1.0)
            soft_limit = st.number_input("Soft Limit (GB)", min_value=0.0, step=1.0)

        enforced = st.checkbox("Enforced", value=True)
        include_snapshots = st.checkbox("Include Snapshots in Usage", value=False)
        
        submit = st.form_submit_button("CREATE QUOTA", type="primary", use_container_width=True)
        
    if submit:
        if not path.startswith("/ifs"):
            st.error("Path must start with /ifs")
            return
            
        try:
            with st.spinner(f"Creating quota on {path}..."):
                new_id = api.create_quota(
                    path=path,
                    type=q_type,
                    hard_limit_gb=hard_limit,
                    soft_limit_gb=soft_limit,
                    access_zone=access_zone,
                    enforced=enforced,
                    include_snapshots=include_snapshots
                )
                
                # Audit log
                write_audit_entry(
                    admin=state.admin_user or "unknown",
                    cluster=state.selected_cluster,
                    action="QUOTA_CREATE",
                    share_name=path.split("/")[-1],
                    path=path,
                    old_limit_gb=0,
                    new_limit_gb=hard_limit
                )
                
                st.success(f"✅ Quota created successfully! ID: {new_id}")
                # Reset cache
                if "quotas_loaded" in state:
                    del state.quotas_loaded
        except Exception as e:
            if not handle_api_error(e):
                st.error(f"Failed to create quota: {e}")


def export_tab():
    """Tab for bulk exporting quotas."""
    st.header("Bulk Export 📥")
    
    # Official Documentation Link
    st.info("📖 [OneFS 9.12.0.0 Documentation Info Hub](https://www.dell.com/support/kbdoc/en-us/000355502/powerscale-onefs-9-12-0-0-documentation-info-hub)")
    
    if not state.api_client:
        st.warning("Login required")
        return
        
    api = state.api_client
    
    st.markdown("Download full quota reports for the current cluster.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Export Options")
        export_type = st.radio(
            "Select Export Scope",
            ["All Quotas", "By Access Zone", "By Protocol"],
            key="export_scope_radio"
        )
        
        selected_zone = "All"
        if export_type == "By Access Zone":
            zones = api.list_access_zones()
            selected_zone = st.selectbox("Select Zone", zones)
            
        selected_protocol = "All"
        if export_type == "By Protocol":
            selected_protocol = st.selectbox("Select Protocol", ["SMB", "NFS"])

    with col2:
        st.subheader("Generate Report")
        if st.button("Generate & Download CSV", use_container_width=True):
            with st.spinner("Fetching all quotas (this may take a minute)..."):
                try:
                    # Fetch all quotas (paginated)
                    all_quotas = api.list_all_quotas()
                    
                    # Fetch protocol mapping
                    mapping = api.get_protocol_mapping()
                    
                    # Convert to list of dicts with protocol info
                    export_data = []
                    for q in all_quotas:
                        d = q.to_dict()
                        # Add protocol
                        d["Protocol"] = mapping.get(q.path, "-")
                        export_data.append(d)
                    
                    df = pd.DataFrame(export_data)
                    
                    # Apply filters if needed
                    if export_type == "By Access Zone":
                        df = df[df["access_zone"] == selected_zone]
                    elif export_type == "By Protocol":
                        df = df[df["Protocol"].str.contains(selected_protocol, na=False)]
                        
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="Click here to download",
                        data=csv,
                        file_name=f"quota_export_{export_type.lower().replace(' ', '_')}_{state.selected_cluster}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                    st.success(f"Report generated with {len(df)} entries.")
                except Exception as e:
                    st.error(f"Failed to generate report: {e}")


def monitoring_tab():
    """Tab for quota monitoring and viewing."""
    st.header("Quota Monitoring")
    
    # Official Documentation Link
    st.info("📖 [Official Dell Documentation: Quota Monitoring](https://developer.dell.com/apis/4357/versions/9.12.0/docs/Introduction.md)")
    
    api = state.api_client
    
    # Load quotas
    if "quotas_loaded" not in st.session_state:
        with st.spinner("Loading quotas..."):
            try:
                quotas, _ = api.list_quotas(limit=500)
                state.quotas = quotas
                state.quotas_loaded = True
                st.session_state.last_quota_list = quotas
            except Exception as e:
                if not handle_api_error(e):
                    st.error(f"Failed to load quotas: {e}")
                return
    
    # Top offenders cards
    st.subheader("⚠️ Top Offenders")
    categories = get_top_offenders(state.quotas)
    
    if any(categories.values()):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"<h3 style='color:#D72638'>🔴 Critical (>90%)</h3>", unsafe_allow_html=True)
            for item in categories["critical"][:5]:
                st.warning(f"{item['share_name']}: {item['usage_percent']:.1f}%")
        
        with col2:
            st.markdown(f"<h3 style='color:#F58513'>🟡 Warning (80-90%)</h3>", unsafe_allow_html=True)
            for item in categories["warning"][:5]:
                st.warning(f"{item['share_name']}: {item['usage_percent']:.1f}%")
        
        with col3:
            st.markdown(f"<h3 style='color:#006837'>🟢 Notice (70-80%)</h3>", unsafe_allow_html=True)
            for item in categories["notice"][:5]:
                st.info(f"{item['share_name']}: {item['usage_percent']:.1f}%")
    else:
        st.success("All quotas healthy!")
    
    st.divider()
    
    # Search and filter
    st.subheader("🔍 Search Quotas")
    
    col1, col2 = st.columns(2)
    with col1:
        search_term = st.text_input("Share Name (partial match)", key="search_share")
    with col2:
        zones = api.list_access_zones()
        access_zone = st.selectbox("Access Zone", ["All"] + zones, key="search_zone")
    
    # Filter quotas
    filtered = filter_quotas(
        state.quotas,
        share_name=search_term if search_term else None,
        access_zone=access_zone if access_zone != "All" else None,
    )
    
    # Export section
    st.divider()
    col_exp1, col_exp2 = st.columns([4, 1])
    with col_exp2:
        if filtered:
            # Prepare export data
            export_df = pd.DataFrame([q.to_dict() for q in filtered])
            csv = export_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export to CSV",
                data=csv,
                file_name=f"quotas_{state.selected_cluster}.csv",
                mime="text/csv",
                use_container_width=True,
            )

    # Paginate
    page = st.number_input("Page", min_value=1, value=1, key="quota_page")
    page_size = 25
    paginated, total_pages = paginate_list(filtered, page, page_size)
    
    if paginated:
        # Create table
        data = []
        for q in paginated:
            status = status_badge(q.status) + " " + q.status.value.upper()
            data.append({
                "Share Name": q.path.split("/")[-1],
                "Access Zone": q.access_zone,
                "Path": q.path,
                "Hard Limit (GB)": f"{q.hard_limit_gb:.2f}",
                "Soft Limit (GB)": f"{q.soft_limit_gb:.2f}",
                "Usage (GB)": f"{q.usage_gb:.2f}",
                "Usage %": f"{q.usage_percent:.1f}",
                "Status": status,
            })
        
        df = pd.DataFrame(data)
        st.dataframe(df, hide_index=True, use_container_width=True)
        
        # Selection
        selected = st.multiselect(
            "Select quotas to modify",
            options=[f"{q.path} ({q.usage_percent:.1f}%)" for q in paginated],
            key="selected_quota_paths",
        )
        state.selected_quota_paths = selected
    else:
        st.info("No quotas found matching your criteria.")


def modify_tab():
    """Tab for universal quota and path modification."""
    st.header("Universal Object Manager 🛠️")
    
    # Official Documentation Link
    with st.expander("📖 Official Dell Documentation Resources", expanded=False):
        st.markdown("""
        - [Quota Management API](https://developer.dell.com/apis/4357/versions/9.12.0/docs/Introduction.md)
        - [SnapshotIQ Management API](https://developer.dell.com/apis/4357/versions/9.12.0/docs/Introduction.md)
        - [Namespace (ACL) API Reference](https://developer.dell.com/apis/4357/versions/9.12.0/docs/Introduction.md)
        - [OneFS 9.12 CLI Command Reference (PDF)](https://dl.dell.com/content/manual24245533-powerscale-onefs-9-12-0-0-cli-command-reference.pdf)
        """)
    
    if not state.api_client:
        st.warning("Login required")
        return
    
    api = state.api_client
    
    # Get selected quotas
    if "selected_quota_paths" not in state or not state.selected_quota_paths:
        st.info("Select a quota from the Monitoring tab to manage it.")
        return
    
    # For simplicity in Universal view, we manage one object at a time if multiple selected
    selected_path_str = state.selected_quota_paths[0]
    
    # Find the quota object
    quota = None
    for q in state.quotas:
        if f"{q.path} ({q.usage_percent:.1f}%)" == selected_path_str:
            quota = q
            break
            
    if not quota:
        st.error("Selected quota not found in session.")
        return

    st.title(f"📁 {quota.path.split('/')[-1]}")
    st.caption(f"Full Path: {quota.path}")

    # Tabs for different aspects of the filesystem object
    obj_tabs = st.tabs(["⚙️ Quota Settings", "📸 Snapshots", "🔒 Permissions (ACL)"])

    with obj_tabs[0]:
        try:
            # Fetch raw data for dynamic grid
            raw_quota = api.get_raw_quota(quota.id)
            
            # Render Dynamic Grid
            with st.form(key=f"universal_form_{quota.id}"):
                modified_payload = render_dynamic_grid(raw_quota, key_prefix=f"univ_{quota.id}")
                
                st.divider()
                st.warning("⚠️ Changes here affect production. Verify all fields.")
                confirm = st.checkbox("I confirm these changes", key=f"conf_{quota.id}")
                submit = st.form_submit_button("APPLY CHANGES", type="primary", use_container_width=True)
                
            if submit and confirm:
                if not modified_payload:
                    st.info("No changes detected.")
                else:
                    with st.spinner("Applying changes..."):
                        updated_raw = api.update_quota_dynamic(quota.id, modified_payload)
                        
                        # Write audit log
                        admin = state.admin_user or "unknown"
                        write_audit_entry(
                            admin=admin,
                            cluster=state.selected_cluster,
                            action="QUOTA_DYNAMIC_MODIFY",
                            share_name=quota.path.split("/")[-1],
                            path=quota.path,
                            old_limit_gb=quota.hard_limit_gb,
                            new_limit_gb=updated_raw.get("limits", {}).get("hard", 0) / (1024**3),
                        )
                        
                        st.success("✅ Successfully updated quota!")
                        # Clear cache to force reload
                        if "quotas_loaded" in state:
                            del state.quotas_loaded
                        st.rerun()
        except Exception as e:
            if not handle_api_error(e):
                st.error(f"Error loading quota details: {e}")

    # Add Delete capability at the bottom of Quota Settings tab
    with obj_tabs[0]:
        st.divider()
        with st.expander("🗑️ Decommission Quota", expanded=False):
            st.error("DANGER: This action will permanently delete the quota entry.")
            delete_confirm = st.text_input("Type 'DELETE' to confirm", key=f"del_confirm_{quota.id}")
            if st.button("DELETE QUOTA PERMANENTLY", type="primary", key=f"del_btn_{quota.id}", use_container_width=True):
                if delete_confirm == "DELETE":
                    try:
                        api.delete_quota(quota.id)
                        write_audit_entry(
                            admin=state.admin_user or "unknown",
                            cluster=state.selected_cluster,
                            action="QUOTA_DELETE",
                            share_name=quota.path.split("/")[-1],
                            path=quota.path,
                            old_limit_gb=quota.hard_limit_gb,
                            new_limit_gb=0
                        )
                        st.success("✅ Quota deleted.")
                        if "quotas_loaded" in state:
                            del state.quotas_loaded
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete: {e}")
                else:
                    st.warning("Please type 'DELETE' to confirm.")

    with obj_tabs[1]:
        try:
            with st.spinner("Fetching snapshots..."):
                snapshots = api.get_snapshots_for_path(quota.path)
                render_snapshot_viewer(snapshots)
        except Exception as e:
            st.error(f"Error fetching snapshots: {e}")

    with obj_tabs[2]:
        try:
            with st.spinner("Fetching ACLs..."):
                acl = api.get_acl_for_path(quota.path, access_zone=quota.access_zone)
                render_acl_viewer(acl)
        except Exception as e:
            st.error(f"Error fetching ACLs: {e}")


def audit_tab():
    """Tab for viewing audit log."""
    st.header(f"Audit Log: {state.selected_cluster} 📜")
    
    # Official Documentation Link
    st.info("📖 [OneFS 9.12.0.0 Documentation Info Hub](https://www.dell.com/support/kbdoc/en-us/000355502/powerscale-onefs-9-12-0-0-documentation-info-hub)")
    
    if not state.api_client:
        st.warning("Login required")
        return
    
    # Display recent audit entries
    try:
        from src.audit import read_audit_log
        
        # This will automatically use the cluster-specific log file
        entries = read_audit_log(cluster=state.selected_cluster)
        
        if not entries:
            st.info(f"No audit entries found for {state.selected_cluster}.")
            return
        
        # Show most recent 50
        recent = entries[-50:]
        recent.reverse() # Show newest at top
        
        df = pd.DataFrame(recent)
        st.dataframe(df, hide_index=True, use_container_width=True)
        
        if st.button("Export Full Audit"):
            csv = df.to_csv(index=False)
            st.download_button(
                "Download CSV",
                csv,
                f"audit_log_{state.selected_cluster}.csv",
                "text/csv",
            )
            
    except Exception as e:
        st.error(f"Failed to read audit log: {e}")


# Main layout
def main():
    """Main layout function."""
    # Load logo placeholder (will be replaced with actual logo if available)
    logo_path = "https://logo_clear.png"
    st.sidebar.image(logo_path, width=50)  # Placeholder logo
    
    # Sidebar content
    if state.api_client:
        logout_button()
        cluster_management()
    else:
        login_section()
    
    # Main content
    main_view()


if __name__ == "__main__":
    main()


# --- ENTRY POINT ---
if __name__ == "__main__":
    # This part only runs inside the Streamlit context
    main()
