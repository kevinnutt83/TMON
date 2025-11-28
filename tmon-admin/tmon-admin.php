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
// AJAX: Delete field data log
add_action('wp_ajax_tmon_admin_delete_field_data', function() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_ajax_referer('tmon_admin_file_ops');
    $file = sanitize_file_name($_GET['file'] ?? '');
    $log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
    $path = realpath($log_dir . '/' . $file);
    if ($path && strpos($path, realpath($log_dir)) === 0 && file_exists($path)) {
        unlink($path);
    }
    exit;
});
// AJAX: Download data history log
add_action('wp_ajax_tmon_admin_download_data_history', function() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_ajax_referer('tmon_admin_file_ops');
    $file = sanitize_file_name($_GET['file'] ?? '');
    $log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
    $path = realpath($log_dir . '/' . $file);
    if (!$path || strpos($path, realpath($log_dir)) !== 0 || !file_exists($path)) wp_die('Not found');
    header('Content-Type: text/plain');
    header('Content-Disposition: attachment; filename="' . basename($path) . '"');
    readfile($path);
    exit;
});

// AJAX: Delete data history log
add_action('wp_ajax_tmon_admin_delete_data_history', function() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_ajax_referer('tmon_admin_file_ops');
    $file = sanitize_file_name($_GET['file'] ?? '');
    $log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
    $path = realpath($log_dir . '/' . $file);
    if ($path && strpos($path, realpath($log_dir)) === 0 && file_exists($path)) {
        unlink($path);
    }
    exit;
});
// AJAX: Mark notification as read
add_action('wp_ajax_tmon_admin_mark_notification_read', function() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_ajax_referer('tmon_admin_notice');
    $id = intval($_POST['id'] ?? 0);
    $notices = get_option('tmon_admin_notifications', []);
    if (isset($notices[$id])) {
        $notices[$id]['read'] = true;
        update_option('tmon_admin_notifications', $notices);
        wp_send_json_success();
    }
    wp_send_json_error();
});

// AJAX: Update OTA job status
add_action('wp_ajax_tmon_admin_update_ota_status', function() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_ajax_referer('tmon_admin_ota');
    $id = intval($_POST['id'] ?? 0);
    $status = sanitize_text_field($_POST['status'] ?? '');
    $jobs = get_option('tmon_admin_ota_jobs', []);
    if (isset($jobs[$id])) {
        $jobs[$id]['status'] = $status;
        update_option('tmon_admin_ota_jobs', $jobs);
        wp_send_json_success();
    }
    wp_send_json_error();
});

// AJAX: Upload file (metadata only, not actual file storage)
add_action('wp_ajax_tmon_admin_upload_file', function() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_ajax_referer('tmon_admin_file_upload');
    $name = sanitize_text_field($_POST['name'] ?? '');
    $type = sanitize_text_field($_POST['type'] ?? '');
    $meta = $_POST['meta'] ?? [];
    do_action('tmon_admin_file_upload', [
        'name' => $name,
        'type' => $type,
        'meta' => $meta,
    ]);
    wp_send_json_success();
});

// Admin-post: file upload with metadata persistence
add_action('admin_post_tmon_admin_file_upload_post', function() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_admin_referer('tmon_admin_file_upload');
    $dir = WP_CONTENT_DIR . '/tmon-admin-packages';
    if (!is_dir($dir)) wp_mkdir_p($dir);
    require_once ABSPATH . 'wp-admin/includes/file.php';
    $ok = false; $stored = [];
    if (!empty($_FILES['package']['name'])) {
        $overrides = ['test_form' => false];
        $file = wp_handle_upload($_FILES['package'], $overrides);
        if (!isset($file['error'])) {
            $src = $file['file'];
            $dest = trailingslashit($dir) . basename($src);
            if (@rename($src, $dest) || @copy($src, $dest)) {
                $ok = true;
                $stored = [
                    'timestamp' => current_time('mysql'),
                    'name' => basename($dest),
                    'type' => pathinfo($dest, PATHINFO_EXTENSION),
                    'path' => $dest,
                ];
                $files = get_option('tmon_admin_files', []);
                if (!is_array($files)) $files = [];
                $files[] = $stored;
                update_option('tmon_admin_files', $files);
            }
        }
    }
    wp_redirect(admin_url('admin.php?page=tmon-admin-files&uploaded=' . ($ok ? '1' : '0')));
    exit;
});

