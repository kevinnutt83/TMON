<?php
// TMON Admin REST API Endpoints

// Shared helper to push UC install/update payloads (reused by REST + admin page)
if (!function_exists('tmon_admin_uc_push_request')) {
    function tmon_admin_uc_push_request($site_url, $package_url, $action = 'install', $auth = '', $sha256 = '') {
        $site_url = esc_url_raw($site_url);
        $package_url = esc_url_raw($package_url);
        $action = $action ? sanitize_text_field($action) : 'install';
        $sha256 = $sha256 ? sanitize_text_field($sha256) : '';
        if (!$site_url || !$package_url) {
            return new WP_Error('missing_params', 'site_url and package_url are required');
        }
        // Construct signed payload
        $secret = defined('TMON_HUB_SHARED_SECRET') ? TMON_HUB_SHARED_SECRET : wp_salt('auth');
        $payload = [
            'ts' => time(),
            'action' => $action,
            'package_url' => $package_url,
            'callback' => rest_url('tmon-admin/v1/uc/confirm'),
        ];
        if ($sha256) { $payload['sha256'] = $sha256; }
        $sig = hash_hmac('sha256', wp_json_encode($payload), $secret);
        $endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/uc/pull-install';
        $resp = wp_remote_post($endpoint, [
            'timeout' => 20,
            'headers' => array_filter(['Content-Type'=>'application/json','Authorization' => $auth ? $auth : '']),
            'body' => wp_json_encode(['payload'=>$payload,'sig'=>$sig]),
        ]);
        if (is_wp_error($resp)) return $resp;
        $code = wp_remote_retrieve_response_code($resp);
        $body = wp_remote_retrieve_body($resp);
        return [
            'success' => in_array($code, [200,201], true),
            'code' => $code,
            'body' => $body,
        ];
    }
}

// Helper: generate a unique unit_id when a device checks in without one
if (!function_exists('tmon_admin_generate_unique_unit_id')) {
    function tmon_admin_generate_unique_unit_id($length = 6, $prefix = 'unit-') {
        global $wpdb;
        $length = max(4, intval($length));
        $table  = $wpdb->prefix . 'tmon_devices';
        $tries  = 0;
        while ($tries < 8) {
            $candidate = $prefix . strtolower(wp_generate_password($length, false, false));
            $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM {$table} WHERE unit_id = %s", $candidate));
            if (intval($exists) === 0) {
                return $candidate;
            }
            $tries++;
        }
        // Fallback: timestamp-based to avoid hard failure
        return $prefix . time();
    }
}

