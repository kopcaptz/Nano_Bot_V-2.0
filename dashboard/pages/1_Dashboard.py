"""Dashboard - Main page with real-time metrics."""

import streamlit as st
from pathlib import Path

from dashboard.utils.config import load_dashboard_config
from dashboard.utils.sessions import get_sessions_list
from dashboard.utils.memory import get_token_usage_today
from dashboard.utils.navigator import get_navigator_session_metrics
from dashboard.utils.fake_data import fake_sessions, fake_token_usage

st.title("📊 Dashboard")

# Real-time: auto-refresh every 5 seconds
def refresh_block():
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    with col2:
        st.caption("Auto-refreshes every 5 seconds")
    with col3:
        pass

refresh_block()
st.divider()


def _cfg_get(config_obj, keys, default=None):
    """Read nested values from dict or pydantic config object."""
    current = config_obj
    for key in keys:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key)
        else:
            current = getattr(current, key, None)
    return default if current is None else current


# Load real data
sessions = get_sessions_list(limit=20)
token_data = get_token_usage_today()
config = load_dashboard_config()
navigator_data = get_navigator_session_metrics(config=config, limit=2000)

# Use fake data when empty
if not sessions:
    sessions = fake_sessions(5)
    using_fake_sessions = True
else:
    using_fake_sessions = False

if not token_data:
    token_data = fake_token_usage()
    using_fake_tokens = True
else:
    using_fake_tokens = False

# Metrics row
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("Sessions", len(sessions), help="Active conversation sessions")
with m2:
    total = token_data.get("total_tokens", 0)
    st.metric("Tokens Today", f"{total:,}", help="Total tokens used today")
with m3:
    requests = token_data.get("requests", 0)
    st.metric("Requests Today", requests, help="API requests today")
with m4:
    model = _cfg_get(config, ["agents", "defaults", "model"], "—")
    st.metric("Default Model", model[:30] + "…" if len(str(model)) > 30 else model, help="Agent default model")

if using_fake_sessions or using_fake_tokens:
    st.caption("⚠️ Some data is placeholder (no real data yet)")

st.divider()

# Recent sessions
st.subheader("Recent Sessions")
if sessions:
    for s in sessions[:10]:
        key = s.get("key", "unknown")
        updated = s.get("updated_at", "")[:19] if s.get("updated_at") else "—"
        channel = key.split(":")[0] if ":" in key else "gateway"
        with st.expander(f"📎 {key}", expanded=False):
            st.markdown(f"**Channel:** `{channel}` | **Updated:** {updated}")
            if s.get("path"):
                st.caption(s["path"])
else:
    st.info("No sessions yet. Start a conversation to see them here.")

st.divider()

st.subheader("Navigator Pilot Metrics")
if navigator_data.get("events", 0) > 0:
    n1, n2, n3 = st.columns(3)
    with n1:
        st.metric("Navigator Events", navigator_data.get("events", 0))
    with n2:
        st.metric("Tokens Saved (est.)", f"{navigator_data.get('tokens_saved_est', 0):,}")
    with n3:
        st.metric("Avg Navigator Latency (ms)", navigator_data.get("avg_latency", 0.0))

    route_mix = navigator_data.get("route_mix", {})
    if route_mix:
        st.caption("Route Mix (%)")
        for route, pct in sorted(route_mix.items()):
            st.markdown(f"- **{route}**: {pct}%")
    st.caption(f"Log source: `{navigator_data.get('log_path', '')}`")
else:
    st.info("No navigator pilot events yet. Check logs/navigator_pilot.jsonl after enabling hybrid mode.")

# Auto-refresh (Streamlit 1.33+)
try:
    from datetime import timedelta
    @st.fragment(run_every=timedelta(seconds=5))
    def auto_refresh_indicator():
        st.caption("↻ Last updated: " + __import__("datetime").datetime.now().strftime("%H:%M:%S"))
except (ImportError, AttributeError):
    pass