// AJAX: Update group
add_action('wp_ajax_tmon_admin_update_group', function() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_ajax_referer('tmon_admin_group');
    $name = sanitize_text_field($_POST['name'] ?? '');
    $type = sanitize_text_field($_POST['type'] ?? '');
    $meta = $_POST['meta'] ?? [];
    do_action('tmon_admin_group_update', [
        'name' => $name,
        'type' => $type,
        'meta' => $meta,
    ]);
    wp_send_json_success();
});

// AJAX: Submit AI feedback
add_action('wp_ajax_tmon_admin_submit_ai_feedback', function() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_ajax_referer('tmon_admin_ai_feedback');
    $user_id = get_current_user_id();
    $feedback = sanitize_text_field($_POST['feedback'] ?? '');
    do_action('tmon_admin_ai_feedback', [
        'user_id' => $user_id,
        'feedback' => $feedback,
    ]);
    wp_send_json_success();
});

// --- Provisioning queue helpers ---
// Persist queued provisioning actions keyed by unit_id or machine_id.
function tmon_admin_enqueue_provision($key, $payload) {
    if (!$key || !is_string($key)) return false;
    $queue = get_option('tmon_admin_pending_provision', []);
    if (!is_array($queue)) $queue = [];
    $payload['requested_at'] = current_time('mysql');
    $payload['status'] = 'pending';
    $queue[$key] = $payload;
    update_option('tmon_admin_pending_provision', $queue);
    return true;
}

function tmon_admin_get_pending_provision($key) {
    if (!$key || !is_string($key)) return null;
    $queue = get_option('tmon_admin_pending_provision', []);
    if (!is_array($queue)) return null;
    return $queue[$key] ?? null;
}

function tmon_admin_dequeue_provision($key) {
    if (!$key || !is_string($key)) return null;
    $queue = get_option('tmon_admin_pending_provision', []);
    if (!is_array($queue) || !isset($queue[$key])) return null;
    $entry = $queue[$key];
    unset($queue[$key]);
    update_option('tmon_admin_pending_provision', $queue);
    return $entry;
}

