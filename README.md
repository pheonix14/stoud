# Stoud v3 - Live Streaming Manager (50GB Shard Edition)

A self-hosted web dashboard for managing 24/7 live streams to platforms like YouTube and Twitch. Built with Flask, FFmpeg, and `yt-dlp`. Specially engineered to run 24/7 on **Render.com Free Tier** with zero disk usage and automated **50GB Google Drive Sharding**.

---

## ⚡ 50GB Google Drive Shard Engine & Render Free Tier Features

Streaming a 50GB video file on a free cloud instance (which has only 512MB RAM and ~1GB temporary disk) is normally impossible. Stoud solves this with a multi-layered Shard Architecture:

1. **Pure HTTP Range Sharding (0MB Disk Usage)**
   - Stoud **never downloads the 50GB video** to Render's disk.
   - It streams directly from Google Drive's edge servers using HTTP Range requests (`bytes=X-Y`).
   - Ephemeral disk usage remains strictly at **0 MB**.

2. **Sequential Time Sharding (Prevents 4-Hour Token Death & Memory Bloat)**
   - Google Drive signed download URLs expire after ~4 hours. A 50GB video can take 12 to 24+ hours to stream.
   - Stoud automatically splits the 50GB video into seamless 30-minute shards.
   - For each shard, Stoud re-resolves a fresh Google Drive token so the stream **never dies from token expiration**.
   - Input fast seeking (`-ss <offset>` before `-i`) jumps directly to the shard offset via HTTP Range headers without reading earlier portions of the 50GB file.
   - Memory is completely reclaimed by Python GC between shards, keeping RAM safely around **60MB - 120MB** (well below Render's 512MB limit).

3. **Render Free Tier Keep-Alive Pinger**
   - Render's free web services spin down after 15 minutes of idle time.
   - Stoud auto-detects `RENDER_EXTERNAL_URL` and pings itself every 5 minutes to keep your live stream awake **24/7**.

4. **Multi-Platform RTMP Ingestion**
   - Stream simultaneously to YouTube Live, Twitch, and custom RTMP destinations.
   - Direct Copy mode (`-c:v copy -c:a aac`) provides near-zero CPU usage on Render's 0.1 core.

---

## 🚀 Deployment to Render.com (100% Free Tier)

### Method A: One-Click Blueprint (Recommended)
1. Fork or push this repository to your GitHub account.
2. Log in to [Render.com](https://render.com).
3. Click **New +** > **Blueprint**.
4. Select your `stoud` repository. Render will automatically detect [`render.yaml`](render.yaml) and configure:
   - Environment: `Docker`
   - Plan: `Free`
   - Health check: `/api/health`
   - Port: `10000`
5. Click **Apply**. Your 24/7 stream server will be live in 2 minutes!

### Method B: Manual Web Service
1. Click **New +** > **Web Service**.
2. Connect your repository.
3. Choose **Docker** as the Runtime.
4. Select the **Free** instance plan.
5. In **Environment Variables**, add:
   - `PORT`: `10000`
   - `STOUD_RAM_LIMIT_MB`: `450`
   - `STOUD_SHARD_DURATION`: `1800`
   - `PYTHONUNBUFFERED`: `1`
   - `MALLOC_ARENA_MAX`: `2`
6. Click **Create Web Service**.

---

## 🎬 How to Stream a 50GB Google Drive Video

1. Open your Stoud web dashboard (`https://your-service.onrender.com`).
2. Go to **Settings**:
   - Add your YouTube Stream Key under **Multi-Stream Ingestion Platforms**.
   - Verify that **Auto-Shard Google Drive videos** is checked (enabled by default).
   - Ensure **Render Free-Tier Budget Mode** is checked.
   - Click **Save Configuration Changes**.
3. Return to **Dashboard**:
   - Paste your Google Drive video link into **Video Source Link**:
     ```
     https://drive.google.com/file/d/YOUR_FILE_ID/view?usp=sharing
     ```
     *(Ensure the Google Drive file permissions are set to "Anyone with the link can view")*
   - Stoud will instantly inspect the link, detect the 50GB file size, and show the **Google Drive Shard Engine** indicator.
   - Streaming Method: Select **Direct Copy** (recommended for zero CPU usage).
   - Click **Start Stream**.
4. Stoud starts Shard 1 immediately and queues remaining shards sequentially in the **Live Broadcast Queue**.

---

## 🖥️ Local Usage

If running locally:
```bash
# Clone the repository
git clone https://github.com/pheonix14/stoud.git
cd stoud

# Install dependencies
pip install -r requirements.txt

# Run server
python main.py
```
Open `http://localhost:5000` in your web browser.

---

## 🏗️ Architecture

- `main.py`: Flask REST API, health checks, and Gunicorn entry point.
- `player.py`: FFmpeg subprocess manager, HTTP Range sharder, and memory watchdog.
- `runner.py`: Background queue orchestrator, shard sequencer, and Render keep-alive pinger.
- `settings.py`: Thread-safe JSON configuration manager with optional GitHub backup sync.
- `render.yaml`: Infrastructure-as-code blueprint for Render.com deployment.
- `Dockerfile`: Multi-stage Docker configuration with FFmpeg, Gunicorn `gthread`, and memory bounds.
