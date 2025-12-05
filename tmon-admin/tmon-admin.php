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

// Process pending provisioning payloads: send to saved site URL (WORDPRESS_API_URL)
add_action('admin_init', function () {
	// Simple lock with transient to avoid concurrent dispatch
	if (get_transient('tmon_admin_provision_dispatch_lock')) { return; }
	set_transient('tmon_admin_provision_dispatch_lock', 1, 30);

	$queue = get_option('tmon_admin_pending_provision', []);
	if (!is_array($queue) || empty($queue)) {
		delete_transient('tmon_admin_provision_dispatch_lock');
		return;
	}
	// Optional: provisioning devices table for site_url lookup
	global $wpdb;
	$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';

	// Load UC pairings for shared key lookup
	$pairings = function_exists('tmon_admin_uc_pairings_get') ? tmon_admin_uc_pairings_get() : array();

	$updated_queue = $queue;
	foreach ($queue as $key => $item) {
		// Expect shape: ['unit_id'=>..., 'machine_id'=>..., 'payload'=>json, 'enqueued_at'=>..., 'type'=>'reprovision']
		$unit = isset($item['unit_id']) ? sanitize_text_field($item['unit_id']) : '';
		$mach = isset($item['machine_id']) ? sanitize_text_field($item['machine_id']) : '';
		$payload_json = isset($item['payload']) ? $item['payload'] : '{}';

		// Resolve target Site URL
		$site_url = '';
		if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $prov_table))) {
			$row = $wpdb->get_row($wpdb->prepare("SELECT site_url FROM {$prov_table} WHERE unit_id=%s OR machine_id=%s ORDER BY updated_at DESC LIMIT 1", $unit, $mach), ARRAY_A);
			if ($row && !empty($row['site_url'])) {
				$site_url = esc_url_raw($row['site_url']);
			}
		}
		// Fallback: try per-device meta option
		if (!$site_url) {
			$map = get_option('tmon_admin_device_sites', []);
			if (is_array($map) && !empty($map[$unit])) {
				$site_url = esc_url_raw($map[$unit]);
			}
		}
		if (!$site_url) {
			// keep in queue; cannot resolve destination
			continue;
		}

		// Lookup shared key by normalized UC URL
		$shared_key = '';
		if (function_exists('tmon_admin_uc_normalize_url')) {
			$key_id = tmon_admin_uc_normalize_url($site_url);
			if ($key_id && !empty($pairings[$key_id]['key']) && !empty($pairings[$key_id]['active'])) {
				$shared_key = $pairings[$key_id]['key'];
			}
		}

		if (!$shared_key) {
			// No key; cannot authenticate to UC
			if (function_exists('tmon_admin_audit_log')) {
				tmon_admin_audit_log('provision_dispatch_fail', 'uc_push', array(
					'unit_id' => $unit,
					'machine_id' => $mach,
					'extra' => array('endpoint' => $site_url, 'reason' => 'missing_shared_key')
				));
			}
			continue;
		}

		// Dispatch to Unit Connector endpoint(s) with shared key header
		$base = trailingslashit($site_url);
		$paths = array(
			'wp-json/tmon/v1/admin/provision-apply',
			'wp-json/tmon-uc/v1/provision/apply',
			'wp-json/tmon-uc/v1/provision-apply',
		);
		$delivered = false;
		foreach ($paths as $path) {
			$endpoint = $base . $path;
			$args = array(
				'headers' => array(
					'Content-Type' => 'application/json',
					'Accept' => 'application/json',
					'User-Agent' => 'TMON-Admin/1.0',
					'X-TMON-HUB' => $shared_key, // UC validates this against its tmon_uc_shared_key
				),
				'body' => $payload_json,
				'timeout' => 20,
				'method' => 'POST',
			);
			$resp = wp_remote_post($endpoint, $args);
			if (!is_wp_error($resp) && wp_remote_retrieve_response_code($resp) === 200) {
				$delivered = true;
				// Remove from queue on success
				unset($updated_queue[$key]);
				if (function_exists('tmon_admin_audit_log')) {
					tmon_admin_audit_log('provision_dispatch', 'uc_push', array(
						'unit_id' => $unit,
						'machine_id' => $mach,
						'extra' => array('endpoint' => $endpoint)
					));
				}
				break;
			}
		}
		if (!$delivered) {
			// Leave in queue; record failure in audit
			if (function_exists('tmon_admin_audit_log')) {
				tmon_admin_audit_log('provision_dispatch_fail', 'uc_push', array(
					'unit_id' => $unit,
					'machine_id' => $mach,
					'extra' => array('endpoint' => $base, 'reason' => 'all_endpoints_failed')
				));
			}
		}
	}
	// Persist updated queue
	update_option('tmon_admin_pending_provision', $updated_queue, false);
	delete_transient('tmon_admin_provision_dispatch_lock');
});

