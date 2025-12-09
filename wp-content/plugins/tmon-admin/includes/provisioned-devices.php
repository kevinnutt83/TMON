<?php
// ...existing code...

add_action('tmon_admin_provisioned_devices_page', function () {
	static $printed = false; if ($printed) return; $printed = true;
	global $wpdb;

	echo '<div class="wrap"><h1>Provisioned Devices</h1>';

	$prov = $wpdb->prefix . 'tmon_provisioned_devices';
	$mirror = $wpdb->prefix . 'tmon_devices';

	$rows = [];
	if (tmon_admin_table_exists($prov)) {
		$rows = $wpdb->get_results("SELECT id, unit_id, machine_id, unit_name, provisioned_at FROM $prov ORDER BY provisioned_at DESC LIMIT 200");
	} elseif (tmon_admin_table_exists($mirror)) {
		$rows = $wpdb->get_results("SELECT id, unit_id, machine_id, unit_name, provisioned_at FROM $mirror ORDER BY provisioned_at DESC LIMIT 200");
	}

	echo '<table class="widefat striped"><thead><tr><th>ID</th><th>UNIT_ID</th><th>MACHINE_ID</th><th>Name</th><th>Provisioned</th></tr></thead><tbody>';
	if ($rows) {
		foreach ($rows as $r) {
			echo '<tr><td>' . intval($r->id) . '</td><td>' . esc_html($r->unit_id) . '</td><td>' . esc_html($r->machine_id) . '</td><td>' . esc_html($r->unit_name) . '</td><td>' . esc_html($r->provisioned_at) . '</td></tr>';
		}
	} else {
		echo '<tr><td colspan="5">No provisioned devices found.</td></tr>';
	}
	echo '</tbody></table></div>';
});

// ...existing code...