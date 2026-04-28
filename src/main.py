"""Main Streamlit application for SmartQuota Manager."""

import streamlit as st
from streamlit import session_state as state
import pandas as pd

# Import our modules
from src.config import load_clusters, add_cluster, remove_cluster
from src.api import IsilonAPI
from src.audit import write_audit_entry, read_audit_log
from src.utils import (
    filter_quotas, get_top_offenders, paginate_list, 
    status_badge, color_for_status
)
from src.ui.components import (
    render_dynamic_grid, render_snapshot_viewer, render_acl_viewer
)
from src.ui.session import init_session, set_api_client, clear_api_client, handle_api_error

# Set page config
st.set_page_config(page_title="SmartQuota Manager", page_icon="📊", layout="wide")

# Initialize session state
init_session()

# Custom CSS
st.markdown("""
<style>
    :root { --primary-orange: #F58513; --primary-green: #006837; }
    .stApp { font-family: sans-serif; }
    h1, h2, h3 { color: var(--primary-green); }
    .stMetric [data-testid="stMetricValue"] { color: var(--primary-orange) !important; }
</style>
""", unsafe_allow_html=True)


def login_section():
    """Login form sidebar."""
    st.sidebar.header("🔐 Login")
    clusters = load_clusters()
    
    cluster_names = list(clusters.keys())
    selected = st.sidebar.selectbox("Select Cluster", options=cluster_names + ["Custom URL..."], key="selected_cluster")
    
    custom_url = ""
    if selected == "Custom URL...":
        custom_url = st.sidebar.text_input("Isilon URL", placeholder="https://isilon.local:8080")
    
    username = st.sidebar.text_input("Username", key="login_username", placeholder="domain\\user or user")
    password = st.sidebar.text_input("Password", type="password", key="login_password")
    ssl_warning = st.sidebar.checkbox("Ignore SSL Certificate", value=True, key="ssl_setting")
    
    if st.sidebar.button("Login", use_container_width=True):
        if not username or not password:
            st.sidebar.error("Credentials required")
            return
        
        url = custom_url if selected == "Custom URL..." else clusters[selected]
        if not url:
            st.sidebar.error("URL required")
            return

        # Derive clean hostname for display and logging
        display_name = selected
        if selected == "Custom URL...":
            display_name = url.split("//")[-1].split(":")[0].replace(".", "_")
        
        try:
            api = IsilonAPI(cluster_url=url, username=username, password=password, verify_ssl=not ssl_warning)
            set_api_client(api)
            if selected == "Custom URL...":
                add_cluster(display_name, url)
            
            state.selected_cluster = display_name
            state.admin_user = username
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Login failed: {e}")


def logout_section():
    """Logout button and info."""
    if state.api_client:
        st.sidebar.header(f"Connected: {state.selected_cluster}")
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            clear_api_client()
            st.rerun()


def cluster_management():
    """Cluster management sidebar expander."""
    with st.sidebar.expander("⚙️ Cluster Management", expanded=False):
        clusters = load_clusters()
        for name, url in clusters.items():
            col1, col2 = st.columns([3, 1])
            col1.caption(f"{name}")
            if col2.button("🗑️", key=f"del_{name}"):
                remove_cluster(name)
                st.rerun()
        st.divider()
        new_name = st.text_input("New Name")
        new_url = st.text_input("New URL", placeholder="https://...")
        if st.button("Add"):
            if new_name and new_url:
                add_cluster(new_name, new_url)
                st.rerun()


def main_view():
    """Main dashboard content."""
    if not state.api_client:
        st.title("📊 SmartQuota Manager")
        st.info("Please login from the sidebar to manage your PowerScale clusters.")
        return
    
    st.title(f"📊 {state.selected_cluster}")
    tabs = st.tabs(["📈 Monitoring", "🔧 Universal Manager", "➕ Create", "📜 Audit Log", "📥 Export"])
    
    with tabs[0]: monitoring_tab()
    with tabs[1]: modify_tab()
    with tabs[2]: create_tab()
    with tabs[3]: audit_tab()
    with tabs[4]: export_tab()


