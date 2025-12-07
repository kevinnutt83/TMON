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
		echo '</div>'; // Documentation card
		echo '</div>'; // wrap
	}
}

// Menu callback: use real renderer if present
if (!function_exists('tmon_admin_provisioned_devices_page')) {
	// Fallback exists elsewhere; no-op here
} else {
	// already defined in includes/provisioning.php and will be used by menu
}

// Fallback helpers to avoid fatal errors if UC helper includes are not loaded
if (!function_exists('tmon_admin_uc_pairings_get')) {
	function tmon_admin_uc_pairings_get() {
		$pair = get_option('tmon_uc_pairings', []);
		return is_array($pair) ? $pair : [];
	}
}
if (!function_exists('tmon_admin_uc_pairings_set')) {
	function tmon_admin_uc_pairings_set($pair) {
		return is_array($pair) ? update_option('tmon_uc_pairings', $pair, false) : false;
	}
}
if (!function_exists('tmon_admin_uc_normalize_url')) {
	function tmon_admin_uc_normalize_url($uc_url) {
		$u = trim((string)$uc_url);
		if ($u === '') return '';
		if (!preg_match('#^https?://#i', $u)) $u = 'https://' . $u;
		$parts = parse_url($u);
		if (!$parts || empty($parts['host'])) return '';
		$host = strtolower($parts['host']);
		$port = isset($parts['port']) ? intval($parts['port']) : null;
		return $port ? ($host . ':' . $port) : $host;
	}
}

// UC Pairing endpoint: register UC site and return shared hub key + read token
add_action('rest_api_init', function () {
	register_rest_route('tmon-admin/v1', '/uc/pair', [
		'methods' => 'POST',
		'callback' => function($request){
			$site_url = esc_url_raw($request->get_param('site_url'));
			$uc_key   = sanitize_text_field($request->get_param('uc_key'));
			if (!$site_url || !$uc_key) {
				return new WP_REST_Response(['status'=>'error','message'=>'site_url and uc_key required'], 400);
			}
			// Normalize URL to host[:port] for key
			if (!function_exists('tmon_admin_uc_normalize_url')) {
				$norm = parse_url($site_url);
				$key_id = isset($norm['host']) ? strtolower($norm['host']) : '';
				if (isset($norm['port'])) $key_id .= ':' . intval($norm['port']);
			} else {
				$key_id = tmon_admin_uc_normalize_url($site_url);
			}
			if (!$key_id) {
				return new WP_REST_Response(['status'=>'error','message'=>'invalid site_url'], 400);
			}
			$pairings = get_option('tmon_uc_pairings', []);
			if (!is_array($pairings)) $pairings = [];

			// Generate hub shared key and read token (stable per site)
			$hub_key = isset($pairings[$key_id]['key']) && $pairings[$key_id]['key'] ? $pairings[$key_id]['key'] : wp_generate_password(48, false, false);
			$read_token = isset($pairings[$key_id]['read_token']) && $pairings[$key_id]['read_token'] ? $pairings[$key_id]['read_token'] : wp_generate_password(32, false, false);

			$pairings[$key_id] = [
				'uc_url'       => $site_url,
				'site_name'    => get_option('blogname'),
				'key'          => $hub_key,
				'read_token'   => $read_token,
				'uc_key'       => $uc_key,
				'created'      => current_time('mysql'),
				'last_verified'=> current_time('mysql'),
				'active'       => 1,
			];
			update_option('tmon_uc_pairings', $pairings, false);
			// Hint for Pairings page
			update_option('tmon_admin_last_uc_url', $site_url, false);

			return rest_ensure_response([
				'status'     => 'ok',
				'hub_key'    => $hub_key,
				'read_token' => $read_token,
			]);
		},
		'permission_callback' => '__return_true',
	]);
});