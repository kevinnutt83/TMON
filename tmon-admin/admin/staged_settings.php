<?php
// Admin page: Staged Settings -> apply now / clear staged
add_action('admin_menu', function(){
    add_submenu_page('tmon-admin', 'Staged Settings', 'Staged Settings', 'manage_options', 'tmon-admin-staged-settings', 'tmon_admin_staged_settings_page');
});

function tmon_admin_staged_settings_page(){
    if (!current_user_can('manage_options')) wp_die('Forbidden');

    $msg = '';
    if (isset($_POST['tmon_staged_action'])) {
        if (!function_exists('tmon_admin_verify_nonce') || !tmon_admin_verify_nonce('tmon_admin_staged')) {
            echo '<div class="notice notice-error"><p>Security check failed. Please refresh and try again.</p></div>';
        } else {
            $site = esc_url_raw($_POST['site_url'] ?? '');
            $unit = sanitize_text_field($_POST['unit_id'] ?? '');
            $action = sanitize_text_field($_POST['tmon_staged_action'] ?? '');
            $payload = ['unit_id' => $unit];
            $endpoint = '';
            if ($action === 'apply') $endpoint = rtrim($site, '/') . '/wp-json/tmon/v1/admin/device/apply-staged';
            if ($action === 'clear') $endpoint = rtrim($site, '/') . '/wp-json/tmon/v1/admin/device/clear-staged';
            if ($endpoint && $site && $unit) {
                $resp = wp_remote_post($endpoint, [
                    'headers' => ['Content-Type' => 'application/json'],
                    'body' => wp_json_encode($payload),
                    'timeout' => 10,
                ]);
                $code = wp_remote_retrieve_response_code($resp);
                $body = wp_remote_retrieve_body($resp);
                $ok = in_array(intval($code), [200,201], true);
                $cls = $ok ? 'updated' : 'notice notice-error';
                echo '<div class="'.$cls.'"><p>'.esc_html($ok ? 'Action sent.' : 'Action failed.').' HTTP '.intval($code).': '.esc_html(substr($body,0,200)).'</p></div>';
                // audit into option for traceability
                $audit = get_option('tmon_admin_staged_audit', []);
                if (!is_array($audit)) $audit = [];
                $audit[] = [
                    'ts' => time(),
                    'site' => $site,
                    'unit' => $unit,
                    'action' => $action,
                    'result_code' => intval($code),
                    'result_snip' => substr($body, 0, 200),
                    'user' => wp_get_current_user()->user_login,
                ];
                update_option('tmon_admin_staged_audit', array_slice($audit, -200)); // keep last 200
            } else {
                echo '<div class="notice notice-error"><p>Site URL and Unit ID required.</p></div>';
            }
        }
    }

    echo '<div class="wrap"><h1>Staged Settings</h1>';
    echo '<p>Trigger immediate apply or clear of staged settings on a target Unit Connector site (best-effort).</p>';
    echo '<form method="post">';
    wp_nonce_field('tmon_admin_staged');
    echo '<table class="form-table">';
    echo '<tr><th>Target Site URL</th><td><input type="url" name="site_url" class="regular-text" placeholder="https://uc.example.com" required></td></tr>';
    echo '<tr><th>Unit ID</th><td><input type="text" name="unit_id" class="regular-text" placeholder="UNIT123" required></td></tr>';
    echo '</table>';
    echo '<p>';
    echo '<button class="button button-primary" name="tmon_staged_action" value="apply">Apply Now</button> ';
    echo '<button class="button" name="tmon_staged_action" value="clear">Clear Staged</button>';
    echo '</p>';
    echo '</form>';

    // show recent audit
    $audit = get_option('tmon_admin_staged_audit', []);
    echo '<h2>Recent staged actions</h2>';
    echo '<table class="widefat"><thead><tr><th>Time</th><th>Site</th><th>Unit</th><th>Action</th><th>Result</th><th>User</th></tr></thead><tbody>';
    if (is_array($audit) && $audit) {
        foreach (array_reverse($audit) as $a) {
            $t = date('Y-m-d H:i:s', intval($a['ts'] ?? time()));
            echo '<tr><td>'.esc_html($t).'</td><td>'.esc_html($a['site'] ?? '').'</td><td>'.esc_html($a['unit'] ?? '').'</td><td>'.esc_html($a['action'] ?? '').'</td><td>'.esc_html(intval($a['result_code'] ?? 0)).' '.esc_html($a['result_snip'] ?? '').'</td><td>'.esc_html($a['user'] ?? '').'</td></tr>';
        }
    } else {
        echo '<tr><td colspan="6"><em>No staged actions recorded yet.</em></td></tr>';
    }
    echo '</tbody></table>';
    echo '</div>';
}
?>
