#!/usr/bin/env python3
"""
SmartQuota Manager - Universal Single-File Distribution
Optimized for OneFS 9.12.0.1
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

# Python Version Check
if sys.version_info < (3, 8):
    print("Error: Python 3.8 or higher is required.")
    sys.exit(1)

def run_command(cmd, shell=False):
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
        print("Manual install required: pip install " + " ".join(missing_deps))
        sys.exit(1)

    if system == "darwin": # macOS
        if shutil.which("brew"):
            print("[*] Ensuring python3 is available via brew...")
            run_command(["brew", "install", "python"])
    
    elif system == "linux":
        if shutil.which("apt-get"):
            run_command(["sudo", "apt-get", "update", "-y"])
            run_command(["sudo", "apt-get", "install", "-y", "python3-pip"])
        elif shutil.which("dnf"):
            run_command(["sudo", "dnf", "install", "-y", "python3-pip"])

    print("[*] Installing python dependencies via pip...")
    pip_cmd = [sys.executable, "-m", "pip", "install"] + missing_deps
    if not run_command(pip_cmd):
        run_command(pip_cmd + ["--user"])

    print("\n[+] Done. Re-launching...\n")
    return True

if "__main__" == __name__ and not os.environ.get("STREAMLIT_RUNNING"):
    bootstrap()
    os.environ["STREAMLIT_RUNNING"] = "1"
    subprocess.run([sys.executable, "-m", "streamlit", "run", __file__])
    sys.exit(0)

import streamlit as st
import pandas as pd
import urllib3
try:
    import isi_sdk
except ImportError:
    pass

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


from typing import List, Dict, Any, Optional, Tuple



def bytes_to_gb(value: int) -> float:
    """Convert bytes to GB."""
    if not value:
        return 0.0
    return round(value / (1024 ** 3), 2)


def bytes_to_tb(value: int) -> float:
    """Convert bytes to TB."""
    if not value:
        return 0.0
    return round(value / (1024 ** 4), 2)


def format_size(value: int) -> str:
    """Format byte value as human-readable string."""
    if not value:
        return "0 bytes"
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


def status_badge(status: Status) -> str:
    """Get status emoji for UI display."""
    mapping = {
        Status.HEALTHY: "🟢",
        Status.WARNING: "🟡",
        Status.CRITICAL: "🔴",
    }
    return mapping.get(status, "⚪")


def color_for_status(status: Status) -> str:
    """Get hex color for status display."""
    mapping = {
        Status.HEALTHY: "#006837",
        Status.WARNING: "#F58513",
        Status.CRITICAL: "#D72638",
    }
    return mapping.get(status, "#666666")


def filter_quotas(
    quotas: List[Any],
    share_name: Optional[str] = None,
    access_zone: Optional[str] = None,
) -> List[Any]:
    """Filter quotas by name or zone."""
    results = quotas
    if share_name:
        share_lower = share_name.lower()
        results = [q for q in results if share_lower in q.path.lower()]
    if access_zone and access_zone != "All":
        results = [q for q in results if q.access_zone == access_zone]
    return results


def get_top_offenders(quotas: List[Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Group quotas by usage thresholds (95, 80, 70)."""
    categories = {"critical": [], "warning": [], "notice": []}
    for quota in quotas:
        pct = quota.usage_percent
        detail = {
            "share_name": quota.path.split("/")[-1],
            "usage_percent": round(pct, 1),
        }
        if pct > 95:
            categories["critical"].append(detail)
        elif pct > 80:
            categories["warning"].append(detail)
        elif pct > 70:
            categories["notice"].append(detail)
            
    for cat in categories:
        categories[cat].sort(key=lambda x: x["usage_percent"], reverse=True)
    return categories


def paginate_list(items: List[Any], page: int, page_size: int = 25) -> Tuple[List[Any], int]:
    """Paginate a list of items."""
    total_pages = (len(items) + page_size - 1) // page_size if items else 1
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    return items[start:start + page_size], total_pages


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





