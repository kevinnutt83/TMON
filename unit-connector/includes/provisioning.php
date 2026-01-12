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
	$sql = "CREATE TABLE IF NOT EXISTS {$table} (
		id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
		unit_id VARCHAR(64) NOT NULL,
		machine_id VARCHAR(64) DEFAULT '',
		unit_name VARCHAR(191) DEFAULT '',
		role VARCHAR(64) DEFAULT '',
		assigned TINYINT(1) DEFAULT 0,
		staged_settings LONGTEXT NULL,
		staged_at DATETIME NULL,
		wordpress_api_url VARCHAR(255) DEFAULT '',
		updated_at DATETIME NOT NULL,
		PRIMARY KEY (id),
		UNIQUE KEY uniq_unit (unit_id),
		KEY idx_machine (machine_id),
		KEY idx_assigned (assigned),
		KEY idx_updated (updated_at)
	) {$charset};";
	require_once ABSPATH . 'wp-admin/includes/upgrade.php';
	dbDelta($sql);
}

function uc_devices_upsert_row($row) {
	global $wpdb;
	uc_devices_ensure_table();
	$table = $wpdb->prefix . 'tmon_uc_devices';
	$unit_id    = isset($row['unit_id']) ? sanitize_text_field($row['unit_id']) : '';
	$machine_id = isset($row['machine_id']) ? sanitize_text_field($row['machine_id']) : '';
	if (!$unit_id) { return false; }
	$wpdb->replace($table, array(
		'unit_id'           => $unit_id,
		'machine_id'        => $machine_id,
		'unit_name'         => isset($row['unit_name']) ? sanitize_text_field($row['unit_name']) : '',
		'role'              => isset($row['role']) ? sanitize_text_field($row['role']) : '',
		'assigned'          => !empty($row['assigned']) ? 1 : 0,
		'staged_settings'   => isset($row['staged_settings']) ? $row['staged_settings'] : null,
		'staged_at'         => isset($row['staged_at']) ? $row['staged_at'] : null,
		'wordpress_api_url' => home_url(),
		'updated_at'        => current_time('mysql', true),
	));
	return true;
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
	foreach ($data as $d) {
		uc_devices_upsert_row(array(
			'unit_id'         => $d['unit_id'] ?? '',
			'machine_id'      => $d['machine_id'] ?? '',
			'unit_name'       => $d['unit_name'] ?? '',
			'role'            => $d['role'] ?? '',
			'assigned'        => $d['assigned'] ?? ($d['assigned_to_uc'] ?? 0),
			'staged_settings' => isset($d['staged_settings']) ? wp_json_encode($d['staged_settings']) : null,
			'staged_at'       => $d['staged_at'] ?? null,
		));
	}
	return $data;
}

/**
 * Populate local mirror from last device check-ins (fallback).
 * Reads tmon_devices mirror table if present (created by Admin handoff) and upserts.
 */
function uc_devices_refresh_from_local_mirror() {
	global $wpdb;
	uc_devices_ensure_table();
	$source = $wpdb->prefix . 'tmon_devices';
	if (!$wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $source))) { return 0; }
	$cols = $wpdb->get_col("SHOW COLUMNS FROM {$source}", 0);
	$has_role = in_array('role', $cols, true);
	$has_assigned = in_array('assigned_to_uc', $cols, true);
	$select = "unit_id, machine_id, unit_name" . ($has_role ? ", role" : "") . ($has_assigned ? ", assigned_to_uc AS assigned" : "");
	$rows = $wpdb->get_results("SELECT {$select} FROM {$source} ORDER BY id DESC LIMIT 500", ARRAY_A);
	$count = 0;
	foreach ($rows as $r) {
		if (!isset($r['role'])) { $r['role'] = ''; }
		if (!isset($r['assigned'])) { $r['assigned'] = 0; }
		uc_devices_upsert_row($r);
		$count++;
	}
	return $count;
}

// Schedule periodic sync of UC device mirror to Admin hub
add_action('init', function(){
	if (!wp_next_scheduled('tmon_uc_sync_devices_cron')) {
		wp_schedule_event(time() + 120, 'hourly', 'tmon_uc_sync_devices_cron');
	}
});

add_action('tmon_uc_sync_devices_cron', function(){
	if (!function_exists('tmon_uc_push_devices_to_hub')) return;
	tmon_uc_push_devices_to_hub();
});

