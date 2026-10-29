#!/usr/bin/env python3
"""
System Check — Verifies all dependencies are properly installed.
Run this before using the clipping system.

Usage: python check_system.py
"""

import os
import sys
import subprocess
import importlib
import shutil
from pathlib import Path

# Fix Windows console UTF-8 encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Ensure WinGet/FFmpeg paths are in PATH if available
winget_links = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links"
if winget_links.exists() and str(winget_links) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{winget_links};{os.environ.get('PATH', '')}"


def check(name: str, fn, fix: str = None) -> bool:
    """Run a single check and print result."""
    try:
        result = fn()
        print(f"  ✅  {name}: {result}")
        return True
    except Exception as e:
        print(f"  ❌  {name}: FAILED — {e}")
        if fix:
            print(f"       Fix: {fix}")
        return False


def check_python_version():
    v = sys.version_info
    if v.major < 3 or (v.major == 3 and v.minor < 9):
        raise RuntimeError(f"Python 3.9+ required, got {v.major}.{v.minor}")
    return f"{v.major}.{v.minor}.{v.micro}"


def check_module(module_name: str):
    m = importlib.import_module(module_name)
    version = getattr(m, '__version__', 'installed')
    return version


def check_ffmpeg():
    result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("ffmpeg not found in PATH")
    first_line = result.stdout.split('\n')[0]
    return first_line.split(' ')[2] if len(first_line.split(' ')) > 2 else "found"


def check_ffprobe():
    result = subprocess.run(['ffprobe', '-version'], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("ffprobe not found in PATH")
    first_line = result.stdout.split('\n')[0]
    return first_line.split(' ')[2] if len(first_line.split(' ')) > 2 else "found"


def check_whisper_model(model_name: str = "base"):
    """Check if whisper can load a model."""
    import whisper
    # Don't actually download, just check if it can be loaded from cache
    import os
    cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "whisper")
    model_files = list(Path(cache_dir).glob(f"{model_name}*.pt")) if Path(cache_dir).exists() else []
    if model_files:
        return f"cached at {cache_dir}"
    return "will download on first use"


def check_directories():
    dirs = ['input', 'output/clips', 'output/logs', 'models']
    missing = [d for d in dirs if not Path(d).exists()]
    if missing:
        # Create them
        for d in missing:
            Path(d).mkdir(parents=True, exist_ok=True)
        return f"created: {', '.join(missing)}"
    return "all present"


def check_disk_space():
    import shutil
    total, used, free = shutil.disk_usage(".")
    free_gb = free / (1024**3)
    if free_gb < 1:
        raise RuntimeError(f"Only {free_gb:.2f}GB free — need at least 1GB")
    return f"{free_gb:.1f}GB free"


def main():
    print("\n" + "="*60)
    print("  🔍 AI VIRAL CLIPPING SYSTEM — DEPENDENCY CHECK")
    print("="*60 + "\n")
    
    all_ok = True
    
    # Core requirements
    print("  Core Requirements:")
    print("  " + "─"*50)
    
    all_ok &= check("Python version", check_python_version,
                    "Install Python 3.9+ from python.org")
    
    all_ok &= check("FFmpeg", check_ffmpeg,
                    "winget install Gyan.FFmpeg  (or download from ffmpeg.org)")
    
    all_ok &= check("ffprobe", check_ffprobe,
                    "FFprobe is included with FFmpeg. Check your PATH.")
    
    print()
    print("  Python Packages:")
    print("  " + "─"*50)
    
    packages = [
        ("torch", "torch", "pip install torch --index-url https://download.pytorch.org/whl/cpu"),
        ("whisper", "whisper", "pip install openai-whisper"),
        ("numpy", "numpy", "pip install numpy"),
        ("tqdm", "tqdm", "pip install tqdm"),
    ]
    
    for display_name, module_name, fix in packages:
        all_ok &= check(display_name, lambda m=module_name: check_module(m), fix)
    
    print()
    print("  System:")
    print("  " + "─"*50)
    
    check("Disk space", check_disk_space)
    check("Directories", check_directories)
    
    # Optional checks
    print()
    print("  Optional:")
    print("  " + "─"*50)
    
    try:
        check("Whisper base model", lambda: check_whisper_model("base"))
    except Exception:
        pass
    
    # GPU check
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
            print(f"  ✅  CUDA GPU: {gpu_name} (transcription will be MUCH faster!)")
        else:
            print(f"  ℹ️   CUDA GPU: Not available (CPU mode — slower but works fine)")
    except Exception:
        pass
    
    print()
    print("=" * 60)
    
    if all_ok:
        print("  ✅  ALL CHECKS PASSED — System is ready!")
        print()
        print("  Quick Start:")
        print("    1. Put your video in the input\\ folder")
        print("    2. Run: python clipper.py input\\your_video.mp4")
        print("    3. Use --dry-run first for a quick preview")
    else:
        print("  ⚠️   SOME CHECKS FAILED — See fixes above")
        print()
        print("  Quick Fix:")
        print("    1. Install FFmpeg: winget install Gyan.FFmpeg")
        print("    2. Run setup:      setup_windows.bat")
        print("    3. Re-run check:   python check_system.py")
    
    print("=" * 60)
    print()
    
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
