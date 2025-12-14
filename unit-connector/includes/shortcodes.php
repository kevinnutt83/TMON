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
        // Parse DB timestamp directly (no timezone conversion/offset)
        $parsed = $last_str ? strtotime($last_str) : false;
        if ($parsed === false || $parsed === null) {
            $last = 0;
            $age = PHP_INT_MAX;
            $cls = 'tmon-red';
            $title = 'Never seen';
        } else {
            $last = intval($parsed);
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
            $title = 'Last seen: ' . date_i18n(get_option('date_format') . ' ' . get_option('time_format'), $last) . ' (' . human_time_diff($last, $now) . ' ago)';
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
        $enabled_relays = array_values(array_unique($enabled_relays));

        // Status dot
        echo '<tr>';
        echo '<td><span class="tmon-dot ' . esc_attr($cls) . '" title="' . esc_attr($title) . '"></span></td>';
        echo '<td>' . esc_html($r['unit_id']) . '</td>';
        echo '<td>' . esc_html($r['unit_name'] ?: '-') . '</td>';
        echo '<td>' . esc_html($last_str) . '</td>';
        echo '<td>';
        if ($can_control) {
            echo '<div class="tmon-relay-ctl" data-unit="'.esc_attr($r['unit_id']).'" data-nonce="'.esc_attr($nonce).'">';
            echo '<label class="tmon-text-muted">Run (min)</label><input type="number" min="0" max="1440" step="1" class="tmon-runtime-min" title="Runtime minutes (0 = no auto-off)" value="0"> ';
            echo '<label class="tmon-text-muted">At</label><input type="datetime-local" class="tmon-schedule-at" title="Optional schedule time"> ';
            foreach ($enabled_relays as $n) {
                echo '<div class="tmon-relay-row">';
                echo '<span class="tmon-text-muted">R'.esc_html($n).'</span> ';
                echo '<button type="button" class="button button-small tmon-relay-btn" data-relay="'.esc_attr($n).'" data-state="on">On</button> ';
                echo '<button type="button" class="button button-small tmon-relay-btn" data-relay="'.esc_attr($n).'" data-state="off">Off</button>';
                echo '</div>';
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
    // Inline JS to handle relay control clicks (delegated)
    $ajax_url = esc_js(admin_url('admin-ajax.php'));
    echo '<script>(function(){ function post(url,data){ return fetch(url,{method:"POST", headers: {"Content-Type":"application/x-www-form-urlencoded; charset=UTF-8"}, body: new URLSearchParams(data)}).then(r=>r.json()); } document.addEventListener("click", function(ev){ var btn = ev.target.closest(".tmon-relay-btn"); if(!btn) return; var wrap = btn.closest(".tmon-relay-ctl"); if(!wrap) return; var unit = wrap.getAttribute("data-unit"); var nonce = wrap.getAttribute("data-nonce"); var relay = btn.getAttribute("data-relay"); var state = btn.getAttribute("data-state"); var rtMinEl = wrap.querySelector(".tmon-runtime-min"); var schEl = wrap.querySelector(".tmon-schedule-at"); var runtime_min = rtMinEl && rtMinEl.value ? parseInt(rtMinEl.value,10) : 0; if(isNaN(runtime_min)||runtime_min<0) runtime_min=0; var schedule_at = schEl ? schEl.value : ""; var payload = { action: "tmon_uc_relay_command", nonce: nonce, unit_id: unit, relay_num: relay, state: state, runtime_min: String(runtime_min), schedule_at: schedule_at }; btn.disabled=true; var old = btn.textContent; btn.textContent = state+"..."; post("'.$ajax_url.'", payload).then(function(res){ btn.textContent = old; btn.disabled=false; if(!res || !res.success){ alert((res && res.data) ? (res.data.message||res.data) : "Command failed"); return; } var d=res.data||{}; var msg = d.scheduled ? "Scheduled" : "Queued"; alert(msg+" relay "+relay+" "+state + (runtime_min?(" for "+runtime_min+" min"):"")); }).catch(function(){ btn.textContent = old; btn.disabled=false; alert("Network error"); }); }); })();</script>';
    return ob_get_clean();
});

// AJAX: relay command (logged-in users only)
if (!function_exists('tmon_uc_relay_command')) {
function tmon_uc_relay_command() {
    if ( empty( $_POST['nonce'] ) || ! wp_verify_nonce( wp_unslash( $_POST['nonce'] ), 'tmon_uc_relay' ) ) {
        wp_send_json_error( 'Invalid nonce', 403 );
    }
    if ( ! ( current_user_can('manage_options') || current_user_can('edit_tmon_units') ) ) {
        wp_send_json_error( 'Permission denied', 403 );
    }
    $unit = isset($_POST['unit_id']) ? sanitize_text_field(wp_unslash($_POST['unit_id'])) : '';
    $relay = isset($_POST['relay_num']) ? intval($_POST['relay_num']) : 0;
    $state = isset($_POST['state']) ? sanitize_text_field($_POST['state']) : '';
    $runtime_min = isset($_POST['runtime_min']) ? intval($_POST['runtime_min']) : 0;
    $schedule_at = isset($_POST['schedule_at']) ? sanitize_text_field($_POST['schedule_at']) : '';
    if (empty($unit) || !$relay || !in_array($state, ['on','off'], true)) {
        wp_send_json_error('Missing parameters', 400);
    }
    global $wpdb;
    $table = $wpdb->prefix . 'tmon_device_commands';
    $now = current_time('mysql');
    $data = [
        'device_id' => $unit,
        'relay_num' => $relay,
        'command' => $state,
        'runtime_min' => $runtime_min,
        'schedule_at' => $schedule_at ?: null,
        'created_at' => $now,
    ];
    $ok = $wpdb->insert($table, $data, array('%s','%d','%s','%d','%s','%s'));
    if (!$ok) return wp_send_json_error('DB error', 500);
    $scheduled = !empty($schedule_at);
    wp_send_json_success(['queued' => true, 'scheduled' => (bool)$scheduled]);
}}
add_action('wp_ajax_tmon_uc_relay_command', 'tmon_uc_relay_command');

// tmon_device_history — allow unit_id="" to fix unit and hide selector
add_shortcode('tmon_device_history', function($atts) {
    $a = shortcode_atts([
        'hours' => '24',
        'refresh_s' => '60',
        'unit_id' => '',
    ], $atts);
    $hours = max(1, intval($a['hours']));
    $refresh = max(0, intval($a['refresh_s']));
    $fixed_unit = sanitize_text_field($a['unit_id']);
    $feature = 'sample';
    $devices = tmon_uc_list_feature_devices($feature);
    if (empty($devices)) return '<em>No provisioned devices found for this feature.</em>';
    $default_unit = $fixed_unit ?: $devices[0]['unit_id'];
    $select_id = 'tmon-history-select-' . wp_generate_password(6, false, false);
    $canvas_id = 'tmon-history-chart-' . wp_generate_password(8, false, false);
    $ajax_root = esc_js(rest_url());
    ob_start();
    echo '<div class="tmon-history-widget">';
    echo '<label class="screen-reader-text" for="'.$select_id.'">Device</label>';
    echo '<select id="'.$select_id.'" class="tmon-history-select" data-hours="'.$hours.'" data-canvas="'.$canvas_id.'">';
    foreach ($devices as $d) {
        $sel = selected($default_unit, $d['unit_id'], false);
        echo '<option value="'.esc_attr($d['unit_id']).'" '.$sel.'>'.esc_html($d['label']).'</option>';
    }
    echo '</select>';
    echo '<div id="'.$canvas_id.'" class="tmon-history-canvas" style="height:300px;min-width:400px"></div>';
    echo '</div>';
    // inject JS with fixed unit support
    $script = <<<'JS'
(function(){
    const select = document.getElementById("%SELECT_ID%");
    const fixedUnit = "%UNIT%";
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
            if (!data || !data.success) return;
            const labels = [], series = [], pointStale = [];
            let minTs = Number.MAX_SAFE_INTEGER, maxTs = 0;
            (data.data || []).forEach(row=>{
                const ts = (row.created_at) ? (new Date(row.created_at)).getTime() : 0;
                if (ts < 1000000000000) return; // sanity
                if (ts < minTs) minTs = ts;
                if (ts > maxTs) maxTs = ts;
                labels.push(new Date(ts));
                series.push(row.avg || 0);
                pointStale.push(!!row.stale);
            });
            if (chart) {
                chart.destroy();
                ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
                chart = null;
            }
            if (labels.length < 2) return;
            const opts = {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Avg. Value',
                        data: series,
                        borderColor: '#0073aa',
                        backgroundColor: 'rgba(0,115,170,0.2)',
                        fill: true,
                        pointRadius: (ctx) => { var i = ctx.dataIndex; return (pointStale[i] ? 4 : 2); },
                        pointBackgroundColor: (ctx) => { var i = ctx.dataIndex; return (pointStale[i] ? '#e74c3c' : '#fff'); },
                        pointBorderColor: (ctx) => { var i = ctx.dataIndex; return (pointStale[i] ? '#e74c3c' : '#0073aa'); },
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            type: 'time',
                            time: {
                                tooltipFormat: 'll HH:mm',
                                unit: 'hour',
                                displayFormats: {
                                    hour: 'MMM D, HH:mm',
                                },
                            },
                            title: {
                                display: true,
                                text: 'Time',
                            },
                        },
                        y: {
                            title: {
                                display: true,
                                text: 'Value',
                            },
                            ticks: {
                                beginAtZero: true,
                            },
                        },
                    },
                    plugins: {
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    let label = context.dataset.label || '';
                                    if (label && context.parsed.y !== null) {
                                        label += ': ' + context.parsed.y.toFixed(2);
                                    }
                                    return label;
                                },
                            },
                        },
                    },
                },
            };
            const Chart = window.Chart;
            if (Chart && typeof Chart === 'function') {
                chart = new Chart(ctx, opts);
            }
        }).catch(err=>{ console.error("TMON history fetch error", err); });
    }
    if (fixedUnit) { select.style.display="none"; render(fixedUnit); return; }
    if (external) { select.style.display = "none"; }
    const activeSelect = external || select;
    activeSelect.addEventListener("change", function(ev){ render(ev.target.value); });
    render(activeSelect.value);
    const refreshMs = %REFRESH_MS%;
    if (refreshMs > 0) { setInterval(function(){ render(activeSelect.value); }, refreshMs); }
})();
JS;
    $script = str_replace(['%SELECT_ID%','%AJAX_ROOT%','%HOURS%','%UNIT%','%REFRESH_MS%'], [$select_id, esc_js(rest_url()), $hours, esc_js($fixed_unit), ($refresh*1000)], $script);
    echo '<script>'.$script.'</script>';
    echo '</div>';
    return ob_get_clean();
});

