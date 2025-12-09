<?php
// TMON Admin Helpers

function tmon_admin_safe_prepare($sql, $args = []) {
	global $wpdb;
	// Only prepare when placeholders are present.
	if (strpos($sql, '%') !== false && !empty($args)) {
		return $wpdb->prepare($sql, $args);
	}
	return $sql;
}

function tmon_admin_table_exists($table) {
	global $wpdb;
	$table = esc_sql($table);
	$sql = "SHOW TABLES LIKE %s";
	$found = $wpdb->get_var($wpdb->prepare($sql, $table));
	return !empty($found);
}

function tmon_admin_column_exists($table, $column) {
	global $wpdb;
	$table = esc_sql($table);
	$column = esc_sql($column);
	$sql = "SHOW COLUMNS FROM `$table` LIKE %s";
	$found = $wpdb->get_var($wpdb->prepare($sql, $column));
	return !empty($found);
}

function tmon_admin_normalize_url($url) {
	$url = trim((string)$url);
	if ($url === '') return '';
	$parts = wp_parse_url($url);
	if (!$parts) return $url;
	$scheme = isset($parts['scheme']) ? $parts['scheme'] : 'https';
	$host = strtolower($parts['host'] ?? '');
	$path = rtrim($parts['path'] ?? '', '/');
	return $scheme . '://' . $host . $path;
}

function tmon_admin_once($key) {
	static $done = [];
	if (isset($done[$key])) return false;
	$done[$key] = true;
	return true;
}

// ...existing code...