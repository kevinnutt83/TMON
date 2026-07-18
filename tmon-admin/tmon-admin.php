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
require_once TMON_ADMIN_PATH . 'includes/helpers.php';
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
require_once TMON_ADMIN_PATH . 'includes/provisioned-devices.php';
require_once TMON_ADMIN_PATH . 'includes/firmware.php';
require_once TMON_ADMIN_PATH . 'includes/custom-code.php';
require_once TMON_ADMIN_PATH . 'includes/export.php';
require_once TMON_ADMIN_PATH . 'includes/ai-feedback.php';
require_once TMON_ADMIN_PATH . 'includes/dashboard-widgets.php';
require_once TMON_ADMIN_PATH . 'includes/field-data-api.php';
require_once TMON_ADMIN_PATH . 'admin/location.php';
require_once TMON_ADMIN_PATH . 'admin/uc-deploy.php';
require_once TMON_ADMIN_PATH . 'admin/firmware.php';

// Wire menu actions to page renderers (separate from menu registration)
if (!function_exists('tmon_admin_dashboard_page_render')) {
	function tmon_admin_dashboard_page_render() {
		if (!current_user_can('manage_options')) { wp_die('Forbidden'); }
		global $wpdb;
		$devices_total = 0;
		$provisioned_total = 0;
		$queued_total = 0;
		$diagnostics_total = 0;
		$recent_diagnostics = [];

		$dev_table = $wpdb->prefix . 'tmon_devices';
		$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
		$history = get_option('tmon_admin_provision_history', []);
		if (!is_array($history)) {
			$history = [];
		}

		$has_dev = (bool) $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $dev_table));
		$has_prov = (bool) $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $prov_table));
		if ($has_dev) {
			$devices_total = (int) $wpdb->get_var("SELECT COUNT(*) FROM {$dev_table}");
		}
		if ($has_prov) {
			$provisioned_total = (int) $wpdb->get_var("SELECT COUNT(*) FROM {$prov_table} WHERE provisioned = 1 OR status = 'active'");
			$queued_total = (int) $wpdb->get_var("SELECT COUNT(*) FROM {$prov_table} WHERE status IN ('queued','staged','pending')");
		}

		$diag_store = get_option('tmon_admin_device_diagnostics', []);
		if (!is_array($diag_store)) {
			$diag_store = [];
		}
		$diagnostics_total = count($diag_store);
		$recent_diagnostics = array_values($diag_store);
		usort($recent_diagnostics, function ($a, $b) {
			$ta = isset($a['received_at']) ? strtotime((string) $a['received_at']) : 0;
			$tb = isset($b['received_at']) ? strtotime((string) $b['received_at']) : 0;
			return $tb <=> $ta;
		});
		$recent_diagnostics = array_slice($recent_diagnostics, 0, 5);

		echo '<div class="wrap"><h1>TMON Admin</h1>';
		echo '<p class="description">Manage provisioning, firmware, notifications, and Unit Connector tooling from this dashboard.</p>';
		echo '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:14px 0 18px;max-width:980px;">';
		echo '<div class="postbox" style="padding:10px 12px;"><div style="font-size:12px;color:#50575e;">Registered Devices</div><div style="font-size:24px;font-weight:600;">' . intval($devices_total) . '</div></div>';
		echo '<div class="postbox" style="padding:10px 12px;"><div style="font-size:12px;color:#50575e;">Provisioned</div><div style="font-size:24px;font-weight:600;">' . intval($provisioned_total) . '</div></div>';
		echo '<div class="postbox" style="padding:10px 12px;"><div style="font-size:12px;color:#50575e;">Queued/Staged</div><div style="font-size:24px;font-weight:600;">' . intval($queued_total) . '</div></div>';
		echo '<div class="postbox" style="padding:10px 12px;"><div style="font-size:12px;color:#50575e;">Diagnostics Records</div><div style="font-size:24px;font-weight:600;">' . intval($diagnostics_total) . '</div></div>';
		echo '<div class="postbox" style="padding:10px 12px;"><div style="font-size:12px;color:#50575e;">Provision History</div><div style="font-size:24px;font-weight:600;">' . intval(count($history)) . '</div></div>';
		echo '</div>';

		echo '<h2 style="margin-top:0;">Recent Diagnostics</h2>';
		echo '<table class="widefat striped" style="max-width:980px;"><thead><tr><th>Unit</th><th>Received</th><th>Node</th><th>Error Count</th><th>Last Error</th></tr></thead><tbody>';
		if ($recent_diagnostics) {
			foreach ($recent_diagnostics as $diag) {
				echo '<tr>';
				echo '<td>' . esc_html((string) ($diag['unit_id'] ?? '')) . '</td>';
				echo '<td>' . esc_html((string) ($diag['received_at'] ?? '')) . '</td>';
				echo '<td>' . esc_html((string) ($diag['node_type'] ?? '')) . '</td>';
				echo '<td>' . intval($diag['error_count'] ?? 0) . '</td>';
				echo '<td>' . esc_html((string) ($diag['last_error'] ?? '')) . '</td>';
				echo '</tr>';
			}
		} else {
			echo '<tr><td colspan="5"><em>No diagnostics received yet.</em></td></tr>';
		}
		echo '</tbody></table>';

		echo '<h2>Quick Links</h2>';
		echo '<ul class="tmon-quick-links">';
		echo '<li><a href="' . esc_url(admin_url('admin.php?page=tmon-admin-provisioning')) . '">Provisioning</a></li>';
		echo '<li><a href="' . esc_url(admin_url('admin.php?page=tmon-admin-firmware')) . '">Firmware</a></li>';
		echo '<li><a href="' . esc_url(admin_url('admin.php?page=tmon-admin-ota')) . '">OTA Jobs</a></li>';
		echo '<li><a href="' . esc_url(admin_url('admin.php?page=tmon-admin-provisioned')) . '">Provisioned Devices</a></li>';
		echo '<li><a href="' . esc_url(admin_url('admin.php?page=tmon-admin-diagnostics')) . '">Diagnostics</a></li>';
		echo '<li><a href="' . esc_url(admin_url('admin.php?page=tmon-admin-settings')) . '">Settings</a></li>';
		echo '</ul>';
		echo '</div>';
	}
}

