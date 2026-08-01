<?php
// DB schema for TMON organizational hierarchy and device data
// Call tmon_uc_install_schema() from the main plugin activation hook

if (!function_exists('tmon_uc_ensure_schema')) {
function tmon_uc_ensure_schema() {
	global $wpdb;
	require_once ABSPATH . 'wp-admin/includes/upgrade.php';
	$charset = $wpdb->get_charset_collate();

	$devices = $wpdb->prefix . 'tmon_devices';
	$commands = $wpdb->prefix . 'tmon_device_commands';

	$sql_devices = "CREATE TABLE {$devices} (
		id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
		unit_id varchar(64) NOT NULL,
		machine_id varchar(128) DEFAULT '',
		unit_name varchar(255) DEFAULT '',
		role varchar(32) DEFAULT '',
		node_type varchar(32) DEFAULT '',
		company varchar(255) DEFAULT '',
		site varchar(255) DEFAULT '',
		zone varchar(255) DEFAULT '',
		cluster varchar(255) DEFAULT '',
		suspended tinyint(1) NOT NULL DEFAULT 0,
		last_seen datetime DEFAULT NULL,
		settings longtext,
		status longtext,
		registered_at datetime DEFAULT NULL,
		updated_at datetime DEFAULT NULL,
		PRIMARY KEY  (id),
		UNIQUE KEY unit_id (unit_id),
		KEY machine_id (machine_id),
		KEY role (role),
		KEY node_type (node_type)
	) {$charset};";

	$sql_commands = "CREATE TABLE {$commands} (
		id bigint(20) unsigned NOT NULL AUTO_INCREMENT,
		device_id varchar(64) NOT NULL,
		command varchar(64) NOT NULL,
		params longtext,
		status varchar(32) NOT NULL DEFAULT 'queued',
		created_at datetime DEFAULT NULL,
		updated_at datetime DEFAULT NULL,
		executed_at datetime DEFAULT NULL,
		result longtext,
		PRIMARY KEY  (id),
		KEY device_status (device_id, status),
		KEY updated_at (updated_at)
	) {$charset};";

	dbDelta($sql_devices);
	dbDelta($sql_commands);

	$dcols = $wpdb->get_col("DESCRIBE {$devices}", 0);
	if (is_array($dcols) && !in_array('role', $dcols, true)) {
		$wpdb->query("ALTER TABLE {$devices} ADD COLUMN role varchar(32) DEFAULT '' AFTER unit_name");
	}
	if (is_array($dcols) && !in_array('node_type', $dcols, true)) {
		$wpdb->query("ALTER TABLE {$devices} ADD COLUMN node_type varchar(32) DEFAULT '' AFTER role");
	}
	if (is_array($dcols) && !in_array('registered_at', $dcols, true)) {
		$wpdb->query("ALTER TABLE {$devices} ADD COLUMN registered_at datetime DEFAULT NULL AFTER settings");
	}
	if (is_array($dcols) && !in_array('updated_at', $dcols, true)) {
		$wpdb->query("ALTER TABLE {$devices} ADD COLUMN updated_at datetime DEFAULT NULL AFTER registered_at");
	}

	$ccols = $wpdb->get_col("DESCRIBE {$commands}", 0);
	if (is_array($ccols) && !in_array('status', $ccols, true)) {
		$wpdb->query("ALTER TABLE {$commands} ADD COLUMN status varchar(32) NOT NULL DEFAULT 'queued' AFTER params");
	}
	if (is_array($ccols) && !in_array('updated_at', $ccols, true)) {
		$wpdb->query("ALTER TABLE {$commands} ADD COLUMN updated_at datetime DEFAULT NULL AFTER created_at");
	}
	if (is_array($ccols) && !in_array('executed_at', $ccols, true)) {
		$wpdb->query("ALTER TABLE {$commands} ADD COLUMN executed_at datetime DEFAULT NULL AFTER updated_at");
	}
	if (is_array($ccols) && !in_array('result', $ccols, true)) {
		$wpdb->query("ALTER TABLE {$commands} ADD COLUMN result longtext AFTER executed_at");
	}

	$wpdb->query("UPDATE {$devices} SET role = node_type WHERE (role IS NULL OR role = '') AND node_type <> ''");
	$wpdb->query("UPDATE {$devices} SET role = 'remote' WHERE (role IS NULL OR role = '')");

	update_option('tmon_uc_schema_version', '2.0.5', false);
}}

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
		status VARCHAR(32) DEFAULT 'queued',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
		updated_at DATETIME NULL,
        executed_at DATETIME NULL
		result LONGTEXT,
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

	// Ensure current live schema matches what the code expects.
	tmon_uc_ensure_schema();
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
