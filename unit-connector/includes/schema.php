<?php
// DB schema for TMON organizational hierarchy and device data
// Call tmon_uc_install_schema() from the main plugin activation hook
function tmon_uc_install_schema() {
    global $wpdb;
    $charset_collate = $wpdb->get_charset_collate();

    // Field Data Table
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_field_data (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        unit_id VARCHAR(64),
        data LONGTEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    ) $charset_collate;");

    // Devices registry (duplicated here for fresh installs)
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_devices (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        unit_id VARCHAR(64) NOT NULL UNIQUE,
        machine_id VARCHAR(64) NULL UNIQUE,
        unit_name VARCHAR(128),
        company VARCHAR(128),
        site VARCHAR(128),
        zone VARCHAR(128),
        cluster VARCHAR(128),
        last_seen DATETIME,
        settings LONGTEXT,
        status LONGTEXT,
        suspended TINYINT(1) DEFAULT 0,
        PRIMARY KEY (id)
    ) $charset_collate;");

    // Lightweight upgrade: add machine_id column if missing on existing installs
    try {
        $table = $wpdb->prefix.'tmon_devices';
        $col = $wpdb->get_var($wpdb->prepare("SHOW COLUMNS FROM `$table` LIKE %s", 'machine_id'));
        if (!$col) {
            $wpdb->query("ALTER TABLE `$table` ADD COLUMN machine_id VARCHAR(64) NULL UNIQUE AFTER unit_id");
        }
    } catch (Exception $e) {
        // ignore if not supported
    }

    // OTA jobs
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_ota_jobs (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        unit_id VARCHAR(64) NOT NULL,
        job_type VARCHAR(64) NOT NULL,
        payload LONGTEXT,
        status VARCHAR(32) DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        completed_at DATETIME NULL
    ) $charset_collate;");

    // Device commands (for queued actions)
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_device_commands (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        device_id VARCHAR(64) NOT NULL,
        command VARCHAR(64) NOT NULL,
        params LONGTEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        executed_at DATETIME NULL
    ) $charset_collate;");

    // Company
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_company (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255),
        description TEXT,
        notes TEXT,
        address VARCHAR(255),
        gps_lat DOUBLE,
        gps_lng DOUBLE,
        timezone VARCHAR(64),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) $charset_collate;");

    // Site
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_site (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        company_id BIGINT UNSIGNED,
        name VARCHAR(255),
        description TEXT,
        notes TEXT,
        address VARCHAR(255),
        gps_lat DOUBLE,
        gps_lng DOUBLE,
        timezone VARCHAR(64),
        overhead_map_url VARCHAR(255),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (company_id) REFERENCES {$wpdb->prefix}tmon_company(id) ON DELETE CASCADE
    ) $charset_collate;");

    // Zone
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_zone (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        site_id BIGINT UNSIGNED,
        name VARCHAR(255),
        description TEXT,
        notes TEXT,
        address VARCHAR(255),
        gps_lat DOUBLE,
        gps_lng DOUBLE,
        timezone VARCHAR(64),
        overhead_map_url VARCHAR(255),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (site_id) REFERENCES {$wpdb->prefix}tmon_site(id) ON DELETE CASCADE
    ) $charset_collate;");

    // Cluster
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_cluster (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        zone_id BIGINT UNSIGNED,
        name VARCHAR(255),
        description TEXT,
        notes TEXT,
        address VARCHAR(255),
        gps_lat DOUBLE,
        gps_lng DOUBLE,
        timezone VARCHAR(64),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (zone_id) REFERENCES {$wpdb->prefix}tmon_zone(id) ON DELETE CASCADE
    ) $charset_collate;");

    // Unit
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_unit (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        cluster_id BIGINT UNSIGNED,
        name VARCHAR(255),
        description TEXT,
        notes TEXT,
        address VARCHAR(255),
        gps_lat DOUBLE,
        gps_lng DOUBLE,
        timezone VARCHAR(64),
        status VARCHAR(32),
        last_seen DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (cluster_id) REFERENCES {$wpdb->prefix}tmon_cluster(id) ON DELETE CASCADE
    ) $charset_collate;");

    // Audit
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_audit (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT UNSIGNED,
        action VARCHAR(255),
        details TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    ) $charset_collate;");
}

// Ensure core DB schema and upgrade-safe column additions for Unit Connector

if (!function_exists('tmon_admin_column_exists')) {
	function tmon_admin_column_exists($table, $column) {
		global $wpdb;
		if (!$wpdb || empty($wpdb->prefix)) return false;
		$col = $wpdb->get_var($wpdb->prepare("SHOW COLUMNS FROM {$table} LIKE %s", $column));
		return !empty($col);
	}
}

if (!function_exists('tmon_admin_ensure_columns')) {
	function tmon_admin_ensure_columns($table, $columns) {
		global $wpdb;
		if (!$wpdb || empty($wpdb->prefix)) return false;
		foreach ($columns as $col => $sql) {
			if (tmon_admin_column_exists($table, $col)) continue;
			$wpdb->query($sql);
		}
		return true;
	}
}

