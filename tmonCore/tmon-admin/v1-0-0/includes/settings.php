<?php
// TMON Admin Settings registration
add_action('admin_init', function() {
    register_setting('tmon_admin_settings_group', 'tmon_admin_uc_key');
    register_setting('tmon_admin_settings_group', 'tmon_admin_hub_url');
    add_settings_section('tmon_admin_main', 'Main Settings', function(){
        echo '<p>Configure cross-site integration and defaults for TMON Admin.</p>';
    }, 'tmon-admin-settings');
    add_settings_field('tmon_admin_uc_key', 'Shared Key for UC Integration', function() {
        $val = get_option('tmon_admin_uc_key', '');
        echo '<input type="text" name="tmon_admin_uc_key" class="regular-text" value="' . esc_attr($val) . '" />';
        echo '<p class="description">Used as X-TMON-ADMIN header when pushing to Unit Connector endpoints.</p>';
    }, 'tmon-admin-settings', 'tmon_admin_main');
    add_settings_field('tmon_admin_hub_url', 'Hub URL (for UC forward)', function() {
        $val = get_option('tmon_admin_hub_url', home_url());
        echo '<input type="url" name="tmon_admin_hub_url" class="regular-text" value="' . esc_attr($val) . '" />';
        echo '<p class="description">Optional; Unit Connector can set TMON_ADMIN_HUB_URL to forward unknown devices here.</p>';
    }, 'tmon-admin-settings', 'tmon_admin_main');
});
