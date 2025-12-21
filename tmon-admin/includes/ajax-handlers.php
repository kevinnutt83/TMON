<?php
if (!defined('ABSPATH')) exit;

/*
 Centralized AJAX handlers for TMON Admin
 - Consolidates handlers originally scattered in tmon-admin.php
 - Guards to prevent redeclarations
*/

// Helpers: normalize key + queue helpers (guarded)
if (!function_exists('tmon_admin_normalize_key')) {
	function tmon_admin_normalize_key($key) {
		return is_string($key) ? strtolower(trim($key)) : '';
	}
}

if (!function_exists('tmon_admin_get_queue_lifetime')) {
	function tmon_admin_get_queue_lifetime() {
		return intval(get_option('tmon_admin_queue_lifetime', 3600)); // seconds
	}
}

if (!function_exists('tmon_admin_get_queue_max_per_site')) {
	function tmon_admin_get_queue_max_per_site() {
		return max(1, intval(get_option('tmon_admin_queue_max_per_site', 10)));
	}
}

if (!function_exists('tmon_admin_prune_pending_queue')) {
	function tmon_admin_prune_pending_queue() {
		$queue = get_option('tmon_admin_pending_provision', []);
		if (!is_array($queue) || empty($queue)) return;
		$lifetime = tmon_admin_get_queue_lifetime();
		$changed = false;
		foreach ($queue as $k => $v) {
			if (empty($v['requested_at'])) continue;
			$ts = strtotime($v['requested_at']);
			if ($ts && ($ts + $lifetime) < time()) {
				unset($queue[$k]);
				$changed = true;
			}
		}
		if ($changed) update_option('tmon_admin_pending_provision', $queue);
	}
}

// Updated enqueue helper: fill requested_by_user + both site_url & wordpress_api_url, improved logging + pruning
if (!function_exists('tmon_admin_normalize_mac')) {
	function tmon_admin_normalize_mac($mac) {
		if (!is_string($mac)) return '';
		// strip non-hex characters and lowercase
		$stripped = preg_replace('/[^0-9a-fA-F]/', '', $mac);
		return strtolower($stripped);
	}
}

if (!function_exists('tmon_admin_enqueue_provision')) {
	function tmon_admin_enqueue_provision($key, $payload) {
		// Normalize primary key
		$raw_key = (string)$key;
		$key = tmon_admin_normalize_key($raw_key);

		if (!$key) return false;
		if (!is_array($payload)) $payload = (array)$payload;

		// Ensure unit_id/machine_id normalized in payload if present
		if (!empty($payload['unit_id'])) $payload['unit_id'] = tmon_admin_normalize_key($payload['unit_id']);
		if (!empty($payload['machine_id'])) $payload['machine_id'] = tmon_admin_normalize_key($payload['machine_id']);

		// Ensure we have requested_by_user
		if (empty($payload['requested_by_user']) && function_exists('wp_get_current_user')) {
			$user = wp_get_current_user();
			$payload['requested_by_user'] = ($user && $user->user_login) ? $user->user_login : 'system';
		}
		$payload['requested_at'] = current_time('mysql');

		// Ensure both site_url and wordpress_api_url for device compatibility
		if (!empty($payload['site_url']) && empty($payload['wordpress_api_url'])) {
			$payload['wordpress_api_url'] = $payload['site_url'];
		}
		if (!empty($payload['wordpress_api_url']) && empty($payload['site_url'])) {
			$payload['site_url'] = $payload['wordpress_api_url'];
		}

		// Compute normalized keys and persist on payload for robust matching
		$payload['unit_id_norm'] = !empty($payload['unit_id']) ? tmon_admin_normalize_key($payload['unit_id']) : '';
		$payload['machine_id_norm'] = !empty($payload['machine_id']) ? tmon_admin_normalize_mac($payload['machine_id']) : '';

		// prune + per-site max enforcement (existing logic)
		tmon_admin_prune_pending_queue();

		$queue = get_option('tmon_admin_pending_provision', []);
		if (!is_array($queue)) $queue = [];

		// Primary normalized enqueue
		$queue[$key] = $payload;

		// Also mirror to unit_id key (if present) and stripped mac key variants
		if (!empty($payload['unit_id'])) {
			$unit_key = tmon_admin_normalize_key($payload['unit_id']);
			if ($unit_key && $unit_key !== $key) $queue[$unit_key] = $payload;
		}
		if (!empty($payload['machine_id'])) {
			$machine_key = tmon_admin_normalize_key($payload['machine_id']);
			if ($machine_key && $machine_key !== $key) $queue[$machine_key] = $payload;
			$machine_stripped = tmon_admin_normalize_mac($payload['machine_id']);
			if ($machine_stripped && $machine_stripped !== $machine_key && $machine_stripped !== $key) $queue[$machine_stripped] = $payload;
		}

		update_option('tmon_admin_pending_provision', $queue);

		// diagnostics: log count and keys
		$keys = array_keys($queue);
		error_log("tmon-admin: enqueue_provision key={$key} by={$payload['requested_by_user']} site=" . ($payload['site_url'] ?? '') . ' payload=' . wp_json_encode($payload));
		error_log("tmon-admin: enqueue_provision current queue keys: " . implode(',', array_slice($keys,0,50)) . ' (count=' . count($keys) . ')');
		return true;
	}
}

// Notify Unit Connector site using pairing info (best-effort)
if (!function_exists('tmon_admin_notify_uc')) {
	function tmon_admin_notify_uc($site_url, $unit_id, $payload) {
		if (empty($site_url) || empty($unit_id)) return false;
		$pairings = get_option('tmon_admin_uc_sites', []);
		$headers = ['Content-Type' => 'application/json'];
		if (isset($pairings[$site_url]['uc_key']) && $pairings[$site_url]['uc_key']) {
			$headers['X-TMON-ADMIN'] = $pairings[$site_url]['uc_key'];
		} else {
			// fallback hub shared key
			$hub_key = get_option('tmon_admin_hub_shared_key', '');
			if ($hub_key) $headers['X-TMON-HUB'] = $hub_key;
		}
		$endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/device/command';
		$body = [
			'unit_id' => $unit_id,
			'command' => 'settings_update',
			'params' => $payload
		];
		$args = [ 'timeout' => 15, 'headers' => $headers, 'body' => wp_json_encode($body) ];
		$response = wp_remote_post($endpoint, $args);
		if (is_wp_error($response)) {
			error_log("tmon-admin: notify_uc failed (wp_remote_post error): " . $response->get_error_message());
			return false;
		}
		$code = wp_remote_retrieve_response_code($response);
		$ok = in_array($code, [200, 201], true);
		error_log("tmon-admin: notify_uc result for {$unit_id}@{$site_url} => {$code} (ok={$ok})");
		return $ok;
	}
}

