<?php
/**
 * Plugin Name: TMON Admin
 * Description: Hub plugin (tmonsystems.com) - source of truth for customers, unit connectors, and device registry.
 * Version: 0.1.0
 */

if (!defined('ABSPATH')) exit;

define('TMON_ADMIN_VERSION', '0.1.0');
define('TMON_ADMIN_DIR', __DIR__);

require_once TMON_ADMIN_DIR . '/includes/helpers.php';
require_once TMON_ADMIN_DIR . '/includes/api.php';

add_action('rest_api_init', function () {
	if (function_exists('tmon_admin_register_rest_routes')) {
		tmon_admin_register_rest_routes();
	}
});

add_action('admin_menu', function () {
	add_menu_page(
		'TMON Admin',
		'TMON Admin',
		'manage_options',
		'tmon-admin',
		function () { echo '<div class="wrap"><h1>TMON Admin</h1><p>Use the submenu items.</p></div>'; },
		'dashicons-admin-generic'
	);

	add_submenu_page(
		'tmon-admin',
		'Customers',
		'Customers',
		'manage_options',
		'tmon-admin-customers',
		function () {
			require_once TMON_ADMIN_DIR . '/admin/customers.php';
			tmon_admin_render_customers_page();
		}
	);
});
