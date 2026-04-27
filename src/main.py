"""Main Streamlit application for SmartQuota Manager."""

import streamlit as st
from streamlit import session_state as state

# Import our modules (using relative imports for package structure)
from src.config import load_config, load_clusters, save_clusters, add_cluster, remove_cluster
from src.api import IsilonAPI, QuotaEntry, Status
from src.audit import write_audit_entry
from src.utils import filter_quotas, get_top_offenders, paginate_list
from src.ui.components import (
    create_modification_form, 
    status_badge, 
    color_for_status,
    render_dynamic_grid,
    render_snapshot_viewer,
    render_acl_viewer
)
from src.ui.session import init_session, set_api_client, clear_api_client, handle_api_error
import pandas as pd

# Set page config with custom title and icon
st.set_page_config(
    page_title="SmartQuota Manager",
    page_icon="📊",
    layout="wide",
)

# Initialize session state
init_session()


# Custom CSS for orange/green theme
st.markdown("""
<style>
    :root {
        --primary-orange: #F58513;
        --primary-green: #006837;
        --primary-orange-light: #FFA54D;
        --primary-green-light: #339966;
    }
    
    .stApp {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    
    .stAlert {
        border-radius: 0.5rem;
        border-left: 4px solid var(--primary-orange);
    }
    
    .stAlert.warning {
        border-left-color: var(--primary-orange);
    }
    
    .stAlert.success {
        border-left-color: var(--primary-green);
    }
    
    .status-badge {
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-weight: bold;
        color: white;
    }
    
    .status-critical { background-color: #D72638; }
    .status-warning { background-color: #F58513; }
    .status-healthy { background-color: #006837; }
    
    .quota-section {
        background-color: #f8f9fa;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    
    h1, h2, h3 {
        color: var(--primary-green);
    }
    
    .stMetric [data-testid="stMetricValue"] {
        color: var(--primary-orange) !important;
    }
    
    .stMetric [data-testid="stMetricLabel"] {
        color: #666;
    }
</style>
""", unsafe_allow_html=True)


def login_section():
    """Login form - only show if no client is active."""
    st.sidebar.header("🔐 Login")
    
    clusters = load_clusters()
    if not clusters:
        st.sidebar.warning("No clusters configured. Add one to continue.")
        return
    
    # Cluster selector
    cluster_names = list(clusters.keys())
    selected_cluster = st.sidebar.selectbox(
        "Select Cluster",
        options=cluster_names + ["Custom URL..."],
        key="selected_cluster",
    )
    
    custom_url = ""
    if selected_cluster == "Custom URL...":
        custom_url = st.sidebar.text_input("Isilon URL", placeholder="https://isilon.local:8080")
    
    # Credentials
    username = st.sidebar.text_input("Username", key="login_username", placeholder="domain\\user or user")
    password = st.sidebar.text_input("Password", type="password", key="login_password")
    
    # SSL setting
    ssl_warning = st.sidebar.checkbox(
        "Ignore SSL Certificate",
        value=True,
        key="ssl_setting",
    )
    
    # Login button
    if st.sidebar.button("Login", use_container_width=True):
        if not username or not password:
            st.sidebar.error("Username and password are required")
            return
        
        cluster_url = ""
        cluster_display_name = ""
        
        if selected_cluster == "Custom URL...":
            if not custom_url:
                st.sidebar.error("Please enter a custom URL")
                return
            cluster_url = custom_url
            cluster_display_name = custom_url.split("//")[-1].split(":")[0]
        else:
            cluster_url = clusters[selected_cluster]
            cluster_display_name = selected_cluster
        
        try:
            # Create API client
            api = IsilonAPI(
                cluster_url=cluster_url,
                username=username,
                password=password,
                verify_ssl=not ssl_warning,
            )
            set_api_client(api)
            
            # Store additional session state
            state.selected_cluster = cluster_display_name
            state.admin_user = username
            
            st.success(f"✅ Connected to {selected_cluster}")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Connection failed: {e}")