// Admin-post: Queue & notify device now (enqueue + best-effort direct notify)
if (!function_exists('tmon_admin_admin_post_queue_and_notify')) {
	add_action('admin_post_tmon_admin_queue_and_notify', function() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		check_admin_referer('tmon_admin_provision');

		$unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
		$machine_id = sanitize_text_field($_POST['machine_id'] ?? '');
		$site_url = esc_url_raw($_POST['site_url'] ?? '');
		$unit_name = sanitize_text_field($_POST['unit_name'] ?? '');
		if (!$unit_id && !$machine_id) {
			wp_redirect(add_query_arg('provision', 'fail', wp_get_referer() ?: admin_url('admin.php?page=tmon-admin-provisioning')));
			exit;
		}
		global $wpdb;
		// try reading a provision row for helper defaults
		$row = null;
		$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
		if (!empty($machine_id)) {
			$row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$prov_table} WHERE machine_id=%s LIMIT 1", $machine_id), ARRAY_A);
		}
		if (!$row && !empty($unit_id)) {
			$row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$prov_table} WHERE unit_id=%s LIMIT 1", $unit_id), ARRAY_A);
		}
		$payload = [
			'unit_name' => $unit_name ?: ($row['unit_name'] ?? ''),
			'site_url' => $site_url ?: ($row['site_url'] ?? ''),
			'firmware' => $row['firmware'] ?? '',
			'firmware_url' => $row['firmware_url'] ?? '',
			'role' => $row['role'] ?? ''
		];
		$key = $machine_id ?: $unit_id;
		// Add user info
		$payload['requested_by_user'] = wp_get_current_user()->user_login;
		// Ensure payload retains identity keys used by queue detection
		$payload['unit_id'] = $unit_id;
		$payload['machine_id'] = $machine_id;
		// compute normalized values for payload
		$payload['unit_id_norm'] = tmon_admin_normalize_key($unit_id);
		$payload['machine_id_norm'] = tmon_admin_normalize_mac($machine_id);

		tmon_admin_enqueue_provision($key, $payload);

		$notified = false;
		if (!empty($payload['site_url'])) {
			$notified = tmon_admin_notify_uc($payload['site_url'], $unit_id ?: $machine_id, $payload);
		}

		if ($notified) {
			// mirror and mark staged, similar to save_provision logic
			global $wpdb;
			$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
			$mac_norm = tmon_admin_normalize_mac($machine_id);
			$unit_norm = tmon_admin_normalize_key($unit_id);

			if (!empty($machine_id)) {
				// Update normalized columns in DB if they do not exist for the row
				if ($mac_norm) {
					// If a row exists with raw machine_id, ensure its normalized column is populated
					$prov_row_id = $wpdb->get_var($wpdb->prepare("SELECT id FROM {$prov_table} WHERE machine_id=%s LIMIT 1", $machine_id));
					if ($prov_row_id) {
						$wpdb->update($prov_table, ['machine_id_norm' => $mac_norm], ['id' => intval($prov_row_id)]);
						error_log("tmon-admin: ensured machine_id_norm set for prov_row id={$prov_row_id} machine_norm={$mac_norm}");
					}
					// mark staged by normalized column
					$wpdb->update($prov_table, ['settings_staged' => 1, 'updated_at' => current_time('mysql')], ['machine_id_norm' => $mac_norm]);
				} else {
					$wpdb->update($prov_table, ['settings_staged' => 1, 'updated_at' => current_time('mysql')], ['machine_id' => $machine_id]);
				}
				error_log("tmon-admin: queue_notify set settings_staged=1 for machine_id={$machine_id} (stripped={$mac_norm})");
			}
			if (!empty($unit_id) && $unit_id !== $machine_id) {
				// Ensure normalized column persisted
				if ($unit_norm) {
					$prov_row_id = $wpdb->get_var($wpdb->prepare("SELECT id FROM {$prov_table} WHERE unit_id=%s LIMIT 1", $unit_id));
					if ($prov_row_id) {
						$wpdb->update($prov_table, ['unit_id_norm' => $unit_norm], ['id' => intval($prov_row_id)]);
						error_log("tmon-admin: ensured unit_id_norm set for prov_row id={$prov_row_id} unit_norm={$unit_norm}");
					}
					$wpdb->update($prov_table, ['settings_staged' => 1, 'updated_at' => current_time('mysql')], ['unit_id_norm' => $unit_norm]);
				} else {
					$wpdb->update($prov_table, ['settings_staged' => 1, 'updated_at' => current_time('mysql')], ['unit_id' => $unit_id]);
				}
				error_log("tmon-admin: queue_notify set settings_staged=1 for unit_id={$unit_id}");
			}
		}

		// mirror to tmon_devices
		$dev_table = $wpdb->prefix . 'tmon_devices';
		if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $dev_table))) {
			$dev_cols = $wpdb->get_col("SHOW COLUMNS FROM {$dev_table}");
			$mirror = ['last_seen' => current_time('mysql')];
			if (in_array('wordpress_api_url', $dev_cols) && !empty($payload['site_url'])) $mirror['wordpress_api_url'] = $payload['site_url'];
			if (in_array('unit_name', $dev_cols) && !empty($payload['unit_name'])) $mirror['unit_name'] = $payload['unit_name'];
			if (in_array('provisioned_at', $dev_cols)) $mirror['provisioned_at'] = current_time('mysql');
			if (!empty($unit_id)) $wpdb->update($dev_table, $mirror, ['unit_id' => $unit_id]);
			elseif (!empty($machine_id)) $wpdb->update($dev_table, $mirror, ['machine_id' => $machine_id]);
		}

		// audit
		do_action('tmon_admin_audit', 'queue_notify', sprintf('key=%s user=%s site=%s notified=%d', $key, wp_get_current_user()->user_login, $payload['site_url'] ?? '', $notified ? 1 : 0));

		wp_redirect(add_query_arg('provision', $notified ? 'queued-notified' : 'queued', wp_get_referer() ?: admin_url('admin.php?page=tmon-admin-provisioning')));
		exit;
	});
}

