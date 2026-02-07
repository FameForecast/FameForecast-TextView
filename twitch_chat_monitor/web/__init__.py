# twitch_chat_monitor/web/__init__.py
"""
Web interface package for FameForecastTextView.
Flask + WebSocket replacement for tkinter GUI.
"""

from .app import create_app, socketio
from .queue_bridge import QueueBridge

__all__ = ['create_app', 'socketio', 'QueueBridge']