// Admin-post: Save provisioning settings (persist repo/branch/manifest info for a unit)
add_action('admin_post_tmon_admin_save_provision', function() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_admin_referer('tmon_admin_provision');

    global $wpdb;
    $table = $wpdb->prefix . 'tmon_provisioned_devices';

    $unit_id = isset($_POST['unit_id']) ? sanitize_text_field($_POST['unit_id']) : '';
    $machine_id = isset($_POST['machine_id']) ? sanitize_text_field($_POST['machine_id']) : '';
    $repo = isset($_POST['repo']) ? sanitize_text_field($_POST['repo']) : '';
    $branch = isset($_POST['branch']) ? sanitize_text_field($_POST['branch']) : 'main';
    $manifest_url = isset($_POST['manifest_url']) ? esc_url_raw($_POST['manifest_url']) : '';
    $version = isset($_POST['version']) ? sanitize_text_field($_POST['version']) : '';
    $notes = isset($_POST['notes']) ? sanitize_textarea_field($_POST['notes']) : '';
    $site_url = isset($_POST['site_url']) ? esc_url_raw($_POST['site_url']) : '';
    $unit_name = isset($_POST['unit_name']) ? sanitize_text_field($_POST['unit_name']) : '';

    if (!$unit_id && !$machine_id) {
        wp_safe_redirect(add_query_arg('saved', '0', wp_get_referer() ?: admin_url('admin.php?page=tmon-admin-provisioning')));
        exit;
    }

    // Build metadata for notes (preserve existing notes if JSON stored)
    $meta = [
        'repo' => $repo,
        'branch' => $branch,
        'manifest_url' => $manifest_url,
        'firmware_version' => $version,
        'site_url' => $site_url,
        'unit_name' => $unit_name,
    ];
    if ($notes !== '') {
        $meta['notes_text'] = $notes;
    }

    // Find existing row by unit_id or machine_id
    $where_sql = '';
    $params = [];
    if ($unit_id) {
        $where_sql = "unit_id = %s";
        $params[] = $unit_id;
    } elseif ($machine_id) {
        $where_sql = "machine_id = %s";
        $params[] = $machine_id;
    }

    $row = null;
    if ($where_sql) {
        $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table} WHERE {$where_sql} LIMIT 1", $params));
    }

    if ($row) {
        // Merge incoming metadata into existing notes JSON (if present)
        $old_notes = [];
        if (!empty($row->notes)) {
            $old = json_decode($row->notes, true);
            if (is_array($old)) { $old_notes = $old; }
        }
        $new_notes = array_merge($old_notes, $meta);
        $update = [
            'notes' => wp_json_encode($new_notes),
            'status' => 'provisioned',
            'settings_staged' => 1, // mark staged
        ];
        $where = [ 'id' => intval($row->id) ];
        $updated = $wpdb->update($table, $update, $where, ['%s','%s','%d'], ['%d']);
        error_log('tmon-admin: Updated provisioning row ID=' . intval($row->id) . ' by user=' . get_current_user()->user_login . ' meta=' . wp_json_encode($meta));
    } else {
        // Insert new provisioned row
        $insert = [
            'unit_id' => $unit_id,
            'machine_id' => $machine_id,
            'company_id' => '',
            'plan' => 'default',
            'status' => 'provisioned',
            'notes' => wp_json_encode($meta),
            'settings_staged' => 1, // mark staged
            'created_at' => current_time('mysql'),
        ];
        $wpdb->insert($table, $insert, ['%s','%s','%s','%s','%s','%d','%s']);
        $insert_id = $wpdb->insert_id;
        error_log('tmon-admin: Inserted provisioning row ID=' . intval($insert_id) . ' by user=' . get_current_user()->user_login . ' meta=' . wp_json_encode($meta));
    }

    // Enqueue provisioning payload for the device (use machine_id if present else unit_id)
    $key_machine = $machine_id ?: '';
    $key_unit = $unit_id ?: '';

    // Enqueue for both machine_id and unit_id
    $payload_user = $meta;
    $payload_user['requested_by_user'] = wp_get_current_user()->user_login;
    if ($key_machine) {
        tmon_admin_enqueue_provision($key_machine, $payload_user);
        error_log('tmon-admin: enqueued provision for machine ' . $key_machine);
    }
    if ($key_unit && $key_unit !== $key_machine) {
        tmon_admin_enqueue_provision($key_unit, $payload_user);
        error_log('tmon-admin: enqueued provision for unit ' . $key_unit);
    }

    // Mirror: update tmon_devices to reflect provisioned and set site/unit name
    $dev_table = $wpdb->prefix . 'tmon_devices';
    if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $dev_table))) {
        $upd = ['provisioned' => 1, 'last_seen' => current_time('mysql')];
        if (!empty($site_url)) $upd['wordpress_api_url'] = $site_url;
        if (!empty($unit_name)) $upd['unit_name'] = $unit_name;
        $where = [];
        if (!empty($unit_id)) $where = ['unit_id' => $unit_id];
        elseif (!empty($machine_id)) $where = ['machine_id' => $machine_id];

        if (!empty($where)) {
            $ok = $wpdb->update($dev_table, $upd, $where);
            if ($ok === false) {
                error_log('tmon-admin: failed to update tmon_devices for provisioning: ' . $wpdb->last_error);
            } else {
                error_log('tmon-admin: updated tmon_devices provisioned state for ' . json_encode($where));
            }
        }
    }

    // Add admin notice for save success
    add_action('admin_notices', function() {
        echo '<div class="updated"><p>Provisioning saved and queued for next device check-in.</p></div>';
    });

    // Redirect back with status
    wp_safe_redirect(add_query_arg('saved', '1', wp_get_referer() ?: admin_url('admin.php?page=tmon-admin-provisioning')));
    exit;
});

