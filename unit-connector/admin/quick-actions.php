<?php
// Quick Actions widget for TMON admin dashboard (enhanced)
add_action('wp_dashboard_setup', function() {
    wp_add_dashboard_widget('tmon_quick_actions', 'TMON Quick Actions', function() {
        if (!current_user_can('manage_options')) {
            echo '<p>Insufficient permissions</p>'; return;
        }
        global $wpdb;
        $units = $wpdb->get_results("SELECT unit_id, unit_name FROM {$wpdb->prefix}tmon_devices ORDER BY unit_name ASC, unit_id ASC", ARRAY_A);
        $nonce = wp_create_nonce('tmon_uc_nonce');
        echo '<div><label for="tmon_quick_unit">Unit:</label> ';
        echo '<select id="tmon_quick_unit">';
        echo '<option value="">-- select unit --</option>';
        foreach ($units as $u) {
            $label = $u['unit_name'] ? ($u['unit_name'] . ' (' . $u['unit_id'] . ')') : $u['unit_id'];
            echo '<option value="'.esc_attr($u['unit_id']).'">'.esc_html($label).'</option>';
        }
        echo '</select></div>';
        echo '<div style="margin-top:8px;">';
        echo '<button id="tmon_quick_refresh" class="button">Refresh Device (enqueue)</button> ';
        echo '<span id="tmon_quick_status" style="margin-left:8px;"></span>';
        echo '</div>';
        ?>
        <script>
        (function(){
            var ajax = '<?php echo admin_url('admin-ajax.php'); ?>';
            var btn = document.getElementById('tmon_quick_refresh');
            var sel = document.getElementById('tmon_quick_unit');
            var status = document.getElementById('tmon_quick_status');
            btn.addEventListener('click', function(){
                var unit = sel.value;
                if (!unit) { alert('Select unit'); return; }
                status.textContent = 'Queuing...';
                var body = new URLSearchParams();
                body.append('action','tmon_uc_queue_refresh');
                body.append('unit_id', unit);
                body.append('nonce', '<?php echo esc_js($nonce); ?>');
                fetch(ajax, { method:'POST', credentials:'same-origin', body: body })
                .then(r => r.json()).then(function(j){
                    if (j && j.success) status.textContent = 'Queued';
                    else status.textContent = 'Queue failed';
                }).catch(function(){ status.textContent = 'Network error'; });
            });
        })();
        </script>
        <?php
    });
});

// AJAX: enqueue a device refresh (admin clicked "Refresh Device")
add_action('wp_ajax_tmon_uc_queue_refresh', function() {
    if (! current_user_can('manage_options')) wp_send_json_error('forbidden', 403);
    check_ajax_referer('tmon_uc_nonce', 'nonce');
    $unit = sanitize_text_field($_POST['unit_id'] ?? '');
    if (! $unit) wp_send_json_error('missing_unit', 400);
    $queue = get_option('tmon_uc_refresh_queue', array());
    if (!is_array($queue)) $queue = array();
    $queue[] = array('unit_id' => $unit, 'ts' => time());
    update_option('tmon_uc_refresh_queue', $queue);
    // ensure cron scheduled (5-minute interval)
    if (! wp_next_scheduled('tmon_uc_refresh_queue_cron')) {
        if (! wp_get_schedule('tmon_uc_refresh_queue_cron') ) {
            if (! wp_next_scheduled('tmon_uc_refresh_queue_cron')) {
                wp_schedule_event(time(), 'five_minutes', 'tmon_uc_refresh_queue_cron');
            }
        }
    }
    wp_send_json_success(array('queued'=>true));
});

// Add custom cron interval 5 minutes
add_filter('cron_schedules', function($schedules){
    if (!isset($schedules['five_minutes'])) {
        $schedules['five_minutes'] = array('interval' => 300, 'display' => __('Every Five Minutes'));
    }
    return $schedules;
});

// Cron worker: process queued refreshes by pushing to Admin hub
add_action('tmon_uc_refresh_queue_cron', function(){
    $queue = get_option('tmon_uc_refresh_queue', array());
    if (!is_array($queue) || empty($queue)) return;
    $hub = function_exists('tmon_uc_get_hub_url') ? tmon_uc_get_hub_url() : get_option('tmon_uc_hub_url', '');
    $hub_key = get_option('tmon_uc_hub_shared_key', '');
    if (!$hub || !$hub_key) return;
    $endpoint = rtrim($hub, '/') . '/wp-json/tmon-admin/v1/uc/sync-devices';
    $processed = array();
    foreach ($queue as $idx => $item) {
        $unit = sanitize_text_field($item['unit_id'] ?? '');
        if (! $unit) { $processed[] = $idx; continue; }
        global $wpdb;
        $dev = $wpdb->get_row($wpdb->prepare("SELECT unit_id, machine_id, unit_name, role FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s LIMIT 1", $unit), ARRAY_A);
        $fd = $wpdb->get_row($wpdb->prepare("SELECT data, created_at FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s ORDER BY created_at DESC LIMIT 1", $unit), ARRAY_A);
        $device_payload = array(
            'unit_id' => $dev['unit_id'] ?? $unit,
            'machine_id' => $dev['machine_id'] ?? '',
            'unit_name' => $dev['unit_name'] ?? '',
            'role' => $dev['role'] ?? '',
            'last_field_data' => $fd ? (json_decode($fd['data'], true) ?: $fd['data']) : null,
        );
        $body = json_encode(array('devices' => array($device_payload)));
        $args = array('timeout' => 20, 'headers' => array('Content-Type'=>'application/json','X-TMON-HUB'=>$hub_key), 'body' => $body);
        // Use safe helper if available
        if (function_exists('tmon_uc_safe_remote_post')) {
            $resp = tmon_uc_safe_remote_post($endpoint, $args, 'refresh_queue');
            if (!is_wp_error($resp) && intval(wp_remote_retrieve_response_code($resp)) === 200) {
                $processed[] = $idx;
            }
        } else {
            $resp = wp_remote_post($endpoint, $args);
            if (!is_wp_error($resp) && intval(wp_remote_retrieve_response_code($resp)) === 200) {
                $processed[] = $idx;
            }
        }
    }
    // prune processed items
    if (!empty($processed)) {
        // remove by index descending to preserve offsets
        rsort($processed);
        foreach ($processed as $i) { unset($queue[$i]); }
        update_option('tmon_uc_refresh_queue', array_values($queue));
    }
});
