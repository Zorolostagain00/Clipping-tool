"""
Centralized configuration and environment bootstrap for ClipForge Studio.
Import this module first in any engine file — it injects required PATH entries
and fixes the Windows console encoding.
"""

import os
import sys
import tempfile
import pathlib

# ── Windows console UTF-8 fix ──────────────────────────────────────────────
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── WinGet / Scoop FFmpeg PATH injection ──────────────────────────────────
_EXTRA_PATHS = [
    r"C:\Users\LOQ\AppData\Local\Microsoft\WinGet\Links",
    r"C:\ProgramData\chocolatey\bin",
    r"C:\Program Files\ffmpeg\bin",
    r"C:\ffmpeg\bin",
]
_current_path = os.environ.get("PATH", "")
for _p in _EXTRA_PATHS:
    if os.path.isdir(_p) and _p not in _current_path:
        os.environ["PATH"] = _p + os.pathsep + _current_path
        _current_path = os.environ["PATH"]

# ── Directory layout ───────────────────────────────────────────────────────
# Root of the ClipForge workspace inside the repo
CLIPFORGE_ROOT = pathlib.Path(__file__).parent.parent.resolve()
REPO_ROOT      = CLIPFORGE_ROOT.parent

# Persistent application data (models, DB, config)
APP_DATA_DIR   = CLIPFORGE_ROOT / "data"
MODEL_CACHE_DIR = APP_DATA_DIR / "models"
DB_PATH        = APP_DATA_DIR / "clipforge.db"

# Output for finished clips
OUTPUT_DIR     = REPO_ROOT / "output" / "clips"

# Temp workspace root — lives in OS temp, cleared on session finalize
TEMP_ROOT      = pathlib.Path(tempfile.gettempdir()) / "ClipForge" / "sessions"

# Legacy transcript cache (reuse from existing clipper.py)
TRANSCRIPT_CACHE_DIR = REPO_ROOT / "output" / "logs"

# ── Ensure directories exist ───────────────────────────────────────────────
for _d in [APP_DATA_DIR, MODEL_CACHE_DIR, OUTPUT_DIR, TEMP_ROOT, TRANSCRIPT_CACHE_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Default processing config ──────────────────────────────────────────────
DEFAULT_WHISPER_MODEL  = "base"       # tiny | base | small | medium | large-v3
DEFAULT_LANGUAGE       = None         # None = auto-detect
DEFAULT_MIN_DURATION   = 20.0         # seconds
DEFAULT_MAX_DURATION   = 120.0        # seconds
DEFAULT_WINDOW_SIZE    = 60.0         # sliding window width
DEFAULT_WINDOW_STEP    = 20.0         # sliding window step
DEFAULT_MIN_SCORE      = 0.0          # 0..1

# API server defaults
API_HOST = "127.0.0.1"
API_PORT = 8765          # avoid clash with Streamlit 8501

# ── Helpers ────────────────────────────────────────────────────────────────
def ffmpeg_path() -> str:
    """Return the absolute path to the ffmpeg binary."""
    import shutil
    path = shutil.which("ffmpeg")
    if path:
        return path
    raise EnvironmentError(
        "ffmpeg not found in PATH. Install via: winget install Gyan.FFmpeg"
    )


def ffprobe_path() -> str:
    """Return the absolute path to the ffprobe binary."""
    import shutil
    path = shutil.which("ffprobe")
    if path:
        return path
    raise EnvironmentError(
        "ffprobe not found in PATH. Install via: winget install Gyan.FFmpeg"
    )


def python_path() -> str:
    """Return path to current Python executable."""
    return sys.executable

