let isStreaming = false;
let logLinesCount = 0;
let logsCleared = false;
let currentPlayingUrl = "";
let currentPlayingTitle = "";
let currentLoopState = false;

function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
    `;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function getYouTubeId(url) {
    const regExp = /^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|\&v=)([^#\&\?]*).*/;
    const match = url.match(regExp);
    return (match && match[2].length === 11) ? match[2] : null;
}

function getGDriveId(url) {
    const match = url.match(/\/file\/d\/([a-zA-Z0-9_-]+)/) || url.match(/id=([a-zA-Z0-9_-]+)/);
    return match ? match[1] : null;
}

function updatePreviewPlayer(url, title) {
    const container = document.getElementById("preview-player-container");
    
    if (!url) {
        container.innerHTML = `
            <div id="player-placeholder" style="color: var(--text-secondary); text-align: center;">
                <svg width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" style="margin-bottom: 0.5rem; color: rgba(255,255,255,0.1);"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                <div>Preview Offline - Stream Inactive</div>
            </div>
        `;
        currentPlayingUrl = "";
        return;
    }

    if (currentPlayingUrl === url) return; // Already loading/playing
    currentPlayingUrl = url;

    const ytId = getYouTubeId(url);
    const gdId = getGDriveId(url);

    if (ytId) {
        container.innerHTML = `
            <iframe width="100%" height="100%" src="https://www.youtube.com/embed/${ytId}?autoplay=1&mute=1" 
                    frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                    allowfullscreen style="border: none;"></iframe>
        `;
    } else if (gdId) {
        container.innerHTML = `
            <iframe src="https://drive.google.com/file/d/${gdId}/preview" width="100%" height="100%" 
                    frameborder="0" allow="autoplay" allowfullscreen style="border: none;"></iframe>
        `;
    } else if (url.endsWith(".mp4") || url.endsWith(".webm") || url.endsWith(".mkv") || url.includes("/uploads/")) {
        container.innerHTML = `
            <video width="100%" height="100%" controls autoplay muted src="${url}" style="object-fit: contain;"></video>
        `;
    } else {
        container.innerHTML = `
            <div style="color: var(--text-secondary); text-align: center; padding: 1rem;">
                <div style="font-weight:600; margin-bottom: 0.5rem; color: #fff;">External Link Broadcast</div>
                <div class="video-url" style="max-width: 300px; margin: 0 auto; margin-bottom: 1rem;">${url}</div>
                <div style="font-size:0.8rem;">Preview unavailable for this format. Stream is transmitting in background.</div>
            </div>
        `;
    }
}

async function fetchStatus() {
    try {
        const response = await fetch("/api/status");
        const data = await response.json();
        
        const pill = document.getElementById("active-status-pill");
        const pillText = document.getElementById("active-status-text");
        const metricsCard = document.getElementById("stream-metrics-card");
        const breakBadge = document.getElementById("break-status-badge");
        
        // Show break status
        breakBadge.style.display = data.break_mode ? "inline-block" : "none";
        
        if (data.status === "streaming") {
            isStreaming = true;
            pill.className = "status-pill streaming";
            pillText.innerText = data.title === "Break Stream" ? "Break Mode Active" : "Broadcasting Live";
            
            // Show metrics
            metricsCard.style.display = "block";
            
            const met = data.metrics || {};
            document.getElementById("metric-health").innerText = data.health || "Active";
            document.getElementById("metric-health").style.color = (data.health === "Active" || data.health === "Healthy") ? "var(--success-color)" : "var(--danger-color)";
            document.getElementById("metric-bitrate").innerText = `${met.bitrate || "N/A"} (${met.speed || "N/A"})`;
            document.getElementById("metric-frames").innerText = `${met.fps || "N/A"} fps (frame ${met.frame || "0"})`;
            document.getElementById("metric-uptime").innerText = met.time || "00:00:00";
            
            // Load preview player
            updatePreviewPlayer(data.url, data.title);
        } else {
            isStreaming = false;
            pill.className = "status-pill idle";
            pillText.innerText = "Idle";
            metricsCard.style.display = "none";
            updatePreviewPlayer(null, null);
        }
        
        // Update Video Loop button text state
        currentLoopState = data.loop_current_video;
        const btnLoop = document.getElementById("btn-loop-current");
        if (currentLoopState) {
            btnLoop.innerText = "Loop Video: ON";
            btnLoop.className = "btn btn-primary";
        } else {
            btnLoop.innerText = "Loop Video: OFF";
            btnLoop.className = "btn btn-secondary";
        }
        
        // Render Active Queue
        renderQueue(data.queue || []);
        
        // Update Console Logs
        const logBody = document.getElementById("log-body");
        let logsToRender = data.logs || [];
        
        if (logsToRender.length !== logLinesCount) {
            logBody.innerHTML = "";
            logsToRender.forEach(msg => {
                const line = document.createElement("div");
                line.className = "console-line";
                if (msg.includes("[FFmpeg]")) {
                    line.className += " ffmpeg";
                } else if (msg.includes("Error") || msg.includes("failed")) {
                    line.className += " error";
                } else if (msg.includes("started") || msg.includes("success")) {
                    line.className += " success";
                }
                line.innerText = msg;
                logBody.appendChild(line);
            });
            logLinesCount = logsToRender.length;
            logBody.scrollTop = logBody.scrollHeight;
        }
        
    } catch (err) {
        console.error("Error fetching player status:", err);
    }
}

function renderQueue(queue) {
    const list = document.getElementById("live-queue-list");
    
    if (queue.length === 0) {
        list.innerHTML = `<span style="color: var(--text-secondary); font-size: 0.9rem;">Queue is empty. Stream will go idle after active video finishes.</span>`;
        return;
    }
    
    list.innerHTML = "";
    queue.forEach((item, index) => {
        const tr = document.createElement("div");
        tr.style.display = "flex";
        tr.style.justifyContent = "space-between";
        tr.style.alignItems = "center";
        tr.style.padding = "0.5rem 0.75rem";
        tr.style.borderRadius = "8px";
        tr.style.background = "rgba(255,255,255,0.03)";
        tr.style.border = "1px solid var(--glass-border)";
        
        let typeBadge = "direct";
        if (item.type === "youtube") typeBadge = "youtube";
        if (item.type === "gdrive") typeBadge = "gdrive";
        
        tr.innerHTML = `
            <div style="flex-grow: 1; overflow: hidden; margin-right: 1rem;">
                <div style="font-weight: 500; font-size: 0.9rem; text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">
                    ${index + 1}. ${item.title}
                </div>
                <div style="font-size: 0.7rem; color: var(--text-secondary); font-family: var(--font-mono);">${item.url}</div>
            </div>
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <span class="video-badge ${typeBadge}" style="font-size: 0.65rem; padding: 0.1rem 0.4rem;">${typeBadge.toUpperCase()}</span>
                <button class="btn btn-danger btn-sm" style="padding: 0.2rem 0.4rem; font-size: 0.75rem; background: rgba(239, 68, 68, 0.1);" onclick="removeQueueItem(${index})">-</button>
            </div>
        `;
        list.appendChild(tr);
    });
}

async function startStream() {
    const urlInput = document.getElementById("stream-url");
    const qualitySelect = document.getElementById("stream-quality");
    
    const url = urlInput.value.trim();
    const quality = qualitySelect.value;
    
    if (!url) {
        showToast("Please enter a video URL first.", "danger");
        return;
    }
    
    showToast("Resolving stream URL inputs...");
    try {
        const response = await fetch("/api/stream/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, quality })
        });
        const data = await response.json();
        if (data.success) {
            showToast("Streaming process launched!");
            urlInput.value = "";
            fetchStatus();
        } else {
            showToast(`Launch failed: ${data.error}`, "danger");
        }
    } catch (err) {
        showToast("Error starting broadcast.", "danger");
    }
}

async function stopStream() {
    try {
        const response = await fetch("/api/stream/stop", { method: "POST" });
        const data = await response.json();
        if (data.success) {
            showToast("Broadcaster engine stopped.");
            fetchStatus();
        } else {
            showToast("Failed to stop stream.", "danger");
        }
    } catch (err) {
        showToast("Error communicating with server.", "danger");
    }
}

async function toggleLoopCurrentVideo() {
    try {
        // Toggle the local state
        const targetState = !currentLoopState;
        
        // Fetch current config to modify settings
        const confResp = await fetch("/api/config");
        const config = await confResp.json();
        
        config.settings.loop_current_video = targetState;
        
        const saveResp = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(config.settings)
        });
        
        const data = await saveResp.json();
        if (data.success) {
            showToast(`Loop Video toggled ${targetState ? "ON" : "OFF"}`);
            fetchStatus();
        } else {
            showToast("Failed to save loop configuration.", "danger");
        }
    } catch (err) {
        showToast("Connection error while setting loop mode.", "danger");
    }
}

function openAddQueueModal() {
    document.getElementById("add-queue-modal").classList.add("active");
}

function closeAddQueueModal() {
    document.getElementById("add-queue-modal").classList.remove("active");
    document.getElementById("queue-title").value = "";
    document.getElementById("queue-url").value = "";
}

async function addVideoToQueueSubmit() {
    const title = document.getElementById("queue-title").value.trim();
    const url = document.getElementById("queue-url").value.trim();
    
    if (!url) {
        showToast("URL is required.", "danger");
        return;
    }
    
    try {
        const response = await fetch("/api/queue/add", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, title: title || "Queued Video" })
        });
        const data = await response.json();
        if (data.success) {
            showToast("Video added to live queue!");
            closeAddQueueModal();
            fetchStatus();
        } else {
            showToast("Failed to add item to queue.", "danger");
        }
    } catch (err) {
        showToast("Error adding item to queue.", "danger");
    }
}

async function removeQueueItem(index) {
    try {
        const response = await fetch(`/api/queue/${index}`, { method: "DELETE" });
        const data = await response.json();
        if (data.success) {
            showToast("Item removed from active queue.");
            fetchStatus();
        } else {
            showToast("Failed to remove item.", "danger");
        }
    } catch (err) {
        showToast("Error removing queue item.", "danger");
    }
}

async function clearQueue() {
    if (!confirm("Are you sure you want to clear the playback queue?")) return;
    try {
        const response = await fetch("/api/queue/clear", { method: "POST" });
        const data = await response.json();
        if (data.success) {
            showToast("Queue cleared.");
            fetchStatus();
        }
    } catch (err) {
        showToast("Error clearing queue.", "danger");
    }
}

function clearLogs() {
    document.getElementById("log-body").innerHTML = `<div class="console-line success">Terminal cleared locally.</div>`;
    logLinesCount = 0;
}

// Start Poll loop
fetchStatus();
setInterval(fetchStatus, 2000);
