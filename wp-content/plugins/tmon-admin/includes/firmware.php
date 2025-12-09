<?php
// ...existing code...

add_action('tmon_admin_firmware_page', function () {
	static $printed = false; if ($printed) return; $printed = true;
	echo '<div class="wrap"><h1>Firmware</h1>';

	$data = get_transient('tmon_admin_firmware_meta');
	if (!$data || empty($data['fetched_at'])) {
		$data = tmon_admin_fetch_firmware_meta();
	}

	if (!empty($data['error'])) {
		echo '<div class="notice notice-error"><p>' . esc_html($data['error']) . '</p></div>';
	}

	if (!empty($data['versions'])) {
		echo '<h2>Available Versions</h2><ul>';
		foreach ($data['versions'] as $ver => $files) {
			echo '<li><strong>' . esc_html($ver) . '</strong>: ';
			$links = [];
			foreach ($files as $label => $url) {
				$links[] = '<a href="' . esc_url($url) . '" target="_blank" rel="noreferrer">' . esc_html($label) . '</a>';
			}
			echo implode(' | ', $links) . '</li>';
		}
		echo '</ul>';
		echo '<p><em>Last fetched: ' . esc_html($data['fetched_at']) . '</em></p>';
	}

	// Auto-populate Unit Connectors and Device IDs
	global $wpdb;
	$uc_table = $wpdb->prefix . 'tmon_uc_sites';
	$dev_table = $wpdb->prefix . 'tmon_devices';

	$ucs = tmon_admin_table_exists($uc_table) ? $wpdb->get_results("SELECT id, normalized_url FROM $uc_table ORDER BY created_at DESC LIMIT 200") : [];
	$devices = tmon_admin_table_exists($dev_table) ? $wpdb->get_results("SELECT id, unit_id FROM $dev_table ORDER BY id DESC LIMIT 200") : [];

	echo '<h2>Unit Connectors</h2>';
	echo '<ul>';
	if ($ucs) {
		foreach ($ucs as $uc) {
			echo '<li>' . intval($uc->id) . ' — ' . esc_html($uc->normalized_url) . '</li>';
		}
	} else {
		echo '<li>No Unit Connectors found.</li>';
	}
	echo '</ul>';

	echo '<h2>Devices</h2>';
	echo '<ul>';
	if ($devices) {
		foreach ($devices as $d) {
			echo '<li>' . intval($d->id) . ' — ' . esc_html($d->unit_id) . '</li>';
		}
	} else {
		echo '<li>No devices found.</li>';
	}
	echo '</ul>';

	echo '</div>';
});

function tmon_admin_fetch_firmware_meta() {
	// Fetch manifest and version from GitHub
	$repo = 'https://raw.githubusercontent.com/your-org/TMON/main'; // adjust path
	$headers = [
		'headers' => [
			'User-Agent' => 'TMON-Admin/1.0',
			'Accept' => 'application/json',
		],
		'timeout' => 10,
	];
	$manifest_url = $repo . '/manifest.json';
	$version_url = $repo . '/version.txt';

	$versions = [];
	$error = '';

	$resp_m = wp_remote_get($manifest_url, $headers);
	if (!is_wp_error($resp_m) && wp_remote_retrieve_response_code($resp_m) === 200) {
		$body = wp_remote_retrieve_body($resp_m);
		$manifest = json_decode($body, true);
		if (is_array($manifest) && !empty($manifest['versions'])) {
			foreach ($manifest['versions'] as $ver => $files) {
				$row = [];
				foreach ($files as $label => $path) {
					$row[$label] = $repo . '/' . ltrim($path, '/');
				}
				$versions[$ver] = $row;
			}
		}
	} else {
		$error = 'Failed to fetch manifest.json';
	}

	$resp_v = wp_remote_get($version_url, $headers);
	$txt_version = '';
	if (!is_wp_error($resp_v) && wp_remote_retrieve_response_code($resp_v) === 200) {
		$txt_version = trim(wp_remote_retrieve_body($resp_v));
		if ($txt_version && !isset($versions[$txt_version])) {
			$versions[$txt_version] = [];
		}
	}

	$data = [
		'versions' => $versions,
		'fetched_at' => current_time('mysql'),
	];
	if ($error) $data['error'] = $error;
	set_transient('tmon_admin_firmware_meta', $data, HOUR_IN_SECONDS);
	return $data;
}

// ...existing code...