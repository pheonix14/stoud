import subprocess
import os
import threading

class Engine:
    def __init__(self):
        self.status = "idle"
        self.active_process = None
        self.rtmp_urls = []

    def start_stream(self, source_urls, rtmp_urls, background_url, overlay_url, loop=False):
        if self.active_process:
            self.stop()
            
        self.status = "streaming"
        self.rtmp_urls = rtmp_urls
        print(f"[FFmpeg Engine] Starting stream to {rtmp_urls} (loop: {loop})")
        
        input_file = source_urls[0] if source_urls else "dummy.mp4"
        loop_args = ["-stream_loop", "-1"] if loop else []
        
        cmd = ["ffmpeg", "-re"] + loop_args + ["-i", input_file, "-c:v", "copy", "-c:a", "aac", "-f", "flv", rtmp_urls[0]]
        
        def run_ffmpeg():
            try:
                self.active_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
                self.active_process.wait()
            except Exception as e:
                print(f"[FFmpeg Engine] Error: {e}")
            finally:
                self.status = "idle"
                self.active_process = None
            
        threading.Thread(target=run_ffmpeg, daemon=True).start()
        return True

    def start_ws_stream(self, rtmp_urls):
        if self.active_process:
            self.stop()
            
        self.status = "streaming"
        self.rtmp_urls = rtmp_urls
        print(f"[FFmpeg Engine] Starting REAL-TIME WebSocket stream to {rtmp_urls}")
        
        # We read from pipe:0 (stdin)
        cmd = [
            "ffmpeg", 
            "-i", "pipe:0", 
            "-c:v", "libx264", 
            "-preset", "veryfast", 
            "-b:v", "3000k", 
            "-maxrate", "3000k", 
            "-bufsize", "6000k", 
            "-pix_fmt", "yuv420p", 
            "-g", "50", 
            "-c:a", "aac", 
            "-b:a", "160k", 
            "-ar", "44100", 
            "-f", "flv", 
            rtmp_urls[0]
        ]
        
        try:
            # We must open stdin as PIPE to write chunks to it
            self.active_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            return True
        except Exception as e:
            print(f"[FFmpeg Engine] Error starting ws stream: {e}")
            self.status = "idle"
            self.active_process = None
            return False

    def write_chunk(self, chunk: bytes):
        if self.active_process and self.active_process.stdin:
            try:
                self.active_process.stdin.write(chunk)
                self.active_process.stdin.flush()
            except Exception as e:
                print(f"[FFmpeg Engine] Broken pipe: {e}")
                self.stop()

    def stop(self):
        if self.active_process:
            if self.active_process.stdin:
                try:
                    self.active_process.stdin.close()
                except:
                    pass
            self.active_process.terminate()
        self.status = "idle"
        self.active_process = None
        print("[FFmpeg Engine] Stream stopped.")

engine = Engine()
