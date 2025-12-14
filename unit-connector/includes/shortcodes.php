<?php
// Shortcode to display pending command count for a unit: [tmon_pending_commands]
add_shortcode('tmon_pending_commands', function($atts){
    $a = shortcode_atts(['unit' => ''], $atts);
    $preselect = sanitize_text_field($a['unit']);
    global $wpdb;
    $rows = $wpdb->get_results("SELECT unit_id, unit_name FROM {$wpdb->prefix}tmon_devices ORDER BY unit_name ASC, unit_id ASC", ARRAY_A);
    if (empty($rows)) return '<em>No devices found.</em>';
    $select_id = 'tmon-pending-select-' . wp_generate_password(6, false, false);
    $count_id = 'tmon-pending-count-' . wp_generate_password(6, false, false);
    $nonce = wp_create_nonce('tmon_pending_cmds');
    ob_start();
    echo '<div class="tmon-pending-widget">';
    echo '<label class="screen-reader-text" for="'.$select_id.'">Device</label>';
    echo '<select id="'.$select_id.'">';
    foreach ($rows as $r) {
        $val = esc_attr($r['unit_id']);
        $label = $r['unit_name'] ? ($r['unit_name'] . ' (' . $r['unit_id'] . ')') : $r['unit_id'];
        $sel = ($preselect && $preselect === $r['unit_id']) ? ' selected' : '';
        echo "<option value=\"{$val}\"{$sel}>".esc_html($label)."</option>";
    }
    echo '</select> ';
    echo '<span id="'.$count_id.'" class="tmon-pending-commands" aria-live="polite">Loading…</span>';
    $ajax_url = esc_js(admin_url('admin-ajax.php'));
    echo '<script>(function(){ const sel=document.getElementById("'.esc_js($select_id).'"); const out=document.getElementById("'.esc_js($count_id).'"); const nonce="'.esc_js($nonce).'"; const url="'.esc_js($ajax_url).'"; function refresh(u){ out.textContent="Loading…"; fetch(url, {method:"POST", body: new URLSearchParams({ action:"tmon_get_pending_count", unit: u, nonce: nonce })}).then(r=>r.json()).then(function(j){ if(j && j.success){ out.textContent = String(j.data.count); } else { out.textContent = "—"; } }).catch(function(){ out.textContent="Error"; }); } sel.addEventListener("change", function(){ refresh(this.value); }); refresh(sel.value); })();</script>';
    echo '</div>';
    return ob_get_clean();
});

// AJAX handler for pending count (supports logged-in & anonymous)
if (!function_exists('tmon_ajax_get_pending_count')) {
function tmon_ajax_get_pending_count() {
    if ( empty( $_REQUEST['nonce'] ) || ! wp_verify_nonce( wp_unslash( $_REQUEST['nonce'] ), 'tmon_pending_cmds' ) ) {
        wp_send_json_error( 'Invalid nonce', 403 );
    }
    $unit = isset($_REQUEST['unit']) ? sanitize_text_field(wp_unslash($_REQUEST['unit'])) : '';
    if (!$unit) wp_send_json_error('Missing unit', 400);
    global $wpdb;
    $cnt = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM {$wpdb->prefix}tmon_device_commands WHERE device_id = %s AND executed_at IS NULL", $unit));
    wp_send_json_success(['count' => intval($cnt)]);
}}
add_action('wp_ajax_tmon_get_pending_count', 'tmon_ajax_get_pending_count');
add_action('wp_ajax_nopriv_tmon_get_pending_count', 'tmon_ajax_get_pending_count');

// Dashboard widget to summarize pending commands
add_action('wp_dashboard_setup', function(){
    wp_add_dashboard_widget('tmon_cmd_summary', 'TMON Command Summary', function(){
        global $wpdb;
        $rows = $wpdb->get_results("SELECT device_id, COUNT(*) as pending FROM {$wpdb->prefix}tmon_device_commands WHERE executed_at IS NULL GROUP BY device_id ORDER BY pending DESC LIMIT 10", ARRAY_A);
        echo '<table class="widefat"><thead><tr><th>Unit</th><th>Pending</th></tr></thead><tbody>';
        foreach ((array) $rows as $r) {
            echo '<tr><td>'.esc_html($r['device_id']).'</td><td>'.intval($r['pending']).'</td></tr>';
        }
        if (empty($rows)) echo '<tr><td colspan="2"><em>No pending commands</em></td></tr>';
        echo '</tbody></table>';
    });
});

// Ensure ABSPATH is defined
defined('ABSPATH') || exit;

// Truthy helper for feature flags
if (!function_exists('tmon_uc_truthy_flag')) {
function tmon_uc_truthy_flag($val) {
    return in_array($val, [true, 1, '1', 'true', 'yes', 'on'], true);
}}

