<?php
// TMON Admin Notifications
// Usage: do_action('tmon_admin_notify', $type, $message, $context);
add_action('tmon_admin_notify', function($type, $message, $context = []) {
    $notices = get_option('tmon_admin_notifications', []);
    $notices[] = [
        'timestamp' => current_time('mysql'),
        'type' => $type,
        'message' => $message,
        'context' => $context,
        'read' => false,
    ];
    update_option('tmon_admin_notifications', $notices);
});

// Helper: Get notifications
function tmon_admin_get_notifications($unread_only = false) {
    $notices = get_option('tmon_admin_notifications', []);
    if ($unread_only) {
        $notices = array_filter($notices, function($n) { return empty($n['read']); });
    }
    return array_reverse($notices);
}
