<?php
// Shortcode to display pending command list for a unit: [tmon_pending_commands]
add_shortcode('tmon_pending_commands', function($atts){
    global $wpdb;
    // Get all units for dropdown
    $units = $wpdb->get_results("SELECT unit_id, unit_name FROM {$wpdb->prefix}tmon_devices ORDER BY unit_name ASC, unit_id ASC", ARRAY_A);
    $unit_map = [];
    foreach ($units as $u) {
        $unit_map[$u['unit_id']] = $u['unit_name'];
    }
    // Get pending commands with unit info
    $rows = $wpdb->get_results(
        "SELECT c.id, c.device_id, d.unit_name, c.command, c.created_at
         FROM {$wpdb->prefix}tmon_device_commands c
         LEFT JOIN {$wpdb->prefix}tmon_devices d ON c.device_id = d.unit_id
         WHERE c.executed_at IS NULL
         ORDER BY c.created_at ASC
         LIMIT 100", ARRAY_A);

    if (empty($rows)) {
        return '<em>No pending commands found.</em>';
    }

    // Permission check (same as relay controls)
    $can_control = current_user_can('manage_options') || current_user_can('edit_tmon_units');

    $ajax_nonce = wp_create_nonce('tmon_pending_cmds');
    $table_id = 'tmon-pending-table-' . wp_generate_password(6, false, false);
    $select_id = 'tmon-pending-unit-select-' . wp_generate_password(6, false, false);

    ob_start();
    // Dropdown filter
    echo '<label for="'.$select_id.'" style="margin-right:8px;">Unit:</label>';
    echo '<select id="'.$select_id.'" style="margin-bottom:10px;">';
    echo '<option value="">View All</option>';
    foreach ($unit_map as $uid => $uname) {
        $label = $uname ? ($uname . ' (' . $uid . ')') : $uid;
        echo '<option value="'.esc_attr($uid).'">'.esc_html($label).'</option>';
    }
    echo '</select>';

    echo '<table id="'.$table_id.'" class="wp-list-table widefat" style="margin-top:10px;">';
    echo '<thead><tr><th>Unit ID</th><th>Name</th><th>Command</th><th>Created</th><th>Actions</th></tr></thead><tbody>';
    foreach ($rows as $r) {
        $cmd = $r['command'];
        if (is_string($cmd) && ($decoded = json_decode($cmd, true)) && json_last_error() === JSON_ERROR_NONE) {
            $cmd = '<pre style="margin:0;font-size:13px;">'.esc_html(json_encode($decoded, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)).'</pre>';
        } else {
            $cmd = '<pre style="margin:0;font-size:13px;">'.esc_html($cmd).'</pre>';
        }
        echo '<tr data-unit="'.esc_attr($r['device_id']).'">'
            .'<td>'.esc_html($r['device_id']).'</td>'
            .'<td>'.esc_html($r['unit_name']).'</td>'
            .'<td>'.$cmd.'</td>'
            .'<td>'.esc_html(tmon_uc_format_mysql_datetime($r['created_at'])).'</td>'
            .'<td>';
        if ($can_control) {
            echo '<button class="button button-small tmon-cmd-del" data-id="'.intval($r['id']).'">Delete</button> ';
            echo '<button class="button button-small tmon-cmd-requeue" data-id="'.intval($r['id']).'" data-unit="'.esc_attr($r['device_id']).'">Re-Queue</button>';
        } else {
            echo '<span class="tmon-text-muted">No control permission</span>';
        }
        echo '</td></tr>';
    }
    echo '</tbody></table>';
    ?>
    <script>
    (function(){
        var table = document.getElementById("<?php echo esc_js($table_id); ?>");
        var select = document.getElementById("<?php echo esc_js($select_id); ?>");
        var ajaxurl = window.ajaxurl || "<?php echo admin_url('admin-ajax.php'); ?>";
        var nonce = "<?php echo esc_js($ajax_nonce); ?>";
        // Filtering logic
        select.addEventListener('change', function(){
            var val = select.value;
            Array.from(table.tBodies[0].rows).forEach(function(row){
                if (!val || row.getAttribute('data-unit') === val) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        });
        // Delete logic
        table.addEventListener('click', function(ev){
            var btn = ev.target.closest('.tmon-cmd-del');
            if (!btn) return;
            var id = btn.getAttribute('data-id');
            if (!id || !confirm('Delete this command?')) return;
            btn.disabled = true;
            fetch(ajaxurl + "?action=tmon_pending_commands_delete", {
                method: "POST",
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: "id=" + encodeURIComponent(id) + "&_wpnonce=" + nonce
            }).then(r=>r.json()).then(function(res){
                if (res && res.success) {
                    btn.closest('tr').remove();
                } else {
                    alert('Delete failed');
                    btn.disabled = false;
                }
            }).catch(function(){
                alert('Delete failed');
                btn.disabled = false;
            });
        });
        // Re-queue logic
        table.addEventListener('click', function(ev){
            var btn = ev.target.closest('.tmon-cmd-requeue');
            if (!btn) return;
            var id = btn.getAttribute('data-id');
            var unit = btn.getAttribute('data-unit');
            if (!id || !unit) return;
            btn.disabled = true;
            fetch(ajaxurl + "?action=tmon_pending_commands_get", {
                method: "POST",
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: "id=" + encodeURIComponent(id) + "&_wpnonce=" + nonce
            }).then(r=>r.json()).then(function(res){
                // Fix: handle whitespace, JSON, and fallback for command
                if (res && res.success && typeof res.command !== "undefined") {
                    var unit_id = res.device_id || unit;
                    var cmd = res.command;
                    // If command is an object, stringify it
                    if (typeof cmd === "object") {
                        cmd = JSON.stringify(cmd);
                    }
                    // If command is a string, trim whitespace
                    if (typeof cmd === "string") {
                        cmd = cmd.trim();
                    }
                    fetch(ajaxurl + "?action=tmon_pending_commands_requeue", {
                        method: "POST",
                        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                        body: "unit_id=" + encodeURIComponent(unit_id) + "&command=" + encodeURIComponent(cmd) + "&_wpnonce=" + nonce
                    }).then(r2=>r2.json()).then(function(res2){
                        if (res2 && res2.success) {
                            alert('Command re-queued.');
                        } else {
                            alert('Re-queue failed');
                        }
                        btn.disabled = false;
                    }).catch(function(){
                        alert('Re-queue failed');
                        btn.disabled = false;
                    });
                } else {
                    alert((res && res.message) ? res.message : 'Could not fetch command for re-queue.');
                    btn.disabled = false;
                }
            }).catch(function(){
                alert('Could not fetch command for re-queue.');
                btn.disabled = false;
            });
        });
    })();
    </script>
    <?php
    return ob_get_clean();
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

// [tmon_pending_commands_summary]
// Outputs a table summarizing pending commands per device, similar to the dashboard widget
add_shortcode('tmon_pending_commands_summary', function($atts){
    global $wpdb;
    $rows = $wpdb->get_results("SELECT device_id, COUNT(*) as pending FROM {$wpdb->prefix}tmon_device_commands WHERE executed_at IS NULL GROUP BY device_id ORDER BY pending DESC LIMIT 10", ARRAY_A);
    $out = '<table class="widefat"><thead><tr><th>Unit</th><th>Pending</th></tr></thead><tbody>';
    foreach ($rows as $r) {
        $out .= '<tr><td>'.esc_html($r['device_id']).'</td><td>'.intval($r['pending']).'</td></tr>';
    }
    if (empty($rows)) $out .= '<tr><td colspan="2"><em>No pending commands</em></td></tr>';
    $out .= '</tbody></table>';
    return $out;
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
    foreach ($devices as $r) { $index[$r['unit_id']] = $r; }
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
    // Fix: Use gmdate for now and last_seen, compare as UTC
    $now = time(); // PHP time() is always UTC
    $nonce = wp_create_nonce('tmon_uc_relay');
    foreach ($rows as $r) {
        $last = $r['last_seen'] ? strtotime($r['last_seen'] . ' UTC') : 0;
        if (!$last) {
            $age = PHP_INT_MAX;
            $cls = 'tmon-red';
            $title = 'Never seen';
        } else {
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
            $title = 'Last seen: ' . gmdate(get_option('date_format') . ' ' . get_option('time_format'), $last) . ' (' . human_time_diff($last, $now) . ' ago)';
        }

        // Robust relay detection (scan keys like ENABLE_RELAY1, ENABLE_RELAY_1, enable_relay1, etc)
        // Always enable relays 1 and 2 by default
        $enabled_relays = [1, 2];
        $settings = !empty($r['settings']) ? json_decode($r['settings'], true) : [];
        if (is_array($settings)) {
            foreach ($settings as $k => $v) {
                if (preg_match('/^enable[_]?relay[_]?(\d+)$/i', $k, $m) && isset($m[1])) {
                    $n = intval($m[1]);
                    if ($n >= 1 && $n <= 8 && tmon_uc_truthy_flag($v)) $enabled_relays[] = $n;
                }
            }
        }
        // Also check field data for relay enablement
        $fd = $wpdb->get_row($wpdb->prepare("SELECT data FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s ORDER BY created_at DESC LIMIT 1", $r['unit_id']), ARRAY_A);
        $fddata = $fd['data'] ?? '';
        $d = $fddata ? json_decode($fddata, true) : [];
        if (is_array($d)) {
            foreach ($d as $k => $v) {
                if (preg_match('/^enable[_]?relay[_]?(\d+)$/i', $k, $m) && isset($m[1])) {
                    $n = intval($m[1]);
                    if ($n >= 1 && $n <= 8 && tmon_uc_truthy_flag($v)) $enabled_relays[] = $n;
                }
            }
        }
        $enabled_relays = array_values(array_unique($enabled_relays));

        echo '<tr>';
        echo '<td><span class="tmon-dot '.$cls.'" title="'.esc_attr($title).'"></span></td>';
        echo '<td>'.esc_html($r['unit_id']).'</td>';
        echo '<td>'.esc_html($r['unit_name']).'</td>';
        echo '<td>'.esc_html(tmon_uc_format_mysql_datetime($r['last_seen'])).'</td>';
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
    $hours_id = 'tmon-history-hours-' . wp_generate_password(6, false, false);
    $csv_btn_id = 'tmon-history-csv-' . wp_generate_password(6, false, false);
    $ajax_root = esc_js(rest_url());
    $voltage_min = get_option('tmon_uc_history_voltage_min', '');
    $voltage_max = get_option('tmon_uc_history_voltage_max', '');
    $y4min = ($voltage_min !== '') ? floatval($voltage_min) : 'null';
    $y4max = ($voltage_max !== '') ? floatval($voltage_max) : 'null';

    // Hours filter options
    $hour_opts = [
        1=>'1h',4=>'4h',8=>'8h',12=>'12h',24=>'24h',48=>'48h',72=>'72h',96=>'96h',
        168=>'7d',336=>'14d',504=>'21d',720=>'1mo',2160=>'3mo',4320=>'6mo',8640=>'12mo','yoy'=>'YoY'
    ];

    ob_start();
    echo '<div class="tmon-history-widget">';
    echo '<label class="screen-reader-text" for="'.$select_id.'">Device</label>';
    echo '<select id="'.$select_id.'" class="tmon-history-select" data-canvas="'.$canvas_id.'">';
    foreach ($devices as $d) {
        $sel = selected($default_unit, $d['unit_id'], false);
        echo '<option value="'.esc_attr($d['unit_id']).'" '.$sel.'>'.esc_html($d['label']).'</option>';
    }
    echo '</select> ';
    // Hours filter dropdown
    echo '<label for="'.$hours_id.'" style="margin-left:8px;">Period:</label>';
    echo '<select id="'.$hours_id.'" style="margin-bottom:10px;">';
    foreach ($hour_opts as $hval => $hlabel) {
        $sel = ($hval == $hours) ? 'selected' : '';
        echo '<option value="'.esc_attr($hval).'" '.$sel.'>'.esc_html($hlabel).'</option>';
    }
    echo '</select> ';
    // Export CSV button
    echo '<button id="'.$csv_btn_id.'" type="button" class="button" style="margin-left:8px;">Export CSV</button>';
    echo '<canvas id="'.$canvas_id.'" height="140"></canvas>';
    echo '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>';
    ?>
    <script>
    (function(){
        const select = document.getElementById("<?php echo esc_js($select_id); ?>");
        const hoursSel = document.getElementById("<?php echo esc_js($hours_id); ?>");
        const csvBtn = document.getElementById("<?php echo esc_js($csv_btn_id); ?>");
        const canvas = document.getElementById(select.getAttribute("data-canvas"));
        if(!select || !canvas) return;
        const ctx = canvas.getContext("2d");
        const base = (window.wp && wp.apiSettings && wp.apiSettings.root) ? wp.apiSettings.root.replace(/\/$/, "") : "<?php echo $ajax_root; ?>".replace(/\/$/, "");
        let chart = null;
        let lastData = null;
        function relayStateValue(p, num) {
            // Accept relay1_on, relay_1_on, etc.
            if (!p.relay) return null;
            var k1 = "relay" + num + "_on";
            var k2 = "relay_" + num + "_on";
            if (Object.prototype.hasOwnProperty.call(p.relay, k1)) return Number(p.relay[k1]);
            if (Object.prototype.hasOwnProperty.call(p.relay, k2)) return Number(p.relay[k2]);
            return null;
        }
        function render(unit, hours){
            let url;
            if (hours === 'yoy') {
                url = base + "/tmon/v1/device/history-yoy?unit_id=" + encodeURIComponent(unit);
            } else {
                url = base + "/tmon/v1/device/history?unit_id=" + encodeURIComponent(unit) + "&hours=" + encodeURIComponent(hours);
            }
            fetch(url).then(r=>r.json()).then(data=>{
                lastData = data;
                const pts = Array.isArray(data.points) ? data.points : [];
                const labels = pts.map(p=>p.t);
                const temp = pts.map(p=>p.temp_f);
                const humid = pts.map(p=>p.humid);
                const bar = pts.map(p=>p.bar);
                const volt = pts.map(p=>p.volt);
                // Relay state data
                const enabledRelays = Array.isArray(data.enabled_relays) ? data.enabled_relays : [];
                const relayColors = ["#6c757d", "#95a5a6", "#34495e", "#7f8c8d", "#95a5a6", "#2d3436", "#636e72", "#99a3ad"];
                const relayDatasets = enabledRelays.map(function(num, idx){
                    const values = pts.map(function(p){ 
                        var v = relayStateValue(p, num);
                        return (v === null || v === undefined) ? null : v;
                    });
                    return {label: "Relay " + num, data: values, borderColor: relayColors[idx % relayColors.length], borderDash: [6,3], fill:false, yAxisID: "relay", stepped:true, hidden:false};
                });
                const cfg = {
                    type: "line",
                    data: {
                        labels: labels,
                        datasets: [
                            {label: "Temp (F)", data: temp, borderColor: "#e67e22", fill:false, yAxisID: "y1"},
                            {label: "Humidity (%)", data: humid, borderColor: "#3498db", fill:false, yAxisID: "y2"},
                            {label: "Pressure (hPa)", data: bar, borderColor: "#2ecc71", fill:false, yAxisID: "y3"},
                            {label: "Voltage (V)", data: volt, borderColor: "#9b59b6", fill:false, yAxisID: "y4"}
                        ].concat(relayDatasets)
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
                            y4: { type: "linear", position: "left", grid: { drawOnChartArea: false }, suggestedMin: <?php echo $y4min; ?>, suggestedMax: <?php echo $y4max; ?> },
                            relay: { type: "linear", position: "right", min: -0.1, max: 1.1, grid: { drawOnChartArea: false }, ticks: { stepSize: 1, callback: v => v ? "On" : "Off" } }
                        }
                    }
                };
                if (chart) { chart.destroy(); }
                chart = new Chart(ctx, cfg);
            }).catch(err=>{ console.error("TMON history fetch error", err); });
        }
        function getCurrentUnit() { return select.value; }
        function getCurrentHours() { return hoursSel.value; }
        select.addEventListener("change", function(){ render(getCurrentUnit(), getCurrentHours()); });
        hoursSel.addEventListener("change", function(){ render(getCurrentUnit(), getCurrentHours()); });
        render(getCurrentUnit(), getCurrentHours());
        // CSV export
        csvBtn.addEventListener('click', function(){
            if (!lastData || !Array.isArray(lastData.points) || !lastData.points.length) {
                alert('No data to export.');
                return;
            }
            const pts = lastData.points;
            // Collect all keys
            let keys = new Set();
            pts.forEach(p => Object.keys(p).forEach(k => keys.add(k)));
            keys = Array.from(keys);
            let csv = keys.join(',') + '\n';
            pts.forEach(p => {
                csv += keys.map(k => (p[k] !== undefined ? JSON.stringify(p[k]) : '')).join(',') + '\n';
            });
            const blob = new Blob([csv], {type: 'text/csv'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'tmon_history_' + getCurrentUnit() + '_' + getCurrentHours() + '.csv';
            document.body.appendChild(a);
            a.click();
            setTimeout(()=>{ document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
        });
        // Optional: auto-refresh
        const refreshMs = <?php echo ($refresh*1000); ?>;
        if (refreshMs > 0) {
            setInterval(function(){ render(getCurrentUnit(), getCurrentHours()); }, refreshMs);
        }
    })();
    </script>
    <?php
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
        $out .= '<tr><td>'.esc_html($r['unit_id']).'</td><td>'.esc_html($r['unit_name']).'</td><td>'.esc_html(tmon_uc_format_mysql_datetime($r['last_seen'])).'</td></tr>';
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
             . '<td>' . esc_html(tmon_uc_format_mysql_datetime($r['last_seen'])) . '</td>'
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

// Fallback AJAX handler for pending commands count (if REST endpoint is not present)
add_action('wp_ajax_tmon_pending_commands_count', function() {
    if (!isset($_GET['unit_id'])) {
        wp_send_json(['count' => 0]);
    }
    global $wpdb;
    $unit = sanitize_text_field($_GET['unit_id']);
    $cnt = $wpdb->get_var($wpdb->prepare(
        "SELECT COUNT(*) FROM {$wpdb->prefix}tmon_device_commands WHERE device_id = %s AND executed_at IS NULL",
        $unit
    ));
    wp_send_json(['count' => intval($cnt)]);
});
add_action('wp_ajax_nopriv_tmon_pending_commands_count', function() {
    // Optionally allow non-logged-in users
    if (!isset($_GET['unit_id'])) {
        wp_send_json(['count' => 0]);
    }
    global $wpdb;
    $unit = sanitize_text_field($_GET['unit_id']);
    $cnt = $wpdb->get_var($wpdb->prepare(
        "SELECT COUNT(*) FROM {$wpdb->prefix}tmon_device_commands WHERE device_id = %s AND executed_at IS NULL",
        $unit
    ));
    wp_send_json(['count' => intval($cnt)]);
});

// AJAX: Update unit name
add_action('wp_ajax_tmon_uc_update_unit_name', function() {
    check_admin_referer('tmon_uc_device_data');
    if (!current_user_can('manage_options')) wp_send_json_error();
    $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
    $unit_name = sanitize_text_field($_POST['unit_name'] ?? '');
    global $wpdb;
    $wpdb->update($wpdb->prefix.'tmon_devices', ['unit_name'=>$unit_name], ['unit_id'=>$unit_id]);
    wp_send_json_success();
});

// AJAX: Get settings (applied/staged)
add_action('wp_ajax_tmon_uc_get_settings', function() {
    if (!current_user_can('manage_options')) wp_send_json_error();
    global $wpdb;
    $unit_id = sanitize_text_field($_GET['unit_id'] ?? '');
    $applied = [];
    $staged = [];
    $applied_source = 'none';
    $staged_source = 'none';

    // Applied from devices.settings (validate JSON)
    $row = $wpdb->get_row($wpdb->prepare("SELECT settings FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $unit_id), ARRAY_A);
    if ($row && !empty($row['settings'])) {
        $tmp = json_decode($row['settings'], true);
        if (json_last_error() === JSON_ERROR_NONE && is_array($tmp)) {
            $applied = $tmp;
            $applied_source = 'devices';
        }
    }

    // First attempt: staged table (validate JSON)
    $row2 = $wpdb->get_row($wpdb->prepare("SELECT settings FROM {$wpdb->prefix}tmon_staged_settings WHERE unit_id=%s", $unit_id), ARRAY_A);
    if ($row2 && !empty($row2['settings'])) {
        $tmp = json_decode($row2['settings'], true);
        if (json_last_error() === JSON_ERROR_NONE && is_array($tmp)) {
            $staged = $tmp;
            $staged_source = 'staged_table';
        }
    }

    // Fallback: try to read tmon-field-logs files for this unit (newest first)
    if (empty($staged)) {
        $log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
        if (is_dir($log_dir) && is_readable($log_dir)) {
            $safe_unit = preg_replace('/[^A-Za-z0-9._-]/', '', $unit_id);
            $files = [];
            // Prefer files named "field_data_unit-<unit>*" first (e.g. field_data_unit-3pd8sj.txt),
            // then append any other files that contain the unit id.
            $prefixPattern = $log_dir . '/field_data_unit-' . $safe_unit . '*';
            $prefFiles = glob($prefixPattern);
            if (!empty($prefFiles)) {
                $files = array_merge($files, $prefFiles);
            }
            $general = glob($log_dir . '/*' . $safe_unit . '*');
            if (!empty($general)) {
                foreach ($general as $f) {
                    if (!in_array($f, $files)) $files[] = $f;
                }
            }
            if (!empty($files)) {
                // prefer .txt files first (case-insensitive), then newest-first among equal preference
                usort($files, function($a, $b) {
                    $aTxt = preg_match('/\.txt$/i', $a) ? 0 : 1;
                    $bTxt = preg_match('/\.txt$/i', $b) ? 0 : 1;
                    if ($aTxt !== $bTxt) return $aTxt - $bTxt;
                    return filemtime($b) - filemtime($a);
                });

                // helper parser for .txt content: try JSON, embedded JSON, then key=value/key: value lines
                $parse_text_settings = function($content) {
                    // try whole-file JSON
                    $tmp = json_decode($content, true);
                    if (json_last_error() === JSON_ERROR_NONE && is_array($tmp)) return $tmp;

                    // extract last JSON object in file (if present)
                    if (preg_match_all('/\{[\s\S]*\}/', $content, $matches)) {
                        foreach (array_reverse($matches[0]) as $part) {
                            $tmp2 = json_decode($part, true);
                            if (json_last_error() === JSON_ERROR_NONE && is_array($tmp2)) return $tmp2;
                        }
                    }

                    // fallback: parse simple key=value or key: value lines into associative array
                    $lines = preg_split('/\r\n|\r|\n/', $content);
                    $kv = [];
                    foreach ($lines as $ln) {
                        $ln = trim($ln);
                        if ($ln === '' || strpos($ln, '#') === 0) continue;
                        if (preg_match('/^\s*([A-Za-z0-9_.-]+)\s*[:=]\s*(.+)$/', $ln, $m)) {
                            $k = $m[1];
                            $v = trim($m[2]);
                            // strip surrounding quotes
                            if ((substr($v,0,1) === '"' && substr($v,-1) === '"') || (substr($v,0,1) === "'" && substr($v,-1) === "'")) {
                                $v = substr($v,1,-1);
                            }
                            // cast numbers and booleans where obvious
                            if (is_numeric($v)) {
                                $v = $v + 0;
                            } else {
                                $lv = strtolower($v);
                                if (in_array($lv, ['true','false','on','off','yes','no','1','0'], true)) {
                                    if (in_array($lv, ['true','on','yes','1'], true)) $v = true;
                                    else $v = false;
                                }
                            }
                            $kv[$k] = $v;
                        }
                    }
                    return !empty($kv) ? $kv : null;
                };

                foreach ($files as $f) {
                    // prefer to use .txt files (we already sorted such that .txt come first)
                    $ext = pathinfo($f, PATHINFO_EXTENSION);

                    // try to read file lines (preferred) otherwise whole content
                    $lines = @file($f, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
                    if ($lines) {
                        // iterate lines in reverse (newest-first)
                        for ($i = count($lines) - 1; $i >= 0; $i--) {
                            $ln = trim($lines[$i]);
                            if ($ln === '') continue;

                            // If this line is JSON, decode it
                            $obj = null;
                            if (strpos($ln, '{') !== false) {
                                $obj = json_decode($ln, true);
                                if (json_last_error() !== JSON_ERROR_NONE) {
                                    if (preg_match('/\{[\s\S]*\}/', $ln, $m)) {
                                        $obj = json_decode($m[0], true);
                                        if (json_last_error() !== JSON_ERROR_NONE) $obj = null;
                                    } else {
                                        $obj = null;
                                    }
                                }
                            }

                            if (is_array($obj)) {
                                if (isset($obj['settings']) && is_array($obj['settings'])) {
                                    $staged = $obj['settings'];
                                    $staged_source = 'field_log';
                                    // If applied missing, use this as the applied settings as well.
                                    if (empty($applied)) { $applied = $staged; $applied_source = 'field_log'; }
                                    break 2;
                                }
                                // top-level object that looks like settings
                                $scalar_count = 0;
                                foreach ($obj as $k=>$v) { if (!is_array($v) && !is_object($v)) $scalar_count++; }
                                if ($scalar_count >= 1 && count($obj) <= 200) { $staged = $obj;
                                    $staged_source = 'field_log';
                                    if (empty($applied)) { $applied = $staged; $applied_source = 'field_log'; }
                                    break 2; }
                                continue;
                            }

                            // If file is .txt, attempt to parse key/value lines
                            if (strcasecmp($ext, 'txt') === 0 || preg_match('/\.txt$/i', $f)) {
                                $parsed = $parse_text_settings($ln);
                                if (is_array($parsed)) {
                                    $staged = $parsed;
                                    $staged_source = 'field_log';
                                    if (empty($applied)) { $applied = $staged; $applied_source = 'field_log'; }
                                    break 2;
                                }
                            }
                        }
                        continue;
                    }

                    // If file() failed, fall back to whole-file content handling
                    $content = @file_get_contents($f);
                    if ($content === false) continue;

                    // Give .txt parser first crack
                    if (preg_match('/\.txt$/i', $f)) {
                        $parsed = $parse_text_settings($content);
                        if (is_array($parsed)) {
                            $staged = $parsed;
                            $staged_source = 'field_log';
                            if (empty($applied)) { $applied = $staged; $applied_source = 'field_log'; }
                            break;
                        }
                    }

                    // existing heuristic: whole-file JSON or embedded JSON
                    $tmp = json_decode($content, true);
                    if (json_last_error() === JSON_ERROR_NONE && is_array($tmp)) { $staged = $tmp;
                        $staged_source = 'field_log';
                        if (empty($applied)) { $applied = $staged; $applied_source = 'field_log'; }
                        break; }
                    if (preg_match_all('/\{[\s\S]*?\}/', $content, $matches)) {
                        foreach (array_reverse($matches[0]) as $part) {
                            $tmp2 = json_decode($part, true);
                            if (json_last_error() === JSON_ERROR_NONE && is_array($tmp2)) {
                                // Prefer explicit settings key
                                if (isset($tmp2['settings']) && is_array($tmp2['settings'])) {
                                    $staged = $tmp2['settings']; $staged_source = 'field_log';
                                    if (empty($applied)) { $applied = $staged; $applied_source = 'field_log'; }
                                    break 2;
                                }
                                $staged = $tmp2; $staged_source = 'field_log';
                                if (empty($applied)) { $applied = $staged; $applied_source = 'field_log'; }
                                break 2;
                            }
                        }
                    }
                }
            }
        }
    }

    // If there was no explicit staged entry, expose the applied settings for editing (so user can edit current)
    if (empty($staged) && !empty($applied)) {
        $staged = $applied;
        $staged_source = $staged_source === 'none' ? 'derived_from_applied' : $staged_source;
    }

    // Provide pretty JSON for front-end editable textbox convenience
    $applied_json = (empty($applied) ? '' : json_encode($applied, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));
    $staged_json = (empty($staged) ? '' : json_encode($staged, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES));

    wp_send_json([
        'success' => true,
        'applied' => $applied,
        'staged' => $staged,
        'applied_json' => $applied_json,
        'staged_json' => $staged_json,
        'applied_source' => $applied_source,
        'staged_source' => $staged_source,
    ]);
});
// Note: we intentionally keep compatibility with existing consumers while also returning
// useful JSON strings and source info for front-end usage elsewhere (see comment above).

// AJAX: Stage settings
add_action('wp_ajax_tmon_uc_stage_settings', function() {
    check_admin_referer('tmon_uc_device_data');
    if (!current_user_can('manage_options')) wp_send_json_error();
    global $wpdb;
    $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
    $settings = $_POST['settings'] ?? '';
    $wpdb->replace($wpdb->prefix.'tmon_staged_settings', [
        'unit_id' => $unit_id,
        'settings' => $settings,
        'updated_at' => current_time('mysql', 1)
    ]);
    wp_send_json_success();
});

// AJAX: List pending commands for a unit
add_action('wp_ajax_tmon_pending_commands_list', function() {
    check_ajax_referer('tmon_pending_cmds');
    if (!isset($_GET['unit_id'])) wp_send_json_error(['commands'=>[]]);
    global $wpdb;
    $unit = sanitize_text_field($_GET['unit_id']);
    // Fetch ALL staged commands, including those with NULL or empty executed_at
    $rows = $wpdb->get_results($wpdb->prepare(
        "SELECT id, command, created_at, executed_at FROM {$wpdb->prefix}tmon_device_commands WHERE device_id = %s AND (executed_at IS NULL OR executed_at = '' OR executed_at = '0000-00-00 00:00:00') ORDER BY created_at ASC",
        $unit
    ), ARRAY_A);
    $out = [];
    foreach ($rows as $r) {
        $cmd = $r['command'];
        // Try to pretty-print JSON if possible
        if (is_string($cmd) && ($decoded = json_decode($cmd, true)) && json_last_error() === JSON_ERROR_NONE) {
            $cmd = json_encode($decoded, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
        }
        $out[] = [
            'id' => $r['id'],
            'command' => $cmd,
            'created_at' => $r['created_at'],
            'executed_at' => $r['executed_at']
        ];
    }
    wp_send_json_success(['commands' => $out]);
});
add_action('wp_ajax_nopriv_tmon_pending_commands_list', function() {
    wp_send_json_error(['commands'=>[]]);
});

// AJAX: Delete a pending command by id
add_action('wp_ajax_tmon_pending_commands_delete', function() {
    check_ajax_referer('tmon_pending_cmds');
    if (!isset($_POST['id'])) wp_send_json_error();
    global $wpdb;
    $id = intval($_POST['id']);
    $wpdb->delete($wpdb->prefix.'tmon_device_commands', ['id'=>$id, 'executed_at'=>null]);
    wp_send_json_success();
});
add_action('wp_ajax_nopriv_tmon_pending_commands_delete', function() {
    wp_send_json_error();
});

// AJAX: Get command by id for re-queue
add_action('wp_ajax_tmon_pending_commands_get', function() {
    check_ajax_referer('tmon_pending_cmds');
    if (!isset($_POST['id'])) wp_send_json_error();
    global $wpdb;
    $id = intval($_POST['id']);
    // Fix: Also select device_id for permission check
    $row = $wpdb->get_row($wpdb->prepare("SELECT command, device_id FROM {$wpdb->prefix}tmon_device_commands WHERE id=%d", $id), ARRAY_A);
    if ($row && isset($row['command'])) {
        // Optionally: check user permission for this device here if needed
        wp_send_json_success(['command' => $row['command'], 'device_id' => $row['device_id']]);
    }
    wp_send_json_error(['message' => 'Command not found']);
});

// AJAX: Re-queue a pending command (insert as new pending command)
add_action('wp_ajax_tmon_pending_commands_requeue', function() {
    check_ajax_referer('tmon_pending_cmds');
    if (!current_user_can('manage_options') && !current_user_can('edit_tmon_units')) wp_send_json_error();
    global $wpdb;
    $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
    $command = $_POST['command'] ?? '';
    if (!$unit_id || !$command) wp_send_json_error();
    $wpdb->insert($wpdb->prefix.'tmon_device_commands', [
        'device_id' => $unit_id,
        'command' => $command,
        'created_at' => current_time('mysql', 1),
        'executed_at' => null
    ]);
    wp_send_json_success();
});

// Utility: Ensure tmon_staged_settings table exists (auto-create if missing)
function tmon_uc_ensure_staged_settings_table() {
    global $wpdb;
    $table = $wpdb->prefix . 'tmon_staged_settings';
    $charset_collate = $wpdb->get_charset_collate();
    $sql = "CREATE TABLE IF NOT EXISTS `$table` (
        `unit_id` varchar(64) NOT NULL,
        `settings` longtext NOT NULL,
        `updated_at` datetime DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (`unit_id`)
    ) $charset_collate;";
    require_once(ABSPATH . 'wp-admin/includes/upgrade.php');
    dbDelta($sql);
}

// Ensure table exists on plugin load and before any staged settings access
add_action('init', 'tmon_uc_ensure_staged_settings_table');
add_action('admin_init', 'tmon_uc_ensure_staged_settings_table');
add_action('wp_ajax_tmon_uc_get_settings', 'tmon_uc_ensure_staged_settings_table', 0);
add_action('wp_ajax_tmon_uc_stage_settings', 'tmon_uc_ensure_staged_settings_table', 0);

