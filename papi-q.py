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
import re
import pkgutil
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
    deps_map = {
        "streamlit": "streamlit",
        "pandas": "pandas",
        "urllib3": "urllib3",
        "dotenv": "python-dotenv"
    }
    missing = []
    for mod, pkg in deps_map.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
            
    # Special check for Isilon SDK (can be isi_sdk or isilon_sdk)
    try:
        try:
            import isi_sdk
        except ImportError:
            import isilon_sdk
    except ImportError:
        missing.append("isilon-sdk")
    
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
import importlib
import pkgutil
import re
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from urllib.parse import urlparse


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


from typing import List, Dict, Any



def bytes_to_gb(value: Any) -> float:
    """Convert bytes to GB. Handles None or string inputs."""
    if not value:
        return 0.0
    try:
        return round(float(value) / (1024 ** 3), 2)
    except (ValueError, TypeError):
        return 0.0


def format_size(value: int) -> str:
    """Format byte value as human-readable string."""
    if not value:
        return "0 bytes"
    if value >= (1024 ** 4):
        return f"{round(value / (1024 ** 4), 2):,.2f} TB"
    elif value >= (1024 ** 3):
        return f"{bytes_to_gb(value):,.2f} GB"
    elif value >= (1024 ** 2):
        return f"{round(value / (1024 ** 2), 2):,.2f} MB"
    elif value >= 1024:
        return f"{round(value / 1024, 2):,.2f} KB"
    else:
        return f"{value} bytes"


def status_badge(status: Any) -> str:
    """Get status emoji for UI display. Resilient to both Enum and string inputs."""
    # Extract value if it's an Enum member
    val = status.value if hasattr(status, "value") else str(status).lower()
    
    mapping = {
        "healthy": "🟢",
        "warning": "🟡",
        "critical": "🔴",
    }
    return mapping.get(val, "⚪")


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
        "selected_quota_paths": [],
        "confirm_shutdown": False,
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
        if key in ["id", "usage", "persona", "path", "zone", "access_zone", "type"]:
            st.text(f"{key}: {val}")
            continue
        
        # Handle None values
        if val is None:
            st.text(f"{key}: (null)")
            continue
            
        if isinstance(val, bool):
            new_val = st.checkbox(key, value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, (int, float)):
            if "limit" in key.lower() or key in ["hard", "soft", "advisory"]:
                # Show GB for limits, convert back to bytes on edit
                display_val = bytes_to_gb(val)
                new_val = st.number_input(f"{key} (GB)", value=display_val, key=f"{key_prefix}_{key}")
                if new_val != display_val:
                    modified_payload[key] = int(new_val * (1024 ** 3))
            else:
                new_val = st.number_input(key, value=val, key=f"{key_prefix}_{key}")
                if new_val != val:
                    modified_payload[key] = new_val
        elif isinstance(val, str):
            new_val = st.text_input(key, value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, dict):
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
    # Replace raw bytes with human-readable format
    if "size" in df.columns:
        df["size"] = df["size"].apply(format_size)
        
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_acl_viewer(acl: Dict[str, Any]):
    """Render the ACL/Permissions view."""
    st.markdown("### 🔒 Filesystem Permissions (ACL) `READ-ONLY` ")
    
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
import os
import signal

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
    
    url_input = st.sidebar.text_input("IP, Hostname, or URL", placeholder="10.1.1.50 or http://10.1.1.50") if selected == "Custom URL..." else inv.get(selected, "")
    user = st.sidebar.text_input("Username", placeholder="user, domain\\user, or user@domain")
    pwd = st.sidebar.text_input("Password", type="password")
    
    # SSL/Protocol Context
    is_http = url_input.lower().startswith("http://")
    skip_ssl = st.sidebar.checkbox("Ignore SSL (HTTPS only)", value=True, disabled=is_http)
    if is_http: st.sidebar.info("💡 Using plain HTTP (unencrypted)")
    
    if st.sidebar.button("Connect", use_container_width=True):
        if not all([url_input, user, pwd]):
            st.sidebar.error("Missing fields")
            return
        
        try:
            # Auto-format URL
            url = IsilonAPI.format_url(url_input)
            p = urlparse(url)
            host = p.hostname or url.split("//")[-1].split(":")[0] or "unknown_cluster"
            display_name = selected if selected != "Custom URL..." else host.replace(".", "_")
            
            api = IsilonAPI(url, user, pwd, verify_ssl=not skip_ssl)
            set_api_client(api)
            if selected == "Custom URL...": add_cluster(display_name, url)
            
            state.selected_cluster = display_name
            state.admin_user = user
            log_info(f"User {user} connected to {url}")
            st.rerun()
        except Exception as e:
            log_error(f"Login failed for {user} at {url_input}", e)
            st.sidebar.error(f"Failed: {e}")