// Admin-post: Refresh device metadata (bump updated_at)
add_action('admin_post_tmon_admin_refresh_device', function () {
	if (!current_user_can('manage_options')) wp_die('Forbidden');
	$device_id = intval($_GET['device_id'] ?? 0);
	if (!$device_id || !check_admin_referer('tmon_admin_refresh_device_' . $device_id)) wp_die('Invalid request');
	global $wpdb;
	$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
	$mirror_table = $wpdb->prefix . 'tmon_devices';
	$source = tmon_admin_table_exists($prov_table) ? $prov_table : $mirror_table;
	$exists = $wpdb->get_var($wpdb->prepare("SELECT id FROM {$source} WHERE id = %d", $device_id));
	if (!$exists) {
		wp_safe_redirect(add_query_arg('prov_notice', rawurlencode('error: device not found'), wp_get_referer()));
		exit;
	}
	$wpdb->update($source, ['updated_at' => current_time('mysql')], ['id' => $device_id]);
	wp_safe_redirect(add_query_arg('prov_notice', rawurlencode('Device refreshed.'), wp_get_referer()));
	exit;
});

// Admin-post: Reprovision device (stage settings)
add_action('admin_post_tmon_admin_reprovision_device', function () {
	if (!current_user_can('manage_options')) wp_die('Forbidden');
	$device_id = intval($_GET['device_id'] ?? 0);
	if (!$device_id || !check_admin_referer('tmon_admin_reprovision_device_' . $device_id)) wp_die('Invalid request');
	global $wpdb;
	$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
	$mirror_table = $wpdb->prefix . 'tmon_devices';
	$source = tmon_admin_table_exists($prov_table) ? $prov_table : $mirror_table;
	$row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$source} WHERE id = %d", $device_id), ARRAY_A);
	if (!$row) {
		wp_safe_redirect(add_query_arg('prov_notice', rawurlencode('error: device not found'), wp_get_referer()));
		exit;
	}
	$unit_id = $row['unit_id'] ?? '';
	$machine_id = $row['machine_id'] ?? '';
	$wpdb->update($source, ['settings_staged' => 1, 'updated_at' => current_time('mysql')], ['id' => $device_id]);
	$history = get_option('tmon_admin_provision_history', []);
	$history[] = [
		'unit_id' => $unit_id,
		'machine_id' => $machine_id,
		'action' => 'reprovision',
		'ts' => current_time('mysql'),
	];
	update_option('tmon_admin_provision_history', $history);
	wp_safe_redirect(add_query_arg('prov_notice', rawurlencode('Reprovision staged.'), wp_get_referer()));
	exit;
});

// Admin-post: Unprovision device (clear provisioned flags)
add_action('admin_post_tmon_admin_unprovision_device', function () {
	if (!current_user_can('manage_options')) wp_die('Forbidden');
	$device_id = intval($_GET['device_id'] ?? 0);
	if (!$device_id || !check_admin_referer('tmon_admin_unprovision_device_' . $device_id)) wp_die('Invalid request');
	global $wpdb;
	$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
	$mirror_table = $wpdb->prefix . 'tmon_devices';
	$source = tmon_admin_table_exists($prov_table) ? $prov_table : $mirror_table;
	$row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$source} WHERE id = %d", $device_id), ARRAY_A);
	if (!$row) {
		wp_safe_redirect(add_query_arg('prov_notice', rawurlencode('error: device not found'), wp_get_referer()));
		exit;
	}
	$unit_id = $row['unit_id'] ?? '';
	$machine_id = $row['machine_id'] ?? '';
	$wpdb->update($source, ['status' => 'unprovisioned', 'provisioned' => 0, 'provisioned_at' => null, 'updated_at' => current_time('mysql')], ['id' => $device_id]);
	if ($source !== $mirror_table && tmon_admin_table_exists($mirror_table)) {
		$wpdb->update($mirror_table, ['provisioned' => 0, 'provisioned_at' => null, 'status' => 'unprovisioned'], ['unit_id' => $unit_id, 'machine_id' => $machine_id]);
	}
	wp_safe_redirect(add_query_arg('prov_notice', rawurlencode('Device unprovisioned.'), wp_get_referer()));
	exit;
});

// AJAX: delete a field log file
if (!function_exists('tmon_admin_ajax_delete_field_data')) {
	function tmon_admin_ajax_delete_field_data() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		check_ajax_referer('tmon_admin_file_ops');
		$file = sanitize_file_name($_GET['file'] ?? '');
		$log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
		$path = realpath($log_dir . '/' . $file);
		if ($path && strpos($path, realpath($log_dir)) === 0 && file_exists($path)) {
			unlink($path);
			exit;
		}
		wp_die('Not found');
	}
}
add_action('wp_ajax_tmon_admin_delete_field_data', 'tmon_admin_ajax_delete_field_data');

// AJAX: download a file (data history)
if (!function_exists('tmon_admin_ajax_download_data_history')) {
	function tmon_admin_ajax_download_data_history() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		check_ajax_referer('tmon_admin_file_ops');
		$file = sanitize_file_name($_GET['file'] ?? '');
		$log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
		$path = realpath($log_dir . '/' . $file);
		if (!$path || strpos($path, realpath($log_dir)) !== 0 || !file_exists($path)) wp_die('Not found');
		header('Content-Type: text/plain');
		header('Content-Disposition: attachment; filename="' . basename($path) . '"');
		readfile($path);
		exit;
	}
}
add_action('wp_ajax_tmon_admin_download_data_history', 'tmon_admin_ajax_download_data_history');

// AJAX: delete data history (alias of delete field data)
if (!function_exists('tmon_admin_ajax_delete_data_history')) {
	function tmon_admin_ajax_delete_data_history() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		check_ajax_referer('tmon_admin_file_ops');
		$file = sanitize_file_name($_GET['file'] ?? '');
		$log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
		$path = realpath($log_dir . '/' . $file);
		if ($path && strpos($path, realpath($log_dir)) === 0 && file_exists($path)) {
			unlink($path);
			exit;
		}
		wp_die('Not found');
	}
}
add_action('wp_ajax_tmon_admin_delete_data_history', 'tmon_admin_ajax_delete_data_history');

