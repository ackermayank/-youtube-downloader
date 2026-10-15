"""
Personal YouTube Video Downloader - Backend Application
Powered by Flask, yt-dlp, and FFmpeg.
Runs locally at http://localhost:5000 with zero external APIs, keys, or paid services.
"""

import os
import sys
import shutil
import threading
import time
import uuid
import subprocess
from datetime import datetime

# Ensure SSL certificate resolution works cleanly across macOS, Windows, and Linux
try:
    import certifi
    os.environ.setdefault('SSL_CERT_FILE', certifi.where())
except ImportError:
    pass

from flask import Flask, render_template, request, jsonify, send_from_directory
import yt_dlp

# Initialize Flask application
app = Flask(__name__)

# Configure project directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'Downloads')
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# In-memory dictionary to store active and recent download tasks
tasks = {}
tasks_lock = threading.Lock()


# ============================================================================
# HELPER UTILITIES
# ============================================================================

def check_ffmpeg() -> tuple[bool, str]:
    """Check if ffmpeg is accessible on the system PATH."""
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return True, ffmpeg_path
    return False, ""


def format_bytes(size_bytes: int | float | None) -> str:
    """Format bytes into human-readable strings (e.g. 15.4 MB)."""
    if not size_bytes or size_bytes <= 0:
        return "--"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def format_duration(seconds: int | float | None) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if seconds is None:
        return "Unknown"
    try:
        seconds = int(seconds)
        mins, secs = divmod(seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"
    except (ValueError, TypeError):
        return "Unknown"


def format_speed(speed_bytes: int | float | None) -> str:
    """Format download speed into readable MB/s or KB/s."""
    if not speed_bytes or speed_bytes <= 0:
        return "--"
    return f"{format_bytes(speed_bytes)}/s"


def format_eta(eta_seconds: int | float | None) -> str:
    """Format ETA in seconds to MM:SS."""
    if eta_seconds is None or eta_seconds < 0:
        return "--:--"
    try:
        eta_seconds = int(eta_seconds)
        mins, secs = divmod(eta_seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"
    except (ValueError, TypeError):
        return "--:--"


def parse_friendly_error(error_msg: str) -> str:
    """Translate raw technical errors into clear, friendly guidance."""
    msg = str(error_msg).strip()

    if "ffmpeg is not installed" in msg.lower() or "ffmpeg not found" in msg.lower():
        return (
            "FFmpeg is missing! FFmpeg is needed to merge video & audio or convert to MP3. "
            "Please install FFmpeg and restart the app (see setup guide in README)."
        )
    if "private video" in msg.lower() or "this video is private" in msg.lower():
        return "This video is private and cannot be downloaded without signing in."
    if "video unavailable" in msg.lower() or "has been removed" in msg.lower():
        return "This video is unavailable or has been removed from YouTube."
    if "sign in to confirm your age" in msg.lower():
        return "This video is age-restricted by YouTube and requires logging in."
    if "the playlist does not exist" in msg.lower():
        return "The playlist URL you provided does not exist or has been deleted."
    if "subtitle" in msg.lower() or "caption" in msg.lower():
        return "YouTube's subtitle server timed out. Try unchecking 'Download Subtitles' and downloading again."
    if "connection refused" in msg.lower() or "timed out" in msg.lower() or "network error" in msg.lower() or "incompleteread" in msg.lower():
        return "Network connection error while communicating with YouTube. Please verify your internet connection and try again."
    if "http error 403" in msg.lower():
        return "YouTube rejected the request (403 Forbidden). Updating yt-dlp often fixes this: run 'pip install -U yt-dlp'."
    if "sign in to confirm you're not a bot" in msg.lower() or "bot verification" in msg.lower():
        return "YouTube is requesting a bot verification challenge. Please wait a moment or try another video link."

    # Remove generic technical prefixes for cleaner UI presentation
    cleaned = msg.replace("ERROR:", "").replace("[youtube]", "").strip()
    return cleaned if cleaned else "An unexpected error occurred while processing the request."


def ensure_quicktime_compatible(filepath: str, task_id: str = None) -> str:
    """
    Ensures that the output MP4 file is 100% natively compatible with macOS QuickTime Player,
    Finder spacebar preview, and iOS devices by guaranteeing H.264 video and AAC audio codecs.
    """
    if not filepath or not os.path.exists(filepath) or not filepath.lower().endswith('.mp4'):
        return filepath

    try:
        out = subprocess.check_output([
            'ffprobe', '-v', 'error',
            '-show_entries', 'stream=codec_type,codec_name',
            '-of', 'csv=p=0',
            filepath
        ]).decode().strip().split('\n')

        streams = {}
        for line in out:
            if ',' in line:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) == 2:
                    if parts[0] in ['video', 'audio']:
                        streams[parts[0]] = parts[1].lower()
                    elif parts[1] in ['video', 'audio']:
                        streams[parts[1]] = parts[0].lower()

        vcodec = streams.get('video')
        acodec = streams.get('audio')

        # QuickTime Player natively plays H.264 (avc1/h264), HEVC (hvc1/hevc) and AAC / MP3
        # YouTube often provides VP9 or AV1 with Opus audio, which breaks QuickTime!
        needs_v = vcodec and vcodec not in ['h264', 'hevc']
        needs_a = acodec and acodec not in ['aac', 'mp3']

        if not needs_v and not needs_a:
            return filepath

        if task_id:
            with tasks_lock:
                if task_id in tasks:
                    tasks[task_id]['stage'] = "Making video 100% QuickTime compatible (H.264 + AAC)..."
                    tasks[task_id]['percent'] = 98.0

        temp_out = filepath + '.qt_compat.mp4'
        cmd = ['ffmpeg', '-y', '-i', filepath]

        if needs_v:
            # Convert non-H264 video (like VP9/AV1) to universal H.264 with standard 4:2:0 chroma
            cmd += ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p']
        else:
            cmd += ['-c:v', 'copy']

        if needs_a:
            # Convert non-AAC audio (like Opus) to standard AAC audio
            cmd += ['-c:a', 'aac', '-b:a', '192k']
        else:
            cmd += ['-c:a', 'copy']

        # Add faststart for instant playback in QuickTime and Finder
        cmd += ['-movflags', '+faststart', temp_out]

        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(temp_out) and os.path.getsize(temp_out) > 1000:
            os.replace(temp_out, filepath)

        return filepath
    except Exception:
        # Fallback to keeping original merged file if anything fails
        return filepath


# ============================================================================
# BACKGROUND DOWNLOAD WORKER
# ============================================================================

def run_download_job(task_id: str, options: dict):
    """
    Background worker that runs the yt-dlp download and merges audio/video via FFmpeg.
    Continuously updates task state for live progress tracking.
    """
    url = options['url']
    format_type = options.get('format_type', 'mp4')  # 'mp4' or 'mp3'
    quality = options.get('quality', 'best')         # 'best', '2160', '1080', '720', etc.
    download_subs = options.get('download_subs', False)
    download_thumb = options.get('download_thumb', False)
    is_playlist = options.get('is_playlist', False)

    downloaded_files = []
    current_stream = "video"  # 'video' or 'audio'

    def progress_hook(d):
        nonlocal current_stream
        with tasks_lock:
            if task_id not in tasks:
                return

            task = tasks[task_id]
            status = d.get('status')

            if status == 'downloading':
                # Track filename to determine stream type
                filename = os.path.basename(d.get('filename', ''))
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes', 0)
                speed = d.get('speed')
                eta = d.get('eta')

                # Calculate stream percentage
                stream_pct = (downloaded / total * 100) if total > 0 else 0

                # Detect whether downloading video or audio track
                if format_type == 'mp4':
                    # If format is split (video + audio)
                    if any(ext in filename.lower() for ext in ['.f251.', '.f140.', '.m4a', 'audio']):
                        current_stream = "audio"
                        # Audio represents the second 20% (from 75% to 95%)
                        overall_pct = 75 + (stream_pct * 0.20)
                        stage_msg = f"Downloading audio track ({stream_pct:.0f}%)"
                    else:
                        current_stream = "video"
                        # Video represents the first 75%
                        overall_pct = stream_pct * 0.75
                        stage_msg = f"Downloading video track ({stream_pct:.0f}%)"
                else:
                    # MP3 audio-only
                    overall_pct = stream_pct * 0.85
                    stage_msg = f"Downloading audio ({stream_pct:.0f}%)"

                # Check playlist progress info if present
                info_dict = d.get('info_dict') or {}
                playlist_index = info_dict.get('playlist_index')
                playlist_count = info_dict.get('n_entries')
                if playlist_index and playlist_count:
                    stage_msg = f"[{playlist_index}/{playlist_count}] {stage_msg}"

                task['status'] = 'downloading'
                task['percent'] = min(round(overall_pct, 1), 99.0)
                task['stage'] = stage_msg
                task['speed'] = format_speed(speed)
                task['eta'] = format_eta(eta)
                task['downloaded_bytes'] = downloaded
                task['total_bytes'] = total
                task['active_filename'] = filename

            elif status == 'finished':
                # Finished downloading raw stream, transitioning to processing
                finished_file = d.get('filename')
                if finished_file and finished_file not in downloaded_files:
                    downloaded_files.append(finished_file)

                task['status'] = 'merging'
                task['stage'] = (
                    "Merging video and audio with FFmpeg into MP4..."
                    if format_type == 'mp4'
                    else "Converting audio to high-quality 320kbps MP3..."
                )
                task['percent'] = 95.0
                task['speed'] = "--"
                task['eta'] = "--"

    def postprocessor_hook(d):
        with tasks_lock:
            if task_id not in tasks:
                return
            task = tasks[task_id]
            pp_status = d.get('status')
            pp_name = d.get('postprocessor', '')

            if pp_status == 'started':
                task['status'] = 'merging'
                if 'ExtractAudio' in pp_name:
                    task['stage'] = "Encoding 320kbps MP3 audio with FFmpeg..."
                elif 'EmbedSubtitle' in pp_name:
                    task['stage'] = "Embedding subtitles into video..."
                elif 'ThumbnailsConvertor' in pp_name:
                    task['stage'] = "Converting thumbnail to JPG..."
                else:
                    task['stage'] = "Merging video & audio tracks with FFmpeg..."
                task['percent'] = 97.0
            elif pp_status == 'finished':
                # Grab final output filepath if available
                filepath = d.get('info_dict', {}).get('filepath') or d.get('filepath')
                if filepath and os.path.exists(filepath):
                    task['final_filepath'] = filepath
                    task['final_filename'] = os.path.basename(filepath)

    # Configure output template
    if is_playlist:
        out_template = os.path.join(DOWNLOADS_DIR, '%(playlist_title)s', '%(playlist_index)02d - %(title)s.%(ext)s')
    else:
        out_template = os.path.join(DOWNLOADS_DIR, '%(title)s.%(ext)s')

    # Build yt-dlp options based on format and quality
    ydl_opts = {
        'outtmpl': out_template,
        'progress_hooks': [progress_hook],
        'postprocessor_hooks': [postprocessor_hook],
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 10,
        'file_access_retries': 5,
        'ignoreerrors': True,  # Keep downloading even if auxiliary items like subtitles timeout
    }

    if not is_playlist:
        ydl_opts['noplaylist'] = True

    if format_type == 'mp3':
        # Audio Only (MP3 320kbps)
        ydl_opts['format'] = 'bestaudio/best'
        postprocessors = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }]
    else:
        # MP4 Video + Audio merged via FFmpeg
        # Prioritize native H.264 (avc1) video + native AAC (mp4a) audio for 100% Apple & QuickTime compatibility
        if quality == 'best':
            ydl_opts['format'] = (
                'bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a][acodec^=mp4a]/'
                'bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/'
                'bestvideo[ext=mp4]+bestaudio[ext=m4a]/'
                'bestvideo+bestaudio/best'
            )
        else:
            try:
                height = int(quality)
                ydl_opts['format'] = (
                    f'bestvideo[height<={height}][ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a][acodec^=mp4a]/'
                    f'bestvideo[height<={height}][vcodec^=avc1]+bestaudio[acodec^=mp4a]/'
                    f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/'
                    f'bestvideo[height<={height}]+bestaudio/'
                    f'best[height<={height}]/best'
                )
            except ValueError:
                ydl_opts['format'] = (
                    'bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a][acodec^=mp4a]/'
                    'bestvideo[ext=mp4]+bestaudio[ext=m4a]/'
                    'bestvideo+bestaudio/best'
                )

        ydl_opts['merge_output_format'] = 'mp4'
        postprocessors = []

    # Optional: Subtitles
    if download_subs:
        ydl_opts['writesubtitles'] = True
        ydl_opts['writeautomaticsub'] = True
        ydl_opts['subtitleslangs'] = ['en']
        ydl_opts['subtitlesformat'] = 'srt/vtt/best'

    # Optional: Thumbnail
    if download_thumb:
        ydl_opts['writethumbnail'] = True
        postprocessors.append({
            'key': 'FFmpegThumbnailsConvertor',
            'format': 'jpg',
        })

    if postprocessors:
        ydl_opts['postprocessors'] = postprocessors

    try:
        with tasks_lock:
            tasks[task_id]['stage'] = "Starting download..."
            tasks[task_id]['status'] = 'downloading'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # First extract info to predict filename and retrieve title
            info = ydl.extract_info(url, download=True)
            
            # Identify output file
            filename = None
            if info:
                title = info.get('title', 'Video')
                with tasks_lock:
                    tasks[task_id]['title'] = title
                
                # Check for direct filename
                if 'entries' in info and info['entries']:
                    # Playlist
                    first = info['entries'][0]
                    filename = f"Playlist: {info.get('title', 'YouTube Playlist')}"
                else:
                    target_file = ydl.prepare_filename(info)
                    base, _ = os.path.splitext(target_file)
                    expected_ext = 'mp3' if format_type == 'mp3' else 'mp4'
                    candidate = f"{base}.{expected_ext}"
                    if os.path.exists(candidate):
                        filename = os.path.basename(candidate)
                        with tasks_lock:
                            tasks[task_id]['final_filepath'] = candidate
                    elif os.path.exists(target_file):
                        filename = os.path.basename(target_file)
                        with tasks_lock:
                            tasks[task_id]['final_filepath'] = target_file

        with tasks_lock:
            # Fallback to recorded filepath or newest file in Downloads
            task = tasks[task_id]
            final_name = task.get('final_filename') or filename
            if not final_name and task.get('final_filepath'):
                final_name = os.path.basename(task['final_filepath'])

            if not final_name:
                # Find most recently modified file in Downloads
                try:
                    files = [
                        os.path.join(DOWNLOADS_DIR, f) 
                        for f in os.listdir(DOWNLOADS_DIR) 
                        if not f.startswith('.')
                    ]
                    if files:
                        newest = max(files, key=os.path.getmtime)
                        final_name = os.path.basename(newest)
                        task['final_filepath'] = newest
                except Exception:
                    final_name = "Download completed"

            target_path = task.get('final_filepath')
            if format_type == 'mp4' and target_path and os.path.exists(target_path):
                ensure_quicktime_compatible(target_path, task_id)

            task['status'] = 'completed'
            task['percent'] = 100.0
            task['stage'] = "Download and processing completed successfully!"
            task['filename'] = final_name
            task['completed_at'] = time.time()

            # Calculate final file size if known
            if target_path and os.path.exists(target_path):
                task['file_size_str'] = format_bytes(os.path.getsize(target_path))

    except Exception as e:
        with tasks_lock:
            tasks[task_id]['status'] = 'error'
            tasks[task_id]['error'] = parse_friendly_error(str(e))
            tasks[task_id]['stage'] = "Download failed."


