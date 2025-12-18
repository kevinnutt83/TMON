<?php
/**
 * TMON Unit Connector
 * Main plugin file for TMON Unit Connector.
 *
 * @package TMON_Unit_Connector
 * @author  TMON DevOps
 * @version 0.2.0
 */

/*
Plugin Name: TMON Unit Connector
Description: Site-side connector for TMON devices; receives data and manages provisioning.
Version: 0.2.0
Author: TMON DevOps
*/

if ( ! defined( 'ABSPATH' ) ) exit;

// Defensive fallback: if WP pluggable user functions are not yet defined (some hosts/plugins can trigger REST early),
// provide a minimal stub so current_user_can() and related checks do not fatal during early bootstrap.
if ( ! function_exists( 'wp_get_current_user' ) ) {
	// Minimal WP_User-like stub used only until WP finishes loading pluggables.
	if ( ! class_exists( 'TMON_Fallback_User' ) ) {
		class TMON_Fallback_User {
			public $ID = 0;
			public $roles = [];
			public $locale = '';
			public $user_login = '';
			public $user_email = '';
			public function has_cap( $cap ) { return false; }
			// graceful property access
			public function __get( $name ) { return null; }
		}
	}
	function wp_get_current_user() {
		static $u = null;
		if ( $u === null ) $u = new TMON_Fallback_User();
		return $u;
	}
}
// Only define get_current_user_id() if it doesn't already exist (avoid redeclare).
if ( ! function_exists( 'get_current_user_id' ) ) {
	function get_current_user_id() {
		if ( function_exists( 'wp_get_current_user' ) ) {
			$user = wp_get_current_user();
			return isset( $user->ID ) ? intval( $user->ID ) : 0;
		}
		return 0;
	}
}

// --- Plugin bootstrap/load order notes ---
// This file is the main plugin file and entry point. It handles initial setup, autoloading of includes,
// and early initialization tasks. It also defines the main plugin class, which is responsible for
// loading all other components and features of the plugin.
// ---
// 1. Plugin constants and initial setup
// 2. Autoload includes
// 3. Early initialization tasks (e.g. REST API, scheduled tasks)
// 4. Main plugin class instantiation and setup
// ---

define( 'TMON_UNIT_CONNECTOR_VERSION', '0.2.0' );
define( 'TMON_UNIT_CONNECTOR_PATH', plugin_dir_path( __FILE__ ) );
define( 'TMON_UNIT_CONNECTOR_URL', plugin_dir_url( __FILE__ ) );

// Defer loading of includes and admin pages until plugins_loaded so REST handlers and
// other initialization only run after WP and other plugins (e.g., Elementor) finish setup.
add_action('plugins_loaded', function() {
	// Load all include files (idempotent via require_once)
	foreach ( glob( __DIR__ . '/includes/*.php' ) as $file ) {
		require_once $file;
	}

	// Admin pages and helpers (load only in admin context)
	if ( is_admin() ) {
		foreach ( glob( __DIR__ . '/admin/*.php' ) as $file ) {
			require_once $file;
		}
		require_once __DIR__ . '/admin/starter-page.php';
		require_once __DIR__ . '/admin/public-docs-page.php';
		require_once __DIR__ . '/admin/location.php';
	}
}, 20); // run after most plugins initialize

// Load v2 API routes once
if (!defined('TMON_UC_V2_API_LOADED')) {
	require_once __DIR__ . '/includes/v2-api.php';
}

// Assets

