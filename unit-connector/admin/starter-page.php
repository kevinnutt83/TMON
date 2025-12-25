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

    // Dynamically get all TMON shortcodes from shortcodes.php
    $shortcodes = array();
    global $shortcode_tags;
    foreach ($shortcode_tags as $tag => $func) {
        if (strpos($tag, 'tmon_') === 0) {
            $shortcodes[] = $tag;
        }
    }
    // Remove duplicates, just in case
    $shortcodes = array_unique($shortcodes);

    $content = "<h2>TMON Shortcodes Overview</h2>\n";
    $content .= "<p>This page lists all available TMON shortcodes currently registered in the system.</p>\n";
    foreach ($shortcodes as $shortcode) {
        // $content .= "<h3><strong>[$shortcode]</strong></h3>\n";
        $content .= "[$shortcode]\n\n";
    }

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
