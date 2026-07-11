let ffmpegInterval = null;
let destinationsList = [];

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

function triggerFilePicker(id) {
    document.getElementById(id).click();
}

async function handleFileUpload(input, targetInputId) {
    if (input.files.length === 0) return;
    const file = input.files[0];
    
    // Check local upload warning
    if (file.size > 60 * 1024 * 1024) {
        showToast("File is too large! Maximum local upload is 60MB. Use remote links for large content.", "danger");
        input.value = "";
        return;
    }
    
    showToast(`Uploading ${file.name}...`);
    
    const formData = new FormData();
    formData.append("file", file);
    
    try {
        const response = await fetch("/api/upload", {
            method: "POST",
            body: formData
        });
        const data = await response.json();
        if (data.success) {
            showToast("File uploaded successfully!");
            document.getElementById(targetInputId).value = data.url;
        } else {
            showToast(`Upload failed: ${data.error}`, "danger");
        }
    } catch (err) {
        showToast("Error uploading file.", "danger");
    }
    input.value = ""; // Reset
}

async function loadConfig() {
    try {
        const response = await fetch("/api/config");
        const config = await response.json();
        
        const s = config.settings || {};
        document.getElementById("default-quality").value = s.quality || "copy";
        document.getElementById("auto-ping-url").value = s.auto_ping_url || "";
        document.getElementById("loop-current-video").checked = s.loop_current_video || false;
        document.getElementById("budget-mode").checked = s.budget_mode || false;
        
        // Break Mode configs
        document.getElementById("break-mode").checked = s.break_mode || false;
        document.getElementById("break-video").value = s.break_video_url || "";
        document.getElementById("break-image").value = s.break_image_url || "";
        document.getElementById("intro-video").value = s.intro_video_url || "";
        document.getElementById("intro-enabled").checked = s.intro_enabled !== false;
        document.getElementById("ending-video").value = s.ending_video_url || "";
        document.getElementById("outro-enabled").checked = s.outro_enabled !== false;
        
        // GitHub configurations
        const gh = s.github_backup || {};
        document.getElementById("git-enabled").checked = gh.enabled || false;
        document.getElementById("git-repo").value = gh.repo || "";
        document.getElementById("git-branch").value = gh.branch || "main";
        document.getElementById("git-path").value = gh.path || "stoud-config.json";
        document.getElementById("git-token").value = gh.token || "";
        
        toggleGitFields();
        
        // Load Ingestion Destinations
        destinationsList = s.destinations || [];
        renderDestinations();
        
    } catch (err) {
        showToast("Failed to load configuration from backend.", "danger");
    }
}

