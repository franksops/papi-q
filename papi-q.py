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
import glob
import json
import csv
import time
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

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
    """Ensure dependencies are met using the best available stable Python version."""
    config_dir = (Path.home() / ".papi-q").resolve()
    venv_dir = config_dir / "venv"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    current_prefix = Path(sys.prefix).resolve()
    in_venv = current_prefix == venv_dir.resolve()

    # If we aren't in a venv yet, let's find the best Python to use
    if not in_venv:
        best_python = sys.executable
        if sys.version_info >= (3, 14):
            for version in ["3.13", "3.12", "3.11"]:
                path = shutil.which(f"python{version}")
                if path:
                    print(f"[*] Switching to stable Python: {path}")
                    best_python = path
                    break
        
        if not venv_dir.exists():
            print(f"[*] Creating virtual environment in {venv_dir}...")
            run_command([best_python, "-m", "venv", str(venv_dir)])
        
        venv_python = str(venv_dir / "bin" / "python") if os.name != "nt" else str(venv_dir / "Scripts" / "python.exe")
        
        # If the venv exists but is 3.14, wipe it
        res = subprocess.run([venv_python, "--version"], capture_output=True, text=True)
        if "3.14" in res.stdout and sys.version_info < (3, 14):
            print("[!] Wiping incompatible 3.14 venv...")
            shutil.rmtree(venv_dir)
            return bootstrap()

        print("[*] Syncing dependencies (fresh install)...")
        run_command([venv_python, "-m", "pip", "install", "--upgrade", "pip"])
        deps = ["isilon-sdk", "streamlit", "pandas", "urllib3", "python-dotenv"]
        # Use --no-cache-dir to ensure we aren't pulling a corrupt build
        run_command([venv_python, "-m", "pip", "install", "--no-cache-dir"] + deps)

        print("\n[+] Environment ready. Re-launching...\n")
        os.execv(venv_python, [venv_python] + sys.argv)

    # --- VERIFICATION PHASE (Inside Venv) ---
    deps_map = {"streamlit": "streamlit", "isi_sdk": "isilon-sdk", "pandas": "pandas", "urllib3": "urllib3", "dotenv": "python-dotenv"}
    missing = []
    for mod, pkg in deps_map.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        # Check if we are in a 'Zombie' state (pip thinks they exist, but python can't find them)
        print(f"\n[!] Detected inconsistent environment ({sys.version.split()[0]})")
        print(f"[*] Missing modules: {', '.join(missing)}")
        
        if not os.environ.get("PAPI_RETRY"):
            print("[*] Attempting Nuclear Recovery (wiping venv)...")
            shutil.rmtree(venv_dir)
            os.environ["PAPI_RETRY"] = "1"
            # Launch original python to recreate everything
            orig_python = shutil.which("python3") or sys.executable
            os.execv(orig_python, [orig_python] + sys.argv)
        else:
            print("\n[!] Recovery failed. Please try: rm -rf ~/.papi-q/venv")
            sys.exit(1)

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

# --- Source: src/constants.py ---


from pathlib import Path

# Default paths
DEFAULT_CONFIG_DIR = Path.home() / ".papi-q"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_CLUSTERS_FILE = DEFAULT_CONFIG_DIR / "clusters.json"
DEFAULT_SYSTEM_LOG = DEFAULT_CONFIG_DIR / "system.log"
DEFAULT_AUDIT_LOG = Path.home() / "isilon_admin_audit.csv"

def ensure_config_dir() -> Path:
    """Create the config directory if it doesn't exist."""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_CONFIG_DIR


# --- Source: src/logger.py ---


import logging
from datetime import datetime


def setup_logger():
    """Configure the system logger."""
    ensure_config_dir()
    
    # Configure logging to file and console
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(DEFAULT_SYSTEM_LOG),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("papi-q")

# Initialize logger instance
logger = setup_logger()

def log_info(message: str):
    logger.info(message)

