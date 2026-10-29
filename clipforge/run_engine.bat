@echo off
setlocal
echo ===================================================
echo           Starting ClipForge Studio Engine
echo ===================================================

cd /d "%~dp0"
set PYTHONPATH=%~dp0;%PYTHONPATH%

"C:\Users\LOQ\AppData\Local\Programs\Python\Python313\python.exe" -m engine.main

pause
