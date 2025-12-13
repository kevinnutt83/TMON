<?php
// Unit Connector Settings registration
add_action('admin_init', function() {
    register_setting('tmon_uc_settings', 'tmon_uc_admin_key');
    register_setting('tmon_uc_settings', 'tmon_uc_hub_url');
    register_setting('tmon_uc_settings', 'tmon_uc_remove_data_on_deactivate');
    register_setting('tmon_uc_settings', 'tmon_uc_auto_update');
    add_settings_section('tmon_uc_main', 'Admin Integration', function(){
        echo '<p>Configure cross-site integration with TMON Admin.</p>';
    }, 'tmon_uc_settings');
    add_settings_field('tmon_uc_admin_key', 'Shared Key (X-TMON-ADMIN)', function() {
        $val = get_option('tmon_uc_admin_key', '');
        $gen_url = wp_nonce_url(admin_url('admin-post.php?action=tmon_uc_generate_key'), 'tmon_uc_generate_key');
        echo '<input type="text" name="tmon_uc_admin_key" class="regular-text" value="' . esc_attr($val) . '" /> ';
        echo '<a class="button" href="' . esc_url($gen_url) . '">Generate new key</a>';
        echo '<p class="description">This key must match on the TMON Admin hub for secure cross-site actions. Share via a secure channel if pairing manually.</p>';
    }, 'tmon_uc_settings', 'tmon_uc_main');
    add_settings_field('tmon_uc_hub_url', 'TMON Admin Hub URL', function() {
        // Default to this site’s domain if empty
        $current = home_url();
        $val = get_option('tmon_uc_hub_url', $current);
        echo '<input type="url" name="tmon_uc_hub_url" class="regular-text" placeholder="'.esc_attr($current).'" value="' . esc_attr($val) . '" />';
        echo '<p class="description">Defaults to this site URL; set your Admin hub if different. Pairing and diagnostics now live under Hub Pairing.</p>';
    }, 'tmon_uc_settings', 'tmon_uc_main');

    // Purge utilities section (rendered on a separate page area to avoid nested forms)
    add_settings_section('tmon_uc_purge', 'Data Maintenance', function(){
        echo '<p>Danger zone: permanently delete stored device data and logs.</p>';
    }, 'tmon_uc_purge_page');
    add_settings_field('tmon_uc_purge_controls', 'Purge Tools', function(){
        $nonce_all = wp_nonce_url(admin_url('admin-post.php?action=tmon_uc_purge_all'), 'tmon_uc_purge_all');
        echo '<p><a class="button button-secondary" href="' . esc_url($nonce_all) . '" onclick="return confirm(\'This will delete ALL device data, commands, OTA jobs, and logs on this site. Continue?\');">Purge ALL UC data</a></p>';
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '" onsubmit="return confirm(\'This will delete data for the specified Unit ID. Continue?\');">';
        wp_nonce_field('tmon_uc_purge_unit');
        echo '<input type="hidden" name="action" value="tmon_uc_purge_unit" />';
        echo '<input type="text" name="unit_id" class="regular-text" placeholder="Unit ID (e.g., 123456)" /> ';
        submit_button('Purge by Unit ID', 'delete', 'submit', false);
        echo '</form>';
        echo '<p class="description">This removes DB rows from tmon_field_data, tmon_devices, tmon_device_commands, tmon_ota_jobs and deletes matching CSV/LOG files under wp-content/tmon-field-logs.</p>';
    }, 'tmon_uc_purge_page', 'tmon_uc_purge');
});

// Securely generate/store a new shared admin key
add_action('admin_post_tmon_uc_generate_key', function(){
    if (!current_user_can('manage_options')) wp_die('Insufficient permissions');
    check_admin_referer('tmon_uc_generate_key');
    try {
        if (function_exists('random_bytes')) {
            $raw = random_bytes(24);
            $key = bin2hex($raw);
        } else {
            $key = wp_generate_password(48, false, false);
        }
    } catch (Exception $e) {
        $key = wp_generate_password(48, false, false);
    }
    update_option('tmon_uc_admin_key', $key);
    wp_safe_redirect(admin_url('admin.php?page=tmon-uc-hub&keygen=1'));
    exit;
});

// Admin-post: Purge ALL UC data
add_action('admin_post_tmon_uc_purge_all', function(){
    if (!current_user_can('manage_options')) wp_die('Insufficient permissions');
    check_admin_referer('tmon_uc_purge_all');
    global $wpdb;
    // Delete DB rows
    $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_field_data");
    $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_device_commands");
    $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_ota_jobs");
    $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_devices");
    // Delete files
    $dir = WP_CONTENT_DIR . '/tmon-field-logs';
    if (is_dir($dir)) {
        foreach (glob($dir . '/*') as $f) { @unlink($f); }
    }
    wp_safe_redirect(admin_url('admin.php?page=tmon-settings&purge=all'));
    exit;
});

