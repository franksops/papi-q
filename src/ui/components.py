"""UI component functions for SmartQuota Manager."""

import streamlit as st
import pandas as pd
from typing import List, Dict, Any
from src.utils import format_size, bytes_to_gb


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
        if key in ["id", "usage", "persona", "path", "zone", "access_zone", "type"]:
            st.text(f"{key}: {val}")
            continue
        
        # Handle None values
        if val is None:
            st.text(f"{key}: (null)")
            continue
            
        if isinstance(val, bool):
            new_val = st.checkbox(key, value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, (int, float)):
            if "limit" in key.lower() or key in ["hard", "soft", "advisory"]:
                st.info(f"💡 {key} = {bytes_to_gb(val):,.2f} GB")
            new_val = st.number_input(key, value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, str):
            new_val = st.text_input(key, value=val, key=f"{key_prefix}_{key}")
            if new_val != val:
                modified_payload[key] = new_val
        elif isinstance(val, dict):
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
    st.markdown("### 🔒 Filesystem Permissions (ACL) `READ-ONLY` ")
    
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
