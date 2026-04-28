"""Utility functions for SmartQuota Manager."""

from typing import List, Dict, Any, Optional, Tuple
from src.api import Status, QuotaEntry


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
