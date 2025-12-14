<?php
// Starter Page creation for quick onboarding

add_action('admin_menu', function() {
    add_submenu_page('tmon_devices', 'Starter Page', 'Starter Page', 'manage_options', 'tmon-starter', function(){
        if (!current_user_can('manage_options')) { wp_die('Insufficient permissions'); }
        $starter_id = intval(get_option('tmon_starter_page_id', 0));
        $exists = $starter_id && get_post($starter_id) && get_post_status($starter_id);
        $create_url = wp_nonce_url(admin_url('admin-post.php?action=tmon_create_starter_page'), 'tmon_create_starter_page');
        echo '<div class="wrap"><h1>TMON Starter Page</h1>';
        if ($exists) {
            $view = get_permalink($starter_id);
            echo '<p>A starter page already exists.</p>';
            echo '<p><a class="button button-primary" target="_blank" href="' . esc_url($view) . '">View Starter Page</a> ';
            echo '<a class="button" href="' . esc_url($create_url) . '">Regenerate</a></p>';
        } else {
            echo '<p>Create a starter page pre-populated with common shortcodes to speed up onboarding.</p>';
            echo '<p><a class="button button-primary" href="' . esc_url($create_url) . '">Create Starter Page</a></p>';
        }
        echo '</div>';
    });
});

add_action('admin_post_tmon_create_starter_page', function(){
    if (!current_user_can('manage_options')) { wp_die('Insufficient permissions'); }
    check_admin_referer('tmon_create_starter_page');

    $content = '';
    $content .= "\n<h2>Device Overview</h2>\n";
    $content .= "[tmon_active_units]\n\n";
    $content .= "[tmon_device_status]\n";
    $content .= "<p><em>Tip: If relays are enabled on a unit (via firmware settings), you'll see per-relay controls here. You can turn them on/off immediately or schedule with a runtime in minutes.</em></p>\n\n";
    $content .= "<h3>Known IDs</h3>\n";
    $content .= "[tmon_known_ids]\n\n";
    $content .= "\n<h2>Device Details</h2>\n";
    $content .= "[tmon_device_sdata refresh_s=\"45\"]\n\n";
    $content .= "[tmon_device_history hours=\"24\" refresh_s=\"60\"]\n";
    $content .= "<p><em>Use the dropdown to switch units. Both widgets share the same picker when you have an element with id tmon-unit-picker on the page.</em></p>\n\n";
    $content .= "\n<h2>Claim a Device</h2>\n";
    $content .= "[tmon_claim_device]\n";

    $starter_id = intval(get_option('tmon_starter_page_id', 0));
    $postarr = array(
        'post_title'   => 'TMON Starter',
        'post_content' => $content,
        'post_status'  => 'publish',
        'post_type'    => 'page',
    );

    if ($starter_id && get_post($starter_id)) {
        $postarr['ID'] = $starter_id;
        $new_id = wp_update_post($postarr, true);
    } else {
        $new_id = wp_insert_post($postarr, true);
        if (!is_wp_error($new_id)) update_option('tmon_starter_page_id', $new_id);
    }

    if (is_wp_error($new_id)) {
        wp_redirect(admin_url('admin.php?page=tmon-starter&created=0&error=' . urlencode($new_id->get_error_message())));
    } else {
        wp_redirect(admin_url('admin.php?page=tmon-starter&created=1'));
    }
    exit;
});
