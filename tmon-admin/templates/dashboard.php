
<?php
echo '<div class="wrap">';
echo '<h1>TMON Admin Dashboard</h1>';
echo '<p>Welcome to the TMON Admin dashboard. Use the menu to manage TMON devices, view logs, and configure system-wide settings.</p>';

// LoRa rotation/status widget
echo '<hr />';
echo '<h2>LoRa Remote Rotation Status</h2>';
echo '<p>This widget summarizes the last remotes seen from recent field data and estimates next sync windows to visualize rotation.</p>';
echo '<div id="tmon-rotation-controls" style="margin:8px 0;">';
echo '  <label>Hours: <input id="tmon-rot-hours" type="number" min="1" max="72" value="12" style="width:70px" /></label> ';
echo '  <label>Show last N remotes: <input id="tmon-rot-limit" type="number" min="1" max="50" value="10" style="width:70px" /></label> ';
echo '  <button class="button" id="tmon-rot-refresh">Refresh</button>';
echo '</div>';
echo '<table class="widefat fixed striped" style="max-width:980px">';
echo ' <thead><tr><th>Remote Unit</th><th>Last Seen</th><th>Estimated Interval</th><th>Estimated Next</th></tr></thead>';
echo ' <tbody id="tmon-rot-body"><tr><td colspan="4"><em>Loading…</em></td></tr></tbody>';
echo '</table>';

// Inline JS using WP REST URL for admin field data
echo '<script>(function(){
	function restBase(){ try { return (wp && wp.apiSettings && wp.apiSettings.root) ? wp.apiSettings.root.replace(/\/$/, "") : (window.location.origin||"")+"/wp-json"; } catch(e){ return (window.location.origin||"")+"/wp-json"; } }
	async function loadRotation(){
		const hours = parseInt(document.getElementById("tmon-rot-hours").value||"12",10);
		const limit = parseInt(document.getElementById("tmon-rot-limit").value||"10",10);
		const url = restBase()+"/tmon-admin/v1/field-data";
		const res = await fetch(url, { credentials: "same-origin" });
		const rows = await res.json();
		const cutoff = Date.now() - hours*3600*1000;
		// Build series by unit_id for entries within hours window
		const series = new Map();
		for (const r of rows){
			try{
				const uid = r.unit_id || r.machine_id || r.name || "?";
				// prefer created_at, else timestamp/time
				const tsStr = r.created_at || r.timestamp || r.time || null;
				if (!uid || !tsStr) continue;
				const t = new Date(tsStr.toString().replace(' ', 'T')).getTime();
				if (!t || t < cutoff) continue;
				if (!series.has(uid)) series.set(uid, []);
				series.get(uid).push(t);
			}catch(e){/*ignore*/}
		}
		// Compute lastSeen, lastDelta, estimated interval, next
		const items = [];
		for (const [uid, times] of series.entries()){
			times.sort((a,b)=>a-b);
			const last = times[times.length-1];
			let delta = null;
			if (times.length>=2){ delta = Math.max(1, Math.round((times[times.length-1]-times[times.length-2])/1000)); }
			items.push({ uid, last, delta });
		}
		// Global median interval fallback
		const deltas = items.map(i=>i.delta).filter(Boolean).sort((a,b)=>a-b);
		const median = deltas.length ? deltas[Math.floor(deltas.length/2)] : 300;
		// Sort by most recent
		items.sort((a,b)=>b.last-a.last);
		const out = items.slice(0, limit).map(i=>{
			const estInt = i.delta || median;
			const next = i.last + estInt*1000;
			return `<tr><td>${i.uid}</td><td>${new Date(i.last).toLocaleString()}</td><td>${estInt}s</td><td>${new Date(next).toLocaleString()}</td></tr>`;
		});
		document.getElementById("tmon-rot-body").innerHTML = out.length? out.join("") : '<tr><td colspan="4"><em>No recent remotes in the selected window.</em></td></tr>';
	}
	document.getElementById("tmon-rot-refresh").addEventListener("click", loadRotation);
	loadRotation();
})();</script>';

echo '</div>';
?>