// AJAX: mark notice read
if (!function_exists('tmon_admin_ajax_mark_notification_read')) {
	function tmon_admin_ajax_mark_notification_read() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		check_ajax_referer('tmon_admin_notice');
		$id = intval($_POST['id'] ?? 0);
		$notices = get_option('tmon_admin_notifications', []);
		if (isset($notices[$id])) {
			$notices[$id]['read'] = true;
			update_option('tmon_admin_notifications', $notices);
			wp_send_json_success();
		}
		wp_send_json_error();
	}
}
add_action('wp_ajax_tmon_admin_mark_notification_read', 'tmon_admin_ajax_mark_notification_read');

// AJAX: OTA update status
if (!function_exists('tmon_admin_ajax_update_ota_status')) {
	function tmon_admin_ajax_update_ota_status() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		check_ajax_referer('tmon_admin_ota');
		$id = intval($_POST['id'] ?? 0);
		$status = sanitize_text_field($_POST['status'] ?? '');
		$jobs = get_option('tmon_admin_ota_jobs', []);
		if (isset($jobs[$id])) {
			$jobs[$id]['status'] = $status;
			update_option('tmon_admin_ota_jobs', $jobs);
			wp_send_json_success();
		}
		wp_send_json_error();
	}
}
add_action('wp_ajax_tmon_admin_update_ota_status', 'tmon_admin_ajax_update_ota_status');

// AJAX: upload file metadata (AJAX)
if (!function_exists('tmon_admin_ajax_upload_file')) {
	function tmon_admin_ajax_upload_file() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		check_ajax_referer('tmon_admin_file_upload');
		$name = sanitize_text_field($_POST['name'] ?? '');
		$type = sanitize_text_field($_POST['type'] ?? '');
		$meta = $_POST['meta'] ?? [];
		do_action('tmon_admin_file_upload', ['name'=>$name,'type'=>$type,'meta'=>$meta]);
		wp_send_json_success();
	}
}
add_action('wp_ajax_tmon_admin_upload_file', 'tmon_admin_ajax_upload_file');

// Admin-post: file upload (handles actual file)
if (!function_exists('tmon_admin_admin_post_file_upload')) {
	function tmon_admin_admin_post_file_upload() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		check_admin_referer('tmon_admin_file_upload');
		$dir = WP_CONTENT_DIR . '/tmon-admin-packages';
		if (!is_dir($dir)) wp_mkdir_p($dir);
		require_once ABSPATH . 'wp-admin/includes/file.php';
		$ok = false; $stored = [];
		if (!empty($_FILES['package']['name'])) {
			$overrides = ['test_form' => false];
			$file = wp_handle_upload($_FILES['package'], $overrides);
			if (!isset($file['error'])) {
				$src = $file['file'];
				$dest = trailingslashit($dir) . basename($src);
				if (@rename($src, $dest) || @copy($src, $dest)) {
					$ok = true;
					$stored = [
						'timestamp' => current_time('mysql'),
						'name' => basename($dest),
						'type' => pathinfo($dest, PATHINFO_EXTENSION),
						'path' => $dest,
					];
					$files = get_option('tmon_admin_files', []);
					if (!is_array($files)) $files = [];
					$files[] = $stored;
					update_option('tmon_admin_files', $files);
				}
			}
		}
		wp_redirect(admin_url('admin.php?page=tmon-admin-files&uploaded=' . ($ok ? '1' : '0')));
		exit;
	}
}
add_action('admin_post_tmon_admin_file_upload_post', 'tmon_admin_admin_post_file_upload');

// AJAX: update group (centralized)
if (!function_exists('tmon_admin_ajax_update_group')) {
	function tmon_admin_ajax_update_group() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		check_ajax_referer('tmon_admin_group');
		$name = sanitize_text_field($_POST['name'] ?? '');
		$type = sanitize_text_field($_POST['type'] ?? '');
		$meta = $_POST['meta'] ?? [];
		do_action('tmon_admin_group_update', ['name'=>$name,'type'=>$type,'meta'=>$meta]);
		wp_send_json_success();
	}
}
add_action('wp_ajax_tmon_admin_update_group', 'tmon_admin_ajax_update_group');

// AJAX: AI feedback
if (!function_exists('tmon_admin_ajax_submit_ai_feedback')) {
	function tmon_admin_ajax_submit_ai_feedback() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		check_ajax_referer('tmon_admin_ai_feedback');
		$user_id = get_current_user_id();
		$feedback = sanitize_text_field($_POST['feedback'] ?? '');
		do_action('tmon_admin_ai_feedback', ['user_id'=>$user_id,'feedback'=>$feedback]);
		wp_send_json_success();
	}
}
add_action('wp_ajax_tmon_admin_submit_ai_feedback', 'tmon_admin_ajax_submit_ai_feedback');

