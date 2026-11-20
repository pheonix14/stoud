import os
import re
import sys
import time
import math
import subprocess
import threading
import urllib.request
import urllib.parse
import http.cookiejar
import tempfile
import zipfile
import shutil
import gc

active_process = None
active_thread = None
log_messages = []
active_stream_info = {
    "status": "idle",
    "title": None,
    "url": None,
    "start_time": None,
    "pid": None,
    "quality": None,
    "metrics": {
        "bitrate": "N/A",
        "speed": "N/A",
        "fps": "N/A",
        "frame": "0",
        "time": "00:00:00"
    },
    "health": "Unknown",
    "is_sharded": False,
    "shard_info": None,
    "filesize_gb": None
}

FFMPEG_STATUS = "Not Checked"
download_progress_message = ""

# ============================================================
# RENDER FREE-TIER TUNING CONSTANTS
# ============================================================
RENDER_RAM_MB = int(os.environ.get("STOUD_RAM_LIMIT_MB", "450"))
BUDGET_BUFSIZE_KB = "512k"
BUDGET_MAXRATE_KB = "1200k"
BUDGET_BITRATE_KB = "1000k"
TEMP_CACHE_DIR = os.path.join(tempfile.gettempdir(), "stoud_cache")
os.makedirs(TEMP_CACHE_DIR, exist_ok=True)

