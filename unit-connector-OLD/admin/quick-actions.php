<?php
// Quick Actions widget for TMON admin dashboard
add_action('wp_dashboard_setup', function() {
    wp_add_dashboard_widget('tmon_quick_actions', 'TMON Quick Actions', function() {
        echo '<ul>';
        echo '<li><a href="admin.php?page=tmon-hierarchy">Manage Hierarchy</a></li>';
        echo '<li><a href="admin.php?page=tmon-ota">Send OTA Update</a></li>';
        echo '<li><a href="admin.php?page=tmon-logs">View Logs</a></li>';
        echo '</ul>';
    });
});
