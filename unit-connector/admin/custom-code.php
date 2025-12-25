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
if (!function_exists('tmon_uc_custom_code_page')) {
	function tmon_uc_custom_code_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');

		// Page header and instructions
		echo '<div class="wrap"><h1>TMON UC Custom Code</h1>';
		echo '<div class="card" style="padding:12px;">';
		echo '<h2 style="margin-top:0;">Instructions</h2>';
		echo '<ul style="list-style:disc;margin-left:18px;">';
		echo '<li><strong>Custom Variables</strong>: use Commands → Set Variable to push a key/value. Devices persist supported keys to their settings files.</li>';
		echo '<li><strong>Custom Functions</strong>: use Commands → Run Function with the function name from device firmware (tmon.py) and optional JSON args.</li>';
		echo '<li><strong>Firmware Updates</strong>: use Commands → Firmware Update with a version tag; devices will run OTA check and apply.</li>';
		echo '<li><strong>Custom Code Snippets</strong>: create posts under “TMON Custom Code” (below) and send to selected devices using the action button.</li>';
		echo '</ul>';
		echo '<p>Ensure your Unit Connector is paired with TMON Admin and the shared key is valid. Actions are audited by TMON Admin.</p>';
		echo '</div>';

		// New custom code button
		echo '<p><a class="button button-primary" href="post-new.php?post_type=tmon_custom_code">Add New Custom Code</a></p>';

		// List custom code posts (unchanged)
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
		// Replace raw POST handling with nonce + sanitize
		if (isset($_POST['tmon_run_code_id'])) {
			check_admin_referer('tmon_uc_run_code');
			$post_id = intval($_POST['tmon_run_code_id']);
			if ($post_id > 0) {
				$code = get_post_field('post_content', $post_id);
				$devices = get_post_meta($post_id, 'tmon_devices', true);
				tmon_uc_queue_custom_code_for_devices($code, $devices);
				echo '<div class="updated"><p>Custom code sent to devices.</p></div>';
			}
		}

		// Close wrapper
		echo '</div>';
	}
} // <-- close function_exists guard

// Enhance action form with nonce (used in tmon_uc_custom_code_page)
add_action('admin_footer', function () {
	echo '<script>(function(){var forms=document.querySelectorAll("form input[name=tmon_run_code_id]");forms.forEach(function(i){var f=i.closest("form");if(f){var n=document.createElement("input");n.type="hidden";n.name="_wpnonce";n.value="' . esc_js(wp_create_nonce('tmon_uc_run_code')) . '";f.appendChild(n);}});})();</script>';
});
