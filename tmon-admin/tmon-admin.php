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

// Define required plugin constants early (fix: undefined constant)
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
		require_once TMON_ADMIN_PATH . 'includes/api-uc.php'; // NEW: UC handoff & command endpoints
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

// Activation installs/updates DB schema + version.
if (!has_action('activate_' . plugin_basename(__FILE__))) {
	register_activation_hook(__FILE__, function () {
		if (function_exists('tmon_admin_install_schema')) {
			tmon_admin_install_schema();
		}
		update_option('tmon_admin_version', TMON_ADMIN_VERSION);
	});
}

// Upgrade path on version change.
add_action('plugins_loaded', function () {
	$stored = get_option('tmon_admin_version');
	if ($stored !== TMON_ADMIN_VERSION) {
		if (function_exists('tmon_admin_install_schema')) {
			tmon_admin_install_schema();
		}
		update_option('tmon_admin_version', TMON_ADMIN_VERSION);
	}
});

// Enqueue assets; fix localization ($l10n must be an array).
add_action('admin_enqueue_scripts', function () {
	wp_enqueue_style('tmon-admin', TMON_ADMIN_URL . 'assets/admin.css', [], TMON_ADMIN_VERSION);
	wp_enqueue_script('tmon-admin', TMON_ADMIN_URL . 'assets/admin.js', ['jquery'], TMON_ADMIN_VERSION, true);

	$localized = [
		'ajaxUrl' => admin_url('admin-ajax.php'),
		'nonce'   => wp_create_nonce('tmon-admin'),
		// Add REST root and a manifest fetch nonce for admin.js to call the REST endpoint directly
		'restRoot' => esc_url_raw( rest_url() ),
		'restNonce' => wp_create_nonce('wp_rest'),
		'manifestNonce' => wp_create_nonce('tmon_admin_manifest'),
		'provisionNonce' => wp_create_nonce('tmon_admin_provision_ajax'),
	];
	wp_localize_script('tmon-admin', 'TMON_ADMIN', $localized);
});

// Admin menu registration (keeps admin pages reachable)
if (!has_action('admin_menu', 'tmon_admin_menu')) {
	add_action('admin_menu', 'tmon_admin_menu');
	function tmon_admin_menu() {
		$notices = get_option('tmon_admin_notifications', []);
		$unread = 0;
		foreach ($notices as $n) { if (empty($n['read'])) $unread++; }
		$menu_title = 'TMON Admin' . ($unread ? ' <span class="update-plugins count-1" style="vertical-align:middle"><span class="plugin-count">'.intval($unread).'</span></span>' : '');

		add_menu_page(
			'TMON Admin',
			$menu_title,
			'manage_options',
			'tmon-admin',
			'tmon_admin_dashboard_page',
			'dashicons-admin-generic',
			2
		);

		add_submenu_page('tmon-admin', 'TMON Settings', 'Settings', 'manage_options', 'tmon-admin-settings', 'tmon_admin_settings_page');
		add_submenu_page('tmon-admin', 'Audit Log', 'Audit Log', 'manage_options', 'tmon-admin-audit', 'tmon_admin_audit_page');
		add_submenu_page('tmon-admin', 'Notifications', 'Notifications', 'manage_options', 'tmon-admin-notifications', 'tmon_admin_notifications_page');
		add_submenu_page('tmon-admin', 'OTA Jobs', 'OTA Jobs', 'manage_options', 'tmon-admin-ota', 'tmon_admin_ota_page');
		add_submenu_page('tmon-admin', 'Files', 'Files', 'manage_options', 'tmon-admin-files', 'tmon_admin_files_page');
		add_submenu_page('tmon-admin', 'Groups', 'Groups', 'manage_options', 'tmon-admin-groups', 'tmon_admin_groups_page');

		// Provisioning: top subpage with children
		add_submenu_page('tmon-admin', 'Provisioning', 'Provisioning', 'manage_options', 'tmon-admin-provisioning', 'tmon_admin_provisioning_page');
		add_submenu_page('tmon-admin', 'Provisioned Devices', 'Provisioned Devices', 'manage_options', 'tmon-admin-provisioned', 'tmon_admin_provisioned_devices_page');
		add_submenu_page('tmon-admin', 'Provisioning Activity', 'Provisioning Activity', 'manage_options', 'tmon-admin-provisioning-activity', 'tmon_admin_provisioning_activity_page');
		add_submenu_page('tmon-admin', 'Provisioning History', 'Provisioning History', 'manage_options', 'tmon-admin-provisioning-history', 'tmon_admin_provisioning_history_page');

		add_submenu_page('tmon-admin', 'Device Location', 'Device Location', 'manage_options', 'tmon-admin-location', 'tmon_admin_location_page');
		add_submenu_page('tmon-admin', 'UC Pairings', 'UC Pairings', 'manage_options', 'tmon-admin-pairings', 'tmon_admin_pairings_page');
	}
}

