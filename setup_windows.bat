@echo off
title AI Viral Clipping System - Setup
color 0A
echo ============================================================
echo   AI VIRAL CLIPPING SYSTEM - Windows Setup
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.9+ from python.org
    echo         Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [OK] Python found:
python --version

:: Upgrade pip
echo.
echo [1/5] Upgrading pip...
python -m pip install --upgrade pip

:: Install PyTorch (CPU)
echo.
echo [2/5] Installing PyTorch (CPU version)...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

:: Install Whisper
echo.
echo [3/5] Installing OpenAI Whisper...
pip install openai-whisper

:: Install other dependencies
echo.
echo [4/5] Installing other dependencies...
pip install ffmpeg-python tqdm colorama rich numpy

:: Check FFmpeg
echo.
echo [5/5] Checking FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] FFmpeg not found in PATH.
    echo.
    echo Please install FFmpeg:
    echo   Option A: winget install Gyan.FFmpeg
    echo   Option B: Download from https://ffmpeg.org/download.html
    echo             Extract and add bin/ folder to your PATH.
    echo.
) else (
    echo [OK] FFmpeg found!
)

:: Create directories
echo.
echo Creating folder structure...
mkdir input 2>nul
mkdir output\clips 2>nul
mkdir output\logs 2>nul
mkdir models 2>nul

echo.
echo ============================================================
echo   Setup Complete!
echo ============================================================
echo.
echo HOW TO USE:
echo   1. Put your video in the input\ folder
echo   2. Run: python clipper.py input\your_video.mp4
echo   3. Clips will appear in output\clips\
echo.
echo QUICK START:
echo   python clipper.py input\video.mp4 --dry-run
echo   (Lists all clips without exporting - fast preview)
echo.
pause