function renderDestinations() {
    const tbody = document.getElementById("destinations-tbody");
    tbody.innerHTML = "";
    
    if (destinationsList.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" style="text-align: center; color: var(--text-secondary); padding: 1.5rem;">
                    No ingestion platforms configured. Add one to start streaming.
                </td>
            </tr>
        `;
        return;
    }
    
    destinationsList.forEach((d, index) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>
                <input type="text" class="form-control d-name" style="padding: 0.4rem 0.8rem; font-size: 0.85rem;" placeholder="e.g. YouTube" value="${d.name}">
            </td>
            <td>
                <input type="text" class="form-control d-url" style="padding: 0.4rem 0.8rem; font-size: 0.85rem; font-family: var(--font-mono)" placeholder="rtmp://..." value="${d.rtmp_url}">
            </td>
            <td>
                <input type="password" class="form-control d-key" style="padding: 0.4rem 0.8rem; font-size: 0.85rem; font-family: var(--font-mono)" placeholder="Stream Key" value="${d.stream_key}">
            </td>
            <td style="text-align: center; vertical-align: middle;">
                <div style="display: flex; gap: 0.75rem; align-items: center; justify-content: center;">
                    <input type="checkbox" class="d-enabled" style="width:16px; height:16px; cursor:pointer;" ${d.enabled ? "checked" : ""}>
                    <button class="btn btn-danger btn-sm" style="padding: 0.2rem 0.4rem; background: var(--danger-color);" onclick="deleteDestinationRow(${index})">&times;</button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function addNewDestinationRow() {
    // Read current input values first to preserve edits
    syncDestinationsFromDOM();
    
    destinationsList.push({
        id: "dest-" + Date.now(),
        name: "",
        rtmp_url: "",
        stream_key: "",
        enabled: true
    });
    renderDestinations();
}

function deleteDestinationRow(index) {
    syncDestinationsFromDOM();
    destinationsList.splice(index, 1);
    renderDestinations();
}

function syncDestinationsFromDOM() {
    const tbody = document.getElementById("destinations-tbody");
    const rows = tbody.querySelectorAll("tr");
    
    if (rows.length === 0 || destinationsList.length === 0) return;
    
    rows.forEach((tr, index) => {
        const nameInput = tr.querySelector(".d-name");
        const urlInput = tr.querySelector(".d-url");
        const keyInput = tr.querySelector(".d-key");
        const enabledInput = tr.querySelector(".d-enabled");
        
        if (nameInput && destinationsList[index]) {
            destinationsList[index].name = nameInput.value.trim();
            destinationsList[index].rtmp_url = urlInput.value.trim();
            destinationsList[index].stream_key = keyInput.value.trim();
            destinationsList[index].enabled = enabledInput.checked;
        }
    });
}

function toggleGitFields() {
    const enabled = document.getElementById("git-enabled").checked;
    document.getElementById("git-fields-container").style.display = enabled ? "flex" : "none";
}

function toggleBreakModeUI() {
    // Optional highlight
}

async function checkFFmpegStatus() {
    try {
        const response = await fetch("/api/status");
        const data = await response.json();
        const status = data.ffmpeg;
        const descr = document.getElementById("ffmpeg-status-descr");
        const btn = document.getElementById("ffmpeg-btn");
        
        descr.innerText = `Current Status: ${status}`;
        
        if (status === "Not Installed" || status === "Download Failed" || status === "Extraction Failed") {
            btn.style.display = "block";
            btn.disabled = false;
            clearInterval(ffmpegInterval);
        } else if (status.startsWith("Downloading") || status.startsWith("Extracting")) {
            btn.style.display = "block";
            btn.innerText = "Processing Setup...";
            btn.disabled = true;
            if (!ffmpegInterval) {
                ffmpegInterval = setInterval(checkFFmpegStatus, 1500);
            }
        } else {
            btn.style.display = "none";
            clearInterval(ffmpegInterval);
        }
    } catch (err) {
        console.error("Error reading FFmpeg status:", err);
    }
}

async function downloadFFmpeg() {
    try {
        const response = await fetch("/api/ffmpeg/download", { method: "POST" });
        const data = await response.json();
        if (data.success) {
            showToast("FFmpeg Setup triggered. Check progress.");
            checkFFmpegStatus();
            ffmpegInterval = setInterval(checkFFmpegStatus, 1500);
        }
    } catch (err) {
        showToast("Error triggering download.", "danger");
    }
}

async function saveAllSettings() {
    syncDestinationsFromDOM();
    
    const quality = document.getElementById("default-quality").value;
    const auto_ping_url = document.getElementById("auto-ping-url").value.trim();
    const loop_current_video = document.getElementById("loop-current-video").checked;
    const budget_mode = document.getElementById("budget-mode").checked;
    
    // Break mode configurations
    const break_mode = document.getElementById("break-mode").checked;
    const break_video_url = document.getElementById("break-video").value.trim();
    const break_image_url = document.getElementById("break-image").value.trim();
    const intro_enabled = document.getElementById("intro-enabled").checked;
    const intro_video_url = document.getElementById("intro-video").value.trim();
    const outro_enabled = document.getElementById("outro-enabled").checked;
    const ending_video_url = document.getElementById("ending-video").value.trim();
    
    // GitHub Configurations
    const git_enabled = document.getElementById("git-enabled").checked;
    const git_repo = document.getElementById("git-repo").value.trim();
    const git_branch = document.getElementById("git-branch").value.trim();
    const git_path = document.getElementById("git-path").value.trim();
    const git_token = document.getElementById("git-token").value.trim();
    
    const payload = {
        destinations: destinationsList,
        quality,
        loop_current_video,
        budget_mode,
        auto_ping_url,
        break_mode,
        break_video_url,
        break_image_url,
        intro_enabled,
        intro_video_url,
        outro_enabled,
        ending_video_url,
        github_backup: {
            enabled: git_enabled,
            repo: git_repo,
            branch: git_branch || "main",
            path: git_path || "stoud-config.json",
            token: git_token
        }
    };
    
    try {
        const response = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (data.success) {
            showToast("Settings updated successfully!");
            loadConfig();
        } else {
            showToast("Failed to save configuration settings.", "danger");
        }
    } catch (err) {
        showToast("Error connecting to server to save settings.", "danger");
    }
}

// Initialise
loadConfig();
checkFFmpegStatus();
