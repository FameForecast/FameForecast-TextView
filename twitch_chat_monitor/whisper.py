from faster_whisper import WhisperModel
from datetime import datetime, timezone
import time
import sys
import os
from queue import Empty
from .logger import DataLogger


def get_bundled_model_path():
    """Get path to bundled whisper model if running as frozen exe"""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        bundled_model = os.path.join(exe_dir, 'models', 'faster-whisper-base')
        if os.path.exists(bundled_model) and os.path.isdir(bundled_model):
            # Check if model.bin exists in the directory
            if os.path.exists(os.path.join(bundled_model, 'model.bin')):
                return bundled_model
    return None

# Conditional import for R&D analyzer (not used in public build)
try:
    from .analyzer import rnd_analyzer
    ANALYZER_AVAILABLE = True
except ImportError:
    rnd_analyzer = None
    ANALYZER_AVAILABLE = False

def whisper_worker(audio_queue, gui_queue, control_queue, ai_work_queue, bot_state, data_dir):
    data_logger = DataLogger(data_dir)
    using_gpu = False

    # Check if this is public build (use CPU to avoid CUDNN bundling issues)
    is_public_build = bot_state.get('public_build', False) if bot_state else False

    try:
        print("[WHISPER] Loading Model...")

        if is_public_build:
            # Public build: Use CPU to avoid CUDNN DLL issues in bundled exe
            print("[WHISPER] Public build detected, using CPU mode...")

            # Try bundled model first (no download needed)
            bundled_path = get_bundled_model_path()
            if bundled_path:
                print(f"[WHISPER] Using bundled model from: {bundled_path}")
                model = WhisperModel(bundled_path, device="cpu", compute_type="int8")
            else:
                print("[WHISPER] No bundled model found, downloading...")
                model = WhisperModel("base", device="cpu", compute_type="int8")

            data_logger.log_system(datetime.now(timezone.utc).isoformat(), "WHISPER_READY", "ALL", "CPU Model Loaded", "INFO")
            print("[WHISPER] Ready (CPU Mode).")
        else:
            # R&D build: Try GPU first, fall back to CPU if it fails
            try:
                model = WhisperModel("base", device="cuda", compute_type="float16")
                using_gpu = True
                data_logger.log_system(datetime.now(timezone.utc).isoformat(), "WHISPER_READY", "ALL", "GPU Model Loaded", "INFO")
                print("[WHISPER] Ready (GPU/CUDA Mode).")
            except Exception as e:
                print(f"[WHISPER] GPU init failed: {e}")
                print("[WHISPER] Using CPU mode...")
                model = WhisperModel("base", device="cpu", compute_type="int8")
                data_logger.log_system(datetime.now(timezone.utc).isoformat(), "WHISPER_READY", "ALL", "CPU Model Loaded", "INFO")
                print("[WHISPER] Ready (CPU Mode).")
        
        while True:
            # 1. Check Shutdown
            try:
                if control_queue.get_nowait() == "SHUTDOWN": break
            except Empty: pass
            
            # 2. Get Audio
            try:
                packet = audio_queue.get(timeout=1)

                # 3. Transcribe (with GPU fallback to CPU if needed)
                try:
                    segments, info = model.transcribe(
                        packet['audio_data'],
                        beam_size=1,
                        language="en",
                        condition_on_previous_text=False,
                        vad_filter=True,
                        vad_parameters=dict(min_silence_duration_ms=500)
                    )
                except Exception as transcribe_error:
                    if using_gpu:
                        # GPU transcription failed - switch to CPU
                        print(f"[WHISPER] GPU transcription failed: {transcribe_error}")
                        print("[WHISPER] Switching to CPU mode...")
                        bundled_path = get_bundled_model_path()
                        if bundled_path:
                            model = WhisperModel(bundled_path, device="cpu", compute_type="int8")
                        else:
                            model = WhisperModel("base", device="cpu", compute_type="int8")
                        using_gpu = False
                        # Retry with CPU
                        segments, info = model.transcribe(
                            packet['audio_data'],
                            beam_size=1,
                            language="en",
                            condition_on_previous_text=False,
                            vad_filter=True,
                            vad_parameters=dict(min_silence_duration_ms=500)
                        )
                        print("[WHISPER] Now using CPU mode.")
                    else:
                        raise  # Re-raise if already on CPU

                text = " ".join([s.text for s in segments]).strip()
                
                if text:
                    timestamp_str = datetime.now().strftime("%H:%M:%S")

                    # 1. Always send to the specific channel tab
                    gui_queue.put((packet['channel'], 'TRANSCRIPT', f"[{timestamp_str}] 🗣️ {text}"))

                    # 2. R&D ANALYZER (Unified Filter) - only in non-public builds
                    if ANALYZER_AVAILABLE and rnd_analyzer:
                        insights = rnd_analyzer.analyze_message(packet['channel'], "STREAM_AUDIO", text, timestamp_str)

                        if insights:
                            for insight in insights:
                                gui_queue.put(('EXPERIMENT_DATA', 'DATA',
                                               f"[{packet['channel']}] AUDIO_HIT ({insight.insight_type}): {text}"))

                    # 3. Log to CSV (Raw Data)
                    data_logger.log_transcript(
                        datetime.now(timezone.utc).isoformat(), 
                        packet['channel'], text, 
                        packet['chunk_start'], packet['chunk_end']
                    )
                    
                    # 4. AI Trigger Logic (only if AI mode enabled)
                    ai_mode_enabled = bot_state.get('ai_mode_enabled', False) if bot_state else False
                    if ai_mode_enabled and bot_state:
                        state = bot_state.get(packet['channel'])
                        if state and (time.time() - state['last_time'] < 90):
                            ai_work_queue.put({
                                'channel': packet['channel'],
                                'transcript': text,
                                'last_msg': state['last_msg']
                            })
                            
            except Empty: continue
            
    except Exception as e:
        print(f"[WHISPER CRASH] {e}")
        data_logger.log_system(datetime.now(timezone.utc).isoformat(), "WHISPER_CRASH", "ALL", str(e), "CRITICAL")