<?php
if (!defined('ABSPATH')) exit;

// ...new file...

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
		// Auto-correct known incorrect host (movealong.us) -> default
		if (stripos($opt, 'movealong.us') !== false) {
			$def = tmon_uc_get_default_hub_url();
			update_option('tmon_uc_hub_url', $def);
			error_log("tmon-unit-connector: replaced deprecated hub URL '{$opt}' with '{$def}'.");
			add_action('admin_notices', function() use ($opt, $def) {
				if (!is_admin()) return;
				if (function_exists('current_user_can') && !current_user_can('manage_options')) return;
				echo '<div class="notice notice-warning"><p>TMON Unit Connector: detected deprecated hub URL "'.esc_html($opt).'" and switched to "'.esc_html($def).'". Verify your hub settings under the plugin settings.</p></div>';
			});
			return $def;
		}
		return untrailingslashit($opt);
	}
}

// Local admin key helper (constant override -> option -> empty)
if (!function_exists('tmon_uc_get_local_admin_key')) {
	function tmon_uc_get_local_admin_key() {
		if (defined('TMON_LOCAL_ADMIN_KEY') && TMON_LOCAL_ADMIN_KEY) return TMON_LOCAL_ADMIN_KEY;
		return get_option('tmon_uc_local_admin_key', '');
	}
}
