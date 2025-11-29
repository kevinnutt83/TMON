<?php
/**
 * Plugin Name: TMON Admin
 * Description: Admin dashboard and management tools for TMON Unit Connector and IoT devices.
 * Version: 1.0.0
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

// Define plugin constants before requiring files (fixes undefined constant error)
if (!defined('TMON_ADMIN_VERSION')) {
	define('TMON_ADMIN_VERSION', '0.1.2');
}
if (!defined('TMON_ADMIN_PATH')) {
	define('TMON_ADMIN_PATH', plugin_dir_path(__FILE__));
}
if (!defined('TMON_ADMIN_URL')) {
	define('TMON_ADMIN_URL', plugin_dir_url(__FILE__));
}

// Guard include loader to prevent accidental redeclare.
if (!function_exists('tmon_admin_include_files')) {
	function tmon_admin_include_files() {
		require_once TMON_ADMIN_PATH . 'includes/db.php';
		require_once TMON_ADMIN_PATH . 'includes/admin-dashboard.php';
		require_once TMON_ADMIN_PATH . 'includes/settings.php';
		require_once TMON_ADMIN_PATH . 'includes/api.php';

		// Centralized AJAX handlers & CLI diagnostics
		require_once TMON_ADMIN_PATH . 'includes/ajax-handlers.php';
		require_once TMON_ADMIN_PATH . 'includes/cli-commands.php';

		require_once TMON_ADMIN_PATH . 'includes/provisioning.php';
		require_once TMON_ADMIN_PATH . 'includes/ai.php';
		require_once TMON_ADMIN_PATH . 'includes/audit.php';
		require_once TMON_ADMIN_PATH . 'includes/notifications.php';
		require_once TMON_ADMIN_PATH . 'includes/ota.php';
		require_once TMON_ADMIN_PATH . 'includes/files.php';
		require_once TMON_ADMIN_PATH . 'includes/groups.php';
		require_once TMON_ADMIN_PATH . 'includes/custom-code.php';
		require_once TMON_ADMIN_PATH . 'includes/export.php';
		require_once TMON_ADMIN_PATH . 'includes/ai-feedback.php';
		require_once TMON_ADMIN_PATH . 'includes/dashboard-widgets.php';
		require_once TMON_ADMIN_PATH . 'includes/field-data-api.php';
		// Admin pages
		require_once TMON_ADMIN_PATH . 'admin/location.php';
		require_once TMON_ADMIN_PATH . 'admin/firmware.php';
	}
}
tmon_admin_include_files();

// NOTE: centralize AJAX/CLI handlers via includes/ajax-handlers.php and includes/cli-commands.php
// The following sections previously defined the same AJAX handlers repeatedly in this file.
// They have been removed in favor of the centralized handlers to avoid redeclaration errors.
// If you need to inspect old handlers, check the centralized includes: includes/ajax-handlers.php

// --- Helpers: key normalization + single-definition guard ---
if (!function_exists('tmon_admin_normalize_key')) {
	function tmon_admin_normalize_key($key) {
		if (!is_string($key)) return '';
		return strtolower(trim($key));
	}
}

// Ensure provisioning page callbacks exist so submenu callbacks are valid
if (!function_exists('tmon_admin_provisioned_devices_page')) {
	function tmon_admin_provisioned_devices_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		global $wpdb;
		$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
		$dev_table = $wpdb->prefix . 'tmon_devices';

		echo '<div class="wrap"><h1>Provisioned Devices (Admin)</h1>';
		$rows = [];
		if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $prov_table))) {
			$rows = $wpdb->get_results("SELECT * FROM {$prov_table} ORDER BY created_at DESC", ARRAY_A);
		}
		if (empty($rows)) {
			echo '<p><em>No local provisioned devices found.</em></p>';
		} else {
			echo '<table class="widefat"><thead><tr><th>Unit ID</th><th>Machine ID</th><th>Unit Name</th><th>Site URL</th><th>Status</th><th>Created</th><th>Updated</th></tr></thead><tbody>';
			foreach ($rows as $r) {
				echo '<tr><td>'.esc_html($r['unit_id'] ?? '').'</td><td>'.esc_html($r['machine_id'] ?? '').'</td><td>'.esc_html($r['unit_name'] ?? '').'</td><td>'.esc_html($r['site_url'] ?? '').'</td><td>'.esc_html($r['status'] ?? '').'</td><td>'.esc_html($r['created_at'] ?? '').'</td><td>'.esc_html($r['updated_at'] ?? '').'</td></tr>';
			}
			echo '</tbody></table>';
		}
		echo '</div>';
	}
}

if (!function_exists('tmon_admin_provisioning_activity_page')) {
	function tmon_admin_provisioning_activity_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		$queue = get_option('tmon_admin_pending_provision', []);
		$history = get_option('tmon_admin_provision_history', []);
		echo '<div class="wrap"><h1>Provisioning Activity</h1>';
		echo '<h2>Pending Queue</h2>';
		echo '<table class="widefat"><thead><tr><th>Key</th><th>Payload</th><th>Queued</th><th>Actions</th></tr></thead><tbody>';
		if (!empty($queue) && is_array($queue)) {
			foreach ($queue as $k=>$p) {
				echo '<tr>';
				echo '<td>'.esc_html($k).'</td>';
				echo '<td><pre>'.esc_html(wp_json_encode($p, JSON_PRETTY_PRINT)).'</pre></td>';
				echo '<td>'.esc_html($p['requested_at'] ?? '').'</td>';
				echo '<td><button class="button tmon-pq-reenqueue" data-key="'.esc_attr($k).'">Re-enqueue</button> <button class="button tmon-pq-delete" data-key="'.esc_attr($k).'">Delete</button></td>';
				echo '</tr>';
			}
		} else {
			echo '<tr><td colspan="4"><em>No pending queue entries.</em></td></tr>';
		}
		echo '</tbody></table>';

		echo '<h2>History</h2>';
		echo '<table class="widefat"><thead><tr><th>Time</th><th>User</th><th>Unit</th><th>Machine</th><th>Action</th><th>Meta</th></tr></thead><tbody>';
		if (is_array($history) && !empty($history)) {
			foreach (array_reverse($history) as $h) {
				echo '<tr>';
				echo '<td>'.esc_html($h['ts'] ?? '').'</td>';
				echo '<td>'.esc_html($h['user'] ?? '').'</td>';
				echo '<td>'.esc_html($h['unit_id'] ?? '').'</td>';
				echo '<td>'.esc_html($h['machine_id'] ?? '').'</td>';
				echo '<td>'.esc_html($h['action'] ?? 'saved').'</td>';
				echo '<td><pre>'.esc_html(wp_json_encode($h['meta'] ?? [], JSON_PRETTY_PRINT)).'</pre></td>';
				echo '</tr>';
			}
		} else {
			echo '<tr><td colspan="6"><em>No history recorded.</em></td></tr>';
		}
		echo '</tbody></table>';

		$nonce = wp_create_nonce('tmon_admin_provision_ajax');
		$ajaxurl = admin_url('admin-ajax.php');
		echo "<script>
			(function($){
				$('.tmon-pq-delete').on('click', function(){ const k=$(this).data('key'); if(!confirm('Delete '+k+'?'))return; $.post('{$ajaxurl}', {action:'tmon_admin_manage_pending', manage_action:'delete', key:k, _ajax_nonce:'{$nonce}'}, function(r){ if(r.success) location.reload(); else alert('Failed'); }); });
				$('.tmon-pq-reenqueue').on('click', function(){ const k=$(this).data('key'); const p=prompt('Payload JSON or empty to keep existing:'); $.post('{$ajaxurl}', {action:'tmon_admin_manage_pending', manage_action:'reenqueue', key:k, payload:p, _ajax_nonce:'{$nonce}'}, function(r){ if(r.success) location.reload(); else alert('Failed'); }); });
			})(jQuery);
		</script>";

		echo '</div>';
	}
}

// These admin page callbacks remain in this file (non-AJAX):
// - tmon_admin_menu / admin pages
// - tmon_admin_provisioning_activity_page
// - tmon_admin_provisioned_devices_page
// etc.
// (unchanged)