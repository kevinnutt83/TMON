<?php
// TMON Admin OTA Job Management
// Usage: do_action('tmon_admin_ota_job', $job);
add_action('tmon_admin_ota_job', function($job) {
    $jobs = get_option('tmon_admin_ota_jobs', []);
    $job['timestamp'] = current_time('mysql');
    $job['status'] = $job['status'] ?? 'pending';
    $jobs[] = $job;
    update_option('tmon_admin_ota_jobs', $jobs);
});

// Helper: Get OTA jobs
function tmon_admin_get_ota_jobs($status = null) {
    $jobs = get_option('tmon_admin_ota_jobs', []);
    if ($status) {
        $jobs = array_filter($jobs, function($j) use ($status) { return $j['status'] === $status; });
    }
    return array_reverse($jobs);
}

function tmon_admin_ota_page(){
	echo '<div class="wrap"><h1>OTA Management</h1>';
	tmon_admin_render_ota_jobs_and_actions();
	echo '</div>';
}
function tmon_admin_render_ota_jobs_and_actions(){
	global $wpdb; $jobs = $wpdb->prefix.'tmon_ota_jobs';
	$rows = $wpdb->get_results("SELECT id, unit_id, action, args, status, created_at, updated_at FROM {$jobs} ORDER BY created_at DESC LIMIT 200", ARRAY_A);
	echo '<div class="tmon-card"><h2>OTA Jobs</h2><table class="wp-list-table widefat striped"><thead><tr><th>ID</th><th>Unit</th><th>Action</th><th>Args</th><th>Status</th><th>Created</th><th>Updated</th></tr></thead><tbody>';
	foreach ($rows as $r){
		echo '<tr><td>'.$r['id'].'</td><td>'.$r['unit_id'].'</td><td>'.$r['action'].'</td><td><code>'.$r['args'].'</code></td><td>'.$r['status'].'</td><td>'.$r['created_at'].'</td><td>'.$r['updated_at'].'</td></tr>';
	}
	echo '</tbody></table></div>';
	echo '<div class="tmon-card"><h2>Device Actions</h2><form method="post" action="'.esc_url(admin_url('admin-ajax.php')).'"><input type="hidden" name="action" value="tmon_send_device_command" />';
	echo '<p><label>Unit ID <input name="unit_id" required></label> <label>Command <select name="command"><option value="download_logs">download_logs</option><option value="reboot">reboot</option><option value="firmware_update">firmware_update</option><option value="clear_logs">clear_logs</option></select></label> <button class="button button-primary">Send</button></p></form></div>';
}
