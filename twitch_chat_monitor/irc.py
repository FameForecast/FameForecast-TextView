import socket
import threading
import time
import queue
import json
from datetime import datetime, timezone
from collections import deque
# Try to import from config (R&D build), fallback to defaults (public build)
try:
    from .config import (
        BOT_USERNAME, TWITCH_OAUTH, MSG_LIMIT, MSG_WINDOW, MIN_MSG_DELAY,
        DATA_DIR, EXPERIMENT_ID
    )
except ImportError:
    # Public build defaults - actual values come from bot_state/context
    BOT_USERNAME = ""
    TWITCH_OAUTH = ""
    MSG_LIMIT = 20
    MSG_WINDOW = 30
    MIN_MSG_DELAY = 1.6
    DATA_DIR = None
    EXPERIMENT_ID = "PUBLIC"

# Conditional import for R&D analyzer (not used in public build)
try:
    from .analyzer import rnd_analyzer
    ANALYZER_AVAILABLE = True
except ImportError:
    rnd_analyzer = None
    ANALYZER_AVAILABLE = False

# --- TwitchLimiter (unchanged) ---
class TwitchLimiter:
    def __init__(self, limit=MSG_LIMIT, window=MSG_WINDOW, min_delay=MIN_MSG_DELAY):
        self.limit = limit
        self.window = window
        self.min_delay = min_delay
        self.events = deque()
        self.last_message = 0
        self.lock = threading.Lock()
        self.metrics = {
            'total_attempts': 0,
            'allowed_messages': 0,
            'rate_limited': 0,
            'min_delay_blocked': 0,
            'avg_delay': 0.0
        }
        self.start_time = time.time()

    def allow(self):
        with self.lock:
            self.metrics['total_attempts'] += 1
            now = time.time()

            if now - self.last_message < self.min_delay:
                self.metrics['min_delay_blocked'] += 1
                return False

            while self.events and now - self.events[0] > self.window:
                self.events.popleft()

            if len(self.events) < self.limit:
                self.events.append(now)
                self.last_message = now
                self.metrics['allowed_messages'] += 1

                if len(self.events) > 1:
                    delays = [self.events[i] - self.events[i-1] for i in range(1, len(self.events))]
                    self.metrics['avg_delay'] = sum(delays) / len(delays)

                return True
            else:
                self.metrics['rate_limited'] += 1
                return False

    def get_metrics(self):
        runtime = time.time() - self.start_time
        metrics = self.metrics.copy()
        metrics['runtime_seconds'] = runtime
        metrics['messages_per_minute'] = (metrics['allowed_messages'] / runtime * 60) if runtime > 0 else 0
        return metrics