# ============================================================
# SYSTEM HEALTH & RESOURCE MONITORING
# ============================================================
def get_available_memory_mb():
    """Get available memory in MB (Linux /proc/meminfo or Windows fallback)."""
    try:
        if sys.platform == "linux" and os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        return int(line.split()[1]) // 1024
        elif sys.platform == "win32":
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return int(stat.ullAvailPhys // (1024 * 1024))
    except Exception:
        pass
    return RENDER_RAM_MB

def get_available_disk_mb():
    """Get free disk space in MB."""
    try:
        total, used, free = shutil.disk_usage("/")
        return free // (1024 * 1024)
    except Exception:
        return 500

def cleanup_temp_cache():
    """Clean up old temp files and invoke garbage collector to reclaim RAM."""
    try:
        if os.path.exists(TEMP_CACHE_DIR):
            for f in os.listdir(TEMP_CACHE_DIR):
                filepath = os.path.join(TEMP_CACHE_DIR, f)
                try:
                    if os.path.isfile(filepath) and (time.time() - os.path.getmtime(filepath) > 180):
                        os.remove(filepath)
                except Exception:
                    pass
    except Exception:
        pass
    gc.collect()

# ============================================================
# FFMPEG EXECUTABLE DISCOVERY & SETUP
# ============================================================
def get_ffmpeg_status():
    global FFMPEG_STATUS, download_progress_message
    if download_progress_message:
        return download_progress_message
        
    if sys.platform == "win32":
        local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg.exe")
        local_ffprobe = os.path.join(os.getcwd(), "ffprobe.exe")
        if os.path.exists(local_ffmpeg) and os.path.exists(local_ffprobe):
            FFMPEG_STATUS = "Installed Locally"
            return "Installed Locally"
            
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        FFMPEG_STATUS = "Installed in System PATH"
        return "Installed in System PATH"
    except FileNotFoundError:
        pass
        
    FFMPEG_STATUS = "Not Installed"
    return "Not Installed"

def download_ffmpeg_background():
    global download_progress_message
    if sys.platform != "win32":
        download_progress_message = "Platform is Linux/Docker. FFmpeg is installed via apt-get."
        return
        
    def update_progress(msg):
        global download_progress_message
        download_progress_message = msg
        print(f"FFmpeg Downloader: {msg}")
        
    def worker():
        global download_progress_message, FFMPEG_STATUS
        try:
            update_progress("Starting download of FFmpeg release archive...")
            zip_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            temp_zip = os.path.join(os.getcwd(), "ffmpeg_temp.zip")
            
            req = urllib.request.Request(zip_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp:
                total_size = int(resp.headers.get('content-length', 0))
                downloaded = 0
                with open(temp_zip, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            update_progress(f"Downloading FFmpeg: {percent}% ({downloaded // (1024*1024)}MB / {total_size // (1024*1024)}MB)")
            
            update_progress("Extracting binaries...")
            with zipfile.ZipFile(temp_zip) as z:
                for file_info in z.infolist():
                    filename = file_info.filename
                    if filename.endswith("ffmpeg.exe") and not os.path.basename(filename).startswith("._"):
                        with z.open(file_info) as source, open(os.path.join(os.getcwd(), "ffmpeg.exe"), "wb") as target:
                            target.write(source.read())
                    elif filename.endswith("ffprobe.exe") and not os.path.basename(filename).startswith("._"):
                        with z.open(file_info) as source, open(os.path.join(os.getcwd(), "ffprobe.exe"), "wb") as target:
                            target.write(source.read())
            try:
                os.remove(temp_zip)
            except Exception:
                pass
            FFMPEG_STATUS = "Installed Locally"
            update_progress("")
        except Exception as e:
            update_progress(f"Failed: {str(e)}")
            FFMPEG_STATUS = "Download Failed"
            
    threading.Thread(target=worker, daemon=True).start()

def get_ffmpeg_executable():
    if sys.platform == "win32":
        local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg.exe")
        if os.path.exists(local_ffmpeg):
            return local_ffmpeg
    return "ffmpeg"

# ============================================================
# LOGGING
# ============================================================
def add_log(message):
    global log_messages
    timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
    log_messages.append(f"{timestamp} {message}")
    if len(log_messages) > 300:
        log_messages.pop(0)

# ============================================================
# MEDIA HELPERS & GOOGLE DRIVE SHARD ENGINE
# ============================================================
def extract_gdrive_id(url):
    """Extract Google Drive file ID from various URL patterns."""
    if not url:
        return None
    patterns = [
        r'/file/d/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',
        r'/open\?id=([a-zA-Z0-9_-]+)',
        r'/uc\?id=([a-zA-Z0-9_-]+)'
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def resolve_gdrive_url(url):
    """
    Resolve Google Drive link (even 50GB+) to direct streaming URL.
    Handles Google's large-file virus confirmation tokens and Range capability.
    """
    import yt_dlp
    add_log(f"Resolving Google Drive URL: {url}")
    file_id = extract_gdrive_id(url)
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    video_url = None
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    title = f'GDrive Video ({file_id})' if file_id else 'GDrive Video'
    
    # 1. First attempt with yt-dlp
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                video_url = info.get('url')
                title = info.get('title') or title
                user_agent = info.get('http_headers', {}).get('User-Agent', user_agent)
    except Exception as e:
        add_log(f"yt-dlp GDrive resolution note: {e}")
        
    # 2. Fallback to direct download URL with confirm=t
    if not video_url and file_id:
        add_log(f"Using direct Google Drive API endpoint for ID: {file_id}")
        video_url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t"
        
    if not video_url:
        raise Exception("Could not resolve Google Drive stream URL.")
        
    add_log(f"Google Drive stream link ready for Range-Sharded engine.")
    return video_url, user_agent, title

def query_gdrive_file_size(direct_url, user_agent=None):
    """
    Fast query for file size using a 100-byte Range request.
    Downloads only 100 bytes, returns total size in bytes (e.g. 50GB = ~53,687,091,200).
    """
    try:
        headers = {"Range": "bytes=0-99"}
        if user_agent:
            headers["User-Agent"] = user_agent
        req = urllib.request.Request(direct_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            cr = resp.headers.get("Content-Range")
            if cr and "/" in cr:
                total_str = cr.split("/")[1].strip()
                if total_str.isdigit():
                    return int(total_str)
    except Exception as e:
        add_log(f"Range size probe note: {e}")
    return None

def get_local_mp4_duration(filepath):
    """Parse MP4 mvhd box to extract exact duration and timescale without external tools."""
    import struct
    try:
        if not os.path.isfile(filepath):
            return None
        with open(filepath, 'rb') as f:
            while True:
                header = f.read(8)
                if len(header) < 8:
                    break
                size, box_type = struct.unpack('>I4s', header)
                if size == 1:
                    size = struct.unpack('>Q', f.read(8))[0]
                    content_size = size - 16
                else:
                    content_size = size - 8
                
                if box_type == b'moov':
                    moov_data = f.read(min(content_size, 10 * 1024 * 1024))
                    idx = moov_data.find(b'mvhd')
                    if idx != -1:
                        version = moov_data[idx + 4]
                        if version == 0:
                            timescale, duration = struct.unpack('>II', moov_data[idx + 8 + 8 : idx + 8 + 8 + 8])
                        else:
                            timescale, duration = struct.unpack('>IQ', moov_data[idx + 8 + 16 : idx + 8 + 16 + 12])
                        if timescale > 0:
                            return duration / timescale
                    break
                else:
                    if content_size > 0:
                        f.seek(content_size, os.SEEK_CUR)
    except Exception:
        pass
    return None

def inspect_media(url):
    """
    Inspect a media link and return metadata including duration, filesize,
    whether it's a large 50GB file, and recommended shard plan.
    Supports Google Drive links, YouTube links, and local video captures.
    """
    import yt_dlp
    is_gdrive = "drive.google.com" in url
    is_youtube = "youtube.com" in url or "youtu.be" in url
    is_local = os.path.exists(url)
    
    info_dict = {
        "url": url,
        "is_gdrive": is_gdrive,
        "is_youtube": is_youtube,
        "is_local": is_local,
        "title": os.path.basename(url) if is_local else "Unknown Media",
        "duration": None,
        "duration_formatted": "Unknown",
        "filesize_bytes": None,
        "filesize_gb": None,
        "is_large": False,
        "recommended_shard_minutes": 30,
        "recommended_shards": 1
    }
    
    # 1. Local file inspection
    if is_local:
        try:
            size_bytes = os.path.getsize(url)
            info_dict["filesize_bytes"] = size_bytes
            info_dict["filesize_gb"] = round(size_bytes / (1024 ** 3), 2)
            info_dict["title"] = os.path.basename(url)
            
            dur = get_local_mp4_duration(url)
            if dur:
                info_dict["duration"] = dur
                secs = int(dur)
                info_dict["duration_formatted"] = time.strftime('%H:%M:%S', time.gmtime(secs))
        except Exception as e:
            add_log(f"Local file inspect error: {e}")
            
    # 2. Remote inspection via yt-dlp
    elif not is_local:
        try:
            ydl_opts = {'quiet': True, 'no_warnings': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                data = ydl.extract_info(url, download=False)
                if data:
                    info_dict["title"] = data.get("title", info_dict["title"])
                    info_dict["duration"] = data.get("duration")
                    if info_dict["duration"]:
                        secs = int(info_dict["duration"])
                        info_dict["duration_formatted"] = time.strftime('%H:%M:%S', time.gmtime(secs))
                    
                    direct_url = data.get("url")
                    if direct_url and is_gdrive:
                        ua = data.get('http_headers', {}).get('User-Agent')
                        size = query_gdrive_file_size(direct_url, ua)
                        if size:
                            info_dict["filesize_bytes"] = size
                            info_dict["filesize_gb"] = round(size / (1024 ** 3), 2)
        except Exception as e:
            add_log(f"Inspect error: {e}")
            if is_gdrive:
                fid = extract_gdrive_id(url)
                if fid:
                    info_dict["title"] = f"Google Drive Video ({fid})"
                    direct_url = f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"
                    size = query_gdrive_file_size(direct_url)
                    if size:
                        info_dict["filesize_bytes"] = size
                        info_dict["filesize_gb"] = round(size / (1024 ** 3), 2)
                        
    # Determine if large file
    size_gb = info_dict.get("filesize_gb") or 0
    duration_secs = info_dict.get("duration") or 0
    if size_gb >= 1.0 or duration_secs >= 1800 or is_gdrive:
        info_dict["is_large"] = True
        
    shard_secs = 30 * 60
    if duration_secs > 0:
        info_dict["recommended_shards"] = max(1, math.ceil(duration_secs / shard_secs))
    elif size_gb >= 50.0:
        info_dict["recommended_shards"] = max(1, math.ceil((size_gb * 8000 / 10) / shard_secs))
        
    return info_dict

def get_media_from_path(path):
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://") or path.startswith("rtmp://"):
        return path
    
    if os.path.isdir(path):
        valid_exts = {".mp4", ".mkv", ".mov", ".avi", ".jpg", ".jpeg", ".png"}
        files = [os.path.join(path, f) for f in os.listdir(path) if any(f.lower().endswith(ext) for ext in valid_exts)]
        if files:
            import random
            selected = random.choice(files)
            add_log(f"Selected media '{os.path.basename(selected)}' from folder '{path}'")
            return selected
        add_log(f"No valid media files in folder: {path}")
        return ""
    return path

def extract_playlist_items(url):
    import yt_dlp
    add_log(f"Extracting playlist items for: {url}")
    ydl_opts = {'extract_flat': True, 'quiet': True, 'no_warnings': True}
    items = []
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                for entry in info['entries']:
                    if entry and entry.get('url'):
                        vid_url = entry.get('url')
                        if not vid_url.startswith('http'):
                            vid_url = f"https://www.youtube.com/watch?v={entry.get('id')}"
                        items.append({
                            "title": entry.get('title', 'Unknown Video'),
                            "url": vid_url,
                            "type": "youtube"
                        })
            else:
                items.append({
                    "title": info.get('title', 'Unknown Video'),
                    "url": info.get('url', url),
                    "type": "youtube"
                })
        except Exception as e:
            add_log(f"Playlist extraction failed: {str(e)}")
            raise Exception(f"Failed to extract playlist: {str(e)}")
    return items

def resolve_youtube_url(url):
    import yt_dlp
    add_log(f"Resolving YouTube URL (Public/Unlisted): {url}")
    ydl_opts = {
        'format': 'bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[acodec^=mp4a]/bestvideo[vcodec^=avc1]+bestaudio/best[vcodec^=avc1]/bestvideo+bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            add_log(f"yt-dlp extraction failed: {str(e)}")
            raise Exception(f"yt-dlp extraction failed: {str(e)}")
            
        title = info.get('title', 'YouTube Video')
        requested_formats = info.get('requested_formats')
        if requested_formats and len(requested_formats) >= 2:
            return requested_formats[0].get('url'), requested_formats[1].get('url'), title, False
        else:
            return info.get('url'), None, title, True

# ============================================================
# FFMPEG STATS PARSER
# ============================================================
stats_regex = re.compile(
    r'frame=\s*(?P<frame>\d+)\s+fps=\s*(?P<fps>[\d\.]+)\s+q=.*size=\s*(?P<size>\d+\w*)\s+time=\s*(?P<time>[\d\:\.]+)\s+bitrate=\s*(?P<bitrate>[\d\.]+kbits/s|N/A)\s+speed=\s*(?P<speed>[\d\.]+x)'
)

def log_reader_thread(process):
    global active_stream_info, active_process
    try:
        while True:
            line = process.stderr.readline()
            if not line:
                break
            line_str = line.strip()
            if line_str:
                add_log(f"[FFmpeg] {line_str}")
                match = stats_regex.search(line_str)
                if match:
                    gd = match.groupdict()
                    active_stream_info["metrics"] = {
                        "bitrate": gd.get("bitrate", "N/A"),
                        "speed": gd.get("speed", "N/A"),
                        "fps": gd.get("fps", "N/A"),
                        "frame": gd.get("frame", "0"),
                        "time": gd.get("time", "00:00:00")
                    }
                    active_stream_info["health"] = "Active"
    except Exception as e:
        add_log(f"Error reading FFmpeg log: {str(e)}")
    finally:
        rc = process.wait()
        add_log(f"FFmpeg process exited with code {rc}")
        if active_process and active_process.pid == process.pid:
            active_process = None
            active_stream_info["status"] = "idle"
            active_stream_info["title"] = None
            active_stream_info["url"] = None
            active_stream_info["start_time"] = None
            active_stream_info["pid"] = None
            active_stream_info["quality"] = None
            active_stream_info["health"] = "Disconnected"
            active_stream_info["is_sharded"] = False
            active_stream_info["shard_info"] = None
            active_stream_info["metrics"] = {
                "bitrate": "N/A",
                "speed": "N/A",
                "fps": "N/A",
                "frame": "0",
                "time": "00:00:00"
            }
        cleanup_temp_cache()

def memory_watchdog_thread(process):
    """Keep memory under control on Render's 512MB RAM free dyno."""
    while process.poll() is None:
        try:
            avail_mb = get_available_memory_mb()
            if avail_mb < 60:
                add_log(f"[CRITICAL RAM ALERT] Available memory down to {avail_mb}MB! Triggering emergency GC.")
                gc.collect()
            elif avail_mb < 120:
                gc.collect()
        except Exception:
            pass
        time.sleep(20)

# ============================================================
# SHARDED STREAMING BUILDER
# ============================================================
def build_ffmpeg_cmd(ffmpeg_exe, video_input, audio_input, destinations, quality="copy",
                     budget_mode=True, user_agent_str=None, is_image=False,
                     start_offset=None, duration=None):
    """
    Constructs an ultra-optimized, memory-bounded FFmpeg command.
    
    Key Features for 50GB Google Drive files on Render:
    1. HTTP Range Request Streaming: Never downloads the file to disk.
    2. Input Fast Seeking: `-ss <offset>` before `-i` skips directly via Range headers.
    3. Strict RAM ceiling: Single thread, tiny mux queue, small bufsize.
    4. HTTP Reconnect resilience: Automatically survives network stutters.
    """
    cmd = [ffmpeg_exe]
    
    if user_agent_str:
        cmd.extend(["-user_agent", user_agent_str])
        
    cmd.extend(["-nostdin", "-y"])
    
    # === FAST INPUT SEEK (CRITICAL FOR SHARDING 50GB FILES) ===
    # Placed BEFORE -i so FFmpeg uses HTTP Range request to seek directly
    # without downloading any earlier parts of the 50GB file!
    if start_offset is not None and start_offset > 0:
        cmd.extend(["-ss", str(start_offset)])
        
    cmd.extend(["-re"])
    
    # === RENDER FREE TIER MEMORY CONSTRAINTS ===
    if budget_mode:
        cmd.extend([
            "-threads", "1",
            "-probesize", "1000000",        # 1MB probe limit
            "-analyzeduration", "2000000",   # 2s analyze limit
        ])
    
    # === HTTP RANGE & RECONNECT FLAGS ===
    is_http_input = video_input.startswith("http://") or video_input.startswith("https://")
    if is_http_input:
        cmd.extend([
            "-reconnect", "1",
            "-reconnect_at_eof", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "30",
            "-reconnect_on_network_error", "1",
            "-reconnect_on_http_error", "4xx,5xx",
        ])
        
    if is_image:
        cmd.extend(["-loop", "1", "-framerate", "30"])
        
    cmd.extend(["-i", video_input])
    
    if audio_input:
        if audio_input.startswith("http"):
            cmd.extend([
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "30",
            ])
        if start_offset is not None and start_offset > 0:
            cmd.extend(["-ss", str(start_offset)])
        cmd.extend(["-re", "-i", audio_input])
        
    # === SHARD DURATION LIMIT ===
    if duration is not None and duration > 0:
        cmd.extend(["-t", str(duration)])
        
    # === PER-DESTINATION OUTPUT ENCODING ===
    for dest in destinations:
        full_rtmp_url = dest['rtmp_url']
        if dest.get('stream_key'):
            full_rtmp_url = f"{full_rtmp_url.rstrip('/')}/{dest['stream_key']}"
            
        if quality == "copy":
            # Stream Copy: Minimal CPU, zero transcoding memory overhead
            copy_args = [
                "-c:v", "copy",
                "-c:a", "aac",
                "-strict", "experimental"
            ]
            if budget_mode:
                copy_args.extend([
                    "-max_muxing_queue_size", "128",
                    "-flush_packets", "1"
                ])
                
            if audio_input:
                cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
                
            cmd.extend(copy_args)
            cmd.extend(["-f", "flv", full_rtmp_url])
        else:
            # Transcoding Mode: Ultrafast H.264 constrained to Render's single core & 512MB RAM
            if audio_input:
                cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
                
            transcode_args = [
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-pix_fmt", "yuv420p",
                "-g", "60",
                "-sc_threshold", "0",
                "-refs", "1",
                "-bf", "0",
                "-c:a", "aac",
                "-b:a", "96k",
                "-ar", "44100",
                "-ac", "2"
            ]
            if budget_mode:
                transcode_args.extend([
                    "-b:v", BUDGET_BITRATE_KB,
                    "-maxrate", BUDGET_MAXRATE_KB,
                    "-bufsize", BUDGET_BUFSIZE_KB,
                    "-max_muxing_queue_size", "128",
                    "-flush_packets", "1"
                ])
            else:
                transcode_args.extend([
                    "-b:v", "2500k",
                    "-maxrate", "2500k",
                    "-bufsize", "5000k"
                ])
            cmd.extend(transcode_args)
            cmd.extend(["-f", "flv", full_rtmp_url])
            
    return cmd

# ============================================================
# STREAM CONTROL
# ============================================================
def start_stream(video_url, destinations, quality="copy", budget_mode=True,
                 start_offset=None, duration=None, shard_info=None):
    """
    Launch streaming with sharding support and Render free tier safeguards.
    """
    global active_process, active_thread, active_stream_info
    
    if active_process is not None:
        raise Exception("A stream is already active. Stop it first.")
        
    ffmpeg_exe = get_ffmpeg_executable()
    if get_ffmpeg_status() == "Not Installed":
        raise Exception("FFmpeg is not installed.")
        
    enabled_dests = [d for d in destinations if d.get("enabled")]
    if not enabled_dests:
        raise Exception("No active stream destinations configured/enabled.")
        
    cleanup_temp_cache()
    
    # System check
    avail_mb = get_available_memory_mb()
    disk_mb = get_available_disk_mb()
    add_log(f"[System Health] RAM: ~{avail_mb}MB | Disk: ~{disk_mb}MB | Budget Mode: {budget_mode}")
    
    is_youtube = "youtube.com" in video_url or "youtu.be" in video_url
    is_gdrive = "drive.google.com" in video_url
    
    video_input = None
    audio_input = None
    title = "Live Stream"
    is_combined = True
    user_agent_str = None
    filesize_gb = None
    
    try:
        if is_youtube:
            video_input, audio_input, title, is_combined = resolve_youtube_url(video_url)
        elif is_gdrive:
            video_input, user_agent_str, title = resolve_gdrive_url(video_url)
            # Probe file size for metrics
            size_bytes = query_gdrive_file_size(video_input, user_agent_str)
            if size_bytes:
                filesize_gb = round(size_bytes / (1024 ** 3), 2)
                add_log(f"[GDrive Range Sharder] Stream target size: {filesize_gb} GB. Direct Range-streaming enabled.")
        else:
            video_input = video_url
            title = "Direct Video Stream"
    except Exception as e:
        add_log(f"Stream resolution error: {str(e)}")
        raise e
        
    is_image = video_input.lower().endswith(('.jpg', '.jpeg', '.png'))
    
    # Log shard progress if active
    if shard_info:
        add_log(f"[Shard Engine] Starting Shard {shard_info.get('index')} of {shard_info.get('total')} | "
                f"Offset: {start_offset or 0}s | Duration: {duration or 'Full'}s")
        title = f"[Shard {shard_info.get('index')}/{shard_info.get('total')}] {title}"
        
    cmd = build_ffmpeg_cmd(
        ffmpeg_exe, video_input, audio_input, enabled_dests,
        quality=quality, budget_mode=budget_mode, user_agent_str=user_agent_str,
        is_image=is_image, start_offset=start_offset, duration=duration
    )
    
    add_log(f"Launching FFmpeg streaming subprocess to {len(enabled_dests)} platforms...")
    
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
    env = os.environ.copy()
    if sys.platform == "linux" and budget_mode:
        env["MALLOC_ARENA_MAX"] = "2"
        
    try:
        active_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            startupinfo=startupinfo,
            env=env
        )
    except Exception as e:
        add_log(f"Failed to start FFmpeg subprocess: {str(e)}")
        raise Exception(f"Failed to start FFmpeg subprocess: {str(e)}")
        
    active_stream_info = {
        "status": "streaming",
        "title": title,
        "url": video_url,
        "start_time": time.time(),
        "pid": active_process.pid,
        "quality": quality,
        "metrics": {
            "bitrate": "N/A",
            "speed": "N/A",
            "fps": "N/A",
            "frame": "0",
            "time": "00:00:00"
        },
        "health": "Active",
        "is_sharded": bool(shard_info),
        "shard_info": shard_info,
        "filesize_gb": filesize_gb
    }
    
    add_log(f"Stream online! PID: {active_process.pid}. Broadcasting live.")
    
    active_thread = threading.Thread(target=log_reader_thread, args=(active_process,), daemon=True)
    active_thread.start()
    
    if budget_mode:
        mem_thread = threading.Thread(target=memory_watchdog_thread, args=(active_process,), daemon=True)
        mem_thread.start()
        
    return active_stream_info

def stop_stream():
    global active_process, active_stream_info
    if active_process is None:
        add_log("Stop Stream: No active stream is running.")
        return False
        
    add_log(f"Stopping active stream (PID: {active_process.pid})...")
    try:
        active_process.terminate()
        for _ in range(10):
            if active_process.poll() is not None:
                break
            time.sleep(0.2)
        else:
            active_process.kill()
            active_process.wait()
    except Exception as e:
        add_log(f"Error stopping stream process: {str(e)}")
        
    active_process = None
    active_stream_info["status"] = "idle"
    active_stream_info["title"] = None
    active_stream_info["url"] = None
    active_stream_info["start_time"] = None
    active_stream_info["pid"] = None
    active_stream_info["quality"] = None
    active_stream_info["health"] = "Disconnected"
    active_stream_info["is_sharded"] = False
    active_stream_info["shard_info"] = None
    active_stream_info["filesize_gb"] = None
    active_stream_info["metrics"] = {
        "bitrate": "N/A",
        "speed": "N/A",
        "fps": "N/A",
        "frame": "0",
        "time": "00:00:00"
    }
    cleanup_temp_cache()
    add_log("Stream stopped successfully.")
    return True

def get_live_status():
    global active_stream_info, log_messages
    status = dict(active_stream_info)
    status["logs"] = log_messages
    status["ffmpeg"] = get_ffmpeg_status()
    status["system"] = {
        "ram_available_mb": get_available_memory_mb(),
        "disk_available_mb": get_available_disk_mb(),
        "is_render": bool(os.environ.get("RENDER") or os.environ.get("RENDER_EXTERNAL_URL")),
    }
    return status
