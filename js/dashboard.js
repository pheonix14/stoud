let isStreaming = false;
let logLinesCount = 0;
let currentPlayingUrl = "";
let currentLoopState = false;
let savedDestinations = [];

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

    if (currentPlayingUrl === url) return;
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
                <div style="font-size:0.8rem;">Preview unavailable. Stream is running.</div>
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
        
        breakBadge.style.display = data.break_mode ? "inline-block" : "none";
        
        if (data.status === "streaming") {
            isStreaming = true;
            pill.className = "status-pill streaming";
            pillText.innerText = data.title === "Break Stream" ? "Break Mode Active" : "Broadcasting Live";
            
            metricsCard.style.display = "block";
            
            const met = data.metrics || {};
            document.getElementById("metric-health").innerText = data.health || "Active";
            document.getElementById("metric-health").style.color = (data.health === "Active" || data.health === "Healthy") ? "var(--success-color)" : "var(--danger-color)";
            document.getElementById("metric-bitrate").innerText = `${met.bitrate || "N/A"} (${met.speed || "N/A"})`;
            document.getElementById("metric-frames").innerText = `${met.fps || "N/A"} fps (frame ${met.frame || "0"})`;
            document.getElementById("metric-uptime").innerText = met.time || "00:00:00";
            
            updatePreviewPlayer(data.url, data.title);
            
            document.getElementById("btn-start-stream").style.display = "none";
            document.getElementById("btn-stop-stream").style.display = "flex";
            document.getElementById("stream-url").disabled = true;
            if (document.getElementById("stream-url").value === "") {
                document.getElementById("stream-url").value = data.url;
            }
        } else {
            isStreaming = false;
            pill.className = "status-pill idle";
            pillText.innerText = "Idle";
            metricsCard.style.display = "none";
            updatePreviewPlayer(null, null);
            
            document.getElementById("btn-start-stream").style.display = "flex";
            document.getElementById("btn-stop-stream").style.display = "none";
            document.getElementById("stream-url").disabled = false;
        }
        
        // Loop State Button Update
        currentLoopState = data.loop_current_video;
        const btnLoop = document.getElementById("btn-loop-current");
        if (currentLoopState) {
            btnLoop.innerText = "Loop Video: ON";
            btnLoop.className = "btn btn-primary";
        } else {
            btnLoop.innerText = "Loop Video: OFF";
            btnLoop.className = "btn btn-secondary";
        }
        
        renderQueue(data.queue || []);
        
        // Update Logs Console
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

// Load configurations, populate destinations list and dynamic selectors (Intro, Ending, Break)
async function initDashboard() {
    try {
        const response = await fetch("/api/config");
        const config = await response.json();
        
        const settings = config.settings || {};
        savedDestinations = settings.destinations || [];
        
        // 1. Populate Dest Ingest selector
        const destSelect = document.getElementById("destination-selector");
        destSelect.innerHTML = `<option value="custom">-- Custom RTMP Ingest URL --</option>`;
        savedDestinations.forEach(d => {
            destSelect.innerHTML += `<option value="${d.id}">${d.name} (${d.enabled ? 'Enabled' : 'Disabled'})</option>`;
        });
        
        // Pre-select first enabled destination if available
        const firstEnabled = savedDestinations.find(d => d.enabled);
        if (firstEnabled) {
            destSelect.value = firstEnabled.id;
            applySavedDestination();
        }

        // Render targets list in analytics panel
        const destListDiv = document.getElementById("active-destinations-list");
        destListDiv.innerHTML = "";
        savedDestinations.forEach(d => {
            const row = document.createElement("div");
            row.style.display = "flex";
            row.style.justifyContent = "space-between";
            row.style.alignItems = "center";
            row.style.fontSize = "0.85rem;";
            row.innerHTML = `
                <span style="font-weight:500;">${d.name}</span>
                <span class="video-badge ${d.enabled ? 'success' : 'idle'}" style="font-size:0.65rem;">
                    ${d.enabled ? 'ACTIVE' : 'DISABLED'}
                </span>
            `;
            destListDiv.appendChild(row);
        });

        // 2. Populate Intro, Outro, Break selectors from Library bookmarks
        const introSel = document.getElementById("intro-selector");
        const outroSel = document.getElementById("outro-selector");
        const breakSel = document.getElementById("break-selector");
        
        const library = config.saved_videos || [];
        library.forEach(v => {
            const opt = `<option value="${v.url}">${v.title}</option>`;
            introSel.innerHTML += opt;
            outroSel.innerHTML += opt;
            breakSel.innerHTML += opt;
        });

        // Set initial addon values from settings config
        introSel.value = settings.intro_video_url || "";
        outroSel.value = settings.ending_video_url || "";
        breakSel.value = settings.break_video_url || "";

        // 3. Load Schedules List
        renderHomeSchedules(config.schedules || []);
        
    } catch (err) {
        console.error("Error initializing cockpit configurations:", err);
    }
}

