<?php
// Customer dashboard for managing their company and devices
add_shortcode('tmon_customer_dashboard', 'tmon_uc_customer_dashboard');
function tmon_uc_customer_dashboard() {
    if (!is_user_logged_in()) return '<p>Please log in to manage your devices.</p>';
    $user_id = get_current_user_id();
    global $wpdb;
    // Assume user meta 'company_id' links user to their company
    $company_id = get_user_meta($user_id, 'company_id', true);
    if (!$company_id) return '<p>No company assigned.</p>';
    $company = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$wpdb->prefix}tmon_company WHERE id = %d", $company_id), ARRAY_A);
    $devices = $wpdb->get_results($wpdb->prepare("SELECT * FROM {$wpdb->prefix}tmon_unit WHERE company_id = %d", $company_id), ARRAY_A);
    ob_start();
    echo '<h2>My Company: ' . esc_html($company['name']) . '</h2>';
    echo '<p>' . esc_html($company['description']) . '</p>';
    echo '<h3>My Devices</h3>';
    echo '<table><tr><th>ID</th><th>Name</th><th>Description</th><th>Unit ID</th><th>Status</th></tr>';
    foreach ($devices as $d) {
        echo "<tr><td>{$d['id']}</td><td>{$d['name']}</td><td>{$d['description']}</td><td>{$d['unit_id']}</td><td>{$d['status']}</td></tr>";
    }
    echo '</table>';
    // Company management forms removed; only display company/device data
    return ob_get_clean();
}

function tmon_render_dashboard($dashboard_id) {
    $dashboards = get_option('tmon_user_dashboards', []);
    if (!isset($dashboards[$dashboard_id])) return;
    $db = $dashboards[$dashboard_id];
    echo '<h2>' . esc_html($db['name']) . '</h2>';
    // Company management forms removed; only display company/device data
    if (!empty($db['widgets'])) {
        foreach ($db['widgets'] as $widget) {
            tmon_render_widget($widget);
        }
    }
}

function tmon_render_widget($widget) {
    echo '<div class="tmon-widget" style="border:1px solid #ccc; margin:10px 0; padding:10px;">';
    echo '<h3>' . esc_html($widget['title']) . '</h3>';
    switch ($widget['type']) {
        case 'device_data':
            tmon_widget_device_data($widget);
            break;
        case 'command':
            tmon_widget_command($widget);
            break;
        case 'settings':
            tmon_widget_settings($widget);
            break;
    }
}
