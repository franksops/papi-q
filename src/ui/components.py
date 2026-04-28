"""UI component functions for SmartQuota Manager."""

import streamlit as st
import pandas as pd
from typing import List, Dict, Any

from src.api import QuotaEntry, Status
from src.utils import status_badge, format_size, bytes_to_gb


def render_dynamic_grid(obj: Dict[str, Any], key_prefix: str = "dynamic") -> Dict[str, Any]:
    """
    Render an editable grid for any dictionary object.
    Returns a dictionary of modified fields.
    """
    st.markdown("### 🔧 Dynamic Property Editor")
    st.caption("Editable fields: Int, Str, Bool. Nested 'limits' are editable. All others read-only.")
    
    modified_payload = {}
    
    # Sort keys for consistent UI
    for key in sorted(obj.keys()):
        val = obj[key]
        
        # Non-editable metadata
        if key in ["id", "usage", "persona", "path", "zone"]:
            st.text(f"{key}: {val}")
            continue
            
        if isinstance(val, bool):
            new_val = st.checkbox(f"{key}", value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, (int, float)):
            # Special handling for limit fields to show GB hint
            label = f"{key}"
            if "limit" in key.lower() or key in ["hard", "soft", "advisory"]:
                st.info(f"💡 {key} = {bytes_to_gb(val):,.2f} GB")
            
            new_val = st.number_input(label, value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, str):
            new_val = st.text_input(f"{key}", value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, dict):
            # Special handling for 'limits' dict
            if key == "limits":
                with st.expander("📁 Limits Configuration", expanded=True):
                    nested_mods = render_dynamic_grid(val, key_prefix=f"{key_prefix}_{key}")
                    if nested_mods:
                        modified_payload[key] = nested_mods
            else:
                with st.expander(f"📁 {key} (Read-only)"):
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
    # Use formatted sizes for display
    if "size" in df.columns:
        df["size_readable"] = df["size"].apply(format_size)
        
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_acl_viewer(acl: Dict[str, Any]):
    """Render the ACL/Permissions view."""
    st.markdown("### 🔒 Filesystem Permissions (ACL)")
    
    if "error" in acl:
        st.error(f"Could not retrieve ACL: {acl['error']}")
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
    """Create a form for simple limit modifications."""
    st.subheader(f"Modify Quota: {quota.path}")
    
    with st.form(key=f"{key_prefix}_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_hard = st.number_input("New Hard Limit (GB)", min_value=0.0, value=quota.hard_limit_gb, step=1.0)
            if new_hard > 0 and new_hard < quota.usage_gb:
                st.error(f"⚠️ Warning: Limit ({new_hard:.2f} GB) < current usage ({quota.usage_gb:.2f} GB)")
        
        with col2:
            new_soft = st.number_input("New Soft Limit (GB)", min_value=0.0, value=quota.soft_limit_gb, step=1.0)
        
        apply_to_children = st.checkbox("Apply to child quotas", value=False)
        confirm = st.checkbox("I confirm this production change", value=False)
        submitted = st.form_submit_button("APPLY LIMITS", use_container_width=True)
    
    if submitted and confirm:
        return {
            "hard_limit_gb": new_hard,
            "soft_limit_gb": new_soft,
            "apply_to_children": apply_to_children,
        }
    return None
