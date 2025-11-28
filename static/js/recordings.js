// Recordings page JavaScript
let currentPage = 0;
const pageSize = 50;
let currentRecordings = [];
let allGroups = [];
let selectedRecordings = new Set();

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
    loadRecordings();
    loadStats();
    loadGroups();
    
    // Search input with debounce
    let searchTimeout;
    document.getElementById('search-input').addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            currentPage = 0;
            loadRecordings();
        }, 300);
    });
    
    // Filter change handlers
    document.getElementById('format-filter').addEventListener('change', () => {
        currentPage = 0;
        loadRecordings();
    });
    
    document.getElementById('favorite-filter').addEventListener('change', () => {
        currentPage = 0;
        loadRecordings();
    });
    
    document.getElementById('group-filter').addEventListener('change', () => {
        currentPage = 0;
        loadRecordings();
    });
    
    document.getElementById('clear-filters').addEventListener('click', () => {
        document.getElementById('search-input').value = '';
        document.getElementById('format-filter').value = '';
        document.getElementById('favorite-filter').value = '';
        document.getElementById('group-filter').value = '';
        document.getElementById('date-from-filter').value = '';
        document.getElementById('date-to-filter').value = '';
        document.getElementById('sort-filter').value = 'newest';
        currentPage = 0;
        loadRecordings();
    });

    // Date filter handlers
    document.getElementById('date-from-filter').addEventListener('change', () => {
        currentPage = 0;
        loadRecordings();
    });
    
    document.getElementById('date-to-filter').addEventListener('change', () => {
        currentPage = 0;
        loadRecordings();
    });

    // Sort handler
    document.getElementById('sort-filter').addEventListener('change', () => {
        currentPage = 0;
        loadRecordings();
    });

    // Bulk operations
    document.getElementById('select-all-recordings').addEventListener('click', toggleSelectAll);
    document.getElementById('bulk-favorite').addEventListener('click', bulkFavorite);
    document.getElementById('bulk-delete').addEventListener('click', bulkDelete);
    document.getElementById('export-recordings').addEventListener('click', exportRecordings);
});

async function loadRecordings() {
    const search = document.getElementById('search-input').value.trim();
    const format = document.getElementById('format-filter').value;
    const favoriteFilter = document.getElementById('favorite-filter').value;
    const group = document.getElementById('group-filter').value;
    const dateFrom = document.getElementById('date-from-filter').value;
    const dateTo = document.getElementById('date-to-filter').value;
    const sortBy = document.getElementById('sort-filter').value;
    
    const params = new URLSearchParams({
        skip: currentPage * pageSize,
        limit: pageSize
    });
    
    if (search) params.append('search', search);
    if (format) params.append('format', format);
    if (favoriteFilter === 'true') params.append('favorite_only', 'true');
    if (favoriteFilter === 'false') params.append('favorite_only', 'false');
    if (group) params.append('group', group);
    if (dateFrom) params.append('date_from', dateFrom);
    if (dateTo) params.append('date_to', dateTo);
    if (sortBy) params.append('sort_by', sortBy);
    
    try {
        document.getElementById('recordings-content').innerHTML = 
            '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading recordings...</div>';
        
        const response = await fetch(`/api/v1/recordings?${params}`);
        if (!response.ok) throw new Error('Failed to load recordings');
        
        let recordings = await response.json();
        
        // Apply client-side sorting if not done server-side
        recordings = sortRecordings(recordings, sortBy);
        
        currentRecordings = recordings;
        displayRecordings(recordings);
        updatePagination();
        updateBulkActions();
    } catch (error) {
        console.error('Error loading recordings:', error);
        document.getElementById('recordings-content').innerHTML = 
            `<div class="no-recordings">Error loading recordings: ${error.message}</div>`;
    }
}

