<?php
// Unit Connector Notification Preferences
add_action('admin_menu', function(){
    add_submenu_page('tmon_devices', 'Notifications', 'Notifications', 'read', 'tmon-uc-notifications', 'tmon_uc_notifications_page');
});

function tmon_uc_notifications_page(){
    echo '<div class="wrap"><h1>Notifications</h1>';
    // Show recent notifications (read-only) to users with allowed roles
    $roles_allowed = get_option('tmon_uc_notify_roles', ['administrator']);
    $user = wp_get_current_user();
    $can_view = false;
    foreach ($user->roles as $r) { if (in_array($r, $roles_allowed, true)) { $can_view = true; break; } }
    if ($can_view) {
        $notices = get_option('tmon_admin_notifications', []);
        echo '<h2>Recent Alerts</h2>';
        echo '<table class="widefat"><thead><tr><th>Time</th><th>Type</th><th>Message</th></tr></thead><tbody>';
        $shown = 0;
        foreach (array_reverse($notices) as $n) {
            echo '<tr><td>'.esc_html($n['timestamp'] ?? '').'</td><td>'.esc_html($n['type'] ?? '').'</td><td>'.esc_html($n['message'] ?? '').'</td></tr>';
            if (++$shown >= 50) break;
        }
        if (!$shown) echo '<tr><td colspan="3"><em>No notifications.</em></td></tr>';
        echo '</tbody></table>';
    } else {
        echo '<p><em>You do not have a role configured to view notifications.</em></p>';
    }
    echo '<hr>';
    if (!current_user_can('manage_options')) {
        echo '</div>';
        return;
    }
    echo '<h1>Notification Preferences</h1>';
    if (isset($_POST['tmon_uc_save_notifications'])) {
        check_admin_referer('tmon_uc_notifications');
        $roles = array_map('sanitize_text_field', $_POST['roles'] ?? []);
        $methods = array_map('sanitize_text_field', $_POST['methods'] ?? []);
        update_option('tmon_uc_notify_roles', $roles);
        update_option('tmon_uc_notify_methods', $methods);
        echo '<div class="updated"><p>Preferences saved.</p></div>';
    }
    $roles = get_option('tmon_uc_notify_roles', ['administrator']);
    $methods = get_option('tmon_uc_notify_methods', ['email']);
    echo '<form method="post">';
    wp_nonce_field('tmon_uc_notifications');
    echo '<h3>Recipients by Role</h3>';
    echo '<label><input type="checkbox" name="roles[]" value="administrator"'.(in_array('administrator', $roles)?' checked':'').'> Administrators</label><br>';
    echo '<label><input type="checkbox" name="roles[]" value="editor"'.(in_array('editor', $roles)?' checked':'').'> Editors</label><br>';
    echo '<label><input type="checkbox" name="roles[]" value="tmon_manager"'.(in_array('tmon_manager', $roles)?' checked':'').'> TMON Manager</label><br>';
    echo '<label><input type="checkbox" name="roles[]" value="tmon_operator"'.(in_array('tmon_operator', $roles)?' checked':'').'> TMON Operator</label><br>';
    echo '<h3>Methods</h3>';
    echo '<label><input type="checkbox" name="methods[]" value="email"'.(in_array('email', $methods)?' checked':'').'> Email</label><br>';
    echo '<label><input type="checkbox" name="methods[]" value="sms"'.(in_array('sms', $methods)?' checked':'').'> SMS (requires integration)</label><br>';
    echo '<label><input type="checkbox" name="methods[]" value="push"'.(in_array('push', $methods)?' checked':'').'> Push (requires integration)</label><br>';
    submit_button('Save Preferences', 'primary', 'tmon_uc_save_notifications');
    echo '</form>';

    echo '<h3>Per-Device Overrides</h3>';
    global $wpdb;
    // Save per-device overrides
    if (isset($_POST['tmon_uc_save_device_overrides']) && current_user_can('manage_options')) {
        check_admin_referer('tmon_uc_device_overrides');
        $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
        $emails_raw = trim(sanitize_text_field($_POST['emails'] ?? ''));
        $methods = array_map('sanitize_text_field', $_POST['dev_methods'] ?? []);
        if ($unit_id) {
            $row = $wpdb->get_row($wpdb->prepare("SELECT settings FROM {$wpdb->prefix}tmon_devices WHERE unit_id = %s", $unit_id), ARRAY_A);
            $settings = [];
            if ($row && !empty($row['settings'])) {
                $decoded = json_decode($row['settings'], true);
                if (is_array($decoded)) $settings = $decoded;
            }
            $emails = array_filter(array_map('trim', preg_split('/[\s,;]+/', $emails_raw)));
            $emails = array_values(array_unique(array_filter($emails, function($e){ return is_email($e); })));
            $settings['notify_overrides'] = [
                'emails' => $emails,
                'methods' => $methods,
            ];
            $wpdb->update($wpdb->prefix.'tmon_devices', ['settings' => wp_json_encode($settings)], ['unit_id' => $unit_id]);
            echo '<div class="updated"><p>Overrides saved for unit '.esc_html($unit_id).'.</p></div>';
        } else {
            echo '<div class="error"><p>Unit ID is required to save overrides.</p></div>';
        }
    }
    echo '<p>Optionally define per-device recipients and methods. These override the defaults above and are used by offline alerts.</p>';
    echo '<form method="post">';
    wp_nonce_field('tmon_uc_device_overrides');
    echo '<table class="form-table">';
    // Known Unit IDs list from local DB and remote cache
    $known_units = [];
    $rows_known = $wpdb->get_results("SELECT unit_id, unit_name FROM {$wpdb->prefix}tmon_devices ORDER BY unit_id ASC", ARRAY_A);
    if (is_array($rows_known)) { foreach ($rows_known as $r) { if (!empty($r['unit_id'])) $known_units[$r['unit_id']] = $r['unit_name'] ?: $r['unit_id']; } }
    $remote_known = get_option('tmon_admin_known_ids_cache', []);
    if (is_array($remote_known)) { foreach ($remote_known as $uid => $d) { if (!isset($known_units[$uid])) $known_units[$uid] = isset($d['unit_name']) ? $d['unit_name'] : $uid; } }
    echo '<tr><th>Unit ID</th><td>';
    echo '<input type="text" name="unit_id" class="regular-text" list="tmon_known_unit_ids" placeholder="170170" required>';
    echo '<datalist id="tmon_known_unit_ids">';
    foreach ($known_units as $uid => $uname) { echo '<option value="'.esc_attr($uid).'">'.esc_html($uname).'</option>'; }
    echo '</datalist>';
    echo '</td></tr>';
    echo '<tr><th>Emails</th><td><input type="text" name="emails" class="regular-text" placeholder="ops@example.com, lead@example.com"><p class="description">Comma/space/semicolon separated list.</p></td></tr>';
    echo '<tr><th>Methods</th><td>';
    echo '<label><input type="checkbox" name="dev_methods[]" value="email" checked> Email</label> ';
    echo '<label><input type="checkbox" name="dev_methods[]" value="sms"> SMS</label> ';
    echo '<label><input type="checkbox" name="dev_methods[]" value="push"> Push</label> ';
    echo '</td></tr>';
    echo '</table>';
    submit_button('Save Device Overrides', 'secondary', 'tmon_uc_save_device_overrides');
    echo '</form>';
    echo '</div>';
}