// Map custom actions used by the menu to their render callbacks
$tmon_admin_page_actions = [
	'tmon_admin_dashboard_page' => 'tmon_admin_dashboard_page_render',
	'tmon_admin_settings_page' => 'tmon_admin_settings_page',
	'tmon_admin_audit_page' => 'tmon_admin_audit_page',
	'tmon_admin_notifications_page' => 'tmon_admin_notifications_page',
	'tmon_admin_ota_page' => 'tmon_admin_ota_page',
	'tmon_admin_files_page' => 'tmon_admin_files_page',
	'tmon_admin_groups_page' => 'tmon_admin_groups_page',
	'tmon_admin_provisioning_page' => 'tmon_admin_provisioning_page',
	'tmon_admin_provisioning_activity_page' => 'tmon_admin_provisioning_activity_page',
	'tmon_admin_provisioning_history_page' => 'tmon_admin_provisioning_history_page',
	'tmon_admin_provisioned_devices_page' => 'tmon_admin_provisioned_devices_page',
	'tmon_admin_diagnostics_page' => 'tmon_admin_diagnostics_page',
	'tmon_admin_command_logs_page' => 'tmon_admin_command_logs_page',
];
foreach ($tmon_admin_page_actions as $hook => $callback) {
	if (function_exists($callback) && !has_action($hook, $callback)) {
		add_action($hook, $callback);
	}
}

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