// Ensure schema is present before any UI/REST interaction
add_action('admin_init', function () {
	if (function_exists('tmon_admin_install_schema')) {
		tmon_admin_install_schema();
	}
});
add_action('rest_api_init', function () {
	if (function_exists('tmon_admin_install_schema')) {
		tmon_admin_install_schema();
	}
});

// Wire a minimal audit helper and call it in safe places (best-effort)
if (!function_exists('tmon_admin_audit_log')) {
	function tmon_admin_audit_log($action, $context = null, $args = array()) {
		global $wpdb;
		$table = $wpdb->prefix . 'tmon_admin_audit';
		// Ensure table exists
		if (!function_exists('tmon_admin_audit_ensure_tables')) return;
		tmon_admin_audit_ensure_tables();
		$row = array(
			'ts' => current_time('mysql'),
			'user_id' => get_current_user_id() ?: null,
			'action' => sanitize_text_field($action),
			'context' => $context ? sanitize_text_field($context) : null,
			'unit_id' => isset($args['unit_id']) ? sanitize_text_field($args['unit_id']) : null,
			'machine_id' => isset($args['machine_id']) ? sanitize_text_field($args['machine_id']) : null,
			'extra' => isset($args['extra']) ? wp_json_encode($args['extra']) : null,
		);
		$wpdb->insert($table, $row);
	}
}

// Safe wrappers for pages to avoid fatal errors when dependencies aren’t loaded
function tmon_admin_safe_card_open($title) {
	echo '<div class="card" style="padding:12px;margin-top:12px;"><h2 style="margin-top:0;">' . esc_html($title) . '</h2>';
}
function tmon_admin_safe_card_close() { echo '</div>'; }

// Firmware page: functional replacement using GitHub API (clickable version list and docs)
if (!function_exists('tmon_admin_firmware_page')) {
	function tmon_admin_firmware_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		// Repo config
		$repo = get_option('tmon_admin_repo', 'kevinnutt83/TMON');
		$branch = get_option('tmon_admin_repo_branch', 'main');
		$base_url = 'https://raw.githubusercontent.com/' . $repo . '/' . $branch . '/';
		$api_base = 'https://api.github.com/repos/' . $repo;

		echo '<div class="wrap"><h1>TMON Firmware</h1>';
		tmon_admin_safe_card_open('Repository Info');

		$info = wp_remote_get($api_base, array('timeout' => 15, 'headers' => array('User-Agent' => 'TMON Admin')));
		$ok = !is_wp_error($info) && wp_remote_retrieve_response_code($info) === 200;
		if ($ok) {
			$meta = json_decode(wp_remote_retrieve_body($info), true);
			echo '<p><strong>Name:</strong> ' . esc_html($meta['full_name']) . '</p>';
			echo '<p><strong>Default branch:</strong> ' . esc_html($meta['default_branch']) . '</p>';
			echo '<p><a class="button button-primary" target="_blank" href="https://github.com/' . esc_attr($repo) . '">Open Repository</a></p>';
		} else {
			echo '<p><em>Unable to load repository metadata.</em></p>';
		}
		tmon_admin_safe_card_close();

		tmon_admin_safe_card_open('Latest Versions');
		$releases = wp_remote_get($api_base . '/releases', array('timeout' => 20, 'headers' => array('User-Agent' => 'TMON Admin')));
		$r_ok = !is_wp_error($releases) && wp_remote_retrieve_response_code($releases) === 200;
		if ($r_ok) {
			$list = json_decode(wp_remote_retrieve_body($releases), true);
			if (is_array($list) && !empty($list)) {
				echo '<table class="widefat striped"><thead><tr><th>Tag</th><th>Name</th><th>Published</th><th>Assets</th></tr></thead><tbody>';
				foreach ($list as $rel) {
					$assets = array();
					if (!empty($rel['assets'])) {
						foreach ($rel['assets'] as $a) {
							$assets[] = '<a target="_blank" href="' . esc_url($a['browser_download_url']) . '">' . esc_html($a['name']) . '</a>';
						}
					}
					echo '<tr>';
					echo '<td>' . esc_html($rel['tag_name']) . '</td>';
					echo '<td>' . esc_html($rel['name']) . '</td>';
					echo '<td>' . esc_html(isset($rel['published_at']) ? $rel['published_at'] : '') . '</td>';
					echo '<td>' . implode(' | ', $assets) . '</td>';
					echo '</tr>';
				}
				echo '</tbody></table>';
			} else {
				echo '<p><em>No releases found.</em></p>';
			}
		} else {
			echo '<p><em>Unable to fetch releases.</em></p>';
		}
		tmon_admin_safe_card_close();

		tmon_admin_safe_card_open('Documentation');
		$readme_url = $base_url . 'README.md';
		$readme = wp_remote_get($readme_url, array('timeout' => 15, 'headers' => array('User-Agent' => 'TMON Admin')));
		if (!is_wp_error($readme) && wp_remote_retrieve_response_code($readme) === 200) {
			$md = wp_remote_retrieve_body($readme);
			echo '<p><a class="button" target="_blank" href="' . esc_url($readme_url) . '">Open README</a></p>';
			echo '<pre style="max-height:300px;overflow:auto;white-space:pre-wrap;">' . esc_html($md) . '</pre>';
		} else {
			echo '<p><em>README not available.</em></p>';
		}
		$changes_url = $base_url . 'CHANGELOG.md';
		echo '<p><a class="button" target="_blank" href="' . esc_url($changes_url) . '">Open CHANGELOG</a></p>';
		tmon_admin_safe_card_close();

		echo '</div>';
	}
}