class IRCShard(threading.Thread):
    def __init__(self, channels, shard_id, context):
        super().__init__()
        self.channels = channels
        self.shard_id = shard_id
        self.context = context
        self.sock = None
        self.buffer = ""
        self.limiter = TwitchLimiter()
        self.running = True
        self.reconnect_delay = 1
        self.message_count = 0
        self.start_time = time.time()

        # Get username from bot_state (public build) or config (R&D build)
        if hasattr(context, 'bot_state') and 'bot_username' in context.bot_state:
            self.username = context.bot_state['bot_username']
        else:
            self.username = BOT_USERNAME
        self.data_dir = getattr(context, 'data_dir', DATA_DIR)

        # Real-time user tracking: channel → set of lowercase usernames
        self.channel_users = {chan.lower(): set() for chan in channels}

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass

    def part_channels(self, channels_to_part):
        if not self.sock:
            return
        for chan in channels_to_part:
            try:
                self.sock.send(f"PART #{chan}\r\n".encode('utf-8'))
                self.context.gui_queue.put((chan, 'SYSTEM', f"Bot parted #{chan}"))
            except:
                pass
        self.channels = [c for c in self.channels if c not in channels_to_part]

        # Clean up tracking
        for chan in channels_to_part:
            clean = chan.lower()
            self.channel_users.pop(clean, None)

    def join_channels(self, new_channels):
        if not self.sock or not new_channels:
            return
        new_channels = [c for c in new_channels if c not in self.channels]
        if not new_channels:
            return
        join_str = ",".join([f"#{c}" for c in new_channels])
        try:
            self.sock.send(f"JOIN {join_str}\r\n".encode('utf-8'))
            self.channels.extend(new_channels)
            self.context.gui_queue.put(('SYSTEM', 'SYSTEM', f"Joined additional channels: {new_channels}"))

            # Initialize tracking + inform GUI
            for chan in new_channels:
                clean = chan.lower()
                self.channel_users[clean] = set()
                self.context.gui_queue.put((clean, 'SYSTEM',
                                            "Collecting chatters in real-time from joins, parts & messages..."))

        except Exception as e:
            self.context.data_logger.log_system(
                datetime.now(timezone.utc).isoformat(),
                "JOIN_FAILED", "ALL",
                f"Shard {self.shard_id} failed to join {new_channels}: {e}", "WARNING"
            )

    def run(self):
        while self.running:
            try:
                self.connect(self.channels)
                self.reconnect_delay = 1
                while self.running:
                    try:
                        if self.context.control_queue.get_nowait() == "SHUTDOWN":
                            self.running = False
                            break
                    except queue.Empty:
                        pass

                    # OUTGOING MESSAGES
                    try:
                        target_chan, msg = self.context.send_queue.get_nowait()
                        send_time = time.time()
                        while not self.limiter.allow():
                            time.sleep(0.05)
                        self.sock.send(f"PRIVMSG #{target_chan} :{msg}\r\n".encode('utf-8'))
                        self.context.bot_state[target_chan] = {
                            'last_msg': msg,
                            'last_time': time.time()
                        }
                        self.context.data_logger.log_chat(
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            channel=target_chan,
                            user=self.username,
                            msg_type="SELF",
                            message=msg,
                            irc_delay=int((time.time() - send_time) * 1000)
                        )
                        self.context.gui_queue.put((target_chan, 'SELF', f"You: {msg}"))
                    except queue.Empty:
                        pass

                    # INCOMING MESSAGES
                    try:
                        self.sock.settimeout(0.1)
                        data = self.sock.recv(4096).decode('utf-8', errors='ignore')
                        if not data:
                            break
                        self.buffer += data
                        lines = self.buffer.split('\r\n')
                        self.buffer = lines.pop() if lines else ""
                        for line in lines:
                            if not line:
                                continue
                            if line.startswith("PING"):
                                self.sock.send("PONG :tmi.twitch.tv\r\n".encode('utf-8'))
                            elif "PRIVMSG" in line:
                                self.parse_privmsg(line)
                            elif "NOTICE" in line:
                                self.parse_notice(line)
                            elif "JOIN" in line or "PART" in line:
                                self.parse_presence(line)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        self.context.data_logger.log_system(
                            datetime.now(timezone.utc).isoformat(),
                            "CONNECTION_ERROR", "ALL",
                            f"Shard {self.shard_id}: {str(e)}", "ERROR"
                        )
                        break
            except Exception as e:
                self.context.data_logger.log_system(
                    datetime.now(timezone.utc).isoformat(),
                    "RECONNECT_FAILED", "ALL",
                    f"Shard {self.shard_id}: {str(e)}", "WARNING"
                )
                time.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 2, 60)
        self.cleanup()

    def cleanup(self):
        if self.sock and self.channels:
            self.part_channels(self.channels)
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
        if self.data_dir:
            metrics_file = self.data_dir / f"shard_{self.shard_id}_metrics.json"
            metrics = {
                'shard_id': self.shard_id,
                'channels': self.channels,
                'message_count': self.message_count,
                'runtime_seconds': time.time() - self.start_time,
                'rate_limiter_metrics': self.limiter.get_metrics()
            }
            with open(metrics_file, 'w') as f:
                json.dump(metrics, f, indent=2)

    def connect(self, channels=None):
        if channels is not None:
            self.channels = channels

        # Get token from bot_state (public build) or fall back to config (R&D build)
        if hasattr(self.context, 'bot_state') and 'oauth_token' in self.context.bot_state:
            real_token = self.context.bot_state['oauth_token']
        else:
            real_token = TWITCH_OAUTH

        self.sock = socket.socket()
        self.sock.connect(('irc.chat.twitch.tv', 6667))

        self.sock.send(f"PASS {real_token}\r\n".encode('utf-8'))
        self.sock.send(f"NICK {self.username}\r\n".encode('utf-8'))
        self.sock.send("CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership\r\n".encode('utf-8'))

        if self.channels:
            join_str = ",".join([f"#{c}" for c in self.channels])
            self.sock.send(f"JOIN {join_str}\r\n".encode('utf-8'))

            # No fetch thread anymore — just inform GUI
            for chan in self.channels:
                clean = chan.lower()
                self.channel_users[clean] = set()
                self.context.gui_queue.put((clean, 'SYSTEM',
                                            "Collecting chatters in real-time from joins, parts & messages..."))

        self.context.gui_queue.put(('SYSTEM', 'SYSTEM', f"Shard {self.shard_id} connected to {len(self.channels)} channels"))
        self.context.data_logger.log_system(
            datetime.now(timezone.utc).isoformat(),
            "SHARD_CONNECTED", "ALL",
            f"Shard {self.shard_id} connected to channels: {self.channels}", "INFO"
        )

    def parse_privmsg(self, line):
        try:
            tags = {}
            if line.startswith("@"):
                tag_part, rest = line.split(" ", 1)
                tag_items = tag_part[1:].split(";")
                for item in tag_items:
                    if "=" in item:
                        key, value = item.split("=", 1)
                        tags[key] = value
                line = rest
            parts = line.split("PRIVMSG", 1)
            if len(parts) < 2:
                return
            header = parts[0].strip()
            body = parts[1].strip()
            if ":" not in body:
                return
            chan_part, msg_part = body.split(":", 1)
            chan = chan_part.strip().lstrip("#").lower()
            msg = msg_part.strip()
            raw_user = header.split("!")[0][1:] if "!" in header else "Unknown"
            user = raw_user.lower()
            self.message_count += 1

            self.context.data_logger.log_chat(
                timestamp=datetime.now(timezone.utc).isoformat(),
                channel=chan, user=user, msg_type="CHAT", message=msg
            )
            self.context.gui_queue.put((chan, 'CHAT', f"{user}: {msg}"))

            # R&D Analyzer (only in non-public builds)
            if ANALYZER_AVAILABLE and rnd_analyzer:
                insights = rnd_analyzer.analyze_message(chan, user, msg, datetime.now().strftime("%H:%M:%S"))
                if insights:
                    for insight in insights:
                        self.context.gui_queue.put(('EXPERIMENT_DATA', 'DATA',
                                                   f"[{insight.channel}] {insight.insight_type}: {insight.details}"))
                        self.context.data_logger.log_insight(
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            channel=insight.channel,
                            user=insight.user,
                            insight_type=insight.insight_type,
                            details=insight.details,
                            confidence=insight.confidence,
                            experiment_id=EXPERIMENT_ID
                        )

            is_subscriber = tags.get('subscriber', '0') == '1'
            user_id = tags.get('user-id', '0')
            self.context.data_logger.log_system(
                datetime.now(timezone.utc).isoformat(),
                "USER_METADATA", chan,
                f"user={user} | id={user_id} | sub={is_subscriber}",
                "INFO"
            )

            # Real-time tracking: add speakers
            if chan in self.channel_users and user not in self.channel_users[chan]:
                self.channel_users[chan].add(user)
                self.context.data_logger.log_system(
                    datetime.now(timezone.utc).isoformat(),
                    "USER_PRESENT", chan, user, "INFO"
                )
                print(f"[USER TRACK] New via PRIVMSG: {user} in {chan}")

        except Exception as e:
            self.context.data_logger.log_system(
                datetime.now(timezone.utc).isoformat(),
                "PARSE_ERROR", "UNKNOWN", str(e), "ERROR"
            )

    def parse_notice(self, line):
        try:
            parts = line.split("NOTICE", 1)
            if len(parts) < 2:
                return
            body = parts[1].strip()
            if ":" in body:
                chan_part, msg_part = body.split(":", 1)
                chan = chan_part.strip().lstrip("#").strip()
                msg = msg_part.strip()
                self.context.gui_queue.put((chan, 'SYSTEM', f"[NOTICE] {msg}"))
                self.context.data_logger.log_system(
                    datetime.now(timezone.utc).isoformat(),
                    "IRC_NOTICE", chan, msg, "INFO"
                )
        except Exception as e:
            self.context.data_logger.log_system(
                datetime.now(timezone.utc).isoformat(),
                "NOTICE_PARSE_ERROR", "UNKNOWN",
                f"Failed to parse NOTICE: {line}", "ERROR"
            )

    def parse_presence(self, line):
        try:
            if "JOIN" in line:
                parts = line.split("JOIN", 1)
                raw_user = parts[0].split("!")[0][1:] if "!" in parts[0] else "Unknown"
                user = raw_user.lower()
                chan = parts[1].strip().lstrip("#").lower()

                self.context.data_logger.log_system(
                    datetime.now(timezone.utc).isoformat(),
                    "USER_JOINED", chan, user, "INFO"
                )

                if chan in self.channel_users and user not in self.channel_users[chan]:
                    self.channel_users[chan].add(user)
                    self.context.data_logger.log_system(
                        datetime.now(timezone.utc).isoformat(),
                        "USER_PRESENT", chan, user, "INFO"
                    )
                    print(f"[USER TRACK] New via JOIN: {user} in {chan}")

            elif "PART" in line:
                parts = line.split("PART", 1)
                raw_user = parts[0].split("!")[0][1:] if "!" in parts[0] else "Unknown"
                user = raw_user.lower()
                chan = parts[1].strip().lstrip("#").lower()

                self.context.data_logger.log_system(
                    datetime.now(timezone.utc).isoformat(),
                    "USER_PARTED", chan, user, "INFO"
                )

                if chan in self.channel_users:
                    self.channel_users[chan].discard(user)

        except:
            pass
