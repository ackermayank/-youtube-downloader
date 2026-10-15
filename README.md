# ⚡ Personal YouTube Video Downloader

A lightweight, clean, and local YouTube video & audio downloader running right in your web browser. 

- **100% Free & Private**: Runs locally on your machine.
- **Zero API Keys or Accounts**: No sign-ups, no tracking, no paid limits.
- **Powered by `yt-dlp` & `FFmpeg`**: Get full HD, 2K, 4K, 8K, and 320 kbps MP3s merged cleanly into your `Downloads` folder.

---

## 📋 Features

1. **Simple Web UI**: Clean, modern interface available at `http://localhost:5000`.
2. **Fetch Metadata**: Displays video thumbnail, title, channel name, duration, and view counts before downloading.
3. **Dynamic Quality Selection**: Dropdown lists **only the real resolutions available** for the specific video (Best Available, 4K/2160p, 1440p, 1080p, 720p, 480p, 360p).
4. **Format Choice**:
   - **🎬 MP4 Video**: Downloads best video + best audio and merges them using FFmpeg.
   - **🎵 MP3 Audio**: Extracts audio in crystal clear 320 kbps high fidelity.
5. **Live Progress Tracking**: Real-time progress bar with percentage, download speed (MB/s), file size, and ETA countdown.
6. **Built-in Downloads Folder**: Automatically saves into a `Downloads/` directory inside the project folder, with a 1-click button to open it in your file explorer.
7. **Bonus Features**:
   - Subtitles download (`.srt`) option.
   - High-resolution thumbnail image (`.jpg`) download option.
   - Playlist support (paste a playlist link to fetch and batch download).
8. **Friendly Error Messages**: Clear explanations for invalid links, private videos, age restrictions, and missing tools.

---

## 🪟 Step-by-Step Setup Guide (Windows)

Follow these steps if you are on Windows. No coding experience needed!

### Step 1: Install Python

1. Go to the official Python website: **[https://www.python.org/downloads/](https://www.python.org/downloads/)**
2. Click the yellow button to download the latest **Python 3**.
3. Run the downloaded installer.
4. ⚠️ **VERY IMPORTANT**: On the very first screen of the installer, **check the box at the bottom that says "Add Python to PATH"**. (If you skip this, Windows won't recognize Python).
5. Click **"Install Now"** and finish the setup.

---

### Step 2: Install FFmpeg (Required for 1080p/4K and MP3s)

FFmpeg is the tool that stitches video and audio tracks together.

#### Option A (Easiest — 1 Minute via PowerShell):
1. Press `Win + X` on your keyboard and select **"Terminal"** or **"PowerShell"**.
2. Copy and paste this command and press Enter:
   ```powershell
   winget install Gyan.FFmpeg
   ```
3. Once completed, close the PowerShell window. That's it!

#### Option B (Manual Download):
1. Download the release build `.zip` from **[gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/)** (e.g. `ffmpeg-release-essentials.zip`).
2. Unzip it (for example to `C:\ffmpeg`).
3. Add `C:\ffmpeg\bin` to your Windows Environment Variables (`PATH`).

---

### Step 3: Launch the Downloader!

You don't need to type commands every time:

1. Double-click the file named **`run.bat`** in this project folder.
2. It will automatically:
   - Verify Python and FFmpeg.
   - Set up the virtual environment (`.venv`).
   - Install the required packages (`Flask`, `yt-dlp`, `certifi`).
   - Open your web browser automatically to **`http://localhost:5000`**.

---

## 🍎 macOS & 🐧 Linux Setup

If you are using macOS or Linux:

1. Install FFmpeg:
   - **macOS** (via Homebrew):
     ```bash
     brew install ffmpeg
     ```
   - **Linux** (Ubuntu / Debian):
     ```bash
     sudo apt update && sudo apt install ffmpeg
     ```
2. Double-click or run the launcher script:
   ```bash
   ./run.sh
   ```
   *(Or manually activate virtualenv and run `python3 app.py`)*.

---

## 🔄 Keeping `yt-dlp` Updated (Important Note!)

> [!IMPORTANT]
> YouTube frequently updates its website and streaming protocols. From time to time, an older version of `yt-dlp` may fail to fetch video info or produce a `403 Forbidden` error.

Whenever this happens, simply update `yt-dlp` to the latest version by running:

### Windows:
Open PowerShell in the project folder and run:
```powershell
.venv\Scripts\pip install -U yt-dlp
```

### macOS / Linux:
Open Terminal in the project folder and run:
```bash
.venv/bin/pip install -U yt-dlp
```

---

## 🎯 How to Use

1. **Paste a Link**: Copy a link from YouTube (e.g., `https://www.youtube.com/watch?v=...`) and paste it into the search box.
2. **Fetch Info**: Click **Fetch Info** (or press Enter). The thumbnail, title, channel name, and duration will appear.
3. **Select Format & Quality**:
   - Choose **Video (MP4)** or **Audio Only (MP3)**.
   - If Video is selected, choose your desired resolution (e.g., *1080p*, *720p*, or *Best Available*).
   - Optionally check *Download Subtitles* or *Save Thumbnail*.
4. **Click Download**:
   - Watch the live progress bar update with percent, download speed, and ETA.
   - FFmpeg will automatically merge the video and audio tracks.
5. **Access Your File**:
   - When finished, click **"Open Downloads Folder"** to view your file immediately.
   - All downloaded files are stored safely in the project's `Downloads/` directory.

---

## 📁 Project Structure

```
youtube-downloader/
├── app.py              # Flask server and yt-dlp download manager
├── templates/
│   └── index.html      # Responsive single-page web UI
├── Downloads/          # All downloaded videos, audios, and thumbnails
├── requirements.txt    # Python dependencies
├── run.bat             # 1-click launcher for Windows
├── run.sh              # 1-click launcher for macOS & Linux
└── README.md           # Instructions and documentation
```

---

## 🛠️ Troubleshooting & Common Questions

- **"FFmpeg missing" error**: Make sure you followed Step 2. You can test if it's installed by opening a terminal and running `ffmpeg -version`.
- **"Video unavailable / Private"**: Private videos or videos restricted by copyright/region cannot be downloaded without authenticating with a browser cookie.
- **"Sign in to confirm your age"**: Some age-restricted videos require YouTube account login and cannot be downloaded without session cookies.
- **Port 5000 in use**: If another app is using port 5000, you can edit the last line of `app.py` and change `port=5000` to `port=5050`.

---

## ☁️ Deploying Online for Free (Render.com)

If you want to host this downloader online so you can use it from any phone, laptop, or browser without keeping your computer on:

1. Sign up for free at **[https://render.com](https://render.com)** with your GitHub account.
2. Click **New +** → **Web Service**.
3. Select your repository: **`ackermayank/-youtube-downloader`**.
4. In the settings:
   - **Environment**: Select **Docker** (it will automatically use the included `Dockerfile` with FFmpeg pre-installed).
   - **Plan**: Select **Free**.
5. Click **Create Web Service**.
6. Render will build the container with FFmpeg in ~2 minutes and give you a live URL (e.g. `https://your-downloader.onrender.com`).

