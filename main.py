import os
import uuid
import time
import gc
from flask import Flask, jsonify, request, render_template, send_from_directory
from werkzeug.utils import secure_filename
from settings import SettingsManager
import player
import runner

app = Flask(__name__, template_folder='pages')
settings_mgr = SettingsManager()

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
# Limit max content length to 60MB to protect Render ephemeral disk
app.config['MAX_CONTENT_LENGTH'] = 60 * 1024 * 1024

# ============================================================
# STATIC ASSET & HTML PAGE ROUTES
# ============================================================
@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory('css', filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory('js', filename)

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory('uploads', filename)

@app.route('/')
def index_route():
    return render_template('index.html')

@app.route('/scheduled')
def scheduled_route():
    return render_template('scheduled.html')

@app.route('/playlists')
def playlists_route():
    return render_template('playlists.html')

@app.route('/saved')
def saved_route():
    return render_template('saved.html')

@app.route('/settings')
def settings_route():
    return render_template('settings.html')


# ============================================================
# REST API ENDPOINTS
# ============================================================

# 1. Player Status & Health
@app.route('/api/status', methods=['GET'])
def get_status():
    status = player.get_live_status()
    status["queue"] = [item for item in runner.current_queue]
    status["active_schedule_id"] = runner.active_schedule_id
    config = settings_mgr.get_config()
    settings = config.get("settings", {})
    status["loop_current_video"] = settings.get("loop_current_video", False)
    status["break_mode"] = settings.get("break_mode", False)
    status["budget_mode"] = settings.get("budget_mode", True)
    status["auto_shard_drive"] = settings.get("auto_shard_drive", True)
    status["shard_duration_minutes"] = settings.get("shard_duration_minutes", 30)
    return jsonify(status)

# 2. Media Inspection (for 50GB file detection & auto-shard suggestions)
@app.route('/api/media/inspect', methods=['POST'])
def api_inspect_media():
    data = request.json or {}
    url = data.get("url")
    if not url:
        return jsonify({"success": False, "error": "URL parameter is required"}), 400
    try:
        info = player.inspect_media(url)
        return jsonify({"success": True, "info": info})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# 3. File Uploads (Protected for Render free disk)
@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400
        
    if file:
        filename = secure_filename(file.filename)
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        
        if size > 60 * 1024 * 1024:
            return jsonify({"success": False, "error": "File exceeds 60MB limit. For large or 50GB files, paste a Google Drive link!"}), 400
            
        disk_mb = player.get_available_disk_mb()
        file_mb = size // (1024 * 1024)
        if file_mb > disk_mb - 50:
            return jsonify({"success": False, "error": f"Insufficient disk space ({disk_mb}MB free)."}), 400
            
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        return jsonify({"success": True, "url": f"/uploads/{filename}", "filename": filename})

# 4. Stream Controls (With 50GB Google Drive Sharding Support)
@app.route('/api/stream/start', methods=['POST'])
def api_start_stream():
    data = request.json or {}
    url = data.get("url")
    quality = data.get("quality", "copy")
    custom_rtmp = data.get("rtmp_url")
    force_shard = data.get("shard", None)
    shard_mins = data.get("shard_minutes", None)
    
    if not url:
        return jsonify({"success": False, "error": "URL parameter is required"}), 400
        
    config = settings_mgr.get_config()
    settings = config.get("settings", {})
    budget_mode = settings.get("budget_mode", True)
    
    if shard_mins is None:
        shard_mins = settings.get("shard_duration_minutes", 30)
    else:
        shard_mins = int(shard_mins)
        
    if custom_rtmp:
        destinations = [{
            "id": "custom",
            "name": "Custom Platform",
            "rtmp_url": custom_rtmp,
            "stream_key": "",
            "enabled": True
        }]
    else:
        destinations = settings.get("destinations", [])
        
    enabled_dests = [d for d in destinations if d.get("enabled")]
    if not enabled_dests:
        return jsonify({"success": False, "error": "No stream destinations enabled. Configure in Settings or enter direct RTMP link."}), 400
        
    for d in enabled_dests:
        if d.get("rtmp_url") == "rtmp://a.rtmp.youtube.com/live2" and not d.get("stream_key"):
            return jsonify({"success": False, "error": f"Stream key missing for '{d.get('name')}'. Configure it in Settings."}), 400
            
    gc.collect()
    
    try:
        # Determine whether to use sharded queue
        is_gdrive = "drive.google.com" in url
        is_youtube = ("youtube.com" in url or "youtu.be" in url) and ("list=" not in url and "playlist" not in url)
        auto_shard_setting = settings.get("auto_shard_drive", True)
        
        if force_shard is not None:
            use_sharding = force_shard
        elif auto_shard_setting:
            if is_gdrive:
                use_sharding = True
            elif is_youtube:
                info = player.inspect_media(url)
                use_sharding = bool(info.get("duration") and info.get("duration") > shard_mins * 60)
            else:
                use_sharding = False
        else:
            use_sharding = False
        
        # A: YouTube Playlist
        if "list=" in url or "playlist" in url:
            items = player.extract_playlist_items(url)
            if not items:
                return jsonify({"success": False, "error": "Playlist is empty or invalid."}), 400
            first_item = items.pop(0)
            runner.current_queue = items
            runner.active_schedule_id = None
            info = player.start_stream(first_item["url"], enabled_dests, quality, budget_mode=budget_mode)
            settings_mgr.update_active_stream({
                "status": "streaming",
                "current_video": {"title": first_item.get("title", info.get("title")), "url": first_item["url"]},
                "start_time": info.get("start_time")
            })
            return jsonify({"success": True, "stream": info, "sharded": False})
            
        # B: Google Drive 50GB or Long YouTube Video Sharding Mode
        if use_sharding:
            media_label = "YouTube Video" if is_youtube else "Google Drive Video"
            player.add_log(f"[Sharder] Triggering Sharded Stream Pipeline for {media_label} ({shard_mins}m per shard)...")
            runner.current_queue = []
            success, shard_count = runner.add_sharded_to_queue(url, data.get("title", media_label), shard_duration_minutes=shard_mins)
            
            if runner.current_queue:
                first_item = runner.current_queue.pop(0)
                shard_info = {
                    "index": first_item.get("shard_index", 1),
                    "total": first_item.get("shard_total", shard_count)
                }
                info = player.start_stream(
                    first_item["url"],
                    enabled_dests,
                    quality,
                    budget_mode=budget_mode,
                    start_offset=first_item.get("start_offset", 0),
                    duration=first_item.get("duration"),
                    shard_info=shard_info
                )
                settings_mgr.update_active_stream({
                    "status": "streaming",
                    "current_video": {"title": first_item.get("title"), "url": first_item["url"]},
                    "start_time": info.get("start_time")
                })
                return jsonify({
                    "success": True,
                    "stream": info,
                    "sharded": True,
                    "total_shards": shard_count,
                    "message": f"Successfully launched Shard 1 of {shard_count}. Remaining shards are queued."
                })
                
        # C: Standard Single Stream
        intro_enabled = settings.get("intro_enabled", False)
        outro_enabled = settings.get("outro_enabled", False)
        intro_url = settings.get("intro_video_url", "")
        ending_url = settings.get("ending_video_url", "")
        
        final_queue = []
        if intro_enabled and intro_url:
            intro_media = player.get_media_from_path(intro_url)
            if intro_media:
                final_queue.append({"url": intro_media, "title": "Intro Presentation"})
                
        final_queue.append({"url": url, "title": data.get("title", "Main Stream Video")})
        
        if outro_enabled and ending_url:
            outro_media = player.get_media_from_path(ending_url)
            if outro_media:
                final_queue.append({"url": outro_media, "title": "Ending Credits"})
                
        first_item = final_queue.pop(0)
        runner.current_queue = final_queue
        runner.active_schedule_id = None
        
        info = player.start_stream(first_item["url"], enabled_dests, quality, budget_mode=budget_mode)
        settings_mgr.update_active_stream({
            "status": "streaming",
            "current_video": {"title": first_item.get("title", info.get("title")), "url": first_item["url"]},
            "start_time": info.get("start_time")
        })
        return jsonify({"success": True, "stream": info, "sharded": False})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/stream/stop', methods=['POST'])
def api_stop_stream():
    runner.current_queue = []
    runner.active_schedule_id = None
    success = player.stop_stream()
    gc.collect()
    settings_mgr.update_active_stream({
        "status": "idle",
        "current_video": None,
        "start_time": None
    })
    return jsonify({"success": success})

# 5. Live Queue Management
@app.route('/api/queue/add', methods=['POST'])
def api_add_queue():
    data = request.json or {}
    url = data.get("url")
    title = data.get("title", "Dynamic Queue Item")
    auto_shard = data.get("auto_shard", None)
    
    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400
        
    success = runner.add_to_queue(url, title, auto_shard=auto_shard)
    return jsonify({"success": success})

@app.route('/api/queue/shard_video', methods=['POST'])
def api_shard_video_queue():
    """Explicitly shard a video and add all shards to queue."""
    data = request.json or {}
    url = data.get("url")
    title = data.get("title", "Sharded Video")
    shard_mins = int(data.get("shard_minutes", 30))
    
    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400
        
    success, count = runner.add_sharded_to_queue(url, title, shard_duration_minutes=shard_mins)
    return jsonify({"success": success, "total_shards": count})

@app.route('/api/queue/<int:idx>', methods=['DELETE'])
def api_remove_queue(idx):
    success = runner.remove_from_queue(idx)
    return jsonify({"success": success})

@app.route('/api/queue/clear', methods=['POST'])
def api_clear_queue():
    runner.current_queue = []
    player.add_log("Active playback queue cleared.")
    return jsonify({"success": True})

# 6. Config & Settings
@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(settings_mgr.get_config())

@app.route('/api/settings', methods=['POST'])
def api_update_settings():
    data = request.json or {}
    success = settings_mgr.update_settings(data)
    return jsonify({"success": success})

# 7. Schedule Endpoints
@app.route('/api/schedules', methods=['GET'])
def get_schedules():
    return jsonify(settings_mgr.get_schedules())

@app.route('/api/schedules', methods=['POST'])
def add_schedule():
    data = request.json or {}
    name = data.get("name")
    url = data.get("url")
    time_str = data.get("time")
    
    if not name or not url or not time_str:
        return jsonify({"success": False, "error": "Name, URL, and Time are required"}), 400
        
    new_schedule = {
        "id": str(uuid.uuid4()),
        "name": name,
        "url": url,
        "time": time_str,
        "status": "scheduled"
    }
    success = settings_mgr.add_schedule(new_schedule)
    return jsonify({"success": success, "schedule": new_schedule})

@app.route('/api/schedules/<schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    success = settings_mgr.delete_schedule(schedule_id)
    return jsonify({"success": success})

@app.route('/api/schedules/<schedule_id>/run', methods=['POST'])
def run_schedule_now(schedule_id):
    config = settings_mgr.get_config()
    schedules = config.get("schedules", [])
    schedule = next((s for s in schedules if s.get("id") == schedule_id), None)
    
    if not schedule:
        return jsonify({"success": False, "error": "Schedule not found."}), 404
        
    if player.active_process is not None:
        return jsonify({"success": False, "error": "Cannot stream now: another stream is active."}), 400
        
    runner.active_schedule_id = schedule_id
    settings_mgr.update_schedule_status(schedule_id, "running")
    target_url = schedule.get("url")
    
    settings = config.get("settings", {})
    if settings.get("auto_shard_drive", True) and "drive.google.com" in target_url:
        runner.current_queue = []
        runner.add_sharded_to_queue(target_url, schedule.get("name"), shard_duration_minutes=settings.get("shard_duration_minutes", 30))
    else:
        runner.current_queue = [{"url": target_url, "title": schedule.get("name")}]
        
    player.add_log(f"Manual override: Initiated schedule '{schedule.get('name')}' immediately.")
    return jsonify({"success": True})

# 8. Playlists & Saved
@app.route('/api/playlists', methods=['GET'])
def get_playlists():
    return jsonify(settings_mgr.get_playlists())

@app.route('/api/playlists', methods=['POST'])
def add_playlist():
    data = request.json or {}
    playlist_id = data.get("id")
    name = data.get("name")
    items = data.get("items", [])
    
    if not name:
        return jsonify({"success": False, "error": "Playlist name is required"}), 400
        
    if playlist_id:
        playlist = {"id": playlist_id, "name": name, "items": items}
        success = settings_mgr.update_playlist(playlist_id, playlist)
    else:
        playlist = {"id": str(uuid.uuid4()), "name": name, "items": items}
        success = settings_mgr.add_playlist(playlist)
    return jsonify({"success": success, "playlist": playlist})

@app.route('/api/playlists/<playlist_id>', methods=['DELETE'])
def delete_playlist(playlist_id):
    success = settings_mgr.delete_playlist(playlist_id)
    return jsonify({"success": success})

@app.route('/api/saved', methods=['GET'])
def get_saved():
    return jsonify(settings_mgr.get_saved_videos())

@app.route('/api/saved', methods=['POST'])
def add_saved():
    data = request.json or {}
    title = data.get("title")
    url = data.get("url")
    
    if not title or not url:
        return jsonify({"success": False, "error": "Title and URL are required"}), 400
        
    video_type = "youtube" if ("youtube.com" in url or "youtu.be" in url) else ("gdrive" if "drive.google.com" in url else "direct")
    new_video = {
        "id": str(uuid.uuid4()),
        "title": title,
        "url": url,
        "type": video_type
    }
    success = settings_mgr.add_saved_video(new_video)
    return jsonify({"success": success, "video": new_video})

@app.route('/api/saved/<video_id>', methods=['DELETE'])
def delete_saved(video_id):
    success = settings_mgr.delete_saved_video(video_id)
    return jsonify({"success": success})

# 9. FFmpeg Setup
@app.route('/api/ffmpeg/download', methods=['POST'])
def api_download_ffmpeg():
    status = player.get_ffmpeg_status()
    if "Installed" in status:
        return jsonify({"success": True, "message": "FFmpeg is already installed."})
    player.download_ffmpeg_background()
    return jsonify({"success": True, "message": "Download started in background."})

# 10. Render Free-Tier Health & Diagnostic Check
@app.route('/api/health', methods=['GET'])
def api_health():
    """Endpoint for Render health checks and uptime pingers."""
    return jsonify({
        "status": "healthy",
        "app": "Stoud v3.4.0 (50GB Shard Edition)",
        "ram_available_mb": player.get_available_memory_mb(),
        "disk_available_mb": player.get_available_disk_mb(),
        "is_streaming": player.active_process is not None,
        "queue_length": len(runner.current_queue),
        "is_sharded": player.active_stream_info.get("is_sharded", False),
        "shard_info": player.active_stream_info.get("shard_info"),
        "render_url": os.environ.get("RENDER_EXTERNAL_URL", "local")
    })

# ============================================================
# APP INITIALIZATION
# ============================================================
def init_app():
    os.makedirs(os.path.join(os.getcwd(), "logs"), exist_ok=True)
    status = player.get_ffmpeg_status()
    if status == "Not Installed":
        player.download_ffmpeg_background()

# Initialize immediately so Gunicorn starts runner automatically
init_app()
runner.start_runner()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"Stoud v3 running at http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
