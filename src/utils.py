"""Utility functions for SmartQuota Manager."""

from typing import List, Dict, Any, Optional, Tuple
from src.api import Status


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
