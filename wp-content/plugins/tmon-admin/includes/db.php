<?php
// ...existing code...

function tmon_admin_db_ensure() {
	global $wpdb;
	require_once ABSPATH . 'wp-admin/includes/upgrade.php';
	$charset = $wpdb->get_charset_collate();
	$prefix = $wpdb->prefix;

	// Notifications
	$notifications = "{$prefix}tmon_notifications";
	if (!tmon_admin_table_exists($notifications)) {
		dbDelta("CREATE TABLE $notifications (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			title VARCHAR(255) NOT NULL,
			message LONGTEXT NULL,
			level VARCHAR(32) NOT NULL DEFAULT 'info',
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			read_at DATETIME NULL,
			PRIMARY KEY (id),
			KEY idx_created (created_at),
			KEY idx_read (read_at)
		) $charset;");
	}

	// OTA jobs
	$ota = "{$prefix}tmon_ota_jobs";
	if (!tmon_admin_table_exists($ota)) {
		dbDelta("CREATE TABLE $ota (
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
		) $charset;");
	} else {
		if (!tmon_admin_column_exists($ota, 'action')) {
			$wpdb->query("ALTER TABLE $ota ADD COLUMN action VARCHAR(64) NOT NULL AFTER unit_id");
		}
		if (!tmon_admin_column_exists($ota, 'updated_at')) {
			$wpdb->query("ALTER TABLE $ota ADD COLUMN updated_at DATETIME NULL AFTER created_at");
			$wpdb->query("UPDATE $ota SET updated_at = created_at WHERE updated_at IS NULL");
		}
	}

	// Companies hierarchy
	$companies = "{$prefix}tmon_companies";
	if (!tmon_admin_table_exists($companies)) {
		dbDelta("CREATE TABLE $companies (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			name VARCHAR(191) NOT NULL,
			slug VARCHAR(191) NOT NULL,
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			PRIMARY KEY (id),
			UNIQUE KEY uniq_slug (slug),
			KEY idx_created (created_at)
		) $charset;");
	}

	// Device commands columns
	$commands = "{$prefix}tmon_device_commands";
	if (tmon_admin_table_exists($commands)) {
		if (!tmon_admin_column_exists($commands, 'status')) {
			$wpdb->query("ALTER TABLE $commands ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'staged'");
			$wpdb->query("UPDATE $commands SET status = 'staged' WHERE status IS NULL OR status = ''");
		}
		if (!tmon_admin_column_exists($commands, 'updated_at')) {
			$wpdb->query("ALTER TABLE $commands ADD COLUMN updated_at DATETIME NULL AFTER created_at");
			$wpdb->query("UPDATE $commands SET updated_at = created_at WHERE updated_at IS NULL");
		}
	}

	// UC mirror table (for paired connectors)
	$uc = "{$prefix}tmon_uc_sites";
	if (!tmon_admin_table_exists($uc)) {
		dbDelta("CREATE TABLE $uc (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			site_url VARCHAR(255) NOT NULL,
			normalized_url VARCHAR(255) NOT NULL,
			hub_key VARCHAR(191) NULL,
			read_token VARCHAR(191) NULL,
			last_seen DATETIME NULL,
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			PRIMARY KEY (id),
			UNIQUE KEY uniq_norm (normalized_url),
			KEY idx_last_seen (last_seen)
		) $charset;");
	}
}

// ...existing code...