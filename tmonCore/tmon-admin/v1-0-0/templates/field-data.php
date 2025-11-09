<?php
// TMON Field Data Log Viewer (Admin)
?>
<div class="wrap">
    <h1>Field Data Log</h1>
    <div id="tmon-field-data-log">
        <div id="tmon-sync-hint" class="notice notice-info" style="display:none; margin:10px 0;">
            <p>
                <strong>LoRa schedule:</strong> Latest REMOTE_SYNC_SCHEDULE from base ACKs.
                <span id="tmon-sync-meta" style="margin-left:8px;"></span>
            </p>
            <table class="widefat" style="margin-top:6px; max-width:780px">
                <thead><tr><th>Remote Unit</th><th>Next Sync (local)</th><th>In</th></tr></thead>
                <tbody id="tmon-sync-body"><tr><td colspan="3"><em>Loading…</em></td></tr></tbody>
            </table>
            <div style="max-width:780px; margin-top:10px">
                <canvas id="tmon-sync-chart" height="100"></canvas>
            </div>
        </div>
        <div id="tmon-remote-hint" class="notice notice-info" style="display:none; margin:10px 0;">
            <p>
                <strong>Heads up:</strong> Recent base-station entries include REMOTE_NODE_INFO.
                Remote node readings are being ingested alongside the base record.
                <span id="tmon-remote-count" style="margin-left:8px;"></span>
            </p>
            <p style="margin:6px 0 0 0;">
                Window (hours): <input type="number" id="tmon-remote-hours" value="24" min="1" max="168" style="width:70px;" />
                <label style="margin-left:12px"><input type="checkbox" id="tmon-filter-window" checked> Filter table to this window</label>
            </p>
        </div>
        <button id="refresh-field-data">Refresh</button>
        <table class="widefat">
            <thead>
                <tr>
                    <th>Unit ID</th>
                    <th>Timestamp</th>
                    <th>Data</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody id="field-data-body">
                <tr><td colspan="4">Loading...</td></tr>
            </tbody>
        </table>
    </div>