// AJAX: Update device repo metadata inline (returns JSON)
add_action('wp_ajax_tmon_admin_update_device_repo', function() {
    if (!current_user_can('manage_options')) {
        wp_send_json_error(['message' => 'forbidden']);
    }
    check_ajax_referer('tmon_admin_provision_ajax');

    $unit_id = isset($_POST['unit_id']) ? sanitize_text_field($_POST['unit_id']) : '';
    $machine_id = isset($_POST['machine_id']) ? sanitize_text_field($_POST['machine_id']) : '';
    $repo = isset($_POST['repo']) ? sanitize_text_field($_POST['repo']) : '';
    $branch = isset($_POST['branch']) ? sanitize_text_field($_POST['branch']) : 'main';
    $manifest_url = isset($_POST['manifest_url']) ? esc_url_raw($_POST['manifest_url']) : '';
    $version = isset($_POST['version']) ? sanitize_text_field($_POST['version']) : '';
    $site_url = isset($_POST['site_url']) ? esc_url_raw($_POST['site_url']) : '';
    $unit_name = isset($_POST['unit_name']) ? sanitize_text_field($_POST['unit_name']) : '';

    if (!$unit_id && !$machine_id) {
        wp_send_json_error(['message' => 'unit_id or machine_id is required'], 400);
    }

    global $wpdb;
    $table = $wpdb->prefix . 'tmon_provisioned_devices';
    $where_sql = '';
    $params = [];
    if ($unit_id) { $where_sql = "unit_id = %s"; $params[] = $unit_id; }
    else { $where_sql = "machine_id = %s"; $params[] = $machine_id; }

    $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table} WHERE {$where_sql} LIMIT 1", $params));
    $meta = [
        'repo' => $repo,
        'branch' => $branch,
        'manifest_url' => $manifest_url,
        'firmware_version' => $version,
        'site_url' => $site_url,
        'unit_name' => $unit_name,
    ];

    if ($row) {
        $old_notes = [];
        if (!empty($row->notes)) {
            $old = json_decode($row->notes, true);
            if (is_array($old)) { $old_notes = $old; }
        }
        $new_notes = array_merge($old_notes, $meta);
        $updated = $wpdb->update($table, [ 'notes' => wp_json_encode($new_notes) ], [ 'id' => intval($row->id) ], ['%s'], ['%d']);
        if (false === $updated) {
            wp_send_json_error(['message' => 'DB update failed']);
        }
        $key_machine = $machine_id ?: '';
        $key_unit = $unit_id ?: '';
        $payload = $meta; $payload['requested_by_user'] = wp_get_current_user()->user_login;
        if ($key_machine) {
            tmon_admin_enqueue_provision($key_machine, $payload);
            error_log('tmon-admin: ajax enqueued provision for machine ' . $key_machine);
        }
        if ($key_unit && $key_unit !== $key_machine) {
            tmon_admin_enqueue_provision($key_unit, $payload);
            error_log('tmon-admin: ajax enqueued provision for unit ' . $key_unit);
        }

        // Mirror update
        $dev_table = $wpdb->prefix . 'tmon_devices';
        if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $dev_table))) {
            $upd = ['provisioned' => 1, 'last_seen' => current_time('mysql')];
            if (!empty($site_url)) $upd['wordpress_api_url'] = $site_url;
            if (!empty($unit_name)) $upd['unit_name'] = $unit_name;
            if (!empty($unit_id)) $wpdb->update($dev_table, $upd, ['unit_id' => $unit_id]);
            elseif (!empty($machine_id)) $wpdb->update($dev_table, $upd, ['machine_id' => $machine_id]);
        }

        wp_send_json_success(['message' => 'updated', 'notes' => $new_notes]);
    } else {
        $insert = [
            'unit_id' => $unit_id,
            'machine_id' => $machine_id,
            'company_id' => '',
            'plan' => 'default',
            'status' => 'provisioned',
            'notes' => wp_json_encode($meta),
            'created_at' => current_time('mysql'),
        ];
        $ok = $wpdb->insert($table, $insert, ['%s','%s','%s','%s','%s','%s']);
        error_log('tmon-admin: Ajax inserted provisioning row for key=' . $key . ' user=' . wp_get_current_user()->user_login . ' payload=' . wp_json_encode($payload));
        wp_send_json_success(['message' => 'inserted', 'notes' => $meta]);
    }
});

if (!defined('ABSPATH')) exit;

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
		require_once TMON_ADMIN_PATH . 'includes/api.php';              // contains renamed AJAX handler
		require_once TMON_ADMIN_PATH . 'includes/provisioning.php';
		require_once TMON_ADMIN_PATH . 'includes/ai.php';
		require_once TMON_ADMIN_PATH . 'includes/audit.php';
		require_once TMON_ADMIN_PATH . 'includes/notifications.php';   // fixed signature
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