add_action('rest_api_init', function() {
    register_rest_route('tmon-admin/v1', '/status', [
        'methods' => 'GET',
        'callback' => function() {
            return ['status' => 'ok', 'time' => current_time('mysql')];
        },
        'permission_callback' => '__return_true',
    ]);

    // Aggregate field data from paired Unit Connectors for Admin UI
    register_rest_route('tmon-admin/v1', '/field-data', [
        'methods' => 'GET',
        'permission_callback' => function(){ return current_user_can('manage_options'); },
        'callback' => function($request){
            $hours = intval($request->get_param('hours') ?? 24);
            if ($hours <= 0) $hours = 24;
            $limit = intval($request->get_param('limit') ?? 500);
            $limit = max(1, min(5000, $limit));
            $unit_id = sanitize_text_field($request->get_param('unit_id') ?? '');
            $sites = get_option('tmon_admin_uc_sites', []);
            if (!is_array($sites) || empty($sites)) {
                return rest_ensure_response(['rows'=>[]]);
            }
            $all = [];
            foreach ($sites as $site_url => $meta) {
                $read_token = $meta['read_token'] ?? '';
                if (!$site_url) continue;
                $endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/field-data?hours=' . intval($hours) . '&limit=' . intval($limit) . ($unit_id? ('&unit_id='.rawurlencode($unit_id)) : '');
                $resp = wp_remote_get($endpoint, [
                    'timeout' => 15,
                    'headers' => array_filter([
                        'Accept' => 'application/json',
                        // Prefer dedicated read token if set; fall back to hub key
                        'X-TMON-READ' => $read_token ?: '',
                        'X-TMON-HUB'  => get_option('tmon_admin_uc_key') ?: '',
                    ]),
                ]);
                if (is_wp_error($resp)) continue;
                $code = wp_remote_retrieve_response_code($resp);
                if ($code !== 200) continue;
                $body = json_decode(wp_remote_retrieve_body($resp), true);
                if (is_array($body) && isset($body['rows']) && is_array($body['rows'])) {
                    foreach ($body['rows'] as $row) {
                        if (is_array($row)) { $row['__site'] = $site_url; $all[] = $row; }
                    }
                }
            }
            // Normalize a consistent display name on each row
            foreach ($all as &$row) {
                if (is_array($row)) {
                    if (empty($row['name'])) {
                        $row['name'] = !empty($row['unit_name']) ? $row['unit_name'] : (!empty($row['unit_id']) ? $row['unit_id'] : '');
                    }
                }
            }
            unset($row);
            // Sort by ts_iso desc
            usort($all, function($a,$b){
                $ta = isset($a['ts_iso']) ? strtotime($a['ts_iso']) : 0;
                $tb = isset($b['ts_iso']) ? strtotime($b['ts_iso']) : 0;
                return $tb <=> $ta;
            });
            return rest_ensure_response(['rows'=>$all]);
        }
    ]);

    // Push GPS override to a device via UC (used by provisioning/location tools)
    register_rest_route('tmon-admin/v1', '/device/gps-override', [
        'methods' => 'POST',
        'permission_callback' => function(){ return current_user_can('manage_options'); },
        'callback' => function($request){
            $site_url = esc_url_raw($request->get_param('site_url'));
            $unit_id = sanitize_text_field($request->get_param('unit_id'));
            $lat = $request->get_param('gps_lat');
            $lng = $request->get_param('gps_lng');
            $alt = $request->get_param('gps_alt_m');
            $acc = $request->get_param('gps_accuracy_m');
            if (!function_exists('tmon_admin_push_location_settings')) {
                return new WP_REST_Response(['success'=>false,'message'=>'Location helper unavailable'], 500);
            }
            $result = tmon_admin_push_location_settings($site_url, $unit_id, $lat, $lng, $alt, $acc);
            if (is_wp_error($result)) {
                $code = $result->get_error_code() === 'forbidden' ? 403 : 400;
                return new WP_REST_Response(['success'=>false,'message'=>$result->get_error_message()], $code);
            }
            return rest_ensure_response([
                'success' => true,
                'code' => isset($result['code']) ? intval($result['code']) : 200,
                'body' => $result['body'] ?? '',
            ]);
        }
    ]);
    // Public claim request endpoint (authenticated user recommended)
    register_rest_route('tmon-admin/v1', '/claim', [
        'methods' => 'POST',
        'callback' => function($request) {
            if (!is_user_logged_in()) {
                return new WP_REST_Response(['status' => 'error', 'message' => 'Login required'], 401);
            }
            global $wpdb;
            $unit_id = sanitize_text_field($request->get_param('unit_id'));
            $machine_id = sanitize_text_field($request->get_param('machine_id'));
            if (!$unit_id || !$machine_id) {
                return rest_ensure_response(['status' => 'error', 'message' => 'Missing unit_id or machine_id']);
            }
            $user_id = get_current_user_id();
            $wpdb->insert($wpdb->prefix.'tmon_claim_requests', [
                'unit_id' => $unit_id,
                'machine_id' => $machine_id,
                'user_id' => $user_id,
                'status' => 'pending',
            ]);
            return rest_ensure_response(['status' => 'ok', 'id' => $wpdb->insert_id]);
        },
        'permission_callback' => '__return_true',
    ]);

    // Ingest unknown device reports from Unit Connectors (auto-provisioning queue)
    register_rest_route('tmon-admin/v1', '/ingest-unknown', [
        'methods' => 'POST',
        'callback' => function($request) {
            global $wpdb;
            $unit_id = sanitize_text_field($request->get_param('unit_id'));
            $machine_id = sanitize_text_field($request->get_param('machine_id'));
            $site_url = esc_url_raw($request->get_param('site_url'));
            if (!$unit_id) return rest_ensure_response(['status' => 'error', 'message' => 'Missing unit_id']);
            // Log to audit for admin review
            $wpdb->insert($wpdb->prefix.'tmon_audit', [
                'user_id' => 0,
                'action' => 'ingest_unknown_device',
                'details' => wp_json_encode(['unit_id' => $unit_id, 'machine_id' => $machine_id, 'site_url' => $site_url])
            ]);
            // Optionally, create a pending provision record if not exists
            $prov = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM {$wpdb->prefix}tmon_provisioned_devices WHERE unit_id=%s", $unit_id));
            if (!$prov) {
                $wpdb->insert($wpdb->prefix.'tmon_provisioned_devices', [
                    'unit_id' => $unit_id,
                    'machine_id' => $machine_id,
                    'status' => 'pending',
                    'notes' => 'auto-ingested from ' . $site_url,
                ]);
            }
            return rest_ensure_response(['status' => 'ok']);
        },
        'permission_callback' => '__return_true',
    ]);

    // Proxy claim endpoint: UC forwards claims here using shared hub key header
    register_rest_route('tmon-admin/v1', '/proxy/claim', [
        'methods' => 'POST',
        'permission_callback' => '__return_true',
        'callback' => function($request) {
            // Authenticate via shared hub key
            $expected = get_option('tmon_admin_uc_key', '');
            $provided = '';
            if (function_exists('getallheaders')) {
                $headers = getallheaders();
                $provided = $headers['X-TMON-HUB'] ?? ($headers['x-tmon-hub'] ?? '');
            } else {
                $provided = $_SERVER['HTTP_X_TMON_HUB'] ?? '';
            }
            if (!$expected || !$provided || !hash_equals((string)$expected, (string)$provided)) {
                return new WP_REST_Response(['status' => 'forbidden', 'message' => 'Invalid hub key'], 403);
            }
            // Accept claim parameters
            $unit_id = sanitize_text_field($request->get_param('unit_id'));
            $machine_id = sanitize_text_field($request->get_param('machine_id'));
            $user_hint = sanitize_text_field($request->get_param('user_hint'));
            $site_url = esc_url_raw($request->get_param('site_url'));
            if (!$unit_id || !$machine_id) {
                return new WP_REST_Response(['status' => 'error', 'message' => 'unit_id and machine_id required', 'request' => $request->get_params()], 400);
            }
            global $wpdb;
            $wpdb->insert($wpdb->prefix.'tmon_claim_requests', [
                'unit_id' => $unit_id,
                'machine_id' => $machine_id,
                'user_id' => 0,
                'status' => 'pending',
                'notes' => sprintf('via proxy from %s %s', $site_url ?: 'unknown', $user_hint ? ('user: '.$user_hint) : ''),
            ]);
            return rest_ensure_response(['status' => 'ok', 'id' => $wpdb->insert_id]);
        }
    ]);

    // UC remote install/update request: Admin → UC
    register_rest_route('tmon-admin/v1', '/uc/push', [
        'methods' => 'POST',
        'callback' => function($request){
            if (!current_user_can('manage_options')) return new WP_REST_Response(['status'=>'forbidden'], 403);
            $site_url = esc_url_raw($request->get_param('site_url'));
            $package_url = esc_url_raw($request->get_param('package_url'));
            $action = sanitize_text_field($request->get_param('action') ?: 'install'); // install|update
            $sha256 = sanitize_text_field($request->get_param('sha256') ?: '');
            $auth = $request->get_param('auth'); // optional Authorization header value for spoke
            $result = function_exists('tmon_admin_uc_push_request') ? tmon_admin_uc_push_request($site_url, $package_url, $action, $auth, $sha256) : new WP_Error('missing_helper', 'Push helper unavailable');
            if (is_wp_error($result)) {
                return new WP_REST_Response(['status'=>'error','message'=>$result->get_error_message()], 400);
            }
            return rest_ensure_response([
                'status' => $result['success'] ? 'ok' : 'error',
                'code' => $result['code'],
                'response' => $result['body'],
            ]);
        },
        'permission_callback' => '__return_true',
    ]);

    // UC confirms back
    register_rest_route('tmon-admin/v1', '/uc/confirm', [
        'methods' => 'POST',
        'callback' => function($request){
            $site_url = esc_url_raw($request->get_param('site_url'));
            $status = sanitize_text_field($request->get_param('status'));
            $details = $request->get_param('details');
            // Audit
            global $wpdb;
            $wpdb->insert($wpdb->prefix.'tmon_audit', [
                'user_id' => get_current_user_id(),
                'action' => 'uc_confirm',
                'details' => wp_json_encode(['site_url'=>$site_url,'status'=>$status,'details'=>$details])
            ]);
            return rest_ensure_response(['status' => 'ok']);
        },
        'permission_callback' => '__return_true',
    ]);

    // Pairing: UC calls hub; hub saves mapping and responds with hub_key
    register_rest_route('tmon-admin/v1', '/uc/pair', [
        'methods' => 'POST',
        'permission_callback' => '__return_true',
        'callback' => function($request){
            $site_url = esc_url_raw($request->get_param('site_url'));
            $norm_url = function_exists('tmon_admin_normalize_url') ? tmon_admin_normalize_url($site_url) : $site_url;
            $uc_key = sanitize_text_field($request->get_param('uc_key'));
            if (!$site_url || !$uc_key) return new WP_REST_Response(['status'=>'error','message'=>'site_url and uc_key required'], 400);
            // Persist mapping in options (simple store)
            $map = get_option('tmon_admin_uc_sites', []);
            if (!is_array($map)) $map = [];
            // Generate a per-UC read token for listing devices securely from hub
            $existing = isset($map[$site_url]) ? $map[$site_url] : [];
            $read_token = isset($existing['read_token']) ? $existing['read_token'] : '';
            if (!$read_token) {
                try { $read_token = bin2hex(random_bytes(24)); } catch (Exception $e) { $read_token = wp_generate_password(48, false, false); }
            }
            $map[$site_url] = [
                'uc_key' => $uc_key,
                'paired_at' => current_time('mysql'),
                'read_token' => $read_token,
            ];
            update_option('tmon_admin_uc_sites', $map);
            // Return hub key for UC to store
            $hub_key = get_option('tmon_admin_uc_key');
            if (!$hub_key) {
                try { $hub_key = bin2hex(random_bytes(24)); } catch (Exception $e) { $hub_key = wp_generate_password(48, false, false); }
                update_option('tmon_admin_uc_key', $hub_key);
            }
            // Also persist in tmon_uc_sites table for UI listings
            if (function_exists('tmon_admin_ensure_tables')) { tmon_admin_ensure_tables(); }
            global $wpdb;
            $uc_table = $wpdb->prefix . 'tmon_uc_sites';
            if ($wpdb && $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $uc_table))) {
                $now = current_time('mysql');
                $wpdb->replace($uc_table, [
                    'normalized_url' => $norm_url,
                    'uc_key' => $uc_key,
                    'hub_key' => $hub_key,
                    'read_token' => $read_token,
                    'last_seen' => $now,
                    'created_at' => $now,
                    'updated_at' => $now,
                ]);
            }
            return rest_ensure_response(['status'=>'ok','hub_key'=>$hub_key, 'read_token'=>$read_token]);
        }
    ]);

    // Read-only: list provisioned devices for Unit Connector (authenticated via hub shared key)
    register_rest_route('tmon-admin/v1', '/provisioned-devices', [
        'methods' => 'GET',
        'permission_callback' => '__return_true',
        'callback' => function($request){
            // Authenticate via shared hub key in header X-TMON-HUB
            $expected = get_option('tmon_admin_uc_key', '');
            $provided = '';
            if (function_exists('getallheaders')) {
                $headers = getallheaders();
                $provided = $headers['X-TMON-HUB'] ?? ($headers['x-tmon-hub'] ?? '');
            } else {
                $provided = $_SERVER['HTTP_X_TMON_HUB'] ?? '';
            }
            if (!$expected || !$provided || !hash_equals((string)$expected, (string)$provided)) {
                return new WP_REST_Response(['status'=>'forbidden','message'=>'Invalid hub key'], 403);
            }
            global $wpdb;
            $table = $wpdb->prefix.'tmon_provisioned_devices';
            $exists = $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table));
            if (!$exists) {
                return rest_ensure_response(['status'=>'ok', 'devices'=>[]]);
            }
            $rows = $wpdb->get_results("SELECT id, unit_id, machine_id, role, company_id, plan, status, notes, created_at, updated_at FROM $table ORDER BY created_at DESC", ARRAY_A);
            return rest_ensure_response(['status'=>'ok', 'devices'=> is_array($rows)? $rows : []]);
        }
    ]);

    // Purge data (Admin side): dangerous operations to clean up data; protected by manage_options
    register_rest_route('tmon-admin/v1', '/purge/all', [
        'methods' => 'POST',
        'permission_callback' => function() { return current_user_can('manage_options'); },
        'callback' => function($request){
            global $wpdb;
            // Provisioning and claims
            $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_provisioned_devices");
            $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_claim_requests");
            // Audit log
            $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_audit");
            // Device registry copy (if present here)
            if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $wpdb->prefix.'tmon_devices'))) {
                $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_devices");
            }
            return rest_ensure_response(['status' => 'ok']);
        }
    ]);

    // Proxy GitHub manifest for admin UI to fetch firmware metadata from micropython repo
    register_rest_route('tmon-admin/v1', '/github/manifest', [
        'methods' => 'GET',
        'permission_callback' => '__return_true', // admin.js requests it from admin pages; keep public if needed
        'callback' => function($wp_request) {
            $repo_raw = trim((string) $wp_request->get_param('repo'));
            if (!$repo_raw) {
                // default to known repo path if missing
                $repo_raw = 'kevinnutt83/TMON';
            }

            // Normalize repo param: accept "org/repo", or a GitHub web URL or a raw path
            $repo = $repo_raw;
            // If full GitHub URL, extract org/repo
            if (stripos($repo_raw, 'github.com') !== false) {
                // examples: https://github.com/org/repo/tree/main/micropython/
                $parts = explode('github.com/', $repo_raw, 2);
                if (count($parts) > 1) {
                    $path = trim($parts[1], '/');
                    // remove "tree/main..." suffix
                    $path = preg_replace('#/tree/[^/]+.*$#', '', $path);
                    $repo = $path;
                }
            }
            // Make raw base URL for micropython folder
            // Prefer 'main' branch by default:
            $base_raw = 'https://raw.githubusercontent.com/' . trim($repo, '/') . '/main/micropython/';
            $manifest_url = $base_raw . 'manifest.json';
            $version_url  = $base_raw . 'version.txt';

            // Attempt manifest.json
            $out = ['success' => false, 'data' => null, 'error' => null];
            // Use WP HTTP to fetch
            $resp = wp_remote_get($manifest_url, ['timeout' => 10, 'headers' => ['Accept'=>'application/json']]);
            if (!is_wp_error($resp) && wp_remote_retrieve_response_code($resp) === 200) {
                $body = wp_remote_retrieve_body($resp);
                $m = json_decode($body, true);
                if (is_array($m)) {
                    $version = $m['version'] ?? ($m['tag'] ?? '');
                    $firmware_url = '';
                    if (!empty($m['firmware'])) {
                        $firmware_url = $base_raw . ltrim($m['firmware'], '/');
                    } elseif (!empty($m['files']) && is_array($m['files'])) {
                        foreach ($m['files'] as $f) {
                            $p = is_array($f) ? ($f['path'] ?? '') : (is_string($f) ? $f : '');
                            if ($p && preg_match('/firmware|\\.bin|\\.hex|\\.img/i', $p)) {
                                $firmware_url = $base_raw . ltrim($p, '/');
                                break;
                            }
                        }
                    }
                    $out['success'] = true;
                    $out['data'] = ['version' => $version ?? '', 'firmware_url' => esc_url_raw($firmware_url)];
                    return rest_ensure_response($out);
                }
            }

            // Fallback to version.txt
            $resp2 = wp_remote_get($version_url, ['timeout' => 10]);
            if (!is_wp_error($resp2) && wp_remote_retrieve_response_code($resp2) === 200) {
                $body2 = trim(wp_remote_retrieve_body($resp2));
                $version_txt = $body2 ?: '';
                $firmware_url_fallback = $base_raw . 'firmware.bin';
                $out['success'] = true;
                $out['data'] = ['version' => $version_txt, 'firmware_url' => esc_url_raw($firmware_url_fallback)];
                return rest_ensure_response($out);
            }

            $out['error'] = 'manifest or version file not found';
            return new WP_REST_Response($out, 404);
        }
    ]);
});

