<?php
// TMON Admin OTA Jobs Page
if (!function_exists('tmon_admin_get_ota_jobs')) return;
$jobs = tmon_admin_get_ota_jobs();
echo '<div class="wrap"><h1>OTA Jobs</h1>';
echo '<table class="widefat"><thead><tr><th>Time</th><th>Device</th><th>Type</th><th>Status</th><th>Details</th></tr></thead><tbody>';
foreach ($jobs as $job) {
    echo '<tr><td>' . esc_html($job['timestamp']) . '</td><td>' . esc_html($job['device_id'] ?? '') . '</td><td>' . esc_html($job['type'] ?? '') . '</td><td>' . esc_html($job['status'] ?? '') . '</td><td>' . esc_html(json_encode($job)) . '</td></tr>';
}
echo '</tbody></table></div>';
