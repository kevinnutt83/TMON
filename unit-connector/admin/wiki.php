<?php
// Unit Connector Wiki: user-focused docs
add_action('admin_menu', function(){
    add_submenu_page('tmon_devices', 'Wiki', 'Wiki', 'read', 'tmon-uc-wiki', function(){
        echo '<div class="wrap"><h1>TMON Unit Connector — Wiki</h1>';
        echo '<p>This wiki covers Unit Connector usage for site operators.</p>';
        echo '<h2>Overview</h2><ul>';
        echo '<li>Receives and normalizes device data (base, remotes, WiFi nodes).</li>';
        echo '<li>Stores per-unit records and forwards unauthorized devices to TMON Admin for provisioning.</li>';
        echo '<li>Provides device commands (toggle_relay, settings_update, set_oled_message/banner, clear_oled), OTA, and file transfer.</li>';
        echo '</ul>';
    echo '<h2>Shortcodes</h2><ul>';
        echo '<li><code>[tmon_active_units]</code> — List active devices with last seen.</li>';
        echo '<li><code>[tmon_device_sdata unit_id="170170"]</code> — Latest sensor data table.</li>';
    echo '<li><code>[tmon_device_history unit_id="170170" hours="24"]</code> — History chart.</li>';
    echo '<li><code>[tmon_device_status]</code> — Status table. If relays are enabled for a unit (via firmware settings ENABLE_RELAY1..8), authorized users see inline relay controls with runtime and scheduling.</li>';
        echo '<li><code>[tmon_pending_commands unit="170170"]</code> — Pending command count.</li>';
        echo '</ul>';
        echo '<h2>Device Commands</h2><p>Use Admin → TMON Devices → Device Commands. Supported:</p><ul>';
        echo '<li><b>toggle_relay</b> {relay_num:"1", state:"on", runtime:"5"}</li>';
        echo '<li><b>settings_update</b> {FIELD_DATA_SEND_INTERVAL: 60}</li>';
        echo '<li><b>set_oled_message</b> {message:"Hello", duration:5}</li>';
        echo '<li><b>set_oled_banner</b> {message:"Status: OK", duration:5, persist:true}</li>';
        echo '<li><b>clear_oled</b> {}</li>';
        echo '</ul>';
    echo '<h2>REST Endpoints (devices)</h2><p>All device endpoints require JWT (HS256) with leeway. Key routes:</p><ul>';
        echo '<li>POST /wp-json/tmon/v1/device/ping</li>';
        echo '<li>GET /wp-json/tmon/v1/device/ota-jobs/{unit_id}; POST /device/ota-job-complete</li>';
        echo '<li>GET /wp-json/tmon/v1/device/commands/{unit_id}; POST /device/command-complete</li>';
        echo '</ul>';
    echo '<h2>Admin/Hub Endpoints</h2><ul>';
    echo '<li>GET /wp-json/tmon/v1/admin/field-data.csv — Normalized CSV export (supports unit_id/hours/since/until/gzip). Auth: X-TMON-ADMIN, X-TMON-HUB, or X-TMON-READ.</li>';
    echo '<li>GET /wp-json/tmon/v1/admin/field-data — JSON rows for Admin aggregation (hours, limit, unit_id). Same auth as above.</li>';
    echo '<li>POST /wp-json/tmon/v1/admin/device/settings — Push settings (e.g., GPS overrides) from TMON Admin to UC using X-TMON-ADMIN.</li>';
    echo '</ul>';
    echo '<p>Headers used: <code>X-TMON-ADMIN</code> (UC admin key), <code>X-TMON-HUB</code> (hub shared key), <code>X-TMON-READ</code> (read-only token).</p>';
        echo '<h2>Offline Devices</h2><p>See Admin → TMON Devices → Offline Devices to adjust the threshold and view current offline list. System scans hourly and notifies admins.</p>';
        echo '<h2>Troubleshooting</h2><ul>';
        echo '<li>Check WordPress JWT secret and device time drift.</li>';
        echo '<li>Verify permalinks and REST availability.</li>';
        echo '<li>Use field logs under wp-content/tmon-field-logs for intake debugging.</li>';
        echo '</ul>';
        echo '</div>';
    });
});

// Minimal Wiki / Help page linking to command reference
add_action('admin_menu', function() {
    add_submenu_page('tmon_devices', 'UC Wiki', 'UC Wiki', 'read', 'tmon-uc-wiki', function(){
        if (!current_user_can('read')) { wp_die('Insufficient permissions'); }
        echo '<div class="wrap"><h1>Unit Connector — Quick Reference</h1>';
        echo '<p>Documentation and command reference for device integrators:</p>';
        // Link to our repository file (raw GitHub)
        echo '<ul>';
        echo '<li><a href="https://github.com/kevinnutt83/TMON/blob/main/COMMANDS.md" target="_blank">Device Commands & Staged Settings (COMMANDS.md)</a></li>';
        echo '<li><a href="' . esc_url( plugins_url('README-field-logs.md', __DIR__ ) ) . '" target="_blank">Field Logs: filenames & formats</a></li>';
        echo '</ul>';
        echo '<p>Use the staging pages under <strong>TMON → Devices</strong> to stage settings and view pending commands.</p>';
        echo '</div>';
    });
});
