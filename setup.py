#!/usr/bin/env python3
"""
AI Viral Clipping System — Setup Script
Checks environment, installs dependencies, creates folder structure.
Works on Windows with Python 3.9+
"""

import sys
import os
import subprocess
import platform
from pathlib import Path


# ── ANSI colours (work in modern Windows terminals) ──────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


def ok(msg):   print(f"  {GREEN}[OK]{RESET}    {msg}")
def warn(msg): print(f"  {YELLOW}[WARN]{RESET}  {msg}")
def err(msg):  print(f"  {RED}[ERROR]{RESET} {msg}")
def info(msg): print(f"  {CYAN}[INFO]{RESET}  {msg}")


def banner():
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  AI Viral Clipping System — Setup{RESET}")
    print(f"{'='*60}\n")


# ── 1. Python version check ──────────────────────────────────────────────────
def check_python():
    info("Checking Python version...")
    major, minor = sys.version_info.major, sys.version_info.minor
    version_str = f"{major}.{minor}.{sys.version_info.micro}"
    if major < 3 or (major == 3 and minor < 9):
        err(f"Python 3.9+ required. You have {version_str}.")
        err("Download the latest Python from https://python.org")
        sys.exit(1)
    ok(f"Python {version_str} — good to go.")


# ── 2. pip check ─────────────────────────────────────────────────────────────
def check_pip():
    info("Checking pip...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        err("pip not found. Please reinstall Python with pip enabled.")
        sys.exit(1)
    ok(f"pip available: {result.stdout.strip().split()[1]}")


# ── 3. Install packages ───────────────────────────────────────────────────────
def pip_install(packages, extra_args=None):
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade"] + (extra_args or []) + packages
    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True)
    return result.returncode == 0


def install_packages():
    info("Upgrading pip...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
                   capture_output=True)

    print()
    info("Installing PyTorch (CPU build) ...")
    success = pip_install(
        ["torch", "torchvision", "torchaudio"],
        extra_args=["--index-url", "https://download.pytorch.org/whl/cpu"]
    )
    if success:
        ok("PyTorch installed.")
    else:
        warn("PyTorch install had issues — continuing anyway.")

    print()
    info("Installing OpenAI Whisper...")
    success = pip_install(["openai-whisper"])
    if success:
        ok("openai-whisper installed.")
    else:
        warn("openai-whisper install had issues.")

    print()
    info("Installing supporting packages...")
    deps = ["ffmpeg-python", "tqdm", "colorama", "rich", "numpy"]
    success = pip_install(deps)
    if success:
        ok(f"Installed: {', '.join(deps)}")
    else:
        warn("Some supporting packages may not have installed correctly.")


# ── 4. FFmpeg check / download hint ──────────────────────────────────────────
def check_ffmpeg():
    info("Checking for FFmpeg...")
    result = subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, text=True
    )
    if result.returncode == 0:
        first_line = result.stdout.splitlines()[0] if result.stdout else "unknown"
        ok(f"FFmpeg found: {first_line}")
        return True

    warn("FFmpeg not found in PATH.")
    print()
    print("  FFmpeg is required for video cutting.  Install it with ONE of:")
    print()
    print("    Option A (recommended — winget):")
    print("      winget install Gyan.FFmpeg")
    print()
    print("    Option B (manual):")
    print("      1. Download from  https://ffmpeg.org/download.html")
    print("      2. Extract the archive")
    print("      3. Add the 'bin' subfolder to your system PATH")
    print()

    # Try winget automatically
    winget_result = subprocess.run(
        ["winget", "install", "--id", "Gyan.FFmpeg", "-e", "--silent"],
        capture_output=True, text=True
    )
    if winget_result.returncode == 0:
        ok("FFmpeg installed via winget. Restart your terminal to use it.")
    else:
        warn("Automatic install via winget failed or was skipped.")
        warn("Please install FFmpeg manually using the options above.")

    return False


# ── 5. Create directory structure ─────────────────────────────────────────────
REQUIRED_DIRS = [
    "input",
    "output/clips",
    "output/logs",
    "models",
]

def create_directories():
    info("Creating directory structure...")
    base = Path(__file__).parent
    for rel_path in REQUIRED_DIRS:
        target = base / rel_path
        target.mkdir(parents=True, exist_ok=True)
        gitkeep = target / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
        ok(f"  {rel_path}/")


# ── 6. Validate imports ───────────────────────────────────────────────────────
def validate_installation():
    info("Validating installed packages...")
    missing = []

    packages_to_check = [
        ("torch",     "PyTorch"),
        ("whisper",   "OpenAI Whisper"),
        ("ffmpeg",    "ffmpeg-python"),
        ("tqdm",      "tqdm"),
        ("colorama",  "colorama"),
        ("rich",      "rich"),
        ("numpy",     "numpy"),
    ]

    for module, display in packages_to_check:
        try:
            __import__(module)
            ok(f"{display}")
        except ImportError:
            warn(f"{display} — NOT importable (may need a restart)")
            missing.append(display)

    return missing


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    banner()

    # Platform notice
    if platform.system() != "Windows":
        warn("This setup script is designed for Windows. Proceeding anyway…")

    check_python()
    print()
    check_pip()
    print()
    install_packages()
    print()
    check_ffmpeg()
    print()
    create_directories()
    print()
    missing = validate_installation()
    print()

    print(f"{BOLD}{'='*60}{RESET}")
    if not missing:
        print(f"{GREEN}{BOLD}  ✅  Setup complete! Everything looks good.{RESET}")
    else:
        print(f"{YELLOW}{BOLD}  ⚠️   Setup finished with warnings.{RESET}")
        print(f"  The following packages could not be imported:")
        for m in missing:
            print(f"    • {m}")
        print("  Try closing and reopening your terminal, then run again.")

    print(f"{'='*60}")
    print()
    print("  HOW TO USE:")
    print("    1. Put your video in the  input/  folder")
    print("    2. Run:  python clipper.py input/your_video.mp4")
    print("    3. Clips appear in  output/clips/")
    print()
    print("  QUICK PREVIEW (no export):")
    print("    python clipper.py input/your_video.mp4 --dry-run")
    print()


if __name__ == "__main__":
    main()