// Remove banner text from Provisioning page
add_filter('tmon_admin_provisioning_banner', function ($text) {
	// Return empty to suppress the “Data maintenance...” banner
	return '';
}, 10, 1);

// Ensure schema is present before any UI/REST interaction
add_action('admin_init', function () {
	if (function_exists('tmon_admin_install_schema')) {
		ob_start();
		tmon_admin_install_schema();
		// Drop any unexpected echoes such as “tmon_admin_ensure_columns executed (idempotent).”
		@ob_end_clean();
	}
});
add_action('rest_api_init', function () {
	if (function_exists('tmon_admin_install_schema')) {
		ob_start();
		tmon_admin_install_schema();
		@ob_end_clean();
	}
});

// Minimal audit logger (best-effort) to populate audit entries
if (!function_exists('tmon_admin_audit_log')) {
	function tmon_admin_audit_log($action, $context = null, $args = array()) {
		global $wpdb;
		if (!function_exists('tmon_admin_audit_ensure_tables')) return;
		tmon_admin_audit_ensure_tables();
		$table = $wpdb->prefix . 'tmon_admin_audit';
		$wpdb->insert($table, array(
			'ts' => current_time('mysql'),
			'user_id' => get_current_user_id() ?: null,
			'action' => sanitize_text_field($action),
			'context' => $context ? sanitize_text_field($context) : null,
			'unit_id' => isset($args['unit_id']) ? sanitize_text_field($args['unit_id']) : null,
			'machine_id' => isset($args['machine_id']) ? sanitize_text_field($args['machine_id']) : null,
			'extra' => isset($args['extra']) ? wp_json_encode($args['extra']) : null,
		));
	}
}

// Safe wrappers for pages to avoid critical errors when includes are incomplete
if (!function_exists('tmon_admin_notifications_page')) {
	function tmon_admin_notifications_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>Notifications</h1>';
		echo '<div class="card" style="padding:12px;"><p><em>Page loaded. Ensure includes/notifications.php is active for full features.</em></p></div>';
		echo '</div>';
	}
}
if (!function_exists('tmon_admin_ota_page')) {
	function tmon_admin_ota_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>OTA Jobs</h1>';
		echo '<div class="card" style="padding:12px;"><p><em>Page loaded. Ensure includes/ota.php supplies job listings.</em></p></div>';
		echo '</div>';
	}
}
if (!function_exists('tmon_admin_files_page')) {
	function tmon_admin_files_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>Files</h1>';
		echo '<div class="card" style="padding:12px;"><p><em>Page loaded. Ensure includes/files.php provides handlers.</em></p></div>';
		echo '</div>';
	}
}
if (!function_exists('tmon_admin_groups_page')) {
	function tmon_admin_groups_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>Groups</h1>';
		echo '<div class="card" style="padding:12px;"><p><em>Page loaded. Ensure includes/groups.php provides content.</em></p></div>';
		echo '</div>';
	}
}
if (!function_exists('tmon_admin_pairings_page')) {
	function tmon_admin_pairings_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		// Load pairings from option
		if (!function_exists('tmon_admin_uc_pairings_get')) {
			echo '<div class="wrap"><h1>UC Pairings</h1><div class="card" style="padding:12px;"><p><em>Pairing storage helpers not loaded.</em></p></div></div>';
			return;
		}
		$pairings = tmon_admin_uc_pairings_get();

		echo '<div class="wrap"><h1>UC Pairings</h1>';
		echo '<div class="card" style="padding:12px;">';
		echo '<h2 style="margin-top:0;">Registered Unit Connectors</h2>';

		if (empty($pairings)) {
			echo '<p><em>No Unit Connectors paired yet.</em></p>';
		} else {
			echo '<table class="widefat striped"><thead><tr>';
			echo '<th>Key ID</th><th>UC URL</th><th>Site Name</th><th>Shared Key</th><th>Created</th><th>Last Verified</th><th>Status</th>';
			echo '</tr></thead><tbody>';
			foreach ($pairings as $key_id => $info) {
				$key = isset($info['key']) ? $info['key'] : '';
				$created = isset($info['created']) ? $info['created'] : '';
				$status = !empty($info['active']) ? 'Active' : 'Inactive';
				$uc_url = isset($info['uc_url']) ? $info['uc_url'] : $key_id;
				$lastv  = isset($info['last_verified']) ? $info['last_verified'] : '';
				$site_name = isset($info['site_name']) ? $info['site_name'] : '';
				echo '<tr>';
				echo '<td>' . esc_html($key_id) . '</td>';
				echo '<td>' . esc_html($uc_url) . '</td>';
				echo '<td>' . esc_html($site_name) . '</td>';
				echo '<td><code>' . esc_html($key) . '</code></td>';
				echo '<td>' . esc_html($created) . '</td>';
				echo '<td>' . esc_html($lastv) . '</td>';
				echo '<td>' . esc_html($status) . '</td>';
				echo '</tr>';
			}
			echo '</tbody></table>';
		}
		echo '</div>';
		echo '</div>';
	}
}