// Primary TMON Admin menu (single owner; balanced parentheses/syntax)
add_action('admin_menu', function () {
	// Prevent duplicate top-level menu
	if (defined('TMON_ADMIN_HAVE_MAIN_MENU')) {
		return;
	}
	define('TMON_ADMIN_HAVE_MAIN_MENU', true);

	add_menu_page(
		'TMON Admin',
		'TMON Admin',
		'manage_options',
		'tmon-admin',
		function () { do_action('tmon_admin_dashboard_page'); },
		'dashicons-admin-generic',
		58
	);

	add_submenu_page('tmon-admin', 'Settings', 'Settings', 'manage_options', 'tmon-admin-settings', function () {
		do_action('tmon_admin_settings_page');
	});
	add_submenu_page('tmon-admin', 'Audit Log', 'Audit Log', 'manage_options', 'tmon-admin-audit', function () {
		do_action('tmon_admin_audit_page');
	});
	add_submenu_page('tmon-admin', 'Notifications', 'Notifications', 'manage_options', 'tmon-admin-notifications', function () {
		do_action('tmon_admin_notifications_page');
	});
	add_submenu_page('tmon-admin', 'Firmware', 'Firmware', 'manage_options', 'tmon-admin-firmware', function () {
		do_action('tmon_admin_firmware_page');
	});
	add_submenu_page('tmon-admin', 'OTA Jobs', 'OTA Jobs', 'manage_options', 'tmon-admin-ota', function () {
		do_action('tmon_admin_ota_page');
	});
	add_submenu_page('tmon-admin', 'Files', 'Files', 'manage_options', 'tmon-admin-files', function () {
		do_action('tmon_admin_files_page');
	});
	add_submenu_page('tmon-admin', 'Groups', 'Groups', 'manage_options', 'tmon-admin-groups', function () {
		do_action('tmon_admin_groups_page');
	});
	add_submenu_page('tmon-admin', 'Provisioning', 'Provisioning', 'manage_options', 'tmon-admin-provisioning', function () {
		do_action('tmon_admin_provisioning_page');
	});
	add_submenu_page('tmon-admin', 'Provisioned Devices', 'Provisioned Devices', 'manage_options', 'tmon-admin-provisioned', function () {
		do_action('tmon_admin_provisioned_devices_page');
	});
	add_submenu_page('tmon-admin', 'Diagnostics', 'Diagnostics', 'manage_options', 'tmon-admin-diagnostics', function () {
		do_action('tmon_admin_diagnostics_page');
	});
	add_submenu_page('tmon-admin', 'Provisioning Activity', 'Provisioning Activity', 'manage_options', 'tmon-admin-provisioning-activity', function () {
		do_action('tmon_admin_provisioning_activity_page');
	});
	add_submenu_page('tmon-admin', 'Provisioning History', 'Provisioning History', 'manage_options', 'tmon-admin-provisioning-history', function () {
		do_action('tmon_admin_provisioning_history_page');
	});
	add_submenu_page('tmon-admin', 'Command Logs', 'Command Logs', 'manage_options', 'tmon-admin-command-logs', function () {
		do_action('tmon_admin_command_logs_page');
	});
}, 9);

// Remove any stray standalone Command Logs top-level page
add_action('admin_menu', function () {
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

// Register activation/deactivation hooks to schedule/unschedule a cron event
if (!function_exists('tmon_admin_activate')) {
	register_activation_hook(__FILE__, 'tmon_admin_activate');
	function tmon_admin_activate() {
		if (!wp_next_scheduled('tmon_admin_hourly_event')) {
			wp_schedule_event(time(), 'hourly', 'tmon_admin_hourly_event');
		}
	}

	register_deactivation_hook(__FILE__, 'tmon_admin_deactivate');
	function tmon_admin_deactivate() {
		$ts = wp_next_scheduled('tmon_admin_hourly_event');
		if ($ts) wp_unschedule_event($ts, 'tmon_admin_hourly_event');
	}

	// Cron handler (lightweight housekeeping)
	add_action('tmon_admin_hourly_event', 'tmon_admin_hourly_handler');
	function tmon_admin_hourly_handler() {
		$sites = get_option('tmon_admin_uc_sites', []);
		if (!is_array($sites)) $sites = [];
		update_option('tmon_admin_hourly_last_run', time());
		update_option('tmon_admin_uc_sites_count', count($sites));
	}
}