// Install/upgrade schema
if (!function_exists('tmon_admin_install_schema')) {
	// Provided in includes/db.php; ensure it exists before hook usage.
}

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
		'provisionNonce' => wp_create_nonce('tmon_admin_provision_ajax'), // <--- new
	];
	wp_localize_script('tmon-admin', 'TMON_ADMIN', $localized);

	// For arbitrary data, prefer inline script:
	// wp_add_inline_script('tmon-admin', 'window.TMON_ADMIN_EXTRA = ' . wp_json_encode($extra) . ';', 'before');
});

add_action('admin_menu', 'tmon_admin_menu');
function tmon_admin_menu() {
    // Compute unread notifications count for bubble
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
    add_submenu_page(
        'tmon-admin',
        'TMON Settings',
        'Settings',
        'manage_options',
        'tmon-admin-settings',
        'tmon_admin_settings_page'
    );

    add_submenu_page('tmon-admin', 'Audit Log', 'Audit Log', 'manage_options', 'tmon-admin-audit', 'tmon_admin_audit_page');
    add_submenu_page('tmon-admin', 'Notifications', 'Notifications', 'manage_options', 'tmon-admin-notifications', 'tmon_admin_notifications_page');
    add_submenu_page('tmon-admin', 'OTA Jobs', 'OTA Jobs', 'manage_options', 'tmon-admin-ota', 'tmon_admin_ota_page');
    add_submenu_page('tmon-admin', 'Files', 'Files', 'manage_options', 'tmon-admin-files', 'tmon_admin_files_page');
    add_submenu_page('tmon-admin', 'Groups', 'Groups', 'manage_options', 'tmon-admin-groups', 'tmon_admin_groups_page');
    add_submenu_page('tmon-admin', 'Custom Code', 'Custom Code', 'manage_options', 'tmon-admin-custom-code', 'tmon_admin_custom_code_page');
    add_submenu_page('tmon-admin', 'Data Export', 'Data Export', 'manage_options', 'tmon-admin-export', 'tmon_admin_export_page');
    add_submenu_page('tmon-admin', 'AI Feedback', 'AI Feedback', 'manage_options', 'tmon-admin-ai-feedback', 'tmon_admin_ai_feedback_page');

    add_submenu_page('tmon-admin', 'Provisioning', 'Provisioning', 'manage_options', 'tmon-admin-provisioning', 'tmon_admin_provisioning_page');

    add_submenu_page('tmon-admin', 'Field Data Log', 'Field Data Log', 'manage_options', 'tmon-admin-field-data', 'tmon_admin_field_data_page');
        add_submenu_page('tmon-admin', 'Data History Log', 'Data History Log', 'manage_options', 'tmon-admin-data-history', 'tmon_admin_data_history_page');
    add_submenu_page('tmon-admin', 'Device Location', 'Device Location', 'manage_options', 'tmon-admin-location', 'tmon_admin_location_page');
    add_submenu_page('tmon-admin', 'UC Pairings', 'UC Pairings', 'manage_options', 'tmon-admin-pairings', 'tmon_admin_pairings_page');
}
function tmon_admin_data_history_page() {
    require TMON_ADMIN_PATH . 'templates/data-history.php';
}
function tmon_admin_field_data_page() {
    require TMON_ADMIN_PATH . 'templates/field-data.php';
}

function tmon_admin_dashboard_page() {
    require TMON_ADMIN_PATH . 'templates/dashboard.php';
}

function tmon_admin_settings_page() {
    require TMON_ADMIN_PATH . 'templates/settings.php';
}

function tmon_admin_audit_page() {
    require TMON_ADMIN_PATH . 'templates/audit.php';
}
function tmon_admin_notifications_page() {
    require TMON_ADMIN_PATH . 'templates/notifications.php';
}
function tmon_admin_ota_page() {
    require TMON_ADMIN_PATH . 'templates/ota.php';
}
function tmon_admin_files_page() {
    require TMON_ADMIN_PATH . 'templates/files.php';
}
function tmon_admin_groups_page() {
    require TMON_ADMIN_PATH . 'templates/groups.php';
}
function tmon_admin_custom_code_page() {
    require TMON_ADMIN_PATH . 'templates/custom-code.php';
}
function tmon_admin_export_page() {
    require TMON_ADMIN_PATH . 'templates/export.php';
}
function tmon_admin_ai_feedback_page() {
    require TMON_ADMIN_PATH . 'templates/ai-feedback.php';
}

