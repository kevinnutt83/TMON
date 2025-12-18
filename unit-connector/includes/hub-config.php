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
