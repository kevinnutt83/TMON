<?php
// TMON Admin OTA Job Management
// Usage: do_action('tmon_admin_ota_job', $job);
add_action('tmon_admin_ota_job', function($job) {
    $jobs = get_option('tmon_admin_ota_jobs', []);
    $job['timestamp'] = current_time('mysql');
    $job['status'] = $job['status'] ?? 'pending';
    $jobs[] = $job;
    update_option('tmon_admin_ota_jobs', $jobs);
});

// Helper: Get OTA jobs
function tmon_admin_get_ota_jobs($status = null) {
    $jobs = get_option('tmon_admin_ota_jobs', []);
    if ($status) {
        $jobs = array_filter($jobs, function($j) use ($status) { return $j['status'] === $status; });
    }
    return array_reverse($jobs);
}