def logout_button():
    """Logout button - only show if client is active."""
    if state.api_client:
        st.sidebar.header(f"Connected: {state.selected_cluster}")
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            clear_api_client()
            st.rerun()
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            clear_api_client()
            st.rerun()


def cluster_management():
    """Cluster management panel."""
    with st.sidebar.expander("⚙️ Cluster Management", expanded=False):
        st.subheader("Clusters")
        
        clusters = load_clusters()
        for name, url in clusters.items():
            col1, col2 = st.columns([3, 1])
            col1.text(f"• {name}: {url}")
            if col2.button("🗑️", key=f"del_{name}"):
                remove_cluster(name)
                st.rerun()
        
        st.divider()
        
        st.subheader("Add New Cluster")
        new_name = st.text_input("Name", key="new_cluster_name")
        new_url = st.text_input("URL", placeholder="https://cluster.fqdn.local:8080", key="new_cluster_url")
        
        if st.button("Add Cluster"):
            if new_name and new_url:
                add_cluster(new_name, new_url)
                st.success(f"Added: {new_name}")
                st.rerun()
            else:
                st.error("Name and URL required")


def main_view():
    """Main content area."""
    if not state.api_client:
        st.title("📊 SmartQuota Manager")
        st.markdown("Welcome! Please login to manage your PowerScale clusters.")
        st.markdown("---")
        st.header("Quick Start")
        st.info("""
        1. **Login** using the sidebar
        2. **View** top offenders on the current cluster
        3. **Search** by share name or access zone
        4. **Modify** quotas and monitor usage
        """)
        return
    
    st.title(f"📊 SmartQuota Manager - {state.selected_cluster}")
    
    tabs = st.tabs(["📈 Monitoring", "🔧 Modify", "➕ Create", "📜 Audit Log", "📥 Export"])
    
    with tabs[0]:
        monitoring_tab()
    
    with tabs[1]:
        modify_tab()
        
    with tabs[2]:
        create_tab()
    
    with tabs[3]:
        audit_tab()
        
    with tabs[4]:
        export_tab()


def create_tab():
    """Tab for creating new quotas."""
    st.header("Provision New Quota ➕")
    
    if not state.api_client:
        st.warning("Login required")
        return
        
    api = state.api_client
    
    with st.form("create_quota_form"):
        path = st.text_input("Filesystem Path", placeholder="/ifs/data/...")
        
        col1, col2 = st.columns(2)
        with col1:
            q_type = st.selectbox("Quota Type", ["directory", "user", "group", "default-user", "default-group"])
            access_zone = st.selectbox("Access Zone", api.list_access_zones())
        
        with col2:
            hard_limit = st.number_input("Hard Limit (GB)", min_value=0.0, step=1.0)
            soft_limit = st.number_input("Soft Limit (GB)", min_value=0.0, step=1.0)

        enforced = st.checkbox("Enforced", value=True)
        include_snapshots = st.checkbox("Include Snapshots in Usage", value=False)
        
        submit = st.form_submit_button("CREATE QUOTA", type="primary", use_container_width=True)
        
    if submit:
        if not path.startswith("/ifs"):
            st.error("Path must start with /ifs")
            return
            
        try:
            with st.spinner(f"Creating quota on {path}..."):
                new_id = api.create_quota(
                    path=path,
                    type=q_type,
                    hard_limit_gb=hard_limit,
                    soft_limit_gb=soft_limit,
                    access_zone=access_zone,
                    enforced=enforced,
                    include_snapshots=include_snapshots
                )
                
                # Audit log
                write_audit_entry(
                    admin=state.admin_user or "unknown",
                    cluster=state.selected_cluster,
                    action="QUOTA_CREATE",
                    share_name=path.split("/")[-1],
                    path=path,
                    old_limit_gb=0,
                    new_limit_gb=hard_limit
                )
                
                st.success(f"✅ Quota created successfully! ID: {new_id}")
                # Reset cache
                if "quotas_loaded" in state:
                    del state.quotas_loaded
        except Exception as e:
            if not handle_api_error(e):
                st.error(f"Failed to create quota: {e}")


