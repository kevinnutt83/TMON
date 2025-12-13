<?php
function tmon_admin_install_schema() {
	global $wpdb;
	$charset_collate = $wpdb->get_charset_collate();
	require_once ABSPATH . 'wp-admin/includes/upgrade.php';

	// Devices mirror
	$sql = "CREATE TABLE {$wpdb->prefix}tmon_devices (
		id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
		machine_id VARCHAR(64) NOT NULL,
		unit_id VARCHAR(64) NOT NULL,
		unit_name VARCHAR(100) DEFAULT NULL,
		company VARCHAR(191) DEFAULT NULL,
		site VARCHAR(191) DEFAULT NULL,
		zone VARCHAR(191) DEFAULT NULL,
		cluster VARCHAR(191) DEFAULT NULL,
		suspended TINYINT(1) NOT NULL DEFAULT 0,
		provisioned TINYINT(1) NOT NULL DEFAULT 0,
		last_seen DATETIME NULL DEFAULT NULL,
		wordpress_api_url VARCHAR(255) DEFAULT '',
		settings LONGTEXT NULL,
		canBill TINYINT(1) NOT NULL DEFAULT 0,
		created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
		updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
		UNIQUE KEY uq_machine_id (machine_id),
		UNIQUE KEY uq_unit_id (unit_id),
		PRIMARY KEY (id)
	) $charset_collate;";
	dbDelta($sql);

	// Provisioned devices (authoritative)
	$sql = "CREATE TABLE {$wpdb->prefix}tmon_provisioned_devices (
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
	) $charset_collate;";
	dbDelta($sql);

	// Notifications
	$sql = "CREATE TABLE {$wpdb->prefix}tmon_notifications (
		id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
		title VARCHAR(255) NOT NULL,
		message LONGTEXT NULL,
		level VARCHAR(32) NOT NULL DEFAULT 'info',
		created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
		read_at DATETIME NULL,
		PRIMARY KEY (id),
		KEY idx_created (created_at),
		KEY idx_read (read_at)
	) $charset_collate;";
	dbDelta($sql);

	// Companies hierarchy
	$sql = "CREATE TABLE {$wpdb->prefix}tmon_companies (
		id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
		name VARCHAR(191) NOT NULL,
		slug VARCHAR(191) NOT NULL,
		created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
		PRIMARY KEY (id),
		UNIQUE KEY uniq_slug (slug),
		KEY idx_created (created_at)
	) $charset_collate;";
	dbDelta($sql);

	// OTA jobs (with action)
	$sql = "CREATE TABLE {$wpdb->prefix}tmon_ota_jobs (
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
	) $charset_collate;";
	dbDelta($sql);

	// Commands/history tables (idempotent)
	tmon_admin_ensure_commands_table();
	tmon_admin_ensure_history_table();

	// Ensure device columns referenced by UI
	tmon_admin_ensure_columns($wpdb->prefix . 'tmon_devices', [
		'wordpress_api_url' => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN wordpress_api_url VARCHAR(255) DEFAULT ''",
		'last_seen'         => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN last_seen DATETIME NULL DEFAULT NULL",
		'canBill'           => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN canBill TINYINT(1) NOT NULL DEFAULT 0",
	]);

	// Hub shared key
	if (!get_option('tmon_admin_uc_key')) {
		update_option('tmon_admin_uc_key', wp_generate_password(32, false, false));
	}

	do_action('tmon_admin_install_schema_after');
}

if (!function_exists('tmon_admin_column_exists')) {
	function tmon_admin_column_exists($table, $column) {
		global $wpdb;
		if (!$wpdb || empty($wpdb->prefix)) return false;
		return (bool) $wpdb->get_var($wpdb->prepare("SHOW COLUMNS FROM {$table} LIKE %s", $column));
	}
}

function tmon_admin_ensure_columns($table, $columns) {
	global $wpdb;
	if (!$wpdb || empty($wpdb->prefix)) return false;
	foreach ($columns as $col => $sql) {
		if (!tmon_admin_column_exists($table, $col)) {
			$wpdb->query($sql);
		}
	}
	return true;
}

function tmon_admin_ensure_commands_table() {
	global $wpdb;
	$collate = $wpdb->get_charset_collate();
	$wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_device_commands (
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
	) {$collate}");
}

function tmon_admin_ensure_history_table() {
	global $wpdb;
	$collate = $wpdb->get_charset_collate();
	$wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_provision_history (
		id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
		unit_id VARCHAR(64) NOT NULL,
		machine_id VARCHAR(64) NOT NULL,
		action VARCHAR(64) NOT NULL,
		user VARCHAR(191) NULL,
		meta LONGTEXT NULL,
		created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
		PRIMARY KEY (id),
		KEY unit_machine (unit_id, machine_id),
		KEY action_idx (action)
	) {$collate}");
}

// Silent ensures during admin_init
add_action('admin_init', function(){
	// Run ensures silently each admin load
	tmon_admin_ensure_commands_table();
	tmon_admin_ensure_history_table();
});