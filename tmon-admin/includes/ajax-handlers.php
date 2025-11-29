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
		tmon_admin_enqueue_provision($key, $payload);

		$notified = false;
		if (!empty($payload['site_url'])) {
			$notified = tmon_admin_notify_uc($payload['site_url'], $unit_id ?: $machine_id, $payload);
		}

		if ($notified) {
			// mirror and mark staged, similar to save_provision logic
			if (!empty($machine_id)) {
				$wpdb->update($prov_table, ['settings_staged' => 1, 'updated_at' => current_time('mysql')], ['machine_id' => $machine_id]);
				error_log("tmon-admin: queue_notify set settings_staged=1 for machine_id={$machine_id}");
			}
			if (!empty($unit_id) && $unit_id !== $machine_id) {
				$wpdb->update($prov_table, ['settings_staged' => 1, 'updated_at' => current_time('mysql')], ['unit_id' => $unit_id]);
				error_log("tmon-admin: queue_notify set settings_staged=1 for unit_id={$unit_id}");
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
		}

		// audit
		do_action('tmon_admin_audit', 'queue_notify', sprintf('key=%s user=%s site=%s notified=%d', $key, wp_get_current_user()->user_login, $payload['site_url'] ?? '', $notified ? 1 : 0));

		wp_redirect(add_query_arg('provision', $notified ? 'queued-notified' : 'queued', wp_get_referer() ?: admin_url('admin.php?page=tmon-admin-provisioning')));
		exit;
	});
}

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

		// Search payloads for matching unit_id or machine_id (normalized)
		foreach ($queue as $k => $v) {
			$payload_mid = isset($v['machine_id']) ? tmon_admin_normalize_key($v['machine_id']) : '';
			$payload_uid = isset($v['unit_id']) ? tmon_admin_normalize_key($v['unit_id']) : '';
			if ($payload_mid === $key_norm || $payload_uid === $key_norm || $payload_mid === $mac) return $v;
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
			$payload_mid = isset($v['machine_id']) ? tmon_admin_normalize_key($v['machine_id']) : '';
			$payload_uid = isset($v['unit_id']) ? tmon_admin_normalize_key($v['unit_id']) : '';

			$match = ($k_norm === $key_norm) || ($mac && $k_norm === $mac) || ($payload_mid === $key_norm) || ($payload_mid === $mac) || ($payload_uid === $key_norm);
			if ($match) {
				$removed[$k] = $v;
				unset($queue[$k]);
			}
		}

		if (!empty($removed)) {
			update_option('tmon_admin_pending_provision', $queue);
			error_log('tmon-admin: Dequeued provision entries for key=' . $key_norm . ' removed=' . count($removed));
			return array_shift($removed);
		}
		return null;
	}
}

// Mark that centralized handlers have been registered to prevent duplicate registration.
if (!defined('TMON_ADMIN_HANDLERS_INCLUDED')) {
	define('TMON_ADMIN_HANDLERS_INCLUDED', true);
}
