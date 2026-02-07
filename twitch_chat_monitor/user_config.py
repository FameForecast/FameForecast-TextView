# twitch_chat_monitor/user_config.py
"""
Handles loading/saving user configuration from JSON file.
Used by the public build - R&D build can still use hardcoded config.py
"""

import json
import os
from pathlib import Path

# Config file location - next to the exe/script
def get_config_path():
    """Get path to user_config.json - checks multiple locations"""
    # 1. Check next to the executable (for PyInstaller builds)
    if getattr(sys, 'frozen', False):
        app_dir = Path(sys.executable).parent
    else:
        # 2. Check in the package directory (for development)
        app_dir = Path(__file__).parent.parent

    return app_dir / "user_config.json"

import sys

DEFAULT_CONFIG = {
    "twitch_client_id": "",
    "twitch_client_secret": "",
    "access_token": "",
    "refresh_token": "",
    "bot_username": "",
    "main_username": "",
    "setup_complete": False
}

class UserConfig:
    def __init__(self):
        self.config_path = get_config_path()
        self.config = self._load()

    def _load(self):
        """Load config from JSON file, or return defaults if not found"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    saved = json.load(f)
                    # Merge with defaults to handle new fields
                    return {**DEFAULT_CONFIG, **saved}
            except (json.JSONDecodeError, IOError):
                return DEFAULT_CONFIG.copy()
        return DEFAULT_CONFIG.copy()

    def reload(self):
        """Reload config from file"""
        self.config = self._load()

    def save(self):
        """Save current config to JSON file"""
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def is_setup_complete(self):
        """Check if initial setup has been completed"""
        return (
            self.config.get("setup_complete", False) and
            self.config.get("twitch_client_id") and
            self.config.get("access_token")
        )

    def get(self, key, default=None):
        """Get a config value"""
        return self.config.get(key, default)

    def set(self, key, value):
        """Set a config value (doesn't auto-save)"""
        self.config[key] = value

    def update(self, **kwargs):
        """Update multiple config values and save"""
        self.config.update(kwargs)
        self.save()

# Global instance for easy import
user_config = UserConfig()
