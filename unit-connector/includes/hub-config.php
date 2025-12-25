<?php
if (!defined('ABSPATH')) exit;

// Default hub URL (tmon-admin site)
if (!function_exists('tmon_uc_get_default_hub_url')) {
	function tmon_uc_get_default_hub_url() {
		return 'https://tmonsystems.com';
	}
}

// Return canonical hub URL (constant override -> option -> default).
if (!function_exists('tmon_uc_get_hub_url')) {
	function tmon_uc_get_hub_url() {
		if (defined('TMON_HUB_URL') && TMON_HUB_URL) {
			return untrailingslashit(TMON_HUB_URL);
		}
		$opt = get_option('tmon_uc_hub_url', '');
		// If empty, set to default and persist
		if (empty($opt)) {
			$def = tmon_uc_get_default_hub_url();
			update_option('tmon_uc_hub_url', $def);
			return $def;
		}
		// Auto-correct deprecated hosts (movealong.us) -> default hub
		if (stripos($opt, 'movealong.us') !== false) {
			$def = tmon_uc_get_default_hub_url();
			update_option('tmon_uc_hub_url', $def);
			error_log("tmon-unit-connector: replaced deprecated hub URL '{$opt}' with '{$def}'.");
			add_action('admin_notices', function() use ($opt, $def) {
				if (!is_admin()) return;
				if (function_exists('current_user_can') && !current_user_can('manage_options')) return;
				echo '<div class="notice notice-warning"><p>TMON Unit Connector replaced deprecated hub URL "'.esc_html($opt).'" with "'.esc_html($def) . '". Verify your hub settings if necessary.</p></div>';
			});
			return $def;
		}
		return untrailingslashit($opt);
	}
}

if (!function_exists('tmon_uc_set_hub_url')) {
	function tmon_uc_set_hub_url($url) {
		$url = untrailingslashit(esc_url_raw($url));
		update_option('tmon_uc_hub_url', $url);
		error_log("tmon-unit-connector: hub URL explicitly set to {$url}");
	}
}

// Local admin key helper (constant override -> option -> empty)
if (!function_exists('tmon_uc_get_local_admin_key')) {
	function tmon_uc_get_local_admin_key() {
		if (defined('TMON_LOCAL_ADMIN_KEY') && TMON_LOCAL_ADMIN_KEY) return TMON_LOCAL_ADMIN_KEY;
		return get_option('tmon_uc_local_admin_key', '');
	}
}

// ------------------------
// Time helpers: parse & format MySQL DATETIME stored in WP site timezone
// ------------------------
if (!function_exists('tmon_uc_mysql_to_utc_timestamp')) {
	/**
	 * Convert a MySQL DATETIME string (stored using WP site timezone settings) into a UTC epoch timestamp.
	 * Returns 0 on failure.
	 *
	 * @param string|null $mysql_dt MySQL DATETIME (e.g., '2025-12-19 08:00:00').
	 * @return int UTC epoch seconds
	 */
	function tmon_uc_mysql_to_utc_timestamp($mysql_dt) {
		if (empty($mysql_dt)) return 0;
		$tz_string = get_option('timezone_string', '');
		// Prefer explicit timezone_string (DST-aware)
		if (!empty($tz_string)) {
			try {
				$dt = DateTime::createFromFormat('Y-m-d H:i:s', (string)$mysql_dt, new DateTimeZone($tz_string));
				if ($dt !== false) {
					return (int)$dt->getTimestamp();
				}
			} catch (Exception $e) {
				// fall through to gmt_offset fallback
			}
		}
		// Fallback: interpret as site-local using gmt_offset
		$offset_seconds = (int) round((float) get_option('gmt_offset', 0) * 3600);
		$ts = strtotime($mysql_dt);
		if ($ts === false) return 0;
		// strtotime likely interpreted the string in server timezone (often UTC),
		// so adjust by subtracting the site offset: ts_site_local => ts_utc = ts - offset_seconds
		return (int) ($ts - $offset_seconds);
	}
}

if (!function_exists('tmon_uc_format_mysql_datetime')) {
	/**
	 * Format a MySQL DATETIME (stored using WP site timezone) into a site-local string.
	 *
	 * @param string|null $mysql_dt
	 * @param string $format PHP date format (default uses WP date/time options)
	 * @return string formatted datetime or empty string
	 */
	function tmon_uc_format_mysql_datetime($mysql_dt = null, $format = null) {
		if (empty($mysql_dt)) return '';
		if ($format === null) $format = get_option('date_format') . ' ' . get_option('time_format');
		$ts = tmon_uc_mysql_to_utc_timestamp($mysql_dt);
		if (!$ts) return (string)$mysql_dt;
		return date_i18n($format, (int) $ts);
	}
}

// Ensure hub URL is canonical on admin_init (best-effort, non-destructive)
add_action('admin_init', function(){
	$current = get_option('tmon_uc_hub_url', '');
	$default = tmon_uc_get_default_hub_url();
	// If unset or deprecated host, set to canonical default
	if (empty($current) || stripos($current, 'movealong.us') !== false) {
		update_option('tmon_uc_hub_url', $default);
		error_log("tmon-unit-connector: ensured hub URL is {$default} (was '{$current}').");
	}
	// Lightweight AJAX diagnostics to help find failing admin-ajax requests
	if (defined('DOING_AJAX') && DOING_AJAX) {
		$act = isset($_REQUEST['action']) ? sanitize_text_field($_REQUEST['action']) : '';
		if ($act) {
			// Log only tmon-related requests to avoid noise
			if (stripos($act, 'tmon') === 0 || stripos($act, 'tmon_') === 0) {
				$method = $_SERVER['REQUEST_METHOD'] ?? 'POST';
				error_log("tmon-unit-connector: AJAX action '{$act}' invoked via {$method}. Refer to admin-ajax.php response for details.");
			}
		}
	}
});
