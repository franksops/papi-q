"""Main Streamlit application for SmartQuota Manager."""

import streamlit as st
from streamlit import session_state as state

# Import our modules
from config import load_config, load_clusters, save_clusters, add_cluster, remove_cluster
from api import IsilonAPI, QuotaEntry
from audit import write_audit_entry
from utils import filter_quotas, get_top_offenders, paginate_list
from ui.components import create_modification_form, status_badge, color_for_status
from ui.session import init_session, set_api_client, clear_api_client
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
        options=cluster_names,
        key="selected_cluster",
    )
    
    # Credentials
    username = st.sidebar.text_input("Username", key="login_username")
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
        
        if selected_cluster not in clusters:
            st.sidebar.error("Invalid cluster selected")
            return
        
        cluster_url = clusters[selected_cluster]
        
        try:
            # Create API client
            api = IsilonAPI(
                cluster_url=cluster_url,
                username=username,
                password=password,
                verify_ssl=not ssl_warning,
            )
            set_api_client(api)
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
    
    tabs = st.tabs(["📈 Monitoring", "🔧 Modify", "📜 Audit Log"])
    
    with tabs[0]:
        monitoring_tab()
    
    with tabs[1]:
        modify_tab()
    
    with tabs[2]:
        audit_tab()


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
    """Tab for quota modification."""
    st.header("Modify Quotas")
    
    if not state.api_client:
        st.warning("Login required")
        return
    
    api = state.api_client
    
    # Get selected quotas
    if "selected_quota_paths" not in state:
        st.info("Select quotas from the Monitoring tab to modify them.")
        return
    
    if not state.selected_quota_paths:
        st.info("No quotas selected. Go to Monitoring tab and select some.")
        return
    
    # Map paths back to quota objects
    selected_quotas = []
    for q in state.quotas:
        path_name = f"{q.path} ({q.usage_percent:.1f}%)"
        if path_name in state.selected_quota_paths:
            selected_quotas.append(q)
    
    if not selected_quotas:
        st.info("Could not find selected quotas.")
        return
    
    st.subheader(f"Modifying {len(selected_quotas)} quota(s)")
    
    for quota in selected_quotas:
        st.markdown(f"### {quota.path.split('/')[-1]}")
        st.markdown(f"**Path**: {quota.path}")
        
        result = create_modification_form(quota, key_prefix=f"form_{quota.id}")
        
        if result:
            if st.button("CONFIRM AND MODIFY", key=f"confirm_{quota.id}", type="primary"):
                try:
                    modified = api.update_quota(
                        quota_id=quota.id,
                        hard_limit_gb=result["hard_limit_gb"],
                        soft_limit_gb=result["soft_limit_gb"],
                        apply_to_children=result["apply_to_children"],
                    )
                    
                    # Write audit log
                    admin = state.admin_user or state.login_username or "unknown"
                    write_audit_entry(
                        admin=admin,
                        cluster=state.selected_cluster,
                        action="QUOTA_MODIFY",
                        share_name=quota.path.split("/")[-1],
                        path=quota.path,
                        old_limit_gb=quota.hard_limit_gb,
                        new_limit_gb=modified.hard_limit_gb,
                    )
                    
                    st.success(f"✅ Modified {quota.path}")
                    
                    # Refresh quota data
                    for i, q in enumerate(state.quotas):
                        if q.id == quota.id:
                            state.quotas[i] = modified
                            break
                    
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to modify quota: {e}")


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
    st.sidebar.image("https://logo_clear.png", width=50)  # Placeholder logo
    
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
