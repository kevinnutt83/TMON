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

function tmon_admin_groups_page(){
	echo '<div class="wrap"><h1>Groups & Hierarchy</h1>';
	tmon_admin_render_groups_hierarchy();
	echo '</div>';
}
function tmon_admin_render_groups_hierarchy(){
	global $wpdb;
	$companies = $wpdb->prefix.'tmon_companies';
	$sites     = $wpdb->prefix.'tmon_sites';
	$zones     = $wpdb->prefix.'tmon_zones';
	$groups    = $wpdb->prefix.'tmon_groups';
	$devices   = $wpdb->prefix.'tmon_devices';
	echo '<div class="tmon-responsive-table"><table class="wp-list-table widefat striped"><thead><tr><th>Company > Location > Zone > Group</th><th>Devices</th></tr></thead><tbody>';
	$companies_rows = $wpdb->get_results("SELECT id, name FROM {$companies} ORDER BY name ASC", ARRAY_A);
	foreach ($companies_rows as $c) {
		$sites_rows = $wpdb->get_results($wpdb->prepare("SELECT id, name FROM {$sites} WHERE company_id=%d ORDER BY name ASC", $c['id']), ARRAY_A);
		foreach ($sites_rows as $s) {
			$zones_rows = $wpdb->get_results($wpdb->prepare("SELECT id, name FROM {$zones} WHERE site_id=%d ORDER BY name ASC", $s['id']), ARRAY_A);
			foreach ($zones_rows as $z) {
				$groups_rows = $wpdb->get_results($wpdb->prepare("SELECT id, name FROM {$groups} WHERE zone_id=%d ORDER BY name ASC", $z['id']), ARRAY_A);
				foreach ($groups_rows as $g) {
					$dev_rows = $wpdb->get_results($wpdb->prepare("SELECT unit_id, unit_name FROM {$devices} WHERE group_id=%d ORDER BY unit_name ASC", $g['id']), ARRAY_A);
					echo '<tr><td>'.esc_html($c['name'].' > '.$s['name'].' > '.$z['name'].' > '.$g['name']).'</td><td>';
					if ($dev_rows) {
						echo '<ul>'; foreach ($dev_rows as $d) { echo '<li><a href="'.esc_url( admin_url('admin.php?page=tmon-admin-provisioned&unit_id='.$d['unit_id']) ).'">'.esc_html($d['unit_name']).' ('.esc_html($d['unit_id']).')</a></li>'; } echo '</ul>';
					} else { echo 'No Devices'; }
					echo '</td></tr>';
				}
			}
		}
	}
	echo '</tbody></table></div>';
}