function tmon_unit_connector_enqueue_assets($hook = '') {
    if (is_admin()) {
        wp_enqueue_style( 'tmon-unit-connector', TMON_UNIT_CONNECTOR_URL . 'assets/admin.css', [], TMON_UNIT_CONNECTOR_VERSION );
        wp_enqueue_script( 'tmon-unit-connector', TMON_UNIT_CONNECTOR_URL . 'assets/admin.js', ['jquery'], TMON_UNIT_CONNECTOR_VERSION, true );
        // Fix improper use of wp_localize_script: third param must be array. Expose ajaxurl compatibly.
        wp_localize_script( 'tmon-unit-connector', 'tmon_uc_ajax', array( 'ajaxurl' => admin_url( 'admin-ajax.php' ) ) );
        // Also provide a simple global for legacy code paths if needed.
        wp_add_inline_script( 'tmon-unit-connector', 'window.tmon_uc_ajaxurl = window.ajaxurl || (window.tmon_uc_ajax && window.tmon_uc_ajax.ajaxurl) || "";', 'before' );
        wp_enqueue_script('tmon-hierarchy-js', plugin_dir_url(__FILE__) . 'assets/tmon-hierarchy.js', array('jquery'), null, true);
        wp_enqueue_style('tmon-hierarchy-css', plugin_dir_url(__FILE__) . 'assets/tmon-hierarchy.css');
    } else {
        // Frontend: minimal, user-facing CSS only
        wp_enqueue_style( 'tmon-user', TMON_UNIT_CONNECTOR_URL . 'assets/tmon-user.css', [], TMON_UNIT_CONNECTOR_VERSION );
    }
}
add_action( 'admin_enqueue_scripts', 'tmon_unit_connector_enqueue_assets' );
// Removed duplicate frontend enqueue of admin assets
// add_action( 'wp_enqueue_scripts', 'tmon_unit_connector_enqueue_assets' );

// Activation/Deactivation hooks
register_activation_hook( __FILE__, 'tmon_unit_connector_activate' );
register_deactivation_hook( __FILE__, 'tmon_unit_connector_deactivate' );

function tmon_unit_connector_activate() {
    global $wpdb;
    require_once __DIR__ . '/includes/schema.php';
    // Create all required tables
    tmon_uc_install_schema();

    // Add custom roles and capabilities for TMON
    add_role('tmon_manager', 'TMON Manager', [
        'read' => true,
        'manage_tmon' => true,
        'edit_tmon_hierarchy' => true,
        'edit_tmon_units' => true,
        'edit_tmon_settings' => true,
    ]);
    add_role('tmon_operator', 'TMON Operator', [
        'read' => true,
        'edit_tmon_units' => true,
    ]);
}

function tmon_unit_connector_deactivate() {
    $remove_data = get_option('tmon_uc_remove_data_on_deactivate', false);
    if ( $remove_data ) {
        if (function_exists('tmon_uc_remove_all_data')) {
			error_log('unit-connector: invoking tmon_uc_remove_all_data() during deactivate.');
			tmon_uc_remove_all_data();
		} else {
			error_log('unit-connector: tmon_uc_remove_all_data() missing - skipping purge on deactivate.');
		}
    }
    // Remove custom roles and capabilities for TMON
    remove_role('tmon_manager');
    remove_role('tmon_operator');
}


// Auto-update logic gated by repo config
add_filter('site_transient_update_plugins', function($transient) {
    if (empty($transient->checked)) return $transient;
    $repo = defined('TMON_UC_GITHUB_REPO') ? TMON_UC_GITHUB_REPO : '';
    if (!$repo) return $transient; // disabled until configured, e.g., define('TMON_UC_GITHUB_REPO','org/repo');
    $plugin_slug = plugin_basename(__FILE__);
    $github_api_url = 'https://api.github.com/repos/' . $repo . '/releases/latest';
    $response = wp_remote_get($github_api_url, [
        'headers' => [ 'Accept' => 'application/vnd.github.v3+json', 'User-Agent' => 'WordPress' ]
    ]);
    if (is_wp_error($response)) return $transient;
    $release = json_decode(wp_remote_retrieve_body($response));
    if (empty($release->tag_name)) return $transient;
    $plugin_data = get_plugin_data(__FILE__);
    if (version_compare($plugin_data['Version'], ltrim($release->tag_name, 'v'), '<')) {
        $transient->response[$plugin_slug] = (object) [
            'slug' => $plugin_slug,
            'plugin' => $plugin_slug,
            'new_version' => ltrim($release->tag_name, 'v'),
            'url' => $release->html_url,
            'package' => $release->assets[0]->browser_download_url ?? '',
        ];
    }
    return $transient;
});