// Determine if a device supports a given feature based on settings and latest telemetry
if (!function_exists('tmon_uc_device_supports_feature')) {
function tmon_uc_device_supports_feature($settings, $latest, $feature) {
    $flags = [];
    if (is_array($settings)) $flags = array_merge($flags, $settings);
    if (is_array($latest)) $flags = array_merge($flags, $latest);
    $has_sample = tmon_uc_truthy_flag($flags['SAMPLE_TEMP'] ?? null)
        || tmon_uc_truthy_flag($flags['SAMPLE_HUMID'] ?? null)
        || tmon_uc_truthy_flag($flags['SAMPLE_BAR'] ?? null)
        || isset($flags['t_f']) || isset($flags['cur_temp_f']);
    $has_engine = tmon_uc_truthy_flag($flags['ENGINE_ENABLED'] ?? null)
        || tmon_uc_truthy_flag($flags['USE_RS485'] ?? null)
        || isset($flags['engine1_speed_rpm']) || isset($flags['engine2_speed_rpm']);
    if (in_array($feature, ['engine', 'eng'], true)) return $has_engine;
    if (in_array($feature, ['sample', 'sampling', 'env', 'environment'], true)) return $has_sample;
    return $has_sample || $has_engine || empty($feature);
}}

// Build a list of provisioned devices filtered by feature support
if (!function_exists('tmon_uc_list_feature_devices')) {
function tmon_uc_list_feature_devices($feature = 'sample') {
    global $wpdb;
    $rows = $wpdb->get_results("SELECT unit_id, unit_name, settings FROM {$wpdb->prefix}tmon_devices ORDER BY unit_name ASC, unit_id ASC", ARRAY_A);
    if (!$rows) return [];
    $out = [];
    foreach ($rows as $r) {
        $settings = json_decode($r['settings'] ?? '', true);
        $latest = [];
        if (!tmon_uc_device_supports_feature($settings, $latest, $feature)) {
            $fd = $wpdb->get_row($wpdb->prepare("SELECT data FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s ORDER BY created_at DESC LIMIT 1", $r['unit_id']), ARRAY_A);
            if ($fd && !empty($fd['data'])) {
                $tmp = json_decode($fd['data'], true);
                if (is_array($tmp)) $latest = $tmp;
            }
        }
        if (!tmon_uc_device_supports_feature($settings, $latest, $feature)) continue;
        $label = $r['unit_name'] ? ($r['unit_name'] . ' (' . $r['unit_id'] . ')') : $r['unit_id'];
        $out[] = ['unit_id' => $r['unit_id'], 'label' => $label];
    }
    return $out;
}}

// [tmon_entity type="company|zone|cluster|device" id="123"]
add_shortcode('tmon_entity', function($atts) {
    global $wpdb;
    $a = shortcode_atts([
        'type' => 'device',
        'id' => '',
    ], $atts);
    $type = $a['type'];
    $id = intval($a['id']);
    $table_map = [
        'company' => $wpdb->prefix.'tmon_company',
        'zone' => $wpdb->prefix.'tmon_zone',
        'cluster' => $wpdb->prefix.'tmon_cluster',
        'device' => $wpdb->prefix.'tmon_devices',
    ];
    if (!isset($table_map[$type]) || !$id) return '<em>Invalid entity type or ID.</em>';
    $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table_map[$type]} WHERE id=%d", $id), ARRAY_A);
    if (!$row) return '<em>Entity not found.</em>';
    $out = '<div class="tmon-entity"><h3>' . esc_html($type) . ' Info</h3><table class="widefat">';
    foreach ($row as $k => $v) $out .= '<tr><th>' . esc_html($k) . '</th><td>' . esc_html($v) . '</td></tr>';
    $out .= '</table>';
    // Health/performance metrics
    if ($type === 'device') {
        $metrics = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$wpdb->prefix}tmon_device_data WHERE device_id=%d ORDER BY created_at DESC LIMIT 1", $row['id']), ARRAY_A);
        if ($metrics) {
            $out .= '<h4>Performance Metrics</h4><table class="widefat">';
            $data = maybe_unserialize($metrics['data']);
            foreach ($data as $k => $v) $out .= '<tr><th>' . esc_html($k) . '</th><td>' . esc_html($v) . '</td></tr>';
            $out .= '</table>';
        }
    }
    $out .= '</div>';
    return $out;
});

add_action('admin_post_tmon_export_devices', function() {
    if ( ! isset( $_GET['_wpnonce'] ) || ! wp_verify_nonce( $_GET['_wpnonce'], 'tmon_export_devices' ) ) {
        wp_die( 'Invalid nonce.' );
    }
    global $wpdb;
    $rows = $wpdb->get_results("SELECT * FROM {$wpdb->prefix}tmon_devices", ARRAY_A);
    header('Content-Type: text/csv');
    header('Content-Disposition: attachment; filename="tmon_devices.csv"');
    $out = fopen('php://output', 'w');
    if (!empty($rows)) {
        fputcsv($out, array_keys($rows[0]));
        foreach ($rows as $row) fputcsv($out, $row);
    }
    fclose($out);
    exit;
});

