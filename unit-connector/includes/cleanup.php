<?php
if (!defined('ABSPATH')) exit;

// Centralized cleanup routine to remove DB tables, options, files, scheduled hooks, and roles.
// Call tmon_uc_remove_all_data() from admin purge, deactivation (if option set), or uninstall.php.
if (!function_exists('tmon_uc_rrmdir')) {
	function tmon_uc_rrmdir($dir) {
		if (!is_dir($dir)) return true;
		$files = new RecursiveIteratorIterator(
			new RecursiveDirectoryIterator($dir, RecursiveDirectoryIterator::SKIP_DOTS),
			RecursiveIteratorIterator::CHILD_FIRST
		);
		foreach ($files as $fileinfo) {
			$todo = ($fileinfo->isDir() ? 'rmdir' : 'unlink');
			try { @$todo($fileinfo->getRealPath()); } catch (Exception $e) { /* best-effort */ }
		}
		try { @rmdir($dir); } catch (Exception $e) { /* best-effort */ }
		return !is_dir($dir);
	}
}

if (!function_exists('tmon_uc_remove_all_data')) {
	function tmon_uc_remove_all_data($force = false) {
		global $wpdb;
		$ok = true;

		// Capability check in non-force mode
		if (!$force && !current_user_can('manage_options')) {
			error_log('tmon-uc: remove_all_data called without manage_options capability.');
			return false;
		}

		// List of known tables (prefix will be prepended)
		$tables = array_unique([
			'tmon_field_data',
			'tmon_devices',
			'tmon_ota_jobs',
			'tmon_device_commands',
			'tmon_company',
			'tmon_site',
			'tmon_zone',
			'tmon_cluster',
			'tmon_unit',
			'tmon_audit',
			'tmon_device_data',
			'tmon_staged_settings',
			'tmon_uc_devices',
		]);

		// Disable foreign key checks (MySQL) to avoid constraint failures while dropping
		$wpdb->query("SET FOREIGN_KEY_CHECKS = 0");

		foreach ($tables as $t) {
			$table_name = $wpdb->prefix . $t;
			try {
				$wpdb->query("DROP TABLE IF EXISTS {$table_name}");
			} catch (Exception $e) {
				error_log("tmon-uc: failed to drop table {$table_name} - " . $e->getMessage());
				$ok = false;
			}
		}

		// Re-enable foreign key checks
		$wpdb->query("SET FOREIGN_KEY_CHECKS = 1");

		// Delete options by prefix and a set of known option keys
		try {
			$option_like = $wpdb->esc_like('tmon_uc_') . '%';
			$rows = $wpdb->get_col($wpdb->prepare("SELECT option_name FROM {$wpdb->options} WHERE option_name LIKE %s", $option_like));
			if (is_array($rows)) {
				foreach ($rows as $opt) {
					delete_option($opt);
				}
			}
			// Remove a few known community options used across templates/pages
			$known = [
				'tmon_uc_remove_data_on_deactivate',
				'tmon_uc_admin_key',
				'tmon_uc_hub_url',
				'tmon_uc_paired_sites',
				'tmon_uc_hub_shared_key',
				'tmon_uc_hub_read_token',
				'tmon_starter_page_id',
				'tmon_public_docs_page_id',
				'tmon_public_docs_include_shortcodes',
				'tmon_admin_notifications',
				'tmon_uc_device_settings',
				'tmon_admin_uc_sites',
				'tmon_uc_auto_update',
				'tmon_uc_history_voltage_min',
				'tmon_uc_history_voltage_max',
			];
			foreach ($known as $k) delete_option($k);
		} catch (Exception $e) {
			error_log("tmon-uc: option purge error - " . $e->getMessage());
			$ok = false;
		}

		// Clear scheduled hooks
		if (function_exists('wp_clear_scheduled_hook')) {
			@wp_clear_scheduled_hook('tmon_uc_command_requeue_cron');
			@wp_clear_scheduled_hook('tmon_uc_scan_offline_event');
			@wp_clear_scheduled_hook('tmon_uc_sync_devices_cron');
		}

		// Remove scheduled transients used by plugin
		@delete_transient('tmon_uc_devices_dirty');

		// Remove roles added by plugin
		try {
			remove_role('tmon_manager');
			remove_role('tmon_operator');
		} catch (Exception $e) {
			// ignore
		}

		// Delete plugin-created directories and files (best-effort)
		$dirs = [];
		if (defined('WP_CONTENT_DIR')) {
			$dirs[] = WP_CONTENT_DIR . '/tmon-field-logs';
			$dirs[] = WP_CONTENT_DIR . '/tmon-device-uploads';
		}
		$upload_dir = wp_upload_dir();
		if (!empty($upload_dir['basedir'])) {
			$dirs[] = trailingslashit($upload_dir['basedir']) . 'tmon_device_files';
		}
		foreach (array_unique($dirs) as $d) {
			if (@is_dir($d)) {
				if (!tmon_uc_rrmdir($d)) {
					error_log("tmon-uc: failed to fully remove directory {$d}");
					$ok = false;
				}
			}
		}

		// Remove plugin-specific uploads stored elsewhere if present (best-effort)
		// Remove /wp-content/tmon-field-logs/* files if any residual
		if (defined('WP_CONTENT_DIR')) {
			$fld = WP_CONTENT_DIR . '/tmon-field-logs';
			if (is_dir($fld)) {
				foreach (glob($fld . '/*') as $f) { @unlink($f); }
				@rmdir($fld);
			}
		}

		// Final: attempt to remove transient/plugin-specific cron entries again
		if (function_exists('wp_clear_scheduled_hook')) {
			@wp_clear_scheduled_hook('tmon_uc_command_requeue_cron');
			@wp_clear_scheduled_hook('tmon_uc_scan_offline_event');
			@wp_clear_scheduled_hook('tmon_uc_sync_devices_cron');
		}

		error_log('tmon-uc: tmon_uc_remove_all_data completed. ok=' . ($ok ? '1' : '0'));
		return (bool)$ok;
	}
}
