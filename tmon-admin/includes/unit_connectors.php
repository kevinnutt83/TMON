<?php
// ...existing code...

add_action('tmon_admin_uc_connectors_page', function () {
	static $printed = false; if ($printed) return; $printed = true;
	global $wpdb;

	$table = $wpdb->prefix . 'tmon_uc_sites';
	echo '<div class="wrap"><h1>Unit Connectors</h1>';

	// Show latest pairing notice if available
	$last_pair = get_option('tmon_admin_uc_last_pair');
	if (is_array($last_pair) && !empty($last_pair['normalized_url'])) {
		$ts = esc_html($last_pair['paired_at'] ?? '');
		$url = esc_html($last_pair['normalized_url']);
		echo '<div class="notice notice-success"><p>Unit Connector paired: ' . $url . ($ts ? ' at ' . $ts : '') . '</p></div>';
		delete_option('tmon_admin_uc_last_pair');
	}

	$rows = [];
	if (function_exists('tmon_admin_table_exists') && tmon_admin_table_exists($table)) {
		$rows = $wpdb->get_results("SELECT id, normalized_url, hub_key, read_token, last_seen, created_at FROM $table ORDER BY COALESCE(last_seen, created_at) DESC LIMIT 200");
	}
	// Fallback to option map if table is missing
	if (!$rows) {
		$map = get_option('tmon_admin_uc_sites', []);
		if (is_array($map)) {
			foreach ($map as $url => $meta) {
				$rows[] = (object) [
					'id' => 0,
					'normalized_url' => $url,
					'hub_key' => $meta['uc_key'] ?? '',
					'read_token' => $meta['read_token'] ?? '',
					'last_seen' => $meta['paired_at'] ?? '',
					'created_at' => $meta['paired_at'] ?? '',
				];
			}
		}
	}
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