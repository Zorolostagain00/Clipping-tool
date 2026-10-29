@echo off
setlocal
title ClipForge Studio Launcher

echo ========================================================
echo                 ClipForge Studio
echo     Local-First AI Video Clipping & Editing Studio
echo ========================================================
echo.

cd /d "%~dp0"

echo [1/2] Starting ClipForge Engine on http://127.0.0.1:8765...
start "ClipForge Engine" /min "C:\Users\LOQ\AppData\Local\Programs\Python\Python313\python.exe" -m engine.main

timeout /t 2 /nobreak >nul

echo [2/2] Starting ClipForge UI on http://localhost:5173...
cd clipforge\desktop
start "ClipForge UI" cmd /c "npm run dev"

timeout /t 3 /nobreak >nul

start http://localhost:5173

echo.
echo ClipForge Studio is running!
echo Backend Engine: http://127.0.0.1:8765
echo Web UI:         http://localhost:5173
echo.
pause
