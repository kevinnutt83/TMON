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

register_activation_hook(__FILE__, function () {
	// Ensure all required tables/columns exist on activation.
	if (function_exists('tmon_admin_db_ensure')) {
		tmon_admin_db_ensure();
	}
});
add_action('admin_init', function () {
	// Ensure schema on every admin page load (idempotent).
	if (function_exists('tmon_admin_db_ensure')) {
		tmon_admin_db_ensure();
	}
});

add_action('admin_menu', function () {
	// Single top-level TMON Admin.
	$cap = 'manage_options'; // adjust to custom caps if plugin defines
	$top_slug = 'tmon-admin';

	// Avoid duplicate top-levels by removing any legacy registrations.
	remove_menu_page('tmon-admin-command-logs'); // legacy stray top-level

	add_menu_page(
		'TMON Admin',
		'TMON Admin',
		$cap,
		$top_slug,
		function () {
			// ...existing code to render dashboard or a summary page...
			do_action('tmon_admin_render_dashboard');
		},
		'dashicons-admin-generic',
		56
	);

	// Submenus
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

	add_submenu_page($top_slug, 'Files', 'Files', $cap, 'tmon-admin-files', function () {
		do_action('tmon_admin_files_page');
	});

	add_submenu_page($top_slug, 'Groups', 'Groups', $cap, 'tmon-admin-groups', function () {
		do_action('tmon_admin_groups_page');
	});

	add_submenu_page($top_slug, 'Provisioned Devices', 'Provisioned Devices', $cap, 'tmon-admin-provisioned-devices', function () {
		do_action('tmon_admin_provisioned_devices_page');
	});

	// Move Command Logs under TMON Admin submenu.
	add_submenu_page($top_slug, 'TMON Command Logs', 'Command Logs', $cap, 'tmon-admin-command-logs', function () {
		do_action('tmon_admin_command_logs_page');
	});
}, 9);

// Include page renderers (ensure they use static guard to avoid double output)
require_once __DIR__ . '/includes/notifications.php';
require_once __DIR__ . '/includes/commands.php';
require_once __DIR__ . '/includes/provisioning.php';
require_once __DIR__ . '/includes/firmware.php';
require_once __DIR__ . '/includes/ota.php';
require_once __DIR__ . '/includes/unit_connectors.php';
require_once __DIR__ . '/includes/provisioned-devices.php';

// Dashboard renderer (kept simple)
add_action('tmon_admin_render_dashboard', function () {
	static $printed = false; if ($printed) return; $printed = true;
	echo '<div class="wrap"><h1>TMON Admin</h1>';
	// ...existing code...
	echo '<p>Use the submenu to manage provisioning, firmware, OTA, notifications, devices, and logs.</p>';
	echo '</div>';
});

// ...existing code...