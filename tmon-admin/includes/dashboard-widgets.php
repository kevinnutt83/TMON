<?php
// TMON Admin Dashboard Widgets (System Health, Device Status, AI State)
add_action('wp_dashboard_setup', function() {
    wp_add_dashboard_widget('tmon_admin_system_health', 'TMON System Health', 'tmon_admin_widget_system_health');
    wp_add_dashboard_widget('tmon_admin_device_status', 'TMON Device Status', 'tmon_admin_widget_device_status');
    wp_add_dashboard_widget('tmon_admin_ai_state', 'TMON AI State', 'tmon_admin_widget_ai_state');
});

function tmon_admin_widget_system_health() {
    $audit = get_option('tmon_admin_audit_logs', []);
    $errors = array_filter($audit, function($log) { return stripos($log['action'], 'error') !== false; });
    echo '<p><strong>Recent Errors:</strong> ' . count($errors) . '</p>';
    if ($errors) {
        echo '<ul>';
        foreach (array_slice($errors, -5) as $e) {
            echo '<li>' . esc_html($e['timestamp'] . ': ' . $e['details']) . '</li>';
        }
        echo '</ul>';
    }
}

function tmon_admin_widget_device_status() {
    $ota = get_option('tmon_admin_ota_jobs', []);
    $pending = array_filter($ota, function($j) { return $j['status'] === 'pending'; });
    echo '<p><strong>Pending OTA Jobs:</strong> ' . count($pending) . '</p>';
}

function tmon_admin_widget_ai_state() {
    $ai = get_option('tmon_admin_ai_archive', []);
    echo '<p><strong>AI Events:</strong> ' . count($ai) . '</p>';
    if ($ai) {
        echo '<ul>';
        foreach (array_slice($ai, -5) as $a) {
            echo '<li>' . esc_html($a['timestamp']) . ': ' . esc_html(json_encode($a['payload'])) . '</li>';
        }
        echo '</ul>';
    }
}
