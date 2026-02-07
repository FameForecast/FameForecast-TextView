# twitch_chat_monitor/web/queue_bridge.py
"""
Queue Bridge: Polls multiprocessing.Queue and emits WebSocket events.
This is the critical link between backend workers and the web frontend.

Mirrors the polling pattern from gui.py's update_gui() method.
"""
import threading
import queue
import base64
from datetime import datetime


class QueueBridge:
    """
    Bridge between multiprocessing queues and Flask-SocketIO.
    Runs in a background thread, polling gui_queue and emitting events.
    """

    def __init__(self, context, socketio):
        """
        Args:
            context: RuntimeContext with gui_queue, send_queue, etc.
            socketio: Flask-SocketIO instance
        """
        self.context = context
        self.socketio = socketio
        self.running = False
        self.thread = None

    def start(self):
        """Start the bridge thread"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        print("[QueueBridge] Started")

    def stop(self):
        """Stop the bridge thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        print("[QueueBridge] Stopped")

    def _poll_loop(self):
        """
        Main polling loop - mirrors tkinter's update_gui() pattern.
        Polls gui_queue every 100ms and dispatches to WebSocket.
        """
        while self.running:
            try:
                # Non-blocking get with short timeout (matches tkinter's 100ms)
                item = self.context.gui_queue.get(timeout=0.1)
                self._dispatch(item)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[QueueBridge] Error: {e}")

    def _dispatch(self, item):
        """
        Route queue items to appropriate WebSocket events.
        Mirrors the routing logic in gui.py update_gui() lines 307-375.
        """
        if not isinstance(item, tuple):
            print(f"[QueueBridge] Skipping non-tuple item: {type(item)}")
            return

        # Debug: log all items
        if len(item) >= 2:
            print(f"[QueueBridge] Processing: {item[0]} (len={len(item)})")

        # 1. Metadata updates: ('GUI_UPDATE_META', channel, {game, viewers, thumb_bytes})
        if item[0] == 'GUI_UPDATE_META':
            self._handle_metadata(item[1], item[2])
            return

        # 2. Online prompt: ('ONLINE_PROMPT', 'SYSTEM', stream_info)
        if item[0] == 'ONLINE_PROMPT':
            stream_info = item[2]
            if isinstance(stream_info, dict):
                channel = stream_info.get('user', 'Unknown')
            else:
                channel = str(stream_info)

            self.socketio.emit('stream_online', {
                'channel': channel,
                'info': stream_info if isinstance(stream_info, dict) else {'user': channel}
            })
            return

        # 3. Join channel command: ('GUI_JOIN_NOW', 'SYSTEM', channel)
        if item[0] == 'GUI_JOIN_NOW':
            channel = item[2]
            self.socketio.emit('channel_joined', {'channel': channel})
            return

        # 4. Standard messages: (channel, tag, text)
        if len(item) == 3:
            channel, tag, text = item

            # Skip routing to SYSTEM/EXPERIMENT_DATA tabs (R&D only)
            if channel in ['SYSTEM', 'EXPERIMENT_DATA']:
                return

            timestamp = datetime.now().strftime("%H:%M:%S")

            print(f"[QueueBridge] Emitting chat_message: {channel} [{tag}] {text[:50]}...")

            self.socketio.emit('chat_message', {
                'channel': channel,
                'tag': tag,
                'text': text,
                'timestamp': timestamp
            })

    def _handle_metadata(self, channel, meta):
        """
        Handle channel metadata updates (game, viewers, thumbnail).
        Converts thumbnail bytes to base64 for browser display.
        """
        thumb_b64 = None
        thumb_bytes = meta.get('thumb_bytes')

        if thumb_bytes:
            try:
                thumb_b64 = base64.b64encode(thumb_bytes).decode('utf-8')
            except Exception as e:
                print(f"[QueueBridge] Thumbnail encode error: {e}")

        self.socketio.emit('channel_meta', {
            'channel': channel,
            'game': meta.get('game', 'Unknown'),
            'viewers': meta.get('viewers', 0),
            'thumbnail': thumb_b64
        })
