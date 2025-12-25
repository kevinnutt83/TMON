<?php
// TMON Data History Log Viewer (Admin)
?>
<div class="wrap">
    <h1>Data History Log</h1>
    <div id="tmon-data-history-log">
        <button id="refresh-data-history">Refresh</button>
        <table class="widefat">
            <thead>
                <tr>
                    <th>File</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="data-history-body">
                <tr><td colspan="2">Loading...</td></tr>
            </tbody>
        </table>
    </div>
</div>
<script>
function renderDataHistory(files) {
    const tbody = document.getElementById('data-history-body');
    tbody.innerHTML = '';
    if (!files.length) {
        tbody.innerHTML = '<tr><td colspan="2">No data found.</td></tr>';
        return;
    }
    for (const file of files) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${file.file}</td><td><button onclick=\"downloadDataHistory('${file.file}')\">Download</button> <button onclick=\"deleteDataHistory('${file.file}')\">Delete</button></td>`;
        tbody.appendChild(tr);
    }
}
function fetchDataHistory() {
    fetch('/wp-json/tmon-admin/v1/data-history')
        .then(r => r.json())
        .then(renderDataHistory);
}
function downloadDataHistory(file) {
    window.location = `/wp-admin/admin-ajax.php?action=tmon_admin_download_data_history&file=${encodeURIComponent(file)}`;
}
function deleteDataHistory(file) {
    if (!confirm('Delete this data history log?')) return;
    fetch('/wp-admin/admin-ajax.php?action=tmon_admin_delete_data_history&file=' + encodeURIComponent(file))
        .then(() => fetchDataHistory());
}
document.getElementById('refresh-data-history').onclick = fetchDataHistory;
window.addEventListener('DOMContentLoaded', fetchDataHistory);
</script>
