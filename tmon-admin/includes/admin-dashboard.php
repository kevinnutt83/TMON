<?php
// TMON Admin Dashboard Page
// Content is rendered by the template in tmon_admin_dashboard_page()

if (!function_exists('tmon_admin_diagnostics_page')) {
	function tmon_admin_diagnostics_page() {
		if (!current_user_can('manage_options')) {
			wp_die('Forbidden');
		}

		$unit_id = isset($_GET['unit_id']) ? sanitize_text_field(wp_unslash((string) $_GET['unit_id'])) : '';
		$limit = isset($_GET['limit']) ? intval($_GET['limit']) : 100;
		$limit = max(1, min($limit, 500));

		$store = get_option('tmon_admin_device_diagnostics', []);
		if (!is_array($store)) {
			$store = [];
		}

		if ($unit_id !== '') {
			$store = isset($store[$unit_id]) ? [$unit_id => $store[$unit_id]] : [];
		}

		$rows = array_values($store);
		usort($rows, function ($a, $b) {
			$ta = isset($a['received_at']) ? strtotime((string) $a['received_at']) : 0;
			$tb = isset($b['received_at']) ? strtotime((string) $b['received_at']) : 0;
			return $tb <=> $ta;
		});
		$rows = array_slice($rows, 0, $limit);

		echo '<div class="wrap">';
		echo '<h1>Device Diagnostics</h1>';
		echo '<p class="description">Latest diagnostics pushed by devices after repeated failures or scheduled snapshots.</p>';

		echo '<form method="get" style="margin:12px 0">';
		echo '<input type="hidden" name="page" value="tmon-admin-diagnostics">';
		echo '<label for="tmon_diag_unit" style="margin-right:8px">Unit ID</label>';
		echo '<input id="tmon_diag_unit" type="text" name="unit_id" value="' . esc_attr($unit_id) . '" placeholder="all units" style="margin-right:12px">';
		echo '<label for="tmon_diag_limit" style="margin-right:8px">Limit</label>';
		echo '<input id="tmon_diag_limit" type="number" min="1" max="500" name="limit" value="' . intval($limit) . '" style="width:90px;margin-right:12px">';
		submit_button('Filter', 'secondary', '', false);
		echo ' <a class="button" href="' . esc_url(admin_url('admin.php?page=tmon-admin-diagnostics')) . '">Reset</a>';
		echo '</form>';

		echo '<table class="widefat striped">';
		echo '<thead><tr><th>Unit ID</th><th>Received</th><th>Node</th><th>Firmware</th><th>Errors</th><th>Last Error</th><th>REST Error</th></tr></thead><tbody>';
		foreach ($rows as $row) {
			$rest_error = '';
			if (isset($row['rest_error']) && is_array($row['rest_error']) && !empty($row['rest_error'])) {
				$rest_error = wp_json_encode($row['rest_error']);
			}
			echo '<tr>';
			echo '<td>' . esc_html((string) ($row['unit_id'] ?? '')) . '</td>';
			echo '<td>' . esc_html((string) ($row['received_at'] ?? '')) . '</td>';
			echo '<td>' . esc_html((string) ($row['node_type'] ?? '')) . '</td>';
			echo '<td>' . esc_html((string) ($row['firmware_version'] ?? '')) . '</td>';
			echo '<td>' . intval($row['error_count'] ?? 0) . '</td>';
			echo '<td>' . esc_html((string) ($row['last_error'] ?? '')) . '</td>';
			echo '<td><code>' . esc_html((string) $rest_error) . '</code></td>';
			echo '</tr>';
		}
		if (empty($rows)) {
			echo '<tr><td colspan="7"><em>No diagnostics found for this filter.</em></td></tr>';
		}
		echo '</tbody></table>';
		echo '</div>';
	}
}
