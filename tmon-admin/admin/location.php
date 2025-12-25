<?php
// TMON Admin: Device Location Orchestrator (push via Unit Connector)

// Shared helper to push GPS to a paired UC site
if (!function_exists('tmon_admin_push_location_settings')) {
	function tmon_admin_push_location_settings($site_url, $unit_id, $lat, $lng, $alt = null, $acc = null) {
		$site_url = esc_url_raw($site_url);
		$unit_id = sanitize_text_field($unit_id);
		if (!$site_url || !$unit_id) {
			return new WP_Error('missing_params', 'Site URL and Unit ID are required.');
		}
		if (!is_numeric($lat) || !is_numeric($lng)) {
			return new WP_Error('invalid_coords', 'Latitude and longitude must be numeric.');
		}
		$lat = floatval($lat);
		$lng = floatval($lng);
		if ($lat < -90 || $lat > 90 || $lng < -180 || $lng > 180) {
			return new WP_Error('range_error', 'Latitude must be between -90 and 90, and longitude between -180 and 180.');
		}
		$headers = ['Content-Type' => 'application/json'];
		$pairings = get_option('tmon_admin_uc_sites', []);
		$uc_key = is_array($pairings) && isset($pairings[$site_url]['uc_key']) ? $pairings[$site_url]['uc_key'] : '';
		if ($uc_key) {
			$headers['X-TMON-ADMIN'] = $uc_key;
		} else {
			$hub_key = get_option('tmon_admin_uc_key', '') ?: get_option('tmon_admin_hub_shared_key', '');
			if ($hub_key) {
				$headers['X-TMON-HUB'] = $hub_key;
			} else {
				return new WP_Error('missing_key', 'No UC key found for this site. Pair the Unit Connector or set a hub key.');
			}
		}

		$settings = ['GPS_LAT' => $lat, 'GPS_LNG' => $lng];
		if ($alt !== null && $alt !== '') {
			if (!is_numeric($alt)) return new WP_Error('invalid_alt', 'Altitude must be numeric.');
			$settings['GPS_ALT_M'] = floatval($alt);
		}
		if ($acc !== null && $acc !== '') {
			if (!is_numeric($acc)) return new WP_Error('invalid_acc', 'Accuracy must be numeric.');
			$settings['GPS_ACCURACY_M'] = floatval($acc);
		}

		$endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/device/settings';
		$resp = wp_remote_post($endpoint, [
			'timeout' => 20,
			'headers' => $headers,
			'body' => wp_json_encode(['unit_id' => $unit_id, 'settings' => $settings]),
		]);
		if (is_wp_error($resp)) return $resp;
		$code = wp_remote_retrieve_response_code($resp);
		if (!in_array($code, [200, 201], true)) {
			$body = wp_remote_retrieve_body($resp);
			return new WP_Error('remote_error', 'UC responded with HTTP ' . intval($code) . ($body ? ': ' . wp_strip_all_tags($body) : ''));
		}
		return ['success' => true, 'code' => $code, 'body' => wp_remote_retrieve_body($resp)];
	}
}

function tmon_admin_location_page(){
	if (!current_user_can('manage_options')) wp_die('Forbidden');
	echo '<div class="wrap"><h1>Device Location</h1>';
	echo '<p class="description">Push GPS coordinates to a device through a paired Unit Connector. Pairings populate the site list; Unit IDs autocomplete from known devices.</p>';

	$known_units = [];
	if (function_exists('tmon_admin_get_all_devices')) {
		foreach ((array) tmon_admin_get_all_devices() as $row) {
			if (!empty($row['unit_id'])) $known_units[$row['unit_id']] = true;
		}
	}

	if (isset($_POST['tmon_push_loc'])) {
		if (!function_exists('tmon_admin_verify_nonce') || !tmon_admin_verify_nonce('tmon_admin_location')) {
			echo '<div class="notice notice-error"><p>Security check failed. Please refresh and try again.</p></div>';
		} else {
			$site_url = esc_url_raw($_POST['site_url'] ?? '');
			$unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
			$lat = $_POST['gps_lat'] ?? null;
			$lng = $_POST['gps_lng'] ?? null;
			$alt = $_POST['gps_alt_m'] ?? null;
			$acc = $_POST['gps_accuracy_m'] ?? null;
			$result = tmon_admin_push_location_settings($site_url, $unit_id, $lat, $lng, $alt, $acc);
			if (is_wp_error($result)) {
				echo '<div class="notice notice-error"><p>'.esc_html($result->get_error_message()).'</p></div>';
			} else {
				$code = isset($result['code']) ? intval($result['code']) : 200;
				echo '<div class="updated"><p>Location command pushed via Unit Connector (HTTP '.$code.').</p></div>';
			}
		}
	}

	echo '<form method="post">';
	wp_nonce_field('tmon_admin_location');
	echo '<table class="form-table">';
	$paired = get_option('tmon_admin_uc_sites', []);
	echo '<tr><th>UC Site URL</th><td><input type="url" name="site_url" list="tmon_paired_sites" class="regular-text" placeholder="https://uc.example.com" required>';
	echo '<datalist id="tmon_paired_sites">';
	if (is_array($paired)) { foreach ($paired as $purl => $info) { echo '<option value="'.esc_attr($purl).'">'.esc_html($info['paired_at'] ?? '').'</option>'; } }
	echo '</datalist><p class="description">Must match the paired site URL exactly.</p></td></tr>';
	echo '<tr><th>Unit ID</th><td><input type="text" name="unit_id" class="regular-text" list="tmon_known_units" required><datalist id="tmon_known_units">';
	foreach (array_keys($known_units) as $uid) { echo '<option value="'.esc_attr($uid).'"></option>'; }
	echo '</datalist></td></tr>';
	echo '<tr><th>Latitude</th><td><input type="number" step="any" name="gps_lat" class="regular-text" placeholder="38.8977" required></td></tr>';
	echo '<tr><th>Longitude</th><td><input type="number" step="any" name="gps_lng" class="regular-text" placeholder="-77.0365" required></td></tr>';
	echo '<tr><th>Altitude (m)</th><td><input type="number" step="any" name="gps_alt_m" class="regular-text" placeholder=""></td></tr>';
	echo '<tr><th>Accuracy (m)</th><td><input type="number" step="any" name="gps_accuracy_m" class="regular-text" placeholder=""></td></tr>';
	echo '</table>';
	submit_button('Push Location', 'primary', 'tmon_push_loc');
	echo '</form>';
	echo '</div>';
}