// Admin-post: Purge by unit
add_action('admin_post_tmon_uc_purge_unit', function(){
    if (!current_user_can('manage_options')) wp_die('Insufficient permissions');
    check_admin_referer('tmon_uc_purge_unit');
    $unit_id = isset($_POST['unit_id']) ? sanitize_text_field($_POST['unit_id']) : '';
    if ($unit_id) {
        global $wpdb;
        $wpdb->delete($wpdb->prefix.'tmon_field_data', ['unit_id' => $unit_id]);
        $wpdb->delete($wpdb->prefix.'tmon_device_commands', ['device_id' => $unit_id]);
        $wpdb->delete($wpdb->prefix.'tmon_ota_jobs', ['unit_id' => $unit_id]);
        $wpdb->delete($wpdb->prefix.'tmon_devices', ['unit_id' => $unit_id]);
        $dir = WP_CONTENT_DIR . '/tmon-field-logs';
        // Remove per-unit files
        foreach (['field_data_'.$unit_id.'.csv','field_data_'.$unit_id.'.log'] as $fname) {
            $path = $dir . '/' . $fname;
            if (file_exists($path)) { @unlink($path); }
        }
        // Remove data_history files for unit
        foreach (glob($dir . '/data_history_' . $unit_id . '_*.log') as $f) { @unlink($f); }
    }
    wp_safe_redirect(admin_url('admin.php?page=tmon-settings&purge=unit'));
    exit;
});

// REST: Purge endpoints (for automation or central admin)
add_action('rest_api_init', function(){
    register_rest_route('tmon/v1', '/admin/purge/all', [
        'methods' => 'POST',
        'callback' => function($request){
            if (!tmon_uc_admin_integration_auth($request)) return new WP_REST_Response(['status'=>'forbidden'], 403);
            global $wpdb;
            $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_field_data");
            $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_device_commands");
            $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_ota_jobs");
            $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_devices");
            $dir = WP_CONTENT_DIR . '/tmon-field-logs';
            if (is_dir($dir)) { foreach (glob($dir . '/*') as $f) { @unlink($f); } }
            return rest_ensure_response(['status'=>'ok']);
        },
        'permission_callback' => '__return_true',
    ]);
    register_rest_route('tmon/v1', '/admin/purge/unit', [
        'methods' => 'POST',
        'callback' => function($request){
            if (!tmon_uc_admin_integration_auth($request)) return new WP_REST_Response(['status'=>'forbidden'], 403);
            global $wpdb;
            $unit_id = sanitize_text_field($request->get_param('unit_id'));
            if (!$unit_id) return rest_ensure_response(['status'=>'error','message'=>'unit_id required']);
            $wpdb->delete($wpdb->prefix.'tmon_field_data', ['unit_id' => $unit_id]);
            $wpdb->delete($wpdb->prefix.'tmon_device_commands', ['device_id' => $unit_id]);
            $wpdb->delete($wpdb->prefix.'tmon_ota_jobs', ['unit_id' => $unit_id]);
            $wpdb->delete($wpdb->prefix.'tmon_devices', ['unit_id' => $unit_id]);
            $dir = WP_CONTENT_DIR . '/tmon-field-logs';
            foreach (['field_data_'.$unit_id.'.csv','field_data_'.$unit_id.'.log'] as $fname) {
                $path = $dir . '/' . $fname;
                if (file_exists($path)) { @unlink($path); }
            }
            foreach (glob($dir . '/data_history_' . $unit_id . '_*.log') as $f) { @unlink($f); }
            return rest_ensure_response(['status'=>'ok']);
        },
        'permission_callback' => '__return_true',
    ]);
});