// Harden existing pages against missing dependencies
if (!function_exists('tmon_admin_notifications_page')) {
	function tmon_admin_notifications_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>Notifications</h1>';
		tmon_admin_safe_card_open('Status');
		echo '<p><em>If you see this, the page is loading. Further features require includes/notifications.php.</em></p>';
		tmon_admin_safe_card_close();
		echo '</div>';
	}
}
if (!function_exists('tmon_admin_ota_page')) {
	function tmon_admin_ota_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>OTA Jobs</h1>';
		tmon_admin_safe_card_open('Status');
		echo '<p><em>Page loaded. Ensure includes/ota.php supplies job listings.</em></p>';
		tmon_admin_safe_card_close();
		echo '</div>';
	}
}
if (!function_exists('tmon_admin_files_page')) {
	function tmon_admin_files_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>Files</h1>';
		tmon_admin_safe_card_open('Status');
		echo '<p><em>Page loaded. Ensure includes/files.php provides handlers.</em></p>';
		tmon_admin_safe_card_close();
		echo '</div>';
	}
}
if (!function_exists('tmon_admin_groups_page')) {
	function tmon_admin_groups_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>Groups</h1>';
		tmon_admin_safe_card_open('Status');
		echo '<p><em>Page loaded. Ensure includes/groups.php provides content.</em></p>';
		tmon_admin_safe_card_close();
		echo '</div>';
	}
}
if (!function_exists('tmon_admin_pairings_page')) {
	function tmon_admin_pairings_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>UC Pairings</h1>';
		tmon_admin_safe_card_open('Status');
		echo '<p><em>Page loaded. Ensure pairings data is configured.</em></p>';
		tmon_admin_safe_card_close();
		echo '</div>';
	}
}

// Wrap provisioning history pages to avoid fatal on missing data
if (!function_exists('tmon_admin_provisioning_history_page')) {
	function tmon_admin_provisioning_history_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>Provisioning History</h1>';
		tmon_admin_safe_card_open('Recent Activity');
		$history = get_option('tmon_admin_provision_history', []);
		if (is_array($history) && !empty($history)) {
			echo '<table class="widefat striped"><thead><tr><th>Time</th><th>User</th><th>Unit</th><th>Machine</th><th>Action</th></tr></thead><tbody>';
			foreach (array_reverse($history) as $h) {
				echo '<tr><td>' . esc_html($h['ts'] ?? '') . '</td><td>' . esc_html($h['user'] ?? '') . '</td><td>' . esc_html($h['unit_id'] ?? '') . '</td><td>' . esc_html($h['machine_id'] ?? '') . '</td><td>' . esc_html($h['action'] ?? '') . '</td></tr>';
			}
			echo '</tbody></table>';
		} else {
			echo '<p><em>No history recorded.</em></p>';
		}
		tmon_admin_safe_card_close();
		echo '</div>';
	}
}

// Audit hook examples (lightweight)
add_action('update_option_tmon_admin_repo', function ($old, $new) {
	tmon_admin_audit_log('repo_update', 'firmware', array('extra' => array('old' => $old, 'new' => $new)));
}, 10, 2);

// NOTE: All centralized AJAX handlers are available in includes/ajax-handlers.php.
// Avoid duplicating add_action closures for AJAX handlers; they are defined centrally.
// If duplicates still appear in this file, they are skipped by the guard below.

if (!defined('TMON_ADMIN_HANDLERS_INCLUDED')) {
	// If included file didn't define handlers, (fallback) add our handlers inline.
	// This block should normally be empty because includes/ajax-handlers.php defines the handlers.
	// Keeping the fallback ensures the plugin still functions if the include wasn't loaded.
	// ...existing code if any inline fallback needed...
}

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