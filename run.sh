#!/usr/bin/env bash
# Personal YouTube Video Downloader - macOS / Linux Launcher

set -e
cd "$(dirname "$0")"

echo "========================================================"
echo "      Personal YouTube Video Downloader (Local Web UI)"
echo "========================================================"
echo ""

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is not installed or not in your PATH."
    echo "Please install Python 3.10+."
    exit 1
fi

# 2. Virtual Environment
if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment (.venv)..."
    python3 -m venv .venv
fi

# 3. Dependencies
echo "[*] Ensuring required packages are installed..."
.venv/bin/pip install -r requirements.txt --quiet

# 4. Check FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo ""
    echo "⚠️  [WARNING] FFmpeg is not found in your PATH!"
    echo "FFmpeg is needed to merge video + audio tracks and export MP3."
    echo "  - macOS: brew install ffmpeg"
    echo "  - Linux: sudo apt update && sudo apt install ffmpeg"
    echo ""
else
    echo "[*] FFmpeg: Detected and ready."
fi

echo ""
echo "========================================================"
echo "  Starting local server at http://localhost:5000"
echo "  Press Ctrl + C to stop the server."
echo ""
echo "  💡 TIP: To update yt-dlp anytime YouTube changes:"
echo "     .venv/bin/pip install -U yt-dlp"
echo "========================================================"
echo ""

# Open browser
if command -v open &> /dev/null; then
    (sleep 1.2 && open http://127.0.0.1:5000) &
elif command -v xdg-open &> /dev/null; then
    (sleep 1.2 && xdg-open http://127.0.0.1:5000) &
fi

exec .venv/bin/python app.py
