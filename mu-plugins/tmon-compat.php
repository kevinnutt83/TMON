<?php
// Minimal early mu-plugin to avoid early warnings/fatals when bootstrap ordering is odd.

if (!defined('TMON_COMPAT_MU_LOADED')) {
	define('TMON_COMPAT_MU_LOADED', true);

	// Ensure common login globals exist so wp-login.php won't emit "Undefined variable" warnings.
	// (wp-login.php can run very early; mu-plugins load before regular plugins.)
	if (!isset($GLOBALS['user_login'])) $GLOBALS['user_login'] = '';
	if (!isset($GLOBALS['user_pass']))  $GLOBALS['user_pass']  = '';

	// Also ensure short-named globals so legacy code using $user_login / $user_pass directly won't warn.
	if (!isset($user_login)) $user_login = $GLOBALS['user_login'];
	if (!isset($user_pass))  $user_pass  = $GLOBALS['user_pass'];

	// --- EARLY PLUGGABLE FALLBACKS ---
	// Provide tiny stubs for wp_get_current_user() / get_current_user_id() so calls to current_user_can()
	// during very early bootstrap (before WP pluggables load) do not fatal. These are conservative
	// no-op implementations that will be replaced by core once pluggables are loaded.
	if (!function_exists('wp_get_current_user')) {
		if (!class_exists('TMON_Fallback_User')) {
			class TMON_Fallback_User {
				public $ID = 0;
				public $roles = [];
				public $user_login = '';
				public $user_email = '';
				public function has_cap($cap) { return false; }
				public function exists() { return false; }
				public function __get($name) { return null; }
			}
		}
		function wp_get_current_user() {
			static $u = null;
			if ($u === null) $u = new TMON_Fallback_User();
			return $u;
		}
	}
	if (!function_exists('get_current_user_id')) {
		function get_current_user_id() {
			if (function_exists('wp_get_current_user')) {
				$user = wp_get_current_user();
				return isset($user->ID) ? intval($user->ID) : 0;
			}
			return 0;
		}
	}
	// --- END FALLBACKS ---

	// If some other code set a broken current_user object (missing exists()), clear it so WP can construct WP_User as normal.
	$clear_if_broken = function() {
		if (isset($GLOBALS['current_user']) && is_object($GLOBALS['current_user']) && !method_exists($GLOBALS['current_user'], 'exists')) {
			$GLOBALS['current_user'] = null;
		}
	};

	// Run immediately and re-check early in bootstrap in case another plugin sets the broken object later.
	$clear_if_broken();
	add_action('plugins_loaded', $clear_if_broken, 0);
	add_action('init', $clear_if_broken, 0);
	add_action('admin_init', $clear_if_broken, 0);

	// One-time cleanup of stale transients/options that may cause repeated bootstrap issues.
	// Best-effort: remove transients/options with tmon_uc prefix and a helper transient used by the plugin.
	if (! get_option('tmon_compat_transients_cleared', false) ) {
		global $wpdb;
		// Remove transients named _transient_tmon_uc_* and _site_transient_tmon_uc_*
		$like1 = $wpdb->esc_like('_transient_tmon_uc_') . '%';
		$like2 = $wpdb->esc_like('_site_transient_tmon_uc_') . '%';
		$wpdb->query( $wpdb->prepare("DELETE FROM {$wpdb->options} WHERE option_name LIKE %s", $like1) );
		$wpdb->query( $wpdb->prepare("DELETE FROM {$wpdb->options} WHERE option_name LIKE %s", $like2) );
		// Specific commonly-used transient
		@delete_transient('tmon_uc_devices_dirty');
		// Mark as cleared so we don't repeat this on every mu-plugin load
		update_option('tmon_compat_transients_cleared', current_time('mysql'));
	}
}
