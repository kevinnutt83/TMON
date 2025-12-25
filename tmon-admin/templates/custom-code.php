<?php
// TMON Admin Custom Code Page
if (!function_exists('tmon_admin_get_custom_code')) return;
$codes = tmon_admin_get_custom_code();
echo '<div class="wrap"><h1>Custom Code</h1>';
echo '<table class="widefat"><thead><tr><th>Time</th><th>Name</th><th>Type</th><th>Code</th></tr></thead><tbody>';
foreach ($codes as $c) {
    echo '<tr><td>' . esc_html($c['timestamp']) . '</td><td>' . esc_html($c['name'] ?? '') . '</td><td>' . esc_html($c['type'] ?? '') . '</td><td><pre>' . esc_html($c['code'] ?? '') . '</pre></td></tr>';
}
echo '</tbody></table></div>';
