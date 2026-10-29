#!/usr/bin/env python3
"""
AI Viral Clipper — Interactive Launcher
========================================
The main interactive home screen for the clipping system.
Lets users choose between local file mode and YouTube URL mode.

Run: python launcher.py
"""

import os
import sys
import time
import subprocess
from pathlib import Path


# ============================================================
#  COLOUR HELPERS (works without any extra package)
# ============================================================

class C:
    """ANSI colour codes (no external dependency)."""
    try:
        # Enable on Windows
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.SetConsoleMode(kernel.GetStdHandle(-11), 7)
        COLOUR = True
    except Exception:
        COLOUR = False

    RESET   = "\033[0m"   if COLOUR else ""
    BOLD    = "\033[1m"   if COLOUR else ""
    DIM     = "\033[2m"   if COLOUR else ""
    CYAN    = "\033[96m"  if COLOUR else ""
    GREEN   = "\033[92m"  if COLOUR else ""
    YELLOW  = "\033[93m"  if COLOUR else ""
    RED     = "\033[91m"  if COLOUR else ""
    MAGENTA = "\033[95m"  if COLOUR else ""
    WHITE   = "\033[97m"  if COLOUR else ""


def cprint(text: str, colour: str = "", bold: bool = False):
    prefix = (C.BOLD if bold else "") + colour
    print(f"{prefix}{text}{C.RESET}")


def clear():
    os.system("cls" if os.name == "nt" else "clear")


# ============================================================
#  BANNER
# ============================================================

BANNER = r"""
  ╔═══════════════════════════════════════════════════════════╗
  ║    🎬  ULTIMATE AI VIRAL CLIPPING SYSTEM                 ║
  ║        Finds EVERY funny & engaging moment               ║
  ║        100% local · Free · No API keys                   ║
  ╚═══════════════════════════════════════════════════════════╝
"""

def print_banner():
    cprint(BANNER, C.CYAN, bold=True)


# ============================================================
#  MENU
# ============================================================

def print_menu():
    cprint("  ┌─────────────────────────────────────────────┐", C.WHITE)
    cprint("  │  Choose your video source:                  │", C.WHITE)
    cprint("  │                                             │", C.WHITE)
    cprint("  │   1 › YouTube URL  (paste link, auto-clip)  │", C.GREEN)
    cprint("  │   2 › Local File   (video already on PC)    │", C.YELLOW)
    cprint("  │   3 › Batch Mode   (all videos in input\\)   │", C.CYAN)
    cprint("  │   4 › Check System (verify dependencies)    │", C.WHITE)
    cprint("  │   Q › Quit                                  │", C.DIM)
    cprint("  └─────────────────────────────────────────────┘", C.WHITE)
    print()


# ============================================================
#  YOUTUBE URL FLOW
# ============================================================

def youtube_url_section():
    clear()
    print_banner()
    cprint("  ━━━━  YouTube URL → AI Clips  ━━━━\n", C.GREEN, bold=True)

    print("  Paste a YouTube video URL below.")
    print("  Supported formats:")
    cprint("    • https://www.youtube.com/watch?v=XXXXXXXXXXX", C.DIM)
    cprint("    • https://youtu.be/XXXXXXXXXXX", C.DIM)
    cprint("    • https://www.youtube.com/shorts/XXXXXXXXXXX\n", C.DIM)

    cprint("  LEGAL NOTICE:", C.YELLOW, bold=True)
    cprint("  Only use this tool on videos you own or have explicit", C.YELLOW)
    cprint("  permission to process. Downloading copyrighted content", C.YELLOW)
    cprint("  without permission may violate YouTube's Terms of Service\n", C.YELLOW)
    cprint("  and applicable copyright law.\n", C.YELLOW)

    url = input("  Paste YouTube URL: ").strip()

    if not url:
        cprint("\n  No URL entered. Returning to menu.\n", C.RED)
        time.sleep(1.5)
        return

    # Basic local validation before calling yt-dlp
    try:
        from youtube_downloader import validate_youtube_url
        val = validate_youtube_url(url)
        if not val["valid"]:
            cprint(f"\n  Invalid URL: {val['error']}\n", C.RED)
            input("  Press Enter to return to menu...")
            return
        cprint(f"\n  Valid YouTube URL detected (ID: {val['video_id']})", C.GREEN)
    except ImportError:
        cprint("\n  Warning: youtube_downloader.py not found — skipping local validation.", C.YELLOW)

    print()

    # Model selection
    cprint("  Whisper Model:", C.WHITE, bold=True)
    print("    1) tiny   — Fastest,  lower accuracy")
    cprint("    2) base   — Default, good balance  [recommended]", C.GREEN)
    print("    3) small  — Better accuracy, ~2× slower")
    print("    4) medium — Best accuracy, ~4× slower")
    print()
    model_choice = input("  Choose model [1-4, Enter = base]: ").strip()
    model_map = {"1": "tiny", "2": "base", "3": "small", "4": "medium", "": "base"}
    model = model_map.get(model_choice, "base")
    cprint(f"  Using model: {model}", C.CYAN)

    # Max clips
    print()
    max_clips_str = input("  Max clips to export [1-20, Enter = 10]: ").strip()
    try:
        max_clips = int(max_clips_str) if max_clips_str else 10
        max_clips = max(1, min(20, max_clips))
    except ValueError:
        max_clips = 10
    cprint(f"  Max clips: {max_clips}", C.CYAN)

    # Clip duration
    print()
    cprint("  Clip Duration Style:", C.WHITE, bold=True)
    print("    1) Shorts/Reels  20–60s")
    cprint("    2) Standard      60–120s  [recommended]", C.GREEN)
    print("    3) Long          90–180s")
    dur_choice = input("  Choose [1-3, Enter = 2]: ").strip()
    dur_map = {
        "1": (20, 60), "2": (60, 120), "3": (90, 180), "": (60, 120)
    }
    min_dur, max_dur = dur_map.get(dur_choice, (60, 120))

    # Dry run?
    print()
    dry_run = input("  Dry run? (analyse only, no export) [y/N]: ").strip().lower() == "y"

    # Confirm
    print()
    cprint("  ─── Summary ─────────────────────────────────", C.DIM)
    print(f"  URL:       {url[:70]}")
    print(f"  Model:     {model}")
    print(f"  Max clips: {max_clips}")
    print(f"  Duration:  {min_dur}s–{max_dur}s per clip")
    print(f"  Dry run:   {dry_run}")
    cprint("  ─────────────────────────────────────────────\n", C.DIM)

    confirm = input("  Proceed? [Y/n]: ").strip().lower()
    if confirm == "n":
        print("  Cancelled.\n")
        return

    print()

    # Build command and run
    cmd = [
        sys.executable, "yt_to_clips.py",
        url,
        "--model", model,
        "--max-clips", str(max_clips),
        "--min-duration", str(min_dur),
        "--max-duration", str(max_dur),
    ]
    if dry_run:
        cmd.append("--dry-run")

    print("  Starting pipeline...\n")
    result = subprocess.run(cmd)

    print()
    if result.returncode == 0:
        cprint("  Pipeline completed successfully!", C.GREEN, bold=True)
    else:
        cprint("  Pipeline finished with errors. See output above.", C.RED)

    input("\n  Press Enter to return to menu...")


