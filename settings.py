import os
import json
import base64
import threading
import urllib.request
import urllib.error

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

class SettingsManager:
    def __init__(self, filepath=CONFIG_PATH):
        self.filepath = filepath
        self.lock = threading.Lock()
        self.config = self._load_local()
        # Attempt to pull from GitHub on initialization if enabled
        if self.config.get("settings", {}).get("github_backup", {}).get("enabled"):
            self.sync_from_github()

    def _load_local(self):
        if not os.path.exists(self.filepath):
            return self._get_template_config()
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading local config.json: {e}")
            return self._get_template_config()

    def _get_template_config(self):
        return {
            "settings": {
                "destinations": [
                    {
                        "id": "youtube-default",
                        "name": "YouTube Live",
                        "rtmp_url": "rtmp://a.rtmp.youtube.com/live2",
                        "stream_key": "",
                        "enabled": True
                    }
                ],
                "quality": "copy",
                "loop_current_video": False,
                "github_backup": {
                    "enabled": False,
                    "repo": "",
                    "branch": "main",
                    "token": "",
                    "path": "stoud-config.json"
                },
                "auto_ping_url": "",
                "break_video_url": "",
                "break_image_url": "",
                "break_mode": False,
                "intro_enabled": True,
                "intro_video_url": "",
                "outro_enabled": True,
                "ending_video_url": ""
            },
            "schedules": [],
            "playlists": [],
            "saved_videos": [
                {
                    "id": "test-gdrive-video",
                    "title": "Test GDrive Video",
                    "url": "https://drive.google.com/file/d/1kGDTidwRBYEyXUmeuKmGnldu-k9wGtDu/view?usp=drive_link",
                    "type": "gdrive"
                }
            ],
            "active_stream": {
                "status": "idle",
                "current_video": None,
                "start_time": None,
                "pid": None,
                "log_file": None
            }
        }

    def get_config(self):
        # Dynamically sync from GitHub in real-time if enabled
        if self.config.get("settings", {}).get("github_backup", {}).get("enabled"):
            self.sync_from_github()
            
        fresh_config = self._load_local()
        with self.lock:
            # Preserve active stream state that we track in memory
            if "active_stream" in self.config:
                fresh_config["active_stream"] = self.config["active_stream"]
            self.config = fresh_config
            return self.config

    def save(self):
        with self.lock:
            try:
                # Clear PID in saved file so it doesn't persist
                config_to_save = json.loads(json.dumps(self.config))
                if "active_stream" in config_to_save:
                    config_to_save["active_stream"]["pid"] = None
                
                with open(self.filepath, "w", encoding="utf-8") as f:
                    json.dump(config_to_save, f, indent=2)
            except Exception as e:
                print(f"Error writing config.json: {e}")
                return False
        
        # Trigger GitHub Backup in a separate thread if enabled
        if self.config.get("settings", {}).get("github_backup", {}).get("enabled"):
            threading.Thread(target=self._backup_to_github, daemon=True).start()
        return True

    def sync_from_github(self):
        gh = self.config.get("settings", {}).get("github_backup", {})
        repo = gh.get("repo")
        token = gh.get("token")
        branch = gh.get("branch", "main")
        path = gh.get("path", "stoud-config.json")

        if not repo or not token:
            return False

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Stoud-v2-Backup-Client"
        }

        url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                resp_data = json.loads(resp.read().decode())
                content_b64 = resp_data.get("content", "")
                if content_b64:
                    config_str = base64.b64decode(content_b64.encode('utf-8')).decode('utf-8')
                    remote_config = json.loads(config_str)
                    
                    with self.lock:
                        # Keep current local active_stream pid so we don't drop active streaming status
                        current_active_stream = self.config.get("active_stream", {})
                        self.config = remote_config
                        if "active_stream" in self.config:
                            # If remote says idle but we are streaming, keep our local stream status
                            if current_active_stream.get("status") == "streaming" and self.config["active_stream"].get("status") == "idle":
                                self.config["active_stream"] = current_active_stream
                                
                    # Write to local file so it is persisted
                    with open(self.filepath, "w", encoding="utf-8") as f:
                        json.dump(remote_config, f, indent=2)
                    print("GitHub Data Sync: Successfully pulled configuration from GitHub.")
                    return True
        except Exception as e:
            print(f"GitHub Data Sync: Failed to pull config from GitHub (falling back to local): {str(e)}")
        return False

    def _backup_to_github(self):
        gh = self.config.get("settings", {}).get("github_backup", {})
        repo = gh.get("repo")
        token = gh.get("token")
        branch = gh.get("branch", "main")
        path = gh.get("path", "stoud-config.json")

        if not repo or not token:
            return

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Stoud-v2-Backup-Client"
        }

        # 1. Get SHA of file if exists
        sha = None
        url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req) as resp:
                resp_data = json.loads(resp.read().decode())
                sha = resp_data.get("sha")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                print(f"GitHub Backup: Error checking file SHA: {e.reason} ({e.code})")
                return
        except Exception as e:
            print(f"GitHub Backup: Error checking file SHA: {str(e)}")
            return

        # 2. Put updated content
        put_url = f"https://api.github.com/repos/{repo}/contents/{path}"
        with self.lock:
            # Clean pid for backup copy
            clean_config = json.loads(json.dumps(self.config))
            if "active_stream" in clean_config:
                clean_config["active_stream"]["pid"] = None
                
            config_bytes = json.dumps(clean_config, indent=2).encode('utf-8')
            
        content_b64 = base64.b64encode(config_bytes).decode('utf-8')
        
        payload = {
            "message": "Auto-update config from Stoud v2",
            "content": content_b64,
            "branch": branch
        }
        if sha:
            payload["sha"] = sha

        payload_bytes = json.dumps(payload).encode('utf-8')
        headers["Content-Type"] = "application/json"

        put_req = urllib.request.Request(put_url, data=payload_bytes, headers=headers, method="PUT")
        try:
            with urllib.request.urlopen(put_req) as resp:
                print(f"GitHub Backup: Successfully synced config to GitHub ({repo}/{path})")
        except Exception as e:
            print(f"GitHub Backup: Failed uploading config: {str(e)}")

    def update_settings(self, settings_dict):
        self.config["settings"].update(settings_dict)
        return self.save()

    def get_settings(self):
        return self.config.get("settings", {})

    def get_schedules(self):
        if self.config.get("settings", {}).get("github_backup", {}).get("enabled"):
            self.sync_from_github()
        return self.config.get("schedules", [])

    def add_schedule(self, schedule_dict):
        self.config["schedules"].append(schedule_dict)
        return self.save()

    def delete_schedule(self, schedule_id):
        self.config["schedules"] = [s for s in self.config["schedules"] if s.get("id") != schedule_id]
        return self.save()

    def update_schedule_status(self, schedule_id, status):
        for s in self.config["schedules"]:
            if s.get("id") == schedule_id:
                s["status"] = status
                break
        return self.save()

    def get_playlists(self):
        if self.config.get("settings", {}).get("github_backup", {}).get("enabled"):
            self.sync_from_github()
        return self.config.get("playlists", [])

    def add_playlist(self, playlist_dict):
        self.config["playlists"].append(playlist_dict)
        return self.save()

    def delete_playlist(self, playlist_id):
        self.config["playlists"] = [p for p in self.config["playlists"] if p.get("id") != playlist_id]
        return self.save()

    def update_playlist(self, playlist_id, playlist_dict):
        for i, p in enumerate(self.config["playlists"]):
            if p.get("id") == playlist_id:
                self.config["playlists"][i] = playlist_dict
                break
        return self.save()

    def get_saved_videos(self):
        if self.config.get("settings", {}).get("github_backup", {}).get("enabled"):
            self.sync_from_github()
        return self.config.get("saved_videos", [])

    def add_saved_video(self, video_dict):
        self.config["saved_videos"].append(video_dict)
        return self.save()

    def delete_saved_video(self, video_id):
        self.config["saved_videos"] = [v for v in self.config["saved_videos"] if v.get("id") != video_id]
        return self.save()

    def get_active_stream(self):
        return self.config.get("active_stream", {})

    def update_active_stream(self, active_dict):
        self.config["active_stream"].update(active_dict)
        return self.save()
