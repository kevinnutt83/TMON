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
}

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

    // Accept a device chunk-store snapshot (posted by device firmware or base)
    register_rest_route('tmon/v1', '/admin/chunk-store', [
        'methods' => 'POST',
        'permission_callback' => '__return_true', // we validate hub key inside
        'callback' => function($request) {
            $expected = get_option('tmon_uc_shared_key', '') ?: get_option('tmon_admin_uc_key', '');
            $provided = '';
            if (function_exists('getallheaders')) {
                $h = getallheaders();
                $provided = $h['X-TMON-HUB'] ?? $h['x-tmon-hub'] ?? '';
            } else {
                $provided = $_SERVER['HTTP_X_TMON_HUB'] ?? '';
            }
            if ($expected && !$provided) return new WP_REST_Response(['ok'=>false,'msg'=>'missing hub key'],403);
            if ($expected && !hash_equals((string)$expected, (string)$provided)) return new WP_REST_Response(['ok'=>false,'msg'=>'invalid hub key'],403);

            $params = $request->get_json_params();
            $unit = sanitize_text_field($params['unit_id'] ?? ($params['unit'] ?? 'unknown'));
            $snap = is_array($params) ? $params : [];
            $store = get_option('tmon_uc_chunk_store', []);
            if (!is_array($store)) $store = [];
            $store[$unit] = ['ts' => current_time('mysql'), 'snapshot' => $snap];
            update_option('tmon_uc_chunk_store', $store);
            return rest_ensure_response(['ok'=>true]);
        }
    ]);

    // Accept lora status snapshots
    register_rest_route('tmon/v1', '/admin/lora-status', [
        'methods' => 'POST',
        'permission_callback' => '__return_true',
        'callback' => function($request) {
            $expected = get_option('tmon_uc_shared_key', '') ?: get_option('tmon_admin_uc_key', '');
            $provided = '';
            if (function_exists('getallheaders')) {
                $h = getallheaders();
                $provided = $h['X-TMON-HUB'] ?? $h['x-tmon-hub'] ?? '';
            } else {
                $provided = $_SERVER['HTTP_X_TMON_HUB'] ?? '';
            }
            if ($expected && !$provided) return new WP_REST_Response(['ok'=>false,'msg'=>'missing hub key'],403);
            if ($expected && !hash_equals((string)$expected, (string)$provided)) return new WP_REST_Response(['ok'=>false,'msg'=>'invalid hub key'],403);

            $params = $request->get_json_params();
            $unit = sanitize_text_field($params['unit_id'] ?? ($params['unit'] ?? 'unknown'));
            $snap = is_array($params) ? $params : [];
            $store = get_option('tmon_uc_lora_status', []);
            if (!is_array($store)) $store = [];
            $store[$unit] = ['ts' => current_time('mysql'), 'status' => $snap];
            update_option('tmon_uc_lora_status', $store);
            return rest_ensure_response(['ok'=>true]);
        }
    ]);

    // Accept admin->UC commands: enqueue into local tmon_device_commands table
    register_rest_route('tmon/v1', '/device/command', [
        'methods' => 'POST',
        'permission_callback' => '__return_true',
        'callback' => function($request) {
            // auth: allow either Hub key or WP capability if authenticated
            $expected = get_option('tmon_admin_uc_key', '') ?: get_option('tmon_uc_shared_key', '');
            $provided = '';
            if (function_exists('getallheaders')) {
                $h = getallheaders();
                $provided = $h['X-TMON-HUB'] ?? $h['x-tmon-hub'] ?? '';
            } else {
                $provided = $_SERVER['HTTP_X_TMON_HUB'] ?? '';
            }
            if ($expected && !$provided && !current_user_can('manage_options')) {
                return new WP_REST_Response(['ok'=>false,'msg'=>'forbidden'],403);
            }
            if ($expected && $provided && !hash_equals((string)$expected, (string)$provided)) {
                return new WP_REST_Response(['ok'=>false,'msg'=>'invalid hub key'],403);
            }

            $params = $request->get_json_params();
            $unit = sanitize_text_field($params['unit_id'] ?? ($params['device_id'] ?? ''));
            $cmd  = sanitize_text_field($params['command'] ?? '');
            $data = isset($params['params']) ? $params['params'] : ($params['payload'] ?? []);

            if (!$unit || !$cmd) return new WP_REST_Response(['ok'=>false,'msg'=>'unit_id and command required'],400);

            global $wpdb;
            $table = $wpdb->prefix . 'tmon_device_commands';
            $wpdb->insert($table, [
                'device_id' => $unit,
                'command' => $cmd,
                'params' => wp_json_encode($data),
                'status' => 'queued',
                'created_at' => current_time('mysql'),
            ]);
            return rest_ensure_response(['ok'=>true,'id'=>$wpdb->insert_id]);
        }
    ]);

    // Store a chunk-store snapshot for historical analysis
    register_rest_route('tmon/v1', '/admin/chunk-store-history', [
        'methods' => 'POST',
        'permission_callback' => '__return_true',
        'callback' => function($request) {
            $expected = get_option('tmon_uc_shared_key','') ?: get_option('tmon_admin_uc_key','');
            $provided = $_SERVER['HTTP_X_TMON_HUB'] ?? ($_SERVER['HTTP_X_TMON_ADMIN'] ?? '');
            if ($expected && !hash_equals((string)$expected, (string)$provided)) {
                return new WP_REST_Response(['ok'=>false,'msg'=>'invalid hub key'],403);
            }
            $params = $request->get_json_params();
            $unit = sanitize_text_field($params['unit_id'] ?? ($params['unit'] ?? 'unknown'));
            $payload = wp_json_encode($params);
            global $wpdb;
            $tbl = $wpdb->prefix . 'tmon_uc_lora_snapshots';
            $wpdb->insert($tbl, ['unit_id'=>$unit, 'ts'=>current_time('mysql'), 'payload'=>$payload]);
            return rest_ensure_response(['ok'=>true,'id'=>$wpdb->insert_id]);
        }
    ]);

    // Append shell log chunk from a device (POST)
    register_rest_route('tmon/v1', '/device/shell-log', [
        'methods' => 'POST',
        'permission_callback' => '__return_true',
        'callback' => function($request) {
            $params = $request->get_json_params();
            $unit = sanitize_text_field($params['unit_id'] ?? '');
            $job = sanitize_text_field($params['job_id'] ?? '');
            $seq = intval($params['seq'] ?? 0);
            $chunk = isset($params['chunk']) ? wp_json_encode($params['chunk']) : '';
            if (!$unit || !$job) return new WP_REST_Response(['ok'=>false,'msg'=>'unit_id and job_id required'],400);
            global $wpdb;
            $tbl = $wpdb->prefix . 'tmon_uc_shell_logs';
            $wpdb->insert($tbl, ['unit_id'=>$unit, 'job_id'=>$job, 'seq'=>$seq, 'chunk'=>$chunk, 'created_at'=>current_time('mysql')]);
            return rest_ensure_response(['ok'=>true,'id'=>$wpdb->insert_id]);
        }
    ]);

    // Retrieve shell log (GET) by unit_id & job_id -> returns JSON array of chunks ordered by seq
    register_rest_route('tmon/v1', '/admin/shell-log', [
        'methods' => 'GET',
        'permission_callback' => 'current_user_can', // restrict to logged-in admins in UC UI
        'callback' => function($request) {
            $unit = sanitize_text_field($request->get_param('unit_id') ?? '');
            $job  = sanitize_text_field($request->get_param('job_id') ?? '');
            if (!$unit || !$job) return new WP_REST_Response(['ok'=>false,'msg'=>'unit_id and job_id required'],400);
            global $wpdb;
            $tbl = $wpdb->prefix . 'tmon_uc_shell_logs';
            $rows = $wpdb->get_results($wpdb->prepare("SELECT seq, chunk, created_at FROM {$tbl} WHERE unit_id=%s AND job_id=%s ORDER BY seq ASC", $unit, $job), ARRAY_A);
            if (!$rows) return rest_ensure_response(['ok'=>true,'chunks'=>[]]);
            $chunks = array_map(function($r){ return ['seq'=>intval($r['seq']),'chunk'=>json_decode($r['chunk'], true),'ts'=>$r['created_at']]; }, $rows);
            return rest_ensure_response(['ok'=>true,'chunks'=>$chunks]);
        }
    ]);

    // GET historical chunk-store summary for a unit (timeseries of missing counts)
    register_rest_route('tmon/v1', '/admin/chunk-history', [
        'methods' => 'GET',
        'permission_callback' => function(){ return current_user_can('manage_options'); },
        'callback' => function($request){
            global $wpdb;
            $unit = sanitize_text_field($request->get_param('unit_id') ?? '');
            $limit = intval($request->get_param('limit') ?? 48);
            if (!$unit) return new WP_REST_Response(['ok'=>false,'msg'=>'unit_id required'], 400);
            tmon_uc_ensure_tables();
            $tbl = $wpdb->prefix . 'tmon_uc_lora_snapshots';
            $rows = $wpdb->get_results($wpdb->prepare("SELECT ts, payload FROM {$tbl} WHERE unit_id=%s ORDER BY ts DESC LIMIT %d", $unit, $limit), ARRAY_A);
            $series = [];
            if ($rows && is_array($rows)) {
                foreach ($rows as $r) {
                    $ts = $r['ts'];
                    $payload = json_decode($r['payload'] ?? '{}', true);
                    $missing_count = 0;
                    if (is_array($payload)) {
                        // payload may contain 'chunks' mapping mid->info or similar
                        $chunks = isset($payload['chunks']) && is_array($payload['chunks']) ? $payload['chunks'] : (is_array($payload) ? $payload : []);
                        if (is_array($chunks)) {
                            foreach ($chunks as $mid => $info) {
                                if (is_array($info) && isset($info['missing']) && is_array($info['missing'])) {
                                    $missing_count += count($info['missing']);
                                }
                            }
                        }
                    }
                    $series[] = ['ts' => $ts, 'missing' => intval($missing_count)];
                }
            }
            return rest_ensure_response(['ok'=>true, 'unit'=>$unit, 'series'=>array_reverse($series)]);
        }
    ]);

    // POST backfill from Admin -> UC (customers + locations)
    register_rest_route('tmon/v1', '/admin/backfill', [
        'methods' => 'POST',
        'permission_callback' => '__return_true',
        'callback' => function($request) {
            // authenticate via hub key when configured
            $expected = get_option('tmon_uc_shared_key', '') ?: get_option('tmon_admin_uc_key', '');
            $provided = '';
            if (function_exists('getallheaders')) {
                $h = getallheaders();
                $provided = $h['X-TMON-HUB'] ?? $h['x-tmon-hub'] ?? '';
            } else {
                $provided = $_SERVER['HTTP_X_TMON_HUB'] ?? '';
            }
            if ($expected && !$provided) return new WP_REST_Response(['ok'=>false,'msg'=>'missing hub key'],403);
            if ($expected && !hash_equals((string)$expected, (string)$provided)) return new WP_REST_Response(['ok'=>false,'msg'=>'invalid hub key'],403);

            $params = $request->get_json_params();
            if (!is_array($params)) return new WP_REST_Response(['ok'=>false,'msg'=>'bad payload'],400);
            tmon_uc_ensure_tables();
            global $wpdb;
            // upsert customers
            if (!empty($params['customers']) && is_array($params['customers'])) {
                foreach ($params['customers'] as $c) {
                    $name = sanitize_text_field($c['name'] ?? '');
                    $meta = wp_json_encode($c['meta'] ?? []);
                    if (!$name) continue;
                    $exists = $wpdb->get_var($wpdb->prepare("SELECT id FROM {$wpdb->prefix}tmon_customers WHERE name=%s", $name));
                    if ($exists) $wpdb->update($wpdb->prefix . 'tmon_customers', ['meta'=>$meta,'updated_at'=>current_time('mysql')], ['id'=>$exists]);
                    else $wpdb->insert($wpdb->prefix . 'tmon_customers', ['name'=>$name,'meta'=>$meta]);
                }
            }
            // upsert locations
            if (!empty($params['locations']) && is_array($params['locations'])) {
                foreach ($params['locations'] as $loc) {
                    $cust = sanitize_text_field($loc['customer'] ?? '');
                    $cust_id = $wpdb->get_var($wpdb->prepare("SELECT id FROM {$wpdb->prefix}tmon_customers WHERE name=%s", $cust));
                    if (!$cust_id) continue;
                    $name = sanitize_text_field($loc['name'] ?? '');
                    $lat = floatval($loc['lat'] ?? 0);
                    $lng = floatval($loc['lng'] ?? 0);
                    $addr = sanitize_text_field($loc['address'] ?? '');
                    $uc_site = sanitize_text_field($loc['uc_site_url'] ?? '');
                    $exists = $wpdb->get_var($wpdb->prepare("SELECT id FROM {$wpdb->prefix}tmon_customer_locations WHERE customer_id=%d AND name=%s", $cust_id, $name));
                    if ($exists) $wpdb->update($wpdb->prefix . 'tmon_customer_locations', ['lat'=>$lat,'lng'=>$lng,'address'=>$addr,'uc_site_url'=>$uc_site,'updated_at'=>current_time('mysql')], ['id'=>$exists]);
                    else $wpdb->insert($wpdb->prefix . 'tmon_customer_locations', ['customer_id'=>$cust_id,'name'=>$name,'lat'=>$lat,'lng'=>$lng,'address'=>$addr,'uc_site_url'=>$uc_site]);
                }
            }
            return rest_ensure_response(['ok'=>true]);
        }
    ]);

	register_rest_route('tmon/v1', '/device/commands', [
		'methods' => 'GET',
		'permission_callback' => 'tmon_uc_device_permission_cb',
		'callback' => function (\WP_REST_Request $req) {
			$unit_id = sanitize_text_field((string) $req->get_param('unit_id'));
			if ($unit_id === '') {
				return new \WP_REST_Response(['error' => 'missing_unit_id'], 400);
			}

			// Pop exactly one command per poll (device loop already polls frequently).
			$cmd = tmon_uc_dequeue_next_command($unit_id);
			return new \WP_REST_Response([
				'unit_id' => $unit_id,
				'server_time' => time(),
				'commands' => $cmd ? [$cmd] : [],
			], 200);
		},
	]);

	register_rest_route('tmon/v1', '/device/command-complete', [
		'methods' => 'POST',
		'permission_callback' => 'tmon_uc_device_permission_cb',
		'callback' => function (\WP_REST_Request $req) {
			$body = $req->get_json_params();
			if (!is_array($body)) $body = [];

			$unit_id = sanitize_text_field((string)($body['unit_id'] ?? ''));
			$cmd_id  = sanitize_text_field((string)($body['command_id'] ?? ''));

			if ($unit_id === '' || $cmd_id === '') {
				return new \WP_REST_Response(['error' => 'missing_params'], 400);
			}

			tmon_uc_mark_command_complete($unit_id, $cmd_id, [
				'status'  => sanitize_text_field((string)($body['status'] ?? 'ok')),
				'message' => sanitize_text_field((string)($body['message'] ?? '')),
			]);

			return new \WP_REST_Response(['ok' => true], 200);
		},
	]);
});