// Working Firmware page: repo info, releases, docs
if (!function_exists('tmon_admin_firmware_page')) {
	function tmon_admin_firmware_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		$repo = get_option('tmon_admin_repo', 'kevinnutt83/TMON');
		$branch = get_option('tmon_admin_repo_branch', 'main');
		$api_base = 'https://api.github.com/repos/' . $repo;
		$raw_base = 'https://raw.githubusercontent.com/' . $repo . '/' . $branch . '/';

		echo '<div class="wrap"><h1>TMON Firmware</h1>';
		echo '<div class="card" style="padding:12px;"><h2 style="margin-top:0;">Repository</h2>';
		$info = wp_remote_get($api_base, array('timeout' => 15, 'headers' => array('User-Agent' => 'TMON Admin')));
		if (!is_wp_error($info) && wp_remote_retrieve_response_code($info) === 200) {
			$meta = json_decode(wp_remote_retrieve_body($info), true);
			echo '<p><strong>Name:</strong> ' . esc_html($meta['full_name']) . '</p>';
			echo '<p><strong>Default branch:</strong> ' . esc_html($meta['default_branch']) . '</p>';
			echo '<p><a class="button button-primary" target="_blank" href="https://github.com/' . esc_attr($repo) . '">Open Repository</a></p>';
		} else {
			echo '<p><em>Unable to load repository metadata.</em></p>';
		}
		echo '</div>';

		echo '<div class="card" style="padding:12px;"><h2 style="margin-top:0;">Releases</h2>';
		$releases = wp_remote_get($api_base . '/releases', array('timeout' => 20, 'headers' => array('User-Agent' => 'TMON Admin')));
		if (!is_wp_error($releases) && wp_remote_retrieve_response_code($releases) === 200) {
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
					echo '<tr><td>' . esc_html($rel['tag_name']) . '</td><td>' . esc_html($rel['name']) . '</td><td>' . esc_html($rel['published_at'] ?? '') . '</td><td>' . implode(' | ', $assets) . '</td></tr>';
				}
				echo '</tbody></table>';
			} else {
				echo '<p><em>No releases found.</em></p>';
			}
		} else {
			echo '<p><em>Unable to fetch releases.</em></p>';
		}
		echo '</div>';

		echo '<div class="card" style="padding:12px;"><h2 style="margin-top:0;">Documentation</h2>';
		$readme_url = $raw_base . 'README.md';
		$readme = wp_remote_get($readme_url, array('timeout' => 15, 'headers' => array('User-Agent' => 'TMON Admin')));
		echo '<p><a class="button" target="_blank" href="' . esc_url($readme_url) . '">Open README</a></p>';
		if (!is_wp_error($readme) && wp_remote_retrieve_response_code($readme) === 200) {
			$md = wp_remote_retrieve_body($readme);
			echo '<pre style="max-height:300px;overflow:auto;white-space:pre-wrap;">' . esc_html($md) . '</pre>';
		} else {
			echo '<p><em>README not available.</em></p>';
		}
		$ch_url = $raw_base . 'CHANGELOG.md';
		echo '<p><a class="button" target="_blank" href="' . esc_url($ch_url) . '">Open CHANGELOG</a></p>';
		echo '</div>';

		echo '</div>';
	}
}

