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
        echo '<p class="description">Defaults to this site URL; set your Admin hub if different.</p>';
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
    $hub = trim(get_option('tmon_uc_hub_url', home_url()));
    if (stripos($hub, 'http') !== 0) { $hub = 'https://' . ltrim($hub, '/'); }
    if (!$hub) {
        wp_safe_redirect(admin_url('admin.php?page=tmon-settings&paired=0&msg=nohub'));
        exit;
    }
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
            'site_name'=> get_option('blogname'),
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
        // Track normalized pairing for diagnostics
        $paired = get_option('tmon_uc_paired_sites', []);
        if (!is_array($paired)) $paired = [];
        $paired[tmon_uc_normalize_url($hub)] = [
            'site'      => $hub,
            'paired_at' => current_time('mysql'),
            'read_token'=> isset($body['read_token']) ? sanitize_text_field($body['read_token']) : '',
        ];
        update_option('tmon_uc_paired_sites', $paired, false);
        wp_safe_redirect(admin_url('admin.php?page=tmon-settings&paired=1'));
    } else {
        wp_safe_redirect(admin_url('admin.php?page=tmon-settings&paired=0&msg=bad_response'));
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

// Firmware settings schema mapper (minimal scaffold; extend types/help as needed)
function tmon_uc_settings_schema() {
    return [
        // Network
        'WORDPRESS_API_URL' => ['type'=>'url','label'=>'Admin API URL','desc'=>'Hub endpoint for provisioning.'],
        'WIFI_SSID' => ['type'=>'string','label'=>'WiFi SSID','desc'=>'Network SSID'],
        'WIFI_PASSWORD' => ['type'=>'string','label'=>'WiFi Password','desc'=>'Network password'],
        // Node role and behavior
        'NODE_TYPE' => ['type'=>'enum','label'=>'Node Type','enum'=>['base','remote','wifi'],'desc'=>'Device role'],
        'ENABLE_OLED' => ['type'=>'bool','label'=>'Enable OLED','desc'=>'Toggle OLED updates'],
        // OTA
        'OTA_CHECK_INTERVAL_S' => ['type'=>'number','label'=>'OTA Check Interval (s)','desc'=>'Periodic OTA check interval'],
        // Debug
        'DEBUG' => ['type'=>'bool','label'=>'Global Debug','desc'=>'Enable verbose logs'],
    ];
}

// Admin-post: Stage settings for a device (stores JSON into tmon_uc_devices.staged_settings)
add_action('admin_post_tmon_uc_stage_settings', function(){
    if (!current_user_can('manage_options')) wp_die('Insufficient permissions');
    check_admin_referer('tmon_uc_stage_settings');
    $unit_id = isset($_POST['unit_id']) ? sanitize_text_field($_POST['unit_id']) : '';
    if (!$unit_id) {
        wp_safe_redirect(add_query_arg(['tmon_cfg'=>'fail','msg'=>'missing_unit'], wp_get_referer() ?: admin_url('admin.php?page=tmon-settings')));
        exit;
    }
    // Build staged JSON from posted fields based on schema
    $schema = tmon_uc_settings_schema();
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

// REST endpoints: staged settings (GET) and applied confirmation (POST)
add_action('rest_api_init', function(){
    register_rest_route('tmon/v1', '/admin/device/settings-staged', [
        'methods' => 'GET',
        'callback' => function($request){
            // Auth: allow hub/admin/read tokens or logged-in admin
            $ok = is_user_logged_in() && current_user_can('manage_options');
            $admin_key = (string) ($request->get_header('X-TMON-ADMIN') ?? '');
            $hub_key = (string) ($request->get_header('X-TMON-HUB') ?? '');
            $read_tok = (string) ($request->get_header('X-TMON-READ') ?? '');
            if (!$ok) {
                $exp_admin = get_option('tmon_uc_admin_key');
                $exp_hub   = get_option('tmon_uc_hub_shared_key');
                $exp_read  = get_option('tmon_uc_hub_read_token');
                if ($exp_admin && hash_equals($exp_admin, $admin_key)) $ok = true;
                if (!$ok && $exp_hub && hash_equals($exp_hub, $hub_key)) $ok = true;
                if (!$ok && $exp_read && hash_equals($exp_read, $read_tok)) $ok = true;
            }
            if (!$ok) return new WP_REST_Response(['status'=>'forbidden'], 403);

            $unit_id = sanitize_text_field($request->get_param('unit_id'));
            $machine_id = sanitize_text_field($request->get_param('machine_id'));
            global $wpdb;
            uc_devices_ensure_table();
            $table = $wpdb->prefix . 'tmon_uc_devices';
            $row = null;
            if ($unit_id) {
                $row = $wpdb->get_row($wpdb->prepare("SELECT staged_settings, staged_at FROM {$table} WHERE unit_id=%s LIMIT 1", $unit_id), ARRAY_A);
            } elseif ($machine_id) {
                $row = $wpdb->get_row($wpdb->prepare("SELECT staged_settings, staged_at FROM {$table} WHERE machine_id=%s LIMIT 1", $machine_id), ARRAY_A);
            }
            if (!$row || empty($row['staged_settings'])) {
                return rest_ensure_response(['status'=>'ok','staged'=>false,'settings'=>[]]);
            }
            $json = json_decode($row['staged_settings'], true);
            if (!is_array($json)) $json = [];
            return rest_ensure_response(['status'=>'ok','staged'=>true,'staged_at'=>$row['staged_at'],'settings'=>$json]);
        },
        'permission_callback' => '__return_true',
    ]);

    register_rest_route('tmon/v1', '/admin/device/settings-applied', [
        'methods' => 'POST',
        'callback' => function($request){
            // same auth as above
            $ok = is_user_logged_in() && current_user_can('manage_options');
            $admin_key = (string) ($request->get_header('X-TMON-ADMIN') ?? '');
            $hub_key = (string) ($request->get_header('X-TMON-HUB') ?? '');
            $read_tok = (string) ($request->get_header('X-TMON-READ') ?? '');
            if (!$ok) {
                $exp_admin = get_option('tmon_uc_admin_key');
                $exp_hub   = get_option('tmon_uc_hub_shared_key');
                $exp_read  = get_option('tmon_uc_hub_read_token');
                if ($exp_admin && hash_equals($exp_admin, $admin_key)) $ok = true;
                if (!$ok && $exp_hub && hash_equals($exp_hub, $hub_key)) $ok = true;
                if (!$ok && $exp_read && hash_equals($exp_read, $read_tok)) $ok = true;
            }
            if (!$ok) return new WP_REST_Response(['status'=>'forbidden'], 403);

            $unit_id = sanitize_text_field($request->get_param('unit_id'));
            $machine_id = sanitize_text_field($request->get_param('machine_id'));
            $firmware = sanitize_text_field($request->get_param('firmware_version'));
            $role = sanitize_text_field($request->get_param('role'));
            global $wpdb;
            uc_devices_ensure_table();
            $table = $wpdb->prefix . 'tmon_uc_devices';
            if ($unit_id) {
                $wpdb->update($table, ['staged_settings'=>null], ['unit_id'=>$unit_id]);
            } elseif ($machine_id) {
                $wpdb->update($table, ['staged_settings'=>null], ['machine_id'=>$machine_id]);
            }
            // Optional: audit/log
            do_action('tmon_uc_settings_applied', ['unit_id'=>$unit_id,'machine_id'=>$machine_id,'firmware'=>$firmware,'role'=>$role]);
            return rest_ensure_response(['status'=>'ok']);
        },
        'permission_callback' => '__return_true',
    ]);

    // Devices list: assigned/unassigned, basic filters
    register_rest_route('tmon/v1', '/admin/devices', [
        'methods' => 'GET',
        'callback' => function($request){
            // auth: allow read token/hub/admin or logged-in admin
            $ok = is_user_logged_in() && current_user_can('manage_options');
            $admin_key = (string) ($request->get_header('X-TMON-ADMIN') ?? '');
            $hub_key = (string) ($request->get_header('X-TMON-HUB') ?? '');
            $read_tok = (string) ($request->get_header('X-TMON-READ') ?? '');
            if (!$ok) {
                $exp_admin = get_option('tmon_uc_admin_key');
                $exp_hub   = get_option('tmon_uc_hub_shared_key');
                $exp_read  = get_option('tmon_uc_hub_read_token');
                if ($exp_admin && hash_equals($exp_admin, $admin_key)) $ok = true;
                if (!$ok && $exp_hub && hash_equals($exp_hub, $hub_key)) $ok = true;
                if (!$ok && $exp_read && hash_equals($exp_read, $read_tok)) $ok = true;
            }
            if (!$ok) return new WP_REST_Response(['status'=>'forbidden'], 403);

            $assigned = strtolower(sanitize_text_field($request->get_param('assigned') ?? 'all'));
            $limit = max(1, min(500, intval($request->get_param('limit') ?? 100)));
            $offset = max(0, intval($request->get_param('offset') ?? 0));
            $rows = $assigned === '1'
                ? uc_devices_get_assigned(['limit'=>$limit,'offset'=>$offset,'assigned_only'=>true])
                : ($assigned === '0'
                    ? uc_devices_get_unassigned(['limit'=>$limit,'offset'=>$offset])
                    : uc_devices_get_assigned(['limit'=>$limit,'offset'=>$offset,'assigned_only'=>false]));
            return rest_ensure_response(['status'=>'ok','devices'=>$rows]);
        },
        'permission_callback' => '__return_true',
    ]);
});

// Commands staging: REST API
add_action('rest_api_init', function(){
	// Admin -> UC: stage a command for a device
	register_rest_route('tmon/v1', '/admin/device/command', [
		'methods' => 'POST',
		'callback' => function($request){
			// Auth via hub/admin/read tokens or logged-in admin
			$ok = is_user_logged_in() && current_user_can('manage_options');
			$admin_key = (string) ($request->get_header('X-TMON-ADMIN') ?? '');
			$hub_key   = (string) ($request->get_header('X-TMON-HUB') ?? '');
			$read_tok  = (string) ($request->get_header('X-TMON-READ') ?? '');
			if (!$ok) {
				$exp_admin = get_option('tmon_uc_admin_key');
				$exp_hub   = get_option('tmon_uc_hub_shared_key');
				$exp_read  = get_option('tmon_uc_hub_read_token');
				if ($exp_admin && hash_equals($exp_admin, $admin_key)) $ok = true;
				if (!$ok && $exp_hub && hash_equals($exp_hub, $hub_key)) $ok = true;
				if (!$ok && $exp_read && hash_equals($exp_read, $read_tok)) $ok = true;
			}
			if (!$ok) return new WP_REST_Response(['status'=>'forbidden'], 403);

			$unit_id = sanitize_text_field($request->get_param('unit_id'));
			$command = sanitize_text_field($request->get_param('command')); // e.g., relay_ctrl
			$params  = $request->get_param('params'); // array, e.g., {'relay':1,'state':'on'}
			if (!$unit_id || !$command || !is_array($params)) {
				return new WP_REST_Response(['status'=>'error','message'=>'unit_id, command, params required'], 400);
			}
			global $wpdb;
			$table = $wpdb->prefix . 'tmon_device_commands';
			$wpdb->query("CREATE TABLE IF NOT EXISTS {$table} (
				id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
				device_id VARCHAR(64) NOT NULL,
				command VARCHAR(64) NOT NULL,
				params LONGTEXT NULL,
				status VARCHAR(32) DEFAULT 'staged',
				created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
				updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
				PRIMARY KEY (id),
				KEY device_idx (device_id),
				KEY status_idx (status)
			) " . $wpdb->get_charset_collate());
			$wpdb->insert($table, [
				'device_id' => $unit_id,
				'command'   => $command,
				'params'    => wp_json_encode($params),
				'status'    => 'staged',
			]);
			return rest_ensure_response(['status'=>'ok','id'=>$wpdb->insert_id]);
		},
		'permission_callback' => '__return_true',
	]);

	// Device -> UC: poll staged commands
	register_rest_route('tmon/v1', '/device/commands', [
		'methods' => 'GET',
		'callback' => function($request){
			$unit_id = sanitize_text_field($request->get_param('unit_id'));
			if (!$unit_id) return new WP_REST_Response(['status'=>'error','message'=>'unit_id required'], 400);
			global $wpdb;
			$table = $wpdb->prefix . 'tmon_device_commands';
			$rows = $wpdb->get_results($wpdb->prepare("SELECT id,command,params FROM {$table} WHERE device_id=%s AND status='staged' ORDER BY id ASC LIMIT 50", $unit_id), ARRAY_A);
			$out = [];
			foreach ($rows as $r) {
				$params = json_decode($r['params'], true);
				if (!is_array($params)) $params = [];
				$out[] = ['id'=>intval($r['id']),'command'=>$r['command'],'params'=>$params];
			}
			return rest_ensure_response(['status'=>'ok','commands'=>$out]);
		},
		'permission_callback' => '__return_true',
	]);

	// Device -> UC: confirm command applied
	register_rest_route('tmon/v1', '/device/command/confirm', [
		'methods' => 'POST',
		'callback' => function($request){
			$unit_id = sanitize_text_field($request->get_param('unit_id'));
			$cmd_id  = intval($request->get_param('id'));
			$ok      = (bool)$request->get_param('ok');
			global $wpdb;
			$table = $wpdb->prefix . 'tmon_device_commands';
			if ($cmd_id > 0) {
				$wpdb->update($table, [
					'status' => $ok ? 'applied' : 'failed',
					'updated_at' => current_time('mysql'),
				], ['id' => $cmd_id, 'device_id' => $unit_id]);
			}
			// Optionally notify Admin hub (best-effort)
			$hub = trim(get_option('tmon_uc_hub_url', ''));
			$hub_key = get_option('tmon_uc_hub_shared_key', '');
			if ($hub && $hub_key) {
				$endpoint = rtrim($hub, '/') . '/wp-json/tmon-admin/v1/uc/command/confirm';
				$payload = ['unit_id'=>$unit_id,'id'=>$cmd_id,'ok'=>$ok];
				wp_remote_post($endpoint, ['timeout'=>10,'headers'=>['Content-Type'=>'application/json','X-TMON-HUB'=>$hub_key],'body'=>wp_json_encode($payload)]);
			}
			return rest_ensure_response(['status'=>'ok']);
		},
		'permission_callback' => '__return_true',
	]);
});

// Schedule periodic refresh from Admin hub (best-effort backfill)
add_action('init', function() {
    if (!wp_next_scheduled('tmon_uc_refresh_from_admin_event')) {
        wp_schedule_event(time() + 60, 'hourly', 'tmon_uc_refresh_from_admin_event');
    }
});
add_action('tmon_uc_refresh_from_admin_event', function() {
    // Backfill UC mirror from Admin hub
    uc_devices_refresh_from_admin();
});

// Manual refresh trigger from settings page
add_action('admin_post_tmon_uc_refresh_devices', function(){
    if (!current_user_can('manage_options')) wp_die('Insufficient permissions');
    check_admin_referer('tmon_uc_refresh_devices');
    uc_devices_refresh_from_admin();
    wp_safe_redirect(add_query_arg(['tmon_refresh'=>'1'], admin_url('admin.php?page=tmon-settings')));
    exit;
});

// Helper: normalize URL to canonical host[:port]
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
