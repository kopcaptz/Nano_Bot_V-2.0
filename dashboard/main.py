"""Nanobot Streamlit Dashboard - Entry point."""

import sys
from pathlib import Path

# Ensure project root is in path for nanobot and dashboard imports
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import streamlit as st

st.set_page_config(
    page_title="Nanobot Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for consistent dark theme and responsive design
st.markdown("""
<style>
    /* Main container */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }
    /* Metric cards */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem;
    }
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e1e2e 0%, #181825 100%);
    }
</style>
""", unsafe_allow_html=True)

# Sidebar branding
with st.sidebar:
    st.markdown("# 🤖 Nanobot")
    st.markdown("---")
    st.caption("AI Assistant Dashboard")
    st.markdown("---")

# Redirect to Dashboard as home content
st.markdown("# Welcome to Nanobot Dashboard")
st.markdown("Navigate to **Dashboard** in the sidebar for real-time metrics and session overview.")
st.info("Use the sidebar to explore: Dashboard, Settings, Memory, Tools, Monitor, Admin.")
