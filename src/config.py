"""Configuration management for SmartQuota Manager."""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from src.logger import log_info, log_error, log_warning


from src.constants import DEFAULT_CONFIG_DIR, DEFAULT_CONFIG_FILE, DEFAULT_CLUSTERS_FILE, ensure_config_dir


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
