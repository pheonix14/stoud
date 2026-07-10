import time
import datetime
import threading
import urllib.request
from settings import SettingsManager
import player

# Shared state for the background runner
runner_thread = None
runner_running = False
current_queue = []
active_schedule_id = None
auto_ping_thread = None

def get_current_time():
    return datetime.datetime.now()

def parse_schedule_time(time_str):
    try:
        if "T" in time_str:
            return datetime.datetime.strptime(time_str, "%Y-%m-%dT%H:%M")
        return datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M")
    except Exception as e:
        print(f"Error parsing schedule time '{time_str}': {e}")
        return None

def add_to_queue(url, title):
    global current_queue
    # Detect video type
    video_type = "youtube" if ("youtube.com" in url or "youtu.be" in url) else ("gdrive" if "drive.google.com" in url else "direct")
    item = {"url": url, "title": title, "type": video_type}
    current_queue.append(item)
    player.add_log(f"Added video to active queue: '{title}'")
    return True

def remove_from_queue(idx):
    global current_queue
    if 0 <= idx < len(current_queue):
        removed = current_queue.pop(idx)
        player.add_log(f"Removed video from active queue: '{removed.get('title')}'")
        return True
    return False

def pinger_loop():
    print("Auto-pinger thread started.")
    settings_mgr = SettingsManager()
    
    while runner_running:
        try:
            config = settings_mgr._load_local()
            ping_url = config.get("settings", {}).get("auto_ping_url", "")
            
            # Fallback to localhost if no public URL configured
            target_url = ping_url if ping_url else "http://127.0.0.1:5000/api/status"
            
            req = urllib.request.Request(target_url, headers={"User-Agent": "Stoud-v2-KeepAlive-Pinger"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
                # Print debug log only if pinging external URL
                if ping_url:
                    print(f"Keep-Alive: Successfully pinged external url {ping_url}")
        except Exception as e:
            # Silence local pinger errors to avoid spamming terminal log
            if ping_url:
                print(f"Keep-Alive Error: Could not ping {ping_url}: {e}")
        time.sleep(7)

def runner_loop():
    global runner_running, current_queue, active_schedule_id
    
    settings_mgr = SettingsManager()
    print("Background runner and watchdog loop started.")
    
    while runner_running:
        try:
            # Refresh config
            config = settings_mgr.get_config()
            schedules = config.get("schedules", [])
            settings = config.get("settings", {})
            active_stream = config.get("active_stream", {})
            
            destinations = settings.get("destinations", [])
            quality = settings.get("quality", "copy")
            
            break_mode = settings.get("break_mode", False)
            break_video_url = settings.get("break_video_url", "")
            intro_url = settings.get("intro_video_url", "")
            ending_url = settings.get("ending_video_url", "")
            
            now = get_current_time()
            
            # 1. Manage Watchdog and Queue Playback
            if player.active_process is None:
                # Player is idle
                
                # Check Loop: If loop_current_video is enabled and we were just streaming, re-queue the video
                was_streaming = (active_stream.get("status") == "streaming")
                last_video = active_stream.get("current_video")
                if was_streaming and last_video and settings.get("loop_current_video", False) and not break_mode:
                    current_queue.insert(0, {"url": last_video.get("url"), "title": last_video.get("title")})
                    player.add_log(f"Loop Active: Re-queuing '{last_video.get('title')}' to play again.")
                
                # Check A: If Break Mode is active, stream break content on a loop
                if break_mode:
                    if break_video_url:
                        try:
                            player.add_log(f"Watchdog: Break Mode is Active. Starting Break Stream: {break_video_url}")
                            player.start_stream(break_video_url, destinations, quality)
                            settings_mgr.update_active_stream({
                                "status": "streaming",
                                "current_video": {"title": "Break Stream", "url": break_video_url},
                                "start_time": time.time()
                            })
                        except Exception as e:
                            player.add_log(f"Watchdog: Failed to start break stream: {e}")
                    else:
                        player.add_log("Watchdog: Break Mode is Active, but Break Video URL is not configured.")
                        
                # Check B: Play next item in queue if queue has items and break_mode is false
                elif current_queue:
                    next_item = current_queue.pop(0)
                    url = next_item.get("url")
                    title = next_item.get("title", "Video Queue Item")
                    
                    try:
                        player.add_log(f"Queue: Starting next item: '{title}'")
                        player.start_stream(url, destinations, quality)
                        settings_mgr.update_active_stream({
                            "status": "streaming",
                            "current_video": {"title": title, "url": url},
                            "start_time": time.time()
                        })
                    except Exception as e:
                        player.add_log(f"Queue error playing '{title}': {str(e)}")
                        
                # Check C: Queue is empty. If we were running a schedule, mark it completed
                else:
                    if active_schedule_id:
                        print(f"Schedule {active_schedule_id} completed successfully.")
                        settings_mgr.update_schedule_status(active_schedule_id, "completed")
                        active_schedule_id = None
                        
                    # Sync idle status to config
                    if active_stream.get("status") != "idle":
                        settings_mgr.update_active_stream({
                            "status": "idle",
                            "current_video": None,
                            "start_time": None
                        })
            else:
                # Stream is running
                
                # Watchdog check: If break_mode is enabled but we are currently streaming normal content, 
                # terminate it so break content can start immediately
                if break_mode and active_stream.get("current_video", {}).get("title") != "Break Stream":
                    player.add_log("Watchdog: Break Mode turned ON. Terminating active content...")
                    player.stop_stream()
                # Watchdog check: If break_mode is disabled but we are currently streaming break content,
                # terminate it to return to normal operation/queue
                elif not break_mode and active_stream.get("current_video", {}).get("title") == "Break Stream":
                    player.add_log("Watchdog: Break Mode turned OFF. Terminating break loop...")
                    player.stop_stream()
                else:
                    # Normal monitoring: sync metrics and status to config.json
                    live_status = player.get_live_status()
                    settings_mgr.update_active_stream({
                        "status": "streaming",
                        "current_video": {"title": live_status.get("title"), "url": live_status.get("url")},
                        "start_time": live_status.get("start_time")
                    })
                    
            # 2. Check and trigger scheduled events
            if not break_mode: # Do not trigger schedules during active break mode
                for s in schedules:
                    if s.get("status") == "scheduled":
                        sched_time = parse_schedule_time(s.get("time"))
                        if sched_time and sched_time <= now:
                            print(f"Schedule '{s.get('name')}' is due.")
                            
                            if player.active_process is not None:
                                player.add_log(f"Schedule skipped: '{s.get('name')}' was triggered, but another stream is active.")
                                settings_mgr.update_schedule_status(s.get("id"), "failed")
                                continue
                                
                            active_schedule_id = s.get("id")
                            settings_mgr.update_schedule_status(active_schedule_id, "running")
                            target_url = s.get("url")
                            
                            # Prepare the playlist/queue
                            items_to_queue = []
                            
                            # A: If Intro URL is configured, prepend it
                            if intro_url:
                                items_to_queue.append({"url": intro_url, "title": "Intro Presentation"})
                                
                            # B: Add the main schedule target content
                            if target_url.startswith("playlist:"):
                                playlist_id = target_url.split(":")[1]
                                playlists = config.get("playlists", [])
                                playlist = next((p for p in playlists if p.get("id") == playlist_id), None)
                                
                                if playlist and playlist.get("items"):
                                    items_to_queue.extend(playlist.get("items"))
                                    player.add_log(f"Triggered playlist schedule '{s.get('name')}' with {len(playlist.get('items'))} items.")
                                else:
                                    player.add_log(f"Schedule failed: Playlist '{playlist_id}' not found or is empty.")
                                    settings_mgr.update_schedule_status(active_schedule_id, "failed")
                                    active_schedule_id = None
                                    continue
                            else:
                                items_to_queue.append({"url": target_url, "title": s.get("name")})
                                player.add_log(f"Triggered video schedule '{s.get('name')}'")
                                
                            # C: If Ending URL is configured, append it
                            if ending_url:
                                items_to_queue.append({"url": ending_url, "title": "Ending Credits"})
                                
                            # Set current queue
                            current_queue = items_to_queue
                            
        except Exception as e:
            print(f"Error in runner loop iteration: {e}")
            
        time.sleep(5)

def start_runner():
    global runner_thread, runner_running, auto_ping_thread
    if runner_running:
        return
    runner_running = True
    
    # 1. Start core runner and watchdog thread
    runner_thread = threading.Thread(target=runner_loop, daemon=True)
    runner_thread.start()
    
    # 2. Start 7-second auto-pinger keep-alive thread
    auto_ping_thread = threading.Thread(target=pinger_loop, daemon=True)
    auto_ping_thread.start()
    
    print("Background runner and keep-alive pinger threads started.")

def stop_runner():
    global runner_running
    runner_running = False
    print("Background runner and keep-alive pinger threads stopped.")