function displayRecordings(recordings) {
    if (recordings.length === 0) {
        document.getElementById('recordings-content').innerHTML = 
            '<div class="no-recordings"><i class="fas fa-inbox"></i><br>No recordings found</div>';
        return;
    }
    
    const table = `
        <table class="recordings-table">
            <thead>
                <tr>
                    <th>
                        <input type="checkbox" id="select-all-checkbox" onchange="toggleSelectAll()">
                    </th>
                    <th>Date/Time</th>
                    <th>Frequency</th>
                    <th>Description</th>
                    <th>Group</th>
                    <th>Duration</th>
                    <th>Signal</th>
                    <th>Format</th>
                    <th>Size</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                ${recordings.map(rec => {
                    const freqDisplay = rec.friendly_name ? 
                        `${escapeHtml(rec.friendly_name)} (${formatFrequency(rec.frequency_mhz)})` :
                        formatFrequency(rec.frequency_mhz);
                    const isSelected = selectedRecordings.has(rec.id);
                    return `
                    <tr class="${isSelected ? 'selected' : ''}">
                        <td>
                            <input type="checkbox" class="recording-checkbox" 
                                   value="${rec.id}" 
                                   onchange="toggleRecordingSelection(${rec.id}, this.checked)"
                                   ${isSelected ? 'checked' : ''}>
                        </td>
                        <td>${formatDateTime(rec.timestamp)}</td>
                        <td>${freqDisplay}</td>
                        <td>${escapeHtml(rec.description || '-')}</td>
                        <td>${escapeHtml(rec.group || '-')}</td>
                        <td>${formatDuration(rec.duration_seconds)}</td>
                        <td>${formatSignal(rec.signal_strength_dbm)}</td>
                        <td><span class="badge">${rec.format}</span></td>
                        <td>${formatFileSize(rec.file_size_bytes)}</td>
                        <td>
                            <div class="recording-actions">
                                <button class="btn-icon btn-play" onclick="playRecording(${rec.id}, '${escapeHtml(rec.filename)}', ${rec.duration_seconds})" title="Play">
                                    <i class="fas fa-play"></i>
                                </button>
                                <button class="btn-icon btn-download" onclick="downloadRecording(${rec.id}, '${escapeHtml(rec.filename)}')" title="Download">
                                    <i class="fas fa-download"></i>
                                </button>
                                <button class="btn-icon btn-favorite ${rec.is_favorite ? 'active' : ''}" 
                                        onclick="toggleFavorite(${rec.id}, ${!rec.is_favorite})" title="Favorite">
                                    <i class="fas fa-star"></i>
                                </button>
                                <button class="btn-icon btn-delete" onclick="deleteRecording(${rec.id}, '${escapeHtml(rec.filename)}')" title="Delete">
                                    <i class="fas fa-trash"></i>
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
                }).join('')}
            </tbody>
        </table>
    `;
    
    document.getElementById('recordings-content').innerHTML = table;
}

async function loadStats() {
    try {
        const response = await fetch('/api/v1/recordings/stats/summary');
        if (!response.ok) throw new Error('Failed to load stats');
        
        const stats = await response.json();
        document.getElementById('stat-total').textContent = stats.total_recordings || 0;
        document.getElementById('stat-duration').textContent = stats.total_duration_hours || '0.00';
        document.getElementById('stat-size').textContent = stats.total_size_gb || '0.00';
        document.getElementById('stat-favorites').textContent = stats.favorite_count || 0;
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

async function loadGroups() {
    try {
        const response = await fetch('/api/v1/recordings?limit=1000');
        if (!response.ok) throw new Error('Failed to load groups');
        
        const recordings = await response.json();
        const groups = [...new Set(recordings.map(r => r.group).filter(g => g))].sort();
        allGroups = groups;
        
        const groupSelect = document.getElementById('group-filter');
        groups.forEach(group => {
            const option = document.createElement('option');
            option.value = group;
            option.textContent = group;
            groupSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading groups:', error);
    }
}

function playRecording(id, filename, duration) {
    const player = document.getElementById('audio-player');
    const container = document.getElementById('audio-player-container');
    const filenameEl = document.getElementById('player-filename');
    const detailsEl = document.getElementById('player-details');
    
    player.src = `/api/v1/recordings/${id}/stream`;
    filenameEl.textContent = filename;
    detailsEl.textContent = `Duration: ${formatDuration(duration)}`;
    container.classList.add('active');
    player.play();
}

function closePlayer() {
    const player = document.getElementById('audio-player');
    const container = document.getElementById('audio-player-container');
    player.pause();
    player.src = '';
    container.classList.remove('active');
}

function downloadRecording(id, filename) {
    window.location.href = `/api/v1/recordings/${id}/download`;
}

async function toggleFavorite(id, isFavorite) {
    try {
        const response = await fetch(`/api/v1/recordings/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_favorite: isFavorite })
        });
        
        if (!response.ok) throw new Error('Failed to update favorite');
        
        // Reload recordings to update UI
        loadRecordings();
        loadStats();
    } catch (error) {
        console.error('Error toggling favorite:', error);
        alert('Failed to update favorite: ' + error.message);
    }
}