// Pair with TMON Admin hub: exchange shared key and save hub key locally
add_action('admin_post_tmon_uc_pair_with_hub', function(){
    if (!current_user_can('manage_options')) wp_die('Insufficient permissions');
    check_admin_referer('tmon_uc_pair_with_hub');
    $hub = trim(get_option('tmon_uc_hub_url', home_url()));
    if (stripos($hub, 'http') !== 0) { $hub = 'https://' . ltrim($hub, '/'); }
    $local_key = get_option('tmon_uc_admin_key', '');
    if (!$local_key) {
        try { $local_key = bin2hex(random_bytes(24)); } catch (Exception $e) { $local_key = wp_generate_password(48, false, false); }
        update_option('tmon_uc_admin_key', $local_key);
    }
    $endpoint = rtrim($hub, '/') . '/wp-json/tmon-admin/v1/uc/pair';
    $resp = wp_remote_post($endpoint, [
        'timeout' => 15,
        'headers' => ['Content-Type' => 'application/json', 'Accept'=>'application/json', 'User-Agent'=>'TMON-UC/1.0'],
        'body' => wp_json_encode([
            'site_url' => home_url(),
            'uc_key'   => $local_key,
        ]),
    ]);
    if (is_wp_error($resp)) {
        wp_safe_redirect(admin_url('admin.php?page=tmon-settings&paired=0&msg=' . urlencode($resp->get_error_message())));
        exit;
    }
    $code = wp_remote_retrieve_response_code($resp);
    $body = json_decode(wp_remote_retrieve_body($resp), true);
    if ($code === 200 && is_array($body) && !empty($body['hub_key'])) {
        update_option('tmon_uc_hub_shared_key', sanitize_text_field($body['hub_key']));
        if (!empty($body['read_token'])) update_option('tmon_uc_hub_read_token', sanitize_text_field($body['read_token']));
        // Track normalized pairing
        $paired = get_option('tmon_uc_paired_sites', []);
        if (!is_array($paired)) $paired = [];
        $norm = tmon_uc_normalize_url($hub);
        $paired[$norm] = [
            'site'      => $hub,
            'paired_at' => current_time('mysql'),
            'read_token'=> isset($body['read_token']) ? sanitize_text_field($body['read_token']) : '',
        ];
        update_option('tmon_uc_paired_sites', $paired, false);
        // Backfill devices
        if (function_exists('tmon_uc_backfill_provisioned_from_admin')) {
            tmon_uc_backfill_provisioned_from_admin();
        }
        wp_safe_redirect(admin_url('admin.php?page=tmon-uc-hub&paired=1'));
    } else {
        wp_safe_redirect(admin_url('admin.php?page=tmon-uc-hub&paired=0&msg=bad_response'));
    }
    exit;
});

// Admin-post: forward a claim to hub via proxy endpoint, authenticated by hub shared key
add_action('admin_post_tmon_uc_submit_claim', function(){
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
    $machine_id = sanitize_text_field($_POST['machine_id'] ?? '');
    if (!$unit_id || !$machine_id) wp_die('Missing unit_id or machine_id');
    $hub = trim(get_option('tmon_uc_hub_url', ''));
    if (!$hub) wp_die('Hub URL not configured');
    $endpoint = rtrim($hub, '/') . '/wp-json/tmon-admin/v1/proxy/claim';
    $headers = ['Content-Type' => 'application/json'];
    $hub_key = get_option('tmon_uc_hub_shared_key', '');
    if ($hub_key) $headers['X-TMON-HUB'] = $hub_key;
    $body = [
        'unit_id' => $unit_id,
        'machine_id' => $machine_id,
        'site_url' => home_url(),
        'user_hint' => wp_get_current_user()->user_login,
    ];
    $resp = wp_remote_post($endpoint, [
        'timeout' => 15,
        'headers' => $headers,
        'body' => wp_json_encode($body),
    ]);
    if (is_wp_error($resp)) {
        wp_die('Error forwarding claim: ' . esc_html($resp->get_error_message()));
    }
    $code = wp_remote_retrieve_response_code($resp);
    if ($code !== 200) {
        wp_die('Hub responded with error: ' . esc_html(wp_remote_retrieve_body($resp)));
    }
    // Extract claim id if present
    $claim_id = 0;
    $b = json_decode(wp_remote_retrieve_body($resp), true);
    if (is_array($b) && isset($b['id'])) { $claim_id = intval($b['id']); }
    // Redirect back with notice (and claim_id if available)
    $redirect = wp_get_referer() ?: admin_url('admin.php?page=tmon_uc_provisioned');
    $redirect = add_query_arg('tmon_claim', 'submitted', $redirect);
    if ($claim_id) { $redirect = add_query_arg('claim_id', $claim_id, $redirect); }
    wp_safe_redirect($redirect);
    exit;
});

