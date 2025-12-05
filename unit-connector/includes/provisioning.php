<?php
if (!defined('ABSPATH')) { exit; }

// --- Device provisioning and management functions ---

/**
 * Get assigned devices from the local database.
 *
 * @param array $args Optional. Arguments for limiting and offsetting results.
 * @return array List of assigned devices.
 */
function uc_devices_get_assigned($args = array()) {
	global $wpdb;
	$defaults = array(
		'limit' => 200,
		'offset' => 0,
		'assigned_only' => true,
	);
	$args = wp_parse_args($args, $defaults);
	$table = $wpdb->prefix . 'tmon_uc_devices'; // assumed UC device mirror table
	$where = '1=1';
	if ($args['assigned_only']) {
		$where .= ' AND assigned = 1';
	}
	$sql = $wpdb->prepare("SELECT * FROM $table WHERE $where ORDER BY id DESC LIMIT %d OFFSET %d", $args['limit'], $args['offset']);
	return $wpdb->get_results($sql, ARRAY_A);
}

/**
 * Refresh the list of assigned devices from the Admin hub.
 *
 * Pulls the latest assigned devices from the Admin hub using the shared key,
 * and updates the local mirror table.
 *
 * @return array List of refreshed devices.
 */
function uc_devices_refresh_from_admin() {
	// Pull latest assigned devices from Admin hub using shared key
	$hub = get_option('tmon_admin_hub_url');
	$key = get_option('tmon_uc_shared_key');
	if (!$hub || !$key) { return array(); }
	$url = trailingslashit($hub) . 'wp-json/tmon-admin/v1/uc/assigned-devices';
	$resp = wp_remote_get($url, array('headers' => array('X-TMON-HUB' => $key), 'timeout' => 15));
	if (is_wp_error($resp)) { return array(); }
	$data = json_decode(wp_remote_retrieve_body($resp), true);
	if (!is_array($data)) { return array(); }
	// upsert mirror table
	global $wpdb;
	$table = $wpdb->prefix . 'tmon_uc_devices';
	foreach ($data as $d) {
		$wpdb->replace($table, array(
			'unit_id' => isset($d['unit_id']) ? sanitize_text_field($d['unit_id']) : '',
			'machine_id' => isset($d['machine_id']) ? sanitize_text_field($d['machine_id']) : '',
			'unit_name' => isset($d['unit_name']) ? sanitize_text_field($d['unit_name']) : '',
			'assigned' => 1,
			'role' => isset($d['role']) ? sanitize_text_field($d['role']) : '',
			'wordpress_api_url' => home_url()
		));
	}
	return $data;
}

/**
 * Admin page for viewing and managing provisioned devices.
 */
function tmon_uc_provisioning_page() {
	if (!current_user_can('manage_options')) {
		wp_die(__('Insufficient permissions', 'tmon'));
	}
	if (isset($_POST['uc_refresh_devices']) && check_admin_referer('tmon_uc_refresh')) {
		uc_devices_refresh_from_admin();
		add_settings_error('tmon_uc', 'refreshed', __('Refreshed assigned devices from Admin hub.', 'tmon'), 'updated');
	}
	$devices = uc_devices_get_assigned();
	echo '<div class="wrap"><h1>' . esc_html__('Provisioned Devices', 'tmon') . '</h1>';
	settings_errors('tmon_uc');
	echo '<form method="post">';
	wp_nonce_field('tmon_uc_refresh');
	submit_button(__('Refresh From Admin Hub', 'tmon'), 'secondary', 'uc_refresh_devices', false);
	echo '</form>';
	echo '<table class="widefat striped"><thead><tr>';
	echo '<th>UNIT_ID</th><th>MACHINE_ID</th><th>Name</th><th>Role</th><th>Actions</th>';
	echo '</tr></thead><tbody>';
	if ($devices) {
		foreach ($devices as $d) {
			$unit = esc_html($d['unit_id']);
			$machine = esc_html($d['machine_id']);
			$name = esc_html($d['unit_name']);
			$role = esc_html(isset($d['role']) ? $d['role'] : '');
			$claim_url = esc_url(add_query_arg(array('tmon_uc_claim' => $unit)));
			echo "<tr><td>$unit</td><td>$machine</td><td>$name</td><td>$role</td><td>";
			echo "<a class='button' href='$claim_url'>" . esc_html__('Claim', 'tmon') . "</a>";
			echo "</td></tr>";
		}
	} else {
		echo '<tr><td colspan="5">' . esc_html__('No devices found. Click refresh to sync.', 'tmon') . '</td></tr>';
	}
	echo '</tbody></table></div>';
}

// Handle claim
add_action('admin_init', function () {
	if (!current_user_can('manage_options')) { return; }
	if (!isset($_GET['tmon_uc_claim'])) { return; }
	global $wpdb;
	$unit = sanitize_text_field($_GET['tmon_uc_claim']);
	$table = $wpdb->prefix . 'tmon_uc_devices';
	$wpdb->update($table, array('assigned' => 1), array('unit_id' => $unit));
	wp_safe_redirect(remove_query_arg('tmon_uc_claim'));
	exit;
});