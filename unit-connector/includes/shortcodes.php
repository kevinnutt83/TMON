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
        // Convert stored UTC created_at -> site-local epoch and render display + ISO data attribute
        $created_site = '';
        $created_iso = '';
        $created_title = '';
        if (!empty($r['created_at'])) {
            $ts = function_exists('tmon_uc_mysql_to_local_timestamp') ? tmon_uc_mysql_to_local_timestamp($r['created_at']) : strtotime(get_date_from_gmt($r['created_at']));
            if ($ts) {
                $created_site = date_i18n(get_option('date_format') . ' ' . get_option('time_format'), $ts);
                $created_iso  = date_i18n(DATE_ISO8601, $ts);
                $created_title = 'Created: ' . $created_site . ' (' . human_time_diff($ts, current_time('timestamp')) . ' ago)';
            } else {
                $created_site = tmon_uc_format_mysql_datetime($r['created_at']);
                $created_iso = $r['created_at'];
                $created_title = 'Created: ' . $created_site;
            }
        }
        echo '<tr data-unit="'.esc_attr($r['device_id']).'" data-created="'.esc_attr($created_iso).'" title="'.esc_attr($created_title).'">'
            .'<td>'.esc_html($r['device_id']).'</td>'
            .'<td>'.esc_html($r['unit_name']).'</td>'
            .'<td>'.$cmd.'</td>'
            .'<td>'.esc_html($created_site).'</td>'
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
                    var msg = (res && res.data && res.data.message) ? res.data.message : (res && res.message ? res.message : 'Delete failed');
                    alert(msg);
                    btn.disabled = false;
                }
            }).catch(function(){
                alert('Network or server error deleting command');
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
                if (res && res.success && typeof res.command !== "undefined") {
                    var unit_id = res.device_id || unit;
                    var cmd = res.command;
                    if (typeof cmd === "object") cmd = JSON.stringify(cmd);
                    if (typeof cmd === "string") cmd = cmd.trim();
                    fetch(ajaxurl + "?action=tmon_pending_commands_requeue", {
                        method: "POST",
                        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                        body: "unit_id=" + encodeURIComponent(unit_id) + "&command=" + encodeURIComponent(cmd) + "&_wpnonce=" + nonce
                    }).then(r2=>r2.json()).then(function(res2){
                        if (res2 && res2.success) {
                            alert('Command re-queued.');
                        } else {
                            var msg = (res2 && res2.data && res2.data.message) ? res2.data.message : (res2 && res2.message ? res2.message : 'Re-queue failed');
                            alert(msg);
                        }
                        btn.disabled = false;
                    }).catch(function(){
                        alert('Network or server error re-queuing command');
                        btn.disabled = false;
                    });
                } else {
                    var msg = (res && res.data && res.data.message) ? res.data.message : (res && res.message ? res.message : 'Could not fetch command for re-queue.');
                    alert(msg);
                    btn.disabled = false;
                }
            }).catch(function(){
                alert('Could not fetch command for re-queue.');
                btn.disabled = false;
            });
        });
        // Polling logic
        var last_filter = '';
        function refreshTable() {
            var filter = select.value;
            fetch(ajaxurl + "?action=tmon_pending_commands_refresh&_wpnonce=" + nonce)
                .then(r=>r.json())
                .then(function(res){
                    if (res && res.success && res.html) {
                        table.tBodies[0].innerHTML = res.html;
                        // Reapply filter
                        if (filter && filter !== 'all') {
                            Array.from(table.tBodies[0].rows).forEach(function(row){
                                if (row.getAttribute('data-unit') === filter) {
                                    row.style.display = '';
                                } else {
                                    row.style.display = 'none';
                                }
                            });
                        }
                    }
                })
                .catch(function(err){
                    console.error('Polling error:', err);
                });
        }
        setInterval(refreshTable, 30000); // 30 seconds
    })();
    </script>
    <?php
    return ob_get_clean();
});

// Dashboard widget to summarize pending commands
add_action('wp_dashboard_setup', function(){
    wp_add_dashboard_widget('tmon_cmd_summary', 'TMON Command Summary', function(){
        global $wpdb;
        // Include last created timestamp per device (UTC stored -> format to site-local)
        $rows = $wpdb->get_results("SELECT device_id, COUNT(*) as pending, MAX(created_at) as last_created FROM {$wpdb->prefix}tmon_device_commands WHERE executed_at IS NULL GROUP BY device_id ORDER BY pending DESC LIMIT 10", ARRAY_A);
        echo '<table id="tmon-cmd-summary-table" class="widefat"><thead><tr><th>Unit</th><th>Pending</th><th>Last Created</th></tr></thead><tbody>';
        foreach ($rows as $r) {
            $last = '';
            $last_iso = '';
            if (!empty($r['last_created'])) {
                $ts = function_exists('tmon_uc_mysql_to_local_timestamp') ? tmon_uc_mysql_to_local_timestamp($r['last_created']) : strtotime(get_date_from_gmt($r['last_created']));
                if ($ts) {
                    $last = esc_html( date_i18n(get_option('date_format') . ' ' . get_option('time_format'), $ts) );
                    $last_iso = esc_attr( date_i18n(DATE_ISO8601, $ts) );
                } else {
                    $last = esc_html($r['last_created']);
                    $last_iso = esc_attr($r['last_created']);
                }
            }
            echo '<tr data-last-created="'. $last_iso .'"><td>'.esc_html($r['device_id']).'</td><td>'.intval($r['pending']).'</td><td>'.$last.'</td></tr>';
        }

        if (empty($rows)) echo '<tr><td colspan="3"><em>No pending commands</em></td></tr>';
        echo '</tbody></table>';
        // Auto-refresh widget body (admin only)
        $widget_nonce = wp_create_nonce('tmon_pending_cmds');
        $ajaxurl = esc_js(admin_url('admin-ajax.php'));
        echo "<script>
        (function(){
            var tbl = document.getElementById('tmon-cmd-summary-table');
            if (!tbl) return;
            function refresh(){
                fetch('{$ajaxurl}?action=tmon_pending_commands_summary_refresh&_wpnonce={$widget_nonce}')
                    .then(r=>r.json()).then(function(res){
                        if (res && res.success && res.data && res.data.html) {
                            var tb = tbl.tBodies[0];
                            if (tb) tb.innerHTML = res.data.html;
                        }
                    }).catch(function(e){ console.error('summary refresh error', e); });
            }
            // initial refresh and periodic
            refresh();
            setInterval(refresh, 30000);
        })();
        </script>";
    });
});

