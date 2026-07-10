import time
import datetime
import threading
from settings import SettingsManager
import player

# Shared state for the background runner
runner_thread = None
runner_running = False
current_queue = []
active_schedule_id = None

def get_current_time():
    return datetime.datetime.now()

def parse_schedule_time(time_str):
    try:
        # Standard input datetime-local format: YYYY-MM-DDTHH:MM
        if "T" in time_str:
            return datetime.datetime.strptime(time_str, "%Y-%m-%dT%H:%M")
        return datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M")
    except Exception as e:
        print(f"Error parsing schedule time '{time_str}': {e}")
        return None

def runner_loop():
    global runner_running, current_queue, active_schedule_id
    
    settings_mgr = SettingsManager()
    print("Background runner loop started.")
    
    while runner_running:
        try:
            # Refresh config
            config = settings_mgr._load()
            schedules = config.get("schedules", [])
            settings = config.get("settings", {})
            active_stream = config.get("active_stream", {})
            
            now = get_current_time()
            
            # 1. Check if we need to trigger a new schedule
            for s in schedules:
                if s.get("status") == "scheduled":
                    sched_time = parse_schedule_time(s.get("time"))
                    if sched_time and sched_time <= now:
                        # Time to run!
                        print(f"Schedule '{s.get('name')}' is due.")
                        
                        # Check if a stream is already running
                        if player.active_process is not None:
                            player.add_log(f"Schedule skipped: '{s.get('name')}' was triggered, but another stream is currently active.")
                            settings_mgr.update_schedule_status(s.get("id"), "failed")
                            continue
                            
                        # Set active schedule
                        active_schedule_id = s.get("id")
                        settings_mgr.update_schedule_status(active_schedule_id, "running")
                        
                        # Populate queue
                        target_url = s.get("url")
                        
                        if target_url.startswith("playlist:"):
                            playlist_id = target_url.split(":")[1]
                            # Find the playlist
                            playlists = config.get("playlists", [])
                            playlist = next((p for p in playlists if p.get("id") == playlist_id), None)
                            
                            if playlist and playlist.get("items"):
                                current_queue = list(playlist.get("items"))
                                player.add_log(f"Triggered playlist schedule '{s.get('name')}' with {len(current_queue)} items.")
                            else:
                                player.add_log(f"Schedule failed: Playlist '{playlist_id}' not found or is empty.")
                                settings_mgr.update_schedule_status(active_schedule_id, "failed")
                                active_schedule_id = None
                                current_queue = []
                        else:
                            # Single video
                            current_queue = [{"url": target_url, "title": s.get("name")}]
                            player.add_log(f"Triggered video schedule '{s.get('name')}'.")
                            
            # 2. Manage the queue & player
            if player.active_process is None:
                # Player is idle
                if current_queue:
                    # We have items in the queue to play!
                    next_item = current_queue.pop(0)
                    url = next_item.get("url")
                    title = next_item.get("title", "Video Queue Item")
                    
                    rtmp_url = settings.get("rtmp_url")
                    stream_key = settings.get("stream_key")
                    quality = settings.get("quality", "copy")
                    
                    if not rtmp_url or not stream_key:
                        player.add_log("Streaming error: RTMP URL or Stream Key is not configured.")
                        current_queue = []
                        if active_schedule_id:
                            settings_mgr.update_schedule_status(active_schedule_id, "failed")
                            active_schedule_id = None
                    else:
                        try:
                            player.add_log(f"Queue: Starting next item: '{title}' ({url})")
                            player.start_stream(url, rtmp_url, stream_key, quality)
                            # Sync stream status to config
                            settings_mgr.update_active_stream({
                                "status": "streaming",
                                "current_video": {"title": title, "url": url},
                                "start_time": time.time()
                            })
                        except Exception as e:
                            player.add_log(f"Queue error playing '{title}': {str(e)}")
                            # Skip this item and continue loop in next ticks
                else:
                    # Player is idle and queue is empty
                    # If we had a running schedule, mark it as completed
                    if active_schedule_id:
                        print(f"Schedule {active_schedule_id} completed successfully.")
                        settings_mgr.update_schedule_status(active_schedule_id, "completed")
                        active_schedule_id = None
                        
                    # Sync idle status to config if not already sync'd
                    if active_stream.get("status") != "idle":
                        settings_mgr.update_active_stream({
                            "status": "idle",
                            "current_video": None,
                            "start_time": None
                        })
            else:
                # Stream is running, sync runtime stats to config
                # Keep active stream state up-to-date in config.json
                live_status = player.get_live_status()
                settings_mgr.update_active_stream({
                    "status": "streaming",
                    "current_video": {"title": live_status.get("title"), "url": live_status.get("url")},
                    "start_time": live_status.get("start_time")
                })
                
        except Exception as e:
            print(f"Error in runner loop iteration: {e}")
            
        time.sleep(5)

def start_runner():
    global runner_thread, runner_running
    if runner_running:
        return
    runner_running = True
    runner_thread = threading.Thread(target=runner_loop, daemon=True)
    runner_thread.start()
    print("Background scheduling runner thread started.")

def stop_runner():
    global runner_running
    runner_running = False
    print("Background scheduling runner thread stopped.")
