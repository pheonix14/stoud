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

function openSaveModal() {
    document.getElementById("save-modal").classList.add("active");
}

function closeSaveModal() {
    document.getElementById("save-modal").classList.remove("active");
    document.getElementById("save-title").value = "";
    document.getElementById("save-url").value = "";
}

async function loadSavedVideos() {
    try {
        const response = await fetch("/api/saved");
        const videos = await response.json();
        
        const grid = document.getElementById("saved-grid");
        
        if (videos.length === 0) {
            grid.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; color: var(--text-secondary); padding: 4rem;">
                    Your video library is empty. Bookmark links to start streaming them instantly!
                </div>
            `;
            return;
        }
        
        grid.innerHTML = "";
        videos.forEach(v => {
            const card = document.createElement("div");
            card.className = "video-item";
            
            let badgeClass = "direct";
            let badgeLabel = "Direct Link";
            if (v.type === "youtube") {
                badgeClass = "youtube";
                badgeLabel = "YouTube";
            } else if (v.type === "gdrive") {
                badgeClass = "gdrive";
                badgeLabel = "Google Drive";
            }
            
            card.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem;">
                    <div class="video-title">${v.title}</div>
                    <span class="video-badge ${badgeClass}">${badgeLabel}</span>
                </div>
                <div class="video-url">${v.url}</div>
                <div class="video-meta">
                    <button class="btn btn-primary btn-sm" onclick="playVideo('${v.url}')">
                        <svg width="12" height="12" fill="currentColor" viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                        Stream Now
                    </button>
                    <button class="btn btn-secondary btn-sm" style="background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.2); color: #f87171;" onclick="deleteVideo('${v.id}')">
                        Delete
                    </button>
                </div>
            `;
            grid.appendChild(card);
        });
    } catch (err) {
        console.error("Error loading library:", err);
    }
}

async function saveVideo() {
    const title = document.getElementById("save-title").value.trim();
    const url = document.getElementById("save-url").value.trim();
    
    if (!title || !url) {
        showToast("Please enter both a title and a valid URL.", "danger");
        return;
    }
    
    try {
        const response = await fetch("/api/saved", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title, url })
        });
        const data = await response.json();
        
        if (data.success) {
            showToast("Video bookmarked to library!");
            closeSaveModal();
            loadSavedVideos();
        } else {
            showToast(`Failed: ${data.error}`, "danger");
        }
    } catch (err) {
        showToast("Error bookmarking video link.", "danger");
    }
}

async function playVideo(url) {
    showToast("Resolving library stream... starting broadcast.");
    try {
        const response = await fetch("/api/stream/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, quality: "copy" })
        });
        const data = await response.json();
        
        if (data.success) {
            showToast("Stream started! Check Dashboard logs.");
        } else {
            showToast(`Failed: ${data.error}`, "danger");
        }
    } catch (err) {
        showToast("Error initiating broadcast.", "danger");
    }
}

async function deleteVideo(id) {
    if (!confirm("Are you sure you want to remove this video bookmark?")) return;
    try {
        const response = await fetch(`/api/saved/${id}`, { method: "DELETE" });
        const data = await response.json();
        if (data.success) {
            showToast("Video removed from library.");
            loadSavedVideos();
        } else {
            showToast("Failed to delete video.", "danger");
        }
    } catch (err) {
        showToast("Error deleting video.", "danger");
    }
}

// Initialise
loadSavedVideos();
