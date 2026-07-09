import json
import os
import subprocess
import threading
import time

DATA_DIR = "data"
DB_FILE = os.path.join(DATA_DIR, "stoud_data.json")

os.makedirs(DATA_DIR, exist_ok=True)

default_state = {
    "github_repo": "",
    "github_token": "",
    "urls": [],
    "rtmp_urls": [],
    "overlay_url": "",
    "background_url": "",
    "quality": "1080p",
    "fps": 60,
    "hf_key": "",
    "resume_timestamps": {},
    "loop": False
}

class DBManager:
    def __init__(self):
        self.state = default_state.copy()
        self.lock = threading.Lock()
        self.load()
        # Start the 30-second persistence loop
        threading.Thread(target=self._persistence_loop, daemon=True).start()

    def load(self):
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE, "r") as f:
                    data = json.load(f)
                    self.state.update(data)
            except Exception as e:
                print(f"Error loading DB: {e}")
        else:
            self.save()

    def save(self):
        with self.lock:
            with open(DB_FILE, "w") as f:
                json.dump(self.state, f, indent=4)

    def _persistence_loop(self):
        while True:
            time.sleep(30)
            self.save()
            self._git_sync()

    def _git_sync(self):
        repo = self.state.get("github_repo")
        token = self.state.get("github_token")
        
        if not repo or not token:
            # Fallback to local storage only if no git config
            return

        # Format: https://<token>@github.com/<username>/<repo>.git
        if not repo.startswith("https://"):
            repo_url = f"https://{token}@github.com/{repo}.git"
        else:
            repo_url = repo.replace("https://", f"https://{token}@")

        try:
            # Move to data dir for git ops so we only commit the data folder
            cwd = os.getcwd()
            os.chdir(DATA_DIR)
            
            if not os.path.exists(".git"):
                subprocess.run(["git", "init"], check=True, capture_output=True)
                subprocess.run(["git", "remote", "add", "origin", repo_url], capture_output=True)
            else:
                subprocess.run(["git", "remote", "set-url", "origin", repo_url], capture_output=True)

            subprocess.run(["git", "add", "stoud_data.json"], check=True, capture_output=True)
            res = subprocess.run(["git", "commit", "-m", "Auto-sync Stoud state timestamp"], capture_output=True)
            
            # Only push if commit was successful (i.e. there were changes)
            if res.returncode == 0:
                subprocess.run(["git", "push", "origin", "main", "--force"], check=True, capture_output=True)
                print("[GitSync] Timestamp & Data pushed successfully.")
                
            os.chdir(cwd)
        except Exception as e:
            # Silently fail git sync so it doesn't spam logs or crash
            try:
                os.chdir(cwd)
            except:
                pass

    def update(self, key, value):
        self.state[key] = value
        self.save()

db = DBManager()
