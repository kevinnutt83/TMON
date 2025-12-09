<?php
// Ensure status column exists
add_action('admin_init', function(){
	global $wpdb; $t = $wpdb->prefix.'tmon_device_commands';
	$cols = $wpdb->get_results("SHOW COLUMNS FROM {$t}", ARRAY_A);
	if (is_array($cols)) {
		$names = array_map(function($c){ return $c['Field']; }, $cols);
		if (!in_array('status', $names, true)) {
			$wpdb->query("ALTER TABLE {$t} ADD COLUMN status varchar(32) NOT NULL DEFAULT 'staged'");
		}
	}
});

// Single renderer hook to be used by submenu callback (prevents double tables)
add_action('tmon_admin_render_command_logs', function(){
	echo '<div class="wrap"><h1>Command Logs</h1>';
	echo '<div class="tmon-filter-form"><form id="tmon-command-filter"><div>';
	echo '<div><label>Unit ID</label><input type="text" name="unit_id" /></div>';
	echo '<div><label>Status</label><select name="status"><option value="">Any</option><option>staged</option><option>queued</option><option>claimed</option><option>applied</option><option>failed</option></select></div>';
	echo '<div><button type="submit" class="button button-primary">Filter</button> <a id="tmon-command-export" href="#" class="button">Export CSV</a></div>';
	echo '</div></form></div>';
	echo '<div class="tmon-responsive-table"><table class="wp-list-table widefat striped tmon-stack-table">';
	echo '<thead><tr><th>ID</th><th>Unit ID</th><th>Command</th><th>Params</th><th>Status</th><th>Updated</th></tr></thead><tbody id="tmon-command-rows"><tr><td colspan="6">Loading…</td></tr></tbody></table></div></div>';
	// Page JS is enqueued via tmon-admin.php; ensure only one renderer path is used.
});

// ...existing code...