def render_dynamic_grid(obj: Dict[str, Any], key_prefix: str = "dynamic") -> Dict[str, Any]:
    """
    Render an editable grid for any dictionary object.
    Returns a dictionary of modified fields.
    """
    st.markdown("### 🔧 Dynamic Property Editor")
    st.caption("Editable fields: Int, Str, Bool. Nested 'limits' are editable. All others read-only.")
    
    modified_payload = {}
    
    # Sort keys for consistent UI
    for key in sorted(obj.keys()):
        val = obj[key]
        
        # Non-editable metadata
        if key in ["id", "usage", "persona", "path", "zone"]:
            st.text(f"{key}: {val}")
            continue
            
        if isinstance(val, bool):
            new_val = st.checkbox(f"{key}", value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, (int, float)):
            # Special handling for limit fields to show GB hint
            label = f"{key}"
            if "limit" in key.lower() or key in ["hard", "soft", "advisory"]:
                st.info(f"💡 {key} = {bytes_to_gb(val):,.2f} GB")
            
            new_val = st.number_input(label, value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, str):
            new_val = st.text_input(f"{key}", value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, dict):
            # Special handling for 'limits' dict
            if key == "limits":
                with st.expander("📁 Limits Configuration", expanded=True):
                    nested_mods = render_dynamic_grid(val, key_prefix=f"{key_prefix}_{key}")
                    if nested_mods:
                        modified_payload[key] = nested_mods
            else:
                with st.expander(f"📁 {key} (Read-only)"):
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
    # Use formatted sizes for display
    if "size" in df.columns:
        df["size_readable"] = df["size"].apply(format_size)
        
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_acl_viewer(acl: Dict[str, Any]):
    """Render the ACL/Permissions view."""
    st.markdown("### 🔒 Filesystem Permissions (ACL)")
    
    if "error" in acl:
        st.error(f"Could not retrieve ACL: {acl['error']}")
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
    """Create a form for simple limit modifications."""
    st.subheader(f"Modify Quota: {quota.path}")
    
    with st.form(key=f"{key_prefix}_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_hard = st.number_input("New Hard Limit (GB)", min_value=0.0, value=quota.hard_limit_gb, step=1.0)
            if new_hard > 0 and new_hard < quota.usage_gb:
                st.error(f"⚠️ Warning: Limit ({new_hard:.2f} GB) < current usage ({quota.usage_gb:.2f} GB)")
        
        with col2:
            new_soft = st.number_input("New Soft Limit (GB)", min_value=0.0, value=quota.soft_limit_gb, step=1.0)
        
        apply_to_children = st.checkbox("Apply to child quotas", value=False)
        confirm = st.checkbox("I confirm this production change", value=False)
        submitted = st.form_submit_button("APPLY LIMITS", use_container_width=True)
    
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
import pandas as pd

# Import our modules




    filter_quotas, get_top_offenders, paginate_list, 
    status_badge, color_for_status
)

    render_dynamic_grid, render_snapshot_viewer, render_acl_viewer
)


# Set page config
st.set_page_config(page_title="SmartQuota Manager", page_icon="📊", layout="wide")

# Initialize session state
init_session()

# Custom CSS
st.markdown("""
<style>
    :root { --primary-orange: #F58513; --primary-green: #006837; }
    .stApp { font-family: sans-serif; }
    h1, h2, h3 { color: var(--primary-green); }
    .stMetric [data-testid="stMetricValue"] { color: var(--primary-orange) !important; }
</style>
""", unsafe_allow_html=True)


def login_section():
    """Login form sidebar."""
    st.sidebar.header("🔐 Login")
    clusters = load_clusters()
    
    cluster_names = list(clusters.keys())
    selected = st.sidebar.selectbox("Select Cluster", options=cluster_names + ["Custom URL..."], key="selected_cluster")
    
    custom_url = ""
    if selected == "Custom URL...":
        custom_url = st.sidebar.text_input("Isilon URL", placeholder="https://isilon.local:8080")
    
    username = st.sidebar.text_input("Username", key="login_username", placeholder="domain\\user or user")
    password = st.sidebar.text_input("Password", type="password", key="login_password")
    ssl_warning = st.sidebar.checkbox("Ignore SSL Certificate", value=True, key="ssl_setting")
    
    if st.sidebar.button("Login", use_container_width=True):
        if not username or not password:
            st.sidebar.error("Credentials required")
            return
        
        url = custom_url if selected == "Custom URL..." else clusters[selected]
        if not url:
            st.sidebar.error("URL required")
            return

        # Derive clean hostname for display and logging
        display_name = selected
        if selected == "Custom URL...":
            display_name = url.split("//")[-1].split(":")[0].replace(".", "_")
        
        try:
            api = IsilonAPI(cluster_url=url, username=username, password=password, verify_ssl=not ssl_warning)
            set_api_client(api)
            if selected == "Custom URL...":
                add_cluster(display_name, url)
            
            state.selected_cluster = display_name
            state.admin_user = username
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Login failed: {e}")


