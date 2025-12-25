<?php
// Admin UI for managing Company > Site > Zone > Cluster > Unit
// This is a stub for a drag-and-drop and map-based interface
add_action('admin_menu', function() {
    add_submenu_page('tmon_devices', 'TMON Hierarchy', 'Hierarchy', 'manage_options', 'tmon-hierarchy', 'tmon_hierarchy_page');
});

function tmon_hierarchy_page() {
    // Only allow access to TMON menu for users with manage_tmon or edit_tmon_hierarchy
    if (!current_user_can('manage_tmon') && !current_user_can('edit_tmon_hierarchy')) return;

    echo '<div class="wrap"><h1>TMON Hierarchy Management</h1>';
    echo '<div id="tmon-hierarchy-app"></div>';
    echo '<p>Manage your Company, Sites, Zones, Clusters, and Units. Drag and drop to organize, click to edit, and use the map to set locations and demarcate clusters/units.</p>';
    echo '<div id="tmon-map-container" style="height:500px;"></div>';
    echo '</div>';
    echo '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>';
    echo '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />';
    echo '<script src="' . plugin_dir_url(__FILE__) . '../assets/tmon-hierarchy.js"></script>';
    echo '<link rel="stylesheet" href="' . plugin_dir_url(__FILE__) . '../assets/tmon-hierarchy.css" />';
}
