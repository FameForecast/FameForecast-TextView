import subprocess
import streamlink
from streamlink import Streamlink
import numpy as np
import time
import shutil
import sys
import os
from datetime import datetime, timezone
from queue import Empty

def get_ffmpeg_path():
    """Get FFmpeg path - check bundled location first, then system PATH"""
    # Check if running as frozen exe (PyInstaller)
    if getattr(sys, 'frozen', False):
        # Look for ffmpeg in the same folder as the exe
        exe_dir = os.path.dirname(sys.executable)
        bundled_ffmpeg = os.path.join(exe_dir, 'ffmpeg.exe')
        if os.path.exists(bundled_ffmpeg):
            return bundled_ffmpeg

    # Fall back to system PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    return None
# Try to import from config (R&D build), fallback to defaults (public build)
try:
    from .config import CHUNK_DURATION, SAMPLE_RATE
except ImportError:
    CHUNK_DURATION = 5
    SAMPLE_RATE = 16000
from .logger import DataLogger

def audio_worker(channel, audio_queue, control_queue, data_dir):
    data_logger = DataLogger(data_dir)

    # 1. CRITICAL CHECK: Is FFMPEG available?
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        print(f"[{channel}] ❌ CRITICAL: 'ffmpeg' not found. Audio capture impossible.")
        return

    print(f"[{channel}] 🎧 Audio Worker Started")

    session = Streamlink()
    # Optional: Spoof headers to avoid 403 Forbidden from Twitch
    session.set_option("http-headers", {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    })

    while True:
        try:
            if control_queue.get_nowait() == "SHUTDOWN": return
        except Empty: pass

        process = None
        try:
            # 2. FETCH STREAM URL
            twitch_url = f"https://twitch.tv/{channel}"
            streams = None
            
            try:
                # Try Method A: Default
                streams = streamlink.streams(twitch_url)
            except Exception as e1:
                print(f"[{channel}] Streamlink method A failed: {e1}")
                # Try Method B: Session (Fallback)
                try:
                    streams = session.streams(twitch_url)
                except Exception as e2:
                    print(f"[{channel}] Streamlink method B failed: {e2}")
                    pass

            if not streams:
                print(f"[{channel}] No streams found, waiting 60s...")
                time.sleep(60)
                continue

            if 'audio_only' not in streams:
                print(f"[{channel}] Available streams: {list(streams.keys())}")
                # Try best quality audio alternative
                time.sleep(60)
                continue

            # 3. START CAPTURE
            stream_url = streams['audio_only'].url
            print(f"[{channel}] 🔴 Capture Starting...")
            data_logger.log_system(datetime.now(timezone.utc).isoformat(), "STREAM_ONLINE", channel, "Starting Capture", "INFO")
            
            cmd = [ffmpeg_path, '-i', stream_url, '-f', 'f32le', '-ac', '1', '-ar', str(SAMPLE_RATE), '-vn', '-loglevel', 'error', 'pipe:1']

            # Use a buffer to prevent stalling
            # CREATE_NO_WINDOW flag hides the ffmpeg console on Windows
            creationflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**7, creationflags=creationflags)
            
            chunk_size = 4 * SAMPLE_RATE * CHUNK_DURATION
            idx = 0
            
            while True:
                try: 
                    if control_queue.get_nowait() == "SHUTDOWN": 
                        process.terminate(); return
                except Empty: pass
                
                raw = process.stdout.read(chunk_size)
                
                if not raw:
                    print(f"[{channel}] ⚠️ Stream ended or FFMPEG exited.")
                    break 
                
                # Backpressure Protection
                if audio_queue.qsize() > 50: 
                    continue 
                
                audio_queue.put({
                    'channel': channel, 
                    'audio_data': np.frombuffer(raw, dtype=np.float32), 
                    'chunk_start': idx*CHUNK_DURATION, 
                    'chunk_end': (idx+1)*CHUNK_DURATION
                })
                idx += 1

        except Exception as e:
            # 4. VISIBLE ERROR LOGGING
            print(f"[{channel}] ❌ Audio Crash: {e}")
            data_logger.log_system(datetime.now(timezone.utc).isoformat(), "AUDIO_CRASH", channel, str(e), "ERROR")
            time.sleep(10)
        
        finally:
            if process:
                try:
                    process.terminate()
                    process.wait(timeout=2)
                except:
                    pass