<?php
// ...existing code...

function tmon_admin_install_schema() {
	global $wpdb;
	$charset_collate = $wpdb->get_charset_collate();
	$devices = $wpdb->prefix . 'tmon_devices';

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

	// Ensure additional columns exist for features that reference them.
	tmon_admin_ensure_columns($wpdb->prefix . 'tmon_devices', [
		'unit_name'   => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN unit_name VARCHAR(100) DEFAULT NULL",
		'company'     => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN company VARCHAR(191) DEFAULT NULL",
		'site'        => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN site VARCHAR(191) DEFAULT NULL",
		'zone'        => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN zone VARCHAR(191) DEFAULT NULL",
		'cluster'     => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN cluster VARCHAR(191) DEFAULT NULL",
		'suspended'   => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN suspended TINYINT(1) NOT NULL DEFAULT 0",
		'provisioned' => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN provisioned TINYINT(1) NOT NULL DEFAULT 0",
		'last_seen'   => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN last_seen DATETIME NULL DEFAULT NULL",
		'settings'    => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN settings LONGTEXT NULL",
	]);

	// Generate Hub shared key if missing.
	if (!get_option('tmon_admin_uc_key')) {
		update_option('tmon_admin_uc_key', wp_generate_password(32, false, false));
	}

	// Allow other modules (provisioning, claims, etc.) to install their own schemas.
	do_action('tmon_admin_install_schema_after');
}

// Guard utility to avoid future redeclare warnings if included twice somewhere.
if (!function_exists('tmon_admin_generate_unique_unit_id')) {
	function tmon_admin_generate_unique_unit_id() {
		global $wpdb;
		$table = $wpdb->prefix . 'tmon_devices';
		for ($i = 0; $i < 20; $i++) {
			$unit_id = str_pad((string) random_int(0, 999999), 6, '0', STR_PAD_LEFT);
			$exists = (int) $wpdb->get_var($wpdb->prepare("SELECT COUNT(1) FROM {$table} WHERE unit_id = %s", $unit_id));
			if ($exists === 0) {
				return $unit_id;
			}
		}
		return strtoupper(wp_generate_password(6, false, false));
	}
}

// Provide a fallback implementation for tmon_admin_ensure_columns so activation doesn't fail
if (!function_exists('tmon_admin_ensure_columns')) {
	function tmon_admin_ensure_columns() {
		global $wpdb;
		$table = $wpdb->prefix . 'tmon_provisioned_devices';
		$exists = $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table));
		if (!$exists) return false;

		$cols = $wpdb->get_results("SHOW COLUMNS FROM $table", ARRAY_A);
		$have = [];
		foreach (($cols ?: []) as $c) {
			$have[strtolower($c['Field'])] = true;
		}

		$required = [
			'role' => "ALTER TABLE $table ADD COLUMN role VARCHAR(32) DEFAULT 'base'",
			'company_id' => "ALTER TABLE $table ADD COLUMN company_id BIGINT UNSIGNED NULL",
			'plan' => "ALTER TABLE $table ADD COLUMN plan VARCHAR(64) DEFAULT 'standard'",
			'status' => "ALTER TABLE $table ADD COLUMN status VARCHAR(32) DEFAULT 'active'",
			'notes' => "ALTER TABLE $table ADD COLUMN notes TEXT",
			'created_at' => "ALTER TABLE $table ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP",
			'updated_at' => "ALTER TABLE $table ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP",
			'site_url' => "ALTER TABLE $table ADD COLUMN site_url VARCHAR(255) DEFAULT ''",
			'unit_name' => "ALTER TABLE $table ADD COLUMN unit_name VARCHAR(128) DEFAULT ''",
			'firmware' => "ALTER TABLE $table ADD COLUMN firmware VARCHAR(128) DEFAULT ''",
			'firmware_url' => "ALTER TABLE $table ADD COLUMN firmware_url VARCHAR(255) DEFAULT ''",
			'settings_staged' => "ALTER TABLE $table ADD COLUMN settings_staged TINYINT(1) DEFAULT 0",
			'machine_id_norm' => "ALTER TABLE $table ADD COLUMN machine_id_norm VARCHAR(64) DEFAULT ''",
			'unit_id_norm' => "ALTER TABLE $table ADD COLUMN unit_id_norm VARCHAR(64) DEFAULT ''",
		];

		foreach ($required as $col => $sql) {
			if (empty($have[$col])) {
				$wpdb->query($sql);
				if ($col === 'updated_at') {
					// add ON UPDATE if the column was just created
					$wpdb->query("ALTER TABLE $table MODIFY COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP");
				}
			}
		}

		// Ensure unique index on (unit_id, machine_id)
		$indexes = $wpdb->get_results("SHOW INDEX FROM $table", ARRAY_A);
		$hasUnitMachineIdx = false;
		foreach (($indexes?:[]) as $idx) {
			if (isset($idx['Key_name']) && $idx['Key_name'] === 'unit_machine') {
				$hasUnitMachineIdx = true;
				break;
			}
		}
		if (!$hasUnitMachineIdx) {
			$colsCheck = $wpdb->get_col("SHOW COLUMNS FROM $table LIKE 'unit_id'");
			$colsCheck2 = $wpdb->get_col("SHOW COLUMNS FROM $table LIKE 'machine_id'");
			if (!empty($colsCheck) && !empty($colsCheck2)) {
				$wpdb->query("ALTER TABLE $table ADD UNIQUE KEY unit_machine (unit_id, machine_id)");
			}
		}

		error_log('tmon-admin: ensured provisioning columns and normalized fields.');
		return true;
	}
}

// ...existing code...