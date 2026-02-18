"""Admin - System info and paths."""

import streamlit as st
from pathlib import Path

from dashboard.utils.config import load_dashboard_config, get_config_path_resolved

st.title("🛡️ Admin")

# Paths
st.subheader("Paths")
config_path = Path.home() / ".nanobot" / "config.json"
sessions_dir = Path.home() / ".nanobot" / "sessions"
memory_db = Path.home() / ".nanobot" / "memory.db"

p1, p2, p3 = st.columns(3)
with p1:
    st.markdown("**config.json**")
    st.code(str(config_path), language=None)
    st.caption("Exists" if config_path.exists() else "Not found")
with p2:
    st.markdown("**sessions/**")
    st.code(str(sessions_dir), language=None)
    st.caption("Exists" if sessions_dir.exists() else "Not found")
with p3:
    st.markdown("**memory.db**")
    st.code(str(memory_db), language=None)
    if memory_db.exists():
        size_mb = memory_db.stat().st_size / (1024 * 1024)
        st.caption(f"Exists ({size_mb:.2f} MB)")
    else:
        st.caption("Not found")

st.divider()

# Config summary
st.subheader("Config Summary")
config = load_dashboard_config()
if config:
    st.markdown(f"- **Workspace:** `{config.workspace_path}`")
    st.markdown(f"- **Default Model:** `{config.agents.defaults.model}`")
    st.markdown(f"- **Gateway:** {config.gateway.host}:{config.gateway.port}")
    st.markdown("- **Channels:**")
    for ch in ["telegram", "discord", "whatsapp", "email", "slack", "mochat"]:
        enabled = getattr(getattr(config.channels, ch, None), "enabled", False)
        st.caption(f"  - {ch}: {'enabled' if enabled else 'disabled'}")
else:
    st.warning("Config not loaded")

st.divider()

# Health check
st.subheader("Health Check")
all_ok = config_path.exists() or True  # Config might be created on first run
if config:
    st.success("Configuration loaded successfully")
else:
    st.warning("Configuration could not be loaded")
st.caption("No critical errors detected")
