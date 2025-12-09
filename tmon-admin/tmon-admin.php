<?php
/**
 * Plugin Name: TMON Admin
 * Description: Admin dashboard and management tools for TMON Unit Connector and IoT devices.
 * Version: 0.2.0
 * Author: TMON DevOps
 */
/*
README (minimal)

Key endpoints (tmon-admin/v1):
- GET /status — Health check.

Hooks used by Unit Connector:
- filter tmon_admin_authorize_device ($allowed, $unit_id, $machine_id): Return false to block device posts.
- action tmon_admin_receive_field_data ($unit_id, $record): Receive normalized field data for admin workflows.

Provisioning:
- Database table: wp_tmon_provisioned_devices (unit_id, machine_id, company_id, plan, status, notes).
- Admin UI: TMON Admin → Provisioning.
*/

// Ensure ABSPATH is defined
if (!defined('ABSPATH')) exit;

// Define required plugin constants early (fix: undefined constant)
if (!defined('TMON_ADMIN_VERSION')) {
	define('TMON_ADMIN_VERSION', '0.2.0');
}
if (!defined('TMON_ADMIN_PATH')) {
	define('TMON_ADMIN_PATH', plugin_dir_path(__FILE__));
}
if (!defined('TMON_ADMIN_URL')) {
	define('TMON_ADMIN_URL', plugin_dir_url(__FILE__));
}

// Declare this plugin as the master owner of the TMON Admin menu
if (!defined('TMON_ADMIN_MASTER_MENU')) {
	define('TMON_ADMIN_MASTER_MENU', true);
}

// Includes
require_once TMON_ADMIN_PATH . 'includes/db.php';
require_once TMON_ADMIN_PATH . 'includes/admin-dashboard.php';
require_once TMON_ADMIN_PATH . 'includes/settings.php';
require_once TMON_ADMIN_PATH . 'includes/api.php';
require_once TMON_ADMIN_PATH . 'includes/ajax-handlers.php';
require_once TMON_ADMIN_PATH . 'includes/cli-commands.php';
require_once TMON_ADMIN_PATH . 'includes/provisioning.php';
require_once TMON_ADMIN_PATH . 'includes/ai.php';
require_once TMON_ADMIN_PATH . 'includes/audit.php';
require_once TMON_ADMIN_PATH . 'includes/api-uc.php';
require_once TMON_ADMIN_PATH . 'includes/notifications.php';
require_once TMON_ADMIN_PATH . 'includes/ota.php';
require_once TMON_ADMIN_PATH . 'includes/files.php';
require_once TMON_ADMIN_PATH . 'includes/groups.php';
require_once TMON_ADMIN_PATH . 'includes/custom-code.php';
require_once TMON_ADMIN_PATH . 'includes/export.php';
require_once TMON_ADMIN_PATH . 'includes/ai-feedback.php';
require_once TMON_ADMIN_PATH . 'includes/dashboard-widgets.php';
require_once TMON_ADMIN_PATH . 'includes/field-data-api.php';
require_once TMON_ADMIN_PATH . 'admin/location.php';
require_once TMON_ADMIN_PATH . 'admin/firmware.php';

// Activation ensures schema
if (!has_action('activate_' . plugin_basename(__FILE__))) {
	register_activation_hook(__FILE__, function () {
		if (function_exists('tmon_admin_install_schema')) {
			tmon_admin_install_schema();
		}
		update_option('tmon_admin_version', TMON_ADMIN_VERSION);
	});
}

// Upgrade path
add_action('plugins_loaded', function () {
	$stored = get_option('tmon_admin_version');
	if ($stored !== TMON_ADMIN_VERSION) {
		if (function_exists('tmon_admin_install_schema')) {
			tmon_admin_install_schema();
		}
		update_option('tmon_admin_version', TMON_ADMIN_VERSION);
	}
});

