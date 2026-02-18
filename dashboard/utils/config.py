"""Configuration wrapper for dashboard."""

from pathlib import Path
from typing import Any
import json
import os

try:
    from nanobot.config.loader import load_config, save_config, get_config_path
    from nanobot.config.schema import Config
    _HAS_NANOBOT = True
except ImportError:
    _HAS_NANOBOT = False

def get_config_file_path():
    """Get path to config.json, fallback to direct path if nanobot not available."""
    if _HAS_NANOBOT:
        try:
            return get_config_path()
        except:
            pass
    
    # Fallback: direct path
    home = Path.home()
    return home / ".nanobot" / "config.json"


def load_dashboard_config() -> Any:
    """Load nanobot config. Returns Config or None if unavailable."""
    # Try nanobot loader first
    if _HAS_NANOBOT:
        try:
            return load_config()
        except Exception:
            pass
    
    # Fallback: direct JSON loading
    config_path = get_config_file_path()
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    
    return None


def save_dashboard_config(config: Any) -> bool:
    """Save nanobot config. Returns True on success."""
    # Try nanobot saver first
    if _HAS_NANOBOT:
        try:
            save_config(config)
            return True
        except Exception:
            pass
    
    # Fallback: direct JSON saving
    config_path = get_config_file_path()
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def get_config_path_resolved() -> Path | None:
    """Get resolved config path (~/.nanobot/config.json)."""
    return get_config_file_path()