async function deleteRecording(id, filename) {
    if (!confirm(`Are you sure you want to delete "${filename}"?\n\nThis will permanently delete the recording file and cannot be undone.`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/v1/recordings/${id}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Failed to delete recording');
        
        // Reload recordings
        loadRecordings();
        loadStats();
    } catch (error) {
        console.error('Error deleting recording:', error);
        alert('Failed to delete recording: ' + error.message);
    }
}

function updatePagination() {
    const pagination = document.getElementById('pagination');
    const hasMore = currentRecordings.length === pageSize;
    
    pagination.innerHTML = `
        <button onclick="previousPage()" ${currentPage === 0 ? 'disabled' : ''}>
            <i class="fas fa-chevron-left"></i> Previous
        </button>
        <span>Page ${currentPage + 1}</span>
        <button onclick="nextPage()" ${!hasMore ? 'disabled' : ''}>
            Next <i class="fas fa-chevron-right"></i>
        </button>
    `;
}

function nextPage() {
    currentPage++;
    loadRecordings();
}

function previousPage() {
    if (currentPage > 0) {
        currentPage--;
        loadRecordings();
    }
}

// Utility functions
function formatDateTime(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString();
}

function formatFrequency(mhz) {
    return `${mhz.toFixed(3)} MHz`;
}

function formatDuration(seconds) {
    if (seconds < 60) {
        return `${seconds.toFixed(1)}s`;
    } else if (seconds < 3600) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}m ${secs}s`;
    } else {
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        return `${hours}h ${mins}m`;
    }
}

function formatSignal(dbm) {
    return `${dbm.toFixed(1)} dBm`;
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function sortRecordings(recordings, sortBy) {
    const sorted = [...recordings];
    
    switch (sortBy) {
        case 'newest':
            return sorted.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        case 'oldest':
            return sorted.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
        case 'duration-long':
            return sorted.sort((a, b) => (b.duration_seconds || 0) - (a.duration_seconds || 0));
        case 'duration-short':
            return sorted.sort((a, b) => (a.duration_seconds || 0) - (b.duration_seconds || 0));
        case 'size-large':
            return sorted.sort((a, b) => (b.file_size_bytes || 0) - (a.file_size_bytes || 0));
        case 'size-small':
            return sorted.sort((a, b) => (a.file_size_bytes || 0) - (b.file_size_bytes || 0));
        case 'signal-strong':
            return sorted.sort((a, b) => (b.signal_strength_dbm || 0) - (a.signal_strength_dbm || 0));
        case 'signal-weak':
            return sorted.sort((a, b) => (a.signal_strength_dbm || 0) - (b.signal_strength_dbm || 0));
        default:
            return sorted;
    }
}

function toggleRecordingSelection(id, checked) {
    if (checked) {
        selectedRecordings.add(id);
    } else {
        selectedRecordings.delete(id);
    }
    updateBulkActions();
    updateSelectAllCheckbox();
}

function toggleSelectAll() {
    const checkbox = document.getElementById('select-all-checkbox');
    const allChecked = checkbox.checked;
    
    currentRecordings.forEach(rec => {
        if (allChecked) {
            selectedRecordings.add(rec.id);
        } else {
            selectedRecordings.delete(rec.id);
        }
    });
    
    // Update all checkboxes
    document.querySelectorAll('.recording-checkbox').forEach(cb => {
        cb.checked = allChecked;
    });
    
    // Update row styles
    document.querySelectorAll('.recordings-table tbody tr').forEach(row => {
        if (allChecked) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    });
    
    updateBulkActions();
}

function updateSelectAllCheckbox() {
    const checkbox = document.getElementById('select-all-checkbox');
    if (!checkbox) return;
    
    const allSelected = currentRecordings.length > 0 && 
        currentRecordings.every(rec => selectedRecordings.has(rec.id));
    checkbox.checked = allSelected;
}

function updateBulkActions() {
    const count = selectedRecordings.size;
    const favoriteBtn = document.getElementById('bulk-favorite');
    const deleteBtn = document.getElementById('bulk-delete');
    
    if (favoriteBtn) {
        favoriteBtn.disabled = count === 0;
        if (count > 0) {
            favoriteBtn.innerHTML = `<i class="fas fa-star"></i> <span class="btn-text">Favorite (${count})</span>`;
        } else {
            favoriteBtn.innerHTML = `<i class="fas fa-star"></i> <span class="btn-text">Favorite</span>`;
        }
    }
    
    if (deleteBtn) {
        deleteBtn.disabled = count === 0;
        if (count > 0) {
            deleteBtn.innerHTML = `<i class="fas fa-trash"></i> <span class="btn-text">Delete (${count})</span>`;
        } else {
            deleteBtn.innerHTML = `<i class="fas fa-trash"></i> <span class="btn-text">Delete</span>`;
        }
    }
}

async function bulkFavorite() {
    const ids = Array.from(selectedRecordings);
    if (ids.length === 0) return;
    
    if (!confirm(`Mark ${ids.length} recording(s) as favorite?`)) return;
    
    try {
        const promises = ids.map(id => 
            fetch(`/api/v1/recordings/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_favorite: true })
            })
        );
        
        await Promise.all(promises);
        selectedRecordings.clear();
        loadRecordings();
        loadStats();
    } catch (error) {
        console.error('Error favoriting recordings:', error);
        alert('Failed to favorite recordings: ' + error.message);
    }
}

