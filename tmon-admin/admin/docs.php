<?php
/*
 * TMON Admin Documentation Page
 * Provides usage, API, and troubleshooting info for admins and users.
 */
add_action('admin_menu', function() {
    add_submenu_page('tmon-admin', 'Documentation', 'Documentation', 'read', 'tmon-admin-docs', function() {
        echo '<div class="wrap"><h1>TMON Admin Documentation</h1>';
        echo '<h2>Overview</h2><p>TMON Admin is the central authority for provisioning, authorization, hierarchy, and claims. It receives normalized data from Unit Connector and enforces device access.</p>';
        echo '<h2>Provisioning</h2><ol>' .
            '<li>Go to Provisioning to add devices (unit_id, optional machine_id, company/site associations).</li>' .
            '<li>Status must be Active for devices to be authorized.</li>' .
            '<li>Suspended devices are blocked from data ingestion.</li>' .
        '</ol>';
        echo '<h2>Hierarchy</h2><p>Ensure Company, Site, Zone, Cluster, and Unit tables are populated to organize devices for UI and permissions.</p>';
        echo '<h2>Claims</h2><ol>' .
            '<li>Customers submit claims via <code>[tmon_claim_device]</code> which calls <code>/wp-json/tmon-admin/v1/claim</code>.</li>' .
            '<li>Review pending claims in Admin &gt; Claims. Approve to associate or deny with reason.</li>' .
        '</ol>';
        echo '<h2>Authorization</h2><p>The <code>tmon_admin_authorize_device</code> filter validates that incoming data is for a provisioned, active device (and machine_id matches if configured).</p>';
        echo '<h2>Endpoints & Hooks</h2><ul>' .
            '<li><code>POST /wp-json/tmon-admin/v1/claim</code> — Submit a device claim (auth required).</li>' .
            '<li><code>tmon_admin_receive_field_data</code> — Action hook to receive normalized records.</li>' .
            '<li><code>tmon_admin_authorize_device</code> — Filter to accept/reject incoming device data.</li>' .
        '</ul>';
        echo '<h2>Troubleshooting</h2><ul>' .
            '<li>Run plugin activation to create required tables (includes hierarchy and claim requests).</li>' .
            '<li>Use Audit to trace authorization denials or malformed records.</li>' .
        '</ul>';
        echo '</div>';
    });
});
