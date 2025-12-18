<?php
// Minimal early mu-plugin to avoid fatal when a TMON_Fallback_User lacks exists().

if (!defined('TMON_COMPAT_MU_LOADED')) {
	define('TMON_COMPAT_MU_LOADED', true);

	// Ensure common login globals exist so wp-login.php won't emit "Undefined variable" warnings.
	// (wp-login.php can run very early; mu-plugins load before regular plugins.)
	if (!isset($GLOBALS['user_login'])) $GLOBALS['user_login'] = '';
	if (!isset($GLOBALS['user_pass']))  $GLOBALS['user_pass']  = '';

	// Proxy that forwards to the original object but provides exists()
	if (!class_exists('TMON_User_Proxy')) {
		class TMON_User_Proxy {
			private $orig;
			public function __construct($orig) {
				$this->orig = $orig;
				// mirror properties so code reading props on global still works
				foreach (get_object_vars($orig) as $k => $v) { $this->$k = $v; }
			}
			// satisfies is_user_logged_in() / WP expectations
			public function exists() { return false; }
			public function __get($k) { return $this->orig->$k ?? null; }
			public function __set($k, $v) { $this->orig->$k = $v; $this->$k = $v; }
			public function __isset($k) { return isset($this->orig->$k); }
			public function __call($m, $a) {
				if (is_object($this->orig) && method_exists($this->orig, $m)) {
					return call_user_func_array([$this->orig, $m], $a);
				}
				return null;
			}
		}
	}

	// Fix function — replaces global current_user with a proxy if it's broken
	$fix_current_user_if_broken = function() {
		if (isset($GLOBALS['current_user']) && is_object($GLOBALS['current_user'])) {
			$u = $GLOBALS['current_user'];
			$needs = (is_a($u, 'TMON_Fallback_User') || !method_exists($u, 'exists'));
			if ($needs) {
				$GLOBALS['current_user'] = new TMON_User_Proxy($u);
			}
		}
	};

	// Run immediately and re-check early in bootstrap
	$fix_current_user_if_broken();
	add_action('plugins_loaded', $fix_current_user_if_broken, 0);
	add_action('init', $fix_current_user_if_broken, 0);
	add_action('admin_init', $fix_current_user_if_broken, 0);

	// Prevent determine_current_user from returning a TMON_Fallback_User
	add_filter('determine_current_user', function($user) {
		if (is_object($user) && is_a($user, 'TMON_Fallback_User')) return 0;
		return $user;
	}, 1);

	// Ensure wp_get_current_user() always returns an object with exists()
	add_filter('wp_get_current_user', function($user) {
		if (is_object($user) && !method_exists($user, 'exists')) {
			if (class_exists('WP_User')) return new WP_User(0);
			return new TMON_User_Proxy($user);
		}
		return $user;
	}, 1);
}
