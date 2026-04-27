"""UI component functions for SmartQuota Manager."""

import streamlit as st

from src.api import QuotaEntry, Status
from src.config import DEFAULT_CLUSTERS_FILE
import pandas as pd
from typing import List, Dict, Any


def status_badge(status: Status) -> str:
    """Get status emoji for UI display."""
    mapping = {
        Status.HEALTHY: "🟢",
        Status.WARNING: "🟡",
        Status.CRITICAL: "🔴",
    }
    return mapping.get(status, "⚪")


def color_for_status(status: Status) -> str:
    """Get color code for status."""
    mapping = {
        Status.HEALTHY: "#006837",  # Green (Pantone 3435)
        Status.WARNING: "#F58513",   # Orange (Pantone 158)
        Status.CRITICAL: "#D72638",  # Red for critical
    }
    return mapping.get(status, "#666666")


def format_bytes(bytes_val: int) -> str:
    """Format byte value as human-readable string."""
    if bytes_val >= (1024 ** 4):
        return f"{bytes_val / (1024 ** 4):,.2f} TB"
    elif bytes_val >= (1024 ** 3):
        return f"{bytes_val / (1024 ** 3):,.2f} GB"
    elif bytes_val >= (1024 ** 2):
        return f"{bytes_val / (1024 ** 2):,.2f} MB"
    elif bytes_val >= 1024:
        return f"{bytes_val / 1024:,.2f} KB"
    else:
        return f"{bytes_val} B"


def create_quota_table(
    quotas: List[QuotaEntry],
    key_prefix: str = "quota_table",
) -> List[QuotaEntry]:
    """
    Create a st.dataframe for quota entries with interactive features.
    
    Args:
        quotas: List of QuotaEntry objects
        key_prefix: Prefix for streamlit elements
    
    Returns:
        List of selected quota entries
    """
    if not quotas:
        st.info("No quotas found matching your criteria.")
        return []
    
    # Prepare data for DataFrame
    data = []
    for quota in quotas:
        data.append({
            "Share Name": quota.path.split("/")[-1],
            "Access Zone": quota.access_zone,
            "Path": quota.path,
            "Hard Limit (GB)": f"{quota.hard_limit_gb:.2f}",
            "Soft Limit (GB)": f"{quota.soft_limit_gb:.2f}",
            "Usage (GB)": f"{quota.usage_gb:.2f}",
            "Usage %": f"{quota.usage_percent:.1f}",
            "Status": f"{status_badge(quota.status)} {quota.status.value.upper()}",
        })
    
    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Configure column settings
    column_config = {
        "Share Name": st.column_config.TextColumn("Share Name"),
        "Access Zone": st.column_config.TextColumn("Zone"),
        "Path": st.column_config.TextColumn("Path"),
        "Hard Limit (GB)": st.column_config.TextColumn("Hard Limit"),
        "Soft Limit (GB)": st.column_config.TextColumn("Soft Limit"),
        "Usage (GB)": st.column_config.TextColumn("Usage"),
        "Usage %": st.column_config.TextColumn("%"),
        "Status": st.column_config.TextColumn("Status"),
    }
    
    # Display table with selection
    selected = st.dataframe(
        df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        on_select="rows",
        selection_mode="multi",
        key=f"{key_prefix}_table",
    )
    
    # Return selected indices (caller will map back to quotas)
    return selected.get("selected_rows", [])


def create_quota_viewer(
    quota: QuotaEntry,
    key_prefix: str = "quota_detail",
) -> Dict[str, Any]:
    """
    Create a detailed view of a single quota.
    
    Args:
        quota: The QuotaEntry to display
        key_prefix: Prefix for streamlit element keys
    
    Returns:
        Dictionary with form values if modified, else empty dict
    """
    st.subheader(f"Quota Details: {quota.path}")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Usage %", f"{quota.usage_percent:.1f}%")
        status = status_badge(quota.status) + " " + quota.status.value.upper()
        st.metric("Status", status)
    
    with col2:
        st.metric("Hard Limit", f"{quota.hard_limit_gb:.2f} GB")
        st.metric("Soft Limit", f"{quota.soft_limit_gb:.2f} GB")
    
    with col3:
        st.metric("Current Usage", f"{quota.usage_gb:.2f} GB")
        st.metric("Days at Current Rate", "N/A")  # Future enhancement
    
    # Show access zone
    st.text(f"Access Zone: {quota.access_zone}")
    
    # Show comment if exists
    if quota.comment:
        st.text(f"Comment: {quota.comment}")
    
    # Show users and groups
    if quota.users:
        st.text(f"Users: {', '.join(quota.users[:5])}{'...' if len(quota.users) > 5 else ''}")
    if quota.groups:
        st.text(f"Groups: {', '.join(quota.groups[:5])}{'...' if len(quota.groups) > 5 else ''}")
    
    return {}


