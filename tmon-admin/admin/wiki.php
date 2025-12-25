<?php
// TMON Admin Wiki: admin-focused docs
add_action('admin_menu', function(){
    add_submenu_page('tmon-admin', 'Wiki', 'Wiki', 'manage_options', 'tmon-admin-wiki', function(){
        echo '<div class="wrap"><h1>TMON Admin — Wiki</h1>';
        echo '<p>This wiki covers central provisioning, authorization, hierarchy management, claims, and how it integrates with Unit Connector.</p>';
    echo '<h2>Hub–Spoke Pairing</h2><ul>';
    echo '<li>Pair Unit Connectors via <code>/wp-json/tmon-admin/v1/uc/pair</code>. Admin stores per-site <em>read_token</em> and returns <em>hub_key</em> for the spoke to use.</li>';
    echo '<li>Headers: <code>X-TMON-HUB</code> (hub shared key), <code>X-TMON-ADMIN</code> (UC admin key), <code>X-TMON-READ</code> (read token for read-only endpoints).</li>';
    echo '</ul>';
        echo '<h2>Provisioning</h2><ul>';
        echo '<li>Add devices with unit_id (and machine_id if applicable). Status must be Active.</li>';
        echo '<li>Unknown devices reported by Unit Connector appear in Provisioning queue (via ingest-unknown). Review and assign.</li>';
        echo '</ul>';
        echo '<h2>Authorization</h2><p>Filter <code>tmon_admin_authorize_device</code> enforces per-record authorization. Toggle machine_id matching in settings (if implemented).</p>';
        echo '<h2>Hierarchy</h2><p>Ensure Company → Site → Zone → Cluster → Unit are created and linked. This powers listings and permissions.</p>';
        echo '<h2>Claims</h2><p>Customer claims via <code>[tmon_claim_device]</code> hit <code>/wp-json/tmon-admin/v1/claim</code>. Approve to associate.</p>';
        echo '<h2>Notifications</h2><p>Offline device scans in Unit Connector notify Admin via <code>tmon_admin_notify</code>. See Notifications page (if present) or query via hooks.</p>';
    echo '<h2>Field Data (Admin)</h2><ul>';
    echo '<li>Admin UI aggregates logs from paired Unit Connectors using <code>GET /wp-json/tmon-admin/v1/field-data</code>, which fetches from each spoke <code>/tmon/v1/admin/field-data</code>.</li>';
    echo '<li>Field Data page includes: time window filter, and a mini REMOTE_SYNC_SCHEDULE chart.</li>';
    echo '</ul>';
    echo '<h2>REST Hooks</h2><ul>';
        echo '<li>POST /wp-json/tmon-admin/v1/ingest-unknown — receives unknown devices from Unit Connector.</li>';
    echo '<li>POST /wp-json/tmon-admin/v1/device/gps-override — pushes GPS to a spoke using <code>/tmon/v1/admin/device/settings</code> with <code>X-TMON-ADMIN</code>.</li>';
        echo '<li>Action: tmon_admin_receive_field_data (unit_id, record)</li>';
        echo '<li>Action: tmon_admin_notify (type, message, context)</li>';
        echo '</ul>';
        echo '<h2>Troubleshooting</h2><ul>';
        echo '<li>Run plugin activation to create schema.</li>';
    echo '<li>Audit device authorization failures.</li>';
    echo '<li>If Provisioned Devices table is missing on the spoke, the Unit Connector admin will fall back to the hub endpoint to render the list.</li>';
        echo '</ul>';
        echo '</div>';
    });
});
