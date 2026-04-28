"""Session state management for SmartQuota Manager."""

import streamlit as st
from typing import Optional, Any


def init_session() -> None:
    """Initialize essential session state variables."""
    defaults = {
        "api_client": None,
        "selected_cluster": None,
        "admin_user": None,
        "quotas": [],
        "quotas_loaded": False,
        "selected_quota_paths": []
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def set_api_client(client: Any) -> None:
    st.session_state.api_client = client


def clear_api_client() -> None:
    st.session_state.api_client = None
    st.session_state.selected_cluster = None
    st.session_state.admin_user = None
    st.session_state.quotas = []
    st.session_state.quotas_loaded = False
    st.session_state.selected_quota_paths = []


def handle_api_error(error: Exception) -> bool:
    """Handle 401 errors and auto-logout."""
    err = str(error).lower()
    if any(x in err for x in ["401", "unauthorized", "invalid credentials"]):
        clear_api_client()
        st.error("🔒 Session expired. Please login again.")
        st.rerun()
        return True
    return False
