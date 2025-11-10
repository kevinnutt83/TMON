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
