<?php
// Fallback TMON Admin Hub URL
if (!defined('TMON_UC_DEFAULT_HUB_URL')) {
    define('TMON_UC_DEFAULT_HUB_URL', 'https://tmonsystems.com');
}
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
        $val = get_option('tmon_uc_hub_url', '');
        echo '<input type="url" name="tmon_uc_hub_url" class="regular-text" placeholder="https://admin.example.com" value="' . esc_attr($val) . '" />';
        echo '<p class="description">Unit Connector will forward unknown devices here for provisioning.</p>';
        $pair_url = wp_nonce_url(admin_url('admin-post.php?action=tmon_uc_pair_with_hub'), 'tmon_uc_pair_with_hub');
        echo '<p><a class="button button-secondary" href="' . esc_url($pair_url) . '">Pair with Hub</a></p>';
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
    wp_safe_redirect(admin_url('admin.php?page=tmon-settings&keygen=1'));
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
    $hub = trim(get_option('tmon_uc_hub_url', TMON_UC_DEFAULT_HUB_URL));
    if (!$hub) { $hub = TMON_UC_DEFAULT_HUB_URL; }
    if (stripos($hub, 'http') !== 0) { $hub = 'https://' . ltrim($hub, '/'); }
    if (!$hub) {
        wp_safe_redirect(admin_url('admin.php?page=tmon-settings&paired=0&msg=nohub'));
        exit;
    }
    $local_key = get_option('tmon_uc_admin_key', '');
    if (!$local_key) {
        // generate one if missing
        try { $local_key = bin2hex(random_bytes(24)); } catch (Exception $e) { $local_key = wp_generate_password(48, false, false); }
        update_option('tmon_uc_admin_key', $local_key);
    }
    // Call hub pairing endpoint (best-effort)
    $endpoint = rtrim($hub, '/') . '/wp-json/tmon-admin/v1/uc/pair';
    $resp = wp_remote_post($endpoint, [
        'timeout' => 15,
        'headers' => ['Content-Type' => 'application/json'],
        'body' => wp_json_encode([
            'site_url' => home_url(),
            'uc_key' => $local_key,
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
        if (!empty($body['read_token'])) {
            update_option('tmon_uc_hub_read_token', sanitize_text_field($body['read_token']));
        }
        wp_safe_redirect(admin_url('admin.php?page=tmon-settings&paired=1'));
    } else {
        wp_safe_redirect(admin_url('admin.php?page=tmon-settings&paired=0'));
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