// [tmon_device_list]
add_shortcode('tmon_device_list', function($atts) {
    ob_start();
    echo '<div id="tmon-device-list"></div>';
    echo '<div id="tmon-device-details"></div>';
    return ob_get_clean();
});

// [tmon_device_status]
add_shortcode('tmon_device_status', function($atts) {
    ob_start();
    global $wpdb;

    // Base registry rows
    $devices = $wpdb->get_results("SELECT unit_id, unit_name, last_seen, suspended, settings FROM {$wpdb->prefix}tmon_devices ORDER BY last_seen DESC", ARRAY_A);
    $index = [];
    foreach ((array) $devices as $r) { $index[$r['unit_id']] = $r; }

    // Also include units that only appear in field data (typically remotes)
    $fd_units = $wpdb->get_col("SELECT DISTINCT unit_id FROM {$wpdb->prefix}tmon_field_data");
    if ($fd_units) {
        foreach ($fd_units as $uid) {
            if (!isset($index[$uid])) {
                $last = $wpdb->get_var($wpdb->prepare("SELECT created_at FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s ORDER BY created_at DESC LIMIT 1", $uid));
                $index[$uid] = ['unit_id'=>$uid,'unit_name'=>$uid,'last_seen'=>$last ?: '','suspended'=>0,'settings'=>''];
            }
        }
    }

    $rows = array_values($index);
    $can_control = current_user_can('manage_options') || current_user_can('edit_tmon_units');

    echo '<style>
        .tmon-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
        .tmon-green{background:#2ecc71}.tmon-yellow{background:#f1c40f}.tmon-red{background:#e74c3c}
        .tmon-relay-ctl{display:flex;flex-wrap:wrap;gap:4px;align-items:center}
        .tmon-relay-ctl input[type=number]{width:72px}
        .tmon-relay-ctl input[type=datetime-local]{width:190px}
        .tmon-relay-row{margin:2px 0}
        .tmon-text-muted{color:#777;font-style:italic}
    </style>';
    echo '<table class="wp-list-table widefat"><thead><tr><th>Status</th><th>Unit ID</th><th>Name</th><th>Last Seen</th><th>Controls</th></tr></thead><tbody>';
    $now = time();
    $nonce = wp_create_nonce('tmon_uc_relay');
    foreach ($rows as $r) {
        // Get the DB timestamp string (prefer field_data.created_at then devices.last_seen)
        $last_str = $wpdb->get_var($wpdb->prepare(
            "SELECT COALESCE((SELECT MAX(created_at) FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s), (SELECT last_seen FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s))",
            $r['unit_id'], $r['unit_id']
        ));
        if (empty($last_str)) {
            $last = 0;
            $age = PHP_INT_MAX;
            $cls = 'tmon-red';
            $title = 'Never seen';
        } else {
            // Parse the DB datetime as UTC to avoid implicit server-local offsets
            try {
                $dt = new DateTimeImmutable($last_str, new DateTimeZone('UTC'));
                $last = $dt->getTimestamp();
            } catch (Exception $e) {
                // fallback to strtotime if parsing fails
                $last = intval(strtotime($last_str));
            }
            $age = max(0, $now - $last);
            if (intval($r['suspended'])) {
                $cls = 'tmon-red';
            } else if ($age <= 15 * 60) {
                $cls = 'tmon-green';
            } else if ($age <= 30 * 60) {
                $cls = 'tmon-yellow';
            } else {
                $cls = 'tmon-red';
            }
            // display time converted from UTC epoch to site timezone
            $title = 'Last seen: ' . date_i18n(get_option('date_format') . ' ' . get_option('time_format'), $last, true) . ' (' . human_time_diff($last, $now) . ' ago)';
        }

        // Enabled relays from device settings, else infer from latest field data payload
        $enabled_relays = [];
        $settings = [];
        if (!empty($r['settings'])) { $tmp = json_decode($r['settings'], true); if (is_array($tmp)) $settings = $tmp; }
        for ($i=1; $i<=8; $i++) {
            $k = 'ENABLE_RELAY'.$i;
            if (isset($settings[$k]) && ($settings[$k] === true || $settings[$k] === 1 || $settings[$k] === '1')) $enabled_relays[] = $i;
        }
        if (empty($enabled_relays)) {
            $fd = $wpdb->get_row($wpdb->prepare("SELECT data FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s ORDER BY created_at DESC LIMIT 1", $r['unit_id']), ARRAY_A);
            if ($fd && !empty($fd['data'])) {
                $d = json_decode($fd['data'], true);
                if (is_array($d)) {
                    for ($i=1; $i<=8; $i++) {
                        $k = 'ENABLE_RELAY'.$i;
                        if (isset($d[$k]) && ($d[$k] === true || $d[$k] === 1 || $d[$k] === '1')) $enabled_relays[] = $i;
                    }
                }
            }
        }

        echo '<tr>';
        echo '<td><span class="tmon-dot '.$cls.'" title="'.esc_attr($title).'" data-last="'.esc_attr($last).'" data-age="'.esc_attr($age).'"></span></td>';
        echo '<td>'.esc_html($r['unit_id']).'</td>';
        echo '<td>'.esc_html($r['unit_name']).'</td>';
        echo '<td>'.esc_html($r['last_seen']).'</td>';
        echo '<td>';
        if ($can_control && !empty($enabled_relays)) {
            echo '<div class="tmon-relay-ctl" data-unit="'.esc_attr($r['unit_id']).'" data-nonce="'.esc_attr($nonce).'">';
            echo '<label class="tmon-text-muted">Run (min)</label><input type="number" min="0" max="1440" step="1" class="tmon-runtime-min" title="Runtime minutes (0 = no auto-off)" value="0">';
            echo '<label class="tmon-text-muted">At</label><input type="datetime-local" class="tmon-schedule-at" title="Optional schedule time">';
            foreach ($enabled_relays as $n) {
                echo '<div class="tmon-relay-row">'
                    .'<span class="tmon-text-muted">R'.$n.'</span> '
                    .'<button type="button" class="button button-small tmon-relay-btn" data-relay="'.$n.'" data-state="on">On</button> '
                    .'<button type="button" class="button button-small tmon-relay-btn" data-relay="'.$n.'" data-state="off">Off</button>'
                    .'</div>';
            }
            echo '</div>';
        } else if (empty($enabled_relays)) {
            echo '<span class="tmon-text-muted">No relays enabled</span>';
        } else {
            echo '<span class="tmon-text-muted">No control permission</span>';
        }
        echo '</td>';
        echo '</tr>';
    }
    echo '</tbody></table>';
    echo '<a class="button" href="' . wp_nonce_url(admin_url('admin-post.php?action=tmon_export_devices'), 'tmon_export_devices') . '">Export CSV</a>';
    // Inline JS to handle relay control clicks
    $ajax_url = admin_url('admin-ajax.php');
    echo '<script>(function(){
        function toTs(dtVal){ if(!dtVal) return 0; var t = Date.parse(dtVal); return isNaN(t)?0:Math.floor(t/1000); }
        function post(url, data){ return fetch(url, {method: "POST", headers: {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}, body: new URLSearchParams(data)}).then(r=>r.json()); }
        document.addEventListener("click", function(ev){
            var btn = ev.target.closest(".tmon-relay-btn");
            if(!btn) return;
            var wrap = btn.closest(".tmon-relay-ctl");
            if(!wrap) return;
            var unit = wrap.getAttribute("data-unit");
            var nonce = wrap.getAttribute("data-nonce");
            var relay = btn.getAttribute("data-relay");
            var state = btn.getAttribute("data-state");
            var rtMinEl = wrap.querySelector(".tmon-runtime-min");
            var schEl = wrap.querySelector(".tmon-schedule-at");
            var runtime_min = rtMinEl && rtMinEl.value ? parseInt(rtMinEl.value,10) : 0;
            if(isNaN(runtime_min) || runtime_min<0) runtime_min = 0;
            var schedule_at = schEl ? schEl.value : "";
            var payload = { action: "tmon_uc_relay_command", nonce: nonce, unit_id: unit, relay_num: relay, state: state, runtime_min: String(runtime_min), schedule_at: schedule_at };
            btn.disabled = true; var old = btn.textContent; btn.textContent = state+"...";
            post("'.esc_js($ajax_url).'", payload).then(function(res){
                btn.textContent = old; btn.disabled = false;
                if(!res || !res.success){ alert((res && res.data) ? (res.data.message||res.data) : "Command failed"); return; }
                var d = res.data || {}; var msg = d.scheduled ? "Scheduled" : "Queued"; alert(msg+" relay "+relay+" "+state+ (runtime_min? (" for "+runtime_min+" min"): "") );
            }).catch(function(){ btn.textContent = old; btn.disabled=false; alert("Network error"); });
        });
    })();</script>';
    return ob_get_clean();
});

