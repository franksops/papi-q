"""Main Streamlit application for SmartQuota Manager."""

import streamlit as st
from streamlit import session_state as state
import pandas as pd
from urllib.parse import urlparse
import os
import signal

# Import modular logic
from src.config import load_clusters, add_cluster, remove_cluster
from src.api import IsilonAPI
from src.audit import write_audit_entry, read_audit_log
from src.logger import log_info, log_error
from src.utils import get_top_offenders, status_badge, bytes_to_gb
from src.ui.components import render_dynamic_grid, render_snapshot_viewer, render_acl_viewer
from src.ui.session import init_session, set_api_client, clear_api_client, handle_api_error

st.set_page_config(page_title="SmartQuota Manager", page_icon="📊", layout="wide")
init_session()

# Theme CSS
st.markdown("""
<style>
    :root { --p-orange: #F58513; --p-green: #006837; }
    .stApp { font-family: sans-serif; }
    h1, h2, h3, h4 { color: var(--p-green); }
    .stMetric [data-testid="stMetricValue"] { color: var(--p-orange) !important; }
</style>
""", unsafe_allow_html=True)


def login_section():
    st.sidebar.header("🔐 Login")
    inv = load_clusters()
    selected = st.sidebar.selectbox("Cluster", options=list(inv.keys()) + ["Custom URL..."], key="selected_cluster_box")
    
    url_input = st.sidebar.text_input("IP, Hostname, or URL", placeholder="10.1.1.50 or http://10.1.1.50") if selected == "Custom URL..." else inv.get(selected, "")
    user = st.sidebar.text_input("Username", placeholder="user, domain\\user, or user@domain")
    pwd = st.sidebar.text_input("Password", type="password")
    
    # SSL/Protocol Context
    is_http = url_input.lower().startswith("http://")
    skip_ssl = st.sidebar.checkbox("Ignore SSL (HTTPS only)", value=True, disabled=is_http)
    if is_http: st.sidebar.info("💡 Using plain HTTP (unencrypted)")
    
    if st.sidebar.button("Connect", use_container_width=True):
        if not all([url_input, user, pwd]):
            st.sidebar.error("Missing fields")
            return
        
        try:
            # Auto-format URL
            url = IsilonAPI.format_url(url_input)
            p = urlparse(url)
            host = p.hostname or url.split("//")[-1].split(":")[0] or "unknown_cluster"
            display_name = selected if selected != "Custom URL..." else host.replace(".", "_")
            
            api = IsilonAPI(url, user, pwd, verify_ssl=not skip_ssl)
            set_api_client(api)
            if selected == "Custom URL...": add_cluster(display_name, url)
            
            state.selected_cluster = display_name
            state.admin_user = user
            log_info(f"User {user} connected to {url}")
            st.rerun()
        except Exception as e:
            log_error(f"Login failed for {user} at {url_input}", e)
            st.sidebar.error(f"Failed: {e}")


def sidebar_tools():
    if not state.api_client: return
    st.sidebar.header(f"📍 {state.selected_cluster}")
    
    # Safety lock - must be checked to apply any changes or deletions
    st.sidebar.divider()
    safety_lock = st.sidebar.checkbox("🔓 UNLOCK PRODUCTION ACTIONS", value=False, key="safety_lock", help="Must be checked to apply any changes or deletions.")
    if not safety_lock:
        st.sidebar.info("🔒 Actions are currently locked.")
    
    if st.sidebar.button("🔄 Force Refresh Inventory", use_container_width=True):
        state.quotas_loaded = False
        state.selected_quota_id = None
        st.rerun()

    if st.sidebar.button("🚪 Logout", use_container_width=True):
        clear_api_client()
        st.rerun()
    
    with st.sidebar.expander("⚙️ Inventory"):
        inv = load_clusters()
        for n, u in inv.items():
            c1, c2 = st.columns([4, 1])
            c1.caption(f"{n}")
            if c2.button("🗑️", key=f"d_{n}"):
                remove_cluster(n)
                st.rerun()

def sidebar_footer():
    st.sidebar.divider()
    if st.sidebar.button("🛑 Shutdown Application", use_container_width=True, type="primary"):
        state.confirm_shutdown = True

    if state.get("confirm_shutdown"):
        st.sidebar.warning("Are you sure?")
        cc1, cc2 = st.sidebar.columns(2)
        if cc1.button("Yes", use_container_width=True):
            log_info("Application shutdown requested via GUI")
            st.sidebar.success("Shutting down...")
            os.kill(os.getpid(), signal.SIGINT)
        if cc2.button("No", use_container_width=True):
            state.confirm_shutdown = False
            st.rerun()


