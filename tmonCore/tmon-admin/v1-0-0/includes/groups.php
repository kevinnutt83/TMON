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
