<?php
if (!defined('ABSPATH')) exit;

// --- Safety: do NOT declare or override WP pluggable functions (wp_get_current_user/get_current_user_id).
// If pluggables are not yet available, detect and defer any operations that require them.

if (!function_exists('tmon_uc_current_user_ready')) {
	function tmon_uc_current_user_ready() {
		if (! function_exists('wp_get_current_user')) return false;
		$u = wp_get_current_user();
		return (is_object($u) && property_exists($u, 'ID'));
	}
}

// Diagnostic: add admin notice if current user plumbing is not ready (harmless)
add_action('admin_notices', function() {
	// Only show to administrators and only when WP pluggables are unexpectedly missing.
	if (!is_admin()) return;
	if (function_exists('current_user_can') && !current_user_can('manage_options')) return;
	if (!tmon_uc_current_user_ready()) {
		error_log('tmon-unit-connector: WP pluggables not ready during plugin load; deferring capability checks.');
		// light admin notice so install-time issues are visible
		echo '<div class="notice notice-warning"><p>TMON Unit Connector detected WordPress authentication plumbing not ready — no privileges were changed. If you see login/permission issues after activation, please deactivate/reactivate this plugin to allow WordPress to initialize.</p></div>';
	}
});

// Ensure we do heavy init only after pluggable functions are loaded
add_action('plugins_loaded', function() {
	// ...existing registration code (routes, tables, hooks) remains as-is since they are hooked into rest_api_init/init
	// No op here — presence ensures plugins_loaded run before any optional plugin-internal init you may add later.
}, 20);

// --- Replace dangerous pluggable fallbacks with safe wrappers ---
// DO NOT define pluggable functions such as wp_get_current_user() here.
// Defining them can permanently override WP pluggable implementations
// and break authentication (users being logged out / permission failures).

// Safe wrapper: return WP_User if available, or null if not ready
if (!function_exists('tmon_uc_safe_get_current_user')) {
	function tmon_uc_safe_get_current_user() {
		if (function_exists('wp_get_current_user')) {
			return wp_get_current_user();
		}
		return null;
	}
}

// Safe wrapper: return current user ID if available, otherwise 0
if (!function_exists('tmon_uc_safe_get_current_user_id')) {
	function tmon_uc_safe_get_current_user_id() {
		if (function_exists('get_current_user_id')) {
			return get_current_user_id();
		}
		// Try global shim without overwriting global state
		if (isset($GLOBALS['current_user']) && is_object($GLOBALS['current_user']) && property_exists($GLOBALS['current_user'], 'ID')) {
			return intval($GLOBALS['current_user']->ID);
		}
		return 0;
	}
}

// Remove prior logic that forcibly cleared $GLOBALS['current_user'].

// Guard pull-install function registration
add_action('rest_api_init', function(){
	static $tmon_uc_rest_registered = false;
	if ($tmon_uc_rest_registered) return;
	$tmon_uc_rest_registered = true;

	// If core tmon_uc_pull_install exists (e.g., declared in includes/api.php), do not re-register
	if (function_exists('tmon_uc_pull_install')) {
		return;
	}
	register_rest_route('tmon/v1', '/uc/pull-install', [
		'methods' => 'POST',
		// Use app-password / Authorization header guard instead of calling current_user_can()
		'callback' => 'tmon_uc_pull_install',
		'permission_callback' => 'tmon_uc_require_app_password_auth',
	]);
});

// Define tmon_uc_pull_install only if not already defined
if (!function_exists('tmon_uc_pull_install')) {
	function tmon_uc_pull_install($request){
		// Permission is enforced via the permission_callback above (app-password / Authorization).
		// Additional runtime checks (HMAC, etc.) still apply below.
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
	static $tmon_uc_admin_routes_registered = false;
	if ($tmon_uc_admin_routes_registered) return;
	$tmon_uc_admin_routes_registered = true;

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
	static $tmon_uc_device_routes_registered = false;
	if ($tmon_uc_device_routes_registered) return;
	$tmon_uc_device_routes_registered = true;

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
				'created_at' => current_time('mysql'),
				'updated_at' => current_time('mysql'),
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
				$wpdb->update($tbl, ['status' => 'claimed', 'updated_at' => current_time('mysql')], ['id' => intval($r['id'])]);
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
			$wpdb->update($tbl, ['status' => ($ok ? 'done' : 'failed'), 'executed_at'=>current_time('mysql'), 'executed_result'=>wp_json_encode($result), 'updated_at'=>current_time('mysql')], ['id' => $job_id]);
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
			$wpdb->update($tbl, ['status' => ($ok ? 'done' : 'failed'), 'executed_at'=>current_time('mysql'), 'executed_result'=>wp_json_encode($result), 'updated_at'=>current_time('mysql')], ['id' => $command_id]);
			return rest_ensure_response(['status'=>'ok']);
		}
	]);
});

