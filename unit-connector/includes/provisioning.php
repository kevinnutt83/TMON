<?php
if (!defined('ABSPATH')) { exit; }

// --- Device provisioning and management functions ---

/**
 * Ensure UC device mirror table exists (idempotent).
 */
function uc_devices_ensure_table() {
	global $wpdb;
	$table = $wpdb->prefix . 'tmon_uc_devices';
	$charset = $wpdb->get_charset_collate();
	$sql = "CREATE TABLE IF NOT EXISTS $table (
		id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
		unit_id VARCHAR(16) NOT NULL,
		machine_id VARCHAR(64) NOT NULL,
		unit_name VARCHAR(128) NULL,
		role VARCHAR(32) NULL,
		assigned TINYINT(1) NOT NULL DEFAULT 0,
		wordpress_api_url VARCHAR(255) NULL,
		staged_settings LONGTEXT NULL,
		staged_at DATETIME NULL,
		updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
		PRIMARY KEY (id),
		UNIQUE KEY uniq_unit_machine (unit_id, machine_id),
		KEY idx_assigned (assigned)
	) $charset;";
	require_once ABSPATH . 'wp-admin/includes/upgrade.php';
	dbDelta($sql);
}

/**
 * Get assigned devices from the local database.
 *
 * @param array $args Optional. Arguments for limiting and offsetting results.
 * @return array List of assigned devices.
 */
function uc_devices_get_assigned($args = array()) {
	global $wpdb;
	uc_devices_ensure_table();
	$defaults = array('limit' => 200, 'offset' => 0, 'assigned_only' => true);
	$args = wp_parse_args($args, $defaults);
	$table = $wpdb->prefix . 'tmon_uc_devices';
	$where = '1=1';
	if ($args['assigned_only']) { $where .= ' AND assigned = 1'; }
	$sql = $wpdb->prepare("SELECT * FROM $table WHERE $where ORDER BY id DESC LIMIT %d OFFSET %d", $args['limit'], $args['offset']);
	return $wpdb->get_results($sql, ARRAY_A);
}

/**
 * Get unassigned devices from the local database.
 *
 * @param array $args Optional. Arguments for limiting and offsetting results.
 * @return array List of unassigned devices.
 */
function uc_devices_get_unassigned($args = array()) {
	global $wpdb;
	uc_devices_ensure_table();
	$defaults = array('limit' => 200, 'offset' => 0);
	$args = wp_parse_args($args, $defaults);
	$table = $wpdb->prefix . 'tmon_uc_devices';
	$sql = $wpdb->prepare("SELECT * FROM $table WHERE assigned = 0 ORDER BY id DESC LIMIT %d OFFSET %d", $args['limit'], $args['offset']);
	return $wpdb->get_results($sql, ARRAY_A);
}

/**
 * Refresh assigned/unassigned devices from Admin hub (handoff).
 */
function uc_devices_refresh_from_admin() {
	uc_devices_ensure_table();
	$hub = get_option('tmon_admin_hub_url');
	$key = get_option('tmon_uc_shared_key');
	if (!$hub || !$key) { return array(); }
	$url = trailingslashit($hub) . 'wp-json/tmon-admin/v1/uc/devices';
	$resp = wp_remote_get($url, array('headers' => array('X-TMON-HUB' => $key), 'timeout' => 20));
	if (is_wp_error($resp)) { return array(); }
	$data = json_decode(wp_remote_retrieve_body($resp), true);
	if (!is_array($data)) { return array(); }
	global $wpdb;
	$table = $wpdb->prefix . 'tmon_uc_devices';
	foreach ($data as $d) {
		$unit_id = isset($d['unit_id']) ? sanitize_text_field($d['unit_id']) : '';
		$machine_id = isset($d['machine_id']) ? sanitize_text_field($d['machine_id']) : '';
		if (!$unit_id || !$machine_id) { continue; }
		$wpdb->replace($table, array(
			'unit_id' => $unit_id,
			'machine_id' => $machine_id,
			'unit_name' => isset($d['unit_name']) ? sanitize_text_field($d['unit_name']) : '',
			'role' => isset($d['role']) ? sanitize_text_field($d['role']) : '',
			'assigned' => !empty($d['assigned']) ? 1 : 0,
			'wordpress_api_url' => home_url()
		));
	}
	return $data;
}

/**
 * Push staged settings to device (reprovision) via Admin hub.
 * UC sends staged settings to Admin which queues and notifies device.
 */
function uc_push_staged_settings($unit_id, $machine_id, $settings_json) {
	$hub = get_option('tmon_admin_hub_url');
	$key = get_option('tmon_uc_shared_key');
	if (!$hub || !$key) { return new WP_Error('no_hub', 'Hub not configured'); }
	$url = trailingslashit($hub) . 'wp-json/tmon-admin/v1/uc/reprovision';
	$args = array(
		'headers' => array('X-TMON-HUB' => $key, 'Content-Type' => 'application/json'),
		'body' => wp_json_encode(array(
			'unit_id' => $unit_id,
			'machine_id' => $machine_id,
			'settings' => $settings_json,
		)),
		'timeout' => 20,
		'method' => 'POST',
	);
	$resp = wp_remote_post($url, $args);
	if (is_wp_error($resp)) { return $resp; }
	$code = wp_remote_retrieve_response_code($resp);
	if ($code !== 200) {
		return new WP_Error('push_failed', 'Admin reprovision push failed: ' . $code);
	}
	return true;
}