// Firmware settings schema mapper (extend common keys; raw JSON fallback will handle the rest)
function tmon_uc_settings_schema() {
    return [
        // Identity & APIs
        'WORDPRESS_API_URL' => ['type'=>'url','label'=>'Admin API URL','desc'=>'Defaults to this site URL; used by firmware to call UC.'],
        'TMON_ADMIN_API_URL' => ['type'=>'url','label'=>'TMON Admin Hub URL','desc'=>'Admin hub base URL'],
        'UNIT_Name' => ['type'=>'string','label'=>'Unit Name','desc'=>'Display name'],
        'PLAN' => ['type'=>'string','label'=>'Plan','desc'=>'standard/pro/enterprise'],
        // Role & flags
        'NODE_TYPE' => ['type'=>'enum','label'=>'Node Type','enum'=>['base','remote','wifi']],
        'ENABLE_WIFI' => ['type'=>'bool','label'=>'Enable WiFi'],
        'ENABLE_LORA' => ['type'=>'bool','label'=>'Enable LoRa'],
        'ENABLE_OLED' => ['type'=>'bool','label'=>'Enable OLED'],
        'DEVICE_SUSPENDED' => ['type'=>'bool','label'=>'Device Suspended'],
        // WiFi
        'WIFI_SSID' => ['type'=>'string','label'=>'WiFi SSID'],
        'WIFI_PASS' => ['type'=>'string','label'=>'WiFi Password'],
        'WIFI_CONN_RETRIES' => ['type'=>'number','label'=>'WiFi Retries'],
        'WIFI_BACKOFF_S' => ['type'=>'number','label'=>'WiFi Backoff (s)'],
        // OTA
        'OTA_ENABLED' => ['type'=>'bool','label'=>'Enable OTA'],
        'OTA_CHECK_INTERVAL_S' => ['type'=>'number','label'=>'OTA Check Interval (s)'],
        'OTA_APPLY_INTERVAL_S' => ['type'=>'number','label'=>'OTA Apply Interval (s)'],
        'OTA_VERSION_ENDPOINT' => ['type'=>'url','label'=>'OTA Version URL'],
        'OTA_MANIFEST_URL' => ['type'=>'url','label'=>'OTA Manifest URL'],
        // Sensors & sampling
        'SAMPLE_TEMP' => ['type'=>'bool','label'=>'Sample Temperature'],
        'SAMPLE_BAR' => ['type'=>'bool','label'=>'Sample Barometric Pressure'],
        'SAMPLE_HUMID' => ['type'=>'bool','label'=>'Sample Humidity'],
        'SYS_VOLTAGE_SAMPLE_INTERVAL_S' => ['type'=>'number','label'=>'Voltage Sample Interval (s)'],
        // GPS
        'GPS_ENABLED' => ['type'=>'bool','label'=>'Enable GPS'],
        'GPS_SOURCE' => ['type'=>'enum','label'=>'GPS Source','enum'=>['manual','module','network']],
        'GPS_LAT' => ['type'=>'string','label'=>'GPS Latitude'],
        'GPS_LNG' => ['type'=>'string','label'=>'GPS Longitude'],
        'GPS_ALT_M' => ['type'=>'string','label'=>'GPS Altitude (m)'],
        'GPS_ACCURACY_M' => ['type'=>'string','label'=>'GPS Accuracy (m)'],
        // HMAC for field data
        'FIELD_DATA_HMAC_ENABLED' => ['type'=>'bool','label'=>'Field Data HMAC Enabled'],
        'FIELD_DATA_HMAC_SECRET' => ['type'=>'string','label'=>'Field Data HMAC Secret'],
        // Debug flags
        'DEBUG' => ['type'=>'bool','label'=>'Global Debug'],
        'DEBUG_PROVISION' => ['type'=>'bool','label'=>'Debug Provisioning'],
        'DEBUG_LORA' => ['type'=>'bool','label'=>'Debug LoRa'],
    ];
}

// Helper: merge staged settings from typed inputs and a raw JSON fallback
function tmon_uc_merge_settings_from_post($schema) {
    $settings = [];
    foreach ($schema as $key => $meta) {
        $val = isset($_POST[$key]) ? wp_unslash($_POST[$key]) : null;
        if ($val === null) continue;
        switch ($meta['type']) {
            case 'bool':
                $settings[$key] = !!$val;
                break;
            case 'number':
                $settings[$key] = is_numeric($val) ? 0 + $val : 0;
                break;
            default:
                $settings[$key] = sanitize_text_field($val);
                break;
        }
    }
    // Raw JSON fallback to cover all remaining firmware keys
    $raw = isset($_POST['RAW_SETTINGS_JSON']) ? wp_unslash($_POST['RAW_SETTINGS_JSON']) : '';
    if ($raw) {
        $decoded = json_decode($raw, true);
        if (is_array($decoded)) {
            foreach ($decoded as $k => $v) {
                // Do not override typed values; only add missing
                if (!array_key_exists($k, $settings)) {
                    $settings[$k] = $v;
                }
            }
        }
    }
    // Ensure defaults for WORDPRESS_API_URL when empty
    if (empty($settings['WORDPRESS_API_URL'])) {
        $settings['WORDPRESS_API_URL'] = home_url();
    }
    return $settings;
}

