<?php
// TMON Admin Helpers

function tmon_admin_silence(callable $cb) {
	ob_start();
	$prev = null;
	if (isset($GLOBALS['wpdb'])) {
		$prev = $GLOBALS['wpdb']->suppress_errors();
		$GLOBALS['wpdb']->suppress_errors(true);
	}
	try { $cb(); } finally {
		if ($prev !== null) { $GLOBALS['wpdb']->suppress_errors($prev); }
		ob_end_clean();
	}
}

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
	if (empty($table)) return false;
	return (bool) $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $table));
}

function tmon_admin_column_exists($table, $column) {
	global $wpdb;
	if (empty($table) || empty($column)) return false;
	return (bool) $wpdb->get_var($wpdb->prepare("SHOW COLUMNS FROM `$table` LIKE %s", $column));
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

// Nonce verifier used by legacy admin pages
function tmon_admin_verify_nonce($action, $field = '_wpnonce') {
	if (empty($_REQUEST[$field])) return false;
	return (bool) wp_verify_nonce(sanitize_text_field(wp_unslash($_REQUEST[$field])), $action);
}

function tmon_admin_once($key) {
	static $done = [];
	if (isset($done[$key])) return false;
	$done[$key] = true;
	return true;
}