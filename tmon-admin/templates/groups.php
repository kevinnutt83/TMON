<?php
// TMON Admin Groups Page
if (!function_exists('tmon_admin_get_groups')) return;
$groups = tmon_admin_get_groups();
echo '<div class="wrap"><h1>Groups</h1>';
echo '<table class="widefat"><thead><tr><th>Time</th><th>Name</th><th>Type</th><th>Details</th></tr></thead><tbody>';
foreach ($groups as $g) {
    echo '<tr><td>' . esc_html($g['timestamp']) . '</td><td>' . esc_html($g['name'] ?? '') . '</td><td>' . esc_html($g['type'] ?? '') . '</td><td>' . esc_html(json_encode($g)) . '</td></tr>';
}
echo '</tbody></table></div>';