# ============================================================================
# API ROUTES
# ============================================================================

@app.route('/')
def index():
    """Serve the primary single-page UI."""
    return render_template('index.html')


@app.route('/api/system-status', methods=['GET'])
def system_status():
    """Return system readiness, including FFmpeg status and version info."""
    ffmpeg_installed, ffmpeg_path = check_ffmpeg()
    return jsonify({
        'ffmpeg_installed': ffmpeg_installed,
        'ffmpeg_path': ffmpeg_path,
        'yt_dlp_version': yt_dlp.version.__version__,
        'downloads_dir': DOWNLOADS_DIR,
        'platform': sys.platform,
    })


@app.route('/api/info', methods=['POST'])
def fetch_info():
    """
    Fetch metadata for a given YouTube URL without downloading.
    Returns title, thumbnail, channel, duration, and dynamically detected available resolutions.
    """
    data = request.get_json() or {}
    url = (data.get('url') or '').strip()

    if not url:
        return jsonify({'success': False, 'error': 'Please enter a YouTube video or playlist link.'}), 400

    try:
        # Detect if it's an explicit playlist link
        is_playlist_url = 'playlist?list=' in url and 'watch?v=' not in url

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'nocheckcertificate': True,
            'extract_flat': 'in_playlist' if is_playlist_url else False,
            'noplaylist': not is_playlist_url,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            return jsonify({'success': False, 'error': 'Could not extract information for this link.'}), 400

        # Handle Playlist
        if info.get('_type') == 'playlist' or ('entries' in info and is_playlist_url):
            entries = list(info.get('entries', []))
            first_thumb = ""
            if entries:
                first_thumb = entries[0].get('thumbnails', [{}])[-1].get('url', '') if entries[0].get('thumbnails') else ''

            return jsonify({
                'success': True,
                'is_playlist': True,
                'title': info.get('title', 'YouTube Playlist'),
                'channel': info.get('uploader') or info.get('channel') or 'YouTube Creator',
                'video_count': len(entries),
                'thumbnail': info.get('thumbnail') or first_thumb or 'https://images.unsplash.com/photo-1611162617474-5b21e879e113?w=800',
                'duration_str': f"{len(entries)} videos",
                'resolutions': [
                    {'value': 'best', 'label': 'Best Available Quality (Recommended)'},
                    {'value': '1080', 'label': '1080p (Full HD)'},
                    {'value': '720', 'label': '720p (HD)'},
                    {'value': '480', 'label': '480p (SD)'},
                    {'value': '360', 'label': '360p (SD)'},
                ],
            })

        # Single Video: extract real available video resolutions
        formats = info.get('formats', [])
        available_heights = set()
        for f in formats:
            # Check format contains video stream and has recorded height
            if f.get('vcodec') != 'none' and f.get('height'):
                available_heights.add(f.get('height'))

        # Standard resolution tiers to check against actual formats
        standard_tiers = [
            (4320, '4320p (8K Ultra HD)'),
            (2160, '2160p (4K Ultra HD)'),
            (1440, '1440p (2K Quad HD)'),
            (1080, '1080p (Full HD)'),
            (720, '720p (HD)'),
            (480, '480p (Standard Definition)'),
            (360, '360p (Low Definition)'),
            (240, '240p (Low)'),
            (144, '144p (Minimum)'),
        ]

        # Calculate approximate file sizes per height
        tier_sizes = {}
        for f in formats:
            h = f.get('height')
            sz = f.get('filesize') or f.get('filesize_approx')
            if h and sz:
                if h not in tier_sizes or sz > tier_sizes[h]:
                    tier_sizes[h] = sz

        duration_sec = info.get('duration') or 0
        audio_approx = int(duration_sec * 16000)  # ~128kbps audio

        # Always start with "Best Available"
        resolutions = [{'value': 'best', 'label': 'Best Available Quality (Highest Resolution)'}]

        # Add only resolutions that are actually present for this video with size estimate
        for height_val, label in standard_tiers:
            matched_heights = [h for h in available_heights if abs(h - height_val) <= 10 or h == height_val]
            if matched_heights:
                v_size = max((tier_sizes.get(h, 0) for h in matched_heights), default=0)
                total_sz = (v_size + audio_approx) if v_size > 0 else 0
                size_tag = f"  (~{format_bytes(total_sz)})" if total_sz > 0 else ""
                resolutions.append({'value': str(height_val), 'label': f"{label}{size_tag}"})

        # Thumbnail fallback
        thumbnail = info.get('thumbnail')
        if not thumbnail and info.get('thumbnails'):
            thumbnail = info['thumbnails'][-1].get('url')

        duration_sec = info.get('duration')
        duration_formatted = format_duration(duration_sec)

        return jsonify({
            'success': True,
            'is_playlist': False,
            'id': info.get('id', ''),
            'title': info.get('title', 'Unknown Title'),
            'channel': info.get('uploader') or info.get('channel') or 'YouTube Channel',
            'duration': duration_sec,
            'duration_str': duration_formatted,
            'thumbnail': thumbnail or '',
            'view_count': info.get('view_count'),
            'resolutions': resolutions,
        })

    except Exception as e:
        friendly_error = parse_friendly_error(str(e))
        return jsonify({'success': False, 'error': friendly_error}), 400


