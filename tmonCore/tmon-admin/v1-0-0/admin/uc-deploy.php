<?php
// TMON Admin: Deploy/Update Unit Connector to remote sites
add_action('admin_menu', function(){
    add_submenu_page('tmon-admin', 'Deploy Unit Connector', 'Deploy UC', 'manage_options', 'tmon-admin-deploy-uc', 'tmon_admin_deploy_uc_page');
});

function tmon_admin_deploy_uc_page(){
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    echo '<div class="wrap"><h1>Deploy / Update Unit Connector</h1>';
    if (isset($_POST['tmon_deploy_uc'])) {
        if (!function_exists('tmon_admin_verify_nonce') || !tmon_admin_verify_nonce('tmon_admin_deploy_uc')) {
            echo '<div class="notice notice-error"><p>Security check failed. Please refresh and try again.</p></div>';
        } else {
        $site_url = esc_url_raw($_POST['site_url'] ?? '');
        $package_url = esc_url_raw($_POST['package_url'] ?? '');
        $action = sanitize_text_field($_POST['action_type'] ?? 'install');
        if ($site_url && $package_url) {
            $endpoint = rest_url('tmon-admin/v1/uc/push');
            $resp = wp_remote_post($endpoint, [
                'timeout' => 20,
                'headers' => ['Content-Type'=>'application/json'],
                'body' => wp_json_encode(['site_url'=>$site_url,'package_url'=>$package_url,'action'=>$action]),
            ]);
            if (!is_wp_error($resp) && wp_remote_retrieve_response_code($resp) == 200) {
                echo '<div class="updated"><p>Push request sent. Response: '.esc_html(wp_remote_retrieve_body($resp)).'</p></div>';
            } else {
                echo '<div class="error"><p>Push failed: '.esc_html(is_wp_error($resp)?$resp->get_error_message():wp_remote_retrieve_body($resp)).'</p></div>';
            }
        } else {
            echo '<div class="error"><p>Site URL and Package URL are required.</p></div>';
        }
        }
    }
    echo '<form method="post">';
    wp_nonce_field('tmon_admin_deploy_uc');
    echo '<table class="form-table">';
    echo '<tr><th>Target Site URL</th><td><input type="url" name="site_url" class="regular-text" placeholder="https://example.com" required></td></tr>';
    echo '<tr><th>Package URL (.zip)</th><td><input type="url" name="package_url" class="regular-text" placeholder="https://hub.example.com/assets/tmon-unit-connector.zip" required></td></tr>';
    echo '<tr><th>Action</th><td><select name="action_type"><option value="install">Install</option><option value="update">Update</option></select></td></tr>';
    echo '</table>';
    submit_button('Send');
    echo '</form>';
    echo '<h2>Recent Activity</h2>';
    global $wpdb;
    $rows = $wpdb->get_results("SELECT created_at, action, details FROM {$wpdb->prefix}tmon_audit WHERE action='uc_confirm' ORDER BY created_at DESC LIMIT 50", ARRAY_A);
    echo '<table class="widefat"><thead><tr><th>Time</th><th>Details</th></tr></thead><tbody>';
    foreach ($rows as $r) echo '<tr><td>'.esc_html($r['created_at']).'</td><td><code>'.esc_html($r['details']).'</code></td></tr>';
    if (empty($rows)) echo '<tr><td colspan="2"><em>No confirmations yet.</em></td></tr>';
    echo '</tbody></table>';
    echo '</div>';
}