// --- CSV Export for admin data tables (example: OTA jobs) ---
remove_action('admin_post_tmon_export_ota_jobs', '__return_false'); // ensure not hooked elsewhere
add_action('admin_post_tmon_export_ota_jobs', function() {
    if (!current_user_can('manage_options')) wp_die('Forbidden', 'Forbidden', 403);
    if ( ! isset( $_GET['_wpnonce'] ) || ! wp_verify_nonce( $_GET['_wpnonce'], 'tmon_export_ota_jobs' ) ) {
        wp_die( 'Invalid nonce.' );
    }
    global $wpdb;
    $rows = $wpdb->get_results("SELECT * FROM {$wpdb->prefix}tmon_ota_jobs", ARRAY_A);
    header('Content-Type: text/csv');
    header('Content-Disposition: attachment; filename="tmon_ota_jobs.csv"');
    $out = fopen('php://output', 'w');
    if (!empty($rows)) {
        fputcsv($out, array_keys($rows[0]));
        foreach ($rows as $row) fputcsv($out, $row);
    }
    fclose($out);
    exit;
});

// Helper: get secure OTA jobs CSV URL
function tmon_uc_ota_jobs_csv_url() {
    return wp_nonce_url(admin_url('admin-post.php?action=tmon_export_ota_jobs'), 'tmon_export_ota_jobs');
}

// Shortcodes
require_once __DIR__ . '/includes/shortcodes.php';
require_once __DIR__ . '/includes/field-data-api.php';
require_once __DIR__ . '/includes/api.php';
require_once __DIR__ . '/includes/settings.php';
require_once __DIR__ . '/admin/hierarchy.php';
require_once __DIR__ . '/includes/hierarchy-api.php';
require_once __DIR__ . '/includes/audit.php';
require_once __DIR__ . '/includes/notify.php';
require_once __DIR__ . '/admin/quick-actions.php';
require_once __DIR__ . '/includes/ai.php';

// CSV export for normalized field data (fixes previous CSV parsing issues)
add_action('admin_post_tmon_export_field_data_csv', function() {
    if ( ! isset( $_GET['_wpnonce'] ) || ! wp_verify_nonce( $_GET['_wpnonce'], 'tmon_export_field_data_csv' ) ) {
        wp_die( 'Invalid nonce.' );
    }
    // If not logged in, allow hub read token/keys via headers
    if (!is_user_logged_in()) {
        $ok = false;
        if (function_exists('getallheaders')) { $headers = getallheaders(); } else { $headers = []; }
        // Mirror tmon_uc_admin_read_auth logic inline to avoid cross-file include ordering
        $admin_key = $headers['X-TMON-ADMIN'] ?? ($_SERVER['HTTP_X_TMON_ADMIN'] ?? '');
        $hub_key   = $headers['X-TMON-HUB']   ?? ($_SERVER['HTTP_X_TMON_HUB']   ?? '');
        $read_tok  = $headers['X-TMON-READ']  ?? ($_SERVER['HTTP_X_TMON_READ']  ?? '');
        $exp_admin = get_option('tmon_uc_admin_key');
        $exp_hub   = get_option('tmon_uc_hub_shared_key');
        $exp_read  = get_option('tmon_uc_hub_read_token');
        if ($exp_admin && hash_equals($exp_admin, (string)$admin_key)) $ok = true;
        if (!$ok && $exp_hub && hash_equals($exp_hub, (string)$hub_key)) $ok = true;
        if (!$ok && $exp_read && hash_equals($exp_read, (string)$read_tok)) $ok = true;
        if (!$ok) {
            wp_die('Forbidden', 'Forbidden', 403);
        }
    }
    global $wpdb;
    $unit_id = sanitize_text_field($_GET['unit_id'] ?? '');
    header('Content-Type: text/csv');
    header('Content-Disposition: attachment; filename="tmon_field_data' . ($unit_id?('_'.$unit_id):'') . '.csv"');
    $out = fopen('php://output', 'w');
    // header row
    fputcsv($out, ['created_at','unit_id','origin','timestamp','name','machine_id','temp_f','temp_c','humidity','pressure','voltage_v','wifi_rssi','lora_rssi','free_mem','gps_lat','gps_lng','gps_alt_m','gps_accuracy_m','gps_last_fix_ts']);
    $query = "SELECT unit_id, data, created_at FROM {$wpdb->prefix}tmon_field_data";
    $args = [];
    if ($unit_id) {
        $query .= " WHERE unit_id=%s";
        $args[] = $unit_id;
    }
    $query .= " ORDER BY created_at ASC";
    $rows = $args ? $wpdb->get_results($wpdb->prepare($query, ...$args), ARRAY_A) : $wpdb->get_results($query, ARRAY_A);
    foreach ($rows as $r) {
        $d = json_decode($r['data'], true);
        if (!is_array($d)) continue;
        $origin = 'unknown';
        if (!empty($d['machine_id'])) {
            $origin = 'remote';
        } elseif (!empty($d['NODE_TYPE'])) {
            $origin = strtolower($d['NODE_TYPE']) === 'remote' ? 'remote' : 'base';
        } else {
            $remote_keys = 0;
            foreach (['t_f','t_c','hum','bar','v','fm'] as $k) { if (isset($d[$k])) $remote_keys++; }
            $origin = ($remote_keys >= 3) ? 'remote' : 'base';
        }
        $flat = [
            $r['created_at'],
            $r['unit_id'],
            $origin,
            $d['timestamp'] ?? ($d['time'] ?? ''),
            $d['name'] ?? '',
            $d['machine_id'] ?? '',
            isset($d['t_f']) ? $d['t_f'] : ($d['cur_temp_f'] ?? ''),
            isset($d['t_c']) ? $d['t_c'] : ($d['cur_temp_c'] ?? ''),
            isset($d['hum']) ? $d['hum'] : ($d['cur_humid'] ?? ''),
            isset($d['bar']) ? $d['bar'] : ($d['cur_bar_pres'] ?? ''),
            isset($d['v']) ? $d['v'] : ($d['sys_voltage'] ?? ''),
            $d['wifi_rssi'] ?? '',
            $d['lora_SigStr'] ?? '',
            isset($d['fm']) ? $d['fm'] : ($d['free_mem'] ?? ''),
            $d['gps_lat'] ?? ($d['GPS_LAT'] ?? ''),
            $d['gps_lng'] ?? ($d['GPS_LNG'] ?? ''),
            $d['gps_alt_m'] ?? ($d['GPS_ALT_M'] ?? ''),
            $d['gps_accuracy_m'] ?? ($d['GPS_ACCURACY_M'] ?? ''),
            $d['gps_last_fix_ts'] ?? ($d['GPS_LAST_FIX_TS'] ?? ''),
        ];
        fputcsv($out, $flat);
    }
    fclose($out);
    exit;
});

