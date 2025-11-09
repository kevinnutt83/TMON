<?php
// Add TMON Companies and Devices admin menu

// Add TMON Devices admin menu (company management removed)
add_action('admin_menu', function() {
    add_menu_page('TMON Devices', 'TMON Devices', 'manage_options', 'tmon_devices', 'tmon_admin_devices_page');
    add_submenu_page('tmon_devices', 'Provisioned Devices', 'Provisioned Devices', 'manage_options', 'tmon_uc_provisioned', 'tmon_uc_provisioned_page');
    add_submenu_page('tmon_devices', 'Settings', 'Settings', 'manage_options', 'tmon-settings', function(){
        include __DIR__ . '/../templates/settings.php';
    });
});

function tmon_admin_devices_page() {
    global $wpdb;
    $devices = $wpdb->get_results("SELECT * FROM {$wpdb->prefix}tmon_unit", ARRAY_A);
    echo '<h2>TMON Devices</h2>';
    echo '<table class="widefat"><thead><tr><th>ID</th><th>Name</th><th>Description</th><th>Unit ID</th><th>Company</th></tr></thead><tbody>';
    foreach ($devices as $d) {
        $company = $wpdb->get_var($wpdb->prepare("SELECT name FROM {$wpdb->prefix}tmon_company WHERE id = %d", $d['company_id']));
        echo '<tr>';
        echo '<td>' . esc_html($d['id']) . '</td>';
        echo '<td>' . esc_html($d['name']) . '</td>';
        echo '<td>' . esc_html($d['description']) . '</td>';
        echo '<td>' . esc_html($d['unit_id']) . '</td>';
        echo '<td>' . esc_html($company) . '</td>';
        echo '</tr>';
    }
    echo '</tbody></table>';
}

function tmon_uc_provisioned_page() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    global $wpdb;
    echo '<div class="wrap"><h2>Provisioned Devices (Admin)</h2>';
    // Notice after claim submission
    if (isset($_GET['tmon_claim']) && $_GET['tmon_claim'] === 'submitted') {
        $cid = isset($_GET['claim_id']) ? intval($_GET['claim_id']) : 0;
        $msg = $cid ? 'Claim submitted. ID: ' . $cid : 'Claim submitted.';
        echo '<div class="notice notice-success is-dismissible"><p>' . esc_html($msg) . '</p></div>';
    }
    $table = $wpdb->prefix . 'tmon_provisioned_devices';
    $exists = $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table));
    $rows = [];
    if ($exists) {
        $rows = $wpdb->get_results("SELECT * FROM $table ORDER BY created_at DESC", ARRAY_A);
    } else {
        // Fall back to Hub: fetch provisioned devices list using hub shared key
        $hub = trim(get_option('tmon_uc_hub_url', ''));
        $hub_key = get_option('tmon_uc_hub_shared_key', '');
        if ($hub && $hub_key) {
            $endpoint = rtrim($hub, '/') . '/wp-json/tmon-admin/v1/provisioned-devices';
            $resp = wp_remote_get($endpoint, [
                'timeout' => 15,
                'headers' => ['X-TMON-HUB' => $hub_key]
            ]);
            if (!is_wp_error($resp) && wp_remote_retrieve_response_code($resp) === 200) {
                $data = json_decode(wp_remote_retrieve_body($resp), true);
                if (is_array($data) && isset($data['devices']) && is_array($data['devices'])) {
                    $rows = $data['devices'];
                }
            }
        }
        if (empty($rows)) {
            echo '<p><em>Provisioning table not found locally, and Hub fetch returned no results. Ensure TMON Admin is reachable and paired.</em></p></div>';
            return;
        }
    }
    echo '<table class="widefat"><thead><tr><th>Unit ID</th><th>Machine ID</th><th>Company ID</th><th>Plan</th><th>Status</th><th>Notes</th><th>Created</th><th>Updated</th></tr></thead><tbody>';
    foreach ($rows as $r) {
        echo '<tr>';
        echo '<td>'.esc_html($r['unit_id']).'</td>';
        echo '<td>'.esc_html($r['machine_id']).'</td>';
        echo '<td>'.esc_html($r['company_id']).'</td>';
        echo '<td>'.esc_html($r['plan']).'</td>';
        echo '<td>'.esc_html($r['status']).'</td>';
        echo '<td>'.esc_html($r['notes']).'</td>';
        echo '<td>'.esc_html($r['created_at']).'</td>';
    echo '<td>'.esc_html($r['updated_at']).'</td>';
    // Claim via local admin-post proxy; avoids cross-site auth issues
    echo '<td>';
    echo '<form method="post" action="'.esc_url(admin_url('admin-post.php')).'" onsubmit="return confirm(\'Submit claim for this device?\');">';
    echo '<input type="hidden" name="action" value="tmon_uc_submit_claim" />';
    echo '<input type="hidden" name="unit_id" value="'.esc_attr($r['unit_id']).'" />';
    echo '<input type="hidden" name="machine_id" value="'.esc_attr($r['machine_id']).'" />';
    echo '<button type="submit" class="button">Claim</button>';
    echo '</form>';
    echo '</td>';
    echo '</tr>';
    }
    echo '</tbody></table></div>';
}
