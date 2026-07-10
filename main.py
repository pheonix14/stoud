import os
import uuid
import time
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

# Routing static assets directly
@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory('css', filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory('js', filename)

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    return send_from_directory('uploads', filename)

# HTML Page Routes
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


# REST API ENDPOINTS

# 1. Player Status & Health
@app.route('/api/status', methods=['GET'])
def get_status():
    status = player.get_live_status()
    # Add active queue info
    status["queue"] = [item for item in runner.current_queue]
    status["active_schedule_id"] = runner.active_schedule_id
    # Add loop settings to status
    config = settings_mgr.get_config()
    status["loop_current_video"] = config.get("settings", {}).get("loop_current_video", False)
    status["break_mode"] = config.get("settings", {}).get("break_mode", False)
    return jsonify(status)

# 2. File Uploads (Intro, Ending, Break Content)
@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No selected file"}), 400
        
    if file:
        filename = secure_filename(file.filename)
        # Check size to prevent exceeding 300MB disk limit
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)
        
        # Limit local upload size to 60MB (Warning warning but allow if space permits)
        if size > 60 * 1024 * 1024:
            return jsonify({"success": False, "error": "File size exceeds 60MB limit. To respect the 300MB disk space, use remote YouTube or Google Drive URLs instead!"}), 400
            
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Return public URL path
        url_path = f"/uploads/{filename}"
        return jsonify({"success": True, "url": url_path, "filename": filename})

# 3. Stream Controls
@app.route('/api/stream/start', methods=['POST'])
def api_start_stream():
    data = request.json or {}
    url = data.get("url")
    quality = data.get("quality", "copy")
    
    if not url:
        return jsonify({"success": False, "error": "URL parameter is required"}), 400
        
    custom_rtmp = data.get("rtmp_url")
    if custom_rtmp:
        destinations = [{
            "id": "custom",
            "name": "Custom Platform",
            "rtmp_url": custom_rtmp,
            "stream_key": "",
            "enabled": True
        }]
    else:
        config = settings_mgr.get_config()
        destinations = config.get("settings", {}).get("destinations", [])
        
    enabled_dests = [d for d in destinations if d.get("enabled")]
    
    if not enabled_dests:
        return jsonify({"success": False, "error": "No stream destinations configured. Set platforms in Settings or paste a direct RTMP link."}), 400
        
    try:
        runner.current_queue = []
        runner.active_schedule_id = None
        
        info = player.start_stream(url, destinations, quality)
        
        settings_mgr.update_active_stream({
            "status": "streaming",
            "current_video": {"title": info.get("title"), "url": url},
            "start_time": info.get("start_time")
        })
        return jsonify({"success": True, "stream": info})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/stream/stop', methods=['POST'])
def api_stop_stream():
    runner.current_queue = []
    runner.active_schedule_id = None
    success = player.stop_stream()
    
    settings_mgr.update_active_stream({
        "status": "idle",
        "current_video": None,
        "start_time": None
    })
    return jsonify({"success": success})

# 4. Live Queue Management
@app.route('/api/queue/add', methods=['POST'])
def api_add_queue():
    data = request.json or {}
    url = data.get("url")
    title = data.get("title", "Dynamic Queue Item")
    
    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400
        
    success = runner.add_to_queue(url, title)
    return jsonify({"success": success})

@app.route('/api/queue/<int:idx>', methods=['DELETE'])
def api_remove_queue(idx):
    success = runner.remove_from_queue(idx)
    return jsonify({"success": success})

@app.route('/api/queue/clear', methods=['POST'])
def api_clear_queue():
    runner.current_queue = []
    player.add_log("Active playback queue cleared.")
    return jsonify({"success": True})

# 5. Config & Settings
@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(settings_mgr.get_config())

@app.route('/api/settings', methods=['POST'])
def api_update_settings():
    data = request.json or {}
    success = settings_mgr.update_settings(data)
    return jsonify({"success": success})

# 6. Schedule Endpoints (with "Run Now" support)
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
        
    # Trigger it immediately by overriding its schedule time and setting it running
    runner.active_schedule_id = schedule_id
    settings_mgr.update_schedule_status(schedule_id, "running")
    target_url = schedule.get("url")
    
    settings = config.get("settings", {})
    intro_url = settings.get("intro_video_url", "")
    ending_url = settings.get("ending_video_url", "")
    
    items_to_queue = []
    if intro_url:
        items_to_queue.append({"url": intro_url, "title": "Intro Presentation"})
        
    if target_url.startswith("playlist:"):
        playlist_id = target_url.split(":")[1]
        playlists = config.get("playlists", [])
        playlist = next((p for p in playlists if p.get("id") == playlist_id), None)
        if playlist and playlist.get("items"):
            items_to_queue.extend(playlist.get("items"))
        else:
            return jsonify({"success": False, "error": "Playlist not found or empty."}), 400
    else:
        items_to_queue.append({"url": target_url, "title": schedule.get("name")})
        
    if ending_url:
        items_to_queue.append({"url": ending_url, "title": "Ending Credits"})
        
    runner.current_queue = items_to_queue
    player.add_log(f"Manual override: Initiated schedule '{schedule.get('name')}' immediately.")
    return jsonify({"success": True})

# 7. Playlist Endpoints
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

# 8. Saved Videos
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

# 9. FFmpeg Downloader
@app.route('/api/ffmpeg/download', methods=['POST'])
def api_download_ffmpeg():
    status = player.get_ffmpeg_status()
    if "Installed" in status:
        return jsonify({"success": True, "message": "FFmpeg is already installed."})
    player.download_ffmpeg_background()
    return jsonify({"success": True, "message": "Download started in background."})

# App setup
def init_app():
    os.makedirs(os.path.join(os.getcwd(), "logs"), exist_ok=True)
    status = player.get_ffmpeg_status()
    if status == "Not Installed":
        player.download_ffmpeg_background()

if __name__ == '__main__':
    init_app()
    # Start background tasks
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        runner.start_runner()
        
    print("Stoud v3 server running at http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
