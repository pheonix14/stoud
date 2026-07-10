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

function openScheduleModal() {
    document.getElementById("schedule-modal").classList.add("active");
    const timeInput = document.getElementById("sched-time");
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    timeInput.value = now.toISOString().slice(0, 16);
    loadPlaylistsDropdown();
}

function closeScheduleModal() {
    document.getElementById("schedule-modal").classList.remove("active");
    document.getElementById("sched-name").value = "";
    document.getElementById("sched-url").value = "";
}

function toggleSourceType() {
    const type = document.getElementById("source-type").value;
    const linkGroup = document.getElementById("link-source-group");
    const playlistGroup = document.getElementById("playlist-source-group");
    
    if (type === "link") {
        linkGroup.style.display = "flex";
        playlistGroup.style.display = "none";
    } else {
        linkGroup.style.display = "none";
        playlistGroup.style.display = "flex";
    }
}

async function loadPlaylistsDropdown() {
    try {
        const response = await fetch("/api/playlists");
        const playlists = await response.json();
        const dropdown = document.getElementById("sched-playlist");
        
        dropdown.innerHTML = "";
        if (playlists.length === 0) {
            dropdown.innerHTML = `<option value="">No playlists found. Create one first.</option>`;
            return;
        }
        
        playlists.forEach(p => {
            dropdown.innerHTML += `<option value="playlist:${p.id}">${p.name} (${p.items.length} items)</option>`;
        });
    } catch (err) {
        console.error("Error loading playlists:", err);
    }
}

async function loadSchedules() {
    try {
        const response = await fetch("/api/schedules");
        const schedules = await response.json();
        const tbody = document.getElementById("schedules-table-body");
        
        if (schedules.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align: center; color: var(--text-secondary); padding: 3rem;">
                        No schedules planned. Create one above to stream automatically.
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = "";
        schedules.forEach(s => {
            const row = document.createElement("tr");
            
            let sourceHtml = "";
            if (s.url.startsWith("playlist:")) {
                sourceHtml = `<span class="video-badge gdrive">Playlist</span>`;
            } else if (s.url.includes("youtube.com") || s.url.includes("youtu.be")) {
                sourceHtml = `<span class="video-badge youtube">YouTube</span>`;
            } else if (s.url.includes("drive.google.com")) {
                sourceHtml = `<span class="video-badge gdrive">Google Drive</span>`;
            } else {
                sourceHtml = `<span class="video-badge direct">Direct Link</span>`;
            }
            
            let statusClass = "idle";
            if (s.status === "running") statusClass = "streaming";
            if (s.status === "completed") statusClass = "success";
            if (s.status === "failed") statusClass = "danger";
            
            const dt = new Date(s.time.replace("T", " "));
            const formattedTime = dt.toLocaleString();
            
            row.innerHTML = `
                <td><strong>${s.name}</strong></td>
                <td>
                    <div style="display: flex; align-items: center; gap: 0.5rem;">
                        ${sourceHtml}
                        <span class="video-url" style="max-width: 250px;">${s.url}</span>
                    </div>
                </td>
                <td><span style="font-family: var(--font-mono); font-size: 0.9rem;">${formattedTime}</span></td>
                <td><span class="video-badge ${statusClass}">${s.status}</span></td>
                <td>
                    <div style="display: flex; gap: 0.5rem;">
                        <button class="btn btn-primary btn-sm" onclick="runScheduleNow('${s.id}')">Stream Now</button>
                        <button class="btn btn-danger btn-sm" style="background: rgba(239, 68, 68, 0.1);" onclick="deleteSchedule('${s.id}')">Delete</button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    } catch (err) {
        console.error("Error loading schedules:", err);
    }
}

async function saveSchedule() {
    const name = document.getElementById("sched-name").value.trim();
    const type = document.getElementById("source-type").value;
    const time = document.getElementById("sched-time").value;
    
    let url = "";
    if (type === "link") {
        url = document.getElementById("sched-url").value.trim();
    } else {
        url = document.getElementById("sched-playlist").value;
    }
    
    if (!name || !url || !time) {
        showToast("Please enter all required fields.", "danger");
        return;
    }
    
    try {
        const response = await fetch("/api/schedules", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, url, time })
        });
        const data = await response.json();
        
        if (data.success) {
            showToast("Schedule added successfully!");
            closeScheduleModal();
            loadSchedules();
        } else {
            showToast(`Failed: ${data.error}`, "danger");
        }
    } catch (err) {
        showToast("Error creating schedule.", "danger");
    }
}

async function runScheduleNow(id) {
    showToast("Launching schedule immediately...");
    try {
        const response = await fetch(`/api/schedules/${id}/run`, { method: "POST" });
        const data = await response.json();
        if (data.success) {
            showToast("Schedule started streaming!");
            loadSchedules();
        } else {
            showToast(`Could not start: ${data.error}`, "danger");
        }
    } catch (err) {
        showToast("Error triggering schedule stream.", "danger");
    }
}

async function deleteSchedule(id) {
    if (!confirm("Are you sure you want to delete this schedule?")) return;
    try {
        const response = await fetch(`/api/schedules/${id}`, { method: "DELETE" });
        const data = await response.json();
        if (data.success) {
            showToast("Schedule deleted.");
            loadSchedules();
        } else {
            showToast("Failed to delete schedule.", "danger");
        }
    } catch (err) {
        showToast("Error deleting schedule.", "danger");
    }
}

// Initialise
loadSchedules();
setInterval(loadSchedules, 10000);
