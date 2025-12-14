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

