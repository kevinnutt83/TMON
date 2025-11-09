<?php
// TMON Admin Audit Log Page
if (!function_exists('tmon_admin_get_audit_logs')) return;
$logs = tmon_admin_get_audit_logs();
echo '<div class="wrap"><h1>Audit Log</h1>';
echo '<table class="widefat"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Details</th></tr></thead><tbody>';
foreach ($logs as $log) {
    echo '<tr><td>' . esc_html($log['timestamp']) . '</td><td>' . esc_html($log['user_id']) . '</td><td>' . esc_html($log['action']) . '</td><td>' . esc_html($log['details']) . '</td></tr>';
}
echo '</tbody></table></div>';
