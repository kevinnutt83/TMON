<?php
/**
 * Plugin Name: TMON Admin
 * Description: Administration plugin for TMON devices and firmware management.
 * Version: 0.2.0
 * Author: Your Name
 * License: MIT
 */

require_once __DIR__ . '/includes/helpers.php';
require_once __DIR__ . '/includes/db.php';

function tmon_admin_activation() {
	// Silence any accidental output during activation to avoid “1 character of unexpected output”.
	ob_start();
	$prev = null;
	if (isset($GLOBALS['wpdb'])) {
		$prev = $GLOBALS['wpdb']->suppress_errors();
		$GLOBALS['wpdb']->suppress_errors(true);
	}
	try {
		if (function_exists('tmon_admin_db_ensure')) {
			tmon_admin_db_ensure();
		}
	} catch (\Throwable $e) {
		// Swallow errors here; WP will surface activation failure if fatal.
	} finally {
		if ($prev !== null) {
			$GLOBALS['wpdb']->suppress_errors($prev);
		}
		ob_end_clean();
	}
}
register_activation_hook(__FILE__, 'tmon_admin_activation');

// Also ensure schema idempotently on admin_init without emitting output.
add_action('admin_init', function () {
	if (!function_exists('tmon_admin_db_ensure')) return;
	tmon_admin_silence(function () {
		tmon_admin_db_ensure();
	});
});

// Only register menus here if master is NOT present
if (!defined('TMON_ADMIN_MASTER_MENU')) {
	add_action('admin_menu', function () {
		$cap = 'manage_options';
		$top_slug = 'tmon-admin';

		// Remove any legacy stray top-levels that caused duplication.
		remove_menu_page('tmon-admin-command-logs');

		add_menu_page(
			'TMON Admin',
			'TMON Admin',
			$cap,
			$top_slug,
			function () { do_action('tmon_admin_render_dashboard'); },
			'dashicons-admin-generic',
			56
		);

		// Keep the first submenu pointing to the same dashboard.
		add_submenu_page($top_slug, 'Dashboard', 'Dashboard', $cap, $top_slug, function () {
			do_action('tmon_admin_render_dashboard');
		});
		add_submenu_page($top_slug, 'Provisioning', 'Provisioning', $cap, 'tmon-admin-provisioning', function () {
			do_action('tmon_admin_provisioning_page');
		});
		add_submenu_page($top_slug, 'Provisioning History', 'Provisioning History', $cap, 'tmon-admin-provisioning-history', function () {
			do_action('tmon_admin_provisioning_history_page');
		});
		add_submenu_page($top_slug, 'Provisioning Activity', 'Provisioning Activity', $cap, 'tmon-admin-provisioning-activity', function () {
			do_action('tmon_admin_provisioning_activity_page');
		});
		add_submenu_page($top_slug, 'Notifications', 'Notifications', $cap, 'tmon-admin-notifications', function () {
			do_action('tmon_admin_notifications_page');
		});
		add_submenu_page($top_slug, 'Firmware', 'Firmware', $cap, 'tmon-admin-firmware', function () {
			do_action('tmon_admin_firmware_page');
		});
		add_submenu_page($top_slug, 'OTA Management', 'OTA Management', $cap, 'tmon-admin-ota', function () {
			do_action('tmon_admin_ota_page');
		});
		add_submenu_page($top_slug, 'Unit Connectors', 'Unit Connectors', $cap, 'tmon-admin-uc', function () {
			do_action('tmon_admin_uc_connectors_page');
		});
		add_submenu_page($top_slug, 'Provisioned Devices', 'Provisioned Devices', $cap, 'tmon-admin-provisioned-devices', function () {
			do_action('tmon_admin_provisioned_devices_page');
		});
		add_submenu_page($top_slug, 'Command Logs', 'Command Logs', $cap, 'tmon-admin-command-logs', function () {
			do_action('tmon_admin_command_logs_page');
		});
	}, 9);

	add_action('tmon_admin_render_dashboard', function () {
		static $printed = false; if ($printed) return; $printed = true;
		echo '<div class="wrap"><h1>TMON Admin</h1>';
		echo '</div>';
	});
}

// Include page modules
require_once __DIR__ . '/includes/notifications.php';
require_once __DIR__ . '/includes/commands.php';
require_once __DIR__ . '/includes/provisioning.php';
require_once __DIR__ . '/includes/firmware.php';
require_once __DIR__ . '/includes/ota.php';
require_once __DIR__ . '/includes/unit_connectors.php';
require_once __DIR__ . '/includes/provisioned-devices.php';