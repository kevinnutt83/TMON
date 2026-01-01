<?php
// LoRa Map admin page — reads options 'tmon_uc_lora_status' and 'tmon_uc_chunk_store'
if (!current_user_can('manage_options')) wp_die('Forbidden');

$lora = get_option('tmon_uc_lora_status', []);
$chunks = get_option('tmon_uc_chunk_store', []);
?>
<div class="wrap">
  <h1>LoRa Map & Diagnostics</h1>
  <p class="description">Latest per-unit LoRa status (posted from devices or base stations).</p>
  <p><button id="tmon-lora-refresh" class="button">Refresh Now</button></p>
  <table class="widefat striped"><thead><tr><th>Unit</th><th>Last Seen</th><th>Chunk missing count</th><th>Present</th><th>Bytes</th><th>Details</th><th>Trend</th><th>Sparkline</th></tr></thead><tbody id="tmon-lora-body">
  <?php
  if (is_array($lora) && $lora) {
    foreach ($lora as $unit => $rec) {
      $snap = is_array($rec['status']) ? $rec['status'] : [];
      $meta = isset($chunks[$unit]) ? $chunks[$unit] : null;
      $missing = $meta ? count($meta['missing']) : '-';
      $present = $meta ? intval($meta['present_count']) : '-';
      $bytes = $meta ? intval($meta['bytes']) : '-';
      echo '<tr>';
      echo '<td>'.esc_html($unit).'</td>';
      echo '<td>'.esc_html($rec['ts']).'</td>';
      echo '<td>'.esc_html($missing).'</td>';
      echo '<td>'.esc_html($present).'</td>';
      echo '<td>'.esc_html($bytes).'</td>';
      echo '<td><pre style="max-height:160px;overflow:auto">'.esc_html(substr(json_encode($snap, JSON_PRETTY_PRINT),0,400)).'</pre></td>';
      echo '<td><button class="button tmon-view-trend" data-unit="'.esc_attr($unit).'">View Trend</button></td>';
      echo '<td><canvas class="tmon-sparkline" data-unit="'.esc_attr($unit).'" width="120" height="30"></canvas></td>';
      echo '</tr>';
    }
  } else {
    echo '<tr><td colspan="8"><em>No LoRa status snapshots received yet.</em></td></tr>';
  }
  ?>
  </tbody></table>

  <!-- Add map container -->
  <div style="margin:12px 0;">
    <div id="tmon-lora-map" style="height:400px;border:1px solid #ccc"></div>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.3/dist/leaflet.js"></script>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.3/dist/leaflet.css"/>

  <script>
  (function(){
    const mapDiv = document.getElementById('tmon-lora-map');
    if (!mapDiv) return;
    const map = L.map('tmon-lora-map').setView([0,0], 2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:18, attribution:''}).addTo(map);

    const rows = <?php echo json_encode((is_array($lora)?$lora:[])); ?>;
    let count=0;
    for (let unit in rows) {
      try {
        const rec = rows[unit];
        const snap = rec.status || {};
        // extract coords if present in chunk/store snapshot as {lat,lng} keys
        const lat = snap.gps_lat || snap.gpsLat || (snap.payload && snap.payload.gps_lat);
        const lng = snap.gps_lng || snap.gpsLng || (snap.payload && snap.payload.gps_lng);
        if (lat && lng && !isNaN(lat) && !isNaN(lng)) {
          const m = L.marker([parseFloat(lat), parseFloat(lng)]).addTo(map);
          m.bindPopup(`<strong>${unit}</strong><br/>last: ${rec.ts}<br/>missing: ${snap.missing ? snap.missing.length : '-'}`);
          count++;
        }
      } catch(e){ continue; }
    }
    if (count > 0) map.fitBounds( map.getBounds().pad(0.5) );
  })();
  </script>
</div>
<script>
document.getElementById('tmon-lora-refresh').addEventListener('click', function(){
  location.reload();
});
</script>

<!-- Trend Modal -->
<div id="tmon-trend-modal" style="display:none; position:fixed; left:50%; top:10%; transform:translateX(-50%); width:80%; max-width:900px; z-index:9999; background:#fff; box-shadow:0 4px 12px rgba(0,0,0,.25); padding:12px;">
  <h2 id="tmon-trend-title">LoRa Missing Chunk Trend</h2>
  <canvas id="tmon-trend-chart" width="800" height="300"></canvas>
  <p style="text-align:right;"><button id="tmon-trend-close" class="button">Close</button></p>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
(function(){
  const modal = document.getElementById('tmon-trend-modal');
  const closeBtn = document.getElementById('tmon-trend-close');
  const titleEl = document.getElementById('tmon-trend-title');
  const canvas = document.getElementById('tmon-trend-chart');
  let chart = null;

  function showModal() { modal.style.display = 'block'; }
  function hideModal() { modal.style.display = 'none'; }

  closeBtn.addEventListener('click', hideModal);

  function renderChart(labels, data) {
    if (chart) chart.destroy();
    chart = new Chart(canvas.getContext('2d'), {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'Missing Chunks',
          data: data,
          borderColor: 'rgba(255,99,132,1)',
          backgroundColor: 'rgba(255,99,132,0.15)',
          tension: 0.25,
        }]
      },
      options: {
        scales: {
          x: { display: true },
          y: { beginAtZero: true }
        }
      }
    });
  }

  function fetchAndShow(unit) {
    titleEl.textContent = 'Trend for ' + unit;
    showModal();
    fetch('<?php echo esc_url_raw(rest_url('tmon/v1/admin/chunk-history')); ?>?unit_id=' + encodeURIComponent(unit) + '&limit=48')
      .then(r => r.json())
      .then(j => {
        if (!j || !j.series) {
          renderChart([], []);
          return;
        }
        const series = j.series;
        const labels = series.map(s => new Date(s.ts).toLocaleString());
        const data = series.map(s => s.missing);
        renderChart(labels, data);
      }).catch(e => {
        renderChart([], []);
      });
  }

  document.querySelectorAll('.tmon-view-trend').forEach(btn=>{
    btn.addEventListener('click', function(){
      const unit = this.dataset.unit;
      fetchAndShow(unit);
    });
  });
})();
</script>

<!-- Ensure Chart.js already included above; initialize sparklines -->
<script>
(function(){
  // render small sparklines for each canvas by fetching last 12 points
  document.querySelectorAll('canvas.tmon-sparkline').forEach(function(c){
    const unit = c.dataset.unit;
    fetch('<?php echo esc_url_raw(rest_url('tmon/v1/admin/chunk-history')); ?>?unit_id=' + encodeURIComponent(unit) + '&limit=12')
      .then(r=>r.json()).then(j=>{
        if (!j || !j.series) return;
        const series = j.series;
        const labels = series.map(s=> new Date(s.ts).toLocaleTimeString());
        const data = series.map(s=> s.missing);
        new Chart(c.getContext('2d'), {
          type: 'line',
          data: { labels: labels, datasets: [{ data: data, borderColor: 'rgba(0,120,200,1)', backgroundColor: 'rgba(0,120,200,0.15)', fill: true, pointRadius:0, borderWidth:1 }]},
          options: { responsive:false, maintainAspectRatio:false, animation:false, plugins:{legend:{display:false}}, scales:{x:{display:false}, y:{display:false}}}
        });
      }).catch(e=>{ /* ignore */ });
  });
})();
</script>