// Stage settings admin-post (merge typed + raw JSON)
add_action('admin_post_tmon_uc_stage_settings', function(){
    if (!current_user_can('manage_options')) wp_die('Insufficient permissions');
    check_admin_referer('tmon_uc_stage_settings');
    $unit_id = isset($_POST['unit_id']) ? sanitize_text_field($_POST['unit_id']) : '';
    if (!$unit_id) {
        wp_safe_redirect(add_query_arg(['tmon_cfg'=>'fail','msg'=>'missing_unit'], wp_get_referer() ?: admin_url('admin.php?page=tmon-settings')));
        exit;
    }
    $settings = tmon_uc_merge_settings_from_post(tmon_uc_settings_schema());
    global $wpdb;
    uc_devices_ensure_table();
    $table = $wpdb->prefix . 'tmon_uc_devices';
    $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table} WHERE unit_id=%s LIMIT 1", $unit_id), ARRAY_A);
    if ($row) {
        $wpdb->update($table, [
            'staged_settings' => wp_json_encode($settings),
            'staged_at' => current_time('mysql'),
        ], ['unit_id' => $unit_id]);
    } else {
        $wpdb->insert($table, [
            'unit_id' => $unit_id,
            'machine_id' => '',
            'staged_settings' => wp_json_encode($settings),
            'staged_at' => current_time('mysql'),
        ]);
    }
    wp_safe_redirect(add_query_arg(['tmon_cfg'=>'staged','unit_id'=>$unit_id], wp_get_referer() ?: admin_url('admin.php?page=tmon-settings')));
    exit;
});

// After pairing, auto-refresh provisioned devices from Admin hub
add_action('admin_post_tmon_uc_pair_with_hub', function(){
    if (!current_user_can('manage_options')) wp_die('Insufficient permissions');
    check_admin_referer('tmon_uc_pair_with_hub');
    $hub = trim(get_option('tmon_uc_hub_url', home_url()));
    if (stripos($hub, 'http') !== 0) { $hub = 'https://' . ltrim($hub, '/'); }
    $local_key = get_option('tmon_uc_admin_key', '');
    if (!$local_key) {
        try { $local_key = bin2hex(random_bytes(24)); } catch (Exception $e) { $local_key = wp_generate_password(48, false, false); }
        update_option('tmon_uc_admin_key', $local_key);
    }
    $endpoint = rtrim($hub, '/') . '/wp-json/tmon-admin/v1/uc/pair';
    $resp = wp_remote_post($endpoint, [
        'timeout' => 15,
        'headers' => ['Content-Type' => 'application/json', 'Accept'=>'application/json', 'User-Agent'=>'TMON-UC/1.0'],
        'body' => wp_json_encode([
            'site_url' => home_url(),
            'uc_key'   => $local_key,
        ]),
    ]);
    if (is_wp_error($resp)) {
        wp_safe_redirect(admin_url('admin.php?page=tmon-settings&paired=0&msg=' . urlencode($resp->get_error_message())));
        exit;
    }
    $code = wp_remote_retrieve_response_code($resp);
    $body = json_decode(wp_remote_retrieve_body($resp), true);
    if ($code === 200 && is_array($body) && !empty($body['hub_key'])) {
        update_option('tmon_uc_hub_shared_key', sanitize_text_field($body['hub_key']));
        if (!empty($body['read_token'])) update_option('tmon_uc_hub_read_token', sanitize_text_field($body['read_token']));
        // Track normalized pairing
        $paired = get_option('tmon_uc_paired_sites', []);
        if (!is_array($paired)) $paired = [];
        $norm = tmon_uc_normalize_url($hub);
        $paired[$norm] = [
            'site'      => $hub,
            'paired_at' => current_time('mysql'),
            'read_token'=> isset($body['read_token']) ? sanitize_text_field($body['read_token']) : '',
        ];
        update_option('tmon_uc_paired_sites', $paired, false);
        // Backfill devices
        if (function_exists('tmon_uc_backfill_provisioned_from_admin')) {
            tmon_uc_backfill_provisioned_from_admin();
        }
        wp_safe_redirect(admin_url('admin.php?page=tmon-uc-hub&paired=1'));
    } else {
        wp_safe_redirect(admin_url('admin.php?page=tmon-uc-hub&paired=0&msg=bad_response'));
    }
    exit;
});