// AJAX: Update device repo (inline)
if (!function_exists('tmon_admin_ajax_update_device_repo')) {
	function tmon_admin_ajax_update_device_repo() {
		if (!current_user_can('manage_options')) wp_send_json_error(['message'=>'forbidden']);
		check_ajax_referer('tmon_admin_provision_ajax');

		$unit_id = isset($_POST['unit_id']) ? sanitize_text_field($_POST['unit_id']) : '';
		$machine_id = isset($_POST['machine_id']) ? sanitize_text_field($_POST['machine_id']) : '';
		$repo = isset($_POST['repo']) ? sanitize_text_field($_POST['repo']) : '';
		$branch = isset($_POST['branch']) ? sanitize_text_field($_POST['branch']) : 'main';
		$manifest_url = isset($_POST['manifest_url']) ? esc_url_raw($_POST['manifest_url']) : '';
		$version = isset($_POST['version']) ? sanitize_text_field($_POST['version']) : '';
		$site_url = isset($_POST['site_url']) ? esc_url_raw($_POST['site_url']) : '';
		$unit_name = isset($_POST['unit_name']) ? sanitize_text_field($_POST['unit_name']) : '';

		if (!$unit_id && !$machine_id) {
			wp_send_json_error(['message' => 'unit_id or machine_id is required'], 400);
		}

		global $wpdb;
		$table = $wpdb->prefix . 'tmon_provisioned_devices';
		$where_sql = '';
		$params = [];
		if ($unit_id) { $where_sql = "unit_id = %s"; $params[] = $unit_id; }
		else { $where_sql = "machine_id = %s"; $params[] = $machine_id; }

		$row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table} WHERE {$where_sql} LIMIT 1", $params));
		$meta = [
			'repo' => $repo,
			'branch' => $branch,
			'manifest_url' => $manifest_url,
			'firmware_version' => $version,
			'site_url' => $site_url,
			'unit_name' => $unit_name,
		];

		if ($row) {
			$old_notes = !empty($row->notes) ? json_decode($row->notes, true) : [];
			if (!is_array($old_notes)) $old_notes = [];
			$new_notes = array_merge($old_notes, $meta);
			$updated = $wpdb->update($table, [ 'notes' => wp_json_encode($new_notes) ], [ 'id' => intval($row->id) ]);
			if (false === $updated) {
				wp_send_json_error(['message' => 'DB update failed']);
			}
			$key1 = $machine_id ?: '';
			$key2 = $unit_id ?: '';
			$payload = $meta;
			$payload['site_url'] = $site_url;
			$payload['unit_name'] = $unit_name;
			$payload['requested_by_user'] = wp_get_current_user()->user_login;
			if ($key1) tmon_admin_enqueue_provision($key1, $payload);
			if ($key2 && $key2 !== $key1) tmon_admin_enqueue_provision($key2, $payload);
			// Mirror to tmon_devices, like previous logic
			$dev_table = $wpdb->prefix . 'tmon_devices';
			if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $dev_table))) {
				$dev_cols = $wpdb->get_col("SHOW COLUMNS FROM {$dev_table}");
				$mirror_update = ['last_seen' => current_time('mysql')];
				if (in_array('provisioned', $dev_cols)) $mirror_update['provisioned'] = 1;
				elseif (in_array('status', $dev_cols)) $mirror_update['status'] = 'provisioned';
				if (!empty($site_url) && in_array('site_url', $dev_cols)) $mirror_update['site_url'] = $site_url;
				if (!empty($site_url) && in_array('wordpress_api_url', $dev_cols)) $mirror_update['wordpress_api_url'] = $site_url;
				if (!empty($unit_name) && in_array('unit_name', $dev_cols)) $mirror_update['unit_name'] = $unit_name;
				if (in_array('provisioned_at', $dev_cols)) $mirror_update['provisioned_at'] = current_time('mysql');
				if (!empty($unit_id)) $wpdb->update($dev_table, $mirror_update, ['unit_id' => $unit_id]);
				elseif (!empty($machine_id)) $wpdb->update($dev_table, $mirror_update, ['machine_id' => $machine_id]);
			}
			wp_send_json_success(['message' => 'queued & mirrored']);
		} else {
			$insert = [
				'unit_id' => $unit_id,
				'machine_id' => $machine_id,
				'company_id' => '',
				'plan' => 'default',
				'status' => 'provisioned',
				'notes' => wp_json_encode($meta),
				'created_at' => current_time('mysql'),
			];
			$ok = $wpdb->insert($table, $insert, ['%s','%s','%s','%s','%s','%s']);
			if (!$ok) {
				wp_send_json_error(['message' => 'insert failed']);
			}
			$key = $unit_id ?: $machine_id;
			tmon_admin_enqueue_provision($key, $meta);
			wp_send_json_success(['message' => 'inserted', 'notes' => $meta]);
		}
	}
}
add_action('wp_ajax_tmon_admin_update_device_repo', 'tmon_admin_ajax_update_device_repo');

// AJAX: Manage pending queue (delete / reenq) — centralized
if (!function_exists('tmon_admin_ajax_manage_pending')) {
	function tmon_admin_ajax_manage_pending() {
		if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'forbidden']);
		check_ajax_referer('tmon_admin_provision_ajax');
		global $wpdb;
		$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';

		$key = $_POST['key'] ?? '';
		$action = $_POST['manage_action'] ?? '';
		$payload = $_POST['payload'] ?? '';
		$key_norm = tmon_admin_normalize_key($key);

		if ($action === 'delete') {
			tmon_admin_dequeue_provision($key_norm);
			wp_send_json_success(['message' => 'deleted']);
		} elseif ($action === 'reenqueue') {
			// If empty payload, attempt to re-enqueue the existing queued payload;
			// if none exists, attempt to derive from a DB row (settings_staged).
			if (trim($payload) === '') {
				$existing = tmon_admin_get_pending_provision($key_norm);
				if (is_array($existing) && !empty($existing)) {
					// Refresh timestamp/keep same payload
					$existing['requested_at'] = current_time('mysql');
					$existing['requested_by_user'] = wp_get_current_user()->user_login ?: ($existing['requested_by_user'] ?? 'system');
					tmon_admin_enqueue_provision($key_norm, $existing);
					wp_send_json_success(['message' => 'reenqueued existing']);
				}
				// fallback: try to build from DB row if staged settings exist
				$row = null;
				if ($key) {
					// prefer machine_id match
					$row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$prov_table} WHERE machine_id=%s LIMIT 1", $key), ARRAY_A);
					if (!$row) $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$prov_table} WHERE unit_id=%s LIMIT 1", $key), ARRAY_A);
				}
				if ($row && intval($row['settings_staged'] ?? 0) === 1) {
					$derived = [];
					if (!empty($row['site_url'])) $derived['site_url'] = $row['site_url'];
					if (!empty($row['unit_name'])) $derived['unit_name'] = $row['unit_name'];
					if (!empty($row['firmware'])) $derived['firmware'] = $row['firmware'];
					if (!empty($row['firmware_url'])) $derived['firmware_url'] = $row['firmware_url'];
					if (!empty($row['role'])) $derived['role'] = $row['role'];
					$derived['requested_by_user'] = wp_get_current_user()->user_login ?: 'system';
					$derived['requested_at'] = current_time('mysql');
					tmon_admin_enqueue_provision($key_norm, $derived);
					wp_send_json_success(['message' => 'reenqueued from db']);
				}
				wp_send_json_error(['message' => 'no payload available to reenqueue']);
			}

			// If non-empty payload, validate as JSON and enqueue
			$data = null;
			if ($payload) {
				$decoded = json_decode(stripslashes($payload), true);
				if (json_last_error() === JSON_ERROR_NONE && is_array($decoded)) $data = $decoded;
			}
			if ($data) {
				// ensure user attributed if missing
				if (empty($data['requested_by_user'])) $data['requested_by_user'] = wp_get_current_user()->user_login ?: 'system';
				tmon_admin_enqueue_provision($key_norm, $data);
				wp_send_json_success(['message' => 'reenqueued']);
			}
			wp_send_json_error(['message' => 'invalid payload']);
		}
		wp_send_json_error(['message' => 'unknown action']);
	}
}
add_action('wp_ajax_tmon_admin_manage_pending', 'tmon_admin_ajax_manage_pending');

