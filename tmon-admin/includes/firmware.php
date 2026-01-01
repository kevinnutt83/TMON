<?php
// Firmware metadata viewer and Unit Connector push helper.

add_action('tmon_admin_firmware_page', 'tmon_admin_render_firmware_page');

function tmon_admin_render_firmware_page() {
	if (!current_user_can('manage_options')) {
		wp_die('Forbidden');
	}

	$message = '';
	$message_class = 'notice-success';

	if (isset($_GET['tmon_fw_refresh'])) {
		if (check_admin_referer('tmon_admin_firmware_refresh')) {
			delete_transient('tmon_admin_firmware_meta');
			$message = 'Firmware metadata refreshed from repository.';
		} else {
			$message = 'Invalid refresh request.';
			$message_class = 'notice-error';
		}
	}

	$push_result = null;
	if (!empty($_POST['tmon_push_fw'])) {
		$push_result = tmon_admin_handle_firmware_push();
		$message = $push_result['message'];
		$message_class = $push_result['ok'] ? 'notice-success' : 'notice-error';
	}

	$data = tmon_admin_get_firmware_meta();

	echo '<div class="wrap tmon-firmware-page">';
	echo '<h1>Firmware</h1>';
	if ($message) {
		echo '<div class="notice ' . esc_attr($message_class) . '"><p>' . esc_html($message) . '</p></div>';
	}
	if (!empty($data['error'])) {
		echo '<div class="notice notice-error"><p>' . esc_html($data['error']) . '</p></div>';
	}

	$refresh_url = wp_nonce_url(add_query_arg('tmon_fw_refresh', '1'), 'tmon_admin_firmware_refresh');
	$version = $data['version'] ?: 'Unknown';

	echo '<div class="tmon-card">';
	echo '<h2>Current Manifest</h2>';
	echo '<p><strong>Version:</strong> ' . esc_html($version) . '</p>';
	if (!empty($data['notes'])) {
		echo '<p><strong>Notes:</strong> ' . esc_html($data['notes']) . '</p>';
	}
	echo '<p><strong>Last fetched:</strong> ' . esc_html($data['fetched_at'] ?: 'n/a') . ' ';
	echo '<a class="button" href="' . esc_url($refresh_url) . '">Refresh from GitHub</a></p>';
	if (!empty($data['source_base'])) {
		echo '<p><strong>Source:</strong> ' . esc_html($data['source_base']) . '</p>';
	}
	echo '</div>';

	echo '<div class="tmon-card">';
	echo '<h2>Firmware Files</h2>';
	if (!empty($data['files'])) {
		echo '<table class="wp-list-table widefat striped"><thead><tr><th>File</th><th>Hash</th><th>Download</th></tr></thead><tbody>';
		foreach ($data['files'] as $file) {
			echo '<tr><td>' . esc_html($file['name']) . '</td><td><code>' . esc_html($file['hash']) . '</code></td><td><a href="' . esc_url($file['url']) . '" target="_blank" rel="noreferrer">Download</a></td></tr>';
		}
		echo '</tbody></table>';
	} else {
		echo '<p>No files listed in manifest.</p>';
	}
	echo '</div>';

	$lists = tmon_admin_list_uc_and_devices();
	echo '<div class="tmon-card tmon-two-col">';
	echo '<div><h2>Unit Connectors</h2><ul>';
	if (!empty($lists['ucs'])) {
		foreach ($lists['ucs'] as $uc) {
			echo '<li>' . intval($uc['id']) . ' — ' . esc_html($uc['normalized_url']) . '</li>';
		}
	} else {
		echo '<li>No Unit Connectors found.</li>';
	}
	echo '</ul></div>';
	echo '<div><h2>Devices</h2><ul>';
	if (!empty($lists['devices'])) {
		foreach ($lists['devices'] as $d) {
			echo '<li>' . intval($d['id']) . ' — ' . esc_html($d['unit_id']) . '</li>';
		}
	} else {
		echo '<li>No devices found.</li>';
	}
	echo '</ul></div>';
	echo '</div>';

	echo '<div class="tmon-card">';
	echo '<h2>Push Firmware Job (via Unit Connector)</h2>';
	echo '<form method="post">';
	wp_nonce_field('tmon_admin_firmware');
	$default_uc = $lists['ucs'][0]['normalized_url'] ?? '';
	$default_file = $data['files'][0]['url'] ?? '';
	echo '<table class="form-table">';
	echo '<tr><th scope="row">UC Site URL</th><td><input type="url" name="site_url" class="regular-text" value="' . esc_attr($default_uc) . '" placeholder="https://uc.example.com" required></td></tr>';
	echo '<tr><th scope="row">Firmware URL</th><td><input type="url" name="firmware_url" class="regular-text" value="' . esc_attr($default_file) . '" placeholder="https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/main.py" required></td></tr>';
	echo '<tr><th scope="row">Unit ID (optional)</th><td><input type="text" name="unit_id" class="regular-text" placeholder="170170"></td></tr>';
	echo '<tr><th scope="row">CSV Unit IDs (bulk)</th><td><textarea name="csv_unit_ids" rows="3" class="large-text" placeholder="170170,170171,170172"></textarea><p class="description">Leave both ID fields empty to let the Unit Connector present a selection UI.</p></td></tr>';
	echo '</table>';
	submit_button('Push Firmware Job', 'primary', 'tmon_push_fw');
	echo '</form>';
	echo '</div>';

	echo '</div>';
}

function tmon_admin_get_firmware_meta($force = false) {
	$cached = $force ? false : get_transient('tmon_admin_firmware_meta');
	if ($cached && !empty($cached['fetched_at'])) {
		return $cached;
	}
	return tmon_admin_fetch_firmware_meta();
}