// Robust fetch from Admin hub to UC cache (used by cron and manual refresh)
function tmon_uc_backfill_provisioned_from_admin() {
    $hub = trim(get_option('tmon_uc_hub_url', ''));
    $hub_key = get_option('tmon_uc_hub_shared_key', '');
    if (!$hub || !$hub_key) return 0;
    $endpoint = rtrim($hub, '/') . '/wp-json/tmon-admin/v1/provisioned-devices';
    $resp = wp_remote_get($endpoint, ['timeout'=>15,'headers'=>['X-TMON-HUB'=>$hub_key]]);
    if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) return 0;
    $data = json_decode(wp_remote_retrieve_body($resp), true);
    if (!is_array($data) || empty($data['devices'])) return 0;
    $devices = $data['devices'];
    $count = 0;
    global $wpdb;
    uc_devices_ensure_table();
    $table = $wpdb->prefix . 'tmon_uc_devices';
    foreach ($devices as $d) {
        $ok = uc_devices_upsert_row([
            'unit_id' => $d['unit_id'] ?? '',
            'machine_id' => $d['machine_id'] ?? '',
            'unit_name' => $d['unit_name'] ?? '',
            'role' => $d['role'] ?? '',
            'assigned' => 1,
        ]);
        if ($ok) $count++;
    }
    return $count;
}

// Admin-post: Push staged settings to Admin hub (optional integration)
add_action('admin_post_tmon_uc_push_staged_to_admin', function(){
    if (!current_user_can('manage_options')) wp_die('Insufficient permissions');
    check_admin_referer('tmon_uc_push_staged_to_admin');
    $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
    if (!$unit_id) {
        wp_safe_redirect(add_query_arg(['tmon_cfg'=>'fail','msg'=>'missing_unit'], wp_get_referer() ?: admin_url('admin.php?page=tmon-settings')));
        exit;
    }
    // Lookup staged settings in UC mirror
    global $wpdb;
    uc_devices_ensure_table();
    $table = $wpdb->prefix . 'tmon_uc_devices';
    $row = $wpdb->get_row($wpdb->prepare("SELECT machine_id, staged_settings FROM {$table} WHERE unit_id=%s LIMIT 1", $unit_id), ARRAY_A);
    $settings_json = [];
    if ($row && !empty($row['staged_settings'])) {
        $settings_json = json_decode($row['staged_settings'], true);
        if (!is_array($settings_json)) $settings_json = [];
    }
    // Post to Admin hub reprovision endpoint if hub URL and key exist
    $hub = trim(get_option('tmon_uc_hub_url', ''));
    $hub_key = get_option('tmon_uc_hub_shared_key', '');
    if ($hub && $hub_key && !empty($settings_json)) {
        $endpoint = rtrim($hub, '/') . '/wp-json/tmon-admin/v1/uc/reprovision';
        $headers = ['Content-Type'=>'application/json', 'X-TMON-HUB' => $hub_key];
        $body = [
            'unit_id' => $unit_id,
            'machine_id' => $row['machine_id'] ?? '',
            'settings' => wp_json_encode($settings_json),
        ];
        $resp = wp_remote_post($endpoint, ['timeout'=>20, 'headers'=>$headers, 'body'=>wp_json_encode($body)]);
        $ok = !is_wp_error($resp) && wp_remote_retrieve_response_code($resp) === 200;
        wp_safe_redirect(add_query_arg(['tmon_cfg'=>$ok?'pushed':'fail'], wp_get_referer() ?: admin_url('admin.php?page=tmon-settings')));
    } else {
        wp_safe_redirect(add_query_arg(['tmon_cfg'=>'fail','msg'=>'no_hub_or_key'], wp_get_referer() ?: admin_url('admin.php?page=tmon-settings')));
    }
    exit;
});

// Normalize helper defined early
if (!function_exists('tmon_uc_normalize_url')) {
	function tmon_uc_normalize_url($url) {
		$u = trim((string)$url);
		if ($u === '') return '';
		if (!preg_match('#^https?://#i', $u)) $u = 'https://' . ltrim($u, '/');
		$parts = parse_url($u);
		if (!$parts || empty($parts['host'])) return '';
		$host = strtolower($parts['host']);
		$port = isset($parts['port']) ? intval($parts['port']) : null;
		return $port ? ($host . ':' . $port) : $host;
	}
}

