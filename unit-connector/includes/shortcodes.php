<?php
// Shortcode to display pending command count for a unit: [tmon_pending_commands unit="170170"]
add_shortcode('tmon_pending_commands', function($atts){
    $atts = shortcode_atts(['unit' => ''], $atts);
    $unit = sanitize_text_field($atts['unit']);
    if (!$unit) return '';
    global $wpdb;
    $cnt = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM {$wpdb->prefix}tmon_device_commands WHERE device_id = %s AND executed_at IS NULL", $unit));
    return '<span class="tmon-pending-commands" data-unit="'.esc_attr($unit).'">'.intval($cnt).'</span>';
});

// Dashboard widget to summarize pending commands
add_action('wp_dashboard_setup', function(){
    wp_add_dashboard_widget('tmon_cmd_summary', 'TMON Command Summary', function(){
        global $wpdb;
        $rows = $wpdb->get_results("SELECT device_id, COUNT(*) as pending FROM {$wpdb->prefix}tmon_device_commands WHERE executed_at IS NULL GROUP BY device_id ORDER BY pending DESC LIMIT 10", ARRAY_A);
        echo '<table class="widefat"><thead><tr><th>Unit</th><th>Pending</th></tr></thead><tbody>';
        foreach ($rows as $r) {
            echo '<tr><td>'.esc_html($r['device_id']).'</td><td>'.intval($r['pending']).'</td></tr>';
        }
        if (empty($rows)) echo '<tr><td colspan="2"><em>No pending commands</em></td></tr>';
        echo '</tbody></table>';
    });
});

// Ensure ABSPATH is defined
defined('ABSPATH') || exit;

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
    foreach ($devices as $r) { $index[$r['unit_id']] = $r; }

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
        $last = strtotime($r['last_seen'] ?: '1970-01-01 00:00:00');
        $age = $now - $last;
        $cls = $age <= 10*60 ? 'tmon-green' : ($age <= 60*60 ? 'tmon-yellow' : 'tmon-red');
        if (intval($r['suspended'])) $cls = 'tmon-red';

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
        echo '<td><span class="tmon-dot '.$cls.'"></span></td>';
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

// [tmon_device_history unit_id="123" hours="24"]
add_shortcode('tmon_device_history', function($atts) {
        $a = shortcode_atts(['unit_id' => '', 'hours' => '24'], $atts);
        $unit_id = esc_attr($a['unit_id']);
        $hours = intval($a['hours']);
        if (!$unit_id) return '<em>Missing unit_id.</em>';
        ob_start();
        echo '<canvas id="tmon-history-chart" height="120"></canvas>';
        echo '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>';
        echo '<script>(function(){
                const ctx = document.getElementById("tmon-history-chart").getContext("2d");
                const base = (window.wp && wp.apiSettings && wp.apiSettings.root) ? wp.apiSettings.root.replace(/\/$/, "") : (window.location.origin || "") + "/wp-json";
                const url = `${base}/tmon/v1/device/history?unit_id='. $unit_id .'&hours='. $hours .'`;
                fetch(url)
                    .then(r=>r.json())
                    .then(data=>{
                        const pts = Array.isArray(data.points) ? data.points : [];
                        const labels = pts.map(p=>p.t);
                        const temp = pts.map(p=>p.temp_f);
                        const humid = pts.map(p=>p.humid);
                        const bar = pts.map(p=>p.bar);
                        new Chart(ctx, {
                            type: "line",
                            data: {
                                labels: labels,
                                datasets: [
                                    {label: "Temp (F)", data: temp, borderColor: "#e67e22", fill:false, yAxisID: "y1"},
                                    {label: "Humidity (%)", data: humid, borderColor: "#3498db", fill:false, yAxisID: "y2"},
                                    {label: "Pressure (hPa)", data: bar, borderColor: "#2ecc71", fill:false, yAxisID: "y3"}
                                ]
                            },
                            options: {
                                responsive: true,
                                interaction: { mode: "index", intersect: false },
                                stacked: false,
                                plugins: { legend: { position: "top" } },
                                scales: {
                                    y1: { type: "linear", position: "left" },
                                    y2: { type: "linear", position: "right", grid: { drawOnChartArea: false } },
                                    y3: { type: "linear", position: "right", grid: { drawOnChartArea: false } }
                                }
                            }
                        });
                    })
                    .catch(err=>{ console.error("TMON history fetch error", err); });
        })();</script>';
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
    echo '<script>(function(){
        const ctx = document.getElementById("'.$canvas_id.'").getContext("2d");
        const units = '.json_encode($units).';
        const base = (window.wp && wp.apiSettings && wp.apiSettings.root) ? wp.apiSettings.root.replace(/\/$/, "") : (window.location.origin || "") + "/wp-json";
        Promise.all(units.map(u => fetch(`${base}/tmon/v1/device/history?unit_id=${encodeURIComponent(u)}&hours='.$hours.'`).then(r=>r.json()).catch(()=>({points:[], unit_id:u}))))
            .then(results=>{
                const labels = (results[0] && Array.isArray(results[0].points)) ? results[0].points.map(p=>p.t) : [];
                const colors = ["#e67e22", "#3498db", "#2ecc71", "#9b59b6", "#e74c3c", "#16a085", "#34495e"]; 
                const ds = results.map((res, idx) => ({label: (res.unit_id||units[idx]), data: (Array.isArray(res.points)?res.points:[]).map(p=>p.temp_f), borderColor: colors[idx%colors.length], fill:false}));
                new Chart(ctx, { type:"line", data: { labels, datasets: ds }, options: { responsive:true, plugins: { legend:{position:"top"} } } });
            })
            .catch(err=>{ console.error("TMON multi-history fetch error", err); });
    })();</script>';
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