@app.route('/api/download', methods=['POST'])
def start_download():
    """Initiate a download job in a background thread."""
    data = request.get_json() or {}
    url = (data.get('url') or '').strip()

    if not url:
        return jsonify({'success': False, 'error': 'Missing URL.'}), 400

    ffmpeg_installed, _ = check_ffmpeg()
    if not ffmpeg_installed:
        return jsonify({
            'success': False,
            'error': (
                'FFmpeg is not installed on your system! '
                'FFmpeg is required to merge audio and video or convert to MP3. '
                'Please follow the FFmpeg setup instructions in the README.'
            )
        }), 400

    task_id = uuid.uuid4().hex[:10]

    with tasks_lock:
        tasks[task_id] = {
            'id': task_id,
            'url': url,
            'title': data.get('title', 'YouTube Video'),
            'format_type': data.get('format_type', 'mp4'),
            'quality': data.get('quality', 'best'),
            'status': 'starting',
            'percent': 0.0,
            'stage': 'Initializing download...',
            'speed': '--',
            'eta': '--',
            'downloaded_bytes': 0,
            'total_bytes': 0,
            'filename': '',
            'error': None,
            'created_at': time.time(),
        }

    # Start background thread
    worker = threading.Thread(
        target=run_download_job,
        args=(task_id, data),
        daemon=True
    )
    worker.start()

    return jsonify({'success': True, 'task_id': task_id})