// Pair with hub: persist keys and normalized pairing; backfill devices to UC cache
add_action('admin_post_tmon_uc_pair_with_hub', function(){
	if (!current_user_can('manage_options')) wp_die('Insufficient permissions');
	check_admin_referer('tmon_uc_pair_with_hub');
	$hub = trim(get_option('tmon_uc_hub_url', home_url()));
	if (stripos($hub, 'http') !== 0) { $hub = 'https://' . ltrim($hub, '/'); }
	$local_key = get_option('tmon_uc_admin_key', '');
	if (!$local_key) { try { $local_key = bin2hex(random_bytes(24)); } catch (Exception $e) { $local_key = wp_generate_password(48, false, false); } update_option('tmon_uc_admin_key', $local_key); }
	$endpoint = rtrim($hub, '/') . '/wp-json/tmon-admin/v1/uc/pair';
	$resp = wp_remote_post($endpoint, ['timeout'=>15,'headers'=>['Content-Type'=>'application/json','Accept'=>'application/json','User-Agent'=>'TMON-UC/1.0'],'body'=>wp_json_encode(['site_url'=>home_url(),'uc_key'=>$local_key])]);
	if (is_wp_error($resp)) { wp_safe_redirect(admin_url('admin.php?page=tmon-settings&paired=0&msg=' . urlencode($resp->get_error_message()))); exit; }
	$code = wp_remote_retrieve_response_code($resp);
	$body = json_decode(wp_remote_retrieve_body($resp), true);
	if ($code === 200 && is_array($body) && !empty($body['hub_key'])) {
		update_option('tmon_uc_hub_shared_key', sanitize_text_field($body['hub_key']));
		if (!empty($body['read_token'])) update_option('tmon_uc_hub_read_token', sanitize_text_field($body['read_token']));
		$paired = get_option('tmon_uc_paired_sites', []);
		if (!is_array($paired)) $paired = [];
		$paired[tmon_uc_normalize_url($hub)] = ['site'=>$hub,'paired_at'=>current_time('mysql'),'read_token'=> isset($body['read_token']) ? sanitize_text_field($body['read_token']) : ''];
		update_option('tmon_uc_paired_sites', $paired, false);
		// Backfill devices
		if (function_exists('tmon_uc_backfill_provisioned_from_admin')) { tmon_uc_backfill_provisioned_from_admin(); }
		wp_safe_redirect(admin_url('admin.php?page=tmon-settings&paired=1'));
	} else {
		wp_safe_redirect(admin_url('admin.php?page=tmon-settings&paired=0&msg=bad_response'));
	}
	exit;
});

    // Manual refresh of provisioned devices from Admin hub
    add_action('admin_post_tmon_uc_refresh_devices', function(){
        if (!current_user_can('manage_options')) wp_die('Insufficient permissions');
        check_admin_referer('tmon_uc_refresh_devices');
        $count = 0;
        if (function_exists('tmon_uc_backfill_provisioned_from_admin')) {
            $count = intval(tmon_uc_backfill_provisioned_from_admin());
        }
        wp_safe_redirect(add_query_arg(['tmon_refresh'=>1,'fetched'=>$count], wp_get_referer() ?: admin_url('admin.php?page=tmon-uc-hub')));
        exit;
    });

// Ensure command table exists (with status column) before any use
function tmon_uc_ensure_command_table() {
	global $wpdb;
	$table = $wpdb->prefix . 'tmon_device_commands';
	$collate = $wpdb->get_charset_collate();
	$wpdb->query("CREATE TABLE IF NOT EXISTS {$table} (
		id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
		device_id VARCHAR(64) NOT NULL,
		command VARCHAR(64) NOT NULL,
		params LONGTEXT NULL,
		status VARCHAR(32) NOT NULL DEFAULT 'staged',
		created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
		updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
		PRIMARY KEY (id),
		KEY device_idx (device_id),
		KEY status_idx (status)
	) {$collate}");
}
add_action('init', 'tmon_uc_ensure_command_table');

// Cron: requeue stale claimed commands back to queued (guard column exists)
add_action('init', function(){
	if (!wp_next_scheduled('tmon_uc_command_requeue_cron')) {
		wp_schedule_event(time() + 60, 'hourly', 'tmon_uc_command_requeue_cron');
	}
});
add_action('tmon_uc_command_requeue_cron', function(){
	global $wpdb;
	tmon_uc_ensure_command_table();
	$table = $wpdb->prefix . 'tmon_device_commands';
	// Status column ensured above; run requeue safely
	$wpdb->query("UPDATE {$table} SET status='queued' WHERE status='claimed' AND updated_at < (NOW() - INTERVAL 5 MINUTE)");
});

