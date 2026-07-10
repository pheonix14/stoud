import os
import re
import sys
import time
import subprocess
import threading
import urllib.request
import http.cookiejar
import tempfile
import zipfile

active_process = None
active_thread = None
log_messages = []
active_stream_info = {
    "status": "idle",
    "title": None,
    "url": None,
    "start_time": None,
    "pid": None,
    "quality": None
}

FFMPEG_STATUS = "Not Checked"
download_progress_message = ""

def get_ffmpeg_status():
    global FFMPEG_STATUS, download_progress_message
    if download_progress_message:
        return download_progress_message
        
    local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg.exe")
    local_ffprobe = os.path.join(os.getcwd(), "ffprobe.exe")
    
    if os.path.exists(local_ffmpeg) and os.path.exists(local_ffprobe):
        FFMPEG_STATUS = "Installed Locally"
        return "Installed Locally"
        
    # Check if ffmpeg is in path
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
    
    def update_progress(msg):
        global download_progress_message
        download_progress_message = msg
        print(f"FFmpeg Downloader: {msg}")
        
    def worker():
        global download_progress_message, FFMPEG_STATUS
        try:
            update_progress("Starting download of FFmpeg release archive...")
            zip_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            
            # Temporary zip path in current workspace
            temp_zip = os.path.join(os.getcwd(), "ffmpeg_temp.zip")
            
            req = urllib.request.Request(zip_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as resp:
                total_size = int(resp.headers.get('content-length', 0))
                downloaded = 0
                
                with open(temp_zip, "wb") as f:
                    while True:
                        chunk = resp.read(1024 * 1024)  # 1MB chunk
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            update_progress(f"Downloading FFmpeg: {percent}% ({downloaded // (1024*1024)}MB / {total_size // (1024*1024)}MB)")
                        else:
                            update_progress(f"Downloading FFmpeg: {downloaded // (1024*1024)}MB downloaded")
            
            update_progress("Extracting binaries from archive...")
            extracted_ffmpeg = False
            extracted_ffprobe = False
            
            with zipfile.ZipFile(temp_zip) as z:
                for file_info in z.infolist():
                    filename = file_info.filename
                    if filename.endswith("ffmpeg.exe") and not os.path.basename(filename).startswith("._"):
                        out_path = os.path.join(os.getcwd(), "ffmpeg.exe")
                        with z.open(file_info) as source, open(out_path, "wb") as target:
                            target.write(source.read())
                        extracted_ffmpeg = True
                    elif filename.endswith("ffprobe.exe") and not os.path.basename(filename).startswith("._"):
                        out_path = os.path.join(os.getcwd(), "ffprobe.exe")
                        with z.open(file_info) as source, open(out_path, "wb") as target:
                            target.write(source.read())
                        extracted_ffprobe = True
                        
            # Clean up zip
            try:
                os.remove(temp_zip)
            except Exception:
                pass
                
            if extracted_ffmpeg and extracted_ffprobe:
                update_progress("")
                FFMPEG_STATUS = "Installed Locally"
                print("FFmpeg installation complete!")
            else:
                update_progress("Failed: ffmpeg.exe or ffprobe.exe not found in downloaded zip.")
                FFMPEG_STATUS = "Extraction Failed"
                
        except Exception as e:
            update_progress(f"Failed: {str(e)}")
            FFMPEG_STATUS = "Download Failed"
            
    threading.Thread(target=worker, daemon=True).start()

def get_ffmpeg_executable():
    local_ffmpeg = os.path.join(os.getcwd(), "ffmpeg.exe")
    if os.path.exists(local_ffmpeg):
        return local_ffmpeg
    return "ffmpeg"

def add_log(message):
    global log_messages
    timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
    log_messages.append(f"{timestamp} {message}")
    if len(log_messages) > 300:
        log_messages.pop(0)

def resolve_youtube_url(url):
    import yt_dlp
    add_log(f"Resolving YouTube URL: {url}")
    # Force H264 video and AAC audio formats if possible to allow direct copy without transcoding
    ydl_opts = {
        'format': 'bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[vcodec^=avc1]/best',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            add_log(f"yt-dlp extraction failed: {str(e)}")
            raise Exception(f"yt-dlp extraction failed: {str(e)}")
            
        title = info.get('title', 'YouTube Video')
        
        # Check for separated formats
        requested_formats = info.get('requested_formats')
        if requested_formats and len(requested_formats) >= 2:
            video_url = requested_formats[0].get('url')
            audio_url = requested_formats[1].get('url')
            add_log(f"Resolved YouTube video. Format: Multi-stream (Separate Video/Audio).")
            return video_url, audio_url, title, False
        else:
            video_url = info.get('url')
            add_log(f"Resolved YouTube video. Format: Single-stream (Combined Video/Audio).")
            return video_url, None, title, True

def resolve_gdrive_url(url):
    add_log(f"Resolving Google Drive URL: {url}")
    file_id = None
    m = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if m:
        file_id = m.group(1)
    else:
        m = re.search(r'id=([a-zA-Z0-9_-]+)', url)
        if m:
            file_id = m.group(1)
            
    if not file_id:
        add_log("Google Drive ID not found in the link.")
        raise Exception("Could not parse Google Drive File ID from URL.")
        
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    
    confirm_url = f"https://docs.google.com/uc?export=download&id={file_id}"
    req = urllib.request.Request(confirm_url, headers={"User-Agent": "Mozilla/5.0"})
    
    try:
        with opener.open(req) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except Exception as e:
        add_log(f"Failed to fetch GDrive warning page: {str(e)}")
        raise Exception(f"Failed to fetch GDrive warning page: {str(e)}")
        
    confirm_token = None
    match = re.search(r'confirm=([a-zA-Z0-9_-]+)', html)
    if match:
        confirm_token = match.group(1)
        
    cookies = []
    for cookie in cj:
        cookies.append(f"{cookie.name}={cookie.value}")
    cookie_str = "; ".join(cookies) if cookies else None
    
    if confirm_token:
        direct_url = f"https://docs.google.com/uc?export=download&confirm={confirm_token}&id={file_id}"
        add_log("Bypassed Google Drive virus scan warning successfully.")
    else:
        direct_url = resp.geturl()
        add_log("Google Drive direct download link obtained.")
        
    return direct_url, cookie_str, f"GDrive Video ({file_id})"

def log_reader_thread(process):
    global active_stream_info, active_process
    try:
        # ffmpeg outputs logs to stderr
        while True:
            line = process.stderr.readline()
            if not line:
                break
            line_str = line.decode('utf-8', errors='ignore').strip()
            if line_str:
                add_log(f"[FFmpeg] {line_str}")
    except Exception as e:
        add_log(f"Error reading FFmpeg log: {str(e)}")
    finally:
        # Subprocess finished
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

def start_stream(video_url, rtmp_url, stream_key, quality="copy"):
    global active_process, active_thread, active_stream_info
    
    if active_process is not None:
        raise Exception("A stream is already active. Stop it first.")
        
    ffmpeg_exe = get_ffmpeg_executable()
    if get_ffmpeg_status() == "Not Installed":
        raise Exception("FFmpeg is not installed. Download it in Settings first.")
        
    full_rtmp_url = f"{rtmp_url.rstrip('/')}/{stream_key}"
    
    # Resolve the inputs
    is_youtube = "youtube.com" in video_url or "youtu.be" in video_url
    is_gdrive = "drive.google.com" in video_url
    
    video_input = None
    audio_input = None
    title = "Live Stream"
    is_combined = True
    cookie_str = None
    
    try:
        if is_youtube:
            video_input, audio_input, title, is_combined = resolve_youtube_url(video_url)
        elif is_gdrive:
            video_input, cookie_str, title = resolve_gdrive_url(video_url)
        else:
            # Direct link fallback
            video_input = video_url
            title = "Direct Video Stream"
            add_log(f"Streaming direct video link: {video_url}")
    except Exception as e:
        add_log(f"Error resolving stream: {str(e)}")
        raise e
        
    # Build FFmpeg command
    cmd = [ffmpeg_exe]
    
    # Global/Input parameters
    # Set headers/cookies for GDrive if available
    if cookie_str:
        cmd.extend(["-headers", f"Cookie: {cookie_str}\r\n"])
        
    # Standard input parameters: -re tells FFmpeg to read input in real-time speed (crucial for live streaming!)
    cmd.extend(["-re"])
    
    # Add input(s)
    cmd.extend(["-i", video_input])
    if audio_input:
        cmd.extend(["-re", "-i", audio_input])
        
    # Add mapping & coding logic based on quality setting
    if quality == "copy":
        if audio_input:
            cmd.extend([
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "copy",
                "-c:a", "aac",  # Transcode audio to AAC if it's not already, since RTMP requires AAC
                "-strict", "experimental"
            ])
        else:
            cmd.extend([
                "-c:v", "copy",
                "-c:a", "aac",  # Copy video codec, transcode audio to standard AAC
                "-strict", "experimental"
            ])
    else:
        # Transcoding options (720p H264 medium quality)
        add_log("Transcoding stream to H.264/AAC...")
        if audio_input:
            cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
            
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-b:v", "2500k",
            "-maxrate", "2500k",
            "-bufsize", "5000k",
            "-pix_fmt", "yuv420p",
            "-g", "60",         # Keyframe interval of 2 seconds for standard streaming
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100"
        ])
        
    # Output parameters
    cmd.extend([
        "-f", "flv",
        full_rtmp_url
    ])
    
    add_log(f"Launching FFmpeg streaming subprocess...")
    # Hide window on Windows to avoid annoying popups
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
    try:
        active_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            startupinfo=startupinfo
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
        "quality": quality
    }
    
    add_log(f"Stream started! PID: {active_process.pid}. Streaming '{title}' to target RTMP.")
    
    # Start reader thread to grab stderr logs
    active_thread = threading.Thread(target=log_reader_thread, args=(active_process,), daemon=True)
    active_thread.start()
    
    return active_stream_info

def stop_stream():
    global active_process, active_stream_info
    if active_process is None:
        add_log("Stop Stream: No active stream is running.")
        return False
        
    add_log(f"Stopping active stream (PID: {active_process.pid})...")
    try:
        active_process.terminate()
        # Wait a moment for it to terminate
        for _ in range(10):
            if active_process.poll() is not None:
                break
            time.sleep(0.2)
        else:
            # Force kill if it's still alive
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
    
    add_log("Stream stopped successfully.")
    return True

def get_live_status():
    global active_stream_info, log_messages
    status = dict(active_stream_info)
    status["logs"] = log_messages
    status["ffmpeg"] = get_ffmpeg_status()
    return status