// Safe remote POST helper to avoid warnings on invalid endpoints
if (!function_exists('tmon_uc_safe_remote_post')) {
	function tmon_uc_safe_remote_post($endpoint, $args = [], $context_label = '') {
		// Normalize -- ensure string; Quick guard avoids parse_url(null) calls.
		if (!is_string($endpoint) || trim($endpoint) === '') {
			error_log("unit-connector: tmon_uc_safe_remote_post called with empty or invalid endpoint (context={$context_label}). Aborting.");
			return new WP_Error('invalid_endpoint', 'Endpoint not provided or invalid');
		}

		// Check URL validity
		$parsed = @parse_url($endpoint);
		if ($parsed === false || empty($parsed['host'])) {
			error_log("unit-connector: tmon_uc_safe_remote_post invalid endpoint: {$endpoint} (context={$context_label})");
			return new WP_Error('invalid_endpoint', 'Endpoint invalid');
		}

		// Normalize args
		if (!isset($args['headers'])) $args['headers'] = [];
		if (!isset($args['body'])) $args['body'] = '';

		$res = @wp_remote_post($endpoint, $args);
		if (is_wp_error($res)) {
			error_log("unit-connector: tmon_uc_safe_remote_post failed for {$endpoint} (context={$context_label}): " . $res->get_error_message());
			return $res;
		}
		$code = intval(wp_remote_retrieve_response_code($res));
		if ($code < 200 || $code >= 300) {
			error_log("unit-connector: tmon_uc_safe_remote_post non-2xx response for {$endpoint} (context={$context_label}): HTTP {$code}");
		}
		return $res;
	}
}

// Ensure default variables exist so stray references do not emit PHP notices.
// These are harmless defaults and avoid "Undefined variable" warnings if a stray reference occurs
$endpoint = '';
$headers = [];
$token = '';