@app.route('/api/progress/<task_id>', methods=['GET'])
def get_progress(task_id: str):
    """Poll live progress for a specific task."""
    with tasks_lock:
        task = tasks.get(task_id)
        if not task:
            return jsonify({'success': False, 'error': 'Task not found.'}), 404

        return jsonify({
            'success': True,
            'id': task['id'],
            'status': task['status'],
            'percent': task['percent'],
            'stage': task['stage'],
            'speed': task.get('speed', '--'),
            'eta': task.get('eta', '--'),
            'downloaded_str': format_bytes(task.get('downloaded_bytes')),
            'total_str': format_bytes(task.get('total_bytes')),
            'filename': task.get('filename', ''),
            'file_size_str': task.get('file_size_str', ''),
            'error': task.get('error'),
        })


@app.route('/api/open-folder', methods=['POST'])
def open_folder():
    """Open the local Downloads folder in the host operating system's file manager."""
    try:
        if sys.platform == 'win32':
            os.startfile(DOWNLOADS_DIR)
        elif sys.platform == 'darwin':
            subprocess.run(['open', DOWNLOADS_DIR], check=False)
        else:
            subprocess.run(['xdg-open', DOWNLOADS_DIR], check=False)
        return jsonify({'success': True, 'path': DOWNLOADS_DIR})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/downloads', methods=['GET'])
