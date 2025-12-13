<?php
// TMON Admin: Deploy/Update Unit Connector to remote sites
add_action('admin_menu', function(){
    add_submenu_page('tmon-admin', 'Deploy Unit Connector', 'Deploy UC', 'manage_options', 'tmon-admin-deploy-uc', 'tmon_admin_deploy_uc_page');
});

function tmon_admin_deploy_uc_page(){
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    echo '<div class="wrap"><h1>Deploy / Update Unit Connector</h1>';
    echo '<p class="description">Push the latest Unit Connector package to a paired site. Uses hub shared secret to sign payloads.</p>';

    $pairings = get_option('tmon_admin_uc_sites', []);
    $sites = [];
    if (is_array($pairings)) { foreach ($pairings as $url => $_) { $sites[] = $url; } }

    // Paired Unit Connectors summary (option map + table fallback)
    echo '<h2>Paired Unit Connectors</h2>';
    $rows = [];
    if (function_exists('tmon_admin_ensure_tables')) { tmon_admin_ensure_tables(); }
    global $wpdb;
    $uc_table = $wpdb->prefix . 'tmon_uc_sites';
    if ($wpdb && $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $uc_table))) {
        $rows = $wpdb->get_results("SELECT normalized_url, hub_key, read_token, COALESCE(last_seen, created_at) AS seen, created_at FROM {$uc_table} ORDER BY COALESCE(last_seen, created_at) DESC LIMIT 200", ARRAY_A);
    }
    if (!$rows && is_array($pairings)) {
        foreach ($pairings as $url => $meta) {
            $rows[] = [
                'normalized_url' => $url,
                'hub_key' => $meta['uc_key'] ?? '',
                'read_token' => $meta['read_token'] ?? '',
                'seen' => $meta['paired_at'] ?? '',
                'created_at' => $meta['paired_at'] ?? '',
            ];
        }
    }
    echo '<table class="widefat striped"><thead><tr><th>URL</th><th>Hub Key</th><th>Read Token</th><th>Paired/Last Seen</th></tr></thead><tbody>';
    if ($rows) {
        foreach ($rows as $r) {
            echo '<tr>';
            echo '<td>'.esc_html($r['normalized_url'] ?? '').'</td>';
            echo '<td><code>'.esc_html($r['hub_key'] ?? '').'</code></td>';
            echo '<td><code>'.esc_html($r['read_token'] ?? '').'</code></td>';
            echo '<td>'.esc_html($r['seen'] ?? $r['created_at'] ?? '').'</td>';
            echo '</tr>';
        }
    } else {
        echo '<tr><td colspan="4"><em>No paired Unit Connectors yet.</em></td></tr>';
    }
    echo '</tbody></table>';

    if (isset($_POST['tmon_deploy_uc'])) {
        if (!function_exists('tmon_admin_verify_nonce') || !tmon_admin_verify_nonce('tmon_admin_deploy_uc')) {
            echo '<div class="notice notice-error"><p>Security check failed. Please refresh and try again.</p></div>';
        } else {
            $site_url = esc_url_raw($_POST['site_url'] ?? '');
            $package_url = esc_url_raw($_POST['package_url'] ?? '');
            $action = sanitize_text_field($_POST['action_type'] ?? 'install');
            $sha256 = sanitize_text_field($_POST['sha256'] ?? '');
            $auth = sanitize_text_field($_POST['auth'] ?? '');
            if ($site_url && $package_url && function_exists('tmon_admin_uc_push_request')) {
                $result = tmon_admin_uc_push_request($site_url, $package_url, $action, $auth, $sha256);
                if (is_wp_error($result)) {
                    echo '<div class="notice notice-error"><p>'.esc_html($result->get_error_message()).'</p></div>';
                } else {
                    $cls = $result['success'] ? 'updated' : 'notice notice-error';
                    $msg = $result['success'] ? 'Push request sent.' : 'Push failed.';
                    echo '<div class="'.$cls.'"><p>'.$msg.' HTTP '.intval($result['code']).': '.esc_html($result['body']).'</p></div>';
                }
            } else {
                echo '<div class="notice notice-error"><p>Site URL and Package URL are required.</p></div>';
            }
        }
    }

    echo '<form method="post">';
    wp_nonce_field('tmon_admin_deploy_uc');
    echo '<table class="form-table">';
    echo '<tr><th>Target Site URL</th><td><input type="url" name="site_url" class="regular-text" list="tmon_uc_sites" placeholder="https://example.com" required>';    
    echo '<datalist id="tmon_uc_sites">';
    foreach ($sites as $s) { echo '<option value="'.esc_attr($s).'"></option>'; }
    echo '</datalist><p class="description">Must be a paired UC site.</p></td></tr>';
    echo '<tr><th>Package URL (.zip)</th><td><input type="url" name="package_url" class="regular-text" placeholder="https://hub.example.com/assets/tmon-unit-connector.zip" required><p class="description">Publicly accessible zip for UC.</p></td></tr>';
    echo '<tr><th>SHA256 (optional)</th><td><input type="text" name="sha256" class="regular-text" placeholder=""></td></tr>';
    echo '<tr><th>Action</th><td><select name="action_type"><option value="install">Install</option><option value="update">Update</option></select></td></tr>';
    echo '<tr><th>Authorization (optional)</th><td><input type="text" name="auth" class="regular-text" placeholder="Bearer ..."><p class="description">Optional header if the target site requires it.</p></td></tr>';
    echo '</table>';
    submit_button('Send');
    echo '</form>';
    echo '<h2>Recent Activity</h2>';
    global $wpdb;
    if (function_exists('tmon_admin_audit_ensure_tables')) {
        tmon_admin_audit_ensure_tables();
    }
    $audit_table = function_exists('tmon_admin_audit_table_name') ? tmon_admin_audit_table_name() : ($wpdb->prefix . 'tmon_admin_audit');
    $rows = [];
    if ($wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $audit_table))) {
        $rows = $wpdb->get_results($wpdb->prepare("SELECT ts AS created_at, action, COALESCE(context, extra) AS details FROM {$audit_table} WHERE action=%s ORDER BY ts DESC LIMIT 50", 'uc_confirm'), ARRAY_A);
    }
    echo '<table class="widefat"><thead><tr><th>Time</th><th>Details</th></tr></thead><tbody>';
    foreach ($rows as $r) echo '<tr><td>'.esc_html($r['created_at']).'</td><td><code>'.esc_html($r['details']).'</code></td></tr>';
    if (empty($rows)) echo '<tr><td colspan="2"><em>No confirmations yet.</em></td></tr>';
    echo '</tbody></table>';
    echo '</div>';
}
