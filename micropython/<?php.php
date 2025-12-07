<?php

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
	if (function_exists('tmon_admin_ensure_commands_table')) {
		tmon_admin_ensure_commands_table();
	}
	// Ensure canBill only once
	tmon_admin_ensure_columns($wpdb->prefix . 'tmon_devices', [
		'canBill' => "ALTER TABLE {$wpdb->prefix}tmon_devices ADD COLUMN canBill TINYINT(1) NOT NULL DEFAULT 0",
	]);
});