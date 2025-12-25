<?php
// Public Docs Page creation for end users (with images and descriptions)

add_action('admin_menu', function() {
    add_submenu_page('tmon_devices', 'Public Docs', 'Public Docs', 'manage_options', 'tmon-public-docs', function(){
        if (!current_user_can('manage_options')) { wp_die('Insufficient permissions'); }
        $docs_id = intval(get_option('tmon_public_docs_page_id', 0));
        $exists = $docs_id && get_post($docs_id) && get_post_status($docs_id);
        $include_pref = get_option('tmon_public_docs_include_shortcodes', 0) ? 1 : 0;
        echo '<div class="wrap"><h1>TMON Public Docs Page</h1>';
        echo '<p>Create a public-facing documentation page with embedded images and descriptions. Optionally include live shortcodes for demos (may expose device data publicly).</p>';
        if ($exists) {
            $view = get_permalink($docs_id);
            echo '<p><a class="button button-primary" target="_blank" href="' . esc_url($view) . '">View Docs Page</a></p>';
        }
        echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '" style="margin-top:12px">';
        echo '<input type="hidden" name="action" value="tmon_create_public_docs_page">';
        wp_nonce_field('tmon_create_public_docs_page');
        echo '<label><input type="checkbox" name="include_shortcodes" value="1" ' . checked(1, $include_pref, false) . '> Include live shortcodes (demo)</label>';
        echo '<p class="description">Warning: enabling this may reveal device information on a public page. Use a staging environment or limited visibility if needed.</p>';
        echo '<p><button type="submit" class="button button-primary">' . ($exists ? 'Regenerate Docs Page' : 'Create Docs Page') . '</button></p>';
        echo '</form>';
        echo '</div>';
    });
});

add_action('admin_post_tmon_create_public_docs_page', function(){
    if (!current_user_can('manage_options')) { wp_die('Insufficient permissions'); }
    check_admin_referer('tmon_create_public_docs_page');

    // Resolve image base URL
    $plugin_main = dirname(__DIR__) . '/tmon-unit-connector.php';
    $img_base = plugins_url('assets/images/', $plugin_main);
    $include_live = !empty($_POST['include_shortcodes']);
    update_option('tmon_public_docs_include_shortcodes', $include_live ? 1 : 0);

    $content = '';
    $content .= "<h1>TMON Device Monitoring</h1>\n";
    $content .= "<p>Welcome! This page shows how to view your devices, explore their data, and claim a device.</p>\n";

    // Hierarchy section
    $content .= "<h2>1. Hierarchy Overview</h2>\n";
    $content .= "<p>Devices are organized by Company, Site, Zone, Cluster, and Unit. This helps you locate and group devices logically.</p>\n";
    $content .= '<p><img src="' . esc_url($img_base . 'hierarchy.svg') . '" alt="Hierarchy Overview" style="max-width: 720px; width: 100%; height: auto; border:1px solid #ddd; border-radius:6px"/></p>';

    // Shortcodes/Widgets section
    $content .= "<h2>2. Device Views</h2>\n";
    $content .= "<p>Below are common views you might see on your site. Your administrator can place these widgets on different pages.</p>\n";
    $content .= '<p><img src="' . esc_url($img_base . 'shortcodes.svg') . '" alt="Shortcodes" style="max-width: 720px; width: 100%; height: auto; border:1px solid #ddd; border-radius:6px"/></p>';
    $content .= "<ul>\n";
    $content .= "<li><strong>Active Units</strong> — Current devices and their last seen time.</li>\n";
    $content .= "<li><strong>Device List/Status</strong> — Organized lists and status tables per hierarchy. If relays are enabled for a device, authorized users may see controls to turn relays on/off or schedule actions.</li>\n";
    $content .= "<li><strong>Device Data</strong> — Latest sensor data for a specific unit.</li>\n";
    $content .= "<li><strong>Device History</strong> — A 24-hour chart of recent readings.</li>\n";
    $content .= "</ul>\n";

    // Claim section
    $content .= "<h2>3. Claim a Device</h2>\n";
    $content .= "<p>If you purchased a compatible device, you can request ownership by submitting your Unit ID and Machine ID.</p>\n";
    $content .= '<p><img src="' . esc_url($img_base . 'claim.svg') . '" alt="Claim Device Form" style="max-width: 720px; width: 100%; height: auto; border:1px solid #ddd; border-radius:6px"/></p>';
    $content .= "<p>After submitting, an administrator will review your claim. You will be notified if it is approved.</p>\n";

    if ($include_live) {
        $content .= "<h2>Live Demos (Optional)</h2>\n";
        $content .= "<p>The following sections are rendered using live shortcodes and may show real device data. Replace <code>UNIT123</code> with an actual unit ID for device-specific views.</p>\n";
        $content .= "<h3>Active Units</h3>\n[tmon_active_units]\n\n";
        $content .= "<h3>Device List & Status</h3>\n[tmon_device_list]\n\n[tmon_device_status]\n\n";
        $content .= "<h3>Device Data (replace UNIT123)</h3>\n[tmon_device_sdata unit_id=\"UNIT123\"]\n\n";
        $content .= "<h3>Device History (replace UNIT123)</h3>\n[tmon_device_history unit_id=\"UNIT123\" hours=\"24\"]\n\n";
        $content .= "<h3>Claim a Device</h3>\n[tmon_claim_device]\n\n";
    }

    $content .= "<h2>Privacy & Support</h2>\n";
    $content .= "<p>Your data is protected according to your organization's policies. For help, contact your administrator.</p>\n";

    $docs_id = intval(get_option('tmon_public_docs_page_id', 0));
    $postarr = array(
        'post_title'   => 'TMON Docs',
        'post_content' => $content,
        'post_status'  => 'publish',
        'post_type'    => 'page',
    );

    if ($docs_id && get_post($docs_id)) {
        $postarr['ID'] = $docs_id;
        $new_id = wp_update_post($postarr, true);
    } else {
        $new_id = wp_insert_post($postarr, true);
        if (!is_wp_error($new_id)) update_option('tmon_public_docs_page_id', $new_id);
    }

    if (is_wp_error($new_id)) {
        wp_redirect(admin_url('admin.php?page=tmon-public-docs&created=0&error=' . urlencode($new_id->get_error_message())));
    } else {
        wp_redirect(admin_url('admin.php?page=tmon-public-docs&created=1'));
    }
    exit;
});
