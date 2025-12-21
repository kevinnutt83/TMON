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
    $now = time(); // PHP time() is UTC; we compare against UTC timestamps
    $nonce = wp_create_nonce('tmon_uc_relay');
    foreach ($rows as $r) {
        // Convert MySQL DATETIME (stored in WP timezone) to an accurate UTC epoch
        $last = $r['last_seen'] ? tmon_uc_mysql_to_utc_timestamp($r['last_seen']) : 0;
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
            // Show site-local formatted time in tooltip and keep human_time_diff in UTC epoch space
            $title = 'Last seen: ' . tmon_uc_format_mysql_datetime($r['last_seen'], get_option('date_format') . ' ' . get_option('time_format')) . ' (' . human_time_diff($last, $now) . ' ago)';
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

// Shortcode to embed device settings form (alias for template inclusion)
// Keep canonical definition, guard to avoid redeclare.
if (!function_exists('tmon_device_settings_shortcode')) {
function tmon_device_settings_shortcode($atts = []) {
    ob_start();
    include plugin_dir_path(__FILE__) . '../templates/device-data.php';
    return ob_get_clean();
}
add_shortcode('tmon_device_settings', 'tmon_device_settings_shortcode');
}

// AJAX: save staged settings for a unit (admin only)
add_action('wp_ajax_tmon_uc_stage_device_settings', function(){
    if (!current_user_can('manage_options')) {
        wp_send_json_error('Forbidden');
    }
    if (!check_admin_referer('tmon_uc_stage_settings', '_wpnonce', false)) {
        // also accept older nonce field name for compatibility
        if (!isset($_POST['_wpnonce']) || !wp_verify_nonce($_POST['_wpnonce'], 'tmon_uc_stage_settings')) {
            wp_send_json_error('Invalid nonce');
        }
    }
    $unit = sanitize_text_field($_POST['unit_id'] ?? '');
    if (!$unit) wp_send_json_error('Missing unit_id');
    $raw = $_POST['settings'] ?? '{}';
    $settings_in = json_decode(wp_unslash($raw), true);
    if (!is_array($settings_in)) $settings_in = [];

    // Allowed keys (a minimal whitelist; server-side sanitization)
    $allowed = [
        'NODE_TYPE','UNIT_Name',
        'SAMPLE_TEMP','SAMPLE_HUMID','SAMPLE_BAR',
        'ENABLE_OLED',
        'ENGINE_ENABLED','ENGINE_FORCE_DISABLED',
        'WIFI_SSID','WIFI_PASS',
        'RELAY_PIN1','RELAY_PIN2'
    ];

    $out = [];
    foreach ($settings_in as $k => $v) {
        if (!in_array($k, $allowed, true)) continue;
        // sanitize by key
        switch ($k) {
            case 'NODE_TYPE':
            case 'UNIT_Name':
            case 'WIFI_SSID':
            case 'WIFI_PASS':
                $out[$k] = sanitize_text_field($v);
                break;
            case 'RELAY_PIN1':
            case 'RELAY_PIN2':
                $out[$k] = intval($v);
                break;
            case 'SAMPLE_TEMP':
            case 'SAMPLE_HUMID':
            case 'SAMPLE_BAR':
            case 'ENABLE_OLED':
            case 'ENGINE_ENABLED':
            case 'ENGINE_FORCE_DISABLED':
                // accept 0/1, true/false, "1"/"0"
                $out[$k] = (bool) filter_var($v, FILTER_VALIDATE_BOOLEAN, FILTER_NULL_ON_FAILURE);
                break;
            default:
                $out[$k] = sanitize_text_field($v);
        }
    }

    // persist to single option mapping unit_id -> staged settings
    $map = get_option('tmon_uc_staged_settings', []);
    if (!is_array($map)) $map = [];
    $map[$unit] = $out;
    update_option('tmon_uc_staged_settings', $map);
    wp_send_json_success('staged');
});

// AJAX: get staged settings for a unit (admin only)
add_action('wp_ajax_tmon_uc_get_staged_settings', function(){
    if (!current_user_can('manage_options')) {
        wp_send_json_error('Forbidden');
    }
    $unit = sanitize_text_field($_POST['unit_id'] ?? $_GET['unit_id'] ?? '');
    if (!$unit) wp_send_json_error('Missing unit_id');
    $map = get_option('tmon_uc_staged_settings', []);
    if (!is_array($map) || empty($map[$unit])) {
        wp_send_json_success([]); // empty staged settings
    } else {
        wp_send_json_success($map[$unit]);
    }
});