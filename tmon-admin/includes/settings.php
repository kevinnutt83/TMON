<?php
// TMON Admin Settings registration
add_action('admin_init', function() {
    register_setting('tmon_admin_settings_group', 'tmon_admin_uc_key');
    register_setting('tmon_admin_settings_group', 'tmon_admin_hub_url');
    register_setting('tmon_admin_settings_group', 'tmon_admin_queue_lifetime');
    register_setting('tmon_admin_settings_group', 'tmon_admin_queue_max_per_site');
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

if (!defined('ABSPATH')) exit;

// Add the settings submenu callback if it doesn't exist; the menu is already registered
// in tmon-admin.php; implement the callback and purge handlers here.
if (!function_exists('tmon_admin_settings_page')) {
	function tmon_admin_settings_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		// Save action handling (moved purge forms)
		echo '<div class="wrap"><h1>TMON Admin Settings</h1>';
		// Purge options
		echo '<h2>Data Maintenance</h2>';
		echo '<form method="post" onsubmit="return confirm(\'This will delete ALL provisioning and audit data on this Admin site. Continue?\');" style="margin-bottom:10px">';
		wp_nonce_field('tmon_admin_purge_all');
		echo '<input type="hidden" name="tmon_admin_action" value="purge_all" />';
		submit_button('Purge ALL Admin data', 'delete', 'submit', false);
		echo '</form>';

		echo '<form method="post" onsubmit="return confirm(\'This will delete data for the specified Unit ID. Continue?\');">';
		wp_nonce_field('tmon_admin_purge_unit');
		echo '<input type="hidden" name="tmon_admin_action" value="purge_unit" />';
		echo 'Unit ID <input type="text" name="unit_id" class="regular-text" placeholder="123456" /> ';
		submit_button('Purge by Unit ID', 'delete', 'submit', false);
		echo '</form>';

		// Settings forms
		echo '<h2>Provisioning Queue Settings</h2>';
		echo '<form method="post" action="options.php">';
		settings_fields('tmon_admin_settings_group');
		do_settings_sections('tmon-admin-settings');
		echo '<table class="form-table">';
		$cur_lifetime = intval(get_option('tmon_admin_queue_lifetime', 3600));
		$cur_max = intval(get_option('tmon_admin_queue_max_per_site', 10));
		echo '<tr><th scope="row">Queue Lifetime (seconds)</th><td><input name="tmon_admin_queue_lifetime" type="number" class="small-text" value="'.esc_attr($cur_lifetime).'" /></td></tr>';
		echo '<tr><th scope="row">Max Pending Per Site</th><td><input name="tmon_admin_queue_max_per_site" type="number" min="1" class="small-text" value="'.esc_attr($cur_max).'" /></td></tr>';
		echo '</table>';
		submit_button('Save Queue Settings');
		echo '</form>';

		echo '</div>';
	}
}

// Add action handler for the purge postbacks (mirrors what existed in provisioning, but now here)
add_action('admin_init', function(){
    if (!current_user_can('manage_options')) return;
    // Purge all
    if (isset($_POST['tmon_admin_action']) && $_POST['tmon_admin_action'] === 'purge_all' && check_admin_referer('tmon_admin_purge_all')) {
        global $wpdb;
        $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_provisioned_devices");
        $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_claim_requests");
        $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_audit");
        if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $wpdb->prefix.'tmon_devices'))) {
            $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_devices");
        }
        add_action('admin_notices', function(){ echo '<div class="updated"><p>Admin data purged.</p></div>'; });
    }
    // Purge unit
    if (isset($_POST['tmon_admin_action']) && $_POST['tmon_admin_action'] === 'purge_unit' && check_admin_referer('tmon_admin_purge_unit')) {
        global $wpdb;
        $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
        if ($unit_id) {
            $wpdb->delete($wpdb->prefix.'tmon_provisioned_devices', ['unit_id'=>$unit_id]);
            $wpdb->query($wpdb->prepare("DELETE FROM {$wpdb->prefix}tmon_claim_requests WHERE unit_id=%s", $unit_id));
            if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $wpdb->prefix.'tmon_devices'))) {
                $wpdb->delete($wpdb->prefix.'tmon_devices', ['unit_id'=>$unit_id]);
            }
        }
        add_action('admin_notices', function(){ echo '<div class="updated"><p>Unit data purged.</p></div>'; });
    }
});