</div>
<script>
let __tmon_latest_rows = [];
let __tmon_sync_chart = null;
function humanizeDelta(sec){
    try{
        sec = Math.max(0, Math.floor(Number(sec)||0));
        const h = Math.floor(sec/3600); const m = Math.floor((sec%3600)/60); const s = sec%60;
        const parts = [];
        if (h) parts.push(h+"h"); if (m) parts.push(m+"m"); if (s || !parts.length) parts.push(s+"s");
        return parts.join(' ');
    }catch(e){ return sec+"s"; }
}
function parseRowTimestamp(row) {
    // Try ts_iso first
    if (row && row.ts_iso) {
        const d = new Date(row.ts_iso.replace(' ', 'T'));
        if (!isNaN(d.getTime())) return d.getTime();
    }
    // Fallback to numeric timestamp (assume seconds since epoch if plausible)
    const t = row && (row.timestamp || row.time);
    if (t) {
        const num = Number(t);
        if (!isNaN(num) && num > 0) {
            // Heuristic: treat as seconds if value is within reasonable range
            if (num < 10_000_000_000) return num * 1000;
            return num; // already ms
        }
    }
    return 0;
}
function extractLatestSyncSchedule(rows){
    // Find the most recent row that contains a REMOTE_SYNC_SCHEDULE object
    try{
        for (let i = rows.length - 1; i >= 0; i--) {
            const row = rows[i];
            if (!row || typeof row !== 'object') continue;
            const sched = row.REMOTE_SYNC_SCHEDULE;
            if (sched && typeof sched === 'object') {
                const ts = parseRowTimestamp(row);
                const baseInterval = Number(row.nextLoraSync || 0);
                const minGap = Number(row.LORA_SYNC_WINDOW || 0);
                return { sched, ts, baseInterval, minGap };
            }
        }
    } catch(e){}
    return null;
}
function computeDistinctRemoteCount(rows, hours) {
    try {
        const cutoff = Date.now() - (Number(hours) * 3600 * 1000);
        const ids = new Set();
        for (const row of rows) {
            if (!row || typeof row !== 'object') continue;
            const ts = parseRowTimestamp(row);
            if (ts && ts < cutoff) continue;
            const rni = row.REMOTE_NODE_INFO;
            if (rni && typeof rni === 'object') {
                for (const key of Object.keys(rni)) {
                    ids.add(String(key));
                }
            }
        }
        return ids.size;
    } catch(e) { return 0; }
}
function renderFieldData(rows) {
    __tmon_latest_rows = Array.isArray(rows) ? rows : [];
    const tbody = document.getElementById('field-data-body');
    tbody.innerHTML = '';
    let showHint = false;
    let showSync = false;
    const hours = Number(document.getElementById('tmon-remote-hours')?.value || 24);
    const filterOn = !!document.getElementById('tmon-filter-window')?.checked;
    const cutoff = Date.now() - (hours * 3600 * 1000);
    const sourceRows = __tmon_latest_rows;
    const tableRows = filterOn ? sourceRows.filter(r => (parseRowTimestamp(r) || 0) >= cutoff) : sourceRows;
    if (!sourceRows.length) {
        tbody.innerHTML = '<tr><td colspan="4">No data found.</td></tr>';
        document.getElementById('tmon-remote-hint').style.display = 'none';
        document.getElementById('tmon-sync-hint').style.display = 'none';
        return;
    }
    // Update sync schedule banner if available (use all rows, not filtered)
    const latest = extractLatestSyncSchedule(sourceRows);
    const syncDiv = document.getElementById('tmon-sync-hint');
    if (latest && latest.sched) {
        try{
            const entries = Object.keys(latest.sched).map(uid => ({ uid, next: Number(latest.sched[uid])||0 }));
            entries.sort((a,b)=>a.next-b.next);
            const nowSec = Math.floor(Date.now()/1000);
            const rowsHtml = entries.map(e=>{
                const nextMs = (e.next<10_000_000_000? e.next*1000 : e.next);
                const delta = Math.max(0, Math.floor(((nextMs/1000) - nowSec)));
                return `<tr><td>${e.uid}</td><td>${new Date(nextMs).toLocaleString()}</td><td>${humanizeDelta(delta)}</td></tr>`;
            });
            document.getElementById('tmon-sync-body').innerHTML = rowsHtml.length? rowsHtml.join('') : '<tr><td colspan="3"><em>No scheduled remotes.</em></td></tr>';
            const meta = [];
            if (latest.ts) meta.push('as of '+new Date(latest.ts).toLocaleString());
            if (latest.baseInterval) meta.push('base interval '+latest.baseInterval+'s');
            if (latest.minGap) meta.push('min spacing '+latest.minGap+'s');
            document.getElementById('tmon-sync-meta').textContent = meta.length? '('+meta.join(' · ')+')' : '';
            syncDiv.style.display = 'block';
            // Mini chart: seconds to next sync per remote
            try {
                if (typeof Chart === 'undefined') {
                    var s = document.createElement('script');
                    s.src = 'https://cdn.jsdelivr.net/npm/chart.js';
                    s.onload = function(){ renderFieldData(__tmon_latest_rows); };
                    document.head.appendChild(s);
                } else {
                    const labels = entries.map(e=>e.uid);
                    const nowS = Math.floor(Date.now()/1000);
                    const data = entries.map(e=>Math.max(0, ( (e.next<10_000_000_000? e.next : Math.floor(e.next/1000)) - nowS )));
                    const ctx = document.getElementById('tmon-sync-chart').getContext('2d');
                    if (__tmon_sync_chart) { try { __tmon_sync_chart.destroy(); } catch(e){} }
                    __tmon_sync_chart = new Chart(ctx, {
                        type: 'bar',
                        data: { labels, datasets: [{ label: 'Next sync (s)', data, backgroundColor: '#3498db' }] },
                        options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
                    });
                }
            } catch(e){}
            showSync = true;
        }catch(e){ syncDiv.style.display = 'none'; }
    } else {
        syncDiv.style.display = 'none';
    }
    // Determine if any rows contain REMOTE_NODE_INFO (use all rows)
    for (const row of sourceRows) {
        try {
            if (row && row.REMOTE_NODE_INFO && typeof row.REMOTE_NODE_INFO === 'object') { showHint = true; break; }
        } catch(e) {}
    }
    // Render table rows (filtered if checkbox is on)
    const rowsForTable = tableRows.length ? tableRows : [];
    for (const row of rowsForTable) {
        const tr = document.createElement('tr');
        const file = row.unit_id ? `field_data_${row.unit_id}.log` : '';
        // Detect REMOTE_NODE_INFO presence to hint in UI
        try {
            const obj = typeof row === 'object' ? row : {};
            if (obj && obj.REMOTE_NODE_INFO && typeof obj.REMOTE_NODE_INFO === 'object') {
                showHint = true;
            }
        } catch(e) {}
        const tdUnit = document.createElement('td');
        tdUnit.textContent = row.unit_id || '';
        const tdTimestamp = document.createElement('td');
        tdTimestamp.textContent = row.timestamp || '';
        const tdData = document.createElement('td');
        const pre = document.createElement('pre');
        pre.textContent = JSON.stringify(row, null, 2);
        tdData.appendChild(pre);
        const tdActions = document.createElement('td');
        const btn = document.createElement('button');
        btn.textContent = 'Delete';
        btn.onclick = function() { deleteFieldData(file); };
        tdActions.appendChild(btn);
        tr.appendChild(tdUnit);
        tr.appendChild(tdTimestamp);
        tr.appendChild(tdData);
        tr.appendChild(tdActions);
        tbody.appendChild(tr);
    }
    // If filtering produced zero rows, show a single empty-state row but keep hints visible
    if (!rowsForTable.length && sourceRows.length) {
        tbody.innerHTML = '<tr><td colspan="4">No rows in this window.</td></tr>';
    }
    const hint = document.getElementById('tmon-remote-hint');
    hint.style.display = showHint ? 'block' : 'none';
    if (showHint) {
        const count = computeDistinctRemoteCount(sourceRows, hours);
        const span = document.getElementById('tmon-remote-count');
        span.textContent = `(last ${hours}h: ${count} distinct remote unit_id${count===1?'':'s'})`;
    }
}
function fetchFieldData() {
    fetch('/wp-json/tmon-admin/v1/field-data')
        .then(r => r.json())
        .then(renderFieldData);
}
function deleteFieldData(file) {
    if (!confirm('Delete this field data log?')) return;
    fetch('/wp-admin/admin-ajax.php?action=tmon_admin_delete_field_data&file=' + encodeURIComponent(file))
        .then(() => fetchFieldData());
}
document.getElementById('refresh-field-data').onclick = fetchFieldData;
window.addEventListener('DOMContentLoaded', fetchFieldData);
document.addEventListener('DOMContentLoaded', function(){
    const input = document.getElementById('tmon-remote-hours');
    if (input) {
        input.addEventListener('change', function(){
            if (__tmon_latest_rows && __tmon_latest_rows.length) {
                const hours = Number(input.value || 24);
                const count = computeDistinctRemoteCount(__tmon_latest_rows, hours);
                const span = document.getElementById('tmon-remote-count');
                if (span) span.textContent = `(last ${hours}h: ${count} distinct remote unit_id${count===1?'':'s'})`;
                renderFieldData(__tmon_latest_rows);
            }
        });
    }
    const chk = document.getElementById('tmon-filter-window');
    if (chk) {
        chk.addEventListener('change', function(){
            if (__tmon_latest_rows && __tmon_latest_rows.length) {
                renderFieldData(__tmon_latest_rows);
            }
        });
    }
});
</script>
