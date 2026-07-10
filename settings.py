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
        self.config = self._load()

    def _load(self):
        with self.lock:
            if not os.path.exists(self.filepath):
                # Return empty config structure if file does not exist
                return {
                    "settings": {
                        "rtmp_url": "",
                        "stream_key": "",
                        "quality": "copy",
                        "github_backup": {
                            "enabled": False,
                            "repo": "",
                            "branch": "main",
                            "token": "",
                            "path": "stoud-config.json"
                        }
                    },
                    "schedules": [],
                    "playlists": [],
                    "saved_videos": [],
                    "active_stream": {
                        "status": "idle",
                        "current_video": None,
                        "start_time": None,
                        "pid": None,
                        "log_file": None
                    }
                }
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading config.json: {e}")
                # Fallback template
                return {}

    def get_config(self):
        with self.lock:
            return self.config

    def save(self):
        with self.lock:
            try:
                # Always clear pid from saved config as it represents current running state
                # that shouldn't persist across server restarts
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

    def _backup_to_github(self):
        gh = self.config.get("settings", {}).get("github_backup", {})
        repo = gh.get("repo")
        token = gh.get("token")
        branch = gh.get("branch", "main")
        path = gh.get("path", "stoud-config.json")

        if not repo or not token:
            print("GitHub Backup: Missing repo or token. Backup aborted.")
            return

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Stoud-v2-Backup-Client"
        }

        # 1. Get the current file SHA if it exists
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

        # 2. Put the updated content
        put_url = f"https://api.github.com/repos/{repo}/contents/{path}"
        with self.lock:
            # Clean pid for backup copy too
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

    # Update helper methods
    def update_settings(self, settings_dict):
        self.config["settings"].update(settings_dict)
        return self.save()

    def get_settings(self):
        return self.config.get("settings", {})

    # Schedule management
    def get_schedules(self):
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

    # Playlists
    def get_playlists(self):
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

    # Saved Videos
    def get_saved_videos(self):
        return self.config.get("saved_videos", [])

    def add_saved_video(self, video_dict):
        self.config["saved_videos"].append(video_dict)
        return self.save()

    def delete_saved_video(self, video_id):
        self.config["saved_videos"] = [v for v in self.config["saved_videos"] if v.get("id") != video_id]
        return self.save()

    # Active Stream
    def get_active_stream(self):
        return self.config.get("active_stream", {})

    def update_active_stream(self, active_dict):
        self.config["active_stream"].update(active_dict)
        return self.save()
