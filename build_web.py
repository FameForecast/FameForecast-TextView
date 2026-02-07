# build_web.py
"""
Build script for creating the FameForecastTextView WEB executable.
Uses Flask + WebSocket instead of tkinter.

Usage:
    python build_web.py
    python build_web.py --debug  (with console window)

Requirements:
    pip install pyinstaller
"""

import subprocess
import sys
import shutil
import os
from pathlib import Path

# Path to cached faster-whisper base model
WHISPER_MODEL_CACHE = Path(os.path.expanduser("~")) / ".cache" / "huggingface" / "hub" / "models--Systran--faster-whisper-base" / "snapshots"

# FFmpeg location
FFMPEG_PATH = Path("C:/ffmpeg/bin")

# Packages to EXCLUDE - these are not needed for the public build
EXCLUDE_MODULES = [
    # R&D modules (CRITICAL: config.py contains private credentials!)
    "twitch_chat_monitor.ai",
    "twitch_chat_monitor.analyzer",
    "twitch_chat_monitor.token_manager",
    "twitch_chat_monitor.config",  # Contains private API keys - NEVER bundle

    # AI/ML frameworks (not needed - we use ctranslate2 via faster_whisper)
    "torch",
    "torchvision",
    "torchaudio",
    "unsloth",
    "bitsandbytes",
    "transformers",
    "tensorflow",
    "keras",

    # Data science (not needed)
    "scipy",
    "pandas",
    "matplotlib",
    "sklearn",
    "scikit-learn",
    "seaborn",
    "plotly",

    # NLP (not needed)
    "spacy",
    "nltk",
    "thinc",
    "langcodes",

    # Database (not needed)
    "sqlalchemy",
    "psycopg2",
    "pymysql",

    # Cloud/API (not needed)
    "google.cloud",
    "google.api_core",
    "grpc",
    "grpcio",
    "boto3",
    "botocore",

    # Video/Media (not needed - we use streamlink separately)
    "cv2",
    "opencv",
    "yt_dlp",
    "moviepy",

    # Tkinter (not needed - we use web interface)
    "tkinter",
    "_tkinter",
    "PIL._tkinter_finder",

    # Other heavy packages
    "pyarrow",
    "sympy",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "py",
]


def ensure_whisper_model():
    """Download Whisper model if not already cached"""
    print("\nChecking Whisper model...")

    if WHISPER_MODEL_CACHE.exists() and list(WHISPER_MODEL_CACHE.iterdir()):
        print("  Whisper model already cached.")
        return True

    print("  Downloading Whisper model (this may take a minute)...")
    try:
        from faster_whisper import WhisperModel
        # This will download the model to cache
        model = WhisperModel("base", device="cpu", compute_type="int8")
        del model
        print("  Whisper model downloaded successfully.")
        return True
    except Exception as e:
        print(f"  ERROR downloading Whisper model: {e}")
        return False


def copy_whisper_model(dist_folder):
    """Copy the faster-whisper base model to the dist folder for offline use"""
    print("\nCopying Whisper model for offline use...")

    if not WHISPER_MODEL_CACHE.exists():
        print("WARNING: Whisper model cache not found.")
        print("Attempting to download...")
        if not ensure_whisper_model():
            return False

    snapshots = list(WHISPER_MODEL_CACHE.iterdir())
    if not snapshots:
        print("WARNING: No model snapshots found in cache.")
        return False

    model_src = snapshots[0]
    model_dest = dist_folder / "models" / "faster-whisper-base"

    required_files = ["model.bin", "config.json", "tokenizer.json", "vocabulary.txt"]

    for f in required_files:
        if not (model_src / f).exists():
            print(f"WARNING: Missing model file: {f}")
            return False

    model_dest.mkdir(parents=True, exist_ok=True)

    for f in required_files:
        src_file = model_src / f
        dst_file = model_dest / f
        print(f"  Copying {f}...")
        shutil.copy2(src_file, dst_file)

    print(f"Whisper model copied to: {model_dest}")
    return True


def copy_ffmpeg(dist_folder):
    """Copy FFmpeg binaries for audio processing"""
    print("\nCopying FFmpeg binaries...")

    if not FFMPEG_PATH.exists():
        print(f"WARNING: FFmpeg not found at {FFMPEG_PATH}")
        return False

    # Copy directly to dist folder (same folder as exe) so get_ffmpeg_path() finds it
    for exe in ["ffmpeg.exe", "ffprobe.exe"]:
        src = FFMPEG_PATH / exe
        if src.exists():
            dst = dist_folder / exe
            print(f"  Copying {exe}...")
            shutil.copy2(src, dst)
        else:
            print(f"  WARNING: {exe} not found")

    print(f"FFmpeg copied to: {dist_folder}")
    return True