function tmon_admin_pairings_page(){
    echo '<div class="wrap"><h1>Unit Connector Pairings</h1>';
    $hub_key = get_option('tmon_admin_uc_key', '');
    echo '<p><b>Hub Shared Key:</b> <code>' . esc_html($hub_key) . '</code></p>';
    $map = get_option('tmon_admin_uc_sites', []);
    if (!is_array($map) || empty($map)) {
        echo '<p><em>No Unit Connector sites paired yet.</em></p>';
    } else {
        echo '<table class="widefat"><thead><tr><th>Site URL</th><th>UC Key</th><th>Read Token</th><th>Paired At</th><th>Actions</th></tr></thead><tbody>';
        foreach ($map as $url => $info) {
            echo '<tr>';
            echo '<td>'.esc_html($url).'</td>';
            echo '<td><code>'.esc_html($info['uc_key'] ?? '').'</code></td>';
            echo '<td><code>'.esc_html($info['read_token'] ?? '').'</code></td>';
            echo '<td>'.esc_html($info['paired_at'] ?? '').'</td>';
            echo '<td>';
            echo '<form method="post" style="display:inline-block;margin-right:6px">';
            wp_nonce_field('tmon_admin_rotate_token');
            echo '<input type="hidden" name="tmon_action" value="rotate_token" />';
            echo '<input type="hidden" name="site_url" value="'.esc_attr($url).'" />';
            submit_button('Regenerate Read Token', 'secondary', '', false);
            echo '</form>';
            echo '<form method="post" style="display:inline-block">';
            wp_nonce_field('tmon_admin_revoke_token');
            echo '<input type="hidden" name="tmon_action" value="revoke_token" />';
            echo '<input type="hidden" name="site_url" value="'.esc_attr($url).'" />';
            submit_button('Revoke', 'delete', '', false);
            echo '</form>';
            echo '</td>';
            echo '</tr>';
        }
        echo '</tbody></table>';
    }
    echo '</div>';
}

// Keep a single activation + upgrade flow and enqueue block already present above.
// Add the token rotation/revocation handlers here (moved up from the bottom so we can delete duplicates below).
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
                // Push to UC
                $endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/read-token/set';
                $headers = ['Content-Type'=>'application/json'];
                $uc_key = $map[$site_url]['uc_key'] ?? '';
                if ($uc_key) $headers['X-TMON-ADMIN'] = $uc_key;
                wp_remote_post($endpoint, ['timeout'=>15,'headers'=>$headers,'body'=>wp_json_encode(['read_token'=>$token])]);
                add_action('admin_notices', function(){ echo '<div class="updated"><p>Read token regenerated and pushed to UC.</p></div>'; });
            }
        }
    }

    if (isset($_POST['tmon_action']) && $_POST['tmon_action'] === 'revoke_token' && check_admin_referer('tmon_admin_revoke_token')) {
        $site_url = esc_url_raw($_POST['site_url'] ?? '');
        if ($site_url) {
            $map = get_option('tmon_admin_uc_sites', []);
            if (isset($map[$site_url])) {
                $map[$site_url]['read_token'] = '';
                update_option('tmon_admin_uc_sites', $map);
                // Push revoke to UC
                $endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/read-token/set';
                $headers = ['Content-Type'=>'application/json'];
                $uc_key = $map[$site_url]['uc_key'] ?? '';
                if ($uc_key) $headers['X-TMON-ADMIN'] = $uc_key;
                wp_remote_post($endpoint, ['timeout'=>15,'headers'=>$headers,'body'=>wp_json_encode(['read_token'=>''])]);
                add_action('admin_notices', function(){ echo '<div class="updated"><p>Read token revoked and cleared on UC.</p></div>'; });
            }
        }
    }
});

