# twitch_chat_monitor/web/socket_events.py
"""
WebSocket event handlers for real-time communication.
"""
import os
import threading
from flask_socketio import emit
from flask import request

# Track connected clients
_connected_clients = set()
_shutdown_timer = None


def register(socketio, context):
    """
    Register all WebSocket event handlers.

    Args:
        socketio: Flask-SocketIO instance
        context: RuntimeContext with queues
    """

    @socketio.on('connect')
    def handle_connect():
        """Client connected - send current state"""
        global _shutdown_timer

        # Cancel any pending shutdown
        if _shutdown_timer is not None:
            _shutdown_timer.cancel()
            _shutdown_timer = None

        _connected_clients.add(request.sid)
        print(f"[WebSocket] Client connected: {request.sid} (total: {len(_connected_clients)})")
        emit('connected', {'status': 'ok', 'sid': request.sid})

        # Send list of active channels if available
        if context and hasattr(context, 'active_channels'):
            emit('active_channels', {
                'channels': list(context.active_channels)
            })

    @socketio.on('disconnect')
    def handle_disconnect():
        """Client disconnected - shutdown if no clients remain"""
        global _shutdown_timer

        _connected_clients.discard(request.sid)
        print(f"[WebSocket] Client disconnected: {request.sid} (remaining: {len(_connected_clients)})")

        # If no clients left, schedule shutdown after brief delay
        # (delay allows for page refresh without triggering shutdown)
        if len(_connected_clients) == 0:
            print("[WebSocket] No clients connected. Shutting down in 3 seconds...")
            _shutdown_timer = threading.Timer(3.0, _trigger_shutdown)
            _shutdown_timer.start()


def _trigger_shutdown():
    """Force shutdown the application"""
    print("[WebSocket] All clients disconnected. Exiting...")
    os._exit(0)

    @socketio.on('send_chat')
    def handle_send_chat(data):
        """
        User sends a chat message.
        Puts message on send_queue for IRC shard to send.
        """
        channel = data.get('channel')
        message = data.get('message', '').strip()

        if channel and message and context:
            # Put on send queue (same as tkinter's send_msg)
            context.send_queue.put((channel, message))

            # Echo back confirmation
            emit('chat_sent', {'channel': channel, 'message': message})

    @socketio.on('join_channel')
    def handle_join_channel(data):
        """User accepts prompt to join a new channel"""
        channel = data.get('channel')

        if channel and context:
            context.gui_queue.put(('GUI_JOIN_NOW', 'SYSTEM', channel))
            emit('join_accepted', {'channel': channel})

    @socketio.on('skip_channel')
    def handle_skip_channel(data):
        """User declines prompt to join a channel"""
        channel = data.get('channel')
        emit('channel_skipped', {'channel': channel})

    @socketio.on('get_active_channels')
    def handle_get_channels(data=None):
        """Request current list of active channels"""
        if context and hasattr(context, 'active_channels'):
            emit('active_channels', {
                'channels': list(context.active_channels)
            })
        else:
            emit('active_channels', {'channels': []})

    @socketio.on('ping')
    def handle_ping():
        """Simple ping/pong for connection health check"""
        emit('pong', {'time': __import__('time').time()})
