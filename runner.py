import os
import time
import math
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
cleanup_thread = None

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

def add_sharded_to_queue(url, title, shard_duration_minutes=30):
    """
    Split a 50GB Google Drive or long video into sequential playback shards.
    Each shard is streamed with Range headers and fresh URL tokens.
    """
    global current_queue
    player.add_log(f"[Sharder] Inspecting video for 50GB sharded plan: {url}")
    
    info = player.inspect_media(url)
    duration = info.get("duration")
    size_gb = info.get("filesize_gb")
    video_title = title or info.get("title") or "Sharded Video"
    
    shard_secs = int(shard_duration_minutes * 60)
    
    if duration and duration > shard_secs:
        total_shards = math.ceil(duration / shard_secs)
        player.add_log(f"[Sharder] Splitting into {total_shards} shards ({shard_duration_minutes}m each). Total Duration: {info.get('duration_formatted')} | Size: {size_gb or 'N/A'} GB")
        
        for i in range(total_shards):
            offset = i * shard_secs
            dur = min(shard_secs, int(duration - offset))
            start_str = time.strftime('%H:%M:%S', time.gmtime(offset))
            end_str = time.strftime('%H:%M:%S', time.gmtime(offset + dur))
            
            shard_item = {
                "url": url,
                "title": f"[Shard {i+1}/{total_shards}] {video_title} ({start_str} - {end_str})",
                "type": "gdrive" if "drive.google.com" in url else "direct",
                "start_offset": offset,
                "duration": dur,
                "shard_index": i + 1,
                "shard_total": total_shards,
                "original_url": url,
                "is_shard": True
            }
            current_queue.append(shard_item)
            
        player.add_log(f"[Sharder] Successfully queued {total_shards} shards for seamless 24/7 streaming.")
        return True, total_shards
    else:
        # File has unknown duration or is shorter than shard duration: queue as single range-sharded stream
        video_type = "gdrive" if "drive.google.com" in url else "direct"
        item = {
            "url": url,
            "title": f"{video_title} (Range Stream)",
            "type": video_type,
            "start_offset": 0,
            "duration": None,
            "shard_index": 1,
            "shard_total": 1,
            "original_url": url,
            "is_shard": False
        }
        current_queue.append(item)
        player.add_log(f"Queued single range-streaming item: '{video_title}'")
        return True, 1

