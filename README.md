# Stoud v3 - Live Streaming Manager

A powerful, self-hosted web dashboard for managing 24/7 live streams to platforms like YouTube and Twitch. Built with Flask, FFmpeg, and `yt-dlp`.

## Features
- **YouTube Playlists**: Drop a YouTube playlist URL and Stoud automatically queues all videos to play sequentially.
- **Google Drive Integration**: Direct stream large `.mp4` and `.mkv` files directly from Google Drive without downloading them to your server.
- **Folder Support & Image Looping**: Point Stoud to a local directory for Intros, Outros, and Breaks. Stoud will scan the folder and randomly pick media to play. If a `.jpg` or `.png` is selected, Stoud uses FFmpeg to loop it indefinitely as a live stream!
- **Dashboard Quick-Toggles**: Easily toggle Break Mode, Intros, and Outros with one click directly from the Stream Launcher dashboard.
- **Render/Heroku Budget Mode**: Optimize FFmpeg with a single click. Uses strict RAM bounds (`-max_muxing_queue_size`, smaller `-bufsize`, `-threads 1`) to ensure stable 24/7 streaming on free/hobby tier platforms with only 300MB RAM.
- **Looping & Break Content**: Intercut dynamic break screens, loop a single file indefinitely, or queue up videos dynamically.
- **Real-Time Logs**: View FFmpeg output directly in your browser.

## Deployment

### Deploying to Render.com (or other budget hosts)
1. Fork or upload this repository to your GitHub.
2. Go to Render and create a **New Web Service**.
3. Connect your repository.
4. Set the Start Command to: `gunicorn --worker-class eventlet -w 1 -b 0.0.0.0:$PORT main:app`
5. Go to your Stoud Settings page and **Enable Budget Mode**.

## Requirements
- Python 3.9+
- FFmpeg installed and accessible in the system PATH.
- `pip install -r requirements.txt`

## Local Usage
Run the backend server locally:
```bash
python main.py
```
Open `http://localhost:5000` in your web browser.

## Architecture Highlights
- `main.py`: Flask Web API that handles user requests and REST logic.
- `player.py`: Python wrapper around FFmpeg and `yt-dlp` for URL resolution and streaming.
- `runner.py`: The background watchdog thread that manages the active queue and auto-restarts failed streams.