// [tmon_device_sdata unit_id="123"]
// Renders latest sdata payload in a user-friendly table, works for remotes and bases alike.
add_shortcode('tmon_device_sdata', function($atts) {
    global $wpdb;
    $a = shortcode_atts(['unit_id' => ''], $atts);
    $unit_id = sanitize_text_field($a['unit_id']);
    if (!$unit_id) return '<em>Missing unit_id.</em>';
    $row = $wpdb->get_row($wpdb->prepare("SELECT data, created_at FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s ORDER BY created_at DESC LIMIT 1", $unit_id), ARRAY_A);
    if (!$row) return '<em>No data for this unit.</em>';
    $data = json_decode($row['data'], true);
    if (!is_array($data)) return '<em>Invalid data.</em>';
    // If record came from a base with embedded remote, still treated the same as we saved per-unit rows
    $friendly = [
        'Timestamp' => isset($data['timestamp']) ? esc_html($data['timestamp']) : esc_html($row['created_at']),
        'Temperature (F)' => isset($data['t_f']) ? esc_html($data['t_f']) : (isset($data['cur_temp_f']) ? esc_html($data['cur_temp_f']) : ''),
        'Temperature (C)' => isset($data['t_c']) ? esc_html($data['t_c']) : (isset($data['cur_temp_c']) ? esc_html($data['cur_temp_c']) : ''),
        'Humidity (%)' => isset($data['hum']) ? esc_html($data['hum']) : (isset($data['cur_humid']) ? esc_html($data['cur_humid']) : ''),
        'Pressure (hPa)' => isset($data['bar']) ? esc_html($data['bar']) : (isset($data['cur_bar_pres']) ? esc_html($data['cur_bar_pres']) : ''),
        'Voltage (V)' => isset($data['v']) ? esc_html($data['v']) : (isset($data['sys_voltage']) ? esc_html($data['sys_voltage']) : ''),
        'Free Mem (bytes)' => isset($data['fm']) ? esc_html($data['fm']) : (isset($data['free_mem']) ? esc_html($data['free_mem']) : ''),
        'Device Name' => isset($data['name']) ? esc_html($data['name']) : '',
    ];
    $out = '<table class="wp-list-table widefat"><tbody>';
    foreach ($friendly as $k => $v) {
        if ($v === '') continue;
        $out .= '<tr><th>'.esc_html($k).'</th><td>'.$v.'</td></tr>';
    }
    $out .= '</tbody></table>';
    return $out;
});

