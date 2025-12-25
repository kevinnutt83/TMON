<?php
// Unit Connector: Device Location Override UI
add_action('admin_menu', function(){
    add_submenu_page('tmon_devices', 'Device Location', 'Device Location', 'manage_options', 'tmon_uc_location', 'tmon_uc_location_page');
});

function tmon_uc_location_page(){
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    echo '<div class="wrap"><h1>Device Location Override</h1>';
    if (isset($_POST['tmon_uc_save_location'])) {
        check_admin_referer('tmon_uc_location');
        global $wpdb;
        $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
        $lat = isset($_POST['gps_lat']) && $_POST['gps_lat'] !== '' ? floatval($_POST['gps_lat']) : null;
        $lng = isset($_POST['gps_lng']) && $_POST['gps_lng'] !== '' ? floatval($_POST['gps_lng']) : null;
        $alt = isset($_POST['gps_alt_m']) && $_POST['gps_alt_m'] !== '' ? floatval($_POST['gps_alt_m']) : null;
        $acc = isset($_POST['gps_accuracy_m']) && $_POST['gps_accuracy_m'] !== '' ? floatval($_POST['gps_accuracy_m']) : null;
        $enqueue = !empty($_POST['enqueue_command']);
        if ($unit_id && $lat !== null && $lng !== null) {
            $row = $wpdb->get_row($wpdb->prepare("SELECT settings FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $unit_id));
            $settings = $row && $row->settings ? json_decode($row->settings, true) : [];
            if (!is_array($settings)) $settings = [];
            $settings['GPS_LAT'] = $lat;
            $settings['GPS_LNG'] = $lng;
            if ($alt !== null) $settings['GPS_ALT_M'] = $alt;
            if ($acc !== null) $settings['GPS_ACCURACY_M'] = $acc;
            $wpdb->update($wpdb->prefix.'tmon_devices', ['settings' => wp_json_encode($settings)], ['unit_id' => $unit_id]);

            // Write per-device settings file for local processes / devices to fetch
            $logs_dir = trailingslashit(WP_CONTENT_DIR) . 'tmon-field-logs';
            if (! file_exists($logs_dir)) wp_mkdir_p($logs_dir);
            $file = $logs_dir . '/device_settings-' . sanitize_file_name($unit_id) . '.json';
            @file_put_contents($file, wp_json_encode($settings));

            echo '<div class="updated"><p>Location saved in device settings.</p></div>';
            if ($enqueue) {
                $wpdb->insert($wpdb->prefix.'tmon_device_commands', [
                    'device_id' => $unit_id,
                    'command' => 'settings_update',
                    'params' => wp_json_encode(['GPS_LAT'=>$lat,'GPS_LNG'=>$lng,'GPS_ALT_M'=>$alt,'GPS_ACCURACY_M'=>$acc]),
                    'created_at' => current_time('mysql'),
                ]);
                echo '<div class="updated"><p>settings_update command enqueued (ID: '.intval($wpdb->insert_id).').</p></div>';
            }
        } else {
            echo '<div class="error"><p>Unit ID, Latitude, and Longitude are required.</p></div>';
        }
    }
    echo '<form method="post">';
    wp_nonce_field('tmon_uc_location');
    echo '<table class="form-table">';
    echo '<tr><th>Unit ID</th><td><input type="text" name="unit_id" class="regular-text" required></td></tr>';
    echo '<tr><th>Latitude</th><td><input type="text" name="gps_lat" class="regular-text" placeholder="38.8977" required></td></tr>';
    echo '<tr><th>Longitude</th><td><input type="text" name="gps_lng" class="regular-text" placeholder="-77.0365" required></td></tr>';
    echo '<tr><th>Altitude (m)</th><td><input type="text" name="gps_alt_m" class="regular-text" placeholder=""></td></tr>';
    echo '<tr><th>Accuracy (m)</th><td><input type="text" name="gps_accuracy_m" class="regular-text" placeholder=""></td></tr>';
    echo '<tr><th>Also send command</th><td><label><input type="checkbox" name="enqueue_command" value="1" checked> Enqueue immediate settings_update command to device</label></td></tr>';
    echo '</table>';
    submit_button('Save Location', 'primary', 'tmon_uc_save_location');
    echo '</form>';
    echo '</div>';
}