if (!function_exists('tmon_admin_ensure_commands_table')) {
	function tmon_admin_ensure_commands_table() {
		global $wpdb;
		if (!$wpdb || empty($wpdb->prefix)) return;
		$table = $wpdb->prefix . 'tmon_device_commands';
		$collate = $wpdb->get_charset_collate();
		$wpdb->query("CREATE TABLE IF NOT EXISTS {$table} (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			device_id VARCHAR(64) NOT NULL,
			command VARCHAR(64) NOT NULL,
			params LONGTEXT NULL,
			status VARCHAR(32) NOT NULL DEFAULT 'queued',
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			dispatched_at DATETIME NULL,
			executed_at DATETIME NULL,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
			PRIMARY KEY (id),
			KEY device_idx (device_id),
			KEY status_idx (status)
		) {$collate}");
	}
}

add_action('admin_init', function(){
	global $wpdb;
	if (!$wpdb || empty($wpdb->prefix)) return;
	// Ensure commands table exists with dispatched/executed timestamps
	tmon_admin_ensure_commands_table();

	// Ensure legacy installs get column additions when missing
	tmon_admin_ensure_columns($wpdb->prefix . 'tmon_device_commands', [
		'dispatched_at' => "ALTER TABLE {$wpdb->prefix}tmon_device_commands ADD COLUMN dispatched_at DATETIME NULL",
		'executed_at' => "ALTER TABLE {$wpdb->prefix}tmon_device_commands ADD COLUMN executed_at DATETIME NULL",
	]);

	// Ensure canBill column on tmon_devices
	tmon_admin_ensure_columns($wpdb->prefix . 'tmon_devices', [
		'canBill' => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN canBill TINYINT(1) NOT NULL DEFAULT 0",
	]);
});

// Ensure DB tables for UC extended features exist (idempotent)
function tmon_uc_ensure_tables() {
	global $wpdb;
	$coll = $wpdb->get_charset_collate();

	// LoRa snapshots for historical/trend views
	$tbl_snap = $wpdb->prefix . 'tmon_uc_lora_snapshots';
	$wpdb->query("
	CREATE TABLE IF NOT EXISTS {$tbl_snap} (
		id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
		unit_id VARCHAR(64) NOT NULL,
		ts DATETIME NOT NULL,
		payload LONGTEXT,
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		KEY (unit_id),
		KEY (ts)
	) {$coll};
	");

	// Remote shell logs (appendable chunks)
	$tbl_shell = $wpdb->prefix . 'tmon_uc_shell_logs';
	$wpdb->query("
	CREATE TABLE IF NOT EXISTS {$tbl_shell} (
		id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
		unit_id VARCHAR(64) NOT NULL,
		job_id VARCHAR(128) DEFAULT '',
		seq INT DEFAULT 0,
		chunk LONGTEXT,
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		KEY (unit_id),
		KEY (job_id),
		KEY (seq)
	) {$coll};
	");

	// Customer & location model (for backfilled data from Admin)
	$tbl_customer = $wpdb->prefix . 'tmon_customers';
	$wpdb->query("
	CREATE TABLE IF NOT EXISTS {$tbl_customer} (
		id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
		name VARCHAR(255) NOT NULL,
		meta LONGTEXT,
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP NULL DEFAULT NULL
	) {$coll};
	");

	$tbl_location = $wpdb->prefix . 'tmon_customer_locations';
	$wpdb->query("
	CREATE TABLE IF NOT EXISTS {$tbl_location} (
		id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
		customer_id BIGINT UNSIGNED NOT NULL,
		name VARCHAR(255),
		lat DOUBLE,
		lng DOUBLE,
		address TEXT,
		uc_site_url VARCHAR(255) DEFAULT '',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		updated_at TIMESTAMP NULL DEFAULT NULL,
		KEY (customer_id),
		KEY (uc_site_url)
	) {$coll};
	");

	// Zones & device groups for UC local grouping
	$tbl_zone = $wpdb->prefix . 'tmon_uc_zones';
	$wpdb->query("
	CREATE TABLE IF NOT EXISTS {$tbl_zone} (
		id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
		uc_site_url VARCHAR(255) DEFAULT '',
		location_id BIGINT UNSIGNED DEFAULT 0,
		name VARCHAR(255) DEFAULT '',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		KEY (uc_site_url),
		KEY (location_id)
	) {$coll};
	");

	$tbl_group = $wpdb->prefix . 'tmon_uc_device_groups';
	$wpdb->query("
	CREATE TABLE IF NOT EXISTS {$tbl_group} (
		id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
		uc_site_url VARCHAR(255) DEFAULT '',
		zone_id BIGINT UNSIGNED DEFAULT 0,
		name VARCHAR(255) DEFAULT '',
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		KEY (uc_site_url),
		KEY (zone_id)
	) {$coll};
	");

	$tbl_assign = $wpdb->prefix . 'tmon_uc_group_assignments';
	$wpdb->query("
	CREATE TABLE IF NOT EXISTS {$tbl_assign} (
		id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
		group_id BIGINT UNSIGNED NOT NULL,
		unit_id VARCHAR(64) NOT NULL,
		created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
		KEY (group_id),
		KEY (unit_id)
	) {$coll};
	");
}

// Provide legacy alias used by some admin pages
if (!function_exists('uc_devices_ensure_table')) {
	function uc_devices_ensure_table() {
		tmon_uc_ensure_tables();
	}
}