// Wrap provisioning history page to render even when empty
if (!function_exists('tmon_admin_provisioning_history_page')) {
	function tmon_admin_provisioning_history_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>Provisioning History</h1>';
		$history = get_option('tmon_admin_provision_history', []);
		echo '<div class="card" style="padding:12px;"><h2 style="margin-top:0;">Recent Activity</h2>';
		if (is_array($history) && !empty($history)) {
			echo '<table class="widefat striped"><thead><tr><th>Time</th><th>User</th><th>Unit</th><th>Machine</th><th>Action</th></tr></thead><tbody>';
			foreach (array_reverse($history) as $h) {
				echo '<tr><td>' . esc_html($h['ts'] ?? '') . '</td><td>' . esc_html($h['user'] ?? '') . '</td><td>' . esc_html($h['unit_id'] ?? '') . '</td><td>' . esc_html($h['machine_id'] ?? '') . '</td><td>' . esc_html($h['action'] ?? '') . '</td></tr>';
			}
			echo '</tbody></table>';
		} else {
			echo '<p><em>No history recorded yet.</em></p>';
		}
		echo '</div></div>';
	}
}

// Example audit log on repo option changes (ensures entries begin populating)
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

// Normalize UC URL to a canonical key (host[:port]) to avoid duplicates from http/https/trailing slash variants.
if (!function_exists('tmon_admin_uc_normalize_url')) {
	function tmon_admin_uc_normalize_url($uc_url) {
		$u = trim($uc_url);
		if (!$u) return '';
		// Ensure scheme for parse_url
		if (!preg_match('#^https?://#i', $u)) {
			$u = 'https://' . $u;
		}
		$parts = parse_url($u);
		if (!$parts || empty($parts['host'])) return '';
		$host = strtolower($parts['host']);
		$port = isset($parts['port']) ? intval($parts['port']) : null;
		return $port ? ($host . ':' . $port) : $host;
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

// UC connector pairing store helpers (per-UC shared keys)
if (!function_exists('tmon_admin_uc_pairings_get')) {
	function tmon_admin_uc_pairings_get() {
		$pair = get_option('tmon_uc_pairings', array());
		return is_array($pair) ? $pair : array();
	}
}
if (!function_exists('tmon_admin_uc_pairings_set')) {
	function tmon_admin_uc_pairings_set($pair) {
		if (!is_array($pair)) { return false; }
		return update_option('tmon_uc_pairings', $pair, false);
	}
}
if (!function_exists('tmon_admin_uc_key_generate')) {
	function tmon_admin_uc_key_generate() {
		$raw = wp_generate_password(64, true, true);
		return hash('sha256', $raw . wp_rand() . microtime(true));
	}
}
if (!function_exists('tmon_admin_hmac_valid')) {
	function tmon_admin_hmac_valid($msg, $sig, $key) {
		if (!$key || !$sig) return false;
		$calc = hash_hmac('sha256', $msg, $key);
		// Accept hex or base64 signatures
		if (hash_equals($calc, $sig)) return true;
		$b64 = base64_encode(hex2bin($calc));
		return hash_equals($b64, $sig);
	}
}

/**
 * Dynamic key resolution for legacy UC endpoints (uses X-TMON-UC header)
 * Existing includes/api-uc.php reads get_option('tmon_uc_shared_key'); resolve per-UC on the fly.
 */
add_filter('pre_option_tmon_uc_shared_key', function ($pre) {
	$uc_raw = '';
	if (isset($_SERVER['HTTP_X_TMON_UC'])) {
		$uc_raw = wp_unslash($_SERVER['HTTP_X_TMON_UC']);
	} elseif (!empty($_GET['uc_url'])) {
		$uc_raw = wp_unslash($_GET['uc_url']);
	}
	if (!$uc_raw || !function_exists('tmon_admin_uc_normalize_url')) { return $pre; }
	$key_id = tmon_admin_uc_normalize_url($uc_raw);
	$pair = tmon_admin_uc_pairings_get();
	if (!empty($pair[$key_id]['active']) && !empty($pair[$key_id]['key'])) {
		return $pair[$key_id]['key'];
	}
	return $pre;
}, 10, 1);

/**
 * REST: UC pairing endpoints
 * - POST /tmon-admin/v1/uc/pair       -> issue per-UC shared key
 * - POST /tmon-admin/v1/uc/verify     -> HMAC verify (uc_url|nonce) with shared key
 */
add_action('rest_api_init', function () {
	register_rest_route('tmon-admin/v1', '/uc/pair', array(
		'methods'  => 'POST',
		'callback' => function ($request) {
			$uc_url_raw = $request->get_param('uc_url');
			$uc_url = esc_url_raw($uc_url_raw);
			$key_id = tmon_admin_uc_normalize_url($uc_url ?: $uc_url_raw);
			if (!$key_id) {
				return new WP_Error('bad_request', 'uc_url required', array('status' => 400));
			}
			$pair = tmon_admin_uc_pairings_get();
			// Issue or rotate key; keep existing metadata if present
			$key = tmon_admin_uc_key_generate();
			$pair[$key_id] = array(
				'key'       => $key,
				'created'   => current_time('mysql'),
				'active'    => 1,
				'uc_url'    => $uc_url ?: $key_id,
				'site_name' => sanitize_text_field($request->get_param('site_name') ?: ''),
				'last_verified' => null,
			);
			tmon_admin_uc_pairings_set($pair);
			if (function_exists('tmon_admin_audit_log')) {
				tmon_admin_audit_log('uc_pair_issue', 'pair', array('extra' => array('uc' => $pair[$key_id]['uc_url'])));
			}
			return rest_ensure_response(array(
				'status' => 'ok',
				'hub_id' => get_site_url(),
				'shared_key' => $key,
			));
		},
		'permission_callback' => '__return_true',
	));

	register_rest_route('tmon-admin/v1', '/uc/verify', array(
		'methods'  => 'POST',
		'callback' => function ($request) {
			$uc_url_raw = $request->get_param('uc_url');
			$uc_url = esc_url_raw($uc_url_raw);
			$key_id = tmon_admin_uc_normalize_url($uc_url ?: $uc_url_raw);
			$nonce  = sanitize_text_field($request->get_param('nonce'));
			$sig    = sanitize_text_field($request->get_param('signature'));
			if (!$key_id || !$nonce || !$sig) {
				return new WP_Error('bad_request', 'uc_url, nonce, signature required', array('status' => 400));
			}
			$pair = tmon_admin_uc_pairings_get();
			if (empty($pair[$key_id]['active']) || empty($pair[$key_id]['key'])) {
				return new WP_Error('not_paired', 'UC not paired', array('status' => 403));
			}
			$msg = ($pair[$key_id]['uc_url'] ?: $key_id) . '|' . $nonce;
			if (!tmon_admin_hmac_valid($msg, $sig, $pair[$key_id]['key'])) {
				return new WP_Error('bad_sig', 'Invalid signature', array('status' => 403));
			}
			// Update metadata
			$pair[$key_id]['last_verified'] = current_time('mysql');
			if ($uc_url) { $pair[$key_id]['uc_url'] = $uc_url; }
			if ($request->get_param('site_name')) {
				$pair[$key_id]['site_name'] = sanitize_text_field($request->get_param('site_name'));
			}
			tmon_admin_uc_pairings_set($pair);
			if (function_exists('tmon_admin_audit_log')) {
				tmon_admin_audit_log('uc_pair_verify', 'pair', array('extra' => array('uc' => $pair[$key_id]['uc_url'])));
			}
			return rest_ensure_response(array('status' => 'ok'));
		},
		'permission_callback' => '__return_true',
	));

	// List pairings endpoint to help UC and Admin UI
	register_rest_route('tmon-admin/v1', '/uc/pairings', array(
		'methods'  => 'GET',
		'callback' => function () {
			$pair = tmon_admin_uc_pairings_get();
			$out = array();
			foreach ($pair as $key_id => $info) {
				$out[] = array(
					'key_id' => $key_id,
					'uc_url' => $info['uc_url'] ?? $key_id,
					'shared_key' => $info['key'] ?? '',
					'active' => !empty($info['active']) ? 1 : 0,
					'created' => $info['created'] ?? '',
					'last_verified' => $info['last_verified'] ?? '',
					'site_name' => $info['site_name'] ?? '',
				);
			}
			return rest_ensure_response($out);
		},
		'permission_callback' => '__return_true',
	));
});

/**
 * REST: UC sync endpoint
 * - POST /tmon-admin/v1/uc/sync
 * Returns customer/account summary and devices filtered by UC domain (uc_url).
 */
add_action('rest_api_init', function () {
	register_rest_route('tmon-admin/v1', '/uc/sync', array(
		'methods'  => 'POST',
		'callback' => function ($request) {
			$uc_url_raw = $request->get_param('uc_url');
			$uc_url = esc_url_raw($uc_url_raw);
			$key_id = function_exists('tmon_admin_uc_normalize_url') ? tmon_admin_uc_normalize_url($uc_url ?: $uc_url_raw) : ($uc_url ?: $uc_url_raw);
			if (!$key_id) { return new WP_Error('bad_request', 'uc_url required', array('status' => 400)); }
			$pair = tmon_admin_uc_pairings_get();
			if (empty($pair[$key_id]['active'])) {
				return new WP_Error('not_paired', 'UC not paired', array('status' => 403));
			}
			global $wpdb;
			$out = array(
				'account' => array(
					'hub' => get_site_url(),
					'uc_url' => $pair[$key_id]['uc_url'] ?? $key_id,
					'paired_at' => $pair[$key_id]['created'] ?? '',
				),
				'devices' => array(),
			);
			// Filter devices by domain match (site_url like uc_url)
			$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
			if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $prov_table))) {
				$like_host = parse_url($pair[$key_id]['uc_url'] ?? '', PHP_URL_HOST);
				$like = '%' . $wpdb->esc_like($like_host ?: $key_id) . '%';
				$rows = $wpdb->get_results($wpdb->prepare("SELECT unit_id, machine_id, unit_name, role, site_url, status FROM {$prov_table} WHERE site_url LIKE %s ORDER BY updated_at DESC LIMIT 500", $like), ARRAY_A);
				if ($rows) {
					foreach ($rows as $r) {
						$out['devices'][] = array(
							'unit_id' => $r['unit_id'],
							'machine_id' => $r['machine_id'],
							'unit_name' => $r['unit_name'],
							'role' => $r['role'],
							'assigned' => 1,
							'site_url' => $r['site_url'],
							'status' => $r['status'],
						);
					}
				}
			}
			// Optional audit
			if (function_exists('tmon_admin_audit_log')) {
				tmon_admin_audit_log('uc_sync', 'pair', array('extra' => array('uc' => ($pair[$key_id]['uc_url'] ?? $key_id), 'devices' => count($out['devices']))));
			}
			return rest_ensure_response($out);
		},
		'permission_callback' => '__return_true',
	));
});

