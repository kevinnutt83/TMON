<?php
if (!defined('ABSPATH')) exit;

// Unit Connector API for remote install/update orchestrated by TMON Admin (v2.00m compatible)
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
	if (stripos($package_url, 'https://') !== 0) {
		return rest_ensure_response(['status'=>'error','message'=>'HTTPS required for package_url']);
	}
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

// Simple auth check (placeholder)
function tmon_uc_check_admin_auth($request) {
	return true;
}

add_action('rest_api_init', function() {
	// Admin pushes device settings to UC (staged cache)
	register_rest_route('tmon/v1', '/admin/device/settings', [
		'methods' => 'POST',
		'permission_callback' => '__return_true',
		'callback' => function(WP_REST_Request $req) {
			$body = json_decode($req->get_body(), true);
			if (!is_array($body)) $body = (array)$req->get_params();
			$unit_id = sanitize_text_field($body['unit_id'] ?? '');
			$machine_id = sanitize_text_field($body['machine_id'] ?? '');
			$settings = isset($body['settings']) ? (is_array($body['settings']) ? $body['settings'] : json_decode($body['settings'], true)) : [];
			if (!is_array($settings)) $settings = [];

			$store = get_option('tmon_uc_device_settings', []);
			$key = $unit_id ?: $machine_id ?: ('rec_' . time());
			$store[$key] = [
				'unit_id' => $unit_id,
				'machine_id' => $machine_id,
				'settings' => $settings,
				'ts' => current_time('mysql'),
			];
			update_option('tmon_uc_device_settings', $store);

			return rest_ensure_response(['ok' => true]);
		}
	]);

	// Admin confirms device provision (mirror)
	register_rest_route('tmon/v1', '/admin/device/confirm', [
		'methods' => 'POST',
		'permission_callback' => '__return_true',
		'callback' => function(WP_REST_Request $req) {
			$body = json_decode($req->get_body(), true);
			if (!is_array($body)) $body = (array)$req->get_params();
			$unit_id = sanitize_text_field($body['unit_id'] ?? '');
			$machine_id = sanitize_text_field($body['machine_id'] ?? '');
			$rec = [
				'unit_id' => $unit_id,
				'machine_id' => $machine_id,
				'confirmed' => true,
				'ts' => current_time('mysql'),
			];
			$conf = get_option('tmon_uc_device_confirms', []);
			$conf[] = $rec;
			update_option('tmon_uc_device_confirms', $conf);
			return rest_ensure_response(['ok' => true]);
		}
	]);

	// Hierarchy upserts from Admin → UC (companies/sites/zones/clusters/units)
	$upsert_cb = function($what, $id_key) {
		return function(WP_REST_Request $req) use ($what, $id_key) {
			$data = json_decode($req->get_body(), true);
			if (!is_array($data)) $data = (array)$req->get_params();
			$id = isset($data[$id_key]) ? intval($data[$id_key]) : intval($data['id'] ?? 0);
			$list = get_option('tmon_uc_' . $what, []);
			$row = ['id' => $id];
			foreach ($data as $k => $v) {
				$row[$k] = is_scalar($v) ? $v : wp_json_encode($v);
			}
			$list[$id ?: (count($list)+1)] = $row;
			update_option('tmon_uc_' . $what, $list);
			return rest_ensure_response(['ok'=>true]);
		};
	};
	register_rest_route('tmon/v1', '/admin/company/upsert', ['methods'=>'POST','permission_callback'=>'__return_true','callback'=>$upsert_cb('companies','company_id')]);
	register_rest_route('tmon/v1', '/admin/site/upsert',    ['methods'=>'POST','permission_callback'=>'__return_true','callback'=>$upsert_cb('sites','id')]);
	register_rest_route('tmon/v1', '/admin/zone/upsert',    ['methods'=>'POST','permission_callback'=>'__return_true','callback'=>$upsert_cb('zones','id')]);
	register_rest_route('tmon/v1', '/admin/cluster/upsert', ['methods'=>'POST','permission_callback'=>'__return_true','callback'=>$upsert_cb('clusters','id')]);
	register_rest_route('tmon/v1', '/admin/unit/upsert',    ['methods'=>'POST','permission_callback'=>'__return_true','callback'=>$upsert_cb('units','id')]);
});

// AI helpers (optional)
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
	public static function recover_system() { self::log('AI: Performing system recovery', 'recovery'); }
	public static function suggest_action($context) {
		if (stripos($context, 'wifi') !== false) return 'Check WiFi credentials or signal.';
		if (stripos($context, 'ota') !== false) return 'Retry OTA or check file integrity.';
		return 'Check logs and restart the service if needed.';
	}
	public static function log($msg, $context = null) { error_log('[TMON_AI] ' . $msg . ($context ? " | Context: $context" : '')); }
}
add_action('tmon_uc_error', function($msg, $context = null) { TMON_AI::observe_error($msg, $context); });
add_action('tmon_admin_error', function($msg, $context = null) { TMON_AI::observe_error($msg, $context); });
