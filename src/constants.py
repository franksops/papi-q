"""Constants and path definitions for SmartQuota Manager."""

from pathlib import Path

# Default paths
DEFAULT_CONFIG_DIR = Path.home() / ".papi-q"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_CLUSTERS_FILE = DEFAULT_CONFIG_DIR / "clusters.json"
DEFAULT_SYSTEM_LOG = DEFAULT_CONFIG_DIR / "system.log"

def ensure_config_dir() -> Path:
    """Create the config directory if it doesn't exist."""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_CONFIG_DIR
