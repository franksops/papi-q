"""Session state management for SmartQuota Manager."""

import streamlit as st
from typing import Optional, Dict, Any


def init_session() -> None:
    """Initialize session state variables."""
    if "api_client" not in st.session_state:
        st.session_state.api_client = None
    
    if "_clusters" not in st.session_state:
        st.session_state.clusters = {}
    
    if "current_cluster" not in st.session_state:
        st.session_state.current_cluster = None
    
    if "last_quota_list" not in st.session_state:
        st.session_state.last_quota_list = []
    
    if "selected_quotas" not in st.session_state:
        st.session_state.selected_quotas = []
    
    if "quota_cache" not in st.session_state:
        st.session_state.quota_cache = {}
    
    if "audit_log" not in st.session_state:
        st.session_state.audit_log = []
    
    if "admin_user" not in st.session_state:
        st.session_state.admin_user = None
    
    if "clusters_modified" not in st.session_state:
        st.session_state.clusters_modified = False


def get_api_client() -> Optional[Any]:
    """Get the current API client from session state."""
    return st.session_state.api_client


def set_api_client(client: Any) -> None:
    """Set the API client in session state."""
    st.session_state.api_client = client


def clear_api_client() -> None:
    """Clear the API client (logout)."""
    st.session_state.api_client = None
    st.session_state.current_cluster = None
    st.session_state.admin_user = None
    st.session_state.last_quota_list = []
    st.session_state.selected_quotas = []


def handle_api_error(error: Exception) -> bool:
    """
    Handle API errors, specifically 401 Unauthorized.
    Returns True if session was cleared.
    """
    error_str = str(error).lower()
    if "401" in error_str or "unauthorized" in error_str or "invalid credentials" in error_str:
        clear_api_client()
        st.error("🔒 Session expired or unauthorized. Please login again.")
        st.rerun()
        return True
    return False


def get_selected_quotas() -> list:
    """Get currently selected quotas."""
    return st.session_state.selected_quotas


def set_selected_quotas(quotas: list) -> None:
    """Set selected quotas."""
    st.session_state.selected_quotas = quotas


def get_cluster_name() -> Optional[str]:
    """Get current cluster name from URL."""
    if st.session_state.current_cluster:
        return st.session_state.current_cluster.split("://")[-1]
    return None