// Ensure helpers to read & remove queue entries exist
if (!function_exists('tmon_admin_get_pending_provision')) {
	function tmon_admin_get_pending_provision($key) {
		$key_norm = tmon_admin_normalize_key($key);
		if (!$key_norm) return null;
		$queue = get_option('tmon_admin_pending_provision', []);
		if (!is_array($queue) || empty($queue)) return null;

		// Direct match (normalized)
		if (isset($queue[$key_norm])) return $queue[$key_norm];

		// Try stripped mac form
		$mac = tmon_admin_normalize_mac($key);
		if ($mac && isset($queue[$mac])) return $queue[$mac];

		// Search payloads for matching normalized unit/machine keys
		foreach ($queue as $k => $v) {
			$payload_mid_norm = isset($v['machine_id_norm']) ? $v['machine_id_norm'] : (isset($v['machine_id']) ? tmon_admin_normalize_mac($v['machine_id']) : '');
			$payload_uid_norm = isset($v['unit_id_norm']) ? $v['unit_id_norm'] : (isset($v['unit_id']) ? tmon_admin_normalize_key($v['unit_id']) : '');
			if ($payload_mid_norm === $key_norm || $payload_uid_norm === $key_norm || $payload_mid_norm === $mac) {
				return $v;
			}
		}
		return null;
	}
}

if (!function_exists('tmon_admin_dequeue_provision')) {
	function tmon_admin_dequeue_provision($key) {
		$key_norm = tmon_admin_normalize_key($key);
		if (!$key_norm) return null;
		$queue = get_option('tmon_admin_pending_provision', []);
		if (!is_array($queue) || empty($queue)) return null;

		$mac = tmon_admin_normalize_mac($key);
		$removed = [];

		foreach ($queue as $k => $v) {
			$k_norm = tmon_admin_normalize_key($k);
			$payload_mid_norm = isset($v['machine_id_norm']) ? $v['machine_id_norm'] : (isset($v['machine_id']) ? tmon_admin_normalize_mac($v['machine_id']) : '');
			$payload_uid_norm = isset($v['unit_id_norm']) ? $v['unit_id_norm'] : (isset($v['unit_id']) ? tmon_admin_normalize_key($v['unit_id']) : '');

			$match = ($k_norm === $key_norm) || ($mac && $k_norm === $mac) || ($payload_mid_norm === $key_norm) || ($payload_mid_norm === $mac) || ($payload_uid_norm === $key_norm);
			if ($match) {
				$removed[$k] = $v;
				unset($queue[$k]);
			}
		}

		if (!empty($removed)) {
			update_option('tmon_admin_pending_provision', $queue);
			error_log('tmon-admin: Dequeued provision entries for key=' . $key_norm . ' removed=' . count($removed));
			// Record provisioning history for queue dequeue events (include first removed payload for context)
			$first = reset($removed);
			tmon_admin_record_provision_history([
				'action' => 'dequeued',
				'key' => $key_norm,
				'removed_keys' => array_keys($removed),
				'payload' => is_array($first) ? $first : [],
				'note' => sprintf('Dequeued %d queue entries for key=%s', count($removed), $key_norm)
			]);
			return array_shift($removed);
		}
		return null;
	}
}

// Add a helper to append to provisioning history option with structured entries
if (!function_exists('tmon_admin_record_provision_history')) {
	function tmon_admin_record_provision_history(array $entry) {
		$history = get_option('tmon_admin_provision_history', []);
		if (!is_array($history)) $history = [];
		$now = current_time('mysql');
		$user = (function_exists('wp_get_current_user')) ? wp_get_current_user()->user_login : 'system';
		$entry['ts'] = $now;
		if (!isset($entry['user'])) $entry['user'] = $user ?: 'system';
		// Ensure small payload for options; keep limited size by trimming very long payloads
		if (isset($entry['payload']) && is_array($entry['payload'])) {
			$cloned = $entry['payload'];
			// remove deeply nested fields or huge arrays
			if (isset($cloned['data']) && is_array($cloned['data'])) {
				$cloned['data'] = array_slice($cloned['data'], 0, 16);
			}
			$entry['payload'] = $cloned;
		}
		$history[] = $entry;
		// Keep history bounded to ~500 items to avoid option bloat
		if (count($history) > 500) {
			$history = array_slice($history, -500);
		}
		update_option('tmon_admin_provision_history', $history);
	}
}

// Mark that centralized handlers have been registered to prevent duplicate registration.
if (!defined('TMON_ADMIN_HANDLERS_INCLUDED')) {
	define('TMON_ADMIN_HANDLERS_INCLUDED', true);
}

// AJAX: fetch GitHub manifest (proxy)
if (!function_exists('tmon_admin_ajax_fetch_github_manifest')) {
    function tmon_admin_ajax_fetch_github_manifest() {
        if (!current_user_can('manage_options') && !is_user_logged_in()) {
            wp_send_json_error('forbidden', 403);
        }
        $repo = isset($_GET['repo']) ? sanitize_text_field($_GET['repo']) : '';
        if (!$repo) {
            wp_send_json_error('missing repo', 400);
        }
        // Simple mapping: user expects manifest.json at the tree main/micropython/manifest.json
        $manifest_url = $repo;
        // If repo looks like a tree URL, rewrite common pattern to raw manifest path
        // e.g., https://github.com/kevinnutt83/TMON/tree/main/micropython -> raw.githubusercontent...
        if (preg_match('#https?://github.com/([^/]+)/([^/]+)/tree/([^/]+)/(.+)$#', $repo, $m)) {
            $user = $m[1]; $repo_name = $m[2]; $branch = $m[3]; $path = $m[4];
            $manifest_url = "https://raw.githubusercontent.com/{$user}/{$repo_name}/{$branch}/" . trim($path, '/') . "/manifest.json";
        } elseif (strpos($repo, 'raw.githubusercontent.com') !== false && strpos($repo, 'manifest.json') === false) {
            $manifest_url = rtrim($repo, '/') . '/manifest.json';
        }
        $res = wp_remote_get($manifest_url, ['timeout' => 8]);
        if (is_wp_error($res)) {
            wp_send_json_error(['error' => $res->get_error_message()], 502);
        }
        $code = wp_remote_retrieve_response_code($res);
        $body = wp_remote_retrieve_body($res);
        if ($code !== 200 || !$body) {
            wp_send_json_error(['status' => $code, 'body' => substr($body, 0, 1024)], 502);
        }
        $data = json_decode($body, true);
        if (json_last_error() !== JSON_ERROR_NONE) {
            wp_send_json_success(['raw' => $body]); // return raw body if not strict JSON
        }
        wp_send_json_success($data);
    }
    add_action('wp_ajax_tmon_admin_fetch_github_manifest', 'tmon_admin_ajax_fetch_github_manifest');
}