def logout_section():
    """Logout button and info."""
    if state.api_client:
        st.sidebar.header(f"Connected: {state.selected_cluster}")
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            clear_api_client()
            st.rerun()


def cluster_management():
    """Cluster management sidebar expander."""
    with st.sidebar.expander("⚙️ Cluster Management", expanded=False):
        clusters = load_clusters()
        for name, url in clusters.items():
            col1, col2 = st.columns([3, 1])
            col1.caption(f"{name}")
            if col2.button("🗑️", key=f"del_{name}"):
                remove_cluster(name)
                st.rerun()
        st.divider()
        new_name = st.text_input("New Name")
        new_url = st.text_input("New URL", placeholder="https://...")
        if st.button("Add"):
            if new_name and new_url:
                add_cluster(new_name, new_url)
                st.rerun()


def main_view():
    """Main dashboard content."""
    if not state.api_client:
        st.title("📊 SmartQuota Manager")
        st.info("Please login from the sidebar to manage your PowerScale clusters.")
        return
    
    st.title(f"📊 {state.selected_cluster}")
    tabs = st.tabs(["📈 Monitoring", "🔧 Universal Manager", "➕ Create", "📜 Audit Log", "📥 Export"])
    
    with tabs[0]: monitoring_tab()
    with tabs[1]: modify_tab()
    with tabs[2]: create_tab()
    with tabs[3]: audit_tab()
    with tabs[4]: export_tab()


