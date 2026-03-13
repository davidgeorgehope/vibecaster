"""Configuration management for Vibecaster CLI."""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".vibecaster"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "api_url": "https://vibecaster.ai/api",
    "api_key": None,
}


def load_config() -> dict:
    """Load configuration from disk."""
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        # Merge with defaults for any missing keys
        merged = DEFAULT_CONFIG.copy()
        merged.update(config)
        return merged
    except (json.JSONDecodeError, IOError):
        return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """Save configuration to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    # Restrict permissions on config file (contains API key)
    os.chmod(CONFIG_FILE, 0o600)


def get_api_key() -> str | None:
    """Get the configured API key."""
    return load_config().get("api_key")


def get_api_url() -> str:
    """Get the configured API URL."""
    return load_config().get("api_url", DEFAULT_CONFIG["api_url"])
