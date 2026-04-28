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
from src.logger import log_info, log_error, log_warning
from src.utils import filter_quotas, get_top_offenders, paginate_list, status_badge, color_for_status, bytes_to_gb
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
    
    url_input = st.sidebar.text_input("IP or Hostname", placeholder="10.1.1.50") if selected == "Custom URL..." else inv.get(selected, "")
    user = st.sidebar.text_input("Username", placeholder="user, domain\\user, or user@domain")
    pwd = st.sidebar.text_input("Password", type="password")
    skip_ssl = st.sidebar.checkbox("Ignore SSL", value=True)
    
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
    
    c1, c2 = st.sidebar.columns(2)
    if c1.button("🚪 Logout", use_container_width=True):
        clear_api_client()
        st.rerun()
    
    if c2.button("🛑 Shutdown", use_container_width=True, type="primary"):
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

    with st.sidebar.expander("⚙️ Inventory"):
        inv = load_clusters()
        for n, u in inv.items():
            c1, c2 = st.columns([4, 1])
            c1.caption(f"{n}")
            if c2.button("🗑️", key=f"d_{n}"):
                remove_cluster(n)
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


def dashboard():
    tabs = st.tabs(["📈 Dashboard", "🔧 Universal Manager", "➕ Provision", "📜 Audit History", "📥 Export"])
    
    with tabs[0]: monitoring_tab()
    with tabs[1]: modify_tab()
    with tabs[2]: provision_tab()
    with tabs[3]: audit_tab()
    with tabs[4]: export_tab()


def monitoring_tab():
    st.header("Cluster Overview")
    api = state.api_client
    if not state.quotas_loaded:
        with st.spinner("Loading..."):
            try:
                state.quotas = api.list_quotas(limit=500)[0]
                state.quotas_loaded = True
            except Exception as e:
                if not handle_api_error(e): st.error(e)
                return

    off = get_top_offenders(state.quotas)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("<h4 style='color:#D72638'>🔴 Critical</h4>", unsafe_allow_html=True)
        for i in off["critical"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")
    with c2:
        st.markdown("<h4 style='color:#F58513'>🟡 Warning</h4>", unsafe_allow_html=True)
        for i in off["warning"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")
    with c3:
        st.markdown("<h4 style='color:#006837'>🟢 Notice</h4>", unsafe_allow_html=True)
        for i in off["notice"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")

    st.divider()
    sc, zc = st.columns(2)
    search = sc.text_input("Search Name")
    zone = zc.selectbox("Zone", ["All"] + api.list_access_zones())
    
    filt = filter_quotas(state.quotas, search, zone)
    page = st.number_input("Page", min_value=1, value=1)
    items, total = paginate_list(filt, page)
    
    if items:
        df = pd.DataFrame([{
            "Share": q.path.split("/")[-1], "Zone": q.access_zone, "Path": q.path,
            "Usage %": f"{q.usage_percent:.1f}%", "Status": f"{status_badge(q.status)} {q.status.value.upper()}"
        } for q in items])
        st.dataframe(df, use_container_width=True, hide_index=True)
        state.selected_quota_paths = st.multiselect("Select share to manage", 
                                                    options=[f"{q.path} ({q.usage_percent:.1f}%)" for q in items],
                                                    max_selections=1)
    else: st.info("No records.")


def modify_tab():
    st.header("Universal Manager 🛠️")
    if not state.selected_quota_paths:
        st.info("Select a quota from the Dashboard.")
        return
    
    path_key = state.selected_quota_paths[0]
    quota = next((q for q in state.quotas if f"{q.path} ({q.usage_percent:.1f}%)" == path_key), None)
    if not quota: return

    api = state.api_client
    st.subheader(f"📁 {quota.path}")
    t1, t2, t3 = st.tabs(["⚙️ Quota Settings", "📸 Snapshots", "🔒 Permissions"])
    
    with t1:
        try:
            raw = api.get_raw_quota(quota.id)
            with st.form(f"u_{quota.id}"):
                payload = render_dynamic_grid(raw, f"e_{quota.id}")
                st.divider()
                if st.form_submit_button("APPLY PRODUCTION CHANGES", type="primary"):
                    if payload:
                        updated = api.update_quota_dynamic(quota.id, payload)
                        keys = ", ".join(payload.keys())
                        new_h = bytes_to_gb(updated.get("limits", {}).get("hard", 0)) if "limits" in payload else quota.hard_limit_gb
                        write_audit_entry(state.admin_user, state.selected_cluster, f"UPDATE ({keys})", quota.path.split("/")[-1], quota.path, quota.hard_limit_gb, new_h)
                        st.success("Updated successfully.")
                        state.quotas_loaded = False
                        st.rerun()
            
            with st.expander("🗑️ Danger Zone"):
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
        
        if st.form_submit_button("CREATE QUOTA", type="primary"):
            if not path.startswith("/ifs"): st.error("Invalid path"); return
            try:
                api.create_quota(path, q_type, {"hard": h, "soft": s, "advisory": a}, zone, enforced, snapshots)
                write_audit_entry(state.admin_user, state.selected_cluster, "CREATE", path.split("/")[-1], path, 0, h)
                st.success(f"Quota created on {path}")
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
    if st.button("Generate Full CSV Report"):
        with st.spinner("Processing large dataset..."):
            try:
                qs = state.api_client.list_all_quotas()
                mapping = state.api_client.get_protocol_mapping()
                data = [ {**q.to_dict(), "Protocol": mapping.get(q.path, "-")} for q in qs ]
                st.download_button("Download Report", pd.DataFrame(data).to_csv(index=False), "quota_report.csv")
            except Exception as e: st.error(e)