// --- Consolidated manifest fetch helpers (used by both REST & admin-ajax) ---
if (!function_exists('tmon_admin_build_manifest_try_urls')) {
	function tmon_admin_build_manifest_try_urls($manifest_url = '', $repo = '', $branch = 'main') {
		$try_urls = [];

		// If explicit manifest URL provided, prefer that
		if (!empty($manifest_url)) {
			$manifest_url = trim($manifest_url);
			// Convert GitHub 'blob' and 'tree' URL forms to raw.githubusercontent equivalents
			if (preg_match('#^https?://github\.com/([^/]+/[^/]+)/(?:blob|tree)/([^/]+)/(.*)$#', $manifest_url, $m)) {
				$ownerrepo = $m[1];      // owner/repo
				$url_branch = $m[2];     // branch (may be 'main' etc.)
				$path = $m[3];           // path inside repo
				$try_urls[] = "https://raw.githubusercontent.com/{$ownerrepo}/{$url_branch}/{$path}";
				// Also try the 'master' branch fallback if different
				if ($url_branch !== 'master') {
					$try_urls[] = "https://raw.githubusercontent.com/{$ownerrepo}/master/{$path}";
				}
			} elseif (preg_match('#^https?://github\.com/([^/]+/[^/]+)/(.*)$#', $manifest_url, $m)) {
				// Generic GitHub URL (owner/repo/<something>), try store path as-is using default branch.
				$ownerrepo = $m[1];
				$path = $m[2];
				$try_urls[] = "https://raw.githubusercontent.com/{$ownerrepo}/{$branch}/{$path}";
				if ($branch !== 'master') {
					$try_urls[] = "https://raw.githubusercontent.com/{$ownerrepo}/master/{$path}";
				}
			} else {
				// Non-GitHub URL or raw already: use provided URL
				$try_urls[] = esc_url_raw($manifest_url);
			}
			return $try_urls;
		}

		// Fallback default repo for firmware (explicit GitHub 'tree' URL).
		// This was requested: https://github.com/kevinnutt83/TMON/tree/main/micropython
		if (empty($repo)) {
			$repo = 'https://github.com/kevinnutt83/TMON/tree/main/micropython';
		}

		$repo = trim($repo, " \t\n\r/");

		// If raw.githubusercontent URL passed directly, use it
		if (preg_match('#^https?://raw\.githubusercontent\.com/#', $repo)) {
			$try_urls[] = $repo;
			return $try_urls;
		}

		// If repo looks like a GitHub full URL with /tree or /blob, extract owner/repo/branch/path
		if (preg_match('#^https?://github\.com/([^/]+/[^/]+)/(?:blob|tree)/([^/]+)/(.*)$#', $repo, $m)) {
			$ownerrepo = $m[1];
			$url_branch = $m[2];
			$path = $m[3];
			$try_urls[] = "https://raw.githubusercontent.com/{$ownerrepo}/{$url_branch}/{$path}";
			if ($url_branch !== 'master') {
				$try_urls[] = "https://raw.githubusercontent.com/{$ownerrepo}/master/{$path}";
			}
			return $try_urls;
		}

		$parts = explode('/', $repo);
		if (count($parts) > 2) {
			// owner/repo/path/to/file
			$owner = $parts[0];
			$r = $parts[1];
			$path = implode('/', array_slice($parts, 2));
			$try_urls[] = "https://raw.githubusercontent.com/{$owner}/{$r}/{$branch}/{$path}";
			if ($branch !== 'master') {
				$try_urls[] = "https://raw.githubusercontent.com/{$owner}/{$r}/master/{$path}";
			}
		} else {
			// owner/repo -> try root manifest.json and version.txt
			$try_urls[] = "https://raw.githubusercontent.com/{$repo}/{$branch}/manifest.json";
			$try_urls[] = "https://raw.githubusercontent.com/{$repo}/{$branch}/version.txt";
			if ($branch !== 'master') {
				$try_urls[] = "https://raw.githubusercontent.com/{$repo}/master/manifest.json";
				$try_urls[] = "https://raw.githubusercontent.com/{$repo}/master/version.txt";
			}
		}
		return $try_urls;
	}
}