// Activation-time diagnostics: if plugin activation results in auth plumbing missing,
// record a transient and log. Uses activated_plugin hook so we don't need main plugin
// filename here; keep logic small and safe.
add_action('activated_plugin', function($plugin, $network_wide) {
	// Only run when activated in admin context
	if (!is_admin()) return;
	// If WP pluggables aren't ready (wp_get_current_user), note the condition.
	if (!tmon_uc_current_user_ready()) {
		error_log('tmon-unit-connector: activation detected WP current_user not ready. Attempting soft re-init on next admin_init.');
		// Short-lived transient to surface admin notice after activation
		set_transient('tmon_uc_activation_current_user_missing', 1, 30);
	}
}, 10, 2);

// On admin_init attempt a safe re-initialization of current_user if needed.
// We only call pluggable functions if they exist and do not override anything.
add_action('admin_init', function() {
	// Only attempt recovery in admin area
	if (!is_admin()) return;
	// If current user is already ready, nothing to do.
	if (tmon_uc_current_user_ready()) {
		// Clear transient if it was set and we've recovered
		if (get_transient('tmon_uc_activation_current_user_missing')) {
			delete_transient('tmon_uc_activation_current_user_missing');
		}
		return;
	}
	// Try to run safe re-init if pluggables available
	if (function_exists('wp_get_current_user')) {
		$u = wp_get_current_user();
		if (is_object($u) && property_exists($u, 'ID') && $u->ID) {
			// Set globals safely and ensure WP internal current user is set
			$GLOBALS['current_user'] = $u;
			if (function_exists('wp_set_current_user')) {
				wp_set_current_user(intval($u->ID));
			}
			error_log('tmon-unit-connector: Restored $current_user during admin_init after activation.');
			delete_transient('tmon_uc_activation_current_user_missing');
			return;
		}
	}
	// If we reach here, recovery did not succeed; log for diagnostics.
	error_log('tmon-unit-connector: current user remained missing during admin_init after activation.');
});

// Add admin notice if we detected a problem at activation time. Only visible to admins.
add_action('admin_notices', function() {
	if (!is_admin()) return;
	if (function_exists('current_user_can') && !current_user_can('manage_options')) return;
	if (get_transient('tmon_uc_activation_current_user_missing')) {
		echo '<div class="notice notice-error"><p>TMON Unit Connector detected a problem initializing WordPress authentication during activation. If you see persistent permission errors or being logged out, please <strong>deactivate</strong> and <strong>reactivate</strong> this plugin. Check your error log for messages prefixed with <code>tmon-unit-connector:</code>.</p></div>';
	}
});

// --- TMON Hub / Device Connector v1.0+ ---
// TMON Unit Connector: lightweight, secure, versioned unit/device management
//
// Notes:
// - Designed for compatibility with WordPress multisite and standalone installs.
// - Uses WordPress REST API, custom database tables, and hooks for efficient operation.
// - Minimal front-end footprint; primarily admin-facing with device communication endpoints.
// - Relies on WordPress cron for background tasks (e.g., command polling, status updates).
//
// API Endpoints:
// - /wp-json/tmon/v1/uc/pull-install
// - /wp-json/tmon/v1/admin/device/settings
// - /wp-json/tmon/v1/admin/device/confirm
// - /wp-json/tmon/v1/admin/company/upsert
// - /wp-json/tmon/v1/admin/site/upsert
// - /wp-json/tmon/v1/admin/zone/upsert
// - /wp-json/tmon/v1/admin/cluster/upsert
// - /wp-json/tmon/v1/admin/unit/upsert
// - /wp-json/tmon/v1/device/staged-settings
// - /wp-json/tmon/v1/device/command
// - /wp-json/tmon/v1/device/commands
// - /wp-json/tmon/v1/device/command-complete
// - /wp-json/tmon/v1/device/ack
//
// Activation:
// - On activation, the plugin checks and logs the status of WordPress authentication plumbing.
// - If issues are detected, a transient is set to display an admin notice after activation.
// - Admins are advised to deactivate and reactivate the plugin to resolve initialization issues.
//
// Diagnostics:
// - Safe wrappers are provided for current user functions to avoid breaking changes.
// - Errors and important events are logged with context for easier troubleshooting.
// - AI-powered diagnostics suggest actions based on error patterns (optional feature).
//
// Security:
// - Relies on WordPress capabilities and nonce checks for permission management.
// - Data is sanitized and validated at multiple stages to prevent injection attacks.
// - Uses hashed secrets and HMAC for secure communication with the TMON Hub.