// [tmon_device_history hours="24" refresh_s="60"]
// Unit ID is sourced from a page-level dropdown with id "tmon-unit-picker" when present; otherwise a local dropdown is shown.
add_shortcode('tmon_device_history', function($atts) {
    $a = shortcode_atts([
        'hours' => '24',
        'refresh_s' => '60',
    ], $atts);
    $hours = max(1, intval($a['hours']));
    $refresh = max(0, intval($a['refresh_s']));
    $feature = 'sample';
    $devices = tmon_uc_list_feature_devices($feature);
    if (empty($devices)) {
        return '<em>No provisioned devices found for this feature.</em>';
    }

    $default_unit = $devices[0]['unit_id'];

    $select_id = 'tmon-history-select-' . wp_generate_password(6, false, false);
    $canvas_id = 'tmon-history-chart-' . wp_generate_password(8, false, false);
    $ajax_root = esc_js(rest_url());
    $voltage_min = get_option('tmon_uc_history_voltage_min', '');
    $voltage_max = get_option('tmon_uc_history_voltage_max', '');
    $y4min = ($voltage_min !== '') ? floatval($voltage_min) : 'null';
    $y4max = ($voltage_max !== '') ? floatval($voltage_max) : 'null';
    ob_start();
    echo '<div class="tmon-history-widget">';
    echo '<label class="screen-reader-text" for="'.$select_id.'">Device</label>';
    echo '<select id="'.$select_id.'" class="tmon-history-select" data-hours="'.$hours.'" data-canvas="'.$canvas_id.'">';
    foreach ($devices as $d) {
        $sel = selected($default_unit, $d['unit_id'], false);
        echo '<option value="'.esc_attr($d['unit_id']).'" '.$sel.'>'.esc_html($d['label']).'</option>';
    }
    echo '</select>';
    echo '<canvas id="'.$canvas_id.'" height="140"></canvas>';
    echo '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>';
    $script = <<<'JS'
(function(){
    const select = document.getElementById("%SELECT_ID%");
    const external = document.getElementById("tmon-unit-picker");
    const canvas = document.getElementById(select.getAttribute("data-canvas"));
    if(!select || !canvas) return;
    const ctx = canvas.getContext("2d");
    const base = (window.wp && wp.apiSettings && wp.apiSettings.root) ? wp.apiSettings.root.replace(/\/$/, "") : "%AJAX_ROOT%".replace(/\/$/, "");
    let chart = null;
    function render(unit){
        const hrs = select.getAttribute("data-hours") || "%HOURS%";
        const url = base + "/tmon/v1/device/history?unit_id=" + encodeURIComponent(unit) + "&hours=" + encodeURIComponent(hrs);
        fetch(url).then(r=>r.json()).then(data=>{
            const pts = Array.isArray(data.points) ? data.points : [];
            const labels = pts.map(p=>p.t);
            const temp = pts.map(p=>p.temp_f);
            const humid = pts.map(p=>p.humid);
            const bar = pts.map(p=>p.bar);
            const volt = pts.map(p=>p.volt);
            const enabledRelays = Array.isArray(data.enabled_relays) ? data.enabled_relays : [];
            const relayColors = ["#6c757d", "#95a5a6", "#34495e", "#7f8c8d", "#95a5a6", "#2d3436", "#636e72", "#99a3ad"];
            const relayDatasets = enabledRelays.map(function(num, idx){
                const key = "relay" + num + "_on";
                const values = pts.map(function(p){ return (p.relay && Object.prototype.hasOwnProperty.call(p.relay, key)) ? Number(p.relay[key]) : null; });
                return {label: "Relay " + num, data: values, borderColor: relayColors[idx % relayColors.length], borderDash: [6,3], fill:false, yAxisID: "relay", stepped:true};
            });
            const cfg = {
                type: "line",
                data: {
                    labels: labels,
                    datasets: [{label: "Temp (F)", data: temp, borderColor: "#e67e22", fill:false, yAxisID: "y1"},
                        {label: "Humidity (%)", data: humid, borderColor: "#3498db", fill:false, yAxisID: "y2"},
                        {label: "Pressure (hPa)", data: bar, borderColor: "#2ecc71", fill:false, yAxisID: "y3"},
                        {label: "Voltage (V)", data: volt, borderColor: "#9b59b6", fill:false, yAxisID: "y4"}].concat(relayDatasets)
                },
                options: {
                    responsive: true,
                    interaction: { mode: "index", intersect: false },
                    stacked: false,
                    plugins: {
                        legend: {
                            position: "top",
                            onClick: (evt, item, legend) => {
                                const ci = legend.chart;
                                const index = item.datasetIndex;
                                const visible = ci.isDatasetVisible(index);
                                ci.setDatasetVisibility(index, !visible);
                                ci.update();
                            }
                        }
                    },
                    scales: {
                        y1: { type: "linear", position: "left" },
                        y2: { type: "linear", position: "right", grid: { drawOnChartArea: false } },
                        y3: { type: "linear", position: "right", grid: { drawOnChartArea: false } },
                        y4: { type: "linear", position: "left", grid: { drawOnChartArea: false }, suggestedMin: %Y4MIN%, suggestedMax: %Y4MAX% },
                        relay: { type: "linear", position: "right", min: -0.1, max: 1.1, grid: { drawOnChartArea: false }, ticks: { stepSize: 1, callback: v => v ? "On" : "Off" } }
                    }
                }
            };
            if (chart) { chart.destroy(); }
            chart = new Chart(ctx, cfg);
        }).catch(err=>{ console.error("TMON history fetch error", err); });
    }
    if (external) { select.style.display = "none"; }
    const activeSelect = external || select;
    activeSelect.addEventListener("change", function(ev){ render(ev.target.value); });
    render(activeSelect.value);
    const refreshMs = %REFRESH_MS%;
    if (refreshMs > 0) {
        setInterval(function(){ render(activeSelect.value); }, refreshMs);
    }
})();
JS;
    $script = str_replace(
        ['%SELECT_ID%', '%AJAX_ROOT%', '%HOURS%', '%Y4MIN%', '%Y4MAX%', '%REFRESH_MS%'],
        [esc_js($select_id), esc_js(rest_url()), $hours, $y4min, $y4max, ($refresh*1000)],
        $script
    );
    echo '<script>'.$script.'</script>';
    echo '</div>';
    return ob_get_clean();
});

