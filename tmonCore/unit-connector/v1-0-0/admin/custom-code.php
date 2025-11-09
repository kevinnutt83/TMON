<?php
// Register custom post type for custom code
add_action('init', function() {
    register_post_type('tmon_custom_code', [
        'label' => 'TMON Custom Code',
        'public' => false,
        'show_ui' => true,
        'supports' => ['title', 'editor', 'custom-fields'],
        'menu_icon' => 'dashicons-editor-code',
        // Show under TMON Devices top-level menu
        'show_in_menu' => 'tmon_devices',
    ]);
});
// Custom Code Management for TMON Admin and Unit Connector
// Allows users to define, send, and manage custom code snippets for TMON devices

add_action('admin_menu', function() {
    // Removed: Custom Code menu is centralized in TMON Admin to avoid redundancy
});

function tmon_custom_code_page() {
    echo '<div class="wrap"><h1>TMON Custom Code</h1>';
    echo '<p><a class="button" href="post-new.php?post_type=tmon_custom_code">Add New Custom Code</a></p>';
    // List custom code posts
    $args = [
        'post_type' => 'tmon_custom_code',
        'posts_per_page' => 20,
        'post_status' => 'publish',
    ];
    $posts = get_posts($args);
    if ($posts) {
        echo '<table class="widefat"><thead><tr><th>Title</th><th>Devices</th><th>Schedule</th><th>Action</th></tr></thead><tbody>';
        foreach ($posts as $post) {
            $devices = get_post_meta($post->ID, 'tmon_devices', true) ?: 'All';
            $schedule = get_post_meta($post->ID, 'tmon_schedule', true) ?: 'On Demand';
            echo '<tr>';
            echo '<td>' . esc_html($post->post_title) . '</td>';
            echo '<td>' . esc_html(is_array($devices) ? implode(", ", $devices) : $devices) . '</td>';
            echo '<td>' . esc_html($schedule) . '</td>';
            echo '<td><form method="post"><input type="hidden" name="tmon_run_code_id" value="' . esc_attr($post->ID) . '"><button class="button">Send to Devices</button></form></td>';
            echo '</tr>';
        }
        echo '</tbody></table>';
    } else {
        echo '<p>No custom code found.</p>';
    }
    // Handle send to devices
    if (isset($_POST['tmon_run_code_id'])) {
        $post_id = intval($_POST['tmon_run_code_id']);
        $code = get_post_field('post_content', $post_id);
        $devices = get_post_meta($post_id, 'tmon_devices', true);
        tmon_uc_queue_custom_code_for_devices($code, $devices);
        echo '<div class="updated"><p>Custom code sent to devices.</p></div>';
    }
    echo '</div>';
}
function tmon_uc_queue_custom_code_for_devices($code, $devices = null) {
    global $wpdb;
    if (!$devices || $devices === 'All') {
        $devices = $wpdb->get_results("SELECT unit_id FROM {$wpdb->prefix}tmon_devices", ARRAY_A);
        $devices = array_column($devices, 'unit_id');
    }
    foreach ((array)$devices as $dev_id) {
        $wpdb->insert($wpdb->prefix.'tmon_device_commands', [
            'device_id' => $dev_id,
            'command' => 'custom_code',
            'params' => maybe_serialize(['code' => $code]),
            'created_at' => current_time('mysql'),
        ]);
    }
}
