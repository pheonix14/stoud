# Stoud v3 🚀

<div align="center">
  <h3>The Ultimate 24/7 Cloud Broadcasting Engine & Restream Alternative</h3>
  <p>Stream continuously to YouTube, Twitch, and custom platforms simultaneously from Google Drive (up to 8GB+ files) or YouTube links without consuming local storage or bandwidth.</p>
  <p><b>Developed by <a href="https://github.com/pheonix14">pheonix14</a> — Follow and Star the repo to support! ⭐</b></p>
</div>

---

## ⚡ What's New in Stoud v3

- **Unified Control Cockpit**: Launch streams, select custom RTMPs, toggle loops, and define intros/ending overlays on the fly directly from the home screen.
- **Dynamic Ingestion Routing**: Stream to multiple destinations at the same time using native FFmpeg multiplexing.
- **Large Google Drive Warning Bypass**: Stream large files (like 8GB+ movies/shows) by dynamically extracting virus scan warning tokens (`confirm` and `uuid`), enabling direct 200 HTTP video parsing.
- **Render-Ready Containerization**: Bundled with a optimized `Dockerfile` that automates system-wide `ffmpeg` setup.
- **Active Watchdog Monitor**: Self-healing loops check stream integrity and auto-restart crashed processes instantly.
- **7-Second Self-Pinger**: Built-in pinger engine hits public endpoints every 7 seconds to keep free containers (like Render) awake.
- **Interactive Queue Manager**: Real-time queue controllers (+/-) let you add and remove stream assets without stopping active broadcasts.

---

## 🛠️ Installation & Setup

### 🐳 Deploying via Docker (Recommended for Render)
Stoud v3 is optimized for container deployment. Simply link your GitHub fork to Render or deploy manually:

```bash
# Build the Docker image
docker build -t stoud-v3 .

# Run the container (Map port 5000)
docker run -d -p 5000:5000 stoud-v3
```

### 💻 Local Manual Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/pheonix14/stoud.git
   cd stoud
   ```

2. **Install Python dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install FFmpeg**:
   - **Windows**: Stoud features an automated standalone downloader directly in the Settings dashboard!
   - **Linux/macOS**: Ensure `ffmpeg` is available on your system path (`sudo apt install ffmpeg`).

4. **Launch the Engine**:
   ```bash
   python main.py
   ```
   Open `http://127.0.0.1:5000` in your web browser.

---

## ⚙️ Core Architectures

### 1. Zero-Disk 8GB Google Drive Streaming
Instead of downloading massive video files to your disk (which exceeds common 300MB storage limits), Stoud resolves the direct download link and pipes the HTTP stream segment-by-segment straight into FFmpeg's standard input.

### 2. Multi-Destination RTMP Multiplexing
By utilizing FFmpeg's split tee output flags, Stoud splits the single parsed video source into multiple streams, broadcasting to YouTube, Twitch, and local targets at the same time.

---

## 🌟 Support the Developer
This project is built and maintained by **pheonix14**. If Stoud helps power your 24/7 stream channels, please leave a **Star** on this repository and follow **[pheonix14 on GitHub](https://github.com/pheonix14)**!

## SEO Tags
`#multistreaming` `#ffmpeg-cockpit` `#restream-alternative` `#24-7-cloud-stream` `#google-drive-streamer` `#youtube-live` `#twitch-stream` `#docker-streamer` `#python-broadcaster`
