<?php
// Minimal early mu-plugin to avoid fatal when a TMON_Fallback_User lacks exists().

if (!defined('TMON_COMPAT_MU_LOADED')) {
	define('TMON_COMPAT_MU_LOADED', true);

	// Clear any broken global immediately.
	if (isset($GLOBALS['current_user']) && is_object($GLOBALS['current_user']) && !method_exists($GLOBALS['current_user'], 'exists')) {
		$GLOBALS['current_user'] = null;
	}

	// Prevent determine_current_user from returning a broken TMON_Fallback_User.
	add_filter('determine_current_user', function($user) {
		if (is_object($user) && is_a($user, 'TMON_Fallback_User')) {
			return 0;
		}
		return $user;
	}, 1);

	// Ensure wp_get_current_user() returns an object with exists().
	add_filter('wp_get_current_user', function($user) {
		if (is_object($user) && !method_exists($user, 'exists')) {
			if (class_exists('WP_User')) {
				return new WP_User(0);
			}
			if (!class_exists('TMON_User_Compat_Stub')) {
				class TMON_User_Compat_Stub { public function exists() { return false; } }
			}
			return new TMON_User_Compat_Stub();
		}
		return $user;
	}, 1);

	// Re-check in case another plugin sets the broken object later.
	$clear_if_broken = function() {
		if (isset($GLOBALS['current_user']) && is_object($GLOBALS['current_user']) && !method_exists($GLOBALS['current_user'], 'exists')) {
			$GLOBALS['current_user'] = null;
		}
	};
	add_action('plugins_loaded', $clear_if_broken, 0);
	add_action('init', $clear_if_broken, 0);
	add_action('admin_init', $clear_if_broken, 0);
}