// Guard deactivation/uninstall code to only call cleanup function if it exists.
if (!function_exists('tmon_unit_connector_deactivate')) {
	function tmon_unit_connector_deactivate() {
		$remove_data = get_option('tmon_uc_remove_data_on_deactivate', false);
		if ( $remove_data ) {
			if (function_exists('tmon_uc_remove_all_data')) {
				error_log('unit-connector: running tmon_uc_remove_all_data() on deactivation');
				tmon_uc_remove_all_data();
			} else {
				error_log('unit-connector: tmon_uc_remove_all_data() not present; skip purge on deactivate');
			}
		}
		// Remove custom roles and capabilities for TMON
		remove_role('tmon_manager');
		remove_role('tmon_operator');
	}
}
register_deactivation_hook(__FILE__, 'tmon_unit_connector_deactivate');

// --- Token rotation/revoke handlers --- (use the safe helper so no undefined variable warnings occur)
add_action('admin_init', function(){
    if (!current_user_can('manage_options')) return;

    if (isset($_POST['tmon_action']) && $_POST['tmon_action'] === 'rotate_token' && check_admin_referer('tmon_admin_rotate_token')) {
        $site_url = esc_url_raw($_POST['site_url'] ?? '');
        if ($site_url) {
            $map = get_option('tmon_admin_uc_sites', []);
            if (isset($map[$site_url])) {
                try { $token = bin2hex(random_bytes(24)); } catch (Exception $e) { $token = wp_generate_password(48, false, false); }
                $map[$site_url]['read_token'] = $token;
                update_option('tmon_admin_uc_sites', $map);

                // Build endpoint & headers in scope and use safe helper
                $endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/read-token/set';
                $headers = ['Content-Type' => 'application/json'];
                $uc_key = $map[$site_url]['uc_key'] ?? '';
                if ($uc_key) $headers['X-TMON-ADMIN'] = $uc_key;
                $body = wp_json_encode(['read_token' => $token]);

                $res = tmon_uc_safe_remote_post($endpoint, ['timeout' => 15, 'headers' => $headers, 'body' => $body], 'rotate_token');
                if (is_wp_error($res)) {
                    error_log('unit-connector: Failed push read token to UC ' . $site_url . ' error=' . $res->get_error_message());
                } else {
                    error_log('unit-connector: Pushed read token to UC ' . $site_url . ' status=' . intval(wp_remote_retrieve_response_code($res)));
                }

                add_action('admin_notices', function(){ echo '<div class="updated"><p>Read token regenerated and pushed to UC.</p></div>'; });
            } else {
                error_log('unit-connector: rotate_token called for unrecognized site_url=' . $site_url);
            }
        } else {
            error_log('unit-connector: rotate_token called without site_url');
        }
    }

    if (isset($_POST['tmon_action']) && $_POST['tmon_action'] === 'revoke_token' && check_admin_referer('tmon_admin_revoke_token')) {
        $site_url = esc_url_raw($_POST['site_url'] ?? '');
        if ($site_url) {
            $map = get_option('tmon_admin_uc_sites', []);
            if (isset($map[$site_url])) {
                $map[$site_url]['read_token'] = '';
                update_option('tmon_admin_uc_sites', $map);

                // Build endpoint & headers in scope and use safe helper
                $endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/read-token/set';
                $headers = ['Content-Type' => 'application/json'];
                $uc_key = $map[$site_url]['uc_key'] ?? '';
                if ($uc_key) $headers['X-TMON-ADMIN'] = $uc_key;
                $body = wp_json_encode(['read_token' => '']);

                $res = tmon_uc_safe_remote_post($endpoint, ['timeout' => 15, 'headers' => $headers, 'body' => $body], 'revoke_token');
                if (is_wp_error($res)) {
                    error_log('unit-connector: Failed to push revoke read token to UC ' . $site_url . ' error=' . $res->get_error_message());
                } else {
                    error_log('unit-connector: Pushed revoke read token to UC ' . $site_url . ' status=' . intval(wp_remote_retrieve_response_code($res)));
                }

                add_action('admin_notices', function(){ echo '<div class="updated"><p>Read token revoked and cleared on UC.</p></div>'; });
            } else {
                error_log('unit-connector: revoke_token called for unrecognized site_url=' . $site_url);
            }
        } else {
            error_log('unit-connector: revoke_token called without site_url');
        }
    }
});

// Ensure default Admin API URL shown in settings template comes from home_url()
// (The templates/settings.php already renders WORDPRESS_API_URL and we now default it there via schema)
add_filter('tmon_uc_default_options', function($defaults) {
    $defaults['admin_api_url'] = rtrim(home_url('/'), '/');
    return $defaults;
});
