<?php
// TMON Admin Audit Logging
// Usage: do_action('tmon_admin_audit', $action, $details, $user_id);
add_action('tmon_admin_audit', function($action, $details = '', $user_id = null) {
    $logs = get_option('tmon_admin_audit_logs', []);
    $logs[] = [
        'timestamp' => current_time('mysql'),
        'user_id' => $user_id ?: get_current_user_id(),
        'action' => $action,
        'details' => $details,
    ];
    update_option('tmon_admin_audit_logs', $logs);
});

// Helper: Get audit logs
function tmon_admin_get_audit_logs($limit = 100) {
    $logs = get_option('tmon_admin_audit_logs', []);
    return array_slice(array_reverse($logs), 0, $limit);
}
