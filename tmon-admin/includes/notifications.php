<?php
// TMON Admin Notifications
// Usage: do_action('tmon_admin_notify', $type, $message, $context);
add_action('tmon_admin_notify', function ($message, $context = []) {
	if (!is_array($context)) {
		$context = ['context' => $context];
	}
	$notice = sprintf('[TMON] %s %s', (string) $message, empty($context) ? '' : wp_json_encode($context));
	error_log($notice); // keep lightweight and reliable

	// Optionally surface in WP Admin UI:
	add_action('admin_notices', function () use ($notice) {
		echo '<div class="notice notice-info"><p>' . esc_html($notice) . '</p></div>';
	});
}, 10, 2);

// Helper: Get notifications
function tmon_admin_get_notifications($unread_only = false) {
    $notices = get_option('tmon_admin_notifications', []);
    if ($unread_only) {
        $notices = array_filter($notices, function($n) { return empty($n['read']); });
    }
    return array_reverse($notices);
}

function tmon_admin_notifications_page(){
	echo '<div class="wrap"><h1>Notifications</h1>';
	tmon_admin_render_notifications();
	echo '</div>';
}
function tmon_admin_render_notifications(){
	global $wpdb; $tbl = $wpdb->prefix.'tmon_notifications';
	$rows = $wpdb->get_results("SELECT id, title, message, level, created_at, read_at FROM {$tbl} ORDER BY created_at DESC LIMIT 200", ARRAY_A);
	echo '<table class="wp-list-table widefat striped"><thead><tr><th>ID</th><th>Title</th><th>Level</th><th>Message</th><th>Created</th><th>Status</th></tr></thead><tbody>';
	foreach ($rows as $r) {
		$status = $r['read_at'] ? 'read' : 'unread';
		echo '<tr><td>'.esc_html($r['id']).'</td><td>'.esc_html($r['title']).'</td><td>'.esc_html($r['level']).'</td><td>'.esc_html($r['message']).'</td><td>'.esc_html($r['created_at']).'</td><td>'.esc_html($status).'</td></tr>';
	}
	echo '</tbody></table>';
}
