<?php
// TMON Admin Group/Hierarchy Management
// Usage: do_action('tmon_admin_group_update', $group);
add_action('tmon_admin_group_update', function($group) {
    $groups = get_option('tmon_admin_groups', []);
    $group['timestamp'] = current_time('mysql');
    $groups[] = $group;
    update_option('tmon_admin_groups', $groups);
});

// Helper: Get groups
function tmon_admin_get_groups() {
    $groups = get_option('tmon_admin_groups', []);
    return array_reverse($groups);
}

if (!function_exists('tmon_admin_groups_page')) {
	function tmon_admin_groups_page(){
		echo '<div class="wrap"><h1>Groups & Hierarchy</h1>';
		tmon_admin_render_groups_hierarchy();
		echo '</div>';
	}
}

if (!function_exists('tmon_admin_render_groups_hierarchy')) {
	function tmon_admin_render_groups_hierarchy(){
		global $wpdb;
		$companies = $wpdb->prefix.'tmon_companies';
		$sites     = $wpdb->prefix.'tmon_sites';
		$zones     = $wpdb->prefix.'tmon_zones';
		$groups    = $wpdb->prefix.'tmon_groups';
		$devices   = $wpdb->prefix.'tmon_devices';

		// Verify tables exist
		foreach ([$companies,$sites,$zones,$groups,$devices] as $tbl) {
			$exists = $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $tbl));
			if ($exists !== $tbl) {
				echo '<div class="notice notice-warning"><p>Hierarchy table missing: '.esc_html(basename($tbl)).'.</p></div>';
				echo '<p>No hierarchy data available.</p>';
				return;
			}
		}

		// Safe SELECTs only when tables exist
		echo '<div class="tmon-responsive-table"><table class="wp-list-table widefat striped"><thead><tr><th>Company > Location > Zone > Group</th><th>Devices</th></tr></thead><tbody>';

		$companies_rows = $wpdb->get_results("SELECT id, name FROM {$companies} ORDER BY name ASC", ARRAY_A) ?: [];
		if (!$companies_rows) { echo '<tr><td colspan="2">No companies found.</td></tr>'; echo '</tbody></table></div>'; return; }

		foreach ($companies_rows as $c) {
			$sites_rows = $wpdb->get_results($wpdb->prepare("SELECT id, name FROM {$sites} WHERE company_id=%d ORDER BY name ASC", $c['id']), ARRAY_A) ?: [];
			if (!$sites_rows) { echo '<tr><td>'.esc_html($c['name']).' > (no locations)</td><td>—</td></tr>'; continue; }
			foreach ($sites_rows as $s) {
				$zones_rows = $wpdb->get_results($wpdb->prepare("SELECT id, name FROM {$zones} WHERE site_id=%d ORDER BY name ASC", $s['id']), ARRAY_A) ?: [];
				if (!$zones_rows) { echo '<tr><td>'.esc_html($c['name'].' > '.$s['name']).' > (no zones)</td><td>—</td></tr>'; continue; }
				foreach ($zones_rows as $z) {
					$groups_rows = $wpdb->get_results($wpdb->prepare("SELECT id, name FROM {$groups} WHERE zone_id=%d ORDER BY name ASC", $z['id']), ARRAY_A) ?: [];
					if (!$groups_rows) { echo '<tr><td>'.esc_html($c['name'].' > '.$s['name'].' > '.$z['name']).' > (no groups)</td><td>—</td></tr>'; continue; }
					foreach ($groups_rows as $g) {
						$dev_rows = $wpdb->get_results($wpdb->prepare("SELECT unit_id, unit_name FROM {$devices} WHERE group_id=%d ORDER BY unit_name ASC", $g['id']), ARRAY_A) ?: [];
						echo '<tr><td>'.esc_html($c['name'].' > '.$s['name'].' > '.$z['name'].' > '.$g['name']).'</td><td>';
						if ($dev_rows) {
							echo '<ul>';
							foreach ($dev_rows as $d) {
								echo '<li><a href="'.esc_url( admin_url('admin.php?page=tmon-admin-provisioned&unit_id='.$d['unit_id']) ).'">'.esc_html($d['unit_name']).' ('.esc_html($d['unit_id']).')</a></li>';
							}
							echo '</ul>';
						} else {
							echo 'No Devices';
						}
						echo '</td></tr>';
					}
				}
			}
		}
		echo '</tbody></table></div>';
	}
}