// Authorization: decide if a device is allowed to post data (fee-for-service, provisioning, etc.)
add_filter('tmon_admin_authorize_device', function($allowed, $unit_id, $machine_id) {
    // Policy: require a matching provisioned record and not suspended/expired
    global $wpdb;
    $prov = $wpdb->get_row($wpdb->prepare("SELECT plan, status, machine_id FROM {$wpdb->prefix}tmon_provisioned_devices WHERE unit_id=%s", $unit_id));
    if (!$prov) return false;
    if (in_array($prov->status, ['suspended','expired'], true)) return false;
    if (!empty($prov->machine_id) && !empty($machine_id) && $prov->machine_id !== $machine_id) return false;
    // Optional: also ensure device registered table exists and not suspended there
    $row = $wpdb->get_row($wpdb->prepare("SELECT suspended FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $unit_id));
    if ($row && intval($row->suspended) === 1) return false;
    return true;
}, 10, 3);

// Receive field data forwarded by unit-connector and perform admin-side tasks
add_action('tmon_admin_receive_field_data', function($unit_id, $rec) {
    global $wpdb;
    // Upsert device name and last_seen
    $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $unit_id));
    if (!$exists) {
        $wpdb->insert($wpdb->prefix.'tmon_devices', [
            'unit_id' => $unit_id,
            'unit_name' => isset($rec['name']) ? sanitize_text_field($rec['name']) : $unit_id,
            'last_seen' => current_time('mysql'),
            'suspended' => 0,
        ]);
    } else {
        $update = ['last_seen' => current_time('mysql')];
        if (!empty($rec['name'])) {
            $update['unit_name'] = sanitize_text_field($rec['name']);
        }
        $wpdb->update($wpdb->prefix.'tmon_devices', $update, ['unit_id' => $unit_id]);
    }

    // TODO: tie into company/unit association tables when present
}, 10, 2);

