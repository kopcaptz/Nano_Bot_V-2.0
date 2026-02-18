"""Tools - Agent tools list."""

import streamlit as st

# Static list from nanobot/agent/loop.py (read_file, write_file, edit_file, list_dir, exec, web_search, web_fetch, memory_search, skill, message, spawn, cron, mcp)
TOOLS_STATIC = [
    {"name": "read_file", "description": "Read file contents from the workspace or allowed directory", "policy": "allow"},
    {"name": "write_file", "description": "Write or overwrite a file", "policy": "allow"},
    {"name": "edit_file", "description": "Edit file with search-and-replace", "policy": "allow"},
    {"name": "list_dir", "description": "List directory contents", "policy": "allow"},
    {"name": "exec", "description": "Execute shell commands", "policy": "deny"},
    {"name": "web_search", "description": "Search the web via Brave Search API", "policy": "allow"},
    {"name": "web_fetch", "description": "Fetch and extract content from a URL", "policy": "allow"},
    {"name": "memory_search", "description": "Semantic search over long-term memory", "policy": "allow"},
    {"name": "create_skill", "description": "Create a new skill from conversation", "policy": "allow"},
    {"name": "message", "description": "Send a message back to the user", "policy": "allow"},
    {"name": "spawn", "description": "Spawn a subagent for delegated tasks", "policy": "allow"},
    {"name": "cron", "description": "Schedule recurring or one-shot tasks", "policy": "allow"},
    {"name": "mcp_call", "description": "Call MCP (Model Context Protocol) tools", "policy": "allow"},
]

st.title("🔧 Tools")

st.caption("Registered agent tools from nanobot")

for t in TOOLS_STATIC:
    with st.expander(f"🔧 {t['name']}", expanded=False):
        st.markdown(t.get("description", "—"))
        st.caption(f"Policy: {t.get('policy', '—')}")
