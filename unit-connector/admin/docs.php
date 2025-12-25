<?php
/*
 * TMON Unit Connector Documentation Page
 * Provides usage, API, and troubleshooting info for admins and users.
 */
add_action('admin_menu', function() {
    add_submenu_page('tmon_devices', 'Documentation', 'Documentation', 'read', 'tmon-docs', function() {
        echo '<div class="wrap"><h1>TMON Unit Connector Documentation</h1>';
        echo '<h2>Overview</h2><p>The Unit Connector receives device data, normalizes remote nodes, stores records, and forwards to TMON Admin for authorization and provisioning checks.</p>';
        echo '<h2>Quick Start</h2><ol>' .
            '<li>Configure hierarchy (Company/Site/Zone/Cluster/Unit) under the Hierarchy menu.</li>' .
            '<li>Provision devices in TMON Admin (or mirror view in Provisioned Devices).</li>' .
            '<li>Install shortcodes on public pages to list devices and show data.</li>' .
            '<li>Monitor status, use OTA, review audit logs.</li>' .
        '</ol>';
        echo '<h2>Shortcodes</h2><ul>' .
            '<li><code>[tmon_active_units]</code> — List active devices with last seen.</li>' .
            '<li><code>[tmon_device_sdata unit_id="..."]</code> — Friendly latest sdata table.</li>' .
            '<li><code>[tmon_device_history unit_id="..." hours="24"]</code> — 24h Chart.js history.</li>' .
            '<li><code>[tmon_device_list]</code>, <code>[tmon_device_status]</code> — Hierarchical list/status.</li>' .
            '<li><code>[tmon_claim_device]</code> — Logged-in users submit device claims (Unit ID + Machine ID).</li>' .
        '</ul>';
        echo '<h3>Examples</h3><ul>' .
            '<li>Overview: <code>[tmon_active_units]</code>, <code>[tmon_device_list]</code>, <code>[tmon_device_status]</code></li>' .
            '<li>Device: <code>[tmon_device_sdata unit_id="UNIT123"]</code>, <code>[tmon_device_history unit_id="UNIT123" hours="24"]</code></li>' .
            '<li>Claim: <code>[tmon_claim_device]</code> (requires login)</li>' .
        '</ul>';
        echo '<h2>REST Endpoints (tmon/v1)</h2><ul>' .
            '<li><code>POST /device/field-data</code> — Normalizes base/remote records; forwards to TMON Admin.</li>' .
            '<li><code>POST /device/data-history</code> — Upload history CSV (multipart).</li>' .
            '<li><code>POST /device/ping</code></li>' .
            '<li><code>GET /device/ota-jobs/{unit_id}</code></li>' .
            '<li><code>POST /device/ota-job-complete</code></li>' .
        '</ul>';
    echo '<h2>Authorization & Provisioning</h2><p>Per-record authorization is enforced by TMON Admin via the <code>tmon_admin_authorize_device</code> filter. Devices must be provisioned and active (not suspended). Optional machine_id match can be required.</p>';
        echo '<h2>Claim Device Flow</h2><ol>' .
            '<li>User submits claim via <code>[tmon_claim_device]</code> (requires login).</li>' .
            '<li>Claim hits <code>/wp-json/tmon-admin/v1/claim</code>.</li>' .
            '<li>Admins approve/deny in TMON Admin &gt; Claims.</li>' .
        '</ol>';
        echo '<h2>Troubleshooting</h2><ul>' .
            '<li>Ensure all required tables created on activation (Unit Connector and TMON Admin).</li>' .
            '<li>Check audit logs for rejected records (authorization failures, malformed payloads).</li>' .
            '<li>Verify device clock and network connectivity.</li>' .
            '<li>Confirm permalinks enabled for REST routes.</li>' .
        '</ul>';
    $img_base = plugins_url('assets/images/', dirname(__DIR__) . '/tmon-unit-connector.php');
    echo '<h2>Screenshots</h2>';
    echo '<p>Use the Starter Page (under this menu) to quickly create a public page with all core shortcodes. Below are illustrative screenshots:</p>';
    echo '<div style="display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start">';
    echo '<figure style="margin:0"><img alt="Hierarchy" src="' . esc_url($img_base . 'hierarchy.svg') . '" style="max-width:320px;border:1px solid #ddd;border-radius:6px"><figcaption style="text-align:center">Hierarchy Overview</figcaption></figure>';
    echo '<figure style="margin:0"><img alt="Shortcodes" src="' . esc_url($img_base . 'shortcodes.svg') . '" style="max-width:320px;border:1px solid #ddd;border-radius:6px"><figcaption style="text-align:center">Shortcodes</figcaption></figure>';
    echo '<figure style="margin:0"><img alt="Claim Form" src="' . esc_url($img_base . 'claim.svg') . '" style="max-width:320px;border:1px solid #ddd;border-radius:6px"><figcaption style="text-align:center">Claim Device Form</figcaption></figure>';
    echo '</div>';
        echo '</div>';
    });
    add_submenu_page('tmon_devices', 'Offline Devices', 'Offline Devices', 'manage_options', 'tmon-offline', function(){
        echo '<div class="wrap"><h1>Offline Devices</h1>';
        if (isset($_POST['tmon_uc_offline_threshold_minutes'])) {
            check_admin_referer('tmon_uc_offline');
            update_option('tmon_uc_offline_threshold_minutes', max(5, intval($_POST['tmon_uc_offline_threshold_minutes'])));
            echo '<div class="updated"><p>Threshold updated.</p></div>';
        }
        $minutes = intval(get_option('tmon_uc_offline_threshold_minutes', 30));
        echo '<form method="post">';
        wp_nonce_field('tmon_uc_offline');
        echo '<p>Consider devices offline if last_seen older than <input type="number" name="tmon_uc_offline_threshold_minutes" value="'.intval($minutes).'" min="5" step="5"> minutes.';
        submit_button('Save Threshold');
        echo '</form>';
        // List offline
        global $wpdb;
        $threshold = gmdate('Y-m-d H:i:s', time() - $minutes * 60);
        $rows = $wpdb->get_results($wpdb->prepare("SELECT unit_id, unit_name, last_seen FROM {$wpdb->prefix}tmon_devices WHERE (last_seen IS NULL OR last_seen < %s) AND suspended = 0 ORDER BY last_seen ASC", $threshold), ARRAY_A);
        echo '<h2>Currently Offline</h2>';
        echo '<table class="widefat"><thead><tr><th>Unit ID</th><th>Name</th><th>Last Seen</th></tr></thead><tbody>';
        foreach ($rows as $r) {
            echo '<tr><td>'.esc_html($r['unit_id']).'</td><td>'.esc_html($r['unit_name']).'</td><td>'.esc_html($r['last_seen']).'</td></tr>';
        }
        if (empty($rows)) echo '<tr><td colspan="3"><em>All devices are online within threshold.</em></td></tr>';
        echo '</tbody></table>';
        echo '</div>';
    });
});
