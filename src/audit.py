"""Audit logging for SmartQuota Manager."""

import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.config import DEFAULT_AUDIT_LOG, load_config


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
    
    Args:
        admin: Username who performed the action
        cluster: Cluster name where action occurred
        action: Type of action (e.g., "QUOTA_MODIFY")
        share_name: Name of the share
        path: Quota path
        old_limit_gb: Previous hard limit in GB
        new_limit_gb: New hard limit in GB
        log_file: Path to audit log file (defaults to config value)
    
    Returns:
        True if successful, False otherwise
    """
    if log_file is None:
        log_file = load_config().get("log_file", str(DEFAULT_AUDIT_LOG))
    
    log_path = Path(log_file)
    
    # Ensure parent directory exists
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Build entry
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
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
    Read audit log entries with optional filtering.
    
    Args:
        cluster: Filter by cluster name
        share_name: Filter by share name (partial match)
        start_date: Filter entries from this date (ISO format)
        end_date: Filter entries until this date (ISO format)
        log_file: Path to audit log file
    
    Returns:
        List of audit log entries (oldest first)
    """
    if log_file is None:
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
                if cluster and row["cluster"] != cluster:
                    continue
                if share_name and share_name.lower() not in row["share_name"].lower():
                    continue
                if start_date and row["timestamp"] < start_date:
                    continue
                if end_date and row["timestamp"] > end_date:
                    continue
                
                # Convert numeric fields
                row["old_limit_gb"] = float(row["old_limit_gb"]) if row["old_limit_gb"] else 0.0
                row["new_limit_gb"] = float(row["new_limit_gb"]) if row["new_limit_gb"] else 0.0
                
                results.append(row)
        
        # Sort by timestamp (oldest first)
        results.sort(key=lambda x: x["timestamp"])
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
