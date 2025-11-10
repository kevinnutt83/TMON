<?php
// TMON Admin Notifications UI
add_action('admin_menu', function(){
    add_submenu_page('tmon-admin', 'Notifications', 'Notifications', 'manage_options', 'tmon-admin-notifications', 'tmon_admin_notifications_page');
});

function tmon_admin_notifications_page(){
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    // Actions: mark read, mark all read, filter
    $filter = isset($_GET['filter']) && $_GET['filter'] === 'unread' ? 'unread' : 'all';
    if (isset($_POST['tmon_mark_all_read'])) {
        if (!function_exists('tmon_admin_verify_nonce') || !tmon_admin_verify_nonce('tmon_admin_notices')) {
            echo '<div class="notice notice-error"><p>Security check failed. Please refresh and try again.</p></div>';
        } else {
        $notices = get_option('tmon_admin_notifications', []);
        foreach ($notices as &$n) { $n['read'] = true; }
        update_option('tmon_admin_notifications', $notices);
        echo '<div class="updated"><p>All notifications marked as read.</p></div>';
        }
    }
    if (isset($_POST['tmon_mark_read']) && isset($_POST['idx'])) {
        if (!function_exists('tmon_admin_verify_nonce') || !tmon_admin_verify_nonce('tmon_admin_notices')) {
            echo '<div class="notice notice-error"><p>Security check failed. Please refresh and try again.</p></div>';
        } else {
        $idx = intval($_POST['idx']);
        $notices = get_option('tmon_admin_notifications', []);
        if (isset($notices[$idx])) { $notices[$idx]['read'] = true; update_option('tmon_admin_notifications', $notices); }
        echo '<div class="updated"><p>Notification marked as read.</p></div>';
        }
    }
    $notices = get_option('tmon_admin_notifications', []);
    if ($filter === 'unread') {
        $notices = array_filter($notices, function($n){ return empty($n['read']); });
    }
    echo '<div class="wrap"><h1>Notifications</h1>';
    echo '<p><a class="button" href="'.esc_url(admin_url('admin.php?page=tmon-admin-notifications&filter=all')).'">All</a> ';
    echo '<a class="button" href="'.esc_url(admin_url('admin.php?page=tmon-admin-notifications&filter=unread')).'">Unread</a></p>';
    echo '<form method="post" style="margin:8px 0">';
    wp_nonce_field('tmon_admin_notices');
    submit_button('Mark All Read', 'secondary', 'tmon_mark_all_read', false);
    echo '</form>';
    echo '<table class="widefat"><thead><tr><th>#</th><th>Time</th><th>Type</th><th>Message</th><th>Context</th><th>Status</th><th>Action</th></tr></thead><tbody>';
    foreach ($notices as $i => $n) {
        echo '<tr>';
        echo '<td>'.intval($i).'</td>';
        echo '<td>'.esc_html($n['timestamp'] ?? '').'</td>';
        echo '<td>'.esc_html($n['type'] ?? '').'</td>';
        echo '<td>'.esc_html($n['message'] ?? '').'</td>';
        echo '<td><code>'.esc_html(is_array($n['context'] ?? null) ? wp_json_encode($n['context']) : strval($n['context'] ?? '')).'</code></td>';
        echo '<td>'.(empty($n['read'])?'<span style="color:#e67e22">Unread</span>':'<span style="color:#2ecc71">Read</span>').'</td>';
        echo '<td><form method="post">';
        wp_nonce_field('tmon_admin_notices');
        echo '<input type="hidden" name="idx" value="'.intval($i).'">';
        echo '<button class="button" name="tmon_mark_read" value="1">Mark Read</button>';
        echo '</form></td>';
        echo '</tr>';
    }
    if (empty($notices)) echo '<tr><td colspan="7"><em>No notifications.</em></td></tr>';
    echo '</tbody></table></div>';
}
