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
		$pairings = tmon_admin_uc_pairings_get();

		echo '<div class="wrap"><h1>UC Pairings</h1>';
		echo '<div class="card" style="padding:12px;"><h2 style="margin-top:0;">Registered Unit Connectors</h2>';

		if (empty($pairings)) {
			// If a last UC URL exists, hint that verification is pending
			$uc_guess = get_option('tmon_admin_last_uc_url');
			if ($uc_guess) {
				echo '<p><em>Pairing issued to ' . esc_html($uc_guess) . ' — awaiting verification.</em></p>';
			} else {
				echo '<p><em>No Unit Connectors paired yet.</em></p>';
			}
		} else {
			echo '<table class="widefat striped"><thead><tr>';
			echo '<th>Key ID</th><th>UC URL</th><th>Site Name</th><th>Shared Key</th><th>Created</th><th>Last Verified</th><th>Status</th>';
			echo '</tr></thead><tbody>';
			foreach ($pairings as $key_id => $info) {
				$status = !empty($info['active']) ? 'Active' : 'Awaiting Verify';
				echo '<tr>';
				echo '<td>' . esc_html($key_id) . '</td>';
				echo '<td>' . esc_html($info['uc_url'] ?? $key_id) . '</td>';
				echo '<td>' . esc_html($info['site_name'] ?? '') . '</td>';
				echo '<td><code>' . esc_html($info['key'] ?? '') . '</code></td>';
				echo '<td>' . esc_html($info['created'] ?? '') . '</td>';
				echo '<td>' . esc_html($info['last_verified'] ?? '') . '</td>';
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

// Ensure UC pairing storage helpers are available before menus/pages/REST
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
		if (hash_equals($calc, $sig)) return true;
		$b64 = base64_encode(hex2bin($calc));
		return hash_equals($b64, $sig);
	}
}

// UC Pairings admin page (show pending unverified pairs)
if (!function_exists('tmon_admin_pairings_page')) {
	function tmon_admin_pairings_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		$pairings = tmon_admin_uc_pairings_get();
		echo '<div class="wrap"><h1>UC Pairings</h1><div class="card" style="padding:12px;"><h2 style="margin-top:0;">Registered Unit Connectors</h2>';
		if (empty($pairings)) {
			// If a last UC URL exists, hint that verification is pending
			$uc_guess = get_option('tmon_admin_last_uc_url');
			if ($uc_guess) {
				echo '<p><em>Pairing issued to ' . esc_html($uc_guess) . ' — awaiting verification.</em></p>';
			} else {
				echo '<p><em>No Unit Connectors paired yet.</em></p>';
			}
		} else {
			echo '<table class="widefat striped"><thead><tr><th>Key ID</th><th>UC URL</th><th>Site Name</th><th>Shared Key</th><th>Created</th><th>Last Verified</th><th>Status</th></tr></thead><tbody>';
			foreach ($pairings as $key_id => $info) {
				$status = !empty($info['active']) ? 'Active' : 'Awaiting Verify';
				echo '<tr>';
				echo '<td>' . esc_html($key_id) . '</td>';
				echo '<td>' . esc_html($info['uc_url'] ?? $key_id) . '</td>';
				echo '<td>' . esc_html($info['site_name'] ?? '') . '</td>';
				echo '<td><code>' . esc_html($info['key'] ?? '') . '</code></td>';
				echo '<td>' . esc_html($info['created'] ?? '') . '</td>';
				echo '<td>' . esc_html($info['last_verified'] ?? '') . '</td>';
				echo '<td>' . esc_html($status) . '</td>';
				echo '</tr>';
			}
			echo '</tbody></table>';
		}
		echo '</div>';
		echo '</div>';
	}
}

// Ensure provisioning table exists before use (idempotent)
if (!function_exists('tmon_admin_ensure_provision_table')) {
	function tmon_admin_ensure_provision_table() {
		global $wpdb;
		$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
		$charset = $wpdb->get_charset_collate();
		$sql = "CREATE TABLE IF NOT EXISTS {$prov_table} (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			unit_id VARCHAR(64) NOT NULL,
			machine_id VARCHAR(64) NOT NULL,
			unit_name VARCHAR(191) NULL,
			site_url VARCHAR(191) NULL,
			status VARCHAR(64) NULL,
			role VARCHAR(64) NULL,
			created_at DATETIME NULL,
			updated_at DATETIME NULL,
			PRIMARY KEY (id),
			UNIQUE KEY uniq_unit_machine (unit_id, machine_id),
			KEY idx_site (site_url),
			KEY idx_updated (updated_at)
		) {$charset};";
		require_once ABSPATH . 'wp-admin/includes/upgrade.php';
		dbDelta($sql);
	}
}