// [tmon_pending_commands_summary]
// Outputs a table summarizing pending commands per device, similar to the dashboard widget
add_shortcode('tmon_pending_commands_summary', function($atts){
    global $wpdb;
    $refresh_s = isset($atts['refresh_s']) ? max(5, intval($atts['refresh_s'])) : 30;
    // Include last created timestamp per device and format to site-local
    $rows = $wpdb->get_results("SELECT device_id, COUNT(*) as pending, MAX(created_at) as last_created FROM {$wpdb->prefix}tmon_device_commands WHERE executed_at IS NULL GROUP BY device_id ORDER BY pending DESC LIMIT 10", ARRAY_A);
    $table_id = 'tmon-pending-summary-' . wp_generate_password(6,false,false);
    $nonce = wp_create_nonce('tmon_pending_cmds');
    $ajaxurl = esc_js(admin_url('admin-ajax.php'));
    $out = '<table id="'.esc_attr($table_id).'" class="widefat"><thead><tr><th>Unit</th><th>Pending</th><th>Last Created</th></tr></thead><tbody>';
    foreach ($rows as $r) {
        $last = '';
        $last_iso = '';
        if (!empty($r['last_created'])) {
            $ts = function_exists('tmon_uc_mysql_to_local_timestamp') ? tmon_uc_mysql_to_local_timestamp($r['last_created']) : strtotime(get_date_from_gmt($r['last_created']));
            if ($ts) {
                $last = esc_html( date_i18n(get_option('date_format') . ' ' . get_option('time_format'), $ts) );
                $last_iso = esc_attr( date_i18n(DATE_ISO8601, $ts) );
            } else {
                $last = esc_html($r['last_created']);
                $last_iso = esc_attr($r['last_created']);
            }
        }
        $out .= '<tr data-last-created="'.$last_iso.'"><td>'.esc_html($r['device_id']).'</td><td>'.intval($r['pending']).'</td><td>'.$last.'</td></tr>';
    }
    if (empty($rows)) $out .= '<tr><td colspan="3"><em>No pending commands</em></td></tr>';
    $out .= '</tbody></table>';
    // Inline JS to auto-refresh the summary table
    $out .= '<script>(function(){var t=document.getElementById("'.esc_js($table_id).'"); if(!t) return; function r(){ fetch("'.$ajaxurl.'?action=tmon_pending_commands_summary_refresh&_wpnonce='.$nonce.'").then(r=>r.json()).then(function(s){ if(s && s.success && s.data && s.data.html){ t.tBodies[0].innerHTML = s.data.html; } }).catch(e=>console.error("summary refresh",e)); } r(); setInterval(r,'.intval($refresh_s*1000).');})();</script>';
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
    echo '<table id="tmon-device-status-table" class="wp-list-table widefat"><thead><tr><th>Status</th><th>Unit ID</th><th>Name</th><th>Last Seen</th><th>Controls</th></tr></thead><tbody>';
    // Use WP site-local timestamp and convert stored DATETIME to site-local timestamps for consistent comparison
    $now = current_time('timestamp');
    $nonce = wp_create_nonce('tmon_uc_relay');
    foreach ($rows as $r) {
        // Convert MySQL DATETIME (stored in WP/site timezone) to a site-local Unix timestamp for comparison
        $last = $r['last_seen'] ? tmon_uc_mysql_to_local_timestamp($r['last_seen']) : 0;

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
            // Show site-local formatted time in tooltip and keep human_time_diff in site-local epoch space
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
    $status_nonce = wp_create_nonce('tmon_uc_relay');
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
        // Auto-refresh device status tbody periodically (admin context)
        (function(){
            var tbl = document.getElementById("tmon-device-status-table");
            if (!tbl) return;
            function refreshStatus(){
                fetch("'.esc_js($ajax_url).'?action=tmon_device_status_refresh&_wpnonce='.$status_nonce.'")
                    .then(r=>r.json()).then(function(res){
                        if (res && res.success && res.data && res.data.html){
                            var tb = tbl.tBodies[0];
                            if (tb) tb.innerHTML = res.data.html;
                        }
                    }).catch(function(e){ console.error("status refresh", e); });
            }
            refreshStatus();
            setInterval(refreshStatus, 30000);
        })();
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
		const localSelect = document.getElementById("<?php echo esc_js($select_id); ?>");
		const hoursSel    = document.getElementById("<?php echo esc_js($hours_id); ?>");
		const csvBtn      = document.getElementById("<?php echo esc_js($csv_btn_id); ?>");
		const canvas      = document.getElementById("<?php echo esc_js($canvas_id); ?>");
		if (!localSelect || !canvas) return;

		// Use page-level picker when present to avoid duplicate selectors in device template.
		const externalSelect = document.getElementById('tmon-unit-picker');
		if (externalSelect) { try { localSelect.style.display = 'none'; } catch(e){} }
		const select = externalSelect || localSelect;

		const ctx = canvas.getContext('2d');
		const base = (window.wp && wp.apiSettings && wp.apiSettings.root) ? wp.apiSettings.root.replace(/\/$/, "") : "<?php echo $ajax_root; ?>".replace(/\/$/, "");
        const legendKey = "tmon_history_legend_" + (canvas.id || "default");
		let chart = null;
		let lastData = null;

        function getCookie(name) {
            try {
                const needle = name + "=";
                const parts = document.cookie ? document.cookie.split(';') : [];
                for (let i = 0; i < parts.length; i++) {
                    const c = parts[i].trim();
                    if (c.indexOf(needle) === 0) {
                        return decodeURIComponent(c.substring(needle.length));
                    }
                }
            } catch(e) {}
            return null;
        }

        function setCookie(name, value, days) {
            try {
                const maxAge = Math.max(1, Number(days || 30)) * 24 * 60 * 60;
                document.cookie = name + "=" + encodeURIComponent(value) + "; path=/; max-age=" + maxAge + "; SameSite=Lax";
            } catch(e) {}
        }

        function loadLegendState() {
            try {
                const cookieRaw = getCookie(legendKey);
                if (cookieRaw) return JSON.parse(cookieRaw);
            } catch(e) {}
            try {
                // Backward compatibility with prior localStorage-only persistence.
                const raw = localStorage.getItem(legendKey);
                return raw ? JSON.parse(raw) : {};
            } catch(e) {
                return {};
            }
        }

        function collectLegendState(input) {
            const state = {};
            if (!input) return state;
            if (input.data && Array.isArray(input.data.datasets) && typeof input.isDatasetVisible === 'function') {
                input.data.datasets.forEach(function(d, i){
                    if (d && d.label) state[d.label] = !input.isDatasetVisible(i);
                });
                return state;
            }
            (input || []).forEach(function(d){
                if (d && d.label) state[d.label] = !!d.hidden;
            });
            return state;
        }

        function saveLegendState(input) {
            try {
                const state = collectLegendState(input);
                setCookie(legendKey, JSON.stringify(state), 30);
                localStorage.setItem(legendKey, JSON.stringify(state));
            } catch(e) {}
        }

		// Robust relay value extraction (top-level keys and nested p.relay)
		function relayStateValue(pt, num) {
			if (!pt) return null;
			const keys = [`relay${num}_on`, `relay_${num}_on`, `relay${num}`, `relay_${num}`, `r${num}`];
			for (const k of keys) {
				if (Object.prototype.hasOwnProperty.call(pt, k)) {
					const v = pt[k];
					if (typeof v === 'boolean') return v ? 1 : 0;
					if (typeof v === 'number' ) return v;
					if (typeof v === 'string') {
						const lv = v.trim().toLowerCase();
						if (['1','true','on','yes'].includes(lv)) return 1;
						if (['0','false','off','no'].includes(lv)) return 0;
						const nv = Number(v);
						return isNaN(nv) ? null : nv;
					}
				}
			}
			if (pt && typeof pt.relay === 'object') {
				for (const k of Object.keys(pt.relay)) {
					let m = k.match(/^relay[_]?(\d+)_?on$/i) || k.match(/^relay[_]?(\d+)$/i) || k.match(/^r(\d+)$/i);
					if (m && Number(m[1]) === num) {
						const v = pt.relay[k];
						if (typeof v === 'boolean') return v ? 1 : 0;
						if (typeof v === 'number' ) return v;
						if (typeof v === 'string') {
							const lv = v.trim().toLowerCase();
							if (['1','true','on','yes'].includes(lv)) return 1;
							if (['0','false','off','no'].includes(lv)) return 0;
							const nv = Number(v);
							return isNaN(nv) ? null : nv;
						}
					}
				}
			}
			return null;
		}

		// Infer relay channel numbers from point keys when server doesn't return enabled_relays
		function detectRelaysFromPoints(pts) {
			const nums = new Set();
			(pts || []).forEach(p => {
				Object.keys(p || {}).forEach(k => {
					let m = k.match(/^relay[_]?(\d+)_?on$/i) || k.match(/^relay[_]?(\d+)$/i) || k.match(/^r(\d+)$/i);
					if (m) nums.add(parseInt(m[1], 10));
				});
				if (p && typeof p.relay === 'object') {
					Object.keys(p.relay).forEach(k => {
						let m = k.match(/^relay[_]?(\d+)_?on$/i) || k.match(/^relay[_]?(\d+)$/i) || k.match(/^r(\d+)$/i);
						if (m) nums.add(parseInt(m[1], 10));
					});
				}
			});
			return Array.from(nums).sort((a,b)=>a-b);
		}

		function render(unit, hours) {
			if (!unit) return;
			const url = (hours === 'yoy')
				? (base + "/tmon/v1/device/history-yoy?unit_id=" + encodeURIComponent(unit))
				: (base + "/tmon/v1/device/history?unit_id=" + encodeURIComponent(unit) + "&hours=" + encodeURIComponent(hours));
			fetch(url).then(r=>r.json()).then(data=>{
				lastData = data;
				const pts = Array.isArray(data.points) ? data.points : [];
				const labels = pts.map(p=>p.t || '');
				const temp = pts.map(p => (p && typeof p.temp_f !== 'undefined') ? p.temp_f : null);
				const humid = pts.map(p => (p && typeof p.humid !== 'undefined') ? p.humid : null);
				const bar = pts.map(p => (p && typeof p.bar !== 'undefined') ? p.bar : null);
				const volt = pts.map(p => (p && typeof p.volt !== 'undefined') ? p.volt : null);
				const devTemp = pts.map(p => (p && typeof p.device_temp_f !== 'undefined') ? p.device_temp_f : null);
				const devHumid = pts.map(p => (p && typeof p.device_humid !== 'undefined') ? p.device_humid : null);
				const devBar = pts.map(p => (p && typeof p.device_bar !== 'undefined') ? p.device_bar : null);
				const soilMoisture = pts.map(p => (p && typeof p.soil_moisture !== 'undefined') ? p.soil_moisture : null);
                const lowTempF = pts.map(p => (p && Object.prototype.hasOwnProperty.call(p, 'lowest_temp_f')) ? p.lowest_temp_f : null);
                const highTempF = pts.map(p => (p && Object.prototype.hasOwnProperty.call(p, 'highest_temp_f')) ? p.highest_temp_f : null);
                const lowBar = pts.map(p => (p && Object.prototype.hasOwnProperty.call(p, 'lowest_bar')) ? p.lowest_bar : null);
                const highBar = pts.map(p => (p && Object.prototype.hasOwnProperty.call(p, 'highest_bar')) ? p.highest_bar : null);
                const lowHumid = pts.map(p => (p && Object.prototype.hasOwnProperty.call(p, 'lowest_humid')) ? p.lowest_humid : null);
                const highHumid = pts.map(p => (p && Object.prototype.hasOwnProperty.call(p, 'highest_humid')) ? p.highest_humid : null);

				const relayNums = Array.isArray(data.enabled_relays) && data.enabled_relays.length ? data.enabled_relays : detectRelaysFromPoints(pts);
				const relayColors = ["#6c757d","#95a5a6","#34495e","#7f8c8d","#95a5a6","#2d3436","#636e72","#99a3ad"];
                const relayDatasets = relayNums.map((num, idx) => {
                    const values = pts.map(p => relayStateValue(p, num));
                    return {
                        label: "Relay " + num,
                        data: values,
                        borderColor: relayColors[idx % relayColors.length],
                        borderDash: [6,3],
                        fill: false,
                        yAxisID: "relay",
                        stepped: true,
                        pointRadius: 0,
                        // ensure boolean numeric values so legend toggling behaves predictably
                        spanGaps: true
                    };
                });

                const datasets = [
                    { label: "Probe Temp (F)", data: temp, borderColor: "#e67e22", fill:false, yAxisID: "y1", pointRadius: 0, cubicInterpolationMode: 'monotone' },
                    { label: "Device Temp (F)", data: devTemp, borderColor: "#d35400", borderDash: [4,2], fill:false, yAxisID: "y1", pointRadius: 0, cubicInterpolationMode: 'monotone' },
                    { label: "Lowest Temp (F)", data: lowTempF, borderColor: "#f5b041", borderDash: [3,3], fill:false, yAxisID: "y1", pointRadius: 0, cubicInterpolationMode: 'monotone', hidden: true },
                    { label: "Highest Temp (F)", data: highTempF, borderColor: "#af601a", borderDash: [3,3], fill:false, yAxisID: "y1", pointRadius: 0, cubicInterpolationMode: 'monotone', hidden: true },
                    { label: "Probe Humidity (%)", data: humid, borderColor: "#3498db", fill:false, yAxisID: "y2", pointRadius: 0, cubicInterpolationMode: 'monotone' },
                    { label: "Device Humidity (%)", data: devHumid, borderColor: "#2980b9", borderDash: [4,2], fill:false, yAxisID: "y2", pointRadius: 0, cubicInterpolationMode: 'monotone' },
                    { label: "Lowest Humidity (%)", data: lowHumid, borderColor: "#5dade2", borderDash: [3,3], fill:false, yAxisID: "y2", pointRadius: 0, cubicInterpolationMode: 'monotone', hidden: true },
                    { label: "Highest Humidity (%)", data: highHumid, borderColor: "#1f618d", borderDash: [3,3], fill:false, yAxisID: "y2", pointRadius: 0, cubicInterpolationMode: 'monotone', hidden: true },
                    { label: "Probe Pressure (hPa)", data: bar, borderColor: "#2ecc71", fill:false, yAxisID: "y3", pointRadius: 0, cubicInterpolationMode: 'monotone' },
                    { label: "Device Pressure (hPa)", data: devBar, borderColor: "#27ae60", borderDash: [4,2], fill:false, yAxisID: "y3", pointRadius: 0, cubicInterpolationMode: 'monotone' },
                    { label: "Lowest Pressure (hPa)", data: lowBar, borderColor: "#58d68d", borderDash: [3,3], fill:false, yAxisID: "y3", pointRadius: 0, cubicInterpolationMode: 'monotone', hidden: true },
                    { label: "Highest Pressure (hPa)", data: highBar, borderColor: "#1e8449", borderDash: [3,3], fill:false, yAxisID: "y3", pointRadius: 0, cubicInterpolationMode: 'monotone', hidden: true },
                    { label: "Voltage (V)", data: volt, borderColor: "#9b59b6", fill:false, yAxisID: "y4", pointRadius: 0, cubicInterpolationMode: 'monotone' },
                    { label: "Soil Moisture", data: soilMoisture, borderColor: "#795548", fill:false, yAxisID: "y2", pointRadius: 0, cubicInterpolationMode: 'monotone' }
                ].concat(relayDatasets);

                const persistedLegend = Object.assign({}, loadLegendState(), collectLegendState(chart));
                datasets.forEach(function(ds){
                    if (ds && ds.label && Object.prototype.hasOwnProperty.call(persistedLegend, ds.label)) {
                        ds.hidden = !!persistedLegend[ds.label];
                    }
                });

                // Config for initial creation
                const cfg = {
                    type: "line",
                    data: { labels: labels, datasets: datasets },
                    options: {
                        responsive: true,
                        animation: { duration: 600, easing: 'linear' },
                        interaction: { mode: "index", intersect: false },
                        plugins: {
                            legend: {
                                position: "top",
                                labels: { usePointStyle: true },
                                onClick: function(e, legendItem, legend) {
                                    const ci = legend.chart;
                                    const idx = legendItem.datasetIndex;
                                    const meta = ci.getDatasetMeta(idx);
                                    meta.hidden = meta.hidden === null ? !ci.data.datasets[idx].hidden : null;
                                    ci.update();
                                    saveLegendState(ci);
                                }
                            }
                        },
                        elements: { line: { tension: 0.25 }, point: { radius: 0 } },
                        scales: {
                            y1: { type: "linear", position: "left" },
                            y2: { type: "linear", position: "right", grid: { drawOnChartArea: false } },
                            y3: { type: "linear", position: "right", grid: { drawOnChartArea: false } },
                            y4: { type: "linear", position: "left", grid: { drawOnChartArea: false }, suggestedMin: <?php echo $y4min; ?>, suggestedMax: <?php echo $y4max; ?> },
                            relay: { type: "linear", position: "right", min: -0.1, max: 1.1, grid: { drawOnChartArea: false }, ticks: { stepSize: 1, callback: v => (v? 'On':'Off') } }
                        }
                    }
                };

                // Update existing chart in place to enable smooth shifting animation
                if (chart) {
                    chart.data.labels = labels;
                    chart.data.datasets = datasets;
                    chart.update('active'); // animate the transition
                    saveLegendState(chart);
                } else {
                    chart = new Chart(ctx, cfg);
                    saveLegendState(chart);
                }
            }).catch(err=>{
                console.error("TMON history fetch error", err);
                // keep UI subtle: don't throw alerts on network errors; attempt to console log
            });
        }

        function getCurrentUnit(){ return select.value; }
		function getCurrentHours(){ return hoursSel.value; }

		// Listen to page-level picker when present so graph follows page controls
		if (externalSelect) externalSelect.addEventListener('change', function(){ render(getCurrentUnit(), getCurrentHours()); });
		select.addEventListener('change', function(){ render(getCurrentUnit(), getCurrentHours()); });
		hoursSel.addEventListener('change', function(){ render(getCurrentUnit(), getCurrentHours()); });

		render(getCurrentUnit(), getCurrentHours());

		// CSV export (unchanged behavior)
		csvBtn.addEventListener('click', function(){
			if (!lastData || !Array.isArray(lastData.points) || !lastData.points.length) { alert('No data to export.'); return; }
			const pts = lastData.points;
			let keys = new Set();
			pts.forEach(p => Object.keys(p || {}).forEach(k => keys.add(k)));
			keys = Array.from(keys);
			let csv = keys.join(',') + '\n';
			pts.forEach(p => {
				csv += keys.map(k => (p[k] !== undefined ? JSON.stringify(p[k]) : '')).join(',') + '\n';
			});
			const blob = new Blob([csv], {type: 'text/csv'});
			const url = URL.createObjectURL(blob);
			const a = document.createElement('a'); a.href = url; a.download = 'tmon_history_' + getCurrentUnit() + '_' + getCurrentHours() + '.csv';
			document.body.appendChild(a); a.click(); setTimeout(()=>{ document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
		});

		// Optional: auto-refresh
		const refreshMs = <?php echo ($refresh*1000); ?>;
		if (refreshMs > 0) setInterval(function(){ render(getCurrentUnit(), getCurrentHours()); }, refreshMs);
	})();
    </script>
    <?php
    echo '</div>';
    return ob_get_clean();
});

// [tmon_frost_heat_watch refresh_s="30"]
// Shows frost/heat watch status and low/high probe ranges for the selected unit.
add_shortcode('tmon_frost_heat_watch', function($atts) {
    $a = shortcode_atts([
        'refresh_s' => '30',
    ], $atts);
    $refresh = max(0, intval($a['refresh_s']));
    $devices = tmon_uc_list_feature_devices('sample');
    if (empty($devices)) {
        return '<em>No provisioned devices found for this feature.</em>';
    }

    $default_unit = $devices[0]['unit_id'];
    $select_id = 'tmon-watch-select-' . wp_generate_password(6, false, false);
    $box_id = 'tmon-watch-box-' . wp_generate_password(6, false, false);
    $ajax_root = esc_js(rest_url());

    ob_start();
    echo '<div class="tmon-watch-widget">';
    echo '<label class="screen-reader-text" for="'.$select_id.'">Device</label>';
    echo '<select id="'.$select_id.'" class="tmon-watch-select">';
    foreach ($devices as $d) {
        $sel = selected($default_unit, $d['unit_id'], false);
        echo '<option value="'.esc_attr($d['unit_id']).'" '.$sel.'>'.esc_html($d['label']).'</option>';
    }
    echo '</select>';
    echo '<div id="'.$box_id.'" style="margin-top:8px;"><em>Loading...</em></div>';
    echo '<style>
    .tmon-watch-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;margin-top:8px}
    .tmon-watch-card{border:1px solid #dcdcde;border-radius:8px;padding:8px;background:#fff}
    .tmon-watch-k{font-size:12px;color:#50575e}
    .tmon-watch-v{font-size:16px;font-weight:600}
    .tmon-watch-pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px}
    .tmon-watch-on{background:#fbeaea;color:#8a2424}
    .tmon-watch-off{background:#eaf7ee;color:#1f6b37}
    </style>';
    $watch_script = <<<'JS'
(function(){
    var localSelect = document.getElementById("%SELECT_ID%");
    var external = document.getElementById("tmon-unit-picker");
    if (external) { try { localSelect.style.display = "none"; } catch(e){} }
    var select = external || localSelect;
    var box = document.getElementById("%BOX_ID%");
    var base = (window.wp && wp.apiSettings && wp.apiSettings.root) ? wp.apiSettings.root.replace(/\/$/, "") : "%AJAX_ROOT%".replace(/\/$/, "");

    function truthy(v){
        if (typeof v === 'boolean') return v;
        if (typeof v === 'number') return v !== 0;
        if (typeof v === 'string') {
            var s = v.trim().toLowerCase();
            return ['1','true','yes','on','active'].indexOf(s) >= 0;
        }
        return false;
    }

    function pick(obj, keys){
        for (var i = 0; i < keys.length; i++) {
            var k = keys[i];
            if (obj && Object.prototype.hasOwnProperty.call(obj, k)) return obj[k];
        }
        return null;
    }

    function fmt(v){
        if (v === null || typeof v === 'undefined' || v === '') return 'N/A';
        return String(v);
    }

    function statePill(active){
        return active
            ? '<span class="tmon-watch-pill tmon-watch-on">ACTIVE</span>'
            : '<span class="tmon-watch-pill tmon-watch-off">INACTIVE</span>';
    }

    function render(unit){
        if (!unit) { box.innerHTML = '<em>Select a unit.</em>'; return; }
        fetch(base + "/tmon/v1/device/sdata?unit_id=" + encodeURIComponent(unit))
            .then(function(r){ return r.json(); })
            .then(function(resp){
                var d = (resp && resp.data) ? resp.data : {};
                var frostActive = truthy(pick(d, ['frostwatch_active']));
                var heatActive = truthy(pick(d, ['heatwatch_active']));
                var lowTemp = pick(d, ['lowest_temp_f']);
                var highTemp = pick(d, ['highest_temp_f']);
                var lowBar = pick(d, ['lowest_bar']);
                var highBar = pick(d, ['highest_bar']);
                var lowHumid = pick(d, ['lowest_humid']);
                var highHumid = pick(d, ['highest_humid']);

                box.innerHTML = '' +
                    '<div class="tmon-watch-grid">' +
                        '<div class="tmon-watch-card"><div class="tmon-watch-k">Frostwatch</div><div class="tmon-watch-v">' + statePill(frostActive) + '</div></div>' +
                        '<div class="tmon-watch-card"><div class="tmon-watch-k">Heatwatch</div><div class="tmon-watch-v">' + statePill(heatActive) + '</div></div>' +
                        '<div class="tmon-watch-card"><div class="tmon-watch-k">Lowest Temp (F)</div><div class="tmon-watch-v">' + fmt(lowTemp) + '</div></div>' +
                        '<div class="tmon-watch-card"><div class="tmon-watch-k">Highest Temp (F)</div><div class="tmon-watch-v">' + fmt(highTemp) + '</div></div>' +
                        '<div class="tmon-watch-card"><div class="tmon-watch-k">Lowest Pressure (hPa)</div><div class="tmon-watch-v">' + fmt(lowBar) + '</div></div>' +
                        '<div class="tmon-watch-card"><div class="tmon-watch-k">Highest Pressure (hPa)</div><div class="tmon-watch-v">' + fmt(highBar) + '</div></div>' +
                        '<div class="tmon-watch-card"><div class="tmon-watch-k">Lowest Humidity (%)</div><div class="tmon-watch-v">' + fmt(lowHumid) + '</div></div>' +
                        '<div class="tmon-watch-card"><div class="tmon-watch-k">Highest Humidity (%)</div><div class="tmon-watch-v">' + fmt(highHumid) + '</div></div>' +
                    '</div>';
            })
            .catch(function(){
                box.innerHTML = '<em>Error loading frost/heat watch data.</em>';
            });
    }

    select.addEventListener('change', function(){ render(select.value); });
    render(select.value);
    var refreshMs = %REFRESH_MS%;
    if (refreshMs > 0) {
        setInterval(function(){ render(select.value); }, refreshMs);
    }
})();
JS;
    $watch_script = str_replace(
        ['%SELECT_ID%', '%BOX_ID%', '%AJAX_ROOT%', '%REFRESH_MS%'],
        [esc_js($select_id), esc_js($box_id), esc_js(rest_url()), ($refresh * 1000)],
        $watch_script
    );
    echo '<script>'.$watch_script.'</script>';
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
    $out = '<table class="wp-list-table widefat"><thead><tr><th>Unit</th><th>Name</th><th>Last Seen</th><th>Device Temp (F)</th><th>Device Humidity (%)</th><th>Device Pressure (hPa)</th><th>Voltage (V)</th><th>Soil Moisture</th></tr></thead><tbody>';
    foreach ($rows as $r) {
        $fd = $wpdb->get_row($wpdb->prepare("SELECT data, created_at FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s ORDER BY created_at DESC LIMIT 1", $r['unit_id']), ARRAY_A);
        $device_temp = $device_humid = $device_bar = $volt = $soil = '';
        if ($fd) {
            $d = json_decode($fd['data'], true);
            if (is_array($d)) {
                $device_temp = $d['cur_device_temp_f'] ?? '';
                $device_humid = $d['cur_device_humid'] ?? '';
                $device_bar = $d['cur_device_bar_pres'] ?? '';
                $volt = $d['v'] ?? ($d['sys_voltage'] ?? '');
                $soil = $d['cur_soil_moisture'] ?? '';
            }
        }
        $out .= '<tr>'
            .'<td>'.esc_html($r['unit_id']).'</td>'
            .'<td>'.esc_html($r['unit_name']).'</td>'
            .'<td>'.esc_html($r['last_seen']).'</td>'
            .'<td>'.esc_html($device_temp).'</td>'
            .'<td>'.esc_html($device_humid).'</td>'
            .'<td>'.esc_html($device_bar).'</td>'
            .'<td>'.esc_html($volt).'</td>'
            .'<td>'.esc_html($soil).'</td>'
            .'</tr>';
    }
    $out .= '</tbody></table>';
    return $out;
});

// [tmon_device_widgets limit="12"]
// Compact telemetry widgets for quick fleet visibility.
add_shortcode('tmon_device_widgets', function($atts){
    global $wpdb;
    $a = shortcode_atts(['limit' => '12'], $atts);
    $limit = max(1, min(50, intval($a['limit'])));

    $devices = $wpdb->get_results("SELECT unit_id, unit_name, last_seen, suspended FROM {$wpdb->prefix}tmon_devices ORDER BY last_seen DESC LIMIT {$limit}", ARRAY_A);
    if (!$devices) {
        return '<em>No devices found.</em>';
    }

    $now = current_time('timestamp');
    $online = 0;
    $warning = 0;
    $offline = 0;
    $cards = [];

    foreach ($devices as $d) {
        $uid = (string) ($d['unit_id'] ?? '');
        $name = (string) ($d['unit_name'] ?? $uid);
        $last_seen = (string) ($d['last_seen'] ?? '');
        $last_ts = $last_seen ? tmon_uc_mysql_to_local_timestamp($last_seen) : 0;
        $age = $last_ts ? max(0, $now - $last_ts) : PHP_INT_MAX;
        $status = 'offline';
        if (intval($d['suspended'] ?? 0)) {
            $status = 'suspended';
            $offline++;
        } elseif ($age <= 15 * 60) {
            $status = 'online';
            $online++;
        } elseif ($age <= 30 * 60) {
            $status = 'warning';
            $warning++;
        } else {
            $offline++;
        }

        $fd = $wpdb->get_row($wpdb->prepare("SELECT data, created_at FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s ORDER BY created_at DESC LIMIT 1", $uid), ARRAY_A);
        $temp = $humid = $volt = $soil = '';
        if ($fd && !empty($fd['data'])) {
            $j = json_decode($fd['data'], true);
            if (is_array($j)) {
                $temp = $j['cur_device_temp_f'] ?? ($j['t_f'] ?? '');
                $humid = $j['cur_device_humid'] ?? ($j['hum'] ?? '');
                $volt = $j['sys_voltage'] ?? ($j['v'] ?? '');
                $soil = $j['cur_soil_moisture'] ?? '';
            }
        }
        $cards[] = [
            'unit_id' => $uid,
            'name' => $name,
            'status' => $status,
            'last_seen' => $last_seen,
            'temp' => $temp,
            'humid' => $humid,
            'volt' => $volt,
            'soil' => $soil,
        ];
    }

    ob_start();
    echo '<style>
    .tmon-widgets-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
    .tmon-widget-card{border:1px solid #d9d9d9;border-radius:10px;padding:10px 12px;background:#fff}
    .tmon-widget-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
    .tmon-pill{font-size:11px;padding:2px 8px;border-radius:999px;background:#f0f0f0}
    .tmon-pill-online{background:#e9f9ef;color:#1e7e34}
    .tmon-pill-warning{background:#fff8e1;color:#8a6d3b}
    .tmon-pill-offline,.tmon-pill-suspended{background:#fdecea;color:#a94442}
    .tmon-widget-metrics{display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:12px}
    .tmon-widget-summary{display:grid;grid-template-columns:repeat(3,minmax(90px,1fr));gap:8px;margin:0 0 12px 0}
    .tmon-widget-summary .box{border:1px solid #d9d9d9;border-radius:8px;padding:8px 10px;background:#fafafa;text-align:center}
    .tmon-widget-summary .n{font-size:20px;font-weight:700;line-height:1.1}
    </style>';

    echo '<div class="tmon-widget-summary">';
    echo '<div class="box"><div>Online</div><div class="n">' . intval($online) . '</div></div>';
    echo '<div class="box"><div>Warning</div><div class="n">' . intval($warning) . '</div></div>';
    echo '<div class="box"><div>Offline</div><div class="n">' . intval($offline) . '</div></div>';
    echo '</div>';

    echo '<div class="tmon-widgets-grid">';
    foreach ($cards as $c) {
        $pill = 'tmon-pill-' . esc_attr($c['status']);
        echo '<div class="tmon-widget-card">';
        echo '<div class="tmon-widget-head"><strong>' . esc_html($c['name']) . '</strong><span class="tmon-pill ' . $pill . '">' . esc_html($c['status']) . '</span></div>';
        echo '<div class="tmon-widget-metrics">';
        echo '<div><span class="tmon-text-muted">Unit</span><br>' . esc_html($c['unit_id']) . '</div>';
        echo '<div><span class="tmon-text-muted">Seen</span><br>' . esc_html(tmon_uc_format_mysql_datetime($c['last_seen'])) . '</div>';
        echo '<div><span class="tmon-text-muted">Temp F</span><br>' . esc_html((string) $c['temp']) . '</div>';
        echo '<div><span class="tmon-text-muted">Humidity</span><br>' . esc_html((string) $c['humid']) . '</div>';
        echo '<div><span class="tmon-text-muted">Voltage</span><br>' . esc_html((string) $c['volt']) . '</div>';
        echo '<div><span class="tmon-text-muted">Soil</span><br>' . esc_html((string) $c['soil']) . '</div>';
        echo '</div>';
        echo '</div>';
    }
    echo '</div>';

    return ob_get_clean();
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

// Shortcode: [tmon_device_settings] — admin/uc device settings editor
add_shortcode('tmon_device_settings', function($atts = array()){
	// Gather device list (best-effort): prefer helper if available
	$devices = array();
	if (function_exists('tmon_admin_get_all_devices')) {
		foreach ((array) tmon_admin_get_all_devices() as $d) {
			if (!empty($d['unit_id'])) $devices[$d['unit_id']] = $d['unit_id'] . ' — ' . ($d['unit_name'] ?? '');
		}
	} else {
		$opt = get_option('tmon_admin_provisioned_devices', array());
		if (is_array($opt)) {
			foreach ($opt as $u => $m) { $devices[$u] = $u; }
		}
	}
	ob_start();
	?>
	<div id="tmon-device-settings" class="tmon-device-settings">
        <p><em>Use the page-level Unit selector when present; otherwise use the local unit dropdown below.</em></p>
        <p id="tmon_ds_unit_row">
            <label for="tmon_ds_unit"><strong>Unit</strong></label><br>
            <select id="tmon_ds_unit" class="regular-text" style="max-width:360px;">
                <option value="">-- choose unit --</option>
                <?php foreach ($devices as $uid => $label): ?>
                    <option value="<?php echo esc_attr($uid); ?>"><?php echo esc_html($label); ?></option>
                <?php endforeach; ?>
            </select>
        </p>
		<button id="tmon_ds_load" class="button">Load</button>

		<div id="tmon_ds_form" style="margin-top:12px; display:none;">
			<form id="tmon_ds_editor">
				<!-- Controls are rendered by JS for flexibility -->
				<div id="tmon_ds_fields"></div>
				<p class="submit">
					<button id="tmon_ds_save" class="button button-primary">Stage settings</button>
					<span id="tmon_ds_status" style="margin-left:12px"></span>
				</p>
			</form>
		</div>
	</div>
    <style>
        /* Animated toggle used by bool settings in the staged settings editor */
        .tmon-switch {
            position: relative;
            display: inline-block;
            width: 44px;
            height: 24px;
            vertical-align: middle;
        }
        .tmon-switch input {
            opacity: 0;
            width: 0;
            height: 0;
        }
        .tmon-switch-slider {
            position: absolute;
            cursor: pointer;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: #a7aaad;
            transition: .2s;
            border-radius: 24px;
        }
        .tmon-switch-slider:before {
            position: absolute;
            content: "";
            height: 18px;
            width: 18px;
            left: 3px;
            bottom: 3px;
            background-color: #fff;
            transition: .2s;
            border-radius: 50%;
        }
        .tmon-switch input:checked + .tmon-switch-slider {
            background-color: #2271b1;
        }
        .tmon-switch input:checked + .tmon-switch-slider:before {
            transform: translateX(20px);
        }
        .tmon-switch-state {
            display: inline-block;
            margin-left: 8px;
            color: #50575e;
            font-size: 12px;
            vertical-align: middle;
            min-width: 30px;
        }
    </style>

	<!-- Expose a REST nonce as a fallback when wp.apiSettings.nonce is not available -->
	<script>var TMON_REST_NONCE = '<?php echo esc_js(wp_create_nonce('wp_rest')); ?>';</script>

	<script>
	(function(){
        // Prefer the page-level picker on Device Data page, otherwise use local shortcode picker.
        var external = document.getElementById ? document.getElementById('tmon-unit-picker') : null;
        var local = document.getElementById('tmon_ds_unit');
        var localRow = document.getElementById('tmon_ds_unit_row');
        var activeSelect = external || local;
 		var btnLoad = document.getElementById('tmon_ds_load');
 		var formWrap = document.getElementById('tmon_ds_form');
 		var fields = document.getElementById('tmon_ds_fields');
 		var status = document.getElementById('tmon_ds_status');
 		var saveBtn = document.getElementById('tmon_ds_save');

        if (external && localRow) {
            localRow.style.display = 'none';
        }
 
 		// Keep an inline, local SCHEMA identical to what the UI expects
 		var SCHEMA = [
 			{key:'NODE_TYPE', type:'select', opts:['base','wifi','remote'], label:'Node Type'},
 			{key:'UNIT_Name', type:'text', label:'Unit Name'},
 			{key:'SAMPLE_TEMP', type:'bool', label:'Enable Temperature Sampling'},
 			{key:'SAMPLE_HUMID', type:'bool', label:'Enable Humidity Sampling'},
 			{key:'SAMPLE_BAR', type:'bool', label:'Enable Barometric Pressure Sampling'},
 			{key:'ENABLE_OLED', type:'bool', label:'Enable OLED'},
 			{key:'ENGINE_ENABLED', type:'bool', label:'Enable Engine Controller'},
 			{key:'RELAY_PIN1', type:'number', label:'Relay Pin 1'},
 			{key:'RELAY_PIN2', type:'number', label:'Relay Pin 2'},
 			{key:'WIFI_SSID', type:'text', label:'WiFi SSID'},
 			{key:'WIFI_PASS', type:'text', label:'WiFi Password'}
 		];

 		function renderFields(values){
 			fields.innerHTML = '';
 			SCHEMA.forEach(function(f){
 				var v = values && (values[f.key] !== undefined) ? values[f.key] : '';
 				var row = document.createElement('div');
 				row.style.marginBottom = '8px';
 				var label = document.createElement('label');
 				label.style.display = 'block';
 				label.style.fontWeight = '600';
 				label.textContent = f.label;
 				row.appendChild(label);

 				if (f.type === 'bool') {
                    var sw = document.createElement('label');
                    sw.className = 'tmon-switch';
                    var chk = document.createElement('input');
                    chk.type = 'checkbox';
                    chk.name = f.key;
                    chk.checked = !!v;
                    var slider = document.createElement('span');
                    slider.className = 'tmon-switch-slider';
                    sw.appendChild(chk);
                    sw.appendChild(slider);
                    row.appendChild(sw);
                    var state = document.createElement('span');
                    state.className = 'tmon-switch-state';
                    state.textContent = chk.checked ? 'On' : 'Off';
                    chk.addEventListener('change', function(){
                        state.textContent = chk.checked ? 'On' : 'Off';
                    });
                    row.appendChild(state);
 				} else if (f.type === 'select') {
 					var sel = document.createElement('select');
 					sel.name = f.key;
 					f.opts.forEach(function(o){
 						var opt = document.createElement('option');
 						opt.value = o;
 						opt.textContent = o;
 						if (o === v) opt.selected = true;
 						sel.appendChild(opt);
 					});
 					row.appendChild(sel);
 				} else {
 					var inp = document.createElement('input');
 					inp.type = (f.type === 'number') ? 'number' : 'text';
 					inp.name = f.key;
 					inp.value = (v === null || v === undefined) ? '' : v;
 					inp.className = 'regular-text';
 					row.appendChild(inp);
 				}
 				fields.appendChild(row);
 			});
 		}

 		function fetchStaged(unit){
 			status.textContent = 'Loading...';
 			return fetch(window.location.origin + '/wp-json/tmon/v1/device/staged-settings?unit_id=' + encodeURIComponent(unit), { credentials: 'same-origin' })
 				.then(function(r){ return r.json(); })
 				.then(function(j){ status.textContent = ''; return j.staged || {}; })
 				.catch(function(){ status.textContent = 'Load failed'; return {}; });
 		}

 		function loadVals(unit){
 			if (!unit) { status.textContent = 'Choose a unit'; return; }
 			status.textContent = 'Loading...';
 			fetchStaged(unit).then(function(vals){
 				status.textContent = '';
 				renderFields(vals);
 				formWrap.style.display = '';
 			}).catch(function(){ status.textContent = 'Load failed'; });
 		}

        if (!activeSelect) {
            if (status) status.textContent = 'No unit selector found for settings panel.';
 			if (btnLoad) btnLoad.disabled = true;
 			if (saveBtn) saveBtn.disabled = true;
 			return;
 		}

        // Auto-load when picker changes
        activeSelect.addEventListener('change', function(){ loadVals(activeSelect.value); });

        // Load button uses the active selector
 		if (btnLoad) btnLoad.addEventListener('click', function(e){
 			e.preventDefault();
            var unit = activeSelect.value;
 			if (!unit) { alert('Choose a unit'); return; }
 			loadVals(unit);
 		});

 		// Initial populate: auto-load for current selection if available
 		(function(){
            var initial = (activeSelect && activeSelect.value) ? activeSelect.value : (activeSelect && activeSelect.options && activeSelect.options.length ? activeSelect.options[0].value : null);
 			if (initial) loadVals(initial);
 		})();

 		// Save: stage settings to server (uses page-level picker)
 		if (saveBtn) saveBtn.addEventListener('click', function(e){
 			e.preventDefault();
 			status.textContent = 'Saving...';
            var unit = activeSelect.value;
 			if (!unit) { alert('Choose a unit'); status.textContent = ''; return; }
 			var payload = { unit_id: unit, settings: {} };
 			SCHEMA.forEach(function(f){
 				var el = document.querySelector('[name="'+f.key+'"]');
 				if (!el) return;
 				var v;
 				if (f.type === 'bool') v = !!el.checked;
 				else if (f.type === 'number') v = el.value !== '' ? Number(el.value) : '';
 				else v = el.value;
 				payload.settings[f.key] = v;
 			});
			// include WP REST nonce (if available) to authenticate cookie-based POSTs.
			// Use wp.apiSettings.nonce when available, otherwise fallback to TMON_REST_NONCE injected above.
			var nonce = (window.wp && wp.apiSettings && wp.apiSettings.nonce) ? wp.apiSettings.nonce : (typeof TMON_REST_NONCE !== 'undefined' ? TMON_REST_NONCE : '');
			var headers = {'Content-Type': 'application/json'};
			if (nonce) headers['X-WP-Nonce'] = nonce;
			fetch(window.location.origin + '/wp-json/tmon/v1/admin/device/settings-staged', {
				method: 'POST',
				credentials: 'same-origin',
				headers: headers,
				body: JSON.stringify(payload)
			}).then(function(r){ return r.json(); }).then(function(j){
				if (j && j.ok) {
					status.textContent = 'Staged. Will be delivered at next device check-in.';
					loadVals(unit);
				} else {
					status.textContent = (j && j.message) ? j.message : 'Save failed';
					if (j && j.code === 'rest_forbidden') alert('Permission denied: you must be an admin to stage settings.');
				}
			}).catch(function(){ status.textContent = 'Save request failed'; });
 		});
	})();
	</script>
	<?php
	return ob_get_clean();
 });
 
// AJAX: stage a UNIT_Name update for a specific unit (admin UI -> stage name for next check-in)
add_action('wp_ajax_tmon_uc_update_unit_name', function() {
	// Optional: verify nonce if provided
	if ( isset($_REQUEST['security']) ) {
		check_ajax_referer('tmon_uc_nonce', 'security');
	}
	if ( ! current_user_can('manage_options') ) {
		wp_send_json_error(array('message' => 'forbidden'), 403);
	}
	$unit = isset($_REQUEST['unit_id']) ? sanitize_text_field($_REQUEST['unit_id']) : '';
	$name = isset($_REQUEST['unit_name']) ? sanitize_text_field($_REQUEST['unit_name']) : '';
	if ( ! $unit ) {
		wp_send_json_error(array('message' => 'unit_id required'), 400);
	}
	$map = get_option('tmon_uc_staged_settings', array());
	if (! is_array($map)) $map = array();
	$entry = isset($map[$unit]) && is_array($map[$unit]) ? $map[$unit] : array('settings' => array(), 'ts' => current_time('timestamp'), 'who' => wp_get_current_user()->user_login);
	if (! isset($entry['settings']) || ! is_array($entry['settings'])) $entry['settings'] = array();
	$entry['settings']['UNIT_Name'] = $name;
	$entry['ts']  = current_time('timestamp');
	$entry['who'] = wp_get_current_user()->user_login;
	$map[$unit] = $entry;
	update_option('tmon_uc_staged_settings', $map);
	// Keep existing hook/audit behavior consistent
	do_action('tmon_staged_settings_updated', $unit, $entry['settings']);
	wp_send_json_success(array('ok' => true, 'unit_id' => $unit, 'settings' => $entry['settings']));
});

// AJAX: Get settings (applied/staged)
// Replaced large anonymous closure with a concise named handler to avoid deeply nested logic and unbalanced braces.
if (! function_exists('tmon_uc_get_settings_handler')) {
function tmon_uc_get_settings_handler() {
    if (! current_user_can('manage_options') ) wp_send_json_error();
    global $wpdb;
    $unit_id = sanitize_text_field($_GET['unit_id'] ?? '');
    $applied = $staged = [];
    $applied_source = $staged_source = 'none';

    // Applied settings from devices table (validate JSON)
    $row = $wpdb->get_row($wpdb->prepare("SELECT settings FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $unit_id), ARRAY_A);
    if ($row && !empty($row['settings'])) {
        $tmp = json_decode($row['settings'], true);
        if (json_last_error() === JSON_ERROR_NONE && is_array($tmp)) {
            $applied = $tmp;
            $applied_source = 'devices';
        }
    }

    // Staged settings: staged table first
    $row2 = $wpdb->get_row($wpdb->prepare("SELECT settings FROM {$wpdb->prefix}tmon_staged_settings WHERE unit_id=%s", $unit_id), ARRAY_A);
    if ($row2 && !empty($row2['settings'])) {
        $tmp = json_decode($row2['settings'], true);
        if (json_last_error() === JSON_ERROR_NONE && is_array($tmp)) {
            $staged = $tmp;
            $staged_source = 'staged_table';
        }
    }

    // Option fallback (legacy option map)
    if (empty($staged)) {
        $optmap = get_option('tmon_uc_staged_settings', []);
        if (is_array($optmap) && isset($optmap[$unit_id]) && is_array($optmap[$unit_id]['settings'] ?? null)) {
            $staged = $optmap[$unit_id]['settings'];
            $staged_source = 'options';
        }
    }

    // Lightweight log scan fallback: prefer recent files named for unit and look for last JSON object
    if (empty($staged)) {
        $log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
        if (is_dir($log_dir) && is_readable($log_dir)) {
            $safe_unit = preg_replace('/[^A-Za-z0-9._-]/', '', $unit_id);
            $files = [];
            $pref = glob($log_dir . '/field_data_unit-' . $safe_unit . '*') ?: [];
            $general = glob($log_dir . '/*' . $safe_unit . '*') ?: [];
            $files = array_values(array_unique(array_merge($pref, $general)));
            // prefer .txt then newest-first
            usort($files, function($a, $b) {
                $aTxt = preg_match('/\.txt$/i', $a) ? 0 : 1;
                $bTxt = preg_match('/\.txt$/i', $b) ?  0 : 1;
                if ($aTxt !== $bTxt) return $aTxt - $bTxt;
                return filemtime($b) - filemtime($a);
            });
            foreach ($files as $f) {
                $content = @file_get_contents($f);
                if ($content === false) continue;
                // extract last JSON object if present
                if (preg_match_all('/\{[\s\S]*?\}/', $content, $matches)) {
                    foreach (array_reverse($matches[0]) as $part) {
                        $tmp = json_decode($part, true);
                        if (json_last_error() === JSON_ERROR_NONE && is_array($tmp)) {
                            if (isset($tmp['settings']) && is_array($tmp['settings'])) {
                                $staged = $tmp['settings'];
                            } else {
                                $staged = $tmp;
                            }
                            $staged_source = 'field_log';
                            break 2;
                        }
                    }
                }
                // fallback: simple key=value parser for .txt files
                if (preg_match('/\.txt$/i', $f)) {
                    $lines = preg_split('/\r\n|\r|\n/', $content);
                    $kv = [];
                    foreach ($lines as $ln) {
                        $ln = trim($ln);
                        if ($ln === '' || strpos($ln, '#') === 0) continue;
                        if (preg_match('/^\s*([A-Za-z0-9_.-]+)\s*[:=]\s*(.+)$/', $ln, $m)) {
                            $k = $m[1];
                            $v = trim($m[2]);
                            if ((substr($v,0,1) === '"' && substr($v,-1) === '"') || (substr($v,0,1) === "'" && substr($v,-1) === "'")) {
                                $v = substr($v,1,-1);
                            }
                            if (is_numeric($v)) $v = $v + 0;
                            else {
                                $lv = strtolower($v);
                                if (in_array($lv, ['true','false','on','off','yes','no','1','0'], true)) {
                                    $v = in_array($lv, ['true','on','yes','1'], true);
                                }
                            }
                            $kv[$k] = $v;
                        }
                    }
                    if (!empty($kv)) { $staged = $kv; $staged_source = 'field_log'; break; }
                }
            }
        }
    }

    // If no staged but applied exists, expose applied to editor
    if (empty($staged) && !empty($applied)) {
        $staged = $applied;
        $staged_source = 'derived_from_applied';
    }

    $applied_json = empty($applied) ? '' : json_encode($applied, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    $staged_json = empty($staged) ? '' : json_encode($staged, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);

    wp_send_json([
        'success' => true,
        'applied' => $applied,
        'staged' => $staged,
        'applied_json' => $applied_json,
        'staged_json' => $staged_json,
        'applied_source' => $applied_source,
        'staged_source' => $staged_source,
    ]);
}
}
add_action('wp_ajax_tmon_uc_get_settings', 'tmon_uc_get_settings_handler', 10);

// AJAX: Delete a pending command by id
add_action('wp_ajax_tmon_pending_commands_delete', function() {
    check_ajax_referer('tmon_pending_cmds');
    if (!isset($_POST['id'])) wp_send_json_error(['message'=>'id_required'], 400);
    if (!current_user_can('manage_options') && !current_user_can('edit_tmon_units')) wp_send_json_error(['message'=>'forbidden'], 403);
    global $wpdb;
    $id = intval($_POST['id']);
    $deleted = $wpdb->delete($wpdb->prefix.'tmon_device_commands', ['id'=>$id, 'executed_at'=>null]);
    if ($deleted === false) wp_send_json_error(['message'=>'delete_failed'], 500);
    if ($deleted === 0) wp_send_json_error(['message'=>'not_found'], 404);
    wp_send_json_success(['ok' => true]);
});
add_action('wp_ajax_nopriv_tmon_pending_commands_delete', function() {
    wp_send_json_error(['message'=>'not_authenticated'], 403);
});

// AJAX: Get command by id for re-queue
add_action('wp_ajax_tmon_pending_commands_get', function() {
    check_ajax_referer('tmon_pending_cmds');
    if (!isset($_POST['id'])) wp_send_json_error(['message'=>'id_required'], 400);
    if (!current_user_can('manage_options') && !current_user_can('edit_tmon_units')) wp_send_json_error(['message'=>'forbidden'], 403);
    global $wpdb;
    $id = intval($_POST['id']);
    $row = $wpdb->get_row($wpdb->prepare("SELECT command, device_id FROM {$wpdb->prefix}tmon_device_commands WHERE id=%d", $id), ARRAY_A);
    if ($row && isset($row['command'])) {
        wp_send_json_success(['command' => $row['command'], 'device_id' => $row['device_id']]);
    }
    wp_send_json_error(['message' => 'Command not found', 'id' => $id], 404);
});

// AJAX: Re-queue a pending command (insert as new pending command)
add_action('wp_ajax_tmon_pending_commands_requeue', function() {
    check_ajax_referer('tmon_pending_cmds');
    if (!current_user_can('manage_options') && !current_user_can('edit_tmon_units')) wp_send_json_error(['message'=>'forbidden'], 403);
    global $wpdb;
    $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
    $command = $_POST['command'] ?? '';
    if (!$unit_id || $command === '') wp_send_json_error(['message'=>'unit_or_command_required'], 400);
    $ok = $wpdb->insert($wpdb->prefix.'tmon_device_commands', [
        'device_id' => $unit_id,
        'command' => $command,
        // store UTC
        'created_at' => current_time('mysql', true),
        'executed_at' => null
    ]);
    if ($ok === false) wp_send_json_error(['message'=>'insert_failed'], 500);
    wp_send_json_success(['ok' => true]);
});

// --- AUTO-REFRESH AJAX HANDLERS ---
// Return updated pending commands table body (rows only)
add_action('wp_ajax_tmon_pending_commands_refresh', function(){
    check_ajax_referer('tmon_pending_cmds');
    if (!current_user_can('manage_options') && !current_user_can('edit_tmon_units')) wp_send_json_error(['message'=>'forbidden'], 403);
    global $wpdb;
    $table = $wpdb->prefix . 'tmon_device_commands';
    $rows = $wpdb->get_results(
        "SELECT c.id, c.device_id, d.unit_name, c.command, c.created_at
         FROM {$table} c
         LEFT JOIN {$wpdb->prefix}tmon_devices d ON c.device_id = d.unit_id
         WHERE c.executed_at IS NULL
         ORDER BY c.created_at ASC
         LIMIT 200", ARRAY_A);
    ob_start();
    if (empty($rows)) {
        echo '<tr><td colspan="5"><em>No pending commands found.</em></td></tr>';
    } else {
        foreach ($rows as $r) {
            $cmd = $r['command'];
            if (is_string($cmd) && ($decoded = json_decode($cmd, true)) && json_last_error() === JSON_ERROR_NONE) {
                $cmd_html = '<pre style="margin:0;font-size:13px;">'.esc_html(json_encode($decoded, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES)).'</pre>';
            } else {
                $cmd_html = '<pre style="margin:0;font-size:13px;">'.esc_html($cmd).'</pre>';
            }
            $created_site = '';
            if (!empty($r['created_at'])) {
                $ts = function_exists('tmon_uc_mysql_to_local_timestamp') ? tmon_uc_mysql_to_local_timestamp($r['created_at']) : strtotime(get_date_from_gmt($r['created_at']));
                if ($ts) $created_site = date_i18n(get_option('date_format') . ' ' . get_option('time_format'), $ts);
                else $created_site = tmon_uc_format_mysql_datetime($r['created_at']);
            }
            echo '<tr data-unit="'.esc_attr($r['device_id']).'">'
                .'<td>'.esc_html($r['device_id']).'</td>'
                .'<td>'.esc_html($r['unit_name']).'</td>'
                .'<td>'.$cmd_html.'</td>'
                .'<td>'.esc_html($created_site).'</td>'
                .'<td><button class="button button-small tmon-cmd-del" data-id="'.intval($r['id']).'">Delete</button> '
                .'<button class="button button-small tmon-cmd-requeue" data-id="'.intval($r['id']).'" data-unit="'.esc_attr($r['device_id']).'">Re-Queue</button></td>'
                .'</tr>';
        }
    }
    $html = ob_get_clean();
    wp_send_json_success(['html'=>$html]);
});

// Summary refresh (dashboard/shortcode)
add_action('wp_ajax_tmon_pending_commands_summary_refresh', function(){
    check_ajax_referer('tmon_pending_cmds');
    if (!current_user_can('manage_options') && !current_user_can('edit_tmon_units')) wp_send_json_error(['message'=>'forbidden'], 403);
    global $wpdb;
    $rows = $wpdb->get_results("SELECT device_id, COUNT(*) as pending, MAX(created_at) as last_created FROM {$wpdb->prefix}tmon_device_commands WHERE executed_at IS NULL GROUP BY device_id ORDER BY pending DESC LIMIT 50", ARRAY_A);
    ob_start();
    if (empty($rows)) {
        echo '<tr><td colspan="3"><em>No pending commands</em></td></tr>';
    } else {
        foreach ($rows as $r) {
            $last = ''; $last_iso = '';
            if (!empty($r['last_created'])) {
                $ts = function_exists('tmon_uc_mysql_to_local_timestamp') ? tmon_uc_mysql_to_local_timestamp($r['last_created']) : strtotime(get_date_from_gmt($r['last_created']));
                if ($ts) {
                    $last = esc_html( date_i18n(get_option('date_format') . ' ' . get_option('time_format'), $ts) );
                    $last_iso = esc_attr( date_i18n(DATE_ISO8601, $ts) );
                } else {
                    $last = esc_html($r['last_created']);
                    $last_iso = esc_attr($r['last_created']);
                }
            }
            echo '<tr data-last-created="'.$last_iso.'"><td>'.esc_html($r['device_id']).'</td><td>'.intval($r['pending']).'</td><td>'.$last.'</td></tr>';
        }
    }
    $html = ob_get_clean();
    wp_send_json_success(['html'=>$html]);
});

// Device status refresh (table body)
add_action('wp_ajax_tmon_device_status_refresh', function(){
    if (!current_user_can('manage_options') && !current_user_can('edit_tmon_units')) wp_send_json_error(['message'=>'forbidden'], 403);
    check_ajax_referer('tmon_uc_relay'); // reuse relay nonce for status refresh
    global $wpdb;
    // Build the same tbody as the shortcode does
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
    $nonce = wp_create_nonce('tmon_uc_relay');
    ob_start();
    $now = current_time('timestamp');
    foreach ($rows as $r) {
        $last = $r['last_seen'] ? tmon_uc_mysql_to_local_timestamp($r['last_seen']) : 0;
        if (!$last) { $age = PHP_INT_MAX; $cls = 'tmon-red'; $title = 'Never seen'; }
        else {
            $age = max(0, $now - $last);
            if (intval($r['suspended'])) $cls = 'tmon-red';
            else if ($age <= 15 * 60) $cls = 'tmon-green';
            else if ($age <= 30 * 60) $cls = 'tmon-yellow';
            else $cls = 'tmon-red';
            $title = 'Last seen: ' . tmon_uc_format_mysql_datetime($r['last_seen'], get_option('date_format') . ' ' . get_option('time_format')) . ' (' . human_time_diff($last, $now) . ' ago)';
        }
        // Relay detection (lightweight)
        $enabled_relays = [1,2];
        $settings = !empty($r['settings']) ? json_decode($r['settings'], true) : [];
        if (is_array($settings)) {
            foreach ($settings as $k => $v) {
                if (preg_match('/^enable[_]?relay[_]?(\d+)$/i', $k, $m) && isset($m[1])) {
                    $n = intval($m[1]); if ($n>=1 && $n<=8 && tmon_uc_truthy_flag($v)) $enabled_relays[] = $n;
                }
            }
        }
        $fd = $wpdb->get_row($wpdb->prepare("SELECT data FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s ORDER BY created_at DESC LIMIT 1", $r['unit_id']), ARRAY_A);
        $fddata = $fd['data'] ?? '';
        $d = $fddata ? json_decode($fddata, true) : [];
        if (is_array($d)) {
            foreach ($d as $k => $v) {
                if (preg_match('/^enable[_]?relay[_]?(\d+)$/i', $k, $m) && isset($m[1])) {
                    $n = intval($m[1]); if ($n>=1 && $n<=8 && tmon_uc_truthy_flag($v)) $enabled_relays[] = $n;
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
        if (!empty($enabled_relays)) {
            echo '<div class="tmon-relay-ctl" data-unit="'.esc_attr($r['unit_id']).'" data-nonce="'.esc_attr($nonce).'">';
            echo '<label class="tmon-text-muted">Run (min)</label><input type="number" min="0" max="1440" step="1" class="tmon-runtime-min" title="Runtime minutes (0 = no auto-off)" value="0">';
            echo '<label class="tmon-text-muted">At</label><input type="datetime-local" class="tmon-schedule-at" title="Optional schedule time">';
            foreach ($enabled_relays as $n) {
                echo '<div class="tmon-relay-row"><span class="tmon-text-muted">R'.$n.'</span> <button type="button" class="button button-small tmon-relay-btn" data-relay="'.$n.'" data-state="on">On</button> <button type="button" class="button button-small tmon-relay-btn" data-relay="'.$n.'" data-state="off">Off</button></div>';
            }
            echo '</div>';
        } else {
            echo '<span class="tmon-text-muted">No relays enabled</span>';
        }
        echo '</td>';
        echo '</tr>';
    }
    $html = ob_get_clean();
    wp_send_json_success(['html'=>$html]);
});
add_action('wp_ajax_nopriv_tmon_device_status_refresh', function(){ wp_send_json_error(['message'=>'not_authenticated'], 403); });