// --- Tools > TMON Validate Page (register under Tools) ---
if (!function_exists('tmon_admin_register_tools_validate_page')) {
	add_action('admin_menu', function(){
		add_management_page('TMON Validate', 'TMON Validate', 'manage_options', 'tmon-validate', 'tmon_admin_tools_validate_page');
	});
	function tmon_admin_tools_validate_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		$nonce = wp_create_nonce('tmon_admin_validate');
		?>
		<div class="wrap tmon-admin">
			<h1>TMON — Validate WP Endpoints & Compute Manifest</h1>
			<p class="description">Quickly validate Unit Connector/Admin endpoints and compute OTA manifest SHA256 hashes (local repo).</p>

			<h2>Validate WordPress Endpoints</h2>
			<table class="form-table">
				<tr><th>Base URL</th><td><input id="tmon-validate-base" class="regular-text" value="<?php echo esc_attr(get_option('tmon_admin_staging_wp_url','')); ?>" placeholder="https://example.com"></td></tr>
				<tr><th>Unit ID</th><td><input id="tmon-validate-unit" class="regular-text" placeholder="170170"></td></tr>
				<tr><th>Auth</th><td><input id="tmon-validate-auth" class="regular-text" placeholder="Bearer token or user:pass"></td></tr>
				<tr><th>Retries</th><td><input id="tmon-validate-retries" class="small-text" value="1"></td></tr>
				<tr><th>Timeout (s)</th><td><input id="tmon-validate-timeout" class="small-text" value="8"></td></tr>
			</table>
			<p>
				<button id="tmon-validate-run" class="button button-primary">Run Validation</button>
				<button id="tmon-validate-compute" class="button">Compute Manifest Hashes</button>
			</p>
			<pre id="tmon-validate-output" style="max-width:100%;white-space:pre-wrap;background:#fff;border:1px solid #ddd;padding:10px;min-height:120px;"></pre>
		</div>
		<script>
		(function(){
			const out = id => document.getElementById(id);
			const ajaxUrl = '<?php echo esc_js(admin_url('admin-ajax.php')); ?>';
			const nonce = '<?php echo esc_js($nonce); ?>';
			async function runValidate() {
				const base = out('tmon-validate-base').value;
				const unit = out('tmon-validate-unit').value;
				const auth = out('tmon-validate-auth').value;
				const retries = out('tmon-validate-retries').value || '1';
				const timeout = out('tmon-validate-timeout').value || '8';
				out('tmon-validate-output').textContent = 'Validating...';
				const body = new URLSearchParams();
				body.append('action', 'tmon_admin_validate_wp_endpoints');
				body.append('_wpnonce', nonce);
				body.append('base', base);
				body.append('unit', unit);
				body.append('auth', auth);
				body.append('retries', retries);
				body.append('timeout', timeout);
				try {
					const r = await fetch(ajaxUrl, { method: 'POST', credentials: 'same-origin', body });
					const json = await r.json();
					out('tmon-validate-output').textContent = JSON.stringify(json, null, 2);
				} catch (e) {
					out('tmon-validate-output').textContent = 'Validation failed: ' + (e.message || e);
				}
			}
			async function computeManifest() {
				out('tmon-validate-output').textContent = 'Computing SHA256 hashes for micropython/ (may take a moment)...';
				const body = new URLSearchParams();
				body.append('action', 'tmon_admin_compute_manifest_hashes');
				body.append('_wpnonce', nonce);
				try {
					const r = await fetch(ajaxUrl, { method: 'POST', credentials: 'same-origin', body });
					const json = await r.json();
					out('tmon-validate-output').textContent = JSON.stringify(json, null, 2);
				} catch (e) {
					out('tmon-validate-output').textContent = 'Compute failed: ' + (e.message || e);
				}
			}
			document.getElementById('tmon-validate-run').addEventListener('click', runValidate);
			document.getElementById('tmon-validate-compute').addEventListener('click', computeManifest);
		})();
		</script>
		<?php
	}
}