def log_error(message: str, error: Exception = None):
    if error:
        logger.error(f"{message}: {error}", exc_info=True)
    else:
        logger.error(message)

def log_warning(message: str):
    logger.warning(message)


# --- Source: src/config.py ---


import json
import os
from pathlib import Path
from typing import Dict, Any, Optional






def load_config() -> Dict[str, Any]:
    """Load configuration from config.json, creating defaults if missing."""
    ensure_config_dir()
    log_info(f"Loading configuration from {DEFAULT_CONFIG_FILE}")
    
    config = {
        "verify_ssl": False,
        "log_file": str(DEFAULT_CONFIG_DIR / "isilon_admin_audit.csv"),
        "max_retries": 3,
        "cache_ttl_seconds": 60,
    }
    
    if DEFAULT_CONFIG_FILE.exists():
        try:
            with open(DEFAULT_CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                config.update(loaded)
                log_info("Configuration loaded successfully")
        except json.JSONDecodeError as e:
            log_error("Corrupt config.json found, using defaults", e)
            pass
    else:
        log_warning("config.json not found, using defaults")
    
    return config


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to config.json."""
    ensure_config_dir()
    with open(DEFAULT_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def load_clusters() -> Dict[str, str]:
    """Load cluster definitions from clusters.json."""
    if not DEFAULT_CLUSTERS_FILE.exists():
        log_warning(f"Clusters file not found at {DEFAULT_CLUSTERS_FILE}")
        return {}
    
    try:
        with open(DEFAULT_CLUSTERS_FILE, "r") as f:
            clusters = json.load(f)
            log_info(f"Loaded {len(clusters)} clusters from inventory")
            return clusters
    except json.JSONDecodeError as e:
        log_error("Corrupt clusters.json found", e)
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
    
    def __init__(self, cluster_url: str, username: str, password: str, verify_ssl: bool = True):
        self.cluster_url = cluster_url.rstrip("/")
        try:
            import isi_sdk
            self.sdk = isi_sdk
            # Dynamically load models
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


# --- Source: src/audit.py ---


import csv
import glob
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
) -> bool:
    """Write an audit log entry for a quota modification with daily rotation."""
    safe_name = "".join([c if c.isalnum() else "_" for c in cluster])
    datestamp = datetime.now().strftime("%m%d%Y")
    log_file = DEFAULT_CONFIG_DIR / f"{safe_name}_{datestamp}.csv"
    
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "admin": admin,
        "cluster": cluster,
        "action": action,
        "share_name": share_name,
        "path": path,
        "old_limit_gb": round(old_limit_gb, 2),
        "new_limit_gb": round(new_limit_gb, 2),
    }
    
    try:
        exists = log_file.exists()
        with open(log_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=AUDIT_FIELDS)
            if not exists: writer.writeheader()
            writer.writerow(entry)
        return True
    except Exception as e:
        print(f"AUDIT ERROR: {e}", flush=True)
        return False


def read_audit_log(cluster: str) -> List[Dict[str, Any]]:
    """Read full audit history for a cluster by globbing all daily files."""
    safe_name = "".join([c if c.isalnum() else "_" for c in cluster])
    pattern = str(DEFAULT_CONFIG_DIR / f"{safe_name}_*.csv")
    
    files = glob.glob(pattern)
    results = []
    
    for f_path in files:
        try:
            with open(f_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row["old_limit_gb"] = float(row["old_limit_gb"]) if row.get("old_limit_gb") else 0.0
                    row["new_limit_gb"] = float(row["new_limit_gb"]) if row.get("new_limit_gb") else 0.0
                    results.append(row)
        except Exception: continue
        
    results.sort(key=lambda x: x["timestamp"], reverse=True)
    return results


# --- Source: src/utils.py ---


from typing import List, Dict, Any, Optional, Tuple



def bytes_to_gb(value: Any) -> float:
    """Convert bytes to GB. Handles None or string inputs."""
    if not value:
        return 0.0
    try:
        return round(float(value) / (1024 ** 3), 2)
    except (ValueError, TypeError):
        return 0.0


def bytes_to_tb(value: Any) -> float:
    """Convert bytes to TB."""
    if not value:
        return 0.0
    try:
        return round(float(value) / (1024 ** 4), 2)
    except (ValueError, TypeError):
        return 0.0


def format_size(value: int) -> str:
    """Format byte value as human-readable string."""
    if not value:
        return "0 bytes"
    if value >= (1024 ** 4):
        return f"{bytes_to_tb(value):,.2f} TB"
    elif value >= (1024 ** 3):
        return f"{bytes_to_gb(value):,.2f} GB"
    elif value >= (1024 ** 2):
        return f"{round(value / (1024 ** 2), 2):,.2f} MB"
    elif value >= 1024:
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
    quotas: List[QuotaEntry],
    share_name: Optional[str] = None,
    access_zone: Optional[str] = None,
) -> List[QuotaEntry]:
    """Filter quotas by name or zone with explicit type support."""
    results = quotas
    if share_name:
        share_lower = share_name.lower()
        results = [q for q in results if share_lower in q.path.lower()]
    if access_zone and access_zone != "All":
        results = [q for q in results if q.access_zone == access_zone]
    return results


def get_top_offenders(quotas: List[QuotaEntry]) -> Dict[str, List[Dict[str, Any]]]:
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
from typing import Any



def init_session() -> None:
    """Initialize essential session state variables."""
    if "session_initialized" not in st.session_state:
        log_info("Initializing new user session state")
        st.session_state.session_initialized = True

    defaults = {
        "api_client": None,
        "selected_cluster": None,
        "admin_user": None,
        "quotas": [],
        "quotas_loaded": False,
        "selected_quota_paths": []
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def set_api_client(client: Any) -> None:
    st.session_state.api_client = client


def clear_api_client() -> None:
    st.session_state.api_client = None
    st.session_state.selected_cluster = None
    st.session_state.admin_user = None
    st.session_state.quotas = []
    st.session_state.quotas_loaded = False
    st.session_state.selected_quota_paths = []


def handle_api_error(error: Exception) -> bool:
    """Handle 401 errors and auto-logout."""
    err = str(error).lower()
    if any(x in err for x in ["401", "unauthorized", "invalid credentials"]):
        clear_api_client()
        st.error("🔒 Session expired. Please login again.")
        st.rerun()
        return True
    return False


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


# --- Source: src/main.py ---


import streamlit as st
from streamlit import session_state as state
import pandas as pd
from urllib.parse import urlparse

# Import modular logic








st.set_page_config(page_title="SmartQuota Manager", page_icon="📊", layout="wide")
init_session()

# Theme CSS
st.markdown("""
<style>
    :root { --p-orange: #F58513; --p-green: #006837; }
    .stApp { font-family: sans-serif; }
    h1, h2, h3, h4 { color: var(--p-green); }
    .stMetric [data-testid="stMetricValue"] { color: var(--p-orange) !important; }
</style>
""", unsafe_allow_html=True)


def login_section():
    st.sidebar.header("🔐 Login")
    inv = load_clusters()
    selected = st.sidebar.selectbox("Cluster", options=list(inv.keys()) + ["Custom URL..."], key="selected_cluster_box")
    
    url = st.sidebar.text_input("URL", placeholder="https://ip:8080") if selected == "Custom URL..." else inv.get(selected, "")
    user = st.sidebar.text_input("Username", placeholder="domain\\user")
    pwd = st.sidebar.text_input("Password", type="password")
    skip_ssl = st.sidebar.checkbox("Ignore SSL", value=True)
    
    if st.sidebar.button("Connect", use_container_width=True):
        if not all([url, user, pwd]):
            st.sidebar.error("Missing fields")
            return
        
        try:
            p = urlparse(url)
            host = p.hostname or url.split("//")[-1].split(":")[0] or "unknown_cluster"
            display_name = selected if selected != "Custom URL..." else host.replace(".", "_")
            
            api = IsilonAPI(url, user, pwd, verify_ssl=not skip_ssl)
            set_api_client(api)
            if selected == "Custom URL...": add_cluster(display_name, url)
            
            state.selected_cluster = display_name
            state.admin_user = user
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Failed: {e}")


def sidebar_tools():
    if not state.api_client: return
    st.sidebar.header(f"📍 {state.selected_cluster}")
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        clear_api_client()
        st.rerun()
    
    with st.sidebar.expander("⚙️ Inventory"):
        inv = load_clusters()
        for n, u in inv.items():
            c1, c2 = st.columns([4, 1])
            c1.caption(f"{n}")
            if c2.button("🗑️", key=f"d_{n}"):
                remove_cluster(n)
                st.rerun()


def main():
    if not st.session_state.get("startup_logged"):
        log_info("🚀 SmartQuota Manager starting...")
        st.session_state.startup_logged = True

    if not state.api_client:
        login_section()
    else:
        sidebar_tools()
        dashboard()


def dashboard():
    tabs = st.tabs(["📈 Dashboard", "🔧 Universal Manager", "➕ Provision", "📜 Audit History", "📥 Export"])
    
    with tabs[0]: monitoring_tab()
    with tabs[1]: modify_tab()
    with tabs[2]: provision_tab()
    with tabs[3]: audit_tab()
    with tabs[4]: export_tab()


def monitoring_tab():
    st.header("Cluster Overview")
    api = state.api_client
    if not state.quotas_loaded:
        with st.spinner("Loading..."):
            try:
                state.quotas = api.list_quotas(limit=500)[0]
                state.quotas_loaded = True
            except Exception as e:
                if not handle_api_error(e): st.error(e)
                return

    off = get_top_offenders(state.quotas)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("<h4 style='color:#D72638'>🔴 Critical</h4>", unsafe_allow_html=True)
        for i in off["critical"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")
    with c2:
        st.markdown("<h4 style='color:#F58513'>🟡 Warning</h4>", unsafe_allow_html=True)
        for i in off["warning"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")
    with c3:
        st.markdown("<h4 style='color:#006837'>🟢 Notice</h4>", unsafe_allow_html=True)
        for i in off["notice"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")

    st.divider()
    sc, zc = st.columns(2)
    search = sc.text_input("Search Name")
    zone = zc.selectbox("Zone", ["All"] + api.list_access_zones())
    
    filt = filter_quotas(state.quotas, search, zone)
    page = st.number_input("Page", min_value=1, value=1)
    items, total = paginate_list(filt, page)
    
    if items:
        df = pd.DataFrame([{
            "Share": q.path.split("/")[-1], "Zone": q.access_zone, "Path": q.path,
            "Usage %": f"{q.usage_percent:.1f}%", "Status": f"{status_badge(q.status)} {q.status.value.upper()}"
        } for q in items])
        st.dataframe(df, use_container_width=True, hide_index=True)
        state.selected_quota_paths = st.multiselect("Select share to manage", 
                                                    options=[f"{q.path} ({q.usage_percent:.1f}%)" for q in items],
                                                    max_selections=1)
    else: st.info("No records.")


def modify_tab():
    st.header("Universal Manager 🛠️")
    if not state.selected_quota_paths:
        st.info("Select a quota from the Dashboard.")
        return
    
    path_key = state.selected_quota_paths[0]
    quota = next((q for q in state.quotas if f"{q.path} ({q.usage_percent:.1f}%)" == path_key), None)
    if not quota: return

    api = state.api_client
    st.subheader(f"📁 {quota.path}")
    t1, t2, t3 = st.tabs(["⚙️ Quota Settings", "📸 Snapshots", "🔒 Permissions"])
    
    with t1:
        try:
            raw = api.get_raw_quota(quota.id)
            with st.form(f"u_{quota.id}"):
                payload = render_dynamic_grid(raw, f"e_{quota.id}")
                st.divider()
                if st.form_submit_button("APPLY PRODUCTION CHANGES", type="primary"):
                    if payload:
                        updated = api.update_quota_dynamic(quota.id, payload)
                        keys = ", ".join(payload.keys())
                        new_h = bytes_to_gb(updated.get("limits", {}).get("hard", 0)) if "limits" in payload else quota.hard_limit_gb
                        write_audit_entry(state.admin_user, state.selected_cluster, f"UPDATE ({keys})", quota.path.split("/")[-1], quota.path, quota.hard_limit_gb, new_h)
                        st.success("Updated successfully.")
                        state.quotas_loaded = False
                        st.rerun()
            
            with st.expander("🗑️ Danger Zone"):
                if st.text_input("Type 'DELETE' to confirm decommissioning", key=f"d_tx_{quota.id}") == "DELETE":
                    if st.button("CONFIRM PERMANENT DELETE", key=f"d_bt_{quota.id}", type="primary"):
                        api.delete_quota(quota.id)
                        write_audit_entry(state.admin_user, state.selected_cluster, "DELETE", quota.path.split("/")[-1], quota.path, quota.hard_limit_gb, 0)
                        state.quotas_loaded = False
                        st.rerun()
        except Exception as e:
            if not handle_api_error(e): st.error(f"Error: {e}")

    with t2: render_snapshot_viewer(api.get_snapshots_for_path(quota.path))
    with t3: render_acl_viewer(api.get_acl_for_path(quota.path, zone=quota.access_zone))


def provision_tab():
    st.header("Provision Quota ➕")
    api = state.api_client
    with st.form("p_form"):
        path = st.text_input("Path", placeholder="/ifs/data/...")
        col1, col2 = st.columns(2)
        q_type = col1.selectbox("Type", ["directory", "user", "group", "default-user", "default-group"])
        zone = col2.selectbox("Access Zone", api.list_access_zones())
        
        c1, c2, c3 = st.columns(3)
        h = c1.number_input("Hard (GB)", min_value=0.0)
        s = c2.number_input("Soft (GB)", min_value=0.0)
        a = c3.number_input("Advisory (GB)", min_value=0.0)
        
        enforced = st.checkbox("Enforced", value=True)
        snapshots = st.checkbox("Include Snapshots", value=False)
        
        if st.form_submit_button("CREATE QUOTA", type="primary"):
            if not path.startswith("/ifs"): st.error("Invalid path"); return
            try:
                api.create_quota(path, q_type, {"hard": h, "soft": s, "advisory": a}, zone, enforced, snapshots)
                write_audit_entry(state.admin_user, state.selected_cluster, "CREATE", path.split("/")[-1], path, 0, h)
                st.success(f"Quota created on {path}")
                state.quotas_loaded = False
            except Exception as e:
                if not handle_api_error(e): st.error(e)


def audit_tab():
    st.header("Full Audit History")
    st.caption("Combined daily logs for the current cluster.")
    entries = read_audit_log(state.selected_cluster)
    if entries:
        audit_df = pd.DataFrame(entries)
        st.dataframe(audit_df, hide_index=True, use_container_width=True)
        st.download_button("Download CSV History", audit_df.to_csv(index=False), f"audit_{state.selected_cluster}.csv")
    else: st.info("No logs found.")


def export_tab():
    st.header("Reporting")
    if st.button("Generate Full CSV Report"):
        with st.spinner("Processing large dataset..."):
            try:
                qs = state.api_client.list_all_quotas()
                mapping = state.api_client.get_protocol_mapping()
                data = [ {**q.to_dict(), "Protocol": mapping.get(q.path, "-")} for q in qs ]
                st.download_button("Download Report", pd.DataFrame(data).to_csv(index=False), "quota_report.csv")
            except Exception as e: st.error(e)


if __name__ == "__main__": main()


# --- ENTRY POINT ---
if __name__ == "__main__":
    main()
