<?php
// Unit Connector API for remote install/update orchestrated by TMON Admin
add_action('rest_api_init', function(){
    register_rest_route('tmon/v1', '/uc/pull-install', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_pull_install',
        'permission_callback' => '__return_true',
    ]);
});

function tmon_uc_pull_install($request){
    if (!current_user_can('manage_options')) return new WP_REST_Response(['status'=>'forbidden'], 403);
    $payload = $request->get_param('payload');
    $sig = $request->get_param('sig');
    // Optional: require an Authorization bearer (JWT or Application Password) at the spoke
    $require_auth = defined('TMON_UC_PULL_REQUIRE_AUTH') ? TMON_UC_PULL_REQUIRE_AUTH : false;
    if ($require_auth) {
        $auth = isset($_SERVER['HTTP_AUTHORIZATION']) ? $_SERVER['HTTP_AUTHORIZATION'] : '';
        if (!$auth) return new WP_REST_Response(['status'=>'forbidden','message'=>'Missing Authorization'], 403);
    }
    if (!$payload || !$sig) return rest_ensure_response(['status'=>'error','message'=>'Missing payload or sig']);
    $secret = defined('TMON_HUB_SHARED_SECRET') ? TMON_HUB_SHARED_SECRET : wp_salt('auth');
    $calc = hash_hmac('sha256', wp_json_encode($payload), $secret);
    if (!hash_equals($calc, $sig)) return new WP_REST_Response(['status'=>'forbidden'], 403);
    $package_url = esc_url_raw($payload['package_url'] ?? '');
    // Enforce HTTPS package URL
    if (stripos($package_url, 'https://') !== 0) {
        return rest_ensure_response(['status'=>'error','message'=>'HTTPS required for package_url']);
    }
    // Optional: pin package hash via payload['sha256']
    $expected_hash = isset($payload['sha256']) ? strtolower(sanitize_text_field($payload['sha256'])) : '';
    $action = sanitize_text_field($payload['action'] ?? 'install');
    $callback = esc_url_raw($payload['callback'] ?? '');
    if (!$package_url) return rest_ensure_response(['status'=>'error','message'=>'Missing package_url']);

    // Download and install plugin package
    include_once ABSPATH . 'wp-admin/includes/file.php';
    include_once ABSPATH . 'wp-admin/includes/misc.php';
    include_once ABSPATH . 'wp-admin/includes/class-wp-upgrader.php';
    include_once ABSPATH . 'wp-admin/includes/plugin.php';
    WP_Filesystem();
    $upgrader = new Plugin_Upgrader();
    // If hash pinning requested, pre-download and validate
    $result = null;
    if ($expected_hash) {
        $tmp = download_url($package_url);
        if (is_wp_error($tmp)) {
            $result = $tmp;
        } else {
            $data = file_get_contents($tmp);
            $hash = strtolower(hash('sha256', $data));
            if ($hash !== $expected_hash) {
                @unlink($tmp);
                return rest_ensure_response(['status'=>'error','message'=>'Package hash mismatch']);
            }
            $result = $upgrader->install($tmp, ['overwrite_package' => ($action === 'update')]);
        }
    } else {
        $result = $upgrader->install($package_url, ['overwrite_package' => ($action === 'update')]);
    }
    $status = 'ok';
    $details = $result;
    // Activate plugin if install went through and plugin main exists (best-effort)
    if ($result && is_wp_error($result) === false) {
        // Try to find plugin main
        $plugins = get_plugins();
        foreach ($plugins as $file => $data) {
            if (stripos($file, 'tmon-unit-connector.php') !== false) {
                activate_plugin($file);
                break;
            }
        }
    } else {
        $status = 'error';
    }
    // Confirm back to TMON Admin hub
    if ($callback) {
        wp_remote_post($callback, [
            'timeout' => 10,
            'headers' => ['Content-Type'=>'application/json'],
            'body' => wp_json_encode([
                'site_url' => home_url(),
                'status' => $status,
                'details' => is_wp_error($result) ? $result->get_error_message() : $details,
            ]),
        ]);
    }
    return rest_ensure_response(['status' => $status]);
});

// Register REST routes for staged settings
add_action('rest_api_init', function() {
	// GET staged settings for a unit (used by device or admin)
	register_rest_route('tmon/v1', '/device/staged-settings', array(
		'methods'  => 'GET',
		'callback' => function(\WP_REST_Request $req) {
			$unit = sanitize_text_field($req->get_param('unit_id') ?: $req->get_param('machine_id') ?: '');
			if (!$unit) {
				return new WP_REST_Response(array('staged_exists' => false, 'staged' => null), 200);
			}
			$map = get_option('tmon_uc_staged_settings', array());
			$entry = is_array($map) && isset($map[$unit]) ? $map[$unit] : null;
			if (!$entry) {
				return new WP_REST_Response(array('staged_exists' => false, 'staged' => null), 200);
			}
			return new WP_REST_Response(array('staged_exists' => true, 'staged' => $entry['settings'], 'meta' => array('ts' => $entry['ts'], 'who' => $entry['who'] ?? '')), 200);
		},
		'permission_callback' => '__return_true' // allow devices / anonymous to GET (tokenized channels may layer on this)
	));

	// POST staged settings (admin UI -> stage settings for a unit)
	register_rest_route('tmon/v1', '/admin/device/settings-staged', array(
		'methods'  => 'POST',
		'callback' => function(\WP_REST_Request $req) {
			if (!current_user_can('manage_options')) {
				return new WP_Error('forbidden', 'Insufficient permissions', array('status' => 403));
			}
			$body = $req->get_json_params();
			$unit = sanitize_text_field($body['unit_id'] ?? '');
			$settings = isset($body['settings']) && is_array($body['settings']) ? $body['settings'] : array();
			if (!$unit || !$settings) {
				return new WP_Error('invalid', 'unit_id and settings are required', array('status' => 400));
			}
			// Merge/overwrite permitted keys only (server-side sanitization)
			$allowed = apply_filters('tmon_staged_settings_allowed_keys', array(
				'NODE_TYPE','UNIT_Name','SAMPLE_TEMP','SAMPLE_HUMID','SAMPLE_BAR','ENABLE_OLED','ENGINE_ENABLED',
				'RELAY_PIN1','RELAY_PIN2','RELAY_RUNTIME_LIMITS','WIFI_SSID','WIFI_PASS','ENABLE_sensorBME280',
				'ENABLE_WIFI','ENABLE_LORA','DEVICE_SUSPENDED','FIELD_DATA_HMAC_ENABLED','FIELD_DATA_HMAC_SECRET'
			));
			$safe = array();
			foreach ($settings as $k => $v) {
				if (in_array($k, $allowed, true)) {
					// Coerce simple types: boolean strings -> bool
					if (is_string($v) && in_array(strtolower($v), array('true','false','1','0','yes','no'), true)) {
						$v_l = strtolower($v);
						$v = in_array($v_l, array('true','1','yes'), true);
					}
					$safe[$k] = $v;
				}
			}
			$map = get_option('tmon_uc_staged_settings', array());
			if (!is_array($map)) $map = array();
			$map[$unit] = array('settings' => $safe, 'ts' => current_time('timestamp'), 'who' => wp_get_current_user()->user_login);
			update_option('tmon_uc_staged_settings', $map);
			// For audit & discoverability, also write a transient for quick admin UI access
			do_action('tmon_staged_settings_updated', $unit, $safe);
			return new WP_REST_Response(array('ok' => true, 'unit_id' => $unit, 'settings' => $safe), 200);
		},
		'permission_callback' => function() { return current_user_can('manage_options'); }
	));
});