def monitoring_tab():
    """Dashboard and search."""
    st.header("Quota Monitoring")
    st.info("📖 [Documentation](https://developer.dell.com/apis/4357/versions/9.12.0/docs/Introduction.md)")
    
    api = state.api_client
    if "quotas_loaded" not in st.session_state:
        with st.spinner("Fetching quotas..."):
            try:
                state.quotas = api.list_quotas(limit=500)[0]
                state.quotas_loaded = True
            except Exception as e:
                if not handle_api_error(e): st.error(f"Load failed: {e}")
                return

    # Top Offenders
    cats = get_top_offenders(state.quotas)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"<h4 style='color:#D72638'>🔴 Critical (>95%)</h4>", unsafe_allow_html=True)
        for i in cats["critical"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")
    with col2:
        st.markdown(f"<h4 style='color:#F58513'>🟡 Warning (>80%)</h4>", unsafe_allow_html=True)
        for i in cats["warning"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")
    with col3:
        st.markdown(f"<h4 style='color:#006837'>🟢 Notice (>70%)</h4>", unsafe_allow_html=True)
        for i in cats["notice"][:3]: st.caption(f"{i['share_name']}: {i['usage_percent']}%")

    st.divider()
    
    # Search
    c1, c2 = st.columns(2)
    search = c1.text_input("Search Share Name")
    zone = c2.selectbox("Filter Zone", ["All"] + api.list_access_zones())
    
    filtered = filter_quotas(state.quotas, search, zone)
    
    # List Table
    page = st.number_input("Page", min_value=1, value=1)
    items, total = paginate_list(filtered, page)
    
    if items:
        display_data = []
        for q in items:
            display_data.append({
                "Share": q.path.split("/")[-1],
                "Zone": q.access_zone,
                "Path": q.path,
                "Usage %": f"{q.usage_percent:.1f}%",
                "Status": f"{status_badge(q.status)} {q.status.value.upper()}"
            })
        st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)
        
        # Selection
        selected = st.multiselect("Focus on share for Universal Manager", 
                                  options=[f"{q.path} ({q.usage_percent:.1f}%)" for q in items], 
                                  key="selected_paths")
        state.selected_quota_paths = selected
    else:
        st.info("No matching quotas found.")


def modify_tab():
    """Universal Manager with Dynamic Grid."""
    st.header("Universal Object Manager 🛠️")
    with st.expander("📖 API Resources"):
        st.caption("Links to Dell Portal for Quotas, Snapshots, and ACLs.")
    
    if not state.api_client: return
    if "selected_quota_paths" not in state or not state.selected_quota_paths:
        st.info("Select a quota from Monitoring to begin.")
        return
    
    # Find active quota
    path_str = state.selected_quota_paths[0]
    quota = next((q for q in state.quotas if f"{q.path} ({q.usage_percent:.1f}%)" == path_str), None)
    if not quota: return

    st.subheader(f"📁 {quota.path}")
    t1, t2, t3 = st.tabs(["⚙️ Settings", "📸 Snapshots", "🔒 Permissions"])
    
    api = state.api_client
    with t1:
        try:
            raw = api.quota_api.get_quota_entry(quota.id).to_dict()
            with st.form(f"f_{quota.id}"):
                payload = render_dynamic_grid(raw, f"ed_{quota.id}")
                st.divider()
                if st.form_submit_button("APPLY CHANGES", type="primary"):
                    if payload:
                        api.update_quota_dynamic(quota.id, payload)
                        write_audit_entry(state.admin_user, state.selected_cluster, "DYNAMIC_MODIFY", quota.path.split("/")[-1], quota.path, quota.hard_limit_gb, 0)
                        st.success("Updated!")
                        if "quotas_loaded" in state: del state.quotas_loaded
                        st.rerun()
            
            # Delete
            with st.expander("🗑️ Decommission"):
                if st.text_input("Type DELETE") == "DELETE":
                    if st.button("CONFIRM DELETE"):
                        api.delete_quota(quota.id)
                        write_audit_entry(state.admin_user, state.selected_cluster, "DELETE", quota.path.split("/")[-1], quota.path, 0, 0)
                        st.rerun()
        except Exception as e:
            if not handle_api_error(e): st.error(f"Error: {e}")

    with t2:
        render_snapshot_viewer(api.get_snapshots_for_path(quota.path))
    
    with t3:
        render_acl_viewer(api.get_acl_for_path(quota.path))


def create_tab():
    """Quota Provisioning."""
    st.header("Provision New Quota ➕")
    if not state.api_client: return
    
    with st.form("c_form"):
        path = st.text_input("Path", placeholder="/ifs/...")
        q_type = st.selectbox("Type", ["directory", "user", "group"])
        zone = st.selectbox("Zone", state.api_client.list_access_zones())
        hard = st.number_input("Hard Limit (GB)", min_value=0.0, step=1.0)
        if st.form_submit_button("CREATE"):
            if not path.startswith("/ifs"): st.error("Path error"); return
            try:
                state.api_client.create_quota(path, q_type, hard, zone)
                write_audit_entry(state.admin_user, state.selected_cluster, "CREATE", path.split("/")[-1], path, 0, hard)
                st.success("Created!")
                if "quotas_loaded" in state: del state.quotas_loaded
            except Exception as e:
                if not handle_api_error(e): st.error(f"Error: {e}")


def audit_tab():
    """Audit view."""
    st.header(f"Audit Log: {state.selected_cluster}")
    entries = read_audit_log(cluster=state.selected_cluster)
    if entries:
        st.dataframe(pd.DataFrame(entries), hide_index=True, use_container_width=True)
    else:
        st.info("No entries today.")


def export_tab():
    """Reports."""
    st.header("Bulk Export")
    if st.button("Generate All Quotas CSV"):
        with st.spinner("Processing..."):
            all_q = state.api_client.list_all_quotas()
            mapping = state.api_client.get_protocol_mapping()
            data = []
            for q in all_q:
                d = q.to_dict()
                d["Protocol"] = mapping.get(q.path, "-")
                data.append(d)
            st.download_button("Download CSV", pd.DataFrame(data).to_csv(index=False), "export.csv")


def main():
    """App entry."""
    if state.api_client:
        logout_section()
        cluster_management()
    else:
        login_section()
    main_view()

if __name__ == "__main__":
    main()
