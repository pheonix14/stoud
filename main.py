import os
import sys
import threading
import time
import requests
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from handler import router
from ai_commenter import run_ai_commentator
from db import db

heartbeat_count = 0

def anti_sleep_pinger():
    global heartbeat_count
    time.sleep(10)
    while True:
        try:
            requests.get("http://127.0.0.1:8000/api/status", timeout=5)
            heartbeat_count += 1
            print(f"[Anti-Sleep] Ping sent. Total: {heartbeat_count}")
        except Exception as e:
            pass
        time.sleep(600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: pull latest from github if we crashed
    print("Loading DB state...")
    db.load()
    
    pinger = threading.Thread(target=anti_sleep_pinger, daemon=True)
    pinger.start()
    
    ai = threading.Thread(target=run_ai_commentator, daemon=True)
    ai.start()
    
    yield
    # Shutdown

app = FastAPI(title="Stoud API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

frontend_dir = os.path.join(os.path.dirname(__file__), "dist")

@app.get("/")
async def root():
    if os.path.exists(os.path.join(frontend_dir, "index.html")):
        with open(os.path.join(frontend_dir, "index.html"), "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Frontend not built yet. Run npm run build.</h1>")

if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")

@app.get("/api/heartbeat")
async def get_heartbeat():
    return {"heartbeats": heartbeat_count}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
