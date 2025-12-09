<?php
// ...existing code...

add_action('tmon_admin_uc_connectors_page', function () {
	static $printed = false; if ($printed) return; $printed = true;
	global $wpdb;

	$table = $wpdb->prefix . 'tmon_uc_sites';
	echo '<div class="wrap"><h1>Unit Connectors</h1>';

	if (!tmon_admin_table_exists($table)) {
		echo '<p>No Unit Connectors found.</p></div>';
		return;
	}

	$rows = $wpdb->get_results("SELECT id, normalized_url, hub_key, read_token, last_seen, created_at FROM $table ORDER BY COALESCE(last_seen, created_at) DESC LIMIT 200");
	echo '<table class="widefat striped"><thead><tr><th>ID</th><th>URL</th><th>Paired</th><th>Last Seen</th></tr></thead><tbody>';
	if ($rows) {
		foreach ($rows as $r) {
			echo '<tr><td>' . intval($r->id) . '</td><td>' . esc_html($r->normalized_url) . '</td><td>' . esc_html($r->created_at) . '</td><td>' . esc_html($r->last_seen) . '</td></tr>';
		}
	} else {
		echo '<tr><td colspan="4">No paired Unit Connectors.</td></tr>';
	}
	echo '</tbody></table></div>';
});

// ...existing code...