def sidebar_tools():
    if not state.api_client: return
    st.sidebar.header(f"📍 {state.selected_cluster}")
    
    # Safety lock - must be checked to apply any changes or deletions
    st.sidebar.divider()
    safety_lock = st.sidebar.checkbox("🔓 UNLOCK PRODUCTION ACTIONS", value=False, key="safety_lock", help="Must be checked to apply any changes or deletions.")
    if not safety_lock:
        st.sidebar.info("🔒 Actions are currently locked.")
    
    if st.sidebar.button("🔄 Force Refresh Inventory", use_container_width=True):
        state.quotas_loaded = False
        st.rerun()

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

def sidebar_footer():
    st.sidebar.divider()
    if st.sidebar.button("🛑 Shutdown Application", use_container_width=True, type="primary"):
        state.confirm_shutdown = True

    if state.get("confirm_shutdown"):
        st.sidebar.warning("Are you sure?")
        cc1, cc2 = st.sidebar.columns(2)
        if cc1.button("Yes", use_container_width=True):
            log_info("Application shutdown requested via GUI")
            st.sidebar.success("Shutting down...")
            os.kill(os.getpid(), signal.SIGINT)
        if cc2.button("No", use_container_width=True):
            state.confirm_shutdown = False
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
    
    sidebar_footer()


def dashboard():
    tabs = st.tabs(["📈 Dashboard", "🔧 Universal Manager", "➕ Provision", "📜 Audit History", "📥 Export", "🔍 Debug Zones"])
    
    with tabs[0]: monitoring_tab()
    with tabs[1]: modify_tab()
    with tabs[2]: provision_tab()
    with tabs[3]: audit_tab()
    with tabs[4]: export_tab()
    with tabs[5]: debug_zones_tab()


