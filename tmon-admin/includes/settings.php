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

// Helper: delete rows from table if table exists
if (!function_exists('tmon_admin_safe_delete_table_rows')) {
	function tmon_admin_safe_delete_table_rows($table_name) {
		global $wpdb;
		if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table_name))) {
			$wpdb->query("DELETE FROM {$table_name}");
		}
	}
}

// Helper: delete option if it's clearly a data store (not a settings key)
if (!function_exists('tmon_admin_safe_delete_option')) {
	function tmon_admin_safe_delete_option($option_key) {
		// only delete some common data options (do not drop tmon-admin config keys)
		$data_options = [
			'tmon_admin_pending_provision',
			'tmon_admin_provision_history',
			'tmon_admin_known_ids_cache',
			'tmon_admin_ota_jobs',
			'tmon_admin_files',
			'tmon_admin_notifications',
		];
		if (in_array($option_key, $data_options, true)) {
			delete_option($option_key);
		}
	}
}

// Helper: remove stored files produced by plugin (field logs, uploaded packages)
if (!function_exists('tmon_admin_safe_cleanup_files')) {
	function tmon_admin_safe_cleanup_files() {
		// Clear field logs directory (non-settings data)
		$fld = WP_CONTENT_DIR . '/tmon-field-logs';
		if (is_dir($fld)) {
			foreach (glob($fld . '/*') as $f) { if (is_file($f)) @unlink($f); }
		}
		// Clear tmon-admin-packages directory (uploaded packages)
		$pkg = WP_CONTENT_DIR . '/tmon-admin-packages';
		if (is_dir($pkg)) {
			foreach (glob($pkg . '/*') as $f) { if (is_file($f)) @unlink($f); }
		}
	}
}

add_action('admin_init', function(){
    if (!current_user_can('manage_options')) return;

    // Purge all
    if (isset($_POST['tmon_admin_action']) && $_POST['tmon_admin_action'] === 'purge_all' && check_admin_referer('tmon_admin_purge_all')) {
        global $wpdb;
        // Plugin data tables
        $tables = [
            $wpdb->prefix . 'tmon_provisioned_devices',
            $wpdb->prefix . 'tmon_claim_requests',
            $wpdb->prefix . 'tmon_audit',
            $wpdb->prefix . 'tmon_devices',
            $wpdb->prefix . 'tmon_field_data',
            $wpdb->prefix . 'tmon_ota_jobs',
            $wpdb->prefix . 'tmon_files',
        ];
        foreach ($tables as $t) {
            tmon_admin_safe_delete_table_rows($t);
        }

        // In-memory / option caches & queues (data, not settings)
        $data_options = [
            'tmon_admin_pending_provision',
            'tmon_admin_provision_history',
            'tmon_admin_known_ids_cache',
            'tmon_admin_ota_jobs',
            'tmon_admin_files',
            'tmon_admin_notifications',
        ];
        foreach ($data_options as $opt) {
            delete_option($opt);
        }

        // Cleanup generated files, logs, uploads
        tmon_admin_safe_cleanup_files();

        // Audit & notice
        do_action('tmon_admin_audit', 'purge_all', sprintf('user=%s', wp_get_current_user()->user_login));
        add_action('admin_notices', function(){ echo '<div class="updated"><p>All device & provisioning data purged (plugin settings preserved).</p></div>'; });
    }

    // Purge unit (delete rows for a specific unit)
    if (isset($_POST['tmon_admin_action']) && $_POST['tmon_admin_action'] === 'purge_unit' && check_admin_referer('tmon_admin_purge_unit')) {
        global $wpdb;
        $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
        if ($unit_id) {
            $tbls_by_unit = [
                $wpdb->prefix . 'tmon_provisioned_devices' => ['unit_id' => $unit_id],
                // optionally delete any field data or audit records per unit
                $wpdb->prefix . 'tmon_claim_requests' => ['unit_id' => $unit_id],
                $wpdb->prefix . 'tmon_devices' => ['unit_id' => $unit_id],
                $wpdb->prefix . 'tmon_field_data' => ['unit_id' => $unit_id],
            ];
            foreach ($tbls_by_unit as $tbl => $where) {
                if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $tbl))) {
                    $wpdb->delete($tbl, $where);
                }
            }
            // Clean options and history for the unit
            // Remove pending queue entries for this unit (key matches unit_id or machine_id)
            $queue = get_option('tmon_admin_pending_provision', []);
            if (is_array($queue)) {
                foreach ($queue as $k => $v) {
                    if ($k === $unit_id || (isset($v['unit_id']) && $v['unit_id'] === $unit_id) || (isset($v['machine_id']) && $v['machine_id'] === $unit_id)) {
                        unset($queue[$k]);
                    }
                }
                update_option('tmon_admin_pending_provision', $queue);
            }
            // Clear known IDs cache and provision history related to this unit
            $known = get_option('tmon_admin_known_ids_cache', []);
            if (is_array($known) && isset($known[$unit_id])) {
                unset($known[$unit_id]);
                update_option('tmon_admin_known_ids_cache', $known);
            }
            $history = get_option('tmon_admin_provision_history', []);
            if (is_array($history)) {
                $history = array_values(array_filter($history, function($h) use ($unit_id) {
                    return !isset($h['unit_id']) || $h['unit_id'] !== $unit_id;
                }));
                update_option('tmon_admin_provision_history', $history);
            }
        }
        do_action('tmon_admin_audit', 'purge_unit', sprintf('user=%s unit=%s', wp_get_current_user()->user_login, $unit_id));
        add_action('admin_notices', function(){ echo '<div class="updated"><p>Unit data purged.</p></div>'; });
    }
});