// [tmon_devices_history units="123,456" hours="24"]
// Renders a multi-line chart for multiple units over time
add_shortcode('tmon_devices_history', function($atts){
    $a = shortcode_atts(['units' => '', 'hours' => '24'], $atts);
    $units = array_filter(array_map('trim', explode(',', $a['units'])));
    $hours = intval($a['hours']);
    if (empty($units)) return '<em>Provide comma-separated unit IDs via units="...".</em>';
    $canvas_id = 'tmon-history-'.md5(implode(',', $units)).'-'.rand(1000,9999);
    ob_start();
    echo '<canvas id="'.$canvas_id.'" height="160"></canvas>';
    echo '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>';
    $multi_script = <<<'JS'
(function(){
    const ctx = document.getElementById("%CANVAS_ID%").getContext("2d");
    const units = %UNITS_ARR%;
    const base = (window.wp && wp.apiSettings && wp.apiSettings.root) ? wp.apiSettings.root.replace(/\/$/, "") : (window.location.origin || "") + "/wp-json";
    Promise.all(units.map(function(u){ return fetch(base + "/tmon/v1/device/history?unit_id=" + encodeURIComponent(u) + "&hours=%HOURS%" ).then(function(r){ return r.json(); }).catch(function(){ return {points:[], unit_id:u}; }); }))
        .then(function(results){
            const labels = (results[0] && Array.isArray(results[0].points)) ? results[0].points.map(function(p){ return p.t; }) : [];
            const colors = ["#e67e22", "#3498db", "#2ecc71", "#9b59b6", "#e74c3c", "#16a085", "#34495e"]; 
            const ds = results.map(function(res, idx){ return {label: (res.unit_id||units[idx]), data: (Array.isArray(res.points)?res.points:[]).map(function(p){ return p.temp_f; }), borderColor: colors[idx%colors.length], fill:false}; });
            new Chart(ctx, { type:"line", data: { labels: labels, datasets: ds }, options: { responsive:true, plugins: { legend:{position:"top"} } } });
        })
        .catch(function(err){ console.error("TMON multi-history fetch error", err); });
})();
JS;
    $multi_script = str_replace(
        ['%CANVAS_ID%', '%UNITS_ARR%', '%HOURS%'],
        [esc_js($canvas_id), json_encode(array_values($units)), $hours],
        $multi_script
    );
    echo '<script>'.$multi_script.'</script>';
    return ob_get_clean();
});