def render_dynamic_grid(obj: Dict[str, Any], key_prefix: str = "dynamic") -> Dict[str, Any]:
    """
    Render an editable grid for any dictionary object.
    Returns a dictionary of modified fields.
    """
    st.markdown("### 🔧 Dynamic Property Editor")
    st.caption("Editable fields are shown as inputs. Complex objects are read-only.")
    
    modified_payload = {}
    
    # Sort keys for consistent UI
    for key in sorted(obj.keys()):
        val = obj[key]
        
        # Skip internal ID or system fields we shouldn't edit directly in the grid
        if key in ["id", "usage", "persona"]:
            st.text(f"{key}: {val}")
            continue
            
        if isinstance(val, bool):
            new_val = st.checkbox(f"{key}", value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, (int, float)):
            # Special handling for limits to show GB in label but keep bytes in value
            label = f"{key}"
            if "limit" in key.lower():
                gb_val = val / (1024**3)
                st.info(f"💡 {key} is approx {gb_val:.2f} GB")
            
            new_val = st.number_input(label, value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, str):
            new_val = st.text_input(f"{key}", value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, dict):
            with st.expander(f"📁 {key} (Nested)"):
                # Recursively render nested if it's 'limits', otherwise just show JSON
                if key == "limits":
                    nested_mods = render_dynamic_grid(val, key_prefix=f"{key_prefix}_{key}")
                    if nested_mods:
                        modified_payload[key] = nested_mods
                else:
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
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_acl_viewer(acl: Dict[str, Any]):
    """Render the ACL/Permissions view."""
    st.markdown("### 🔒 Filesystem Permissions (ACL)")
    
    if "error" in acl:
        st.error(f"Could not retrieve ACL: {acl['error']}")
        st.info(acl.get("note", ""))
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


def create_modification_form(
    quota: QuotaEntry,
    key_prefix: str = "modify_form",
) -> Dict[str, Any]:
    """
    Create a form to modify quota limits.
    
    Args:
        quota: The QuotaEntry to modify
        key_prefix: Prefix for streamlit element keys
    
    Returns:
        Dictionary with modification values if form submitted, else None
    """
    st.subheader(f"Modify Quota: {quota.path}")
    
    with st.form(key=f"{key_prefix}_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            new_hard = st.number_input(
                "New Hard Limit (GB)",
                min_value=0.0,
                value=quota.hard_limit_gb,
                step=1.0,
                format="%.2f",
            )
            if new_hard > 0 and new_hard < quota.usage_gb:
                st.error(f"⚠️ Warning: New limit ({new_hard:.2f} GB) is below current usage ({quota.usage_gb:.2f} GB)")
        
        with col2:
            new_soft = st.number_input(
                "New Soft Limit (GB)",
                min_value=0.0,
                value=quota.soft_limit_gb,
                step=1.0,
                format="%.2f",
            )
        
        # Warning if values are decreasing
        if new_hard < quota.hard_limit_gb:
            st.warning(f"↓ Hard limit decreased from {quota.hard_limit_gb:.2f} GB")
        if new_soft < quota.soft_limit_gb:
            st.warning(f"↓ Soft limit decreased from {quota.soft_limit_gb:.2f} GB")
        
        # Apply to children
        apply_to_children = st.checkbox(
            "Apply to entire quota tree (all children)",
            value=False,
        )
        
        # Confirmation
        confirm = st.checkbox(
            "CAUTION: I confirm this modification",
            value=False,
        )
        
        submitted = st.form_submit_button("Modify Quota", use_container_width=True)
    
    if submitted and confirm:
        return {
            "hard_limit_gb": new_hard,
            "soft_limit_gb": new_soft,
            "apply_to_children": apply_to_children,
        }
    
    return None
