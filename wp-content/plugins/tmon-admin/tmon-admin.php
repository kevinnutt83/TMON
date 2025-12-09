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

// Fallback: ensure required tables/columns even if includes/db.php didn't provide tmon_admin_db_ensure()
if (!function_exists('tmon_admin_db_ensure')) {
	function tmon_admin_db_ensure() {
		global $wpdb;
		require_once ABSPATH . 'wp-admin/includes/upgrade.php';
		$charset = $wpdb->get_charset_collate();
		$p = $wpdb->prefix;

		// Notifications
		$notifications = "{$p}tmon_notifications";
		dbDelta("CREATE TABLE {$notifications} (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			title VARCHAR(255) NOT NULL,
			message LONGTEXT NULL,
			level VARCHAR(32) NOT NULL DEFAULT 'info',
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			read_at DATETIME NULL,
			PRIMARY KEY (id),
			KEY idx_created (created_at),
			KEY idx_read (read_at)
		) {$charset};");

		// Provisioned devices
		$prov = "{$p}tmon_provisioned_devices";
		dbDelta("CREATE TABLE {$prov} (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			unit_id VARCHAR(64) NOT NULL,
			machine_id VARCHAR(64) NOT NULL,
			unit_name VARCHAR(128) DEFAULT '',
			role VARCHAR(32) DEFAULT 'base',
			company_id BIGINT UNSIGNED NULL,
			plan VARCHAR(64) DEFAULT 'standard',
			status VARCHAR(32) DEFAULT 'active',
			notes TEXT NULL,
			site_url VARCHAR(255) DEFAULT '',
			wordpress_api_url VARCHAR(255) DEFAULT '',
			settings_staged TINYINT(1) DEFAULT 0,
			firmware VARCHAR(128) DEFAULT '',
			firmware_url VARCHAR(255) DEFAULT '',
			machine_id_norm VARCHAR(64) DEFAULT '',
			unit_id_norm VARCHAR(64) DEFAULT '',
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
			PRIMARY KEY (id),
			UNIQUE KEY unit_machine (unit_id, machine_id),
			KEY company_idx (company_id),
			KEY status_idx (status)
		) {$charset};");

		// Commands: ensure status/updated_at
		$cmd = "{$p}tmon_device_commands";
		$exists_cmd = (bool) $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $cmd));
		if (!$exists_cmd) {
			dbDelta("CREATE TABLE {$cmd} (
				id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
				device_id VARCHAR(64) NOT NULL,
				command VARCHAR(64) NOT NULL,
				params LONGTEXT NULL,
				status VARCHAR(32) NOT NULL DEFAULT 'queued',
				created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
				updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
				PRIMARY KEY (id),
				KEY device_idx (device_id),
				KEY status_idx (status)
			) {$charset};");
		} else {
			$col = $wpdb->get_var($wpdb->prepare("SHOW COLUMNS FROM {$cmd} LIKE %s", 'status'));
			if (!$col) $wpdb->query("ALTER TABLE {$cmd} ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'queued'");
			$col = $wpdb->get_var($wpdb->prepare("SHOW COLUMNS FROM {$cmd} LIKE %s", 'updated_at'));
			if (!$col) $wpdb->query("ALTER TABLE {$cmd} ADD COLUMN updated_at DATETIME NULL AFTER created_at");
		}

		// OTA jobs: ensure action/updated_at
		$ota = "{$p}tmon_ota_jobs";
		$exists_ota = (bool) $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $ota));
		if (!$exists_ota) {
			dbDelta("CREATE TABLE {$ota} (
				id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
				unit_id VARCHAR(64) NOT NULL,
				action VARCHAR(64) NOT NULL,
				args LONGTEXT NULL,
				status VARCHAR(32) NOT NULL DEFAULT 'queued',
				created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
				updated_at DATETIME NULL,
				PRIMARY KEY (id),
				KEY idx_unit (unit_id),
				KEY idx_status (status),
				KEY idx_created (created_at)
			) {$charset};");
		} else {
			$col = $wpdb->get_var($wpdb->prepare("SHOW COLUMNS FROM {$ota} LIKE %s", 'action'));
			if (!$col) $wpdb->query("ALTER TABLE {$ota} ADD COLUMN action VARCHAR(64) NOT NULL AFTER unit_id");
			$col = $wpdb->get_var($wpdb->prepare("SHOW COLUMNS FROM {$ota} LIKE %s", 'updated_at'));
			if (!$col) $wpdb->query("ALTER TABLE {$ota} ADD COLUMN updated_at DATETIME NULL AFTER created_at");
		}
	}
}

function tmon_admin_activation() {
	ob_start();
	$prev = null;
	if (isset($GLOBALS['wpdb'])) {
		$prev = $GLOBALS['wpdb']->suppress_errors();
		$GLOBALS['wpdb']->suppress_errors(true);
	}
	try { tmon_admin_db_ensure(); } catch (\Throwable $e) {} finally {
		if ($prev !== null) { $GLOBALS['wpdb']->suppress_errors($prev); }
		ob_end_clean();
	}
}
register_activation_hook(__FILE__, 'tmon_admin_activation');

add_action('admin_init', function () {
	tmon_admin_silence(function () { tmon_admin_db_ensure(); });
});

add_action('admin_menu', function () {
	$cap = 'manage_options';
	$top_slug = 'tmon-admin';

	remove_menu_page('tmon-admin-command-logs');

	add_menu_page('TMON Admin','TMON Admin',$cap,$top_slug,function(){ do_action('tmon_admin_render_dashboard'); },'dashicons-admin-generic',56);

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

// Include page modules
require_once __DIR__ . '/includes/notifications.php';
require_once __DIR__ . '/includes/commands.php';
require_once __DIR__ . '/includes/provisioning.php';
require_once __DIR__ . '/includes/firmware.php';
require_once __DIR__ . '/includes/ota.php';
require_once __DIR__ . '/includes/unit_connectors.php';
require_once __DIR__ . '/includes/provisioned-devices.php';