# twitch_monitor_web.py
"""
FameForecastTextView - Web Interface Entry Point
Replaces tkinter GUI with Flask + WebSocket

Run with: python twitch_monitor_web.py
Opens browser to http://localhost:8080
"""

import os
import sys

# Add parent directory to path so we can import shared twitch_chat_monitor module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import multiprocessing as mp

# CRITICAL: This must be called before any other multiprocessing code
# Required for PyInstaller frozen executables on Windows
if __name__ == '__main__':
    mp.freeze_support()
    mp.set_start_method('spawn', force=True)


def main():
    """Main entry point - all app logic goes here"""
    import queue
    import signal
    import time
    import webbrowser
    from datetime import datetime
    import requests
    import threading
    from pathlib import Path

    from twitch_chat_monitor.user_config import user_config
    from twitch_chat_monitor.logger import DataLogger
    from twitch_chat_monitor.web import create_app, socketio, QueueBridge

    # Settings
    HOST = '127.0.0.1'
    PORT = 8080
    MAX_CHANNELS_PER_CONN = 10

    # Data storage
    SESSION_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
    DATA_DIR = Path(f"session_data/{SESSION_ID}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    class RuntimeContext:
        def __init__(self):
            self.gui_queue = mp.Queue()
            self.send_queue = mp.Queue()
            self.audio_queue = mp.Queue()
            self.control_queue = mp.Queue()
            self.ai_work_queue = mp.Queue()

            manager = mp.Manager()
            self.bot_state = manager.dict()

            # Web-specific state
            self.active_channels = set()
            self.live_data = {}
            self.follower_counts = {}
            self.selected_channels = set()
            self.data_dir = DATA_DIR

    # Create context first (needed for app creation)
    context = RuntimeContext()
    context.data_logger = DataLogger(DATA_DIR)

    # Load credentials if setup is complete
    if user_config.is_setup_complete():
        TWITCH_CLIENT_ID = user_config.get('twitch_client_id')
        TWITCH_CLIENT_SECRET = user_config.get('twitch_client_secret')
        CURRENT_ACCESS_TOKEN = user_config.get('access_token')
        TWITCH_OAUTH = f"oauth:{CURRENT_ACCESS_TOKEN}"
        BOT_USERNAME = user_config.get('bot_username')
        MAIN_USERNAME = user_config.get('main_username')
        MAIN_USER_TOKEN = CURRENT_ACCESS_TOKEN

        context.bot_state['oauth_token'] = TWITCH_OAUTH
        context.bot_state['bot_username'] = BOT_USERNAME
        context.bot_state['client_id'] = TWITCH_CLIENT_ID
        context.bot_state['ai_mode_enabled'] = False
        context.bot_state['public_build'] = True
    else:
        # Will redirect to /setup
        TWITCH_CLIENT_ID = None
        TWITCH_CLIENT_SECRET = None
        MAIN_USERNAME = None
        MAIN_USER_TOKEN = None

    # Create Flask app
    app = create_app(context)

    # Create queue bridge
    bridge = QueueBridge(context, socketio)

    # Track processes and shards
    processes = []
    shards = []
    audio_procs = {}
    followed_channels = []
    known_live_channels = set()

    # API helper functions
    def get_app_access_token():
        resp = requests.post(
            'https://id.twitch.tv/oauth2/token',
            params={
                'client_id': TWITCH_CLIENT_ID,
                'client_secret': TWITCH_CLIENT_SECRET,
                'grant_type': 'client_credentials'
            }
        )
        resp.raise_for_status()
        return resp.json()['access_token']

    def get_main_user_id():
        token = MAIN_USER_TOKEN
        if token and token.startswith('oauth:'):
            token = token.removeprefix('oauth:')

        headers = {'Client-ID': TWITCH_CLIENT_ID, 'Authorization': f'Bearer {token}'}
        params = {'login': MAIN_USERNAME.lower()}

        resp = requests.get('https://api.twitch.tv/helix/users', headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()['data']
        if not data:
            raise ValueError(f"No user found for '{MAIN_USERNAME}'")
        return data[0]['id']

    def get_my_followed_channels(main_user_id):
        token = MAIN_USER_TOKEN
        if token and token.startswith('oauth:'):
            token = token.removeprefix('oauth:')

        headers = {'Client-ID': TWITCH_CLIENT_ID, 'Authorization': f'Bearer {token}'}
        followed = []
        after = None

        while True:
            params = {'user_id': main_user_id, 'first': 100}
            if after:
                params['after'] = after
            resp = requests.get('https://api.twitch.tv/helix/channels/followed', headers=headers, params=params)
            resp.raise_for_status()
            json_data = resp.json()
            for item in json_data['data']:
                followed.append(item['broadcaster_login'].lower())
            after = json_data.get('pagination', {}).get('cursor')
            if not after:
                break

        return followed

    def get_follower_counts(channels, token):
        if not channels:
            return {}

        from concurrent.futures import ThreadPoolExecutor, as_completed

        headers = {'Client-ID': TWITCH_CLIENT_ID, 'Authorization': f'Bearer {token}'}
        follower_counts = {}
        user_ids = {}

        for i in range(0, len(channels), 100):
            batch = channels[i:i+100]
            params = {'login': batch}
            try:
                resp = requests.get('https://api.twitch.tv/helix/users', headers=headers, params=params)
                resp.raise_for_status()
                for user in resp.json()['data']:
                    user_ids[user['login'].lower()] = user['id']
            except Exception as e:
                print(f"Error fetching user IDs: {e}")

        def fetch_followers(channel, user_id):
            try:
                params = {'broadcaster_id': user_id, 'first': 1}
                resp = requests.get('https://api.twitch.tv/helix/channels/followers', headers=headers, params=params)
                resp.raise_for_status()
                return channel, resp.json().get('total', 0)
            except:
                return channel, 0

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_followers, ch, uid) for ch, uid in user_ids.items()]
            for future in as_completed(futures):
                channel, count = future.result()
                follower_counts[channel] = count

        return follower_counts

    def get_live_status(channels, token):
        if not channels:
            return {}

        headers = {'Client-ID': TWITCH_CLIENT_ID, 'Authorization': f'Bearer {token}'}
        live_data = {}

        for i in range(0, len(channels), 100):
            batch = channels[i:i+100]
            params = {'user_login': batch}
            try:
                resp = requests.get('https://api.twitch.tv/helix/streams', headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()['data']

                for stream in data:
                    login = stream['user_login'].lower()
                    raw_thumb_url = stream.get('thumbnail_url', '')
                    thumb_url = raw_thumb_url.replace('{width}', '160').replace('{height}', '90')

                    thumb_bytes = None
                    if thumb_url:
                        try:
                            r = requests.get(thumb_url, timeout=2)
                            if r.status_code == 200:
                                thumb_bytes = r.content
                        except:
                            pass

                    live_data[login] = {
                        'user': login,
                        'game': stream.get('game_name', 'Unknown'),
                        'viewers': stream.get('viewer_count', 0),
                        'thumb_bytes': thumb_bytes
                    }
            except Exception as e:
                print(f"API Error: {e}")

        return live_data

    def rebuild_shards():
        nonlocal shards
        for shard in shards:
            shard.stop()
        for shard in shards:
            if shard.is_alive():
                shard.join(timeout=5)
        shards.clear()

        from twitch_chat_monitor.irc import IRCShard

        channel_list = sorted(context.active_channels)
        for i in range(0, len(channel_list), MAX_CHANNELS_PER_CONN):
            shard_channels = channel_list[i:i + MAX_CHANNELS_PER_CONN]
            if shard_channels:
                shard_id = f"shard_{i // MAX_CHANNELS_PER_CONN}"
                shard = IRCShard(shard_channels, shard_id, context)
                shard.daemon = True
                shard.start()
                shards.append(shard)

    def update_audio_workers():
        current = set(audio_procs.keys())
        needed = context.active_channels

        for chan in current - needed:
            audio_procs[chan].terminate()
            audio_procs[chan].join(timeout=5)
            del audio_procs[chan]

        for chan in needed - current:
            from twitch_chat_monitor.audio import audio_worker
            p = mp.Process(
                target=audio_worker,
                args=(chan, context.audio_queue, context.control_queue, DATA_DIR)
            )
            p.daemon = True
            p.start()
            audio_procs[chan] = p
            processes.append(p)

    def handle_join_channel(channel):
        """Called when user accepts a stream prompt or joins via API"""
        # Add to active_channels if not already there
        if channel not in context.active_channels:
            context.active_channels.add(channel)

        # Always rebuild shards and update workers
        rebuild_shards()
        update_audio_workers()
        context.gui_queue.put((channel, 'SYSTEM', f"Joined {channel}"))

    # Signal handling
    def signal_handler(signum, frame):
        print("\nShutting down...")
        bridge.stop()
        for _ in range(mp.cpu_count() * 2):
            context.control_queue.put("SHUTDOWN")
        time.sleep(2)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Background initialization after setup is complete
    def initialize_after_setup():
        nonlocal followed_channels, known_live_channels
        nonlocal TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, MAIN_USERNAME, MAIN_USER_TOKEN

        # Wait for setup to complete (poll every second)
        while not user_config.is_setup_complete():
            time.sleep(1)

        # Reload credentials after setup
        user_config.reload()
        TWITCH_CLIENT_ID = user_config.get('twitch_client_id')
        TWITCH_CLIENT_SECRET = user_config.get('twitch_client_secret')
        CURRENT_ACCESS_TOKEN = user_config.get('access_token')
        MAIN_USERNAME = user_config.get('main_username')
        MAIN_USER_TOKEN = CURRENT_ACCESS_TOKEN

        # Update context with credentials
        context.bot_state['oauth_token'] = f"oauth:{CURRENT_ACCESS_TOKEN}"
        context.bot_state['bot_username'] = user_config.get('bot_username')
        context.bot_state['client_id'] = TWITCH_CLIENT_ID
        context.bot_state['ai_mode_enabled'] = False
        context.bot_state['public_build'] = True

        # Retry logic with exponential backoff
        max_retries = 5
        retry_delay = 2  # Start with 2 seconds

        for attempt in range(max_retries):
            print(f"Fetching channel data... (attempt {attempt + 1}/{max_retries})")
            try:
                main_user_id = get_main_user_id()
                followed_channels = get_my_followed_channels(main_user_id)
                print(f"Found {len(followed_channels)} followed channels")

                app_token = get_app_access_token()
                live_data = get_live_status(followed_channels, app_token)
                known_live_channels = set(live_data.keys())

                online = [ch for ch in followed_channels if ch.lower() in live_data]

                if online:
                    context.follower_counts = get_follower_counts(online, app_token)
                context.live_data = live_data

                print(f"Found {len(online)} live channels")
                return  # Success, exit the retry loop

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                print(f"Network error (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    print("Max retries reached. Will retry in monitor loop.")

            except Exception as e:
                print(f"Initialization error: {e}")
                import traceback
                traceback.print_exc()
                break  # Don't retry on non-network errors

    # Monitor loop for detecting new streams
    def monitor_loop():
        nonlocal known_live_channels
        consecutive_failures = 0

        while True:
            time.sleep(60)

            if not user_config.is_setup_complete():
                continue

            try:
                token = get_app_access_token()
                current_live_data = get_live_status(followed_channels, token)
                current_live_names = set(current_live_data.keys())

                # Reset failure count on success
                consecutive_failures = 0

                # Offline detection
                went_offline = [ch for ch in context.active_channels if ch.lower() not in current_live_names]
                for ch in went_offline:
                    context.gui_queue.put((ch, 'SYSTEM', f"{ch} went offline"))
                    context.active_channels.discard(ch)

                # New streams
                just_went_live = [ch for ch in current_live_names if ch not in known_live_channels]
                for ch_name in just_went_live:
                    if ch_name not in context.active_channels:
                        stream_info = current_live_data[ch_name]
                        context.gui_queue.put(('ONLINE_PROMPT', 'SYSTEM', stream_info))

                # Update metadata for active channels
                for ch in context.active_channels:
                    if ch in current_live_data:
                        data = current_live_data[ch]
                        context.gui_queue.put(('GUI_UPDATE_META', ch, data))

                known_live_channels = current_live_names
                context.live_data = current_live_data

                if went_offline:
                    rebuild_shards()
                    update_audio_workers()

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                consecutive_failures += 1
                print(f"Monitor network error ({consecutive_failures}): {e}")
                # Back off on repeated failures
                if consecutive_failures > 3:
                    print("Multiple network failures, waiting 2 minutes before retry...")
                    time.sleep(60)  # Extra delay on top of the normal 60s

            except Exception as e:
                print(f"Monitor error: {e}")

    # Track which channels have workers running
    channels_with_workers = set()

    # Handle GUI_JOIN_NOW from queue (triggered by web UI)
    def process_join_requests():
        """Check for join requests from the web UI"""
        nonlocal channels_with_workers

        while True:
            try:
                time.sleep(0.5)

                # Check if there are new channels that need workers started
                channels_needing_workers = context.active_channels - channels_with_workers

                if channels_needing_workers:
                    print(f"Starting workers for: {channels_needing_workers}")
                    for ch in channels_needing_workers:
                        handle_join_channel(ch)
                        channels_with_workers.add(ch)

                # Clear selected_channels since they're now in active
                if context.selected_channels:
                    context.selected_channels.clear()

            except Exception as e:
                print(f"Join processor error: {e}")
                import traceback
                traceback.print_exc()

    # Flag to track if whisper has been started
    whisper_started = False

    def start_whisper_if_needed():
        nonlocal whisper_started
        if whisper_started:
            return

        from twitch_chat_monitor.whisper import whisper_worker

        p_whisper = mp.Process(
            target=whisper_worker,
            args=(context.audio_queue, context.gui_queue, context.control_queue,
                  context.ai_work_queue, context.bot_state, DATA_DIR)
        )
        p_whisper.daemon = True
        p_whisper.start()
        processes.append(p_whisper)
        whisper_started = True
        print("Transcription engine started")

    # Extended initialization that starts whisper after data is loaded
    def full_initialization():
        initialize_after_setup()

        # Start whisper after credentials are loaded
        if user_config.is_setup_complete():
            start_whisper_if_needed()
            # Start monitor loop
            threading.Thread(target=monitor_loop, daemon=True).start()

    # Start background threads
    threading.Thread(target=full_initialization, daemon=True).start()
    threading.Thread(target=process_join_requests, daemon=True).start()

    # Start queue bridge
    bridge.start()

    # Open browser after short delay
    def open_browser():
        time.sleep(1.5)
        url = f'http://{HOST}:{PORT}'
        print(f"Opening browser to {url}")
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()

    # Start Flask server
    print(f"\n{'='*50}")
    print("FameForecastTextView - Web Interface")
    print(f"{'='*50}")
    print(f"Server: http://{HOST}:{PORT}")
    print("Press Ctrl+C to exit.\n")

    try:
        socketio.run(app, host=HOST, port=PORT, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nCleaning up...")
        bridge.stop()

        for _ in range(len(processes) + 10):
            context.control_queue.put("SHUTDOWN")

        for p in processes:
            if p.is_alive():
                p.join(timeout=3)
                if p.is_alive():
                    p.terminate()

        for p in audio_procs.values():
            if p.is_alive():
                p.terminate()
                p.join(timeout=3)

        for shard in shards:
            shard.stop()
            if shard.is_alive():
                shard.join(timeout=5)

        if hasattr(context, 'data_logger'):
            context.data_logger.close_files()

        print("Goodbye!")


if __name__ == '__main__':
    main()
