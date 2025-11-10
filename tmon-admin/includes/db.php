<?php
// ...existing code...

function tmon_admin_install_schema() {
	global $wpdb;
	$charset_collate = $wpdb->get_charset_collate();

	$devices = $wpdb->prefix . 'tmon_devices';

	// Full schema with columns referenced by code (company, site, zone, cluster, suspended).
	$sql = "CREATE TABLE {$devices} (
		id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
		machine_id VARCHAR(64) NOT NULL,
		unit_id VARCHAR(6) NOT NULL,
		unit_name VARCHAR(100) DEFAULT NULL,
		company VARCHAR(191) DEFAULT NULL,
		site VARCHAR(191) DEFAULT NULL,
		zone VARCHAR(191) DEFAULT NULL,
		cluster VARCHAR(191) DEFAULT NULL,
		suspended TINYINT(1) NOT NULL DEFAULT 0,
		provisioned TINYINT(1) NOT NULL DEFAULT 0,
		created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
		updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
		UNIQUE KEY uq_machine_id (machine_id),
		UNIQUE KEY uq_unit_id (unit_id),
		PRIMARY KEY  (id)
	) $charset_collate;";

	require_once ABSPATH . 'wp-admin/includes/upgrade.php';
	dbDelta($sql);

	// Defensive: ensure columns exist even if older installs missed dbDelta additions.
	tmon_admin_ensure_columns($devices, [
		'unit_name' => "ALTER TABLE {$devices} ADD COLUMN unit_name VARCHAR(100) DEFAULT NULL",
		'company'   => "ALTER TABLE {$devices} ADD COLUMN company VARCHAR(191) DEFAULT NULL",
		'site'      => "ALTER TABLE {$devices} ADD COLUMN site VARCHAR(191) DEFAULT NULL",
		'zone'      => "ALTER TABLE {$devices} ADD COLUMN zone VARCHAR(191) DEFAULT NULL",
		'cluster'   => "ALTER TABLE {$devices} ADD COLUMN cluster VARCHAR(191) DEFAULT NULL",
		'suspended' => "ALTER TABLE {$devices} ADD COLUMN suspended TINYINT(1) NOT NULL DEFAULT 0",
		'provisioned' => "ALTER TABLE {$devices} ADD COLUMN provisioned TINYINT(1) NOT NULL DEFAULT 0",
	]);
}

function tmon_admin_ensure_columns($table, $ddl_by_column) {
	global $wpdb;
	$existing = $wpdb->get_col("SHOW COLUMNS FROM {$table}", 0);
	if (!is_array($existing)) {
		return;
	}
	foreach ($ddl_by_column as $col => $ddl) {
		if (!in_array($col, $existing, true)) {
			$wpdb->query($ddl);
		}
	}
}

/**
 * Generate a unique 6-digit UNIT_ID string (zero-padded).
 */
function tmon_admin_generate_unique_unit_id() {
	global $wpdb;
	$devices = $wpdb->prefix . 'tmon_devices';
	for ($i = 0; $i < 20; $i++) {
		$unit_id = str_pad((string) random_int(0, 999999), 6, '0', STR_PAD_LEFT);
		$exists = (int) $wpdb->get_var($wpdb->prepare("SELECT COUNT(1) FROM {$devices} WHERE unit_id = %s", $unit_id));
		if ($exists === 0) {
			return $unit_id;
		}
	}
	// Fallback in the unlikely case of collisions.
	return strtoupper(wp_generate_password(6, false, false));
}

// ...existing code...