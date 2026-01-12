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
	// Ensure pluggable is loaded; on some early includes it may not be
	if (!function_exists('wp_verify_nonce') && defined('ABSPATH')) {
		@include_once ABSPATH . WPINC . '/pluggable.php';
	}
	if (empty($_REQUEST[$field])) return false;
	return (bool) wp_verify_nonce(sanitize_text_field(wp_unslash($_REQUEST[$field])), $action);
}

function tmon_admin_once($key) {
	static $done = [];
	if (isset($done[$key])) return false;
	$done[$key] = true;
	return true;
}

if (!defined('ABSPATH')) exit;

function tmon_admin_customers_option_name(): string {
	return 'tmon_admin_customers_v1';
}

function tmon_admin_get_customers(): array {
	$cs = get_option(tmon_admin_customers_option_name(), []);
	return is_array($cs) ? array_values($cs) : [];
}

function tmon_admin_upsert_customer(array $c): array {
	$cs = get_option(tmon_admin_customers_option_name(), []);
	if (!is_array($cs)) $cs = [];

	$id = sanitize_text_field((string)($c['id'] ?? ''));
	if ($id === '') {
		$id = 'cust_' . wp_generate_uuid4();
	}

	$cs[$id] = [
		'id' => $id,
		'name' => sanitize_text_field((string)($c['name'] ?? '')),
		'unit_connector_url' => esc_url_raw((string)($c['unit_connector_url'] ?? '')),
		'updated_at' => time(),
	];

	update_option(tmon_admin_customers_option_name(), $cs, false);
	return $cs[$id];
}

function tmon_admin_delete_customer(string $id): bool {
	$id = sanitize_text_field($id);
	$cs = get_option(tmon_admin_customers_option_name(), []);
	if (!is_array($cs) || !isset($cs[$id])) return false;
	unset($cs[$id]);
	update_option(tmon_admin_customers_option_name(), $cs, false);
	return true;
}