<?php
// Minimal early mu-plugin to avoid early warnings/fatals when bootstrap ordering is odd.

if (!defined('TMON_COMPAT_MU_LOADED')) {
	define('TMON_COMPAT_MU_LOADED', true);

	// Ensure common login globals exist so wp-login.php won't emit "Undefined variable" warnings.
	if (!isset($GLOBALS['user_login'])) $GLOBALS['user_login'] = '';
	if (!isset($GLOBALS['user_pass']))  $GLOBALS['user_pass']  = '';

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
}