// Suppress specific debug print globally
add_filter('gettext', function ($translated, $text, $domain) {
	$needle = 'tmon-admin: tmon_admin_ensure_columns executed (idempotent).';
	if (strpos($translated, $needle) !== false) {
		$translated = str_replace($needle, '', $translated);
	}
	return $translated;
}, 10, 3);

/**
 * REST: UC → Admin device data relay
 * - POST /tmon-admin/v1/uc/device-data
 * Body: { unit_id, machine_id, site_url, records: [ {timestamp, ...sdata...} ] }
 * Header: X-TMON-HUB must match per-UC shared key (normalized by domain).
 */
add_action('rest_api_init', function () {
	register_rest_route('tmon-admin/v1', '/uc/device-data', array(
		'methods'  => 'POST',
		'callback' => function ($request) {
			// Authenticate UC by shared key from X-TMON-HUB and uc_url in body
			$shared = isset($_SERVER['HTTP_X_TMON_HUB']) ? sanitize_text_field($_SERVER['HTTP_X_TMON_HUB']) : '';
			$site_url_raw = $request->get_param('site_url');
			$site_url = esc_url_raw($site_url_raw);
			$key_id = function_exists('tmon_admin_uc_normalize_url') ? tmon_admin_uc_normalize_url($site_url ?: $site_url_raw) : ($site_url ?: $site_url_raw);
			$pair = function_exists('tmon_admin_uc_pairings_get') ? tmon_admin_uc_pairings_get() : array();
			if (!$key_id || empty($pair[$key_id]['active']) || empty($pair[$key_id]['key']) || !hash_equals($pair[$key_id]['key'], $shared)) {
				return new WP_Error('forbidden', 'Unauthorized UC', array('status' => 403));
			}

			$unit_id = sanitize_text_field($request->get_param('unit_id'));
			$machine_id = sanitize_text_field($request->get_param('machine_id'));
			$records = $request->get_param('records');
			if (!$unit_id || !is_array($records) || empty($records)) {
				return new WP_Error('bad_request', 'unit_id and records required', array('status' => 400));
			}

			// Ensure device data table exists
			global $wpdb;
			$table = $wpdb->prefix . 'tmon_device_data';
			$charset = $wpdb->get_charset_collate();
			$sql = "CREATE TABLE IF NOT EXISTS {$table} (
				id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
				unit_id VARCHAR(32) NOT NULL,
				machine_id VARCHAR(64) NULL,
				recorded_at DATETIME NULL,
				data LONGTEXT NULL,
				PRIMARY KEY (id),
				KEY idx_unit (unit_id),
				KEY idx_rec (recorded_at)
			) {$charset};";
			require_once ABSPATH . 'wp-admin/includes/upgrade.php';
			dbDelta($sql);

			$inserted = 0;
			foreach ($records as $rec) {
				// Normalize record
				$recorded_at = current_time('mysql');
				if (is_array($rec) && isset($rec['timestamp'])) {
					$ts = intval($rec['timestamp']);
					if ($ts > 0) { $recorded_at = gmdate('Y-m-d H:i:s', $ts); }
				}
				$wpdb->insert($table, array(
					'unit_id'     => $unit_id,
					'machine_id'  => $machine_id ?: null,
					'recorded_at' => $recorded_at,
					'data'        => wp_json_encode($rec),
				));
				if ($wpdb->insert_id) { $inserted++; }
			}

			// Optional audit
			if (function_exists('tmon_admin_audit_log')) {
				tmon_admin_audit_log('uc_device_data', 'relay', array(
					'unit_id' => $unit_id,
					'machine_id' => $machine_id,
					'extra' => array('count' => $inserted, 'site_url' => $site_url)
				));
			}
			return rest_ensure_response(array('status' => 'ok', 'inserted' => $inserted));
		},
		'permission_callback' => '__return_true',
	));
});