/**
 * Admin page for viewing and managing provisioned devices.
 */
function tmon_uc_provisioning_page() {
	if (!current_user_can('manage_options')) { wp_die(__('Insufficient permissions', 'tmon')); }

	// Actions
	if (isset($_POST['uc_refresh_devices']) && check_admin_referer('tmon_uc_refresh')) {
		uc_devices_refresh_from_admin();
		add_settings_error('tmon_uc', 'refreshed', __('Refreshed devices from Admin hub.', 'tmon'), 'updated');
	}
	if (isset($_POST['uc_reprovision']) && check_admin_referer('tmon_uc_reprov')) {
		$unit = sanitize_text_field($_POST['unit_id']);
		$machine = sanitize_text_field($_POST['machine_id']);
		$settings_json = wp_unslash($_POST['settings_json']);
		global $wpdb;
		uc_devices_ensure_table();
		$table = $wpdb->prefix . 'tmon_uc_devices';
		$wpdb->update($table, array(
			'staged_settings' => $settings_json,
			'staged_at' => current_time('mysql'),
		), array('unit_id' => $unit, 'machine_id' => $machine));
		$res = uc_push_staged_settings($unit, $machine, $settings_json);
		if (is_wp_error($res)) {
			add_settings_error('tmon_uc', 'reprov_err', esc_html($res->get_error_message()), 'error');
		} else {
			add_settings_error('tmon_uc', 'reprov_ok', __('Staged settings pushed to Admin hub.', 'tmon'), 'updated');
		}
	}

	$devices = uc_devices_get_assigned();
	$unassigned = uc_devices_get_unassigned();

	echo '<div class="wrap"><h1>' . esc_html__('Provisioned Devices', 'tmon') . '</h1>';
	settings_errors('tmon_uc');

	echo '<form method="post" style="margin-bottom:12px;">';
	wp_nonce_field('tmon_uc_refresh');
	submit_button(__('Refresh From Admin Hub', 'tmon'), 'secondary', 'uc_refresh_devices', false);
	echo '</form>';

	// Reprovision form (manual staged settings JSON)
	echo '<div class="card" style="padding:12px;margin:12px 0;">';
	echo '<h2>' . esc_html__('Reprovision Device', 'tmon') . '</h2>';
	echo '<form method="post">';
	wp_nonce_field('tmon_uc_reprov');
	echo '<p><label>UNIT_ID <input type="text" name="unit_id" required /></label> ';
	echo '<label>MACHINE_ID <input type="text" name="machine_id" required /></label></p>';
	echo '<p><label>Settings (JSON) <textarea name="settings_json" rows="6" style="width:100%;" placeholder=\'{"ENABLE_OLED":true,"DEBUG":false,"NODE_TYPE":"base"}\' required></textarea></label></p>';
	submit_button(__('Stage & Push', 'tmon'), 'primary', 'uc_reprovision', false);
	echo '</form></div>';

	echo '<table class="widefat striped"><thead><tr>';
	echo '<th>UNIT_ID</th><th>MACHINE_ID</th><th>Name</th><th>Role</th><th>Status</th><th>Actions</th>';
	echo '</tr></thead><tbody>';
	$rows_rendered = false;

	if ($devices) {
		foreach ($devices as $d) {
			$rows_rendered = true;
			$unit = esc_html($d['unit_id']);
			$machine = esc_html($d['machine_id']);
			$name = esc_html($d['unit_name']);
			$role = esc_html(isset($d['role']) ? $d['role'] : '');
			echo "<tr><td>$unit</td><td>$machine</td><td>$name</td><td>$role</td><td>" . esc_html__('Assigned', 'tmon') . "</td><td>";
			echo "<span class='button disabled'>" . esc_html__('Claimed', 'tmon') . "</span>";
			echo "</td></tr>";
		}
	}
	if ($unassigned) {
		foreach ($unassigned as $d) {
			$rows_rendered = true;
			$unit = esc_html($d['unit_id']);
			$machine = esc_html($d['machine_id']);
			$name = esc_html($d['unit_name']);
			$role = esc_html(isset($d['role']) ? $d['role'] : '');
			$claim_url = esc_url(add_query_arg(array('tmon_uc_claim' => $unit)));
			echo "<tr><td>$unit</td><td>$machine</td><td>$name</td><td>$role</td><td>" . esc_html__('Unassigned', 'tmon') . "</td><td>";
			echo "<a class='button button-primary' href='$claim_url'>" . esc_html__('Claim', 'tmon') . "</a>";
			echo "</td></tr>";
		}
	}
	if (!$rows_rendered) {
		echo '<tr><td colspan="6">' . esc_html__('No devices found. Click refresh to sync.', 'tmon') . '</td></tr>';
	}
	echo '</tbody></table></div>';
}

// Handle claim
add_action('admin_init', function () {
	if (!current_user_can('manage_options')) { return; }
	if (!isset($_GET['tmon_uc_claim'])) { return; }
	global $wpdb;
	uc_devices_ensure_table();
	$unit = sanitize_text_field($_GET['tmon_uc_claim']);
	$table = $wpdb->prefix . 'tmon_uc_devices';
	$wpdb->update($table, array('assigned' => 1), array('unit_id' => $unit));
	wp_safe_redirect(remove_query_arg('tmon_uc_claim'));
	exit;
});