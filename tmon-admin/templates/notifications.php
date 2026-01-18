<?php
// TMON Admin Notifications Page
if (!function_exists('tmon_admin_get_notifications')) return;
$notices = tmon_admin_get_notifications();
echo '<div class="wrap"><h1>Notifications</h1>';
echo '<table class="widefat"><thead><tr><th>Time</th><th>Type</th><th>Message</th><th>Context</th></tr></thead><tbody>';
foreach ($notices as $n) {
    echo '<tr><td>' . esc_html($n['timestamp']) . '</td><td>' . esc_html($n['type']) . '</td><td>' . esc_html($n['message']) . '</td><td>' . esc_html(json_encode($n['context'])) . '</td></tr>';
}
echo '</tbody></table></div>';