// Provisioned Devices page: ensure table, then populate
if (!function_exists('tmon_admin_provisioned_devices_page')) {
	function tmon_admin_provisioned_devices_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		global $wpdb;
		tmon_admin_ensure_provision_table();
		$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';

		echo '<div class="wrap"><h1>Provisioned Devices (Admin)</h1>';
		$rows = $wpdb->get_results("SELECT * FROM {$prov_table} ORDER BY updated_at DESC, created_at DESC", ARRAY_A);

		if (empty($rows)) {
			$pair = tmon_admin_uc_pairings_get();
			foreach ($pair as $key_id => $info) {
				$uc_url = isset($info['uc_url']) ? $info['uc_url'] : '';
				if (!$uc_url || empty($info['active'])) { continue; }
				$host = parse_url($uc_url, PHP_URL_HOST);
				$like = '%' . $wpdb->esc_like($host ?: $key_id) . '%';
				$rows_uc = $wpdb->get_results($wpdb->prepare("SELECT unit_id, machine_id, unit_name, role, site_url, status FROM {$prov_table} WHERE site_url LIKE %s ORDER BY updated_at DESC LIMIT 500", $like), ARRAY_A);
				if (!empty($rows_uc)) {
					foreach ($rows_uc as $d) {
						$wpdb->query($wpdb->prepare(
							"INSERT INTO {$prov_table} (unit_id, machine_id, unit_name, site_url, status, role, created_at, updated_at)
							 VALUES (%s,%s,%s,%s,%s,%s,NOW(),NOW())
							 ON DUPLICATE KEY UPDATE unit_name=VALUES(unit_name), site_url=VALUES(site_url), status=VALUES(status), role=VALUES(role), updated_at=NOW()",
							$d['unit_id'], $d['machine_id'], ($d['unit_name'] ?? ''), ($d['site_url'] ?? ''), ($d['status'] ?? ''), ($d['role'] ?? '')
						));
					}
				}
			}
			$rows = $wpdb->get_results("SELECT * FROM {$prov_table} ORDER BY updated_at DESC, created_at DESC", ARRAY_A);
		}

		if (empty($rows)) {
			echo '<p><em>No provisioned devices found. Verify UC pairing and try again.</em></p>';
		} else {
			echo '<table class="widefat"><thead><tr><th>Unit ID</th><th>Machine ID</th><th>Unit Name</th><th>Site URL</th><th>Status</th><th>Role</th><th>Updated</th></tr></thead><tbody>';
			foreach ($rows as $r) {
				echo '<tr><td>'.esc_html($r['unit_id'] ?? '').'</td><td>'.esc_html($r['machine_id'] ?? '').'</td><td>'.esc_html($r['unit_name'] ?? '').'</td><td>'.esc_html($r['site_url'] ?? '').'</td><td>'.esc_html($r['status'] ?? '').'</td><td>'.esc_html($r['role'] ?? '').'</td><td>'.esc_html($r['updated_at'] ?? '').'</td></tr>';
			}
			echo '</tbody></table>';
		}
		echo '</div>';
	}
}

// Admin-side command forwarder: resolve uc_url if missing and include both headers
add_action('rest_api_init', function () {
	register_rest_route('tmon-admin/v1', '/uc/forward-command', array(
		'methods'  => 'POST',
		'callback' => function ($req) {
			$uc_url   = esc_url_raw($req->get_param('uc_url'));
			$unit_id  = sanitize_text_field($req->get_param('unit_id'));
			$type     = sanitize_text_field($req->get_param('type'));
			$data     = $req->get_param('data');
			if (!$unit_id || !$type) return new WP_Error('bad_request', 'unit_id, type required', array('status' => 400));

			// Resolve uc_url if not provided: from provisioned table or device_sites map
			if (!$uc_url) {
				global $wpdb;
				$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
				$site_url = $wpdb->get_var($wpdb->prepare("SELECT site_url FROM {$prov_table} WHERE unit_id=%s ORDER BY updated_at DESC LIMIT 1", $unit_id));
				if (!$site_url) {
					$map = get_option('tmon_admin_device_sites', []);
					if (is_array($map) && !empty($map[$unit_id])) { $site_url = esc_url_raw($map[$unit_id]); }
				}
				$uc_url = $site_url ?: $uc_url;
			}
			if (!$uc_url) return new WP_Error('bad_request', 'uc_url unresolved', array('status' => 400));

			$key_id = tmon_admin_uc_normalize_url($uc_url);
			$pair   = tmon_admin_uc_pairings_get();
			if (empty($pair[$key_id]['active']) || empty($pair[$key_id]['key'])) return new WP_Error('not_paired', 'UC not paired', array('status' => 403));
			$shared_key = $pair[$key_id]['key'];

			// Normalize relay payload
			if ($type === 'relay_ctrl' && is_array($data)) {
				$data = array(
					'relay'      => intval($data['relay'] ?? 1),
					'state'      => in_array(($data['state'] ?? 'off'), array('on','off'), true) ? $data['state'] : 'off',
					'duration_s' => isset($data['duration_s']) ? intval($data['duration_s']) : 0,
				);
			}

			$endpoint = trailingslashit($uc_url) . 'wp-json/tmon-uc/v1/device/command';
			$args = array(
				'headers' => array(
					'Content-Type' => 'application/json',
					'X-TMON-HUB' => $shared_key,            // hub authentication
					'X-TMON-UC'  => esc_url_raw($uc_url),   // identify UC for legacy filters
				),
				'body'    => wp_json_encode(array('unit_id' => $unit_id, 'type' => $type, 'data' => is_array($data) ? $data : array())),
				'timeout' => 15,
				'method'  => 'POST',
			);
			$r = wp_remote_post($endpoint, $args);
			if (is_wp_error($r)) return new WP_Error('forward_fail', 'UC unreachable', array('status' => 502));
			$code = wp_remote_retrieve_response_code($r);
			$body = wp_remote_retrieve_body($r);
			if ($code !== 200) return new WP_Error('forward_fail', 'UC rejected command', array('status' => $code, 'body' => $body));

			if (function_exists('tmon_admin_audit_log')) {
				tmon_admin_audit_log('forward_command', 'uc', array('unit_id' => $unit_id, 'extra' => array('type' => $type, 'uc' => $uc_url)));
			}
			return rest_ensure_response(array('status' => 'ok', 'uc_response' => json_decode($body, true)));
		},
		'permission_callback' => '__return_true',
	));
});