// --- AJAX: run the python validator or fallback to PHP validator ---
if (!function_exists('tmon_admin_ajax_validate_wp_endpoints')) {
	function tmon_admin_ajax_validate_wp_endpoints() {
		if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'forbidden'], 403);
		check_ajax_referer('tmon_admin_validate');
		$base = isset($_POST['base']) ? esc_url_raw($_POST['base']) : '';
		$unit = isset($_POST['unit']) ? sanitize_text_field($_POST['unit']) : '';
		$auth = isset($_POST['auth']) ? sanitize_text_field($_POST['auth']) : '';
		$retries = max(1, intval($_POST['retries'] ?? 1));
		$timeout = max(1, intval($_POST['timeout'] ?? 8));

		// First: attempt to execute the Python script if shell_exec is available
		$script = dirname(__DIR__, 2) . '/scripts/validate_wp_endpoints.py';
		if (function_exists('shell_exec') && is_file($script) && is_executable(PHP_BINARY)) {
			$py = trim(shell_exec('which python3 || which python || true'));
			if ($py) {
				$cmd = escapeshellcmd($py) . ' ' . escapeshellarg($script) . ' ' . escapeshellarg($base);
				if ($unit) $cmd .= ' --unit ' . escapeshellarg($unit);
				if ($auth) $cmd .= ' --auth ' . escapeshellarg($auth);
				$cmd .= ' --retries ' . intval($retries) . ' --timeout ' . intval($timeout);
				// Run with a reasonable timeout wrapper if proc_open available (best-effort)
				try {
					$output = shell_exec($cmd . ' 2>&1');
					$json = @json_decode($output, true);
					if (is_array($json)) {
						wp_send_json_success(['source' => 'python', 'results' => $json, 'raw' => $output]);
					} else {
						// Fall back to PHP validator if output not JSON
						$python_failure = $output;
					}
				} catch (Exception $e) {
					$python_failure = $e->getMessage();
				}
			}
		}

		// PHP fallback validator (uses WordPress HTTP)
		$endpoints = [
			'/wp-json/tmon/v1/device/field-data',
			'/wp-json/tmon/v1/device/commands',
			'/wp-json/tmon/v1/device/settings', // may append /{unit}
			'/wp-json/tmon-admin/v1/device/check-in'
		];
		$results = [];
		$headers = [];
		if ($auth) {
			// Support Bearer or user:pass (basic)
			if (stripos($auth, 'bearer ') === 0) {
				$headers['Authorization'] = $auth;
			} elseif (strpos($auth, ':') !== false && strpos($auth, ' ') === false) {
				$headers['Authorization'] = 'Basic ' . base64_encode($auth);
			} else {
				$headers['Authorization'] = $auth;
			}
		}
		foreach ($endpoints as $ep) {
			$path = $ep;
			if (strpos($ep, '/device/settings') !== false && $unit) $path = rtrim($ep, '/') . '/' . rawurlencode($unit);
			$ok = false;
			$last_error = '';
			for ($i=1; $i <= $retries; $i++) {
				$url = rtrim($base, '/') . $path;
				$args = ['timeout' => $timeout, 'headers' => $headers];
				$res = wp_remote_get($url, $args);
				if (is_wp_error($res)) {
					$last_error = $res->get_error_message();
					sleep(1);
					continue;
				}
				$code = wp_remote_retrieve_response_code($res);
				$ok = in_array($code, [200,201], true);
				$results[] = ['url' => $url, 'status' => $code, 'ok' => $ok];
				break;
			}
			if (!$ok && empty($results)) {
				$results[] = ['url' => $url, 'status' => null, 'ok' => false, 'error' => $last_error];
			}
		}
		$payload = ['source' => 'php_fallback', 'results' => $results];
		if (!empty($python_failure)) $payload['python_error'] = substr($python_failure, 0, 4096);
		wp_send_json_success($payload);
	}
	add_action('wp_ajax_tmon_admin_validate_wp_endpoints', 'tmon_admin_ajax_validate_wp_endpoints');
}

// --- AJAX: compute micropython/ manifest hashes and return a manifest object ---
if (!function_exists('tmon_admin_ajax_compute_manifest_hashes')) {
	function tmon_admin_ajax_compute_manifest_hashes() {
		if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'forbidden'], 403);
		check_ajax_referer('tmon_admin_validate');
		// Resolve repository root (attempt relative to this file)
		$repo_root = dirname(__DIR__, 2);
		$mpath = $repo_root . '/micropython';
		if (!is_dir($mpath)) {
			wp_send_json_error(['message' => "micropython directory not found at {$mpath}"], 404);
		}
		$iter = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($mpath));
		$files = [];
		foreach ($iter as $f) {
			if ($f->isFile()) {
				$rel = substr($f->getPathname(), strlen($mpath) + 1);
				// skip pycache and hidden
				if (strpos($rel, '__pycache__') !== false) continue;
				if (strpos($rel, '.') === 0) continue;
				$files[$rel] = $f->getPathname();
			}
		}
		$manifest = ['name' => 'tmon-micropython', 'version' => '', 'files' => new stdClass()];
		foreach ($files as $rel => $abs) {
			$hash = @hash_file('sha256', $abs);
			if (!$hash) $hash = str_repeat('0', 64);
			$manifest['files'][$rel] = 'sha256:' . $hash;
		}
		wp_send_json_success(['manifest' => $manifest, 'path' => $mpath]);
	}
	add_action('wp_ajax_tmon_admin_compute_manifest_hashes', 'tmon_admin_ajax_compute_manifest_hashes');
}

// AJAX: refresh device count for a single UC site (per-site refresh button)
add_action('wp_ajax_tmon_refresh_site_count', 'tmon_admin_ajax_refresh_site_count');
function tmon_admin_ajax_refresh_site_count() {
	if (!current_user_can('manage_options')) {
		wp_send_json_error(['message' => 'Forbidden'], 403);
	}

	// Verify nonce (returns false instead of die when arg 3 is false)
	if (! isset($_REQUEST['nonce']) || ! check_ajax_referer('tmon_admin_uc_refresh', 'nonce', false) ) {
		wp_send_json_error(['message' => 'Security check failed'], 403);
	}

	$site = esc_url_raw($_POST['site_url'] ?? $_GET['site_url'] ?? '');
	if (! $site) {
		wp_send_json_error(['message' => 'Missing site_url'], 400);
	}

	$endpoint = rtrim($site, '/') . '/wp-json/tmon/v1/admin/site/devices';
	$resp = wp_remote_get($endpoint, ['timeout' => 5, 'headers' => ['Accept' => 'application/json']]);
	if (is_wp_error($resp)) {
		wp_send_json_error(['message' => $resp->get_error_message()]);
	}
	$code = intval(wp_remote_retrieve_response_code($resp));
	$body = wp_remote_retrieve_body($resp);
	if (! in_array($code, [200,201], true)) {
		wp_send_json_error(['message' => 'HTTP '. $code, 'raw' => substr($body,0,400)]);
	}

	$count = null;
	// Try JSON parse first, accept {count:N} or {devices:[..]} or top-level array
	$j = json_decode($body, true);
	if (is_array($j)) {
		if (isset($j['count'])) $count = intval($j['count']);
		elseif (isset($j['devices']) && is_array($j['devices'])) $count = count($j['devices']);
		elseif (array_values($j) === $j) $count = count($j);
	}
	// If parsing failed, try to extract a number from body
	if ($count === null) {
		if (preg_match('/\bcount\D?(\d+)\b/i', $body, $m)) $count = intval($m[1]);
		elseif (preg_match('/^(\d+)\s*$/', trim($body), $m)) $count = intval($m[1]);
	}

	wp_send_json_success(['count' => $count, 'raw' => substr($body, 0, 400)]);
}
