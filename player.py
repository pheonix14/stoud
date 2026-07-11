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
    "quality": None,
    "metrics": {
        "bitrate": "N/A",
        "speed": "N/A",
        "fps": "N/A",
        "frame": "0",
        "time": "00:00:00"
    },
    "health": "Unknown"
}

FFMPEG_STATUS = "Not Checked"
download_progress_message = ""

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
    
    if sys.platform != "win32":
        download_progress_message = "Platform is not Windows. FFmpeg should be installed via package manager."
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
    if sys.platform == "win32":
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

def extract_playlist_items(url):
    import yt_dlp
    add_log(f"Extracting playlist items for: {url}")
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'no_warnings': True,
    }
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
            add_log(f"yt-dlp playlist extraction failed: {str(e)}")
            raise Exception(f"Failed to extract playlist: {str(e)}")
    return items

def resolve_youtube_url(url):
    import yt_dlp
    add_log(f"Resolving YouTube URL: {url}")
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
        requested_formats = info.get('requested_formats')
        if requested_formats and len(requested_formats) >= 2:
            video_url = requested_formats[0].get('url')
            audio_url = requested_formats[1].get('url')
            add_log("Resolved YouTube video. Format: Multi-stream.")
            return video_url, audio_url, title, False
        else:
            video_url = info.get('url')
            add_log("Resolved YouTube video. Format: Single-stream.")
            return video_url, None, title, True

def resolve_gdrive_url(url):
    import yt_dlp
    add_log(f"Resolving Google Drive URL: {url}")
    
    file_id = None
    m = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if m:
        file_id = m.group(1)
    else:
        m = re.search(r'id=([a-zA-Z0-9_-]+)', url)
        if m:
            file_id = m.group(1)
            
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            add_log(f"yt-dlp GDrive extraction failed: {str(e)}")
            raise Exception(f"yt-dlp GDrive extraction failed: {str(e)}")
            
        title = info.get('title', f'GDrive Video ({file_id})') if info.get('title') else f'GDrive Video ({file_id})'
        video_url = info.get('url')
        user_agent = info.get('http_headers', {}).get('User-Agent', '')
        
        add_log(f"Google Drive direct streaming link obtained via yt-dlp: {video_url}")
        return video_url, user_agent, title

# Regex to parse FFmpeg terminal outputs in real-time
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
                # Add to text logs
                add_log(f"[FFmpeg] {line_str}")
                
                # Parse metrics in real-time
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
            active_stream_info["metrics"] = {
                "bitrate": "N/A",
                "speed": "N/A",
                "fps": "N/A",
                "frame": "0",
                "time": "00:00:00"
            }

def start_stream(video_url, destinations, quality="copy", budget_mode=False):
    global active_process, active_thread, active_stream_info
    
    if active_process is not None:
        raise Exception("A stream is already active. Stop it first.")
        
    ffmpeg_exe = get_ffmpeg_executable()
    if get_ffmpeg_status() == "Not Installed":
        raise Exception("FFmpeg is not installed.")
        
    enabled_dests = [d for d in destinations if d.get("enabled")]
    if not enabled_dests:
        raise Exception("No active stream destinations configured/enabled.")
        
    # Resolve the inputs
    is_youtube = "youtube.com" in video_url or "youtu.be" in video_url
    is_gdrive = "drive.google.com" in video_url
    
    video_input = None
    audio_input = None
    title = "Live Stream"
    is_combined = True
    user_agent_str = None
    
    try:
        if is_youtube:
            video_input, audio_input, title, is_combined = resolve_youtube_url(video_url)
        elif is_gdrive:
            video_input, user_agent_str, title = resolve_gdrive_url(video_url)
        else:
            video_input = video_url
            title = "Direct Video Stream"
            add_log(f"Streaming direct video link: {video_url}")
    except Exception as e:
        add_log(f"Error resolving stream: {str(e)}")
        raise e
        
    # Build FFmpeg command
    cmd = [ffmpeg_exe]
    
    if user_agent_str:
        cmd.extend(["-user_agent", user_agent_str])
        
    cmd.extend(["-nostdin", "-y", "-re"])
    
    if budget_mode:
        cmd.extend(["-threads", "1"])
    
    # Add input
    cmd.extend(["-i", video_input])
    if audio_input:
        cmd.extend(["-re", "-i", audio_input])
        
    # For multiple outputs, we specify mapping and output parameters for EACH destination
    for dest in enabled_dests:
        full_rtmp_url = dest['rtmp_url']
        if dest.get('stream_key'):
            full_rtmp_url = f"{full_rtmp_url.rstrip('/')}/{dest['stream_key']}"
        
        if quality == "copy":
            copy_args = [
                "-c:v", "copy",
                "-c:a", "aac",
                "-strict", "experimental"
            ]
            if budget_mode:
                copy_args.extend(["-max_muxing_queue_size", "256"])
                
            if audio_input:
                cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
                
            cmd.extend(copy_args)
            cmd.extend(["-f", "flv", full_rtmp_url])
        else:
            if audio_input:
                cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
            
            transcode_args = [
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-pix_fmt", "yuv420p",
                "-g", "60",
                "-c:a", "aac",
                "-b:a", "128k",
                "-ar", "44100"
            ]
            
            if budget_mode:
                transcode_args.extend([
                    "-b:v", "1500k",
                    "-maxrate", "1500k",
                    "-bufsize", "1000k",
                    "-max_muxing_queue_size", "256"
                ])
            else:
                transcode_args.extend([
                    "-b:v", "2500k",
                    "-maxrate", "2500k",
                    "-bufsize", "5000k"
                ])
                
            cmd.extend(transcode_args)
            cmd.extend(["-f", "flv", full_rtmp_url])
            
    add_log(f"Launching FFmpeg streaming subprocess to {len(enabled_dests)} platforms...")
    
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
    try:
        active_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
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
        "quality": quality,
        "metrics": {
            "bitrate": "N/A",
            "speed": "N/A",
            "fps": "N/A",
            "frame": "0",
            "time": "00:00:00"
        },
        "health": "Active"
    }
    
    add_log(f"Stream started! PID: {active_process.pid}. Broadcasting to platforms.")
    
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
    active_stream_info["metrics"] = {
        "bitrate": "N/A",
        "speed": "N/A",
        "fps": "N/A",
        "frame": "0",
        "time": "00:00:00"
    }
    
    add_log("Stream stopped successfully.")
    return True

def get_live_status():
    global active_stream_info, log_messages
    status = dict(active_stream_info)
    status["logs"] = log_messages
    status["ffmpeg"] = get_ffmpeg_status()
    return status