// [tmon_devices_sdata units="123,456" company="Acme" site="Main" zone="Z1" cluster="C1" limit="10"]
// Lists latest reading per device filtered by hierarchy or explicit units
add_shortcode('tmon_devices_sdata', function($atts){
    global $wpdb;
    $a = shortcode_atts([
        'units' => '',
        'company' => '',
        'site' => '',
        'zone' => '',
        'cluster' => '',
        'limit' => '10',
    ], $atts);
    $limit = max(1, min(200, intval($a['limit'])));
    $where = ['1=1'];
    $params = [];
    if (!empty($a['company'])) { $where[] = 'company = %s'; $params[] = $a['company']; }
    if (!empty($a['site']))    { $where[] = 'site = %s';    $params[] = $a['site']; }
    if (!empty($a['zone']))    { $where[] = 'zone = %s';    $params[] = $a['zone']; }
    if (!empty($a['cluster'])) { $where[] = 'cluster = %s'; $params[] = $a['cluster']; }
    $units = array_filter(array_map('trim', explode(',', $a['units'])));
    if (!empty($units)) {
        $placeholders = implode(',', array_fill(0, count($units), '%s'));
        $where[] = "unit_id IN ($placeholders)";
        $params = array_merge($params, $units);
    }
    $sql = "SELECT unit_id, unit_name, last_seen FROM {$wpdb->prefix}tmon_devices WHERE ".implode(' AND ', $where)." ORDER BY last_seen DESC LIMIT $limit";
    $rows = $params ? $wpdb->get_results($wpdb->prepare($sql, ...$params), ARRAY_A) : $wpdb->get_results($sql, ARRAY_A);
    if (!$rows) return '<em>No matching devices.</em>';
    // Fetch latest sdata row per unit
    $out = '<table class="wp-list-table widefat"><thead><tr><th>Unit</th><th>Name</th><th>Last Seen</th><th>Temp (F)</th><th>Humidity (%)</th><th>Pressure (hPa)</th><th>Voltage (V)</th></tr></thead><tbody>';
    foreach ($rows as $r) {
        $fd = $wpdb->get_row($wpdb->prepare("SELECT data, created_at FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s ORDER BY created_at DESC LIMIT 1", $r['unit_id']), ARRAY_A);
        $temp = $humid = $bar = $volt = '';
        if ($fd) {
            $d = json_decode($fd['data'], true);
            if (is_array($d)) {
                $temp = $d['t_f'] ?? ($d['cur_temp_f'] ?? '');
                $humid = $d['hum'] ?? ($d['cur_humid'] ?? '');
                $bar = $d['bar'] ?? ($d['cur_bar_pres'] ?? '');
                $volt = $d['v'] ?? ($d['sys_voltage'] ?? '');
            }
        }
        $out .= '<tr>'
            .'<td>'.esc_html($r['unit_id']).'</td>'
            .'<td>'.esc_html($r['unit_name']).'</td>'
            .'<td>'.esc_html($r['last_seen']).'</td>'
            .'<td>'.esc_html($temp).'</td>'
            .'<td>'.esc_html($humid).'</td>'
            .'<td>'.esc_html($bar).'</td>'
            .'<td>'.esc_html($volt).'</td>'
            .'</tr>';
    }
    $out .= '</tbody></table>';
    return $out;
});