function applySavedDestination() {
    const selectedId = document.getElementById("destination-selector").value;
    const customGroup = document.getElementById("custom-rtmp-group");
    const rtmpUrlInput = document.getElementById("custom-rtmp-url");
    
    if (selectedId === "custom") {
        customGroup.style.display = "block";
        rtmpUrlInput.value = "";
    } else {
        customGroup.style.display = "none";
        const dest = savedDestinations.find(d => d.id === selectedId);
        if (dest) {
            // Concatenate URL and key
            rtmpUrlInput.value = `${dest.rtmp_url.rstrip('/')}/${dest.stream_key}`;
        }
    }
}

// Add string prototype helper if needed
String.prototype.rstrip = function(chars) {
    let end = this.length - 1;
    while (end >= 0 && (chars || " \t\r\n").indexOf(this[end]) !== -1) {
        end--;
    }
    return this.substring(0, end + 1);
};

// Save launcher selections back to server to reflect in scheduling injections
async function saveLauncherAddons() {
    const introVal = document.getElementById("intro-selector").value;
    const outroVal = document.getElementById("outro-selector").value;
    const breakVal = document.getElementById("break-selector").value;
    
    try {
        const confResp = await fetch("/api/config");
        const config = await confResp.json();
        
        config.settings.intro_video_url = introVal;
        config.settings.ending_video_url = outroVal;
        config.settings.break_video_url = breakVal;
        
        await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(config.settings)
        });
    } catch (e) {
        console.error("Failed to sync launcher addon selections to settings:", e);
    }
}

async function startStream() {
    const urlInput = document.getElementById("stream-url");
    const qualitySelect = document.getElementById("stream-quality");
    const rtmpInput = document.getElementById("custom-rtmp-url");
    
    const url = urlInput.value.trim();
    const quality = qualitySelect.value;
    const rtmp_url = rtmpInput.value.trim();
    
    if (!url) {
        showToast("Please enter a video URL first.", "danger");
        return;
    }
    
    // Save selector preferences first
    await saveLauncherAddons();
    
    showToast("Resolving stream URL inputs...");
    try {
        const payload = { url, quality };
        // If Custom RTMP or destination URL is filled, pass it
        if (rtmp_url) {
            payload.rtmp_url = rtmp_url;
        }
        
        const response = await fetch("/api/stream/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
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
        const targetState = !currentLoopState;
        
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
        }
    } catch (err) {
        showToast("Connection error while setting loop mode.", "danger");
    }
}

function renderHomeSchedules(schedules) {
    const tbody = document.getElementById("home-schedules-tbody");
    
    if (schedules.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="3" style="text-align: center; color: var(--text-secondary); padding: 1.5rem;">
                    No schedules planned. Go to Schedules page to add.
                </td>
            </tr>
        `;
        return;
    }
    
    tbody.innerHTML = "";
    schedules.slice(0, 5).forEach(s => {
        const row = document.createElement("tr");
        
        const dt = new Date(s.time.replace("T", " "));
        const timeStr = dt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' ' + dt.toLocaleDateString([], { month: 'short', day: 'numeric' });
        
        row.innerHTML = `
            <td><strong>${s.name}</strong></td>
            <td><span style="font-family: var(--font-mono); font-size: 0.8rem;">${timeStr}</span></td>
            <td style="text-align: right;">
                <button class="btn btn-primary btn-sm" onclick="runScheduleNow('${s.id}')">Stream Now</button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

async function runScheduleNow(id) {
    showToast("Launching schedule immediately...");
    try {
        const response = await fetch(`/api/schedules/${id}/run`, { method: "POST" });
        const data = await response.json();
        if (data.success) {
            showToast("Schedule started streaming!");
            fetchStatus();
        } else {
            showToast(`Could not start: ${data.error}`, "danger");
        }
    } catch (err) {
        showToast("Error triggering schedule stream.", "danger");
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

// Initialise
initDashboard();
fetchStatus();
setInterval(fetchStatus, 2000);
// Also refresh lists every 10 seconds
setInterval(initDashboard, 10000);