def monitoring_tab():
    """Dashboard and search."""
    st.header("Quota Monitoring")
    st.info("📖 [Documentation](https://developer.dell.com/apis/4357/versions/9.12.0/docs/Introduction.md)")
    
    api = state.api_client
    if "quotas_loaded" not in st.session_state:
        with st.spinner("Fetching quotas..."):
            try:
                state.quotas = api.list_quotas(limit=500)[0]
                state.quotas_loaded = True
            except Exception as e:
                if not handle_api_error(e): st.error(f"Load failed: {e}")
                return

    # Top Offenders
    cats = get_top_offenders(state.quotas)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"<h4 style='color:#D72638'>🔴 Critical (>95%)</h4>", unsafe_allow_html=True)
        for i in cats["critical"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")
    with col2:
        st.markdown(f"<h4 style='color:#F58513'>🟡 Warning (>80%)</h4>", unsafe_allow_html=True)
        for i in cats["warning"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")
    with col3:
        st.markdown(f"<h4 style='color:#006837'>🟢 Notice (>70%)</h4>", unsafe_allow_html=True)
        for i in cats["notice"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")

    st.divider()
    
    # Search
    c1, c2 = st.columns(2)
    search = c1.text_input("Search Share Name")
    zone = c2.selectbox("Filter Zone", ["All"] + api.list_access_zones())
    
    filtered = filter_quotas(state.quotas, search, zone)
    
    # List Table
    page = st.number_input("Page", min_value=1, value=1)
    items, total = paginate_list(filtered, page)
    
    if items:
        display_data = []
        for q in items:
            display_data.append({
                "Share": q.path.split("/")[-1],
                "Zone": q.access_zone,
                "Path": q.path,
                "Usage %": f"{q.usage_percent:.1f}%",
                "Status": f"{status_badge(q.status)} {q.status.value.upper()}"
            })
        st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)
        
        # Selection
        selected = st.multiselect("Focus on share for Universal Manager", 
                                  options=[f"{q.path} ({q.usage_percent:.1f}%)" for q in items], 
                                  key="selected_paths")
        state.selected_quota_paths = selected
    else:
        st.info("No matching quotas found.")


def modify_tab():
    """Universal Manager with Dynamic Grid."""
    st.header("Universal Object Manager 🛠️")
    with st.expander("📖 API Resources"):
        st.caption("Links to Dell Portal for Quotas, Snapshots, and ACLs.")
    
    if not state.api_client: return
    if "selected_quota_paths" not in state or not state.selected_quota_paths:
        st.info("Select a quota from Monitoring to begin.")
        return
    
    # Find active quota
    path_str = state.selected_quota_paths[0]
    quota = next((q for q in state.quotas if f"{q.path} ({q.usage_percent:.1f}%)" == path_str), None)
    if not quota: return

    st.subheader(f"📁 {quota.path}")
    t1, t2, t3 = st.tabs(["⚙️ Settings", "📸 Snapshots", "🔒 Permissions"])
    
    api = state.api_client
    with t1:
        try:
            raw = api.quota_api.get_quota_entry(quota.id).to_dict()
            with st.form(f"f_{quota.id}"):
                payload = render_dynamic_grid(raw, f"ed_{quota.id}")
                st.divider()
                if st.form_submit_button("APPLY CHANGES", type="primary"):
                    if payload:
                        api.update_quota_dynamic(quota.id, payload)
                        write_audit_entry(state.admin_user, state.selected_cluster, "DYNAMIC_MODIFY", quota.path.split("/")[-1], quota.path, quota.hard_limit_gb, 0)
                        st.success("Updated!")
                        if "quotas_loaded" in state: del state.quotas_loaded
                        st.rerun()
            
            # Delete
            with st.expander("🗑️ Decommission"):
                if st.text_input("Type DELETE") == "DELETE":
                    if st.button("CONFIRM DELETE"):
                        api.delete_quota(quota.id)
                        write_audit_entry(state.admin_user, state.selected_cluster, "DELETE", quota.path.split("/")[-1], quota.path, 0, 0)
                        st.rerun()
        except Exception as e:
            if not handle_api_error(e): st.error(f"Error: {e}")

    with t2:
        render_snapshot_viewer(api.get_snapshots_for_path(quota.path))
    
    with t3:
        render_acl_viewer(api.get_acl_for_path(quota.path))


def create_tab():
    """Quota Provisioning."""
    st.header("Provision New Quota ➕")
    if not state.api_client: return
    
    with st.form("c_form"):
        path = st.text_input("Path", placeholder="/ifs/...")
        q_type = st.selectbox("Type", ["directory", "user", "group"])
        zone = st.selectbox("Zone", state.api_client.list_access_zones())
        hard = st.number_input("Hard Limit (GB)", min_value=0.0, step=1.0)
        if st.form_submit_button("CREATE"):
            if not path.startswith("/ifs"): st.error("Path error"); return
            try:
                state.api_client.create_quota(path, q_type, hard, zone)
                write_audit_entry(state.admin_user, state.selected_cluster, "CREATE", path.split("/")[-1], path, 0, hard)
                st.success("Created!")
                if "quotas_loaded" in state: del state.quotas_loaded
            except Exception as e:
                if not handle_api_error(e): st.error(f"Error: {e}")


def audit_tab():
    """Audit view."""
    st.header(f"Audit Log: {state.selected_cluster}")
    entries = read_audit_log(cluster=state.selected_cluster)
    if entries:
        st.dataframe(pd.DataFrame(entries), hide_index=True, use_container_width=True)
    else:
        st.info("No entries today.")


def export_tab():
    """Reports."""
    st.header("Bulk Export")
    if st.button("Generate All Quotas CSV"):
        with st.spinner("Processing..."):
            all_q = state.api_client.list_all_quotas()
            mapping = state.api_client.get_protocol_mapping()
            data = []
            for q in all_q:
                d = q.to_dict()
                d["Protocol"] = mapping.get(q.path, "-")
                data.append(d)
            st.download_button("Download CSV", pd.DataFrame(data).to_csv(index=False), "export.csv")


def main():
    """App entry."""
    if state.api_client:
        logout_section()
        cluster_management()
    else:
        login_section()
    main_view()

if __name__ == "__main__":
    main()


# --- ENTRY POINT ---
if __name__ == "__main__":
    main()
