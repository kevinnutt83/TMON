<?php
// TMON Admin: Device Location Orchestrator (push via Unit Connector)
function tmon_admin_location_page(){
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    echo '<div class="wrap"><h1>Device Location</h1>';
    if (isset($_POST['tmon_push_loc'])) {
        if (!function_exists('tmon_admin_verify_nonce') || !tmon_admin_verify_nonce('tmon_admin_location')) {
            echo '<div class="notice notice-error"><p>Security check failed. Please refresh and try again.</p></div>';
        } else {
        $site_url = esc_url_raw($_POST['site_url'] ?? ''); // UC site
        $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
        $lat = isset($_POST['gps_lat']) && $_POST['gps_lat'] !== '' ? floatval($_POST['gps_lat']) : null;
        $lng = isset($_POST['gps_lng']) && $_POST['gps_lng'] !== '' ? floatval($_POST['gps_lng']) : null;
        $alt = isset($_POST['gps_alt_m']) && $_POST['gps_alt_m'] !== '' ? floatval($_POST['gps_alt_m']) : null;
        $acc = isset($_POST['gps_accuracy_m']) && $_POST['gps_accuracy_m'] !== '' ? floatval($_POST['gps_accuracy_m']) : null;
        if ($site_url && $unit_id && $lat !== null && $lng !== null) {
            // Use UC admin endpoint with shared key auth
            $endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/device/settings';
            $pairings = get_option('tmon_admin_uc_sites', []);
            $uc_key = is_array($pairings) && isset($pairings[$site_url]['uc_key']) ? $pairings[$site_url]['uc_key'] : '';
            if (!$uc_key) {
                echo '<div class="notice notice-error"><p>No UC admin key found for this site. Pair the Unit Connector in TMON Admin &gt; UC Pairings, or ensure the site URL matches an existing pairing exactly.</p></div>';
            } else {
                $settings = ['GPS_LAT'=>$lat,'GPS_LNG'=>$lng];
                if (!is_null($alt)) $settings['GPS_ALT_M'] = $alt;
                if (!is_null($acc)) $settings['GPS_ACCURACY_M'] = $acc;
                $resp = wp_remote_post($endpoint, [
                    'timeout' => 20,
                    'headers' => ['Content-Type'=>'application/json', 'X-TMON-ADMIN' => $uc_key],
                    'body' => wp_json_encode(['unit_id'=>$unit_id, 'settings'=>$settings]),
                ]);
            }
            $ok = !is_wp_error($resp) && wp_remote_retrieve_response_code($resp) == 200;
            echo $ok ? '<div class="updated"><p>Location command pushed via Unit Connector.</p></div>' : '<div class="error"><p>Failed: '.esc_html(is_wp_error($resp)?$resp->get_error_message():wp_remote_retrieve_body($resp)).'</p></div>';
        } else {
            echo '<div class="error"><p>UC Site URL, Unit ID, Latitude, and Longitude are required.</p></div>';
    }
    }
    }
    echo '<form method="post">';
    wp_nonce_field('tmon_admin_location');
    echo '<table class="form-table">';
    // Datalist of paired UC sites for convenience
    $paired = get_option('tmon_admin_uc_sites', []);
    echo '<tr><th>UC Site URL</th><td><input type="url" name="site_url" list="tmon_paired_sites" class="regular-text" placeholder="https://uc.example.com" required>';
    echo '<datalist id="tmon_paired_sites">';
    if (is_array($paired)) { foreach ($paired as $purl => $info) { echo '<option value="'.esc_attr($purl).'">'.esc_html($info['paired_at'] ?? '').'</option>'; } }
    echo '</datalist></td></tr>';
    echo '<tr><th>Unit ID</th><td><input type="text" name="unit_id" class="regular-text" required></td></tr>';
    echo '<tr><th>Latitude</th><td><input type="text" name="gps_lat" class="regular-text" placeholder="38.8977" required></td></tr>';
    echo '<tr><th>Longitude</th><td><input type="text" name="gps_lng" class="regular-text" placeholder="-77.0365" required></td></tr>';
    echo '<tr><th>Altitude (m)</th><td><input type="text" name="gps_alt_m" class="regular-text" placeholder=""></td></tr>';
    echo '<tr><th>Accuracy (m)</th><td><input type="text" name="gps_accuracy_m" class="regular-text" placeholder=""></td></tr>';
    echo '</table>';
    submit_button('Push Location', 'primary', 'tmon_push_loc');
    echo '</form>';
    echo '</div>';
}
