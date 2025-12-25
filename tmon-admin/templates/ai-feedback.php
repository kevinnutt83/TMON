<?php
// TMON Admin AI Feedback Page
if (!function_exists('tmon_admin_get_ai_feedback')) return;
$fb = tmon_admin_get_ai_feedback();
echo '<div class="wrap"><h1>AI Feedback</h1>';
echo '<table class="widefat"><thead><tr><th>Time</th><th>User</th><th>Feedback</th></tr></thead><tbody>';
foreach ($fb as $f) {
    echo '<tr><td>' . esc_html($f['timestamp']) . '</td><td>' . esc_html($f['user_id'] ?? '') . '</td><td>' . esc_html(json_encode($f)) . '</td></tr>';
}
echo '</tbody></table></div>';
