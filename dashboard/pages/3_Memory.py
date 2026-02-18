"""Memory - Facts, Reflections, Journal."""

import streamlit as st
from datetime import datetime

from dashboard.utils.memory import get_facts, get_facts_categories, get_reflections, get_journal
from dashboard.utils.fake_data import fake_facts, fake_reflections, fake_journal_entries

st.title("🧠 Memory")

tab1, tab2, tab3 = st.tabs(["Facts", "Reflections", "Journal"])

# Facts tab
with tab1:
    st.subheader("Facts")
    search = st.text_input("Search facts (optional)", placeholder="Type to search...")
    categories = get_facts_categories()
    cat_sel = st.selectbox("Category filter", ["All"] + categories) if categories else "All"
    facts = get_facts(category=cat_sel if cat_sel != "All" else None, search_query=search if search else None)
    if not facts:
        facts = fake_facts(5)
        st.caption("Placeholder data (no facts in DB yet)")
    for f in facts[:30]:
        with st.expander(f"{f.get('category', '?')} :: {f.get('key', '?')}", expanded=False):
            st.markdown(f"**Value:** {f.get('value', '')}")
            st.caption(f"Updated: {f.get('updated_at', '')}")

# Reflections tab
with tab2:
    st.subheader("Reflections")
    reflections = get_reflections(limit=20)
    if not reflections:
        reflections = fake_reflections(3)
        st.caption("Placeholder data (no reflections yet)")
    for r in reflections[:15]:
        with st.expander(f"🔧 {r.get('tool_name', '?')}", expanded=False):
            st.markdown(f"**Error:** `{str(r.get('error_text', ''))[:200]}...`" if len(str(r.get('error_text', ''))) > 200 else f"**Error:** `{r.get('error_text', '')}`")
            st.markdown(f"**Insight:** {r.get('insight', '')}")
            st.caption(f"Session: {r.get('session_key', '—')} | {r.get('created_at', '')}")

# Journal tab
with tab3:
    st.subheader("Journal")
    today = datetime.now().strftime("%Y-%m-%d")
    jour_date = st.date_input("Date", value=datetime.now(), max_value=datetime.now())
    date_str = jour_date.strftime("%Y-%m-%d") if hasattr(jour_date, 'strftime') else today
    entries = get_journal(date=date_str)
    if not entries:
        entries = fake_journal_entries(2)
        st.caption("Placeholder data (no journal entries yet)")
    for e in entries:
        st.markdown(f"- {e.get('content', '')}")
        st.caption(e.get('created_at', ''))