def export_tab():
    """Tab for bulk exporting quotas."""
    st.header("Bulk Export 📥")
    
    if not state.api_client:
        st.warning("Login required")
        return
        
    api = state.api_client
    
    st.markdown("Download full quota reports for the current cluster.")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Export Options")
        export_type = st.radio(
            "Select Export Scope",
            ["All Quotas", "By Access Zone", "By Protocol"],
            key="export_scope_radio"
        )
        
        selected_zone = "All"
        if export_type == "By Access Zone":
            zones = api.list_access_zones()
            selected_zone = st.selectbox("Select Zone", zones)
            
        selected_protocol = "All"
        if export_type == "By Protocol":
            selected_protocol = st.selectbox("Select Protocol", ["SMB", "NFS"])

    with col2:
        st.subheader("Generate Report")
        if st.button("Generate & Download CSV", use_container_width=True):
            with st.spinner("Fetching all quotas (this may take a minute)..."):
                try:
                    # Fetch all quotas (paginated)
                    all_quotas = api.list_all_quotas()
                    
                    # Fetch protocol mapping
                    mapping = api.get_protocol_mapping()
                    
                    # Convert to list of dicts with protocol info
                    export_data = []
                    for q in all_quotas:
                        d = q.to_dict()
                        # Add protocol
                        d["Protocol"] = mapping.get(q.path, "-")
                        export_data.append(d)
                    
                    df = pd.DataFrame(export_data)
                    
                    # Apply filters if needed
                    if export_type == "By Access Zone":
                        df = df[df["access_zone"] == selected_zone]
                    elif export_type == "By Protocol":
                        df = df[df["Protocol"].str.contains(selected_protocol, na=False)]
                        
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="Click here to download",
                        data=csv,
                        file_name=f"quota_export_{export_type.lower().replace(' ', '_')}_{state.selected_cluster}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                    st.success(f"Report generated with {len(df)} entries.")
                except Exception as e:
                    st.error(f"Failed to generate report: {e}")


