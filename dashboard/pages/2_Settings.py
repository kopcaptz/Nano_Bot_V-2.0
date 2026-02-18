"""Settings - Edit config.json."""

import streamlit as st

from dashboard.utils.config import load_dashboard_config, save_dashboard_config

st.title("⚙️ Settings")

config = load_dashboard_config()
if not config:
    st.error("Nanobot config not available. Install nanobot and ensure ~/.nanobot/config.json exists.")
    st.stop()

# Agent defaults
st.subheader("Agent Defaults")
c1, c2 = st.columns(2)
with c1:
    new_model = st.text_input(
        "Default Model",
        value=config.get("agents", {}).get("defaults", {}).get("model", "anthropic/claude-opus-4-5"),
        help="LLM model identifier (e.g. anthropic/claude-opus-4-5)",
    )
with c2:
    new_workspace = st.text_input(
        "Workspace",
        value=config.get("agents", {}).get("defaults", {}).get("workspace", "~/.nanobot/workspace"),
        help="Workspace directory path",
    )

c3, c4 = st.columns(2)
with c3:
    new_max_tokens = st.number_input("Max Tokens", value=config.get("agents", {}).get("defaults", {}).get("max_tokens", 4000), min_value=256, max_value=128000)
with c4:
    new_temperature = st.slider("Temperature", 0.0, 2.0, float(config.get("agents", {}).get("defaults", {}).get("temperature", 0.7)), 0.1)

st.divider()

# Gateway
st.subheader("Gateway")
g1, g2 = st.columns(2)
with g1:
    new_host = st.text_input("Host", value=config.get("gateway", {}).get("host", "0.0.0.0"))
with g2:
    new_port = st.number_input("Port", value=config.get("gateway", {}).get("port", 18790), min_value=1, max_value=65535)

st.divider()

# Channels (enabled only, no tokens)
st.subheader("Channels (enabled)")
ch1, ch2, ch3 = st.columns(3)
with ch1:
    tg_enabled = st.checkbox("Telegram", value=config.get("channels", {}).get("telegram", {}).get("enabled", False))
    dc_enabled = st.checkbox("Discord", value=config.get("channels", {}).get("discord", {}).get("enabled", False))
with ch2:
    wa_enabled = st.checkbox("WhatsApp", value=config.get("channels", {}).get("whatsapp", {}).get("enabled", False))
    email_enabled = st.checkbox("Email", value=config.get("channels", {}).get("email", {}).get("enabled", False))
with ch3:
    slack_enabled = st.checkbox("Slack", value=config.get("channels", {}).get("slack", {}).get("enabled", False))
    mochat_enabled = st.checkbox("Mochat", value=config.get("channels", {}).get("mochat", {}).get("enabled", False))

st.divider()

# Save
if st.button("💾 Save Configuration"):
    try:
        # Update config safely
        if "agents" not in config:
            config["agents"] = {"defaults": {}}
        if "defaults" not in config["agents"]:
            config["agents"]["defaults"] = {}
        
        config["agents"]["defaults"]["model"] = new_model
        config["agents"]["defaults"]["workspace"] = new_workspace
        config["agents"]["defaults"]["max_tokens"] = new_max_tokens
        config["agents"]["defaults"]["temperature"] = new_temperature
        
        if "gateway" not in config:
            config["gateway"] = {}
        config["gateway"]["host"] = new_host
        config["gateway"]["port"] = new_port
        
        if "channels" not in config:
            config["channels"] = {}
        for channel, enabled in [
            ("telegram", tg_enabled), ("discord", dc_enabled), ("whatsapp", wa_enabled),
            ("email", email_enabled), ("slack", slack_enabled), ("mochat", mochat_enabled)
        ]:
            if channel not in config["channels"]:
                config["channels"][channel] = {}
            config["channels"][channel]["enabled"] = enabled
        if save_dashboard_config(config):
            st.success("Configuration saved to ~/.nanobot/config.json")
        else:
            st.error("Failed to save configuration")
    except Exception as e:
        st.error(f"Error saving config: {e}")