// tmon_device_sdata — allow unit_id attribute
add_shortcode('tmon_device_sdata', function($atts) {
    $a = shortcode_atts([
        'refresh_s' => '30',
        'unit_id' => '',
    ], $atts);
    $refresh = max(0, intval($a['refresh_s']));
    $fixed_unit = sanitize_text_field($a['unit_id']);
    $devices = tmon_uc_list_feature_devices('sample');
    if (empty($devices)) return '<em>No provisioned devices found for this feature.</em>';
    $default_unit = $fixed_unit ?: $devices[0]['unit_id'];
    $select_id = 'tmon-sdata-select-' . wp_generate_password(6, false, false);
    $table_id = 'tmon-sdata-table-' . wp_generate_password(6, false, false);
    $meta_id = 'tmon-sdata-meta-' . wp_generate_password(6, false, false);
    ob_start();
    echo '<div class="tmon-sdata-widget">';
    echo '<label class="screen-reader-text" for="'.$select_id.'">Device</label>';
    echo '<select id="'.$select_id.'" class="tmon-sdata-select">';
    foreach ($devices as $d) {
        $sel = selected($default_unit, $d['unit_id'], false);
        echo '<option value="'.esc_attr($d['unit_id']).'" '.$sel.'>'.esc_html($d['label']).'</option>';
    }
    echo '</select>';
    echo '<div id="'.$table_id.'" class="tmon-sdata-table"></div>';
    echo '<div id="'.$meta_id.'" class="tmon-sdata-meta"></div>';
    echo '</div>';
    // JS with fixed unit support
    $sdata_script = <<<'JS'
(function(){
    var select = document.getElementById("%SELECT_ID%");
    var fixedUnit = "%UNIT%";
    var external = document.getElementById("tmon-unit-picker");
    var table = document.getElementById("%TABLE_ID%");
    var meta = document.getElementById("%META_ID%");
    var base = (window.wp && wp.apiSettings && wp.apiSettings.root) ? wp.apiSettings.root.replace(/\/$/, "") : "%AJAX_ROOT%".replace(/\/$/, "");
    function render(unit){
        var url = base + "/tmon/v1/device/sdata?unit_id=" + encodeURIComponent(unit);
        fetch(url).then(function(r){ return r.json(); }).then(function(data){
            if (!data || !data.success) return;
            var html = '<table class="widefat striped"><thead><tr><th>Parameter</th><th>Value</th></tr></thead><tbody>';
            var metaHtml = '<h4>Metadata</h4><pre>' + JSON.stringify(data.data.meta || {}, null, 2) + '</pre>';
            (data.data.values || []).forEach(function(row){
                html += '<tr><td>' + esc_html(row.param) + '</td><td>' + esc_html(row.value) + '</td></tr>';
            });
            html += '</tbody></table>';
            table.innerHTML = html;
            meta.innerHTML = metaHtml;
        }).catch(function(err){
            console.error('TMON sdata fetch error', err);
        });
    }
    if (fixedUnit) { select.style.display="none"; render(fixedUnit); return; }
    if (external) { select.style.display = "none"; }
    var activeSelect = external || select;
    activeSelect.addEventListener('change', function(ev){ render(ev.target.value); });
    render(activeSelect.value);
    var refreshMs = %REFRESH_MS%;
    if (refreshMs > 0) { setInterval(function(){ render(activeSelect.value); }, refreshMs); }
})();
JS;
    $sdata_script = str_replace(['%SELECT_ID%','%UNIT%','%TABLE_ID%','%META_ID%','%AJAX_ROOT%','%REFRESH_MS%'], [$select_id, esc_js($fixed_unit), $table_id, $meta_id, esc_js(rest_url()), ($refresh*1000)], $sdata_script);
    echo '<script>'.$sdata_script.'</script>';
    echo '</div>';
    return ob_get_clean();
});