def copy_web_assets(dist_folder):
    """Copy web templates and static files"""
    print("\nCopying web assets...")

    src_dir = Path(__file__).parent.parent / "twitch_chat_monitor" / "web"

    # Copy templates
    templates_src = src_dir / "templates"
    templates_dst = dist_folder / "twitch_chat_monitor" / "web" / "templates"
    if templates_src.exists():
        shutil.copytree(templates_src, templates_dst, dirs_exist_ok=True)
        print(f"  Copied templates to {templates_dst}")

    # Copy static files
    static_src = src_dir / "static"
    static_dst = dist_folder / "twitch_chat_monitor" / "web" / "static"
    if static_src.exists():
        shutil.copytree(static_src, static_dst, dirs_exist_ok=True)
        print(f"  Copied static files to {static_dst}")

    return True


def build(debug=False):
    print("=" * 50)
    print("Building FameForecastTextView (Web Version)")
    print("=" * 50)

    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Ensure Whisper model is downloaded BEFORE building
    print("\nPre-build: Ensuring all models are cached...")
    ensure_whisper_model()

    name = "FameForecastTextView_debug" if debug else "FameForecastTextView"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--console" if debug else "--windowed",
        "--name", name,
        "-y",
    ]

    # Add all exclusions
    for module in EXCLUDE_MODULES:
        cmd.extend(["--exclude-module", module])

    # Add parent directory to paths
    parent_dir = str(Path(__file__).parent.parent)
    cmd.extend(["--paths", parent_dir])

    # Hidden imports for web version
    cmd.extend([
        # Flask and SocketIO
        "--hidden-import", "flask",
        "--hidden-import", "flask_socketio",
        "--hidden-import", "socketio",
        "--hidden-import", "engineio",
        "--hidden-import", "engineio.async_drivers.threading",
        "--hidden-import", "engineio.async_drivers",
        "--hidden-import", "jinja2",
        "--hidden-import", "werkzeug",
        "--hidden-import", "werkzeug.serving",
        "--hidden-import", "werkzeug.debug",
        "--collect-submodules", "flask",
        "--collect-submodules", "flask_socketio",
        "--collect-submodules", "socketio",
        "--collect-submodules", "engineio",
        "--collect-submodules", "jinja2",

        # Whisper and audio
        "--hidden-import", "faster_whisper",
        "--hidden-import", "ctranslate2",
        "--hidden-import", "av",
        "--hidden-import", "sounddevice",
        "--collect-submodules", "faster_whisper",
        "--collect-submodules", "ctranslate2",
        "--collect-data", "faster_whisper",

        # Streamlink plugins
        "--hidden-import", "streamlink",
        "--hidden-import", "streamlink.plugins.twitch",
        "--hidden-import", "streamlink.plugins",
        "--collect-submodules", "streamlink",
        "--collect-submodules", "streamlink.plugins",

        # Requests and networking
        "--hidden-import", "requests",
        "--hidden-import", "urllib3",
        "--hidden-import", "certifi",
        "--collect-data", "certifi",

        # Web templates and static files
        "--add-data", f"{parent_dir}/twitch_chat_monitor/web/templates;twitch_chat_monitor/web/templates",
        "--add-data", f"{parent_dir}/twitch_chat_monitor/web/static;twitch_chat_monitor/web/static",
    ])

    # Entry point - the web version
    cmd.append("twitch_monitor_web.py")

    print("\nExcluding these modules to reduce size:")
    for m in EXCLUDE_MODULES[:10]:
        print(f"  - {m}")
    print(f"  ... and {len(EXCLUDE_MODULES) - 10} more")

    print(f"\nRunning PyInstaller...")
    result = subprocess.run(cmd)

    if result.returncode == 0:
        dist_path = Path(f"dist/{name}")

        # Copy Whisper model
        if dist_path.exists():
            model_copied = copy_whisper_model(dist_path)
            if not model_copied:
                print("\nWARNING: Whisper model not bundled. App will download on first run.")

        # Copy FFmpeg
        if dist_path.exists():
            ffmpeg_copied = copy_ffmpeg(dist_path)
            if not ffmpeg_copied:
                print("\nWARNING: FFmpeg not bundled. Audio transcription may not work.")

        # Get folder size
        if dist_path.exists():
            total_size = sum(f.stat().st_size for f in dist_path.rglob('*') if f.is_file())
            size_mb = total_size / (1024 * 1024)
            size_str = f"{size_mb:.1f} MB"
        else:
            size_str = "unknown"

        print("\n" + "=" * 50)
        print("BUILD SUCCESSFUL!")
        print("=" * 50)
        print(f"\nOutput folder: dist/{name}/")
        print(f"Size: {size_str}")
        print(f"Run: dist/{name}/{name}.exe")
        print("\nThe app will open a browser to http://localhost:8080")
        print("\nTo distribute:")
        print(f"  1. Zip the 'dist/{name}' folder")
        print(f"  2. Users extract and run '{name}.exe'")
        print("  3. Browser opens automatically")
    else:
        print("\n" + "=" * 50)
        print("BUILD FAILED")
        print("=" * 50)
        print("Check the error messages above.")

    return result.returncode


if __name__ == "__main__":
    debug = len(sys.argv) > 1 and sys.argv[1] == "--debug"
    sys.exit(build(debug=debug))
