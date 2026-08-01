<?php
// Starter Page creation for quick onboarding

add_action('admin_menu', function() {
    add_submenu_page('tmon_devices', 'Starter Page', 'Starter Page', 'manage_options', 'tmon-starter', function(){
        if (!current_user_can('manage_options')) { wp_die('Insufficient permissions'); }
        $starter_id = intval(get_option('tmon_starter_page_id', 0));
        $exists = $starter_id && function_exists('get_post') && get_post($starter_id) && function_exists('get_post_status') && get_post_status($starter_id);
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

    $content = "<h2>TMON Starter</h2>\n";
    $content .= "<p>This page uses the shared unit picker flow so the core widgets render without hand-editing unit IDs. Use the Known IDs table below when you need explicit <code>unit_id</code> or <code>units</code> shortcode attributes.</p>\n";
    $content .= "[tmon_known_ids]\n\n";
    $content .= "<h3>Fleet Overview</h3>\n";
    $content .= "[tmon_active_units]\n\n";
    $content .= "[tmon_device_status]\n\n";
    $content .= "<h3>Selected Device</h3>\n";
    $content .= "[tmon_device_sdata refresh_s=\"30\"]\n\n";
    $content .= "[tmon_device_history hours=\"24\" refresh_s=\"60\"]\n\n";
    $content .= "[tmon_frost_heat_watch refresh_s=\"30\"]\n\n";
    $content .= "<h3>Commands</h3>\n";
    $content .= "[tmon_pending_commands]\n\n";
    $content .= "[tmon_relay_controls]\n\n";
    $content .= "<h3>Advanced Shortcodes</h3>\n";
    $content .= "<p>Examples:</p>\n";
    $content .= "<pre>[tmon_device_sdata unit_id=\"your-unit-id\"]\n[tmon_device_history unit_id=\"your-unit-id\" hours=\"24\"]\n[tmon_devices_history units=\"unit-a,unit-b\" hours=\"24\"]</pre>\n";

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
