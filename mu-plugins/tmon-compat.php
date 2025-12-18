<?php
// Minimal compatibility shim to avoid fatal when a TMON_Fallback_User lacks exists().

/* Clear broken global immediately if present */
if (isset($GLOBALS['current_user']) && is_object($GLOBALS['current_user']) && !method_exists($GLOBALS['current_user'], 'exists')) {
	$GLOBALS['current_user'] = null;
}

/* Ensure determine_current_user never returns a TMON_Fallback_User (run very early) */
add_filter('determine_current_user', function($user) {
	if (is_object($user) && is_a($user, 'TMON_Fallback_User')) {
		return 0;
	}
	return $user;
}, 1);

/* Ensure wp_get_current_user() always returns an object with exists() */
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

/* Re-check after other plugins load and on init in case the broken object is set later */
add_action('plugins_loaded', function() {
	if (isset($GLOBALS['current_user']) && is_object($GLOBALS['current_user']) && !method_exists($GLOBALS['current_user'], 'exists')) {
		$GLOBALS['current_user'] = null;
	}
}, 0);
add_action('init', function() {
	if (isset($GLOBALS['current_user']) && is_object($GLOBALS['current_user']) && !method_exists($GLOBALS['current_user'], 'exists')) {
		$GLOBALS['current_user'] = null;
	}
}, 0);
