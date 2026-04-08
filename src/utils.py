"""Utility functions for SmartQuota Manager."""

import re
from typing import List, Dict, Any, Optional, Tuple

from src.api import QuotaEntry, Status


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