// Push UC device mirror to Admin hub (used by cron to keep Admin in sync without device double-posts)
function tmon_uc_push_devices_to_hub($limit = 500) {
	$hub = trim(get_option('tmon_uc_hub_url', ''));
	$hub_key = get_option('tmon_uc_hub_shared_key', '');
	if (!$hub || !$hub_key) return 0;
	uc_devices_ensure_table();
	global $wpdb;
	$table = $wpdb->prefix . 'tmon_uc_devices';
	$rows = $wpdb->get_results($wpdb->prepare("SELECT unit_id, machine_id, unit_name, role, assigned, updated_at FROM {$table} ORDER BY updated_at DESC LIMIT %d", intval($limit)), ARRAY_A);
	if (!$rows) return 0;
	$endpoint = rtrim($hub, '/') . '/wp-json/tmon-admin/v1/uc/sync-devices';
	$resp = wp_remote_post($endpoint, [
		'timeout' => 15,
		'headers' => [
			'Content-Type' => 'application/json',
			'X-TMON-HUB' => $hub_key,
		],
		'body' => wp_json_encode(['devices' => $rows]),
	]);
	if (is_wp_error($resp)) return 0;
	$code = wp_remote_retrieve_response_code($resp);
	if ($code !== 200) return 0;
	return count($rows);
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

	// Auto refresh when empty
	if (empty($devices) && empty($unassigned)) {
		$hub_result = uc_devices_refresh_from_admin();
		if (empty($hub_result)) {
			uc_devices_refresh_from_local_mirror();
		}
		$devices = uc_devices_get_assigned();
		$unassigned = uc_devices_get_unassigned();
	}

	echo '<div class="wrap"><h1>' . esc_html__('Provisioned Devices', 'tmon') . '</h1>';
	if (empty($devices) && empty($unassigned)) {
		echo '<div class="card" style="padding:12px;"><p><em>No devices found. Verify Admin hub URL and shared key, then click Refresh.</em></p></div>';
	}

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

/**
 * Shortcode: [tmon_uc_devices assigned="1|0|all" limit="50"]
 * Displays devices from local mirror, ensuring refresh when list is empty.
 */
add_shortcode('tmon_uc_devices', function ($atts) {
	$atts = shortcode_atts(array(
		'assigned' => 'all',
		'limit' => 50,
	), $atts);
	$assigned = strtolower($atts['assigned']);
	$limit = max(1, intval($atts['limit']));
	uc_devices_ensure_table();

	// Auto refresh when table empty
	global $wpdb;
	$table = $wpdb->prefix . 'tmon_uc_devices';
	$total = (int) $wpdb->get_var("SELECT COUNT(*) FROM {$table}");
	if ($total === 0) {
		$ref = uc_devices_refresh_from_admin();
		if (empty($ref)) {
			uc_devices_refresh_from_local_mirror();
		}
	}

	$where = '1=1';
	if ($assigned === '1') { $where .= ' AND assigned = 1'; }
	elseif ($assigned === '0') { $where .= ' AND assigned = 0'; }
	$rows = $wpdb->get_results($wpdb->prepare("SELECT unit_id,machine_id,unit_name,role,assigned FROM {$table} WHERE {$where} ORDER BY id DESC LIMIT %d", $limit), ARRAY_A);

	if (empty($rows)) {
		return '<div class="tmon-uc-devices-empty">' . esc_html__('No devices found.', 'tmon') . '</div>';
	}
	$out  = '<div class="tmon-uc-devices"><table class="widefat striped"><thead><tr>';
	$out .= '<th>' . esc_html__('UNIT_ID','tmon') . '</th><th>' . esc_html__('MACHINE_ID','tmon') . '</th><th>' . esc_html__('Name','tmon') . '</th><th>' . esc_html__('Role','tmon') . '</th><th>' . esc_html__('Status','tmon') . '</th>';
	$out .= '</tr></thead><tbody>';
	foreach ($rows as $r) {
		$st = !empty($r['assigned']) ? esc_html__('Assigned','tmon') : esc_html__('Unassigned','tmon');
		$out .= '<tr><td>' . esc_html($r['unit_id']) . '</td><td>' . esc_html($r['machine_id']) . '</td><td>' . esc_html($r['unit_name']) . '</td><td>' . esc_html($r['role']) . '</td><td>' . $st . '</td></tr>';
	}
	$out .= '</tbody></table></div>';
	return $out;
});

/**
 * Helper: get staged settings JSON for a unit or machine from UC mirror.
 */
function uc_get_staged_settings($unit_id = '', $machine_id = '') {
	global $wpdb;
	uc_devices_ensure_table();
	$table = $wpdb->prefix . 'tmon_uc_devices';
	$row = null;
	if ($unit_id) {
		$row = $wpdb->get_row($wpdb->prepare("SELECT staged_settings, staged_at FROM {$table} WHERE unit_id=%s LIMIT 1", $unit_id), ARRAY_A);
	} elseif ($machine_id) {
		$row = $wpdb->get_row($wpdb->prepare("SELECT staged_settings, staged_at FROM {$table} WHERE machine_id=%s LIMIT 1", $machine_id), ARRAY_A);
	}
	if (!$row || empty($row['staged_settings'])) return ['staged'=>false,'settings'=>[]];
	$json = json_decode($row['staged_settings'], true);
	if (!is_array($json)) $json = [];
	return ['staged'=>true,'staged_at'=>$row['staged_at'],'settings'=>$json];
}

// Provisioning helpers for Unit Connector: ensure canonical role options and render helper are available.

if (!function_exists('uc_get_node_role_options')) {
	function uc_get_node_role_options() {
		$opts = get_option('tmon_admin_node_roles', null);
		if (is_array($opts) && !empty($opts)) {
			return $opts;
		}
		// canonical device roles (match firmware/ADMIN_MODAL_DEFAULT_ROLE_OPTIONS)
		return array('base', 'wifi', 'remote');
	}
}

if (!function_exists('uc_render_node_role_select')) {
	function uc_render_node_role_select($name = 'role', $selected = '', $attrs = array()) {
		$opts = uc_get_node_role_options();
		$attr_str = '';
		if (is_array($attrs)) {
			foreach ($attrs as $k => $v) {
				$attr_str .= ' ' . esc_attr($k) . '="' . esc_attr($v) . '"';
			}
		}
		echo '<select name="'.esc_attr($name).'" id="'.esc_attr($name).'"'.$attr_str.'>';
		echo '<option value="">Select a type</option>';
		foreach ($opts as $o) {
			$sel = ($o === $selected) ? ' selected' : '';
			echo '<option value="'.esc_attr($o).'"'.$sel.'>'.esc_html($o).'</option>';
		}
		echo '</select>';
	}
}