function tmon_admin_fetch_firmware_meta() {
	$base = rtrim(tmon_admin_firmware_repo_base(), '/');
	$manifest_url = $base . '/manifest.json';
	$version_url = $base . '/version.txt';
	$headers = [
		'headers' => [
			'User-Agent' => 'TMON-Admin/' . TMON_ADMIN_VERSION,
			'Accept' => 'application/json',
		],
		'timeout' => 10,
	];

	$files = [];
	$version = '';
	$notes = '';
	$error = '';

	$resp_m = wp_remote_get($manifest_url, $headers);
	if (!is_wp_error($resp_m) && wp_remote_retrieve_response_code($resp_m) === 200) {
		$manifest = json_decode(wp_remote_retrieve_body($resp_m), true);
		if (is_array($manifest)) {
			$version = $manifest['version'] ?? '';
			$notes = $manifest['notes'] ?? '';
			if (!empty($manifest['files']) && is_array($manifest['files'])) {
				foreach ($manifest['files'] as $name => $hash) {
					$files[] = [
						'name' => $name,
						'hash' => $hash,
						'url'  => $base . '/' . ltrim($name, '/'),
					];
				}
			} else {
				$error = 'Manifest missing file list.';
			}
		} else {
			$error = 'Manifest parse failed.';
		}
	} else {
		$error = 'Failed to fetch manifest.json';
	}

	$resp_v = wp_remote_get($version_url, $headers);
	if (!is_wp_error($resp_v) && wp_remote_retrieve_response_code($resp_v) === 200) {
		$txt_version = trim(wp_remote_retrieve_body($resp_v));
		if ($txt_version && !$version) {
			$version = $txt_version;
		}
	}

	$data = [
		'version' => $version,
		'notes' => $notes,
		'files' => $files,
		'fetched_at' => current_time('mysql'),
		'source_base' => $base,
	];
	if ($error) {
		$data['error'] = $error;
	}
	set_transient('tmon_admin_firmware_meta', $data, HOUR_IN_SECONDS);
	return $data;
}

function tmon_admin_handle_firmware_push() {
	if (!current_user_can('manage_options')) {
		return ['ok' => false, 'message' => 'Forbidden'];
	}
	check_admin_referer('tmon_admin_firmware');

	$site_url = tmon_admin_normalize_url(sanitize_text_field($_POST['site_url'] ?? ''));
	$firmware_url = esc_url_raw($_POST['firmware_url'] ?? '');
	$unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
	$csv_ids = trim((string)($_POST['csv_unit_ids'] ?? ''));

	$targets = tmon_admin_extract_unit_ids($unit_id, $csv_ids);
	return tmon_admin_push_uc_jobs($site_url, $firmware_url, $targets);
}

function tmon_admin_extract_unit_ids($single, $csv) {
	$targets = [];
	if ($single !== '') {
		$targets[] = $single;
	}
	if ($csv !== '') {
		foreach (preg_split('/[\s,;]+/', $csv) as $id) {
			$id = trim($id);
			if ($id !== '') {
				$targets[] = $id;
			}
		}
	}
	return array_values(array_unique($targets));
}

function tmon_admin_push_uc_jobs($site_url, $firmware_url, array $targets) {
	if (!$site_url || !$firmware_url) {
		return ['ok' => false, 'message' => 'Site URL and firmware URL are required.'];
	}

	$endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/device/ota';
	$targets = array_values(array_unique(array_filter(array_map('trim', $targets), 'strlen')));
	if (empty($targets)) {
		$targets = [''];
	}

	$errors = [];
	$sent = 0;
	foreach ($targets as $tid) {
		$body = [
			'unit_id' => $tid,
			'job_type' => 'file_update',
			'payload' => ['filename' => $firmware_url],
		];
		$resp = wp_remote_post($endpoint, [
			'timeout' => 20,
			'headers' => ['Content-Type' => 'application/json'],
			'body' => wp_json_encode($body),
		]);
		$ok = !is_wp_error($resp) && wp_remote_retrieve_response_code($resp) === 200;
		if ($ok) {
			$sent++;
		} else {
			$errors[] = is_wp_error($resp) ? $resp->get_error_message() : wp_remote_retrieve_body($resp);
		}
	}

	return [
		'ok' => empty($errors),
		'message' => empty($errors)
			? 'Queued firmware job for ' . $sent . ' target(s).'
			: 'Some jobs failed: ' . implode('; ', $errors),
	];
}

function tmon_admin_list_uc_and_devices() {
	global $wpdb;
	$uc_table = $wpdb->prefix . 'tmon_uc_sites';
	$dev_table = $wpdb->prefix . 'tmon_devices';

	$has_table = function ($table) use ($wpdb) {
		if (function_exists('tmon_admin_table_exists')) {
			return tmon_admin_table_exists($table);
		}
		return (bool) $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $table));
	};

	$ucs = $has_table($uc_table) ? $wpdb->get_results("SELECT id, normalized_url FROM {$uc_table} ORDER BY created_at DESC LIMIT 200", ARRAY_A) : [];
	$devices = $has_table($dev_table) ? $wpdb->get_results("SELECT id, unit_id FROM {$dev_table} ORDER BY id DESC LIMIT 200", ARRAY_A) : [];

	return [
		'ucs' => $ucs ?: [],
		'devices' => $devices ?: [],
	];
}

function tmon_admin_firmware_repo_base() {
	return apply_filters('tmon_admin_firmware_repo_base', 'https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython');
}