// Assets
add_action('admin_enqueue_scripts', function () {
	wp_enqueue_style('tmon-admin', TMON_ADMIN_URL . 'assets/admin.css', [], TMON_ADMIN_VERSION);
	wp_enqueue_script('tmon-admin', TMON_ADMIN_URL . 'assets/admin.js', ['jquery'], TMON_ADMIN_VERSION, true);
	wp_localize_script('tmon-admin', 'TMON_ADMIN', [
		'ajaxUrl' => admin_url('admin-ajax.php'),
		'nonce'   => wp_create_nonce('tmon-admin'),
		'restRoot' => esc_url_raw(rest_url()),
		'restNonce' => wp_create_nonce('wp_rest'),
		'manifestNonce' => wp_create_nonce('tmon_admin_manifest'),
		'provisionNonce' => wp_create_nonce('tmon_admin_provision_ajax'),
	]);
});

// Primary TMON Admin menu (single owner)
if (!has_action('admin_menu', 'tmon_admin_menu')) {
	add_action('admin_menu', 'tmon_admin_menu');
	function tmon_admin_menu() {
		// Mark we have registered the main menu to prevent any other registrar from adding another top-level
		if (!defined('TMON_ADMIN_HAVE_MAIN_MENU')) define('TMON_ADMIN_HAVE_MAIN_MENU', true);

		$menu_title = 'TMON Admin';
		add_menu_page('TMON Admin', $menu_title, 'manage_options', 'tmon-admin', 'tmon_admin_dashboard_page', 'dashicons-admin-generic', 58);

		add_submenu_page('tmon-admin', 'Settings', 'Settings', 'manage_options', 'tmon-admin-settings', 'tmon_admin_settings_page');
		add_submenu_page('tmon-admin', 'Audit Log', 'Audit Log', 'manage_options', 'tmon-admin-audit', 'tmon_admin_audit_page');
		add_submenu_page('tmon-admin', 'Notifications', 'Notifications', 'manage_options', 'tmon-admin-notifications', 'tmon_admin_notifications_page');
		add_submenu_page('tmon-admin', 'OTA Jobs', 'OTA Jobs', 'manage_options', 'tmon-admin-ota', 'tmon_admin_ota_page');
		add_submenu_page('tmon-admin', 'Files', 'Files', 'manage_options', 'tmon-admin-files', 'tmon_admin_files_page');
		add_submenu_page('tmon-admin', 'Groups', 'Groups', 'manage_options', 'tmon-admin-groups', 'tmon_admin_groups_page');

		add_submenu_page('tmon-admin', 'Provisioning', 'Provisioning', 'manage_options', 'tmon-admin-provisioning', 'tmon_admin_provisioning_page');
		add_submenu_page('tmon-admin', 'Provisioned Devices', 'Provisioned Devices', 'manage_options', 'tmon-admin-provisioned', 'tmon_admin_provisioned_devices_page');
		add_submenu_page('tmon-admin', 'Provisioning Activity', 'Provisioning Activity', 'manage_options', 'tmon-admin-provisioning-activity', 'tmon_admin_provisioning_activity_page');
		add_submenu_page('tmon-admin', 'Provisioning History', 'Provisioning History', 'manage_options', 'tmon-admin-provisioning-history', 'tmon_admin_provisioning_history_page');

		// Move Command Logs under TMON Admin
		add_submenu_page('tmon-admin', 'Command Logs', 'Command Logs', 'manage_options', 'tmon-admin-command-logs', function(){
			do_action('tmon_admin_render_command_logs');
		});
	}
}

// Remove any stray standalone top-level Command Logs menu registered elsewhere
add_action('admin_menu', function(){
	remove_menu_page('tmon-admin-command-logs');
}, 999);

// Ensure schema present on admin_init (silent)
add_action('admin_init', function () {
	if (function_exists('tmon_admin_install_schema')) {
		ob_start();
		tmon_admin_install_schema();
		@ob_end_clean();
	}
});
