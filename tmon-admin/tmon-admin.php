<?php
/**
 * Plugin Name: TMON Admin
 * Description: Hub plugin (tmonsystems.com) - registry, provisioning, customers, firmware/OTA, exports.
 * Version: 0.1.0
 */

if (!defined('ABSPATH')) exit;

define('TMON_ADMIN_VERSION', '0.1.0');
define('TMON_ADMIN_DIR', __DIR__);
define('TMON_ADMIN_URL', plugin_dir_url(__FILE__));

// Load includes (keep require_once so existing modules can own behavior).
require_once TMON_ADMIN_DIR . '/includes/helpers.php';
require_once TMON_ADMIN_DIR . '/includes/schema.php';
require_once TMON_ADMIN_DIR . '/includes/db.php';
require_once TMON_ADMIN_DIR . '/includes/settings.php';
require_once TMON_ADMIN_DIR . '/includes/provisioning.php';
require_once TMON_ADMIN_DIR . '/includes/provisioned-devices.php';
require_once TMON_ADMIN_DIR . '/includes/firmware.php';
require_once TMON_ADMIN_DIR . '/includes/ota.php';
require_once TMON_ADMIN_DIR . '/includes/files.php';
require_once TMON_ADMIN_DIR . '/includes/export.php';
require_once TMON_ADMIN_DIR . '/includes/field-data-api.php';
require_once TMON_ADMIN_DIR . '/includes/groups.php';
require_once TMON_ADMIN_DIR . '/includes/commands.php';
require_once TMON_ADMIN_DIR . '/includes/command-logs.php';
require_once TMON_ADMIN_DIR . '/includes/notifications.php';
require_once TMON_ADMIN_DIR . '/includes/unit_connectors.php';
require_once TMON_ADMIN_DIR . '/includes/api.php';
require_once TMON_ADMIN_DIR . '/includes/api-uc.php';
require_once TMON_ADMIN_DIR . '/includes/ajax-handlers.php';
require_once TMON_ADMIN_DIR . '/includes/audit.php';
require_once TMON_ADMIN_DIR . '/includes/ai.php';
require_once TMON_ADMIN_DIR . '/includes/ai-feedback.php';
require_once TMON_ADMIN_DIR . '/includes/dashboard-widgets.php';
require_once TMON_ADMIN_DIR . '/includes/admin-dashboard.php';

// REST bootstrap (if routes exist in includes/api*.php they can hook themselves too)
add_action('rest_api_init', function () {
	if (function_exists('tmon_admin_register_rest_routes')) {
		tmon_admin_register_rest_routes();
	}
	if (function_exists('tmon_admin_register_uc_rest_routes')) {
		tmon_admin_register_uc_rest_routes();
	}
});

function tmon_admin_render_template(string $name): void {
	$path = TMON_ADMIN_DIR . '/templates/' . $name . '.php';
	if (file_exists($path)) {
		require $path;
		return;
	}
	echo '<div class="wrap"><h1>TMON Admin</h1><p>Missing template: ' . esc_html($name) . '</p></div>';
}

add_action('admin_menu', function () {
	add_menu_page(
		'TMON Admin',
		'TMON Admin',
		'manage_options',
		'tmon-admin',
		function () { tmon_admin_render_template('dashboard'); },
		'dashicons-admin-generic'
	);

	add_submenu_page('tmon-admin', 'Dashboard', 'Dashboard', 'manage_options', 'tmon-admin', function () {
		tmon_admin_render_template('dashboard');
	});

	add_submenu_page('tmon-admin', 'Provisioning', 'Provisioning', 'manage_options', 'tmon-admin-provisioning', function () {
		tmon_admin_render_template('provisioning');
	});

	add_submenu_page('tmon-admin', 'OTA', 'OTA', 'manage_options', 'tmon-admin-ota', function () {
		tmon_admin_render_template('ota');
	});

	add_submenu_page('tmon-admin', 'Field Data', 'Field Data', 'manage_options', 'tmon-admin-field-data', function () {
		tmon_admin_render_template('field-data');
	});

	add_submenu_page('tmon-admin', 'Export', 'Export', 'manage_options', 'tmon-admin-export', function () {
		tmon_admin_render_template('export');
	});

	add_submenu_page('tmon-admin', 'Groups', 'Groups', 'manage_options', 'tmon-admin-groups', function () {
		tmon_admin_render_template('groups');
	});

	add_submenu_page('tmon-admin', 'Files', 'Files', 'manage_options', 'tmon-admin-files', function () {
		tmon_admin_render_template('files');
	});

	add_submenu_page('tmon-admin', 'Notifications', 'Notifications', 'manage_options', 'tmon-admin-notifications', function () {
		tmon_admin_render_template('notifications');
	});

	add_submenu_page('tmon-admin', 'Audit', 'Audit', 'manage_options', 'tmon-admin-audit', function () {
		tmon_admin_render_template('audit');
	});

	add_submenu_page('tmon-admin', 'AI Feedback', 'AI Feedback', 'manage_options', 'tmon-admin-ai-feedback', function () {
		tmon_admin_render_template('ai-feedback');
	});

	add_submenu_page(
		'tmon-admin',
		'Customers',
		'Customers',
		'manage_options',
		'tmon-admin-customers',
		function () {
			require_once TMON_ADMIN_DIR . '/admin/customers.php';
			if (function_exists('tmon_admin_render_customers_page')) {
				tmon_admin_render_customers_page();
			} else {
				echo '<div class="wrap"><h1>Customers</h1><p>Customers page renderer missing.</p></div>';
			}
		}
	);
});
