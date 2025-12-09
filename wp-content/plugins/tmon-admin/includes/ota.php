<?php
// ...existing code...

add_action('tmon_admin_ota_page', function () {
	static $printed = false; if ($printed) return; $printed = true;
	global $wpdb;

	$table = $wpdb->prefix . 'tmon_ota_jobs';
	if (!tmon_admin_table_exists($table)) {
		echo '<div class="wrap"><h1>OTA Management</h1><p>OTA jobs table missing.</p></div>';
		return;
	}

	$has_action = tmon_admin_column_exists($table, 'action');
	$has_updated = tmon_admin_column_exists($table, 'updated_at');

	$select = "SELECT id, unit_id";
	$select .= $has_action ? ", action" : ", '' AS action";
	$select .= ", args, status, created_at";
	$select .= $has_updated ? ", updated_at" : ", NULL AS updated_at";

	$sql = "$select FROM $table ORDER BY created_at DESC LIMIT 200";
	$rows = $wpdb->get_results($sql);

	echo '<div class="wrap"><h1>OTA Management</h1>';
	echo '<table class="widefat striped"><thead><tr><th>ID</th><th>Unit</th><th>Action</th><th>Status</th><th>Created</th><th>Updated</th></tr></thead><tbody>';
	if ($rows) {
		foreach ($rows as $r) {
			echo '<tr><td>' . intval($r->id) . '</td><td>' . esc_html($r->unit_id) . '</td><td>' . esc_html($r->action) . '</td><td>' . esc_html($r->status) . '</td><td>' . esc_html($r->created_at) . '</td><td>' . esc_html($r->updated_at) . '</td></tr>';
		}
	} else {
		echo '<tr><td colspan="6">No OTA jobs.</td></tr>';
	}
	echo '</tbody></table></div>';
});

// ...existing code...