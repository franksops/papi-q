"""Utility functions for SmartQuota Manager."""

from typing import List, Dict, Any
from src.api import Status, QuotaEntry


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
        return f"{bytes_to_tb(value):,.2f} TB"
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


def color_for_status(status: Any) -> str:
    """Get hex color for status display. Resilient to both Enum and string inputs."""
    val = status.value if hasattr(status, "value") else str(status).lower()
    
    mapping = {
        "healthy": "#006837",
        "warning": "#F58513",
        "critical": "#D72638",
    }
    return mapping.get(val, "#666666")


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