// First device check-in: claim flow (UC receives device, calls Admin to confirm and backfills local record)
add_action('rest_api_init', function(){
	register_rest_route('tmon/v1', '/device/first-checkin', [
		'methods' => 'POST',
		'callback' => function($req){
			$unit_id = sanitize_text_field($req->get_param('unit_id'));
			$machine_id = sanitize_text_field($req->get_param('machine_id'));
			if (!$unit_id || !$machine_id) return new WP_REST_Response(['status'=>'error','message'=>'unit_id and machine_id required'], 400);

			// Call Admin to confirm and fetch device record
			$hub = trim(get_option('tmon_uc_hub_url', ''));
			$key = get_option('tmon_uc_hub_shared_key', '');
			if (!$hub || !$key) return new WP_REST_Response(['status'=>'error','message'=>'not_paired'], 400);

			$endpoint = rtrim($hub, '/') . '/wp-json/tmon-admin/v1/uc/confirm-device';
			$resp = wp_remote_post($endpoint, [
				'timeout' => 15,
				'headers' => ['Content-Type'=>'application/json','X-TMON-HUB'=>$key],
				'body' => wp_json_encode(['unit_id'=>$unit_id,'machine_id'=>$machine_id,'site_url'=>home_url()]),
			]);
			if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) {
				return new WP_REST_Response(['status'=>'error','message'=>'admin_unreachable'], 502);
			}
			$data = json_decode(wp_remote_retrieve_body($resp), true);
			// Upsert UC mirror
			global $wpdb;
			uc_devices_ensure_table();
			$table = $wpdb->prefix . 'tmon_uc_devices';
			$wpdb->query($wpdb->prepare(
				"INSERT INTO {$table} (unit_id,machine_id,unit_name,role,assigned,updated_at)
				 VALUES (%s,%s,%s,%s,%d,NOW())
				 ON DUPLICATE KEY UPDATE unit_name=VALUES(unit_name), role=VALUES(role), assigned=VALUES(assigned), updated_at=NOW()",
				$unit_id, $machine_id, sanitize_text_field($data['unit_name'] ?? ''), sanitize_text_field($data['role'] ?? ''), 1
			));
			return rest_ensure_response(['status'=>'ok','claimed'=>true,'device'=>$data]);
		},
		'permission_callback' => '__return_true',
	]);
});

// Shortcode: claim device via Unit ID + Machine ID
add_shortcode('tmon_uc_claim_device', function($atts){
	if (!current_user_can('manage_options')) return '';
	$action = isset($_POST['tmon_uc_claim_submit']);
	$out = '<form method="post"><p><label>Unit ID <input type="text" name="unit_id" required></label> ';
	$out .= '<label>Machine ID <input type="text" name="machine_id" required></label> ';
	$out .= '<button type="submit" name="tmon_uc_claim_submit" class="button">Claim</button></p></form>';
	if ($action) {
		$unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
		$machine_id = sanitize_text_field($_POST['machine_id'] ?? '');
		$req = new WP_REST_Request('POST', '/tmon/v1/device/first-checkin');
		$req->set_param('unit_id', $unit_id);
		$req->set_param('machine_id', $machine_id);
		$res = rest_do_request($req);
		$data = rest_get_server()->response_to_data($res, false);
		if (is_array($data) && ($data['status'] ?? '') === 'ok') {
			$out .= '<div class="notice notice-success is-dismissible"><p>Device claimed.</p></div>';
		} else {
			$out .= '<div class="notice notice-error is-dismissible"><p>Claim failed.</p></div>';
		}
	}
	return $out;
});

// Shortcodes
add_shortcode('tmon_device_list', function($atts){
	$atts = shortcode_atts(['class'=>''], $atts, 'tmon_device_list');
	return '<div id="tmon-device-list" class="'.esc_attr($atts['class']).'"></div><div id="tmon-device-details" class="tmon-card"></div>';
});
add_shortcode('tmon_device_status', function($atts){
	$atts = shortcode_atts(['unit_id'=>'', 'class'=>''], $atts, 'tmon_device_status');
	return '<div id="tmon-device-status" data-unit_id="'.esc_attr($atts['unit_id']).'" class="'.esc_attr($atts['class']).'">Loading…</div>';
});

// Ensure AJAX URL is exposed for frontend JS
add_action('wp_enqueue_scripts', function(){
	wp_register_script('tmon-uc-frontend', plugins_url('assets/js/uc-frontend.js', dirname(__FILE__)), ['jquery'], '1.0', true);
	// Fallback localization for AJAX in case theme does not use admin_url
	wp_localize_script('tmon-uc-frontend', 'tmon_uc_ajax', [
		'ajaxurl' => admin_url('admin-ajax.php'),
	]);
	// Do not force enqueue here; frontend scripts in v2.00m snippets may load via theme or admin enqueue.
});
