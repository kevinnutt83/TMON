<?php
// TMON Admin: Firmware Update Orchestrator
add_action('admin_menu', function(){
    add_submenu_page('tmon-admin', 'Firmware Updates', 'Firmware', 'manage_options', 'tmon-admin-firmware', 'tmon_admin_firmware_page');
});

if (!function_exists('tmon_admin_firmware_page')) {
	function tmon_admin_firmware_page(){
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>Firmware Updates</h1>';
		if (isset($_POST['tmon_push_fw'])) {
			check_admin_referer('tmon_admin_firmware');
			$site_url = esc_url_raw($_POST['site_url'] ?? ''); // UC site managing devices
			$firmware_url = esc_url_raw($_POST['firmware_url'] ?? ''); // Hosted firmware file path
			$unit_id = sanitize_text_field($_POST['unit_id'] ?? ''); // optional single
			$csv_ids = trim($_POST['csv_unit_ids'] ?? ''); // optional CSV list
			if ($site_url && $firmware_url) {
				$endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/device/ota';
				$token = ''; // Optionally include a JWT if needed by UC (omitted here)
				$targets = [];
				if ($unit_id) $targets[] = $unit_id;
				if ($csv_ids) {
					foreach (preg_split('/[\s,;]+/', $csv_ids) as $id) {
						$id = trim($id);
						if ($id) $targets[] = $id;
					}
				}
				$targets = array_values(array_unique($targets));
				if (empty($targets)) $targets = ['']; // UC may handle selection UI when empty
				$ok_all = true; $errors = [];
				foreach ($targets as $tid) {
					$body = ['unit_id'=>$tid, 'job_type'=>'file_update', 'payload'=>['filename'=>$firmware_url]];
					$resp = wp_remote_post($endpoint, [
						'timeout' => 20,
						'headers' => ['Content-Type'=>'application/json', 'Authorization' => $token?('Bearer '.$token):''],
						'body' => wp_json_encode($body),
					]);
					$ok = !is_wp_error($resp) && wp_remote_retrieve_response_code($resp) == 200;
					if (!$ok) { $ok_all = false; $errors[] = is_wp_error($resp)?$resp->get_error_message():wp_remote_retrieve_body($resp); }
				}
				echo $ok_all ? '<div class="updated"><p>Firmware job(s) queued for '.count($targets).' target(s).</p></div>' : '<div class="error"><p>Some jobs failed: '.esc_html(join("; ", $errors)).'</p></div>';
			} else {
				echo '<div class="error"><p>Site URL and firmware URL are required.</p></div>';
			}
		}
		echo '<form method="post">';
		wp_nonce_field('tmon_admin_firmware');
		echo '<table class="form-table">';
		echo '<tr><th>UC Site URL</th><td><input type="url" name="site_url" class="regular-text" placeholder="https://uc.example.com" required></td></tr>';
		echo '<tr><th>Firmware URL</th><td><input type="url" name="firmware_url" class="regular-text" placeholder="https://hub.example.com/fw/tmon-fw-v2.00j.bin" required></td></tr>';
		echo '<tr><th>Unit ID (optional)</th><td><input type="text" name="unit_id" class="regular-text" placeholder="170170 (leave empty for manual selection in UC)"></td></tr>';
		echo '<tr><th>CSV Unit IDs (bulk)</th><td><textarea name="csv_unit_ids" rows="4" class="large-text" placeholder="170170,170171,170172"></textarea><p class="description">Provide a comma/space/semicolon separated list to target multiple devices.</p></td></tr>';
		echo '</table>';
		submit_button('Push Firmware Job', 'primary', 'tmon_push_fw');
		echo '</form>';
		echo '</div>';
	}
}
