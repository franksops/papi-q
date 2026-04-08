"""Configuration management for SmartQuota Manager."""

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
