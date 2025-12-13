<?php
// ...existing code...

add_action('tmon_admin_command_logs_page', function () {
	static $printed = false; if ($printed) return; $printed = true;
	global $wpdb;

	$table = $wpdb->prefix . 'tmon_device_commands';
	if (!tmon_admin_table_exists($table)) {
		echo '<div class="wrap"><h1>Command Logs</h1><p>Command logs table missing.</p></div>';
		return;
	}

	$has_updated = tmon_admin_column_exists($table, 'updated_at');
	$has_status = tmon_admin_column_exists($table, 'status');

	$select = "SELECT id, device_id AS unit_id, command, params";
	$select .= $has_status ? ", status" : ", 'staged' AS status";
	$select .= $has_updated ? ", COALESCE(updated_at, created_at) AS updated_at" : ", created_at AS updated_at";

	$sql = "$select FROM $table ORDER BY " . ($has_updated ? "COALESCE(updated_at, created_at)" : "created_at") . " DESC LIMIT 200";
	$rows = $wpdb->get_results($sql);

	echo '<div class="wrap"><h1>TMON Command Logs</h1>';
	echo '<table class="widefat striped"><thead><tr><th>ID</th><th>Unit</th><th>Command</th><th>Status</th><th>Updated</th></tr></thead><tbody>';
	if ($rows) {
		foreach ($rows as $r) {
			echo '<tr><td>' . intval($r->id) . '</td><td>' . esc_html($r->unit_id) . '</td><td>' . esc_html($r->command) . '</td><td>' . esc_html($r->status) . '</td><td>' . esc_html($r->updated_at) . '</td></tr>';
		}
	} else {
		echo '<tr><td colspan="5">No command logs</td></tr>';
	}
	echo '</tbody></table></div>';
});

// AJAX handler (if used) should also guard columns
add_action('wp_ajax_tmon_admin_get_command_logs', function () {
	if (!current_user_can('manage_options')) {
		wp_send_json_error(['message' => 'forbidden'], 403);
	}
	check_ajax_referer('tmon-admin', 'nonce');
	global $wpdb;
	$table = $wpdb->prefix . 'tmon_device_commands';
	$has_updated = tmon_admin_column_exists($table, 'updated_at');
	$has_status = tmon_admin_column_exists($table, 'status');
	$select = "SELECT id, device_id AS unit_id, command, params";
	if ($has_status) $select .= ", status";
	else $select .= ", 'staged' AS status";
	if ($has_updated) $select .= ", COALESCE(updated_at, created_at) AS updated_at";
	else $select .= ", created_at AS updated_at";
	$sql = "$select FROM $table ORDER BY " . ($has_updated ? "COALESCE(updated_at, created_at)" : "created_at") . " DESC LIMIT 200";
	wp_send_json_success($wpdb->get_results($sql));
});

// ...existing code...