def monitoring_tab():
    """Tab for quota monitoring and viewing."""
    st.header("Quota Monitoring")
    
    api = state.api_client
    
    # Load quotas
    if "quotas_loaded" not in st.session_state:
        with st.spinner("Loading quotas..."):
            try:
                quotas, _ = api.list_quotas(limit=500)
                state.quotas = quotas
                state.quotas_loaded = True
                st.session_state.last_quota_list = quotas
            except Exception as e:
                if not handle_api_error(e):
                    st.error(f"Failed to load quotas: {e}")
                return
    
    # Top offenders cards
    st.subheader("⚠️ Top Offenders")
    categories = get_top_offenders(state.quotas)
    
    if any(categories.values()):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"<h3 style='color:#D72638'>🔴 Critical (>90%)</h3>", unsafe_allow_html=True)
            for item in categories["critical"][:5]:
                st.warning(f"{item['share_name']}: {item['usage_percent']:.1f}%")
        
        with col2:
            st.markdown(f"<h3 style='color:#F58513'>🟡 Warning (80-90%)</h3>", unsafe_allow_html=True)
            for item in categories["warning"][:5]:
                st.warning(f"{item['share_name']}: {item['usage_percent']:.1f}%")
        
        with col3:
            st.markdown(f"<h3 style='color:#006837'>🟢 Notice (70-80%)</h3>", unsafe_allow_html=True)
            for item in categories["notice"][:5]:
                st.info(f"{item['share_name']}: {item['usage_percent']:.1f}%")
    else:
        st.success("All quotas healthy!")
    
    st.divider()
    
    # Search and filter
    st.subheader("🔍 Search Quotas")
    
    col1, col2 = st.columns(2)
    with col1:
        search_term = st.text_input("Share Name (partial match)", key="search_share")
    with col2:
        zones = api.list_access_zones()
        access_zone = st.selectbox("Access Zone", ["All"] + zones, key="search_zone")
    
    # Filter quotas
    filtered = filter_quotas(
        state.quotas,
        share_name=search_term if search_term else None,
        access_zone=access_zone if access_zone != "All" else None,
    )
    
    # Export section
    st.divider()
    col_exp1, col_exp2 = st.columns([4, 1])
    with col_exp2:
        if filtered:
            # Prepare export data
            export_df = pd.DataFrame([q.to_dict() for q in filtered])
            csv = export_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Export to CSV",
                data=csv,
                file_name=f"quotas_{state.selected_cluster}.csv",
                mime="text/csv",
                use_container_width=True,
            )

    # Paginate
    page = st.number_input("Page", min_value=1, value=1, key="quota_page")
    page_size = 25
    paginated, total_pages = paginate_list(filtered, page, page_size)
    
    if paginated:
        # Create table
        data = []
        for q in paginated:
            status = status_badge(q.status) + " " + q.status.value.upper()
            data.append({
                "Share Name": q.path.split("/")[-1],
                "Access Zone": q.access_zone,
                "Path": q.path,
                "Hard Limit (GB)": f"{q.hard_limit_gb:.2f}",
                "Soft Limit (GB)": f"{q.soft_limit_gb:.2f}",
                "Usage (GB)": f"{q.usage_gb:.2f}",
                "Usage %": f"{q.usage_percent:.1f}",
                "Status": status,
            })
        
        df = pd.DataFrame(data)
        st.dataframe(df, hide_index=True, use_container_width=True)
        
        # Selection
        selected = st.multiselect(
            "Select quotas to modify",
            options=[f"{q.path} ({q.usage_percent:.1f}%)" for q in paginated],
            key="selected_quota_paths",
        )
        state.selected_quota_paths = selected
    else:
        st.info("No quotas found matching your criteria.")


