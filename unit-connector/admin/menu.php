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

    // Try local cache first; if empty, backfill from Admin hub
    $table = $wpdb->prefix . 'tmon_uc_devices';
    uc_devices_ensure_table();
    $rows = $wpdb->get_results("SELECT unit_id,machine_id,unit_name,role,assigned,updated_at FROM {$table} ORDER BY updated_at DESC LIMIT 500", ARRAY_A);
    if (!$rows || empty($rows)) {
        $count = function_exists('tmon_uc_backfill_provisioned_from_admin') ? tmon_uc_backfill_provisioned_from_admin() : 0;
        $rows = $wpdb->get_results("SELECT unit_id,machine_id,unit_name,role,assigned,updated_at FROM {$table} ORDER BY updated_at DESC LIMIT 500", ARRAY_A);
        if (!$rows || empty($rows)) {
            echo '<div class="card" style="padding:12px;"><p><em>No provisioned devices found. Pair UC with Admin and refresh.</em></p></div></div>';
            return;
        }
    }

    echo '<table class="widefat"><thead><tr><th>Unit ID</th><th>Machine ID</th><th>Name</th><th>Role</th><th>Assigned</th><th>Updated</th><th>Actions</th></tr></thead><tbody>';
    foreach ($rows as $r) {
        echo '<tr>';
        echo '<td>'.esc_html($r['unit_id']).'</td>';
        echo '<td>'.esc_html($r['machine_id']).'</td>';
        echo '<td>'.esc_html($r['unit_name']).'</td>';
        echo '<td>'.esc_html($r['role']).'</td>';
        echo '<td>'.(intval($r['assigned']) ? 'Yes' : 'No').'</td>';
        echo '<td>'.esc_html($r['updated_at']).'</td>';
        echo '<td>';
        echo '<form method="post" action="'.esc_url(admin_url('admin-post.php')).'" onsubmit="return confirm(\'Submit claim for this device?\');" style="display:inline-block">';
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

// Admin-post: forward a claim to hub via proxy endpoint (already present)
// Add action to notify Admin of approval for canBill updates when hub confirms
add_action('admin_post_tmon_uc_submit_claim', function(){
    // ...existing code...
    // After success, emit a hook that Admin listens to for canBill updates
    do_action('tmon_admin_claim_approved', $unit_id, $machine_id);
    // ...existing code...
});