def list_downloads():
    """List all completed files stored in the Downloads directory."""
    try:
        files = []
        for entry in os.scandir(DOWNLOADS_DIR):
            if entry.is_file() and not entry.name.startswith('.'):
                stat = entry.stat()
                files.append({
                    'name': entry.name,
                    'size': format_bytes(stat.st_size),
                    'size_bytes': stat.st_size,
                    'mtime': stat.st_mtime,
                    'mtime_str': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                    'is_audio': entry.name.lower().endswith(('.mp3', '.m4a', '.wav', '.opus')),
                    'is_video': entry.name.lower().endswith(('.mp4', '.mkv', '.webm')),
                })
        # Sort newest first
        files.sort(key=lambda x: x['mtime'], reverse=True)
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/downloads/<path:filename>')
def serve_download(filename: str):
    """Serve downloaded file for in-browser playback or direct saving."""
    return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=False)


@app.route('/api/download-file/<path:filename>')
def download_file(filename: str):
    """Trigger native browser file download (Save As / system download shelf)."""
    return send_from_directory(DOWNLOADS_DIR, filename, as_attachment=True, download_name=filename)


# ============================================================================
# MAIN ENTRYPOINT
# ============================================================================

def startup_banner():
    """Display startup diagnostics and user-friendly tips in the console."""
    ffmpeg_ok, ffmpeg_path = check_ffmpeg()

    print("\n" + "=" * 65)
    print("  🚀 PERSONAL YOUTUBE VIDEO DOWNLOADER (Local Web UI)")
    print("=" * 65)
    print(f"  • Web UI URL:       http://localhost:5000")
    print(f"  • Downloads Folder: {DOWNLOADS_DIR}")
    print(f"  • yt-dlp Version:   {yt_dlp.version.__version__}")

    if ffmpeg_ok:
        print(f"  • FFmpeg:           ✅ Detected ({ffmpeg_path})")
    else:
        print("  • FFmpeg:           ⚠️  NOT FOUND")
        print("\n  [FFmpeg Setup Instructions]")
        print("  FFmpeg is required to merge HD/4K video tracks and convert MP3s.")
        print("  - Windows (PowerShell): winget install Gyan.FFmpeg")
        print("  - Mac (Terminal):       brew install ffmpeg")
        print("  - Linux (Ubuntu/Deb):   sudo apt install ffmpeg")

    print("\n  💡 Tip: Keep yt-dlp updated as YouTube frequently changes formats:")
    print("     pip install -U yt-dlp")
    print("=" * 65 + "\n")


if __name__ == '__main__':
    startup_banner()
    # Runs locally on port 5000
    app.run(host='127.0.0.1', port=5000, debug=False)
