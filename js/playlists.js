let playlistsCache = [];

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

function openPlaylistModal(id = null) {
    const modal = document.getElementById("playlist-modal");
    const title = document.getElementById("modal-title");
    const nameInput = document.getElementById("playlist-name");
    const idInput = document.getElementById("playlist-id");
    const tbody = document.getElementById("playlist-items-tbody");
    
    tbody.innerHTML = "";
    idInput.value = "";
    nameInput.value = "";
    
    if (id) {
        title.innerText = "Edit Playlist";
        idInput.value = id;
        const p = playlistsCache.find(x => x.id === id);
        if (p) {
            nameInput.value = p.name;
            p.items.forEach(item => {
                addPlaylistItemRow(item.title, item.url);
            });
        }
    } else {
        title.innerText = "Create Playlist";
        addPlaylistItemRow();
        addPlaylistItemRow();
    }
    
    modal.classList.add("active");
}

function closePlaylistModal() {
    document.getElementById("playlist-modal").classList.remove("active");
}

function addPlaylistItemRow(title = "", url = "") {
    const tbody = document.getElementById("playlist-items-tbody");
    const tr = document.createElement("tr");
    
    tr.innerHTML = `
        <td>
            <input type="text" class="form-control item-title" style="padding: 0.4rem 0.8rem; font-size: 0.85rem;" placeholder="Video Title" value="${title}">
        </td>
        <td>
            <input type="text" class="form-control item-url" style="padding: 0.4rem 0.8rem; font-size: 0.85rem; font-family: var(--font-mono)" placeholder="Paste URL..." value="${url}">
        </td>
        <td style="text-align: center;">
            <div style="display: flex; gap: 0.25rem; justify-content: center;">
                <button class="btn btn-secondary btn-sm" style="padding: 0.2rem 0.4rem;" onclick="moveRow(this, -1)">▲</button>
                <button class="btn btn-secondary btn-sm" style="padding: 0.2rem 0.4rem;" onclick="moveRow(this, 1)">▼</button>
                <button class="btn btn-danger btn-sm" style="padding: 0.2rem 0.4rem; background: var(--danger-color);" onclick="deleteRow(this)">&times;</button>
            </div>
        </td>
    `;
    tbody.appendChild(tr);
}

function deleteRow(btn) {
    btn.closest("tr").remove();
}

function moveRow(btn, direction) {
    const tr = btn.closest("tr");
    if (direction === -1) {
        const prev = tr.previousElementSibling;
        if (prev) tr.parentNode.insertBefore(tr, prev);
    } else {
        const next = tr.nextElementSibling;
        if (next) tr.parentNode.insertBefore(next, tr);
    }
}

async function loadPlaylists() {
    try {
        const response = await fetch("/api/playlists");
        const playlists = await response.json();
        playlistsCache = playlists;
        
        const grid = document.getElementById("playlists-grid");
        
        if (playlists.length === 0) {
            grid.innerHTML = `
                <div style="grid-column: 1/-1; text-align: center; color: var(--text-secondary); padding: 4rem;">
                    No playlists created yet. Create a queue to group videos together.
                </div>
            `;
            return;
        }
        
        grid.innerHTML = "";
        playlists.forEach(p => {
            const card = document.createElement("div");
            card.className = "card";
            card.style.marginBottom = "0";
            
            let itemsPreview = "";
            p.items.slice(0, 3).forEach(item => {
                itemsPreview += `
                    <div style="display: flex; justify-content: space-between; font-size: 0.85rem; border-bottom: 1px solid rgba(255,255,255,0.03); padding: 0.4rem 0;">
                        <span style="font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 70%;">${item.title}</span>
                        <span class="video-url" style="max-width: 25%; font-size: 0.7rem;">${item.url}</span>
                    </div>
                `;
            });
            if (p.items.length > 3) {
                itemsPreview += `<div style="text-align: center; font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.5rem;">+ ${p.items.length - 3} more items</div>`;
            }
            if (p.items.length === 0) {
                itemsPreview = `<span style="color: var(--text-secondary); font-size: 0.85rem;">Playlist is empty.</span>`;
            }
            
            card.innerHTML = `
                <div class="card-title">
                    <span>${p.name}</span>
                    <span class="video-badge youtube">${p.items.length} Videos</span>
                </div>
                <div style="display: flex; flex-direction: column; gap: 0.25rem; margin-bottom: 1.5rem;">
                    ${itemsPreview}
                </div>
                <div style="display: flex; gap: 0.5rem; border-top: 1px solid var(--glass-border); padding-top: 1rem; margin-top: auto;">
                    <button class="btn btn-secondary btn-sm" style="flex-grow: 1;" onclick="openPlaylistModal('${p.id}')">Edit</button>
                    <button class="btn btn-danger btn-sm" onclick="deletePlaylist('${p.id}')">Delete</button>
                </div>
            `;
            grid.appendChild(card);
        });
    } catch (err) {
        console.error("Error loading playlists:", err);
    }
}

async function savePlaylist() {
    const name = document.getElementById("playlist-name").value.trim();
    const id = document.getElementById("playlist-id").value;
    const tbody = document.getElementById("playlist-items-tbody");
    
    if (!name) {
        showToast("Please enter a playlist name.", "danger");
        return;
    }
    
    const items = [];
    const rows = tbody.querySelectorAll("tr");
    rows.forEach(tr => {
        const title = tr.querySelector(".item-title").value.trim();
        const url = tr.querySelector(".item-url").value.trim();
        if (url) {
            items.push({
                title: title || "Video Item",
                url: url
            });
        }
    });
    
    try {
        const response = await fetch("/api/playlists", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: id || null, name, items })
        });
        const data = await response.json();
        
        if (data.success) {
            showToast(id ? "Playlist updated successfully!" : "Playlist created!");
            closePlaylistModal();
            loadPlaylists();
        } else {
            showToast(`Failed: ${data.error}`, "danger");
        }
    } catch (err) {
        showToast("Error saving playlist.", "danger");
    }
}

async function deletePlaylist(id) {
    if (!confirm("Are you sure you want to delete this playlist?")) return;
    try {
        const response = await fetch(`/api/playlists/${id}`, { method: "DELETE" });
        const data = await response.json();
        if (data.success) {
            showToast("Playlist deleted successfully.");
            loadPlaylists();
        } else {
            showToast("Failed to delete playlist.", "danger");
        }
    } catch (err) {
        showToast("Error deleting playlist.", "danger");
    }
}

// Initialise
loadPlaylists();
