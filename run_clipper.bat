@echo off
title AI Viral Clipping System
color 0B
echo ============================================================
echo   AI VIRAL CLIPPING SYSTEM
echo   Finds EVERY worthwhile moment automatically
echo ============================================================
echo.

:: List videos in input folder
echo Videos in input\ folder:
echo.
dir input\*.mp4 /b 2>nul
dir input\*.mkv /b 2>nul
dir input\*.avi /b 2>nul
dir input\*.mov /b 2>nul
echo.

:: Prompt user
set /p VIDEO_FILE="Enter video filename (e.g., myvideo.mp4): "
set /p MODEL="Whisper model [tiny/base/small/medium] (press Enter for base): "

if "%MODEL%"=="" set MODEL=base

echo.
echo [OPTIONS]
echo   1. Full Run (analyze + export all clips)
echo   2. Dry Run  (analyze only, no export - faster)
echo.
set /p MODE="Choose mode [1/2]: "

echo.
echo Starting analysis...
echo.

if "%MODE%"=="2" (
    python clipper.py "input\%VIDEO_FILE%" --model %MODEL% --dry-run
) else (
    python clipper.py "input\%VIDEO_FILE%" --model %MODEL%
)

echo.
echo Done! Check output\clips\ for your clips.
pause
