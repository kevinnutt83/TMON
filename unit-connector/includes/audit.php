<?php
// Audit trail for all admin/user actions
add_action('tmon_audit', function($action, $details = []) {
    global $wpdb, $current_user;
    $wpdb->insert($wpdb->prefix.'tmon_audit', [
        'user_id' => get_current_user_id(),
        'action' => $action,
        'details' => maybe_serialize($details),
        'created_at' => current_time('mysql')
    ]);
}, 10, 2);

function tmon_uc_log_audit($action, $details = []) {
    do_action('tmon_audit', $action, $details);
}
// Usage: tmon_uc_log_audit('edit_unit', ['unit_id'=>123, 'changes'=>['name'=>'New Name']]);