// [tmon_claim_device]
add_shortcode('tmon_claim_device', function($atts) {
    if (!is_user_logged_in()) return '<em>Please log in to claim a device.</em>';
    $plugin_main = dirname(__DIR__) . '/tmon-unit-connector.php';
    $js_url   = plugins_url('assets/claim.js', $plugin_main);
    $css_url  = plugins_url('assets/claim.css', $plugin_main);
    // Prefer hub claim endpoint if defined
    $hub = defined('TMON_ADMIN_HUB_URL') ? TMON_ADMIN_HUB_URL : get_option('tmon_admin_hub_url', '');
    $rest_endpoint = $hub ? rtrim($hub, '/') . '/wp-json/tmon-admin/v1/claim' : esc_url_raw( rest_url('tmon-admin/v1/claim') );
    wp_enqueue_script('tmon-claim', $js_url, array(), '1.0', true);
    wp_localize_script('tmon-claim', 'TMON_CLAIM', array('nonce'=>wp_create_nonce('wp_rest'),'restUrl'=>$rest_endpoint));
    wp_enqueue_style('tmon-claim', $css_url, array(), '1.0');

    ob_start();
    ?>
    <div class="tmon-claim">
        <form class="tmon-claim-form" novalidate>
            <p>
                <label>
                    Unit ID
                            <input type="text" name="unit_id" required pattern="[A-Za-z0-9._-]{1,64}" title="Letters, numbers, dots, underscores, or dashes (max 64)" placeholder="e.g. base-001 or node-12">
                </label>
                        <span class="tmon-field-msg" data-for="unit_id" aria-live="polite"></span>
            </p>
            <p>
                <label>
                    Machine ID
                            <input type="text" name="machine_id" required pattern="[A-Fa-f0-9]{6,64}" maxlength="64" title="6–64 hex characters" placeholder="e.g. A1B2C3D4E5F6">
                </label>
                        <span class="tmon-field-msg" data-for="machine_id" aria-live="polite"></span>
            </p>
            <p><button type="submit" class="tmon-claim-submit">Submit Claim</button></p>
            <p class="tmon-claim-result" aria-live="polite"></p>
        </form>
    </div>
    <?php
    return ob_get_clean();
});

// [tmon_active_units]
add_shortcode('tmon_active_units', function($atts) {
    global $wpdb;
    $rows = $wpdb->get_results("SELECT unit_id, unit_name, last_seen FROM {$wpdb->prefix}tmon_devices WHERE suspended = 0 ORDER BY last_seen DESC", ARRAY_A);
    if (!$rows) return '<em>No active units.</em>';
    $out = '<table class="wp-list-table widefat"><thead><tr><th>Unit ID</th><th>Name</th><th>Last Seen</th></tr></thead><tbody>';
    foreach ($rows as $r) {
        $out .= '<tr><td>'.esc_html($r['unit_id']).'</td><td>'.esc_html($r['unit_name']).'</td><td>'.esc_html($r['last_seen']).'</td></tr>';
    }
    $out .= '</tbody></table>';
    return $out;
});