// REST: Device check-in (first boot and recurring)
add_action('rest_api_init', function () {
	register_rest_route('tmon-admin/v1', '/device/check-in', [
		'methods'             => 'POST',
		'callback'            => 'tmon_admin_handle_device_check_in',
		'permission_callback' => '__return_true',
	]);
});

if (!function_exists('tmon_admin_handle_device_check_in')) {
	function tmon_admin_handle_device_check_in(WP_REST_Request $request) {
		global $wpdb;
		$params     = $request->get_json_params();
		$machine_id = isset($params['machine_id']) ? sanitize_text_field($params['machine_id']) : '';
		$unit_id    = isset($params['unit_id']) ? sanitize_text_field($params['unit_id']) : '';

		if (!$machine_id) {
			return new WP_REST_Response(['error' => 'machine_id required'], 400);
		}

		// Normalize (optional)
		$norm_machine = function_exists('tmon_admin_normalize_mac') ? tmon_admin_normalize_mac($machine_id) : strtolower($machine_id);
		$norm_unit    = function_exists('tmon_admin_normalize_key') ? tmon_admin_normalize_key($unit_id) : strtolower($unit_id);

		$table  = $wpdb->prefix . 'tmon_devices';
		$device = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table} WHERE machine_id = %s", $machine_id));

		if (!$device) {
			$unit_id  = tmon_admin_generate_unique_unit_id();
			$inserted = $wpdb->insert(
				$table,
				[
					'machine_id'  => $machine_id,
					'unit_id'     => $unit_id,
					'provisioned' => 0,
					'suspended'   => 0,
					'created_at'  => current_time('mysql'),
					'updated_at'  => current_time('mysql'),
					'last_seen'   => current_time('mysql'),
				],
				['%s', '%s', '%d', '%d', '%s', '%s', '%s']
			);

			if ($inserted === false) {
				return new WP_REST_Response(['error' => 'db insert failed'], 500);
			}

			do_action('tmon_admin_notify', 'Device registered', ['machine_id' => $machine_id, 'unit_id' => $unit_id]);

			$device = (object) [
				'machine_id'  => $machine_id,
				'unit_id'     => $unit_id,
				'provisioned' => 0,
				'suspended'   => 0,
			];
		} else {
			// Update last_seen on subsequent check-ins
			$wpdb->update($table, ['last_seen' => current_time('mysql')], ['machine_id' => $machine_id]);
		}

		// Existing provisioned logic (assumed):
		$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
		$prov_row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$prov_table} WHERE unit_id=%s OR machine_id=%s LIMIT 1", $unit_id, $machine_id), ARRAY_A);
		$provisioned = !empty($prov_row);

		// NEW: staged + metadata helper
        $staged_meta = function_exists('tmon_admin_get_staged_meta_for_device')
            ? (tmon_admin_get_staged_meta_for_device($machine_id, $unit_id) ?: [])
            : [];

		// Build site URL / wordpress_api_url
		$wordpress_api_url = $staged_meta['site_url'] ?? '';
		if (empty($wordpress_api_url) && !empty($prov_row['site_url'])) {
			$wordpress_api_url = $prov_row['site_url'];
		}

		// Response extension
        $response_extra = [
            'staged_exists'     => (bool) ($staged_meta['staged_exists'] ?? false),
            'wordpress_api_url' => $wordpress_api_url,
            'site_url'          => $wordpress_api_url, // alias for clarity
            'role'              => $staged_meta['role'] ?? ($prov_row['role'] ?? ''),
            'plan'              => $staged_meta['plan'] ?? ($prov_row['plan'] ?? ''),
            'firmware'          => $staged_meta['firmware'] ?? ($prov_row['firmware'] ?? ''),
            'firmware_url'      => $staged_meta['firmware_url'] ?? ($prov_row['firmware_url'] ?? ''),
            'unit_name'         => $staged_meta['unit_name'] ?? ($prov_row['unit_name'] ?? ''),
        ];

		// Merge with existing response
		return new WP_REST_Response(array_merge([
			'provisioned' => $provisioned,
			'unit_id'     => $prov_row['unit_id'] ?? $unit_id,
			'machine_id'  => $machine_id,
			'suspended'   => isset($prov_row['status']) && $prov_row['status'] === 'suspended',
		], $response_extra), 200);
	}
}

// Ensure we don't collide with the UC plugin by using a unique handler name in this plugin.
add_action('wp_ajax_tmon_uc_get_devices', 'tmon_admin_get_devices');

if (!function_exists('tmon_admin_get_devices')) {
	function tmon_admin_get_devices() {
		check_ajax_referer('tmon-admin', 'nonce');
		if (!current_user_can('manage_options')) {
			wp_send_json_error(['message' => 'forbidden'], 403);
		}
		global $wpdb;
		$table = $wpdb->prefix . 'tmon_devices';
		$rows  = $wpdb->get_results(
			"SELECT unit_id, unit_name, company, site, zone, cluster, suspended FROM {$table}",
			ARRAY_A
		);
		if ($rows === null) {
			wp_send_json_error(['message' => 'query failed'], 500);
		}
		wp_send_json_success($rows);
	}
}

// IMPORTANT: Remove any previous function tmon_uc_get_devices() from this file.
// If it exists in older code, delete it rather than aliasing it to avoid redeclare with the UC plugin.

// Wherever you previously called notifications with one arg, update to pass context as second arg:
function tmon_admin_example_event_logger($message, $context = []) {
	do_action('tmon_admin_notify', $message, $context);
}
