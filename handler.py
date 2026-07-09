from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from engine import engine
import yt_dlp

router = APIRouter()

class ResolvePayload(BaseModel):
    url: str

@router.post("/api/resolve-video")
async def resolve_video(req: ResolvePayload):
    try:
        ydl_opts = {'format': 'best', 'quiet': True, 'noplaylist': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(req.url, download=False)
            return {"status": "success", "url": info['url']}
    except Exception as e:
        # If yt-dlp fails, just return original url
        print(f"[yt-dlp error] {e}")
        return {"status": "success", "url": req.url}

class StreamPayload(BaseModel):
    urls: List[str]
    rtmp_urls: List[str]
    overlay_url: str = ""
    background_url: str = ""
    loop: bool = False

@router.post("/api/start-stream")
async def start_stream(req: StreamPayload):
    if engine.status != "idle":
        return JSONResponse({"status": "error", "message": "Stream is already running"})

    if not req.rtmp_urls or not req.urls:
        return JSONResponse({"status": "error", "message": "Missing URLs or RTMP destinations"})

    engine.start_stream(req.urls, req.rtmp_urls, req.overlay_url, req.background_url, req.loop)
    return {"status": "success", "message": "Stream started to multiple destinations"}

@router.websocket("/api/ws/stream")
async def ws_stream(websocket: WebSocket, rtmp: str = None):
    await websocket.accept()
    if engine.status != "idle":
        engine.stop()
        
    rtmp_url = rtmp or "rtmp://a.rtmp.youtube.com/live2/dummy"
    success = engine.start_ws_stream([rtmp_url])
    
    if not success:
        await websocket.close()
        return

    try:
        while True:
            # Receive raw binary chunk from browser
            data = await websocket.receive_bytes()
            engine.write_chunk(data)
    except WebSocketDisconnect:
        print("[WebSocket] Client disconnected")
        engine.stop()
    except Exception as e:
        print(f"[WebSocket] Error: {e}")
        engine.stop()

@router.post("/api/stop-stream")
async def stop_stream():
    engine.stop()
    return {"status": "success", "message": "Stream stopped"}

@router.get("/api/status")
async def status():
    return {
        "status": engine.status,
        "active_destinations": engine.rtmp_urls if engine.status != "idle" else []
    }

@router.get("/api/ai-script")
async def get_ai_script():
    try:
        with open("latest_ai_script.txt", "r", encoding="utf-8") as f:
            script = f.read()
            return {"script": script}
    except Exception:
        return {"script": "Waiting for AI commentator to start..."}