def monitoring_tab():
    st.header("Cluster Overview")
    api = state.api_client
    
    # 1. Data Retrieval - Fetch ALL paths (SMB/NFS) and merge with quotas
    if not state.quotas_loaded:
        with st.spinner("Fetching all shares, exports, and quotas..."):
            try:
                # Get zones first
                state.zones = api.list_access_zones()
                log_info(f"Discovered access zones: {state.zones}")
                
                # Get ALL paths from SMB shares and NFS exports
                all_paths = api.get_all_paths()
                log_info(f"Found {len(all_paths)} paths from SMB/NFS")
                
                # Get quotas
                quotas = api.list_all_quotas()
                log_info(f"Found {len(quotas)} quotas")
                
                # Build quota lookup by path
                quota_by_path = {}
                for q in quotas:
                    # Normalize path
                    norm_path = q.path.rstrip("/")
                    quota_by_path[norm_path] = q
                
                # Merge paths with quota info
                state.all_paths_merged = []
                for path, info in all_paths.items():
                    quota = quota_by_path.get(path)
                    state.all_paths_merged.append({
                        "path": path,
                        "protocol": info["protocol"] or "-",
                        "zone": info["zone"],
                        "has_quota": quota is not None,
                        "quota": quota,
                        "usage_percent": quota.usage_percent if quota else 0,
                        "hard_limit_gb": quota.hard_limit_gb if quota else 0,
                        "usage_gb": quota.usage_gb if quota else 0,
                        "status": quota.status if quota else None,
                    })
                
                state.quotas = quotas  # Keep for modify_tab
                state.quotas_loaded = True
                
            except Exception as e:
                if not handle_api_error(e): st.error(f"Inventory Failed: {e}")
                return

    # Zone summary
    zones_in_data = sorted(list(set(p["zone"] for p in state.all_paths_merged)))
    zone_counts = {}
    zone_quota_counts = {}
    for z in zones_in_data:
        zone_paths = [p for p in state.all_paths_merged if p["zone"] == z]
        zone_counts[z] = len(zone_paths)
        zone_quota_counts[z] = len([p for p in zone_paths if p["has_quota"]])
    
    zone_info_expander = st.expander(f"📍 Access Zones ({len(zones_in_data)} zones, {len(state.all_paths_merged)} total paths, {len(state.quotas)} with quotas)", expanded=True)
    with zone_info_expander:
        zc1, zc2, zc3 = st.columns(3)
        for idx, zone in enumerate(zones_in_data):
            col = [zc1, zc2, zc3][idx % 3]
            with col:
                st.metric(f"Zone: {zone}", f"{zone_counts[zone]} paths ({zone_quota_counts[zone]} quotas)")

    # KPIs - only for paths with quotas
    paths_with_quotas = [p for p in state.all_paths_merged if p["has_quota"]]
    off = get_top_offenders([p["quota"] for p in paths_with_quotas])
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("<h4 style='color:#D72638'>🔴 Critical (>95%)</h4>", unsafe_allow_html=True)
        for i in off["critical"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")
    with c2:
        st.markdown("<h4 style='color:#F58513'>🟡 Warning (>80%)</h4>", unsafe_allow_html=True)
        for i in off["warning"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")
    with c3:
        st.markdown("<h4 style='color:#006837'>🟢 Notice (>70%)</h4>", unsafe_allow_html=True)
        for i in off["notice"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")

    st.divider()

    # 3. Filtering & Search
    sc, zc, gc, qc = st.columns([2, 1, 1, 1])
    search = sc.text_input("Search (Path or Share Name)")
    
    available_zones = ["All Zones"] + sorted(zones_in_data)
    zone_filter = zc.selectbox("Zone Filter", available_zones)
    group_by_zone = gc.checkbox("Group by Zone", value=False)
    show_only_quotas = qc.checkbox("Has Quota Only", value=False)
    
    # 4. Filter
    filt = state.all_paths_merged
    if search:
        filt = [p for p in filt if search.lower() in p["path"].lower()]
    if zone_filter != "All Zones":
        filt = [p for p in filt if p["zone"] == zone_filter]
    if show_only_quotas:
        filt = [p for p in filt if p["has_quota"]]
    
    # Sort - quotas first by usage, then paths without quotas
    filt.sort(key=lambda x: (-x["usage_percent"] if x["has_quota"] else 0, x["path"]))
    
    st.markdown(f"**Showing:** {len(filt)} of {len(state.all_paths_merged)} paths ({len([p for p in filt if p['has_quota']])} with quotas)")
    
    if not filt:
        st.info("No paths match the current filter.")
        return

    def render_path_table(paths, key_suffix=""):
        page_size = 25
        total_pages = (len(paths) + page_size - 1) // page_size if paths else 1
        page = st.number_input(f"Page {key_suffix}", min_value=1, max_value=max(1, total_pages), value=1, key=f"page_{key_suffix}")
        
        start = (page - 1) * page_size
        items = paths[start:start + page_size]
        
        if items:
            df_data = []
            for p in items:
                quota_status = ""
                usage_info = ""
                if p["has_quota"]:
                    quota_status = f"{status_badge(p['status'])} {p['status'].value.upper() if p['status'] else 'N/A'}"
                    usage_info = f"{p['usage_percent']:.1f}%"
                else:
                    quota_status = "❌ No Quota"
                    usage_info = "N/A"
                
                df_data.append({
                    "Share": p["path"].split("/")[-1],
                    "Protocol": p["protocol"],
                    "Zone": p["zone"],
                    "Path": p["path"],
                    "Quota": "✅" if p["has_quota"] else "❌",
                    "Usage %": usage_info,
                    "Status": quota_status
                })
            
            st.dataframe(pd.DataFrame(df_data), use_container_width=True, hide_index=True)
            
            # Create selection options - only for paths with quotas
            sel_options = [f"{p['path']} [{p['zone']}] ({p['usage_percent']:.1f}%)" for p in items if p["has_quota"]]
            if sel_options:
                selected = st.multiselect("Select path with quota to manage", 
                                            options=sel_options,
                                            max_selections=1,
                                            key=f"sel_{key_suffix}")
                if selected:
                    state.selected_quota_paths = selected
            elif items:
                st.caption("💡 No quotas on this page. Select a path with ✅ to manage.")
        else:
            st.info("No items on this page.")

    if group_by_zone:
        # Group by zone - show each zone as expandable section
        for z in zones_in_data:
            zone_items = [p for p in filt if p["zone"] == z]
            if zone_items:
                quotas_in_zone = [p for p in zone_items if p["has_quota"]]
                zone_usage = sum(p["quota"].usage_bytes for p in quotas_in_zone if p["quota"])
                zone_capacity = sum(p["quota"].hard_limit_bytes for p in quotas_in_zone if p["quota"] and p["quota"].hard_limit_bytes > 0)
                
                if zone_capacity > 0:
                    overall_pct = (zone_usage / zone_capacity) * 100
                    header = f"📁 Zone: {z} ({len(zone_items)} paths, {len(quotas_in_zone)} quotas, {overall_pct:.1f}% used)"
                else:
                    header = f"📁 Zone: {z} ({len(zone_items)} paths, {len(quotas_in_zone)} quotas)"
                    
                with st.expander(header, expanded=True):
                    render_path_table(zone_items, key_suffix=f"zone_{z}")
    else:
        render_path_table(filt, key_suffix="all")


def modify_tab():
    st.header("Universal Manager 🛠️")
    if not state.selected_quota_paths:
        st.info("Select a quota from the Dashboard.")
        return
    
    path_key = state.selected_quota_paths[0]
    # Handle both old format: "path (usage%)" and new format: "path [zone] (usage%)"
    quota = None
    for q in state.quotas:
        option_new = f"{q.path} [{q.access_zone}] ({q.usage_percent:.1f}%)"
        option_old = f"{q.path} ({q.usage_percent:.1f}%)"
        if option_new == path_key or option_old == path_key:
            quota = q
            break
    if not quota: 
        st.error(f"Could not find quota for selection: {path_key}")
        return

    api = state.api_client
    st.subheader(f"📁 {quota.path}")
    
    # Safety lock is in sidebar_tools - read from session state
    safety_lock = state.get("safety_lock", False)
    if not safety_lock:
        st.sidebar.warning("🔒 Enable safety lock in sidebar to make changes.")

    t1, t2, t3 = st.tabs(["⚙️ Quota Settings", "📸 Snapshots", "🔒 Permissions"])
    
    with t1:
        try:
            raw = api.get_raw_quota(quota.id)
            with st.form(f"u_{quota.id}"):
                payload = render_dynamic_grid(raw, f"e_{quota.id}")
                st.divider()
                
                # Destructive Change Detection
                destructive_warns = []
                if "limits" in payload:
                    new_lims = payload["limits"]
                    curr_lims = raw.get("limits", {})
                    
                    for key in ["hard", "soft", "advisory"]:
                        if key in new_lims:
                            new_val = int(new_lims[key])
                            curr_val = int(curr_lims.get(key, 0))
                            if new_val < curr_val and new_val != 0:
                                destructive_warns.append(f"Reducing {key} limit from {bytes_to_gb(curr_val)}GB to {bytes_to_gb(new_val)}GB.")
                            if new_val < quota.usage_bytes and new_val != 0:
                                destructive_warns.append(f"New {key} limit is BELOW current usage ({bytes_to_gb(quota.usage_bytes)}GB)!")

                if destructive_warns:
                    for w in destructive_warns: st.warning(f"⚠️ {w}")
                    confirm_destructive = st.checkbox("I confirm these REDUCTIONS are intended", value=False)
                else:
                    confirm_destructive = True

                submit_disabled = not safety_lock or (destructive_warns and not confirm_destructive)
                
                if st.form_submit_button("APPLY PRODUCTION CHANGES", type="primary", disabled=submit_disabled):
                    if payload:
                        updated = api.update_quota_dynamic(quota.id, payload)
                        keys = ", ".join(payload.keys())
                        new_h = bytes_to_gb(updated.get("limits", {}).get("hard", 0)) if "limits" in payload else quota.hard_limit_gb
                        write_audit_entry(state.admin_user, state.selected_cluster, f"UPDATE ({keys})", quota.path.split("/")[-1], quota.path, quota.hard_limit_gb, new_h)
                        st.success("Updated successfully.")
                        state.quotas_loaded = False
                        st.rerun()
            
            with st.expander("🗑️ Danger Zone"):
                if not safety_lock:
                    st.error("🔒 Production actions are locked in the sidebar.")
                else:
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
    
    safety_lock = state.get("safety_lock", False)
    
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
        
        btn_label = "CREATE QUOTA" if safety_lock else "CREATE QUOTA (LOCKED)"
        if st.form_submit_button(btn_label, type="primary", disabled=not safety_lock):
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
                # Use already-loaded data if available, otherwise fetch
                if state.quotas_loaded and hasattr(state, 'all_paths_merged'):
                    # Export all paths with quota info
                    rows = []
                    for p in state.all_paths_merged:
                        row = {
                            "path": p["path"],
                            "zone": p["zone"],
                            "protocol": p["protocol"],
                            "has_quota": "Yes" if p["has_quota"] else "No",
                        }
                        if p["has_quota"]:
                            row.update({
                                "hard_limit_gb": p["quota"].hard_limit_gb,
                                "soft_limit_gb": p["quota"].soft_limit_gb,
                                "usage_gb": p["quota"].usage_gb,
                                "usage_percent": round(p["usage_percent"], 1),
                                "status": p["status"].value if p["status"] else "N/A",
                            })
                        rows.append(row)
                    st.download_button("Download Report", pd.DataFrame(rows).to_csv(index=False), "quota_report.csv")
                else:
                    # Fallback: just export quotas
                    qs = state.api_client.list_all_quotas()
                    data = [q.to_dict() for q in qs]
                    st.download_button("Download Report", pd.DataFrame(data).to_csv(index=False), "quota_report.csv")
            except Exception as e: st.error(e)


def debug_zones_tab():
    st.header("🔍 Zone Debugging")
    st.caption("Use this to diagnose zone discovery issues.")
    api = state.api_client
    
    if st.button("🔄 Run Zone Discovery Debug"):
        with st.spinner("Analyzing zone data..."):
            debug = api.debug_zone_discovery()
            
            st.subheader("Available APIs")
            st.json({
                "zones_api": debug["zones_api_available"],
                "namespaces_api": debug["namespaces_api_available"],
                "protocols_api": debug["protocols_api_available"],
                "quota_api": debug["quota_api_available"],
            })
            
            st.subheader("Zones Info (Final)")
            st.json(debug["zones_info"])
            
            st.subheader("Sample Quotas (First 3)")
            for i, sample in enumerate(debug["sample_quotas"]):
                with st.expander(f"Quota {i+1}: {sample['path']}", expanded=True):
                    st.write(f"**ID:** {sample['id']}")
                    st.write(f"**Path:** {sample['path']}")
                    st.write(f"**zone attribute:** {sample['zone_attr']}")
                    st.write(f"**access_zone attribute:** {sample['access_zone_attr']}")
                    st.write(f"**zone_name attribute:** {sample['zone_name_attr']}")
                    st.write(f"**All zone-related raw attrs:**")
                    st.json(sample["raw_attrs"])
            
            st.subheader("Raw API Responses")
            st.json({k: v for k, v in debug.items() if k.startswith("zones_api_") or k.startswith("quota_")})


# --- ENTRY POINT ---
if __name__ == "__main__":
    main()