def modify_tab():
    """Tab for universal quota and path modification."""
    st.header("Universal Object Manager 🛠️")
    
    if not state.api_client:
        st.warning("Login required")
        return
    
    api = state.api_client
    
    # Get selected quotas
    if "selected_quota_paths" not in state or not state.selected_quota_paths:
        st.info("Select a quota from the Monitoring tab to manage it.")
        return
    
    # For simplicity in Universal view, we manage one object at a time if multiple selected
    selected_path_str = state.selected_quota_paths[0]
    
    # Find the quota object
    quota = None
    for q in state.quotas:
        if f"{q.path} ({q.usage_percent:.1f}%)" == selected_path_str:
            quota = q
            break
            
    if not quota:
        st.error("Selected quota not found in session.")
        return

    st.title(f"📁 {quota.path.split('/')[-1]}")
    st.caption(f"Full Path: {quota.path}")

    # Tabs for different aspects of the filesystem object
    obj_tabs = st.tabs(["⚙️ Quota Settings", "📸 Snapshots", "🔒 Permissions (ACL)"])

    with obj_tabs[0]:
        try:
            # Fetch raw data for dynamic grid
            raw_quota = api.get_raw_quota(quota.id)
            
            # Render Dynamic Grid
            with st.form(key=f"universal_form_{quota.id}"):
                modified_payload = render_dynamic_grid(raw_quota, key_prefix=f"univ_{quota.id}")
                
                st.divider()
                st.warning("⚠️ Changes here affect production. Verify all fields.")
                confirm = st.checkbox("I confirm these changes", key=f"conf_{quota.id}")
                submit = st.form_submit_button("APPLY CHANGES", type="primary", use_container_width=True)
                
            if submit and confirm:
                if not modified_payload:
                    st.info("No changes detected.")
                else:
                    with st.spinner("Applying changes..."):
                        updated_raw = api.update_quota_dynamic(quota.id, modified_payload)
                        
                        # Write audit log
                        admin = state.admin_user or "unknown"
                        write_audit_entry(
                            admin=admin,
                            cluster=state.selected_cluster,
                            action="QUOTA_DYNAMIC_MODIFY",
                            share_name=quota.path.split("/")[-1],
                            path=quota.path,
                            old_limit_gb=quota.hard_limit_gb,
                            new_limit_gb=updated_raw.get("limits", {}).get("hard", 0) / (1024**3),
                        )
                        
                        st.success("✅ Successfully updated quota!")
                        # Clear cache to force reload
                        if "quotas_loaded" in state:
                            del state.quotas_loaded
                        st.rerun()
        except Exception as e:
            if not handle_api_error(e):
                st.error(f"Error loading quota details: {e}")

    # Add Delete capability at the bottom of Quota Settings tab
    with obj_tabs[0]:
        st.divider()
        with st.expander("🗑️ Decommission Quota", expanded=False):
            st.error("DANGER: This action will permanently delete the quota entry.")
            delete_confirm = st.text_input("Type 'DELETE' to confirm", key=f"del_confirm_{quota.id}")
            if st.button("DELETE QUOTA PERMANENTLY", type="primary", key=f"del_btn_{quota.id}", use_container_width=True):
                if delete_confirm == "DELETE":
                    try:
                        api.delete_quota(quota.id)
                        write_audit_entry(
                            admin=state.admin_user or "unknown",
                            cluster=state.selected_cluster,
                            action="QUOTA_DELETE",
                            share_name=quota.path.split("/")[-1],
                            path=quota.path,
                            old_limit_gb=quota.hard_limit_gb,
                            new_limit_gb=0
                        )
                        st.success("✅ Quota deleted.")
                        if "quotas_loaded" in state:
                            del state.quotas_loaded
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to delete: {e}")
                else:
                    st.warning("Please type 'DELETE' to confirm.")

    with obj_tabs[1]:
        try:
            with st.spinner("Fetching snapshots..."):
                snapshots = api.get_snapshots_for_path(quota.path)
                render_snapshot_viewer(snapshots)
        except Exception as e:
            st.error(f"Error fetching snapshots: {e}")

    with obj_tabs[2]:
        try:
            with st.spinner("Fetching ACLs..."):
                acl = api.get_acl_for_path(quota.path, access_zone=quota.access_zone)
                render_acl_viewer(acl)
        except Exception as e:
            st.error(f"Error fetching ACLs: {e}")


def audit_tab():
    """Tab for viewing audit log."""
    st.header("Audit Log 📜")
    
    if not state.api_client:
        st.warning("Login required")
        return
    
    # Display recent audit entries
    try:
        from audit import read_audit_log
        log_file = load_config().get("log_file", "~/.papi-q/audit.csv")
        
        entries = read_audit_log()
        
        if not entries:
            st.info("No audit entries found.")
            return
        
        # Show most recent 50
        recent = entries[-50:]
        
        df = pd.DataFrame(recent)
        st.dataframe(df, hide_index=True, use_container_width=True)
        
        if st.button("Export Full Audit"):
            csv = df.to_csv(index=False)
            st.download_button(
                "Download CSV",
                csv,
                f"audit_log_{state.selected_cluster}.csv",
                "text/csv",
            )
            
    except Exception as e:
        st.error(f"Failed to read audit log: {e}")


# Main layout
def main():
    """Main layout function."""
    # Load logo placeholder (will be replaced with actual logo if available)
    logo_path = "https://logo_clear.png"
    st.sidebar.image(logo_path, width=50)  # Placeholder logo
    
    # Sidebar content
    if state.api_client:
        logout_button()
        cluster_management()
    else:
        login_section()
    
    # Main content
    main_view()


if __name__ == "__main__":
    main()