def main():
    if not st.session_state.get("startup_logged"):
        log_info("🚀 SmartQuota Manager starting...")
        st.session_state.startup_logged = True

    if not state.api_client:
        login_section()
    else:
        sidebar_tools()
        dashboard()
    
    sidebar_footer()


def dashboard():
    tabs = st.tabs(["📈 Dashboard", "🔧 Universal Manager", "➕ Provision", "📜 Audit History", "📥 Export", "🔍 Debug Zones"])
    
    with tabs[0]: monitoring_tab()
    with tabs[1]: modify_tab()
    with tabs[2]: provision_tab()
    with tabs[3]: audit_tab()
    with tabs[4]: export_tab()
    with tabs[5]: debug_zones_tab()


def monitoring_tab():
    st.header("Cluster Overview")
    api = state.api_client
    
    # 1. Data Retrieval - Fetch ALL paths (SMB/NFS) and merge with quotas
    if not state.quotas_loaded:
        with st.spinner("Fetching all shares, exports, and quotas..."):
            try:
                # Get ALL paths from SMB shares and NFS exports
                all_paths = api.get_all_paths()
                log_info(f"Found {len(all_paths)} paths from SMB/NFS")
                
                # Get quotas
                quotas = api.list_all_quotas()
                log_info(f"Found {len(quotas)} quotas")
                
                # Build quota lookup by normalized path
                quota_by_path = {}
                for q in quotas:
                    # Normalize path: remove trailing slashes, lowercase for comparison
                    norm_path = q.path.rstrip("/").lower()
                    quota_by_path[norm_path] = q
                
                # Track which quota paths we've matched
                matched_quota_paths = set()
                
                # Merge paths with quota info
                state.all_paths_merged = []
                for path, info in all_paths.items():
                    norm_path = path.rstrip("/").lower()
                    quota = quota_by_path.get(norm_path)
                    if quota:
                        matched_quota_paths.add(id(quota))
                    state.all_paths_merged.append({
                        "path": path,
                        "protocol": info["protocol"] or "-",
                        "zone": info["zone"],
                        "has_quota": quota is not None,
                        "quota": quota,
                        "usage_percent": quota.usage_percent if quota else 0,
                        "hard_limit_gb": quota.hard_limit_gb if quota else 0,
                        "usage_gb": quota.usage_gb if quota else 0,
                        "status": quota.status if quota else None,
                    })
                
                # Add quotas that don't have a corresponding SMB/NFS path
                # These are quotas on paths that aren't shared
                for q in quotas:
                    if id(q) not in matched_quota_paths:
                        state.all_paths_merged.append({
                            "path": q.path,
                            "protocol": "-",  # No share/export
                            "zone": q.access_zone,
                            "has_quota": True,
                            "quota": q,
                            "usage_percent": q.usage_percent,
                            "hard_limit_gb": q.hard_limit_gb,
                            "usage_gb": q.usage_gb,
                            "status": q.status,
                        })
                
                state.quotas = quotas  # Keep for modify_tab
                state.quotas_loaded = True
                
            except Exception as e:
                if not handle_api_error(e): st.error(f"Inventory Failed: {e}")
                return

    # Zone summary
    zones_in_data = sorted(list(set(p["zone"] for p in state.all_paths_merged)))
    zone_counts = {}
    zone_quota_counts = {}
    for z in zones_in_data:
        zone_paths = [p for p in state.all_paths_merged if p["zone"] == z]
        zone_counts[z] = len(zone_paths)
        zone_quota_counts[z] = len([p for p in zone_paths if p["has_quota"]])
    
    zone_info_expander = st.expander(f"📍 Access Zones ({len(zones_in_data)} zones, {len(state.all_paths_merged)} total paths, {len(state.quotas)} with quotas)", expanded=True)
    with zone_info_expander:
        zc1, zc2, zc3 = st.columns(3)
        for idx, zone in enumerate(zones_in_data):
            col = [zc1, zc2, zc3][idx % 3]
            with col:
                st.metric(f"Zone: {zone}", f"{zone_counts[zone]} paths ({zone_quota_counts[zone]} quotas)")

    # KPIs - only for paths with quotas
    paths_with_quotas = [p for p in state.all_paths_merged if p["has_quota"]]
    off = get_top_offenders([p["quota"] for p in paths_with_quotas])
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("<h4 style='color:#D72638'>🔴 Critical (>95%)</h4>", unsafe_allow_html=True)
        for i in off["critical"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")
    with c2:
        st.markdown("<h4 style='color:#F58513'>🟡 Warning (>80%)</h4>", unsafe_allow_html=True)
        for i in off["warning"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")
    with c3:
        st.markdown("<h4 style='color:#006837'>🟢 Notice (>70%)</h4>", unsafe_allow_html=True)
        for i in off["notice"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")

    st.divider()

    # 3. Filtering & Search
    sc, zc, gc, qc = st.columns([2, 1, 1, 1])
    search = sc.text_input("Search (Path or Share Name)")
    
    available_zones = ["All Zones"] + sorted(zones_in_data)
    zone_filter = zc.selectbox("Zone Filter", available_zones)
    group_by_zone = gc.checkbox("Group by Zone", value=False)
    show_only_quotas = qc.checkbox("Has Quota Only", value=False)
    
    # 4. Filter
    filt = state.all_paths_merged
    if search:
        filt = [p for p in filt if search.lower() in p["path"].lower()]
    if zone_filter != "All Zones":
        filt = [p for p in filt if p["zone"] == zone_filter]
    if show_only_quotas:
        filt = [p for p in filt if p["has_quota"]]
    
    # Sort - quotas first by usage, then paths without quotas
    filt.sort(key=lambda x: (-x["usage_percent"] if x["has_quota"] else 0, x["path"]))
    
    st.markdown(f"**Showing:** {len(filt)} of {len(state.all_paths_merged)} paths ({len([p for p in filt if p['has_quota']])} with quotas)")
    
    if not filt:
        st.info("No paths match the current filter.")
        return

    def render_path_table(paths, key_suffix=""):
        page_size = 25
        total_pages = (len(paths) + page_size - 1) // page_size if paths else 1
        page = st.number_input(f"Page {key_suffix}", min_value=1, max_value=max(1, total_pages), value=1, key=f"page_{key_suffix}")
        
        start = (page - 1) * page_size
        items = paths[start:start + page_size]
        
        if items:
            df_data = []
            for p in items:
                quota_status = ""
                usage_info = ""
                if p["has_quota"]:
                    quota_status = f"{status_badge(p['status'])} {p['status'].value.upper() if p['status'] else 'N/A'}"
                    usage_info = f"{p['usage_percent']:.1f}%"
                else:
                    quota_status = "❌ No Quota"
                    usage_info = "N/A"
                
                df_data.append({
                    "Share": p["path"].split("/")[-1],
                    "Protocol": p["protocol"],
                    "Zone": p["zone"],
                    "Path": p["path"],
                    "Quota": "✅" if p["has_quota"] else "❌",
                    "Usage %": usage_info,
                    "Status": quota_status
                })
            
            st.dataframe(pd.DataFrame(df_data), use_container_width=True, hide_index=True)
            
            # Create selection options - only for paths with quotas
            # Include quota ID for stable matching
            # Include page number in key to prevent selection state leaking between pages
            sel_key = f"sel_{key_suffix}_p{page}"
            sel_options = {
                f"{p['path']} [{p['zone']}] ({p['usage_percent']:.1f}%)": p['quota'].id
                for p in items if p["has_quota"]
            }
            if sel_options:
                selected = st.selectbox("Select path with quota to manage", 
                                            options=list(sel_options.keys()),
                                            key=sel_key)
                if selected:
                    state.selected_quota_id = sel_options[selected]
            elif items:
                st.caption("💡 No quotas on this page. Select a path with ✅ to manage.")
        else:
            st.info("No items on this page.")

    if group_by_zone:
        # Group by zone - show each zone as expandable section
        for z in zones_in_data:
            zone_items = [p for p in filt if p["zone"] == z]
            if zone_items:
                quotas_in_zone = [p for p in zone_items if p["has_quota"]]
                zone_usage = sum(p["quota"].usage_bytes for p in quotas_in_zone if p["quota"])
                zone_capacity = sum(p["quota"].hard_limit_bytes for p in quotas_in_zone if p["quota"] and p["quota"].hard_limit_bytes > 0)
                
                if zone_capacity > 0:
                    overall_pct = (zone_usage / zone_capacity) * 100
                    header = f"📁 Zone: {z} ({len(zone_items)} paths, {len(quotas_in_zone)} quotas, {overall_pct:.1f}% used)"
                else:
                    header = f"📁 Zone: {z} ({len(zone_items)} paths, {len(quotas_in_zone)} quotas)"
                    
                with st.expander(header, expanded=True):
                    render_path_table(zone_items, key_suffix=f"zone_{z}")
    else:
        render_path_table(filt, key_suffix="all")


def modify_tab():
    st.header("Universal Manager 🛠️")
    if not state.selected_quota_id:
        st.info("Select a quota from the Dashboard.")
        return
    
    # Find quota by ID
    quota = None
    for q in state.quotas:
        if q.id == state.selected_quota_id:
            quota = q
            break
    if not quota: 
        st.error(f"Could not find quota with ID: {state.selected_quota_id}")
        state.selected_quota_id = None  # Clear invalid selection
        return

    api = state.api_client
    st.subheader(f"📁 {quota.path}")
    
    # Safety lock is in sidebar_tools - read from session state
    safety_lock = state.get("safety_lock", False)
    if not safety_lock:
        st.sidebar.warning("🔒 Enable safety lock in sidebar to make changes.")

    t1, t2, t3 = st.tabs(["⚙️ Quota Settings", "📸 Snapshots", "🔒 Permissions"])
    
    with t1:
        try:
            raw = api.get_raw_quota(quota.id)
            
            # Collect modified fields first
            payload = render_dynamic_grid(raw, f"e_{quota.id}")
            
            # Destructive Change Detection (outside form for better UX)
            destructive_warns = []
            if "limits" in payload:
                new_lims = payload["limits"]
                curr_lims = raw.get("limits", {})
                
                for key in ["hard", "soft", "advisory"]:
                    if key in new_lims:
                        new_val = int(new_lims[key])
                        curr_val = int(curr_lims.get(key, 0))
                        if new_val < curr_val and new_val != 0:
                            destructive_warns.append(f"Reducing {key} limit from {bytes_to_gb(curr_val)}GB to {bytes_to_gb(new_val)}GB.")
                        if new_val < quota.usage_bytes and new_val != 0:
                            destructive_warns.append(f"New {key} limit is BELOW current usage ({bytes_to_gb(quota.usage_bytes)}GB)!")

            with st.form(f"u_{quota.id}", clear_on_submit=False):
                # Show destructive warnings
                if destructive_warns:
                    for w in destructive_warns: st.warning(f"⚠️ {w}")
                    confirm_destructive = st.checkbox("I confirm these REDUCTIONS are intended", value=False)
                else:
                    confirm_destructive = True

                # Calculate disabled state
                submit_disabled = not safety_lock or (destructive_warns and not confirm_destructive)
                
                # Status indicator
                if submit_disabled:
                    if not safety_lock:
                        st.error("🔒 Safety lock disabled - enable in sidebar to apply changes")
                    elif destructive_warns:
                        st.warning("⚠️ Acknowledge reductions above to enable submit")
                
                # Submit button - prominent placement
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    submitted = st.form_submit_button(
                        "💾 APPLY PRODUCTION CHANGES", 
                        type="primary",
                        disabled=submit_disabled
                    )
                
                if submitted and payload:
                    updated = api.update_quota_dynamic(quota.id, payload)
                    keys = ", ".join(payload.keys())
                    new_h = bytes_to_gb(updated.get("limits", {}).get("hard", 0)) if "limits" in payload else quota.hard_limit_gb
                    write_audit_entry(state.admin_user, state.selected_cluster, f"UPDATE ({keys})", quota.path.split("/")[-1], quota.path, quota.hard_limit_gb, new_h)
                    st.success("✅ Updated successfully!")
                    state.quotas_loaded = False
                    st.rerun()
            
            with st.expander("🗑️ Danger Zone"):
                if not safety_lock:
                    st.error("🔒 Production actions are locked in the sidebar.")
                else:
                    if st.text_input("Type 'DELETE' to confirm decommissioning", key=f"d_tx_{quota.id}") == "DELETE":
                        if st.button("CONFIRM PERMANENT DELETE", key=f"d_bt_{quota.id}", type="primary"):
                            api.delete_quota(quota.id)
                            write_audit_entry(state.admin_user, state.selected_cluster, "DELETE", quota.path.split("/")[-1], quota.path, quota.hard_limit_gb, 0)
                            state.quotas_loaded = False
                            st.rerun()
        except Exception as e:
            if not handle_api_error(e): st.error(f"Error: {e}")

    with t2: render_snapshot_viewer(api.get_snapshots_for_path(quota.path))
    with t3: render_acl_viewer(api.get_acl_for_path(quota.path, zone=quota.access_zone))


def provision_tab():
    st.header("Provision Quota ➕")
    api = state.api_client
    
    safety_lock = state.get("safety_lock", False)
    
    with st.form("p_form"):
        path = st.text_input("Path", placeholder="/ifs/data/...")
        col1, col2 = st.columns(2)
        q_type = col1.selectbox("Type", ["directory", "user", "group", "default-user", "default-group"])
        zone = col2.selectbox("Access Zone", api.list_access_zones())
        
        c1, c2, c3 = st.columns(3)
        h = c1.number_input("Hard (GB)", min_value=0.0)
        s = c2.number_input("Soft (GB)", min_value=0.0)
        a = c3.number_input("Advisory (GB)", min_value=0.0)
        
        enforced = st.checkbox("Enforced", value=True)
        snapshots = st.checkbox("Include Snapshots", value=False)
        
        btn_label = "CREATE QUOTA" if safety_lock else "CREATE QUOTA (LOCKED)"
        if st.form_submit_button(btn_label, type="primary", disabled=not safety_lock):
            # Normalize path: ensure it starts with /ifs
            if not path:
                st.error("Path is required")
                return
            if path.startswith('/ifs'):
                normalized_path = path.rstrip('/') or '/ifs'
            else:
                path_clean = path.lstrip('/')
                if path_clean.startswith('ifs'):
                    path_clean = path_clean[3:].lstrip('/')
                normalized_path = f'/ifs/{path_clean}' if path_clean else '/ifs'
            try:
                api.create_quota(normalized_path, q_type, {"hard": h, "soft": s, "advisory": a}, zone, enforced, snapshots)
                write_audit_entry(state.admin_user, state.selected_cluster, "CREATE", normalized_path.split("/")[-1], normalized_path, 0, h)
                st.success(f"Quota created on {normalized_path}")
                state.quotas_loaded = False
            except Exception as e:
                if not handle_api_error(e): st.error(e)


def audit_tab():
    st.header("Full Audit History")
    st.caption("Combined daily logs for the current cluster.")
    entries = read_audit_log(state.selected_cluster)
    if entries:
        audit_df = pd.DataFrame(entries)
        st.dataframe(audit_df, hide_index=True, use_container_width=True)
        st.download_button("Download CSV History", audit_df.to_csv(index=False), f"audit_{state.selected_cluster}.csv")
    else: st.info("No logs found.")


def export_tab():
    st.header("Reporting")
    try:
        # Use already-loaded data if available, otherwise fetch
        if state.quotas_loaded and hasattr(state, 'all_paths_merged'):
            rows = []
            for p in state.all_paths_merged:
                row = {
                    "path": p["path"],
                    "zone": p["zone"],
                    "protocol": p["protocol"],
                    "has_quota": "Yes" if p["has_quota"] else "No",
                }
                if p["has_quota"]:
                    row.update({
                        "hard_limit_gb": p["quota"].hard_limit_gb,
                        "soft_limit_gb": p["quota"].soft_limit_gb,
                        "usage_gb": p["quota"].usage_gb,
                        "usage_percent": round(p["usage_percent"], 1),
                        "status": p["status"].value if p["status"] else "N/A",
                    })
                rows.append(row)
            csv_data = pd.DataFrame(rows).to_csv(index=False)
        else:
            # Fallback: just export quotas
            with st.spinner("Fetching quotas..."):
                qs = state.api_client.list_all_quotas()
            csv_data = pd.DataFrame([q.to_dict() for q in qs]).to_csv(index=False)
        
        st.download_button("📥 Download CSV Report", csv_data, "quota_report.csv")
    except Exception as e:
        st.error(f"Export failed: {e}")


def debug_zones_tab():
    st.header("🔍 Zone Debugging")
    st.caption("Use this to diagnose zone discovery issues.")
    api = state.api_client
    
    if st.button("🔄 Run Zone Discovery Debug"):
        with st.spinner("Analyzing zone data..."):
            debug = api.debug_zone_discovery()
            
            st.subheader("Available APIs")
            st.json({
                "zones_api": debug["zones_api_available"],
                "namespaces_api": debug["namespaces_api_available"],
                "protocols_api": debug["protocols_api_available"],
                "quota_api": debug["quota_api_available"],
            })
            
            st.subheader("Zones Info (Final)")
            st.json(debug["zones_info"])
            
            st.subheader("Sample Quotas (First 3)")
            for i, sample in enumerate(debug["sample_quotas"]):
                with st.expander(f"Quota {i+1}: {sample['path']}", expanded=True):
                    st.write(f"**ID:** {sample['id']}")
                    st.write(f"**Path:** {sample['path']}")
                    st.write(f"**zone:** {sample['zone']}")
                    st.write(f"**access_zone:** {sample['access_zone']}")
                    st.write(f"**zone_name:** {sample['zone_name']}")
                    st.write(f"**scope:** {sample['scope']}")
                    st.write(f"**az:** {sample['az']}")
                    st.write("**All attributes:**")
                    st.json(sample["all_attrs"])
            
            st.subheader("Raw API Responses")
            st.json({k: v for k, v in debug.items() if k.startswith("zones_api_") or k.startswith("quota_")})