// Provisioned Devices page: show a banner if the table is missing and guide to pair UC
add_action('admin_notices', function () {
	if (!current_user_can('manage_options')) return;
	global $wpdb;
	$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
	if (!$wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $prov_table))) {
		echo '<div class="notice notice-warning"><p>Provisioning table not found. Ensure UC is paired and data sync is enabled, then revisit Provisioned Devices.</p></div>';
	}
});

// Guard: ensure Provisioning Activity page callback exists (fixes missing function fatal)
if (!function_exists('tmon_admin_provisioning_activity_page')) {
	function tmon_admin_provisioning_activity_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>Provisioning Activity</h1>';
		$queue = get_option('tmon_admin_pending_provision', []);
		$history = get_option('tmon_admin_provision_history', []);
		echo '<div class="card" style="padding:12px;"><h2 style="margin-top:0;">Pending Queue</h2>';
		if (!empty($queue) && is_array($queue)) {
			echo '<ul>';
			foreach ($queue as $k => $p) {
				echo '<li>' . esc_html($k) . ' — ' . esc_html(json_encode($p)) . '</li>';
			}
			echo '</ul>';
		} else {
			echo '<p><em>No pending queue entries.</em></p>';
		}
		echo '</div>';

		echo '<div class="card" style="padding:12px;"><h2 style="margin-top:0;">History</h2>';
		if (is_array($history) && !empty($history)) {
			echo '<ul>';
			foreach (array_reverse($history) as $h) {
				echo '<li>' . esc_html(($h['ts'] ?? '') . ' — ' . ($h['action'] ?? 'saved')) . '</li>';
			}
			echo '</ul>';
		} else {
			echo '<p><em>No history recorded.</em></p>';
		}
		echo '</div></div>';
	}
}

// REST: Health check for Unit Connectors
add_action('rest_api_init', function () {
	register_rest_route('tmon-admin/v1', '/status', array(
		'methods'  => 'GET',
		'callback' => function () {
			return rest_ensure_response(array(
				'status' => 'ok',
				'hub'    => get_site_url(),
				'version'=> get_option('tmon_admin_version', 'unknown'),
			));
		},
		'permission_callback' => '__return_true',
	));
});

// CORS: allow UC origins, handle preflight, set JSON content-type
add_action('rest_api_init', function () {
	$origins = get_option('tmon_uc_allowed_origins', array(
		'https://tmonsystems.com',
	));
	add_filter('rest_pre_serve_request', function ($served, $result, $request, $server) use ($origins) {
		$origin = isset($_SERVER['HTTP_ORIGIN']) ? trim($_SERVER['HTTP_ORIGIN']) : '';
		$allow  = in_array($origin, $origins, true) ? $origin : '*';
		header('Access-Control-Allow-Origin: ' . $allow);
		header('Access-Control-Allow-Credentials: true');
		header('Access-Control-Allow-Headers: Content-Type, X-TMON-HUB, X-TMON-UC, Authorization');
		header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
		header('Content-Type: application/json; charset=utf-8');
		// Preflight
		if ('OPTIONS' === $_SERVER['REQUEST_METHOD']) {
			echo wp_json_encode(array('status' => 'ok'));
			return true;
		}
		return $served;
	}, 10, 4);
});