// [tmon_known_ids]
add_shortcode('tmon_known_ids', function($atts){
    global $wpdb;
    $rows = $wpdb->get_results("SELECT unit_id, machine_id, unit_name, last_seen FROM {$wpdb->prefix}tmon_devices ORDER BY last_seen DESC", ARRAY_A);
    if (!$rows) return '<em>No devices found.</em>';
    $out = '<table class="wp-list-table widefat"><thead><tr><th>Machine ID</th><th>Unit ID</th><th>Name</th><th>Last Seen</th></tr></thead><tbody>';
    foreach ($rows as $r) {
        $out .= '<tr>'
             . '<td>' . esc_html($r['machine_id'] ?: '') . '</td>'
             . '<td>' . esc_html($r['unit_id']) . '</td>'
             . '<td>' . esc_html($r['unit_name']) . '</td>'
             . '<td>' . esc_html($r['last_seen']) . '</td>'
             . '</tr>';
    }
    $out .= '</tbody></table>';
    return $out;
});

// [tmon_device_sdata refresh_s="30"]
// Renders latest sdata payload; unit is selected from the shared picker (#tmon-unit-picker) or a local dropdown fallback.
add_shortcode('tmon_device_sdata', function($atts) {
    $a = shortcode_atts([
        'refresh_s' => '30',
    ], $atts);
    $refresh = max(0, intval($a['refresh_s']));
    $devices = tmon_uc_list_feature_devices('sample');
    if (empty($devices)) {
        return '<em>No provisioned devices found for this feature.</em>';
    }

    $default_unit = $devices[0]['unit_id'];
    $select_id = 'tmon-sdata-select-' . wp_generate_password(6, false, false);
    $table_id = 'tmon-sdata-table-' . wp_generate_password(6, false, false);
    $meta_id = 'tmon-sdata-meta-' . wp_generate_password(6, false, false);
    $ajax_root = esc_js(rest_url());
    ob_start();
    echo '<div class="tmon-sdata-widget">';
    echo '<label class="screen-reader-text" for="'.$select_id.'">Device</label>';
    echo '<select id="'.$select_id.'" class="tmon-sdata-select">';
    foreach ($devices as $d) {
        $sel = selected($default_unit, $d['unit_id'], false);
        echo '<option value="'.esc_attr($d['unit_id']).'" '.$sel.'>'.esc_html($d['label']).'</option>';
    }
    echo '</select>';
    echo '<div id="'.$meta_id.'" class="tmon-sdata-meta"></div>';
    echo '<table class="wp-list-table widefat"><tbody id="'.$table_id.'"><tr><td><em>Loading...</em></td></tr></tbody></table>';
    $sdata_script = <<<'JS'
(function(){
    var select = document.getElementById("%SELECT_ID%");
    var external = document.getElementById("tmon-unit-picker");
    if (external) { select.style.display = "none"; }
    var activeSelect = external || select;
    var table = document.getElementById("%TABLE_ID%");
    var meta = document.getElementById("%META_ID%");
    var base = (window.wp && wp.apiSettings && wp.apiSettings.root) ? wp.apiSettings.root.replace(/\/$/, "") : "%AJAX_ROOT%".replace(/\/$/, "");
    function render(unit){
        var url = base + "/tmon/v1/device/sdata?unit_id=" + encodeURIComponent(unit);
        fetch(url).then(function(r){ return r.json(); }).then(function(data){
            if (!data || !data.data) {
                table.innerHTML = '<tr><td><em>No data for this unit.</em></td></tr>';
                meta.textContent = '';
                return;
            }
            var friendly = data.friendly || {};
            var rows = [];
            Object.keys(friendly).forEach(function(k){
                var v = friendly[k];
                if (v === null || v === undefined || v === '') return;
                rows.push('<tr><th>' + k + '</th><td>' + v + '</td></tr>');
            });
            table.innerHTML = rows.length ? rows.join('') : '<tr><td><em>No fields reported.</em></td></tr>';
            meta.textContent = data.created_at ? ('Last sample: ' + data.created_at) : '';
        }).catch(function(err){
            console.error('TMON sdata fetch error', err);
            table.innerHTML = '<tr><td><em>Error loading data.</em></td></tr>';
            meta.textContent = '';
        });
    }
    activeSelect.addEventListener('change', function(ev){ render(ev.target.value); });
    render(activeSelect.value);
    var refreshMs = %REFRESH_MS%;
    if (refreshMs > 0) { setInterval(function(){ render(activeSelect.value); }, refreshMs); }
})();
JS;
    $sdata_script = str_replace(
        ['%SELECT_ID%', '%TABLE_ID%', '%META_ID%', '%AJAX_ROOT%', '%REFRESH_MS%'],
        [esc_js($select_id), esc_js($table_id), esc_js($meta_id), esc_js(rest_url()), ($refresh*1000)],
        $sdata_script
    );
    echo '<script>'.$sdata_script.'</script>';
    echo '</div>';
    return ob_get_clean();
});