# ============================================================
#  LOCAL FILE FLOW
# ============================================================

def local_file_section():
    clear()
    print_banner()
    cprint("  ━━━━  Local File → AI Clips  ━━━━\n", C.YELLOW, bold=True)

    # Show files in input/
    input_dir = Path("input")
    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}
    videos = sorted([
        f for f in input_dir.iterdir()
        if f.suffix.lower() in video_exts and not f.name.startswith(".")
    ]) if input_dir.exists() else []

    if videos:
        cprint("  Videos in input\\ folder:", C.WHITE, bold=True)
        for i, v in enumerate(videos, 1):
            size_mb = v.stat().st_size / (1024 * 1024)
            print(f"    {i:>2}. {v.name}  ({size_mb:.1f} MB)")
        print()
        choice = input("  Enter number or full path: ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(videos):
                video_path = str(videos[idx])
            else:
                video_path = choice
        except ValueError:
            video_path = choice
    else:
        cprint("  No videos found in input\\ folder.", C.YELLOW)
        print()
        video_path = input("  Enter full path to video file: ").strip()

    if not video_path or not Path(video_path).exists():
        cprint(f"\n  File not found: {video_path}\n", C.RED)
        input("  Press Enter to return...")
        return

    cprint(f"\n  Selected: {Path(video_path).name}", C.GREEN)

    # Options
    print()
    model_choice = input("  Whisper model [tiny/base/small/medium, Enter=base]: ").strip()
    model = model_choice if model_choice in ["tiny", "base", "small", "medium"] else "base"

    dry_run = input("  Dry run? (no export) [y/N]: ").strip().lower() == "y"

    max_clips_str = input("  Max clips [Enter = unlimited]: ").strip()
    max_clips_arg = ["--max-clips", max_clips_str] if max_clips_str.isdigit() else []

    print()

    cmd = [
        sys.executable, "clipper.py",
        video_path,
        "--model", model,
    ] + max_clips_arg
    if dry_run:
        cmd.append("--dry-run")

    print("  Starting...\n")
    result = subprocess.run(cmd)

    print()
    cprint(("  Done!" if result.returncode == 0 else "  Finished with errors."),
           C.GREEN if result.returncode == 0 else C.RED, bold=True)
    input("\n  Press Enter to return to menu...")


# ============================================================
#  BATCH MODE
# ============================================================

def batch_section():
    clear()
    print_banner()
    cprint("  ━━━━  Batch Mode  ━━━━\n", C.CYAN, bold=True)

    model_choice = input("  Whisper model [tiny/base/small/medium, Enter=base]: ").strip()
    model = model_choice if model_choice in ["tiny", "base", "small", "medium"] else "base"
    dry_run = input("  Dry run? [y/N]: ").strip().lower() == "y"

    cmd = [sys.executable, "batch_processor.py", "--model", model]
    if dry_run:
        cmd.append("--dry-run")

    print("\n  Starting batch...\n")
    subprocess.run(cmd)
    input("\n  Press Enter to return to menu...")


# ============================================================
#  SYSTEM CHECK
# ============================================================

def check_section():
    clear()
    print_banner()
    cprint("  ━━━━  System Dependency Check  ━━━━\n", C.WHITE, bold=True)
    subprocess.run([sys.executable, "check_system.py"])
    print()
    input("  Press Enter to return to menu...")


# ============================================================
#  MAIN LOOP
# ============================================================

def main():
    while True:
        clear()
        print_banner()
        print_menu()

        choice = input("  Your choice: ").strip().lower()

        if choice == "1":
            youtube_url_section()
        elif choice == "2":
            local_file_section()
        elif choice == "3":
            batch_section()
        elif choice == "4":
            check_section()
        elif choice in ("q", "quit", "exit"):
            clear()
            cprint("\n  Goodbye!\n", C.CYAN, bold=True)
            sys.exit(0)
        else:
            cprint("\n  Invalid choice. Press Enter to try again.", C.RED)
            input()


if __name__ == "__main__":
    main()
