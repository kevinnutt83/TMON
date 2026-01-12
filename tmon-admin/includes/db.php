<?php
if (!defined('ABSPATH')) exit;

/**
 * NOTE:
 * tmon_admin_install_schema() must be defined only in includes/schema.php.
 * If this file currently defines it too (the cause of the fatal), delete that duplicate
 * or keep it guarded as below.
 */
if (!function_exists('tmon_admin_install_schema')) {
	function tmon_admin_install_schema() {
		// Delegate to schema.php implementation if it exists there under another name,
		// otherwise keep empty to avoid redeclare fatals.
		if (function_exists('tmon_admin_install_schema_impl')) {
			return tmon_admin_install_schema_impl();
		}
		return null;
	}
}

// Silent ensures during admin_init
add_action('admin_init', function(){
	// Run ensures silently each admin load
	tmon_admin_ensure_commands_table();
	tmon_admin_ensure_history_table();
});