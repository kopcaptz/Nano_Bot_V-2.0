"""Monitor - Token usage and stats."""

import streamlit as st

from dashboard.utils.memory import get_token_usage_today, get_token_usage_period_days
from dashboard.utils.fake_data import fake_token_usage, fake_token_usage_period

st.title("📈 Monitor")

# Today
token_today = get_token_usage_today()
if not token_today:
    token_today = fake_token_usage()
    st.caption("Placeholder data (no token usage recorded yet)")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Total Tokens Today", f"{token_today.get('total_tokens', 0):,}")
with c2:
    st.metric("Prompt Tokens", f"{token_today.get('prompt_tokens', 0):,}")
with c3:
    st.metric("Completion Tokens", f"{token_today.get('completion_tokens', 0):,}")
with c4:
    st.metric("Requests", token_today.get("requests", 0))

st.divider()

# By model
st.subheader("By Model (Today)")
by_model = token_today.get("by_model", [])
if by_model:
    for m in by_model:
        st.markdown(f"- **{m.get('model', '?')}**: {m.get('total_tokens', 0):,} tokens ({m.get('requests', 0)} requests)")
else:
    st.info("No per-model data")

st.divider()

# Period chart
st.subheader("Token Usage (Last 7 Days)")
period_data = get_token_usage_period_days(7)
if not period_data:
    period_data = fake_token_usage_period(7)
    st.caption("Placeholder data")

if period_data:
    import pandas as pd
    df = pd.DataFrame(period_data)
    if "total_tokens" in df.columns:
        st.line_chart(df.set_index("date")[["total_tokens"]])
    else:
        st.dataframe(df, use_container_width=True)
else:
    st.info("No period data")
