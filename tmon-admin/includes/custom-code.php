<?php
// TMON Admin Custom Code Management
// Usage: do_action('tmon_admin_custom_code', $code_info);
add_action('tmon_admin_custom_code', function($code_info) {
    $codes = get_option('tmon_admin_custom_code', []);
    $code_info['timestamp'] = current_time('mysql');
    $codes[] = $code_info;
    update_option('tmon_admin_custom_code', $codes);
});

// Helper: Get custom code entries
function tmon_admin_get_custom_code() {
    $codes = get_option('tmon_admin_custom_code', []);
    return array_reverse($codes);
}
