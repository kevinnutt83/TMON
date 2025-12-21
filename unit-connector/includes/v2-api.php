<?php
if (!defined('ABSPATH')) exit;

// Prevent double-inclusion of this file
if (!defined('TMON_UC_V2_API_LOADED')) {
	define('TMON_UC_V2_API_LOADED', true);
}

// Ensure hub config helpers are available
include_once __DIR__ . '/hub-config.php';

// Guard pull-install function registration
add_action('rest_api_init', function(){
	// If core tmon_uc_pull_install exists (e.g., declared in includes/api.php), do not re-register
	if (function_exists('tmon_uc_pull_install')) {
		return;
	}
	register_rest_route('tmon/v1', '/uc/pull-install', [
		'methods' => 'POST',
		'callback' => 'tmon_uc_pull_install',
		// Enforce Application Password / Authorization rather than managing capabilities via current_user_can()
		'permission_callback' => 'tmon_uc_require_app_password_auth',
	]);
});

// Define tmon_uc_pull_install only if not already defined
if (!function_exists('tmon_uc_pull_install')) {
	function tmon_uc_pull_install($request){
		// DO NOT call current_user_can() here — permission is enforced by the permission_callback above.
		$payload = $request->get_param('payload');
		$sig = $request->get_param('sig');
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
		if (stripos($package_url, 'https://') !== 0) return rest_ensure_response(['status'=>'error','message'=>'HTTPS required for package_url']);
		$expected_hash = isset($payload['sha256']) ? strtolower(sanitize_text_field($payload['sha256'])) : '';
		$action = sanitize_text_field($payload['action'] ?? 'install');
		$callback = esc_url_raw($payload['callback'] ?? '');
		if (!$package_url) return rest_ensure_response(['status'=>'error','message'=>'Missing package_url']);

		include_once ABSPATH . 'wp-admin/includes/file.php';
		include_once ABSPATH . 'wp-admin/includes/misc.php';
		include_once ABSPATH . 'wp-admin/includes/class-wp-upgrader.php';
		include_once ABSPATH . 'wp-admin/includes/plugin.php';
		WP_Filesystem();
		$upgrader = new Plugin_Upgrader();
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
		if ($result && is_wp_error($result) === false) {
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
}

// Permission callback (native WP Application Passwords)
if (!function_exists('tmon_uc_require_app_password_auth')) {
	function tmon_uc_require_app_password_auth() {
		$require = defined('TMON_UC_REQUIRE_APP_PASSWORD') ? TMON_UC_REQUIRE_APP_PASSWORD : (bool) get_option('tmon_uc_require_app_password', false);
		if (!$require) return true;
		return isset($_SERVER['HTTP_AUTHORIZATION']) && $_SERVER['HTTP_AUTHORIZATION'] !== '';
	}
}

// Admin → UC routes (guarded by app password auth)
add_action('rest_api_init', function() {
	register_rest_route('tmon/v1', '/admin/device/settings', [
		'methods' => 'POST',
		'permission_callback' => 'tmon_uc_require_app_password_auth',
		'callback' => function(WP_REST_Request $req) {
			$body = json_decode($req->get_body(), true);
			if (!is_array($body)) $body = (array)$req->get_params();
			$unit_id = sanitize_text_field($body['unit_id'] ?? '');
			$machine_id = sanitize_text_field($body['machine_id'] ?? '');
			$settings = isset($body['settings']) ? (is_array($body['settings']) ? $body['settings'] : json_decode($body['settings'], true)) : [];
			if (!is_array($settings)) $settings = [];
			$store = get_option('tmon_uc_device_settings', []);
			$key = $unit_id ?: $machine_id ?: ('rec_' . time());
			$store[$key] = ['unit_id'=>$unit_id,'machine_id'=>$machine_id,'settings'=>$settings,'ts'=>current_time('mysql')];
			update_option('tmon_uc_device_settings', $store);
			return rest_ensure_response(['ok'=>true]);
		}
	]);

	register_rest_route('tmon/v1', '/admin/device/confirm', [
		'methods' => 'POST',
		'permission_callback' => 'tmon_uc_require_app_password_auth',
		'callback' => function(WP_REST_Request $req) {
			$body = json_decode($req->get_body(), true);
			if (!is_array($body)) $body = (array)$req->get_params();
			$unit_id = sanitize_text_field($body['unit_id'] ?? '');
			$machine_id = sanitize_text_field($body['machine_id'] ?? '');
			$rec = ['unit_id'=>$unit_id,'machine_id'=>$machine_id,'confirmed'=>true,'ts'=>current_time('mysql')];
			$conf = get_option('tmon_uc_device_confirms', []);
			$conf[] = $rec; update_option('tmon_uc_device_confirms', $conf);
			return rest_ensure_response(['ok'=>true]);
		}
	]);

	$upsert_cb = function($what, $id_key) {
		return function(WP_REST_Request $req) use ($what, $id_key) {
			$data = json_decode($req->get_body(), true);
			if (!is_array($data)) $data = (array)$req->get_params();
			$id = isset($data[$id_key]) ? intval($data[$id_key]) : intval($data['id'] ?? 0);
			$list = get_option('tmon_uc_' . $what, []);
			$row = ['id' => $id];
			foreach ($data as $k => $v) { $row[$k] = is_scalar($v) ? $v : wp_json_encode($v); }
			$list[$id ?: (count($list)+1)] = $row;
			update_option('tmon_uc_' . $what, $list);
			return rest_ensure_response(['ok'=>true]);
		};
	};
	register_rest_route('tmon/v1', '/admin/company/upsert', ['methods'=>'POST','permission_callback'=>'tmon_uc_require_app_password_auth','callback'=>$upsert_cb('companies','company_id')]);
	register_rest_route('tmon/v1', '/admin/site/upsert',    ['methods'=>'POST','permission_callback'=>'tmon_uc_require_app_password_auth','callback'=>$upsert_cb('sites','id')]);
	register_rest_route('tmon/v1', '/admin/zone/upsert',    ['methods'=>'POST','permission_callback'=>'tmon_uc_require_app_password_auth','callback'=>$upsert_cb('zones','id')]);
	register_rest_route('tmon/v1', '/admin/cluster/upsert', ['methods'=>'POST','permission_callback'=>'tmon_uc_require_app_password_auth','callback'=>$upsert_cb('clusters','id')]);
	register_rest_route('tmon/v1', '/admin/unit/upsert',    ['methods'=>'POST','permission_callback'=>'tmon_uc_require_app_password_auth','callback'=>$upsert_cb('units','id')]);
});

// Optional AI hooks — guard class redeclaration
if (!class_exists('TMON_AI')) {
	class TMON_AI {
		public static $error_count = 0;
		public static $last_error = null;
		public static $recovery_actions = [];

		public static function observe_error($error_msg, $context = null) {
			self::$error_count++;
			self::$last_error = [$error_msg, $context];
			if (self::$error_count > 5) {
				self::log('AI: Too many errors, attempting system recovery', $context);
				self::recover_system();
			}
		}

		public static function recover_system() {
			self::log('AI: Performing system recovery', 'recovery');
			// ...existing code...
		}

		public static function suggest_action($context) {
			if (stripos($context, 'wifi') !== false) return 'Check WiFi credentials or signal.';
			if (stripos($context, 'ota') !== false) return 'Retry OTA or check file integrity.';
			return 'Check logs and restart the service if needed.';
		}

		public static function log($msg, $context = null) {
			error_log('[TMON_AI] ' . $msg . ($context ? " | Context: $context" : ''));
		}
	}
}

// Hook AI observers (safe to add even if class existed elsewhere)
add_action('tmon_uc_error', function($msg, $context = null) {
	if (class_exists('TMON_AI')) TMON_AI::observe_error($msg, $context);
});
add_action('tmon_admin_error', function($msg, $context = null) {
	if (class_exists('TMON_AI')) TMON_AI::observe_error($msg, $context);
});

// Safe requeue cron: run only if status column exists
add_action('tmon_uc_command_requeue_cron', function(){
	global $wpdb; $t = $wpdb->prefix.'tmon_device_commands';
	$cols = $wpdb->get_results("SHOW COLUMNS FROM {$t}", ARRAY_A);
	$names = array_map(function($c){ return $c['Field']; }, $cols ?: []);
	if ($cols && in_array('status', $names, true)) {
		$wpdb->query("UPDATE {$t} SET status='queued' WHERE status='claimed' AND updated_at < (NOW() - INTERVAL 5 MINUTE)");
	}
});

// Device-facing: staged/applied settings + pending commands for a unit (used by MicroPython devices)
add_action('rest_api_init', function() {
	register_rest_route('tmon/v1', '/device/staged-settings', [
		'methods' => 'GET',
		'permission_callback' => '__return_true',
		'callback' => function(WP_REST_Request $req) {
			global $wpdb;
			$unit = sanitize_text_field($req->get_param('unit_id') ?? $req->get_param('unit') ?? '');
			if (!$unit) return rest_ensure_response(['status'=>'error','message'=>'unit_id required'], 400);

			// Applied settings: try uc mirror, then devices table
			$applied = [];
			$staged = [];
			$row = $wpdb->get_row($wpdb->prepare("SELECT settings FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $unit), ARRAY_A);
			if ($row && !empty($row['settings'])) {
				$tmp = json_decode($row['settings'], true);
				if (json_last_error() === JSON_ERROR_NONE && is_array($tmp)) $applied = $tmp;
			}
			// UC-staged store (if present)
			$store = get_option('tmon_uc_device_settings', []);
			if (is_array($store) && isset($store[$unit]) && !empty($store[$unit]['settings'])) {
				$maybe = $store[$unit]['settings'];
				if (is_string($maybe)) {
					$tmp = json_decode($maybe, true);
					if (json_last_error() === JSON_ERROR_NONE && is_array($tmp)) $staged = $tmp;
				} elseif (is_array($maybe)) {
					$staged = $maybe;
				}
			}
			// Fallback: staged in UC mirror table (tmon_uc_devices)
			$uc_table = $wpdb->prefix.'tmon_uc_devices';
			if (empty($staged) && $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $uc_table))) {
				$row2 = $wpdb->get_row($wpdb->prepare("SELECT staged_settings FROM {$uc_table} WHERE unit_id=%s LIMIT 1", $unit), ARRAY_A);
				if ($row2 && !empty($row2['staged_settings'])) {
					$tmp = json_decode($row2['staged_settings'], true);
					if (json_last_error() === JSON_ERROR_NONE && is_array($tmp)) $staged = $tmp;
				}
			}

			// Pending commands for device
			$cmds = [];
			$rows = $wpdb->get_results($wpdb->prepare(
				"SELECT id, command, params, created_at FROM {$wpdb->prefix}tmon_device_commands WHERE device_id = %s AND (executed_at IS NULL OR executed_at = '' OR executed_at = '0000-00-00 00:00:00') ORDER BY created_at ASC",
				$unit
			), ARRAY_A);
			if (is_array($rows)) {
				foreach ($rows as $r) {
					$params = $r['params'] ?? '';
					$dec = $params;
					if (is_string($params)) {
						$try = json_decode($params, true);
						if (json_last_error() === JSON_ERROR_NONE) $dec = $try;
					}
					$cmds[] = ['id'=>$r['id'],'command'=>$r['command'],'params'=>$dec,'created_at'=>$r['created_at']];
				}
			}

			return rest_ensure_response([
				'status'=>'ok',
				'unit_id'=>$unit,
				'applied'=>$applied,
				'staged'=>$staged,
				'commands'=>$cmds
			]);
		}
	]);
});

// Ensure commands table exists (simple guard)
if (!function_exists('tmon_uc_ensure_commands_table')) {
	function tmon_uc_ensure_commands_table() {
		global $wpdb;
		$table = $wpdb->prefix . 'tmon_device_commands';
		$charset = $wpdb->get_charset_collate();
		$sql = "CREATE TABLE IF NOT EXISTS {$table} (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			device_id VARCHAR(64) NOT NULL,
			command VARCHAR(64) NOT NULL,
			params LONGTEXT NULL,
			status VARCHAR(32) NOT NULL DEFAULT 'queued',
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
			executed_at DATETIME NULL,
			executed_result LONGTEXT NULL,
			PRIMARY KEY (id),
			KEY device_idx (device_id),
			KEY status_idx (status)
		) {$charset};";
		require_once ABSPATH . 'wp-admin/includes/upgrade.php';
		dbDelta($sql);
	}
}
add_action('init', function(){ tmon_uc_ensure_commands_table(); });

// Previously these device endpoints were registered at file-include time and could trigger rest_api_init early.
// Move them into a guarded rest_api_init callback to avoid triggering re-entrant rest_api_init handlers.
add_action('rest_api_init', function() {
	static $tmon_uc_device_command_routes_registered = false;
	if ($tmon_uc_device_command_routes_registered) return;
	$tmon_uc_device_command_routes_registered = true;

	// Endpoint: Admin/UC -> UC: stage a command for a device (used by Admin or hub notify)
	register_rest_route('tmon/v1', '/device/command', [
		'methods' => 'POST',
		'permission_callback' => '__return_true',
		'callback' => function(WP_REST_Request $req){
			global $wpdb;
			$unit_id = sanitize_text_field($req->get_param('unit_id') ?? '');
			$command = sanitize_text_field($req->get_param('command') ?? '');
			$params = $req->get_param('params') ?? $req->get_param('payload') ?? [];
			if (!$unit_id || !$command) return rest_ensure_response(['status'=>'error','message'=>'unit_id and command required'], 400);
			$tbl = $wpdb->prefix . 'tmon_device_commands';
			$wpdb->insert($tbl, [
				'device_id' => $unit_id,
				'command' => $command,
				'params' => wp_json_encode($params),
				'status' => 'queued',
				'created_at' => tmon_uc_store_now(),
				'updated_at' => tmon_uc_store_now(),
			]);
			return rest_ensure_response(['status'=>'ok','id'=>$wpdb->insert_id]);
		}
	]);

	// Endpoint: Device poll for queued commands
	register_rest_route('tmon/v1', '/device/commands', [
		'methods' => 'POST',
		'permission_callback' => '__return_true',
		'callback' => function(WP_REST_Request $req){
			global $wpdb;
			$unit_id = sanitize_text_field($req->get_param('unit_id') ?? '');
			if (!$unit_id) return rest_ensure_response([], 200);
			$tbl = $wpdb->prefix . 'tmon_device_commands';
			$max = intval(get_option('tmon_uc_commands_poll_max', 20));
			$rows = $wpdb->get_results($wpdb->prepare("SELECT id, command, params FROM {$tbl} WHERE device_id=%s AND status='queued' ORDER BY id ASC LIMIT %d", $unit_id, $max), ARRAY_A);
			$out = [];
			foreach ($rows as $r) {
				$out[] = ['id' => intval($r['id']), 'command' => $r['command'], 'params' => json_decode($r['params'], true)];
				// mark claimed to avoid immediate re-delivery
				$wpdb->update($tbl, ['status' => 'claimed', 'updated_at' => tmon_uc_store_now()], ['id' => intval($r['id'])]);
			}
			return rest_ensure_response($out);
		}
	]);

	// Endpoint: Device reports completion of a command
	register_rest_route('tmon/v1', '/device/command-complete', [
		'methods' => 'POST',
		'permission_callback' => '__return_true',
		'callback' => function(WP_REST_Request $req){
			global $wpdb;
			$job_id = intval($req->get_param('job_id') ?? $req->get_param('id') ?? 0);
			$ok = $req->get_param('ok') ? 1 : 0;
			$result = $req->get_param('result') ?? '';
			if (!$job_id) return rest_ensure_response(['status'=>'error','message'=>'job_id required'], 400);
			$tbl = $wpdb->prefix . 'tmon_device_commands';
			$wpdb->update($tbl, ['status' => ($ok ? 'done' : 'failed'), 'executed_at'=>tmon_uc_store_now(), 'executed_result'=>wp_json_encode($result), 'updated_at'=>tmon_uc_store_now()], ['id' => $job_id]);
			return rest_ensure_response(['status'=>'ok']);
		}
	]);

	// Legacy/compat: /device/ack for older devices
	register_rest_route('tmon/v1', '/device/ack', [
		'methods' => 'POST',
		'permission_callback' => '__return_true',
		'callback' => function(WP_REST_Request $req){
			global $wpdb;
			$command_id = intval($req->get_param('command_id') ?? 0);
			$ok = $req->get_param('ok') ? 1 : 0;
			$result = $req->get_param('result') ?? '';
			if (!$command_id) return rest_ensure_response(['status'=>'error','message'=>'command_id required'], 400);
			$tbl = $wpdb->prefix . 'tmon_device_commands';
			$wpdb->update($tbl, ['status' => ($ok ? 'done' : 'failed'), 'executed_at'=>tmon_uc_store_now(), 'executed_result'=>wp_json_encode($result), 'updated_at'=>tmon_uc_store_now()], ['id' => $command_id]);
			return rest_ensure_response(['status'=>'ok']);
		}
	]);
});

// Device registers / check-in and may send its settings snapshot
add_action('rest_api_init', function(){
	register_rest_route('tmon/v1', '/device/register', [
		'methods' => 'POST',
		'callback' => 'tmon_rest_device_register',
		'permission_callback' => '__return_true',
	]);
});

/* Helper: write per-device settings file under WP_CONTENT_DIR/tmon-field-logs */
function tmon_uc_write_device_settings_file($unit_id, $settings_array) {
	if (empty($unit_id) || !is_array($settings_array)) return false;
	$dir = trailingslashit(WP_CONTENT_DIR) . 'tmon-field-logs';
	if (! file_exists($dir)) wp_mkdir_p($dir);
	$fname = $dir . '/device_settings-' . sanitize_file_name($unit_id) . '.json';
	@file_put_contents($fname, wp_json_encode($settings_array));
	return true;
}

/* POST /device/register
   Accept: unit_id, machine_id, settings (object)
   Persist to tmon_devices (settings/last_seen) and write per-device file.
*/
function tmon_rest_device_register(WP_REST_Request $req) {
	global $wpdb;
	$body = $req->get_json_params();
	$unit_id = isset($body['unit_id']) ? sanitize_text_field($body['unit_id']) : '';
	$machine_id = isset($body['machine_id']) ? sanitize_text_field($body['machine_id']) : '';
	$settings = isset($body['settings']) && is_array($body['settings']) ? $body['settings'] : [];

	if (! $unit_id) {
		return rest_ensure_response(['status'=>'error','message'=>'unit_id required'], 400);
	}
	// Update or insert into tmon_devices (best-effort)
	$now = current_time('mysql');
	$row = $wpdb->get_row($wpdb->prepare("SELECT unit_id FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s LIMIT 1", $unit_id));
	$enc = wp_json_encode($settings ?: new stdClass());
	if ($row) {
		$wpdb->update($wpdb->prefix.'tmon_devices', ['settings'=>$enc, 'machine_id'=>$machine_id, 'last_seen'=>$now], ['unit_id'=>$unit_id]);
	} else {
		$wpdb->insert($wpdb->prefix.'tmon_devices', ['unit_id'=>$unit_id,'machine_id'=>$machine_id,'unit_name'=>'','settings'=>$enc,'last_seen'=>$now]);
	}
	// Ensure per-device staged settings file exists for local processes/audit
	if (! empty($settings) && is_array($settings)) {
		tmon_uc_write_device_settings_file($unit_id, $settings);
	}
	return rest_ensure_response([
		'status'=>'ok',
		'unit_id'=>$unit_id,
		'server_time' => current_time('mysql'),
		'server_ts' => intval(current_time('timestamp')),
	]);
}

/* GET /device/settings
   Query params: unit_id or machine_id
   Returns staged settings (if any) and queued commands for immediate download.
*/
function tmon_rest_device_staged_settings(WP_REST_Request $req) {
	global $wpdb;
	$unit_id = sanitize_text_field($req->get_param('unit_id') ?? '');
	$machine_id = sanitize_text_field($req->get_param('machine_id') ?? '');
	$uc_table = $wpdb->prefix . 'tmon_uc_devices';

	// Find staged settings by unit or machine id
	$staged = []; $staged_at = '';
	if ($unit_id || $machine_id) {
		$row = $wpdb->get_row($wpdb->prepare("SELECT staged_settings, staged_at, machine_id FROM {$uc_table} WHERE unit_id=%s OR machine_id=%s LIMIT 1", $unit_id, $machine_id), ARRAY_A);
		if ($row && ! empty($row['staged_settings'])) {
			$tmp = json_decode($row['staged_settings'], true);
			if (is_array($tmp)) $staged = $tmp;
			$staged_at = $row['staged_at'] ?? '';
		}
	}

	// Write per-unit staged file for device-side application (best-effort)
	if ($unit_id && is_array($staged) && $staged) {
		tmon_uc_write_device_settings_file($unit_id, $staged);
	}

	// Return queued commands for this unit (limit)
	$cmds = [];
	if ($unit_id) {
		$cmd_table = $wpdb->prefix . 'tmon_device_commands';
		$rows = $wpdb->get_results($wpdb->prepare("SELECT id, device_id, command, params, created_at FROM {$cmd_table} WHERE device_id=%s AND status='queued' ORDER BY id ASC LIMIT %d", $unit_id, 50), ARRAY_A);
		if ($rows) {
			foreach ($rows as $r) {
				$decoded = json_decode($r['params'], true);
				$cmds[] = [
					'id' => intval($r['id']),
					'command' => $r['command'],
					'params' => is_array($decoded) ? $decoded : $r['params'],
					'created_at' => $r['created_at'],
				];
			}
			// mark returned commands as dispatched
			foreach ($rows as $r) {
				$wpdb->update($cmd_table, ['status'=>'dispatched','dispatched_at'=>current_time('mysql')], ['id'=>intval($r['id'])]);
			}
		}
	}

	return rest_ensure_response([
		'staged' => $staged,
		'staged_at' => $staged_at,
		'commands' => $cmds,
		'server_time' => current_time('mysql'),
		'server_ts' => intval(current_time('timestamp')),
	]);
}

/* POST /device/commands
   Body: { unit_id: "..." } returns queued commands array and marks them dispatched
*/
function tmon_rest_device_commands_fetch(WP_REST_Request $req) {
	global $wpdb;
	$body = $req->get_json_params();
	$unit_id = sanitize_text_field($body['unit_id'] ?? '');
	if (! $unit_id) return rest_ensure_response([], 200);

	$cmd_table = $wpdb->prefix . 'tmon_device_commands';
	$cmds = [];
	$rows = $wpdb->get_results($wpdb->prepare("SELECT id, device_id, command, params, created_at FROM {$cmd_table} WHERE device_id=%s AND status='queued' ORDER BY id ASC LIMIT %d", $unit_id, 50), ARRAY_A);
	if ($rows) {
		foreach ($rows as $r) {
			$decoded = json_decode($r['params'], true);
			$cmds[] = [
				'id' => intval($r['id']),
				'command' => $r['command'],
				'params' => is_array($decoded) ? $decoded : $r['params'],
				'created_at' => $r['created_at'],
			];
		}
		foreach ($rows as $r) {
			$wpdb->update($cmd_table, ['status'=>'dispatched','dispatched_at'=>current_time('mysql')], ['id'=>intval($r['id'])]);
		}
	}
	return rest_ensure_response(['commands'=>$cmds,'server_time'=>current_time('mysql'),'server_ts'=>intval(current_time('timestamp'))], 200);
}

/* POST /device/command-complete
   Body: { job_id: n, ok: true/false, result: "..." }
   Mark command executed + store result into params for audit.
*/
function tmon_rest_device_command_complete(WP_REST_Request $req) {
	global $wpdb;
	$body = $req->get_json_params();
	$job_id = intval($body['job_id'] ?? 0);
	$ok = isset($body['ok']) ? boolval($body['ok']) : null;
	$result = isset($body['result']) ? sanitize_text_field($body['result']) : '';

	if (! $job_id) return rest_ensure_response(['status'=>'error','message'=>'job_id required'], 400);

	$cmd_table = $wpdb->prefix . 'tmon_device_commands';
	$row = $wpdb->get_row($wpdb->prepare("SELECT params FROM {$cmd_table} WHERE id=%d LIMIT 1", $job_id), ARRAY_A);
	if (! $row) return rest_ensure_response(['status'=>'error','message'=>'not found'], 404);

	$params = $row['params'];
	$decoded = json_decode($params, true);
	if (!is_array($decoded)) $decoded = [];
	if ($ok !== null) $decoded['__ok'] = $ok ? true : false;
	if ($result !== '') $decoded['__result'] = $result;

	$wpdb->update($cmd_table, [
		'params' => wp_json_encode($decoded),
		'status' => 'executed',
		'executed_at' => current_time('mysql'),
	], ['id' => $job_id]);

	return rest_ensure_response(['status'=>'ok']);
}

// POST device settings (device -> UC)
add_action('rest_api_init', function(){
	register_rest_route('tmon/v1', '/device/settings', [
		'methods' => 'POST',
		'callback' => 'tmon_v1_device_receive_settings',
		'permission_callback' => '__return_true',
	]);
});

// GET ota jobs for device
add_action('rest_api_init', function(){
	register_rest_route('tmon/v1', '/device/ota-jobs/(?P<unit_id>[\w\-\._]+)', [
		'methods' => 'GET',
		'callback' => 'tmon_v1_device_ota_jobs',
		'permission_callback' => '__return_true',
	]);
});

// POST ota job complete
add_action('rest_api_init', function(){
	register_rest_route('tmon/v1', '/device/ota-job-complete', [
		'methods' => 'POST',
		'callback' => 'tmon_v1_device_ota_job_complete',
		'permission_callback' => '__return_true',
	]);
});

// File upload (multipart/form-data) - saves to wp-content/tmon-files/<unit_id>/
add_action('rest_api_init', function(){
	register_rest_route('tmon/v1', '/device/file', [
		'methods' => 'POST',
		'callback' => 'tmon_v1_device_file_upload',
		'permission_callback' => '__return_true',
	]);
});

// File download
add_action('rest_api_init', function(){
	register_rest_route('tmon/v1', '/device/file/(?P<unit_id>[\w\-\._]+)/(?P<filename>.+)', [
		'methods' => 'GET',
		'callback' => 'tmon_v1_device_file_fetch',
		'permission_callback' => '__return_true',
	]);
});

// Extract Authorization header value robustly.
function tmon_uc_get_authorization_header() {
	// getallheaders() exists on many environments
	if (function_exists('getallheaders')) {
		$h = getallheaders();
		if (!empty($h['Authorization'])) return trim($h['Authorization']);
		if (!empty($h['authorization'])) return trim($h['authorization']);
	}
	// fallback to common $_SERVER vars
	if (!empty($_SERVER['HTTP_AUTHORIZATION'])) return trim($_SERVER['HTTP_AUTHORIZATION']);
	if (!empty($_SERVER['REDIRECT_HTTP_AUTHORIZATION'])) return trim($_SERVER['REDIRECT_HTTP_AUTHORIZATION']);
	// Some servers may use different casing/transforms
	foreach ($_SERVER as $k => $v) {
		if (stripos($k, 'AUTHORIZATION') !== false) return trim($v);
	}
	return '';
}

/**
 * Permission callback for device endpoints: require HTTP Basic auth that maps to a valid WP user.
 */
function tmon_uc_device_permission_callback(\WP_REST_Request $request) {
	$auth = tmon_uc_get_authorization_header();
	if (!$auth) return new WP_Error('forbidden', 'Missing Authorization', ['status' => 401]);
	if (stripos($auth, 'basic ') !== 0) return new WP_Error('forbidden', 'Basic auth required', ['status' => 401]);

	$b64 = trim(substr($auth, 6));
	$decoded = base64_decode($b64);
	if ($decoded === false || strpos($decoded, ':') === false) return new WP_Error('forbidden', 'Invalid Basic credentials', ['status' => 401]);
	list($user, $pass) = explode(':', $decoded, 2);

	// Attempt WP login (does not set a session/cookie)
	$user_obj = wp_authenticate($user, $pass);
	if (is_wp_error($user_obj)) {
		return new WP_Error('forbidden', 'Invalid credentials', ['status' => 403]);
	}
	// Optionally check capability; here any valid user is allowed to call device endpoints.
	return true;
}

// Device-facing routes: require Basic auth
add_action('rest_api_init', function(){
	// Device register/check-in (POST)
	register_rest_route('tmon/v1', '/device/register', [
		'methods' => 'POST',
		'callback' => 'tmon_rest_device_register',
		'permission_callback' => 'tmon_uc_device_permission_callback',
	]);

	// GET device settings
	register_rest_route('tmon/v1', '/device/settings/(?P<unit_id>[\w\-\._]+)', [
		'methods' => 'GET',
		'callback' => 'tmon_v1_device_get_settings',
		'permission_callback' => 'tmon_uc_device_permission_callback',
	]);

	// GET staged settings + queued commands
	register_rest_route('tmon/v1', '/device/staged-settings', [
		'methods' => 'GET',
		'callback' => 'tmon_v1_device_staged_settings',
		'permission_callback' => 'tmon_uc_device_permission_callback',
	]);

	// Fetch queued commands (GET/POST)
	register_rest_route('tmon/v1', '/device/commands', [
		'methods' => ['GET','POST'],
		'callback' => 'tmon_v1_device_commands_fetch',
		'permission_callback' => 'tmon_uc_device_permission_callback',
	]);

	// Command completion ack
	register_rest_route('tmon/v1', '/device/command-complete', [
		'methods' => 'POST',
		'callback' => 'tmon_v1_device_command_complete',
		'permission_callback' => 'tmon_uc_device_permission_callback',
	]);

	// POST device settings (device -> UC)
	register_rest_route('tmon/v1', '/device/settings', [
		'methods' => 'POST',
		'callback' => 'tmon_v1_device_receive_settings',
		'permission_callback' => 'tmon_uc_device_permission_callback',
	]);

	// GET ota jobs for device
	register_rest_route('tmon/v1', '/device/ota-jobs/(?P<unit_id>[\w\-\._]+)', [
		'methods' => 'GET',
		'callback' => 'tmon_v1_device_ota_jobs',
		'permission_callback' => 'tmon_uc_device_permission_callback',
	]);

	// POST ota job complete
	register_rest_route('tmon/v1', '/device/ota-job-complete', [
		'methods' => 'POST',
		'callback' => 'tmon_v1_device_ota_job_complete',
		'permission_callback' => 'tmon_uc_device_permission_callback',
	]);

	// File upload (multipart/form-data) - saves to wp-content/tmon-files/<unit_id>/
	register_rest_route('tmon/v1', '/device/file', [
		'methods' => 'POST',
		'callback' => 'tmon_v1_device_file_upload',
		'permission_callback' => 'tmon_uc_device_permission_callback',
	]);

	// File download
	register_rest_route('tmon/v1', '/device/file/(?P<unit_id>[\w\-\._]+)/(?P<filename>.+)', [
		'methods' => 'GET',
		'callback' => 'tmon_v1_device_file_fetch',
		'permission_callback' => 'tmon_uc_device_permission_callback',
	]);
});

// Device-facing: staged/applied settings + pending commands for a unit (used by MicroPython devices)
add_action('rest_api_init', function() {
	register_rest_route('tmon/v1', '/device/staged-settings', [
		'methods' => 'GET',
		'permission_callback' => '__return_true',
		'callback' => function(WP_REST_Request $req) {
			global $wpdb;
			$unit = sanitize_text_field($req->get_param('unit_id') ?? '');
			$machine = sanitize_text_field($req->get_param('machine_id') ?? '');
			if (!$unit && !$machine) {
				return new WP_REST_Response(['staged' => null, 'commands' => []], 200);
			}
			// Primary lookup by unit_id
			$map = get_option('tmon_uc_staged_settings', []);
			$staged = null;
			if ($unit && is_array($map) && !empty($map[$unit])) {
				$staged = $map[$unit];
			} else if ($machine) {
				// If there is a machine->unit mapping stored somewhere, attempt lookup (optional)
				// fallback: try to find any staged entry with matching machine in payload (not implemented)
				$staged = null;
			}
			return new WP_REST_Response(['staged' => $staged, 'commands' => []], 200);
		},
		'permission_callback' => '__return_true' // devices fetch without WP auth; rely on unit_id param
    ]);
});
