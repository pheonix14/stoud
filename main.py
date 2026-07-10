import os
import uuid
import time
from flask import Flask, jsonify, request, render_template, send_from_directory
from settings import SettingsManager
import player
import runner

app = Flask(__name__, template_folder='.', static_folder='.')
settings_mgr = SettingsManager()

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

# Static files fallback (e.g. style.css)
@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

# API ENDPOINTS

# 1. Player Status & Controls
@app.route('/api/status', methods=['GET'])
def get_status():
    status = player.get_live_status()
    # Add scheduler queue info
    status["queue"] = [item for item in runner.current_queue]
    status["active_schedule_id"] = runner.active_schedule_id
    return jsonify(status)

@app.route('/api/stream/start', methods=['POST'])
def api_start_stream():
    data = request.json or {}
    url = data.get("url")
    quality = data.get("quality", "copy")
    
    if not url:
        return jsonify({"success": False, "error": "URL parameter is required"}), 400
        
    config = settings_mgr.get_config()
    rtmp_url = config.get("settings", {}).get("rtmp_url")
    stream_key = config.get("settings", {}).get("stream_key")
    
    if not rtmp_url or not stream_key:
        return jsonify({"success": False, "error": "RTMP URL and Stream Key must be configured first in Settings."}), 400
        
    try:
        # Clear manual queue and active schedule
        runner.current_queue = []
        runner.active_schedule_id = None
        
        info = player.start_stream(url, rtmp_url, stream_key, quality)
        
        # Sync immediately
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
    # Stop active stream and clear current queue
    runner.current_queue = []
    runner.active_schedule_id = None
    success = player.stop_stream()
    
    # Sync immediately
    settings_mgr.update_active_stream({
        "status": "idle",
        "current_video": None,
        "start_time": None
    })
    return jsonify({"success": success})

# 2. Config & Settings
@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify(settings_mgr.get_config())

@app.route('/api/settings', methods=['POST'])
def api_update_settings():
    data = request.json or {}
    success = settings_mgr.update_settings(data)
    return jsonify({"success": success})

# 3. Schedule Endpoints
@app.route('/api/schedules', methods=['GET'])
def get_schedules():
    return jsonify(settings_mgr.get_schedules())

@app.route('/api/schedules', methods=['POST'])
def add_schedule():
    data = request.json or {}
    name = data.get("name")
    url = data.get("url")
    time_str = data.get("time") # format: YYYY-MM-DDTHH:MM
    
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

# 4. Playlist Endpoints
@app.route('/api/playlists', methods=['GET'])
def get_playlists():
    return jsonify(settings_mgr.get_playlists())

@app.route('/api/playlists', methods=['POST'])
def add_playlist():
    data = request.json or {}
    playlist_id = data.get("id")
    name = data.get("name")
    items = data.get("items", []) # List of {url, title}
    
    if not name:
        return jsonify({"success": False, "error": "Playlist name is required"}), 400
        
    if playlist_id:
        # Edit existing
        playlist = {
            "id": playlist_id,
            "name": name,
            "items": items
        }
        success = settings_mgr.update_playlist(playlist_id, playlist)
    else:
        # Create new
        playlist = {
            "id": str(uuid.uuid4()),
            "name": name,
            "items": items
        }
        success = settings_mgr.add_playlist(playlist)
        
    return jsonify({"success": success, "playlist": playlist})

@app.route('/api/playlists/<playlist_id>', methods=['DELETE'])
def delete_playlist(playlist_id):
    success = settings_mgr.delete_playlist(playlist_id)
    return jsonify({"success": success})

# 5. Saved Videos Endpoints
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

# 6. FFmpeg Downloader trigger
@app.route('/api/ffmpeg/download', methods=['POST'])
def api_download_ffmpeg():
    status = player.get_ffmpeg_status()
    if "Installed" in status:
        return jsonify({"success": True, "message": "FFmpeg is already installed."})
    
    player.download_ffmpeg_background()
    return jsonify({"success": True, "message": "Download started in background."})

# Initialize application setup
def init_app():
    # Create logs directory if not exists
    os.makedirs(os.path.join(os.getcwd(), "logs"), exist_ok=True)
    # Check/Download FFmpeg on start if not present
    status = player.get_ffmpeg_status()
    if status == "Not Installed":
        player.download_ffmpeg_background()

# Main entry
if __name__ == '__main__':
    init_app()
    # Start the background runner
    # We check WERKZEUG_RUN_MAIN to ensure thread only starts once when reloader is active
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        runner.start_runner()
        
    print("Stoud v2 server running at http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
