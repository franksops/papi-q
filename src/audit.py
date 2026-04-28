"""Audit logging for SmartQuota Manager."""

import csv
import glob
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.config import DEFAULT_AUDIT_LOG, DEFAULT_CONFIG_DIR, load_config


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