if (!function_exists('tmon_admin_fetch_manifest_from_try_urls')) {
	function tmon_admin_fetch_manifest_from_try_urls($try_urls = []) {
		$errors = [];
		foreach ((array)$try_urls as $u) {
			$u = esc_url_raw($u);
			$res = wp_remote_get($u, [
				'timeout' => 12,
				'headers' => ['Accept' => 'application/json, text/plain'],
			]);
			if (is_wp_error($res)) {
				$errors[] = sprintf('Request to %s failed: %s', $u, $res->get_error_message());
				continue;
			}
			$code = intval(wp_remote_retrieve_response_code($res));
			$body = wp_remote_retrieve_body($res);
			if ($code !== 200 || !$body) {
				$errors[] = sprintf('%s returned status %d', $u, $code);
				continue;
			}
			$decoded = json_decode($body, true);
			if (json_last_error() === JSON_ERROR_NONE && is_array($decoded)) {
				return ['success' => true, 'source' => $u, 'data' => $decoded, 'errors' => []];
			}
			$trim = trim($body);
			if (preg_match('/^v?\d+(\.\d+){0,3}$/', $trim) || strlen($trim) < 128) {
				return ['success' => true, 'source' => $u, 'version_text' => $trim, 'errors' => []];
			}
			if (strlen($trim) > 0 && strlen($trim) < 100000) {
				return ['success' => true, 'source' => $u, 'raw_text' => $trim, 'errors' => []];
			}
			$errors[] = sprintf('%s returned unknown content (len=%d)', $u, (int)strlen($body));
		}
		return ['success' => false, 'errors' => $errors];
	}
}

// Replace previous inline REST & admin-ajax manifest code with consolidated versions
// REST route: /wp-json/tmon-admin/v1/github/manifest
add_action('rest_api_init', function() {
	register_rest_route('tmon-admin/v1', '/github/manifest', [
		'methods' => WP_REST_Server::ALLMETHODS,
		'permission_callback' => function() { return current_user_can('manage_options'); },
		'callback' => function( WP_REST_Request $request ) {
			$params = $request->get_params();
			$manifest_url = isset($params['manifest_url']) ? trim($params['manifest_url']) : '';
			$repo = isset($params['repo']) ? trim($params['repo']) : '';
			$branch = isset($params['branch']) ? trim($params['branch']) : 'main';

			$try_urls = tmon_admin_build_manifest_try_urls($manifest_url, $repo, $branch);
			if (empty($try_urls)) {
				return rest_ensure_response(['success' => false, 'message' => 'manifest_url or repo parameter required', 'errors' => ['missing params']]);
			}
			$result = tmon_admin_fetch_manifest_from_try_urls($try_urls);
			if ($result['success']) {
				return rest_ensure_response($result);
			}
			return rest_ensure_response(['success' => false, 'message' => 'manifest or version file not found', 'errors' => $result['errors']]);
		}
	]);
});

// Backwards compatible admin-ajax endpoint (GET/POST).
add_action('wp_ajax_tmon_admin_fetch_github_manifest', function() {
	if (!current_user_can('manage_options')) {
		wp_send_json_error(['message' => 'forbidden']);
	}
	$manifest_url = isset($_REQUEST['manifest_url']) ? sanitize_text_field(wp_unslash($_REQUEST['manifest_url'])) : '';
	$repo = isset($_REQUEST['repo']) ? sanitize_text_field(wp_unslash($_REQUEST['repo'])) : '';
	$branch = isset($_REQUEST['branch']) ? sanitize_text_field(wp_unslash($_REQUEST['branch'])) : 'main';

	$try_urls = tmon_admin_build_manifest_try_urls($manifest_url, $repo, $branch);
	if (empty($try_urls)) { wp_send_json_error(['message' => 'manifest_url or repo parameter required']); }

	$result = tmon_admin_fetch_manifest_from_try_urls($try_urls);
	if ($result['success']) {
		$wp_data = [];
		if (isset($result['data'])) $wp_data['data'] = $result['data'];
		if (isset($result['version_text'])) $wp_data['version_text'] = $result['version_text'];
		if (isset($result['raw_text'])) $wp_data['raw_text'] = $result['raw_text'];
		$wp_data['source'] = $result['source'];
		wp_send_json_success($wp_data);
	} else {
		// Return JSON error payload (HTTP 200) with extra errors to avoid 404 console noise.
		wp_send_json_error(['message' => 'manifest or version file not found', 'errors' => $result['errors'] ?? []]);
	}
});