async function bulkDelete() {
    const ids = Array.from(selectedRecordings);
    if (ids.length === 0) return;
    
    if (!confirm(`Are you sure you want to delete ${ids.length} recording(s)?\n\nThis will permanently delete the recording files and cannot be undone.`)) {
        return;
    }
    
    try {
        const promises = ids.map(id => 
            fetch(`/api/v1/recordings/${id}`, {
                method: 'DELETE'
            })
        );
        
        await Promise.all(promises);
        selectedRecordings.clear();
        loadRecordings();
        loadStats();
    } catch (error) {
        console.error('Error deleting recordings:', error);
        alert('Failed to delete recordings: ' + error.message);
    }
}

async function exportRecordings() {
    try {
        // Get all recordings with current filters
        const search = document.getElementById('search-input').value.trim();
        const format = document.getElementById('format-filter').value;
        const favoriteFilter = document.getElementById('favorite-filter').value;
        const group = document.getElementById('group-filter').value;
        const dateFrom = document.getElementById('date-from-filter').value;
        const dateTo = document.getElementById('date-to-filter').value;
        
        const params = new URLSearchParams({ limit: 10000 });
        if (search) params.append('search', search);
        if (format) params.append('format', format);
        if (favoriteFilter === 'true') params.append('favorite_only', 'true');
        if (favoriteFilter === 'false') params.append('favorite_only', 'false');
        if (group) params.append('group', group);
        if (dateFrom) params.append('date_from', dateFrom);
        if (dateTo) params.append('date_to', dateTo);
        
        const response = await fetch(`/api/v1/recordings?${params}`);
        if (!response.ok) throw new Error('Failed to load recordings');
        
        const recordings = await response.json();
        const dataStr = JSON.stringify(recordings, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        
        const link = document.createElement('a');
        link.href = URL.createObjectURL(dataBlob);
        link.download = `sdr2zello_recordings_${new Date().toISOString().split('T')[0]}.json`;
        link.click();
    } catch (error) {
        console.error('Error exporting recordings:', error);
        alert('Failed to export recordings: ' + error.message);
    }
}

function setPlaybackSpeed(speed) {
    const player = document.getElementById('audio-player');
    if (player) {
        player.playbackRate = parseFloat(speed);
    }
}