/**
 * REST: UC → Admin plugin state relay
 * - POST /tmon-admin/v1/uc/plugin-state
 * Body: { site_url, settings: {...}, status: {...} } posted by Unit Connector
 */
add_action('rest_api_init', function () {
	register_rest_route('tmon-admin/v1', '/uc/plugin-state', array(
		'methods'  => 'POST',
		'callback' => function ($request) {
			$shared = isset($_SERVER['HTTP_X_TMON_HUB']) ? sanitize_text_field($_SERVER['HTTP_X_TMON_HUB']) : '';
			$site_url_raw = $request->get_param('site_url');
			$site_url = esc_url_raw($site_url_raw);
			$key_id = function_exists('tmon_admin_uc_normalize_url') ? tmon_admin_uc_normalize_url($site_url ?: $site_url_raw) : ($site_url ?: $site_url_raw);
			$pair = function_exists('tmon_admin_uc_pairings_get') ? tmon_admin_uc_pairings_get() : array();
			if (!$key_id || empty($pair[$key_id]['active']) || empty($pair[$key_id]['key']) || !hash_equals($pair[$key_id]['key'], $shared)) {
				return new WP_Error('forbidden', 'Unauthorized UC', array('status' => 403));
			}

			$settings = $request->get_param('settings');
			$status   = $request->get_param('status');
			// Persist a summary option keyed by normalized site
			$state = array(
				'site_url' => $site_url,
				'settings' => is_array($settings) ? $settings : array(),
				'status'   => is_array($status) ? $status : array(),
				'updated'  => current_time('mysql'),
			);
			$all = get_option('tmon_admin_uc_states', array());
			$all[$key_id] = $state;
			update_option('tmon_admin_uc_states', $all, false);

			if (function_exists('tmon_admin_audit_log')) {
				tmon_admin_audit_log('uc_plugin_state', 'relay', array('extra' => array('site' => $site_url)));
			}
			return rest_ensure_response(array('status' => 'ok'));
		},
		'permission_callback' => '__return_true',
	));
});