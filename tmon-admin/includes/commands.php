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
	// Pending commands panel
	$pending = $wpdb->get_results($wpdb->prepare("SELECT id, device_id AS unit_id, command, params, status, created_at FROM {$table} WHERE status IN (%s,%s) ORDER BY created_at DESC LIMIT 100", 'queued', 'staged'));
	echo '<div class="tmon-card"><h2>Pending Commands</h2>';
	if ($pending) {
		echo '<table class="widefat striped"><thead><tr><th>ID</th><th>Unit</th><th>Command</th><th>Status</th><th>Created</th></tr></thead><tbody>';
		foreach ($pending as $p) {
			echo '<tr><td>'.intval($p->id).'</td><td>'.esc_html($p->unit_id).'</td><td>'.esc_html($p->command).'</td><td>'.esc_html($p->status).'</td><td>'.esc_html($p->created_at).'</td></tr>';
		}
		echo '</tbody></table>';
	} else {
		echo '<p>No pending commands.</p>';
	}
	echo '<form method="post" action="'.esc_url(admin_url('admin-post.php')).'" style="margin-top:10px;">';
	wp_nonce_field('tmon_admin_clear_commands');
	echo '<input type="hidden" name="action" value="tmon_admin_clear_commands" />';
	echo '<p><label>Unit ID (optional) <input type="text" name="unit_id" class="regular-text" placeholder="device_id"></label> ';
	echo '<label>Status <select name="status"><option value="queued">queued</option><option value="staged">staged</option><option value="all">all</option></select></label> ';
	echo '<button class="button button-secondary">Clear Commands</button></p>';
	echo '</form></div>';

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

// Admin-post: clear pending commands
add_action('admin_post_tmon_admin_clear_commands', function(){
	if (!current_user_can('manage_options')) wp_die('Forbidden');
	check_admin_referer('tmon_admin_clear_commands');
	global $wpdb;
	$table = $wpdb->prefix . 'tmon_device_commands';
	$where = [];
	$unit_id = isset($_POST['unit_id']) ? sanitize_text_field($_POST['unit_id']) : '';
	$status = isset($_POST['status']) ? sanitize_text_field($_POST['status']) : 'queued';
	if ($unit_id) {
		$where['device_id'] = $unit_id;
	}
	if ($status !== 'all') {
		$where['status'] = $status;
	}
	if (!empty($where)) {
		$wpdb->delete($table, $where);
	} else {
		// Clear all queued/staged when no filters provided
		$wpdb->query($wpdb->prepare("DELETE FROM {$table} WHERE status IN (%s,%s)", 'queued', 'staged'));
	}
	wp_safe_redirect(add_query_arg('cleared', '1', wp_get_referer() ?: admin_url('admin.php?page=tmon-admin-command-logs')));
	exit;
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