def add_to_queue(url, title, auto_shard=None):
    global current_queue
    if "list=" in url or "playlist" in url:
        try:
            items = player.extract_playlist_items(url)
            current_queue.extend(items)
            player.add_log(f"Added {len(items)} playlist items to active queue.")
            return True
        except Exception as e:
            player.add_log(f"Failed to add playlist to queue: {str(e)}")
            return False
            
    # Check settings for auto-sharding Drive files
    settings_mgr = SettingsManager()
    cfg = settings_mgr.get_config().get("settings", {})
    should_shard = auto_shard if auto_shard is not None else cfg.get("auto_shard_drive", True)
    shard_mins = cfg.get("shard_duration_minutes", 30)
    
    if should_shard and "drive.google.com" in url:
        success, _ = add_sharded_to_queue(url, title, shard_duration_minutes=shard_mins)
        return success

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
    """
    Render Free-Tier Keep-Alive Pinger.
    Pings the public Render service URL to prevent the 15-minute idle spin-down.
    """
    print("Auto-pinger thread started.")
    settings_mgr = SettingsManager()
    
    while runner_running:
        try:
            config = settings_mgr._load_local()
            ping_url = config.get("settings", {}).get("auto_ping_url", "").strip()
            
            # Auto-detect Render external URL if not manually configured
            if not ping_url:
                ping_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
                
            port = os.environ.get("PORT", "5000")
            target_url = ping_url if ping_url else f"http://127.0.0.1:{port}/api/health"
            
            req = urllib.request.Request(target_url, headers={"User-Agent": "Stoud-v3-Render-KeepAlive"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
                if ping_url:
                    print(f"[Keep-Alive] Pinged external service: {ping_url}")
        except Exception as e:
            if ping_url:
                print(f"[Keep-Alive Error] Could not ping {ping_url}: {e}")
        
        # Ping every 5 minutes (300 seconds) to easily stay well within Render's 15-min spin-down window
        # When idle/local, check every 60s
        sleep_secs = 300 if ping_url else 60
        time.sleep(sleep_secs)

def disk_cleanup_loop():
    """Periodic disk & RAM hygiene loop for Render 512MB RAM environment."""
    while runner_running:
        try:
            player.cleanup_temp_cache()
            ram_mb = player.get_available_memory_mb()
            disk_mb = player.get_available_disk_mb()
            if ram_mb < 70:
                player.add_log(f"[WATCHDOG] Free RAM tight: {ram_mb}MB. Cache purged.")
            if disk_mb < 50:
                player.add_log(f"[WATCHDOG] Free Disk tight: {disk_mb}MB.")
        except Exception:
            pass
        time.sleep(60)

def runner_loop():
    global runner_running, current_queue, active_schedule_id
    settings_mgr = SettingsManager()
    print("Background runner and watchdog loop started.")
    
    while runner_running:
        try:
            config = settings_mgr.get_config()
            schedules = config.get("schedules", [])
            settings = config.get("settings", {})
            active_stream = config.get("active_stream", {})
            
            destinations = settings.get("destinations", [])
            quality = settings.get("quality", "copy")
            budget_mode = settings.get("budget_mode", True)
            
            break_mode = settings.get("break_mode", False)
            break_video_url = settings.get("break_video_url", "")
            break_image_url = settings.get("break_image_url", "")
            intro_enabled = settings.get("intro_enabled", False)
            outro_enabled = settings.get("outro_enabled", False)
            intro_url = settings.get("intro_video_url", "")
            ending_url = settings.get("ending_video_url", "")
            
            now = get_current_time()
            
            # 1. Watchdog & Active Stream Monitor
            if player.active_process is None:
                # Loop video support
                was_streaming = (active_stream.get("status") == "streaming")
                last_video = active_stream.get("current_video")
                if was_streaming and last_video and settings.get("loop_current_video", False) and not break_mode:
                    current_queue.insert(0, {"url": last_video.get("url"), "title": last_video.get("title")})
                    player.add_log(f"Loop Active: Re-queuing '{last_video.get('title')}'")
                
                # A: Break Mode Active
                if break_mode:
                    break_media = player.get_media_from_path(break_video_url) or player.get_media_from_path(break_image_url)
                    if break_media:
                        try:
                            player.add_log(f"Watchdog: Break Mode is Active. Starting Break Stream: {break_media}")
                            player.start_stream(break_media, destinations, quality, budget_mode=budget_mode)
                            settings_mgr.update_active_stream({
                                "status": "streaming",
                                "current_video": {"title": "Break Stream", "url": break_media},
                                "start_time": time.time()
                            })
                        except Exception as e:
                            player.add_log(f"Watchdog: Failed to start break stream: {e}")
                    else:
                        player.add_log("Watchdog: Break Mode is Active, but no media configured.")
                        
                # B: Advance Queue (Supports Shards seamlessly)
                elif current_queue:
                    next_item = current_queue.pop(0)
                    url = next_item.get("url")
                    title = next_item.get("title", "Queue Item")
                    start_offset = next_item.get("start_offset")
                    duration = next_item.get("duration")
                    shard_info = None
                    if next_item.get("is_shard"):
                        shard_info = {
                            "index": next_item.get("shard_index"),
                            "total": next_item.get("shard_total")
                        }
                    
                    try:
                        player.add_log(f"Queue: Launching '{title}'")
                        info = player.start_stream(
                            url, destinations, quality,
                            budget_mode=budget_mode,
                            start_offset=start_offset,
                            duration=duration,
                            shard_info=shard_info
                        )
                        settings_mgr.update_active_stream({
                            "status": "streaming",
                            "current_video": {"title": title, "url": url},
                            "start_time": time.time()
                        })
                    except Exception as e:
                        player.add_log(f"Queue error on '{title}': {str(e)}")
                        if "drive.google.com" in url:
                            time.sleep(5)
                else:
                    if active_schedule_id:
                        print(f"Schedule {active_schedule_id} completed.")
                        settings_mgr.update_schedule_status(active_schedule_id, "completed")
                        active_schedule_id = None
                        
                    if active_stream.get("status") != "idle":
                        settings_mgr.update_active_stream({
                            "status": "idle",
                            "current_video": None,
                            "start_time": None
                        })
            else:
                # Active streaming checks
                if break_mode and active_stream.get("current_video", {}).get("title") != "Break Stream":
                    player.add_log("Watchdog: Break Mode turned ON. Terminating active content...")
                    player.stop_stream()
                elif not break_mode and active_stream.get("current_video", {}).get("title") == "Break Stream":
                    player.add_log("Watchdog: Break Mode turned OFF. Returning to normal queue...")
                    player.stop_stream()
                else:
                    live_status = player.get_live_status()
                    settings_mgr.update_active_stream({
                        "status": "streaming",
                        "current_video": {"title": live_status.get("title"), "url": live_status.get("url")},
                        "start_time": live_status.get("start_time")
                    })
                    
            # 2. Check and trigger scheduled events
            if not break_mode:
                for s in schedules:
                    if s.get("status") == "scheduled":
                        sched_time = parse_schedule_time(s.get("time"))
                        if sched_time and sched_time <= now:
                            print(f"Schedule '{s.get('name')}' is due.")
                            if player.active_process is not None:
                                player.add_log(f"Schedule skipped: '{s.get('name')}' — another stream is active.")
                                settings_mgr.update_schedule_status(s.get("id"), "failed")
                                continue
                                
                            active_schedule_id = s.get("id")
                            settings_mgr.update_schedule_status(active_schedule_id, "running")
                            target_url = s.get("url")
                            
                            items_to_queue = []
                            if intro_enabled and intro_url:
                                intro_media = player.get_media_from_path(intro_url)
                                if intro_media:
                                    items_to_queue.append({"url": intro_media, "title": "Intro Presentation"})
                                
                            if target_url.startswith("playlist:"):
                                playlist_id = target_url.split(":")[1]
                                playlists = config.get("playlists", [])
                                playlist = next((p for p in playlists if p.get("id") == playlist_id), None)
                                if playlist and playlist.get("items"):
                                    items_to_queue.extend(playlist.get("items"))
                                else:
                                    settings_mgr.update_schedule_status(active_schedule_id, "failed")
                                    active_schedule_id = None
                                    continue
                            else:
                                # Check if Drive auto-shard applies
                                if settings.get("auto_shard_drive", True) and "drive.google.com" in target_url:
                                    add_sharded_to_queue(target_url, s.get("name"), shard_duration_minutes=settings.get("shard_duration_minutes", 30))
                                    continue
                                else:
                                    items_to_queue.append({"url": target_url, "title": s.get("name")})
                                    
                            if outro_enabled and ending_url:
                                outro_media = player.get_media_from_path(ending_url)
                                if outro_media:
                                    items_to_queue.append({"url": outro_media, "title": "Ending Credits"})
                                    
                            current_queue = items_to_queue
                            
        except Exception as e:
            print(f"Error in runner loop iteration: {e}")
            
        time.sleep(3)

def start_runner():
    global runner_thread, runner_running, auto_ping_thread, cleanup_thread
    if runner_running:
        return
    runner_running = True
    
    runner_thread = threading.Thread(target=runner_loop, daemon=True)
    runner_thread.start()
    
    auto_ping_thread = threading.Thread(target=pinger_loop, daemon=True)
    auto_ping_thread.start()
    
    cleanup_thread = threading.Thread(target=disk_cleanup_loop, daemon=True)
    cleanup_thread.start()
    
    print("Background runner, keep-alive pinger, and memory watchdog started.")

def stop_runner():
    global runner_running
    runner_running = False
    print("Background runner stopped.")
