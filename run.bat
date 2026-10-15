@echo off
title YouTube Downloader
setlocal enabledelayedexpansion

echo ========================================================
echo       Personal YouTube Video Downloader
echo ========================================================
echo.

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found on your system!
    echo.
    echo Please install Python 3 from:
    echo   https://www.python.org/downloads/
    echo.
    echo CRITICAL: Ensure you check the box "Add Python to PATH"
    echo during the Python installation wizard.
    echo.
    pause
    exit /b 1
)

:: 2. Check or Create Virtual Environment
if not exist ".venv" (
    echo [*] Creating virtual environment (.venv)...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

:: 3. Install / Verify Dependencies
echo [*] Checking required libraries (Flask, yt-dlp, certifi)...
.venv\Scripts\pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [WARNING] Updating packages...
    .venv\Scripts\pip install -r requirements.txt
)

:: 4. Check FFmpeg
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo ========================================================
    echo [WARNING] FFmpeg is NOT detected in your Windows PATH!
    echo.
    echo FFmpeg is required to merge 1080p/4K video tracks with
    echo audio into MP4, and to extract 320kbps MP3 audio.
    echo.
    echo Quick Fix (run this in PowerShell):
    echo    winget install Gyan.FFmpeg
    echo.
    echo Then restart this launcher.
    echo ========================================================
    echo.
) else (
    echo [*] FFmpeg: Detected and ready!
)

:: 5. Launch Browser & Start Server
echo.
echo ========================================================
echo   Starting local server at http://localhost:5000
echo.
echo   TIP: YouTube changes regularly. If downloads ever break,
echo   simply update yt-dlp by running:
echo      .venv\Scripts\pip install -U yt-dlp
echo ========================================================
echo.

start http://localhost:5000
.venv\Scripts\python app.py

pause
