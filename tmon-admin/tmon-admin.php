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

    // Ensure we set settings_staged=1 when saving provisioned row (done in insert/update earlier)
    // Build payload for enqueuing and include site_url + unit_name
    $payload = $meta;
    $payload['site_url'] = $site_url;
    $payload['unit_name'] = $unit_name;
    $payload['requested_by_user'] = wp_get_current_user()->user_login;

    // Enqueue provisioning for both machine_id and unit_id
    if ($machine_id) {
        tmon_admin_enqueue_provision($machine_id, $payload);
        error_log('tmon-admin: enqueued provision for machine_id=' . $machine_id);
    }
    if ($unit_id && $unit_id !== $machine_id) {
        tmon_admin_enqueue_provision($unit_id, $payload);
        error_log('tmon-admin: enqueued provision for unit_id=' . $unit_id);
    }

    // Mirror to tmon_devices if table exists
    global $wpdb;
    $dev_table = $wpdb->prefix . 'tmon_devices';
    if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $dev_table))) {
        $dev_cols = $wpdb->get_col("SHOW COLUMNS FROM {$dev_table}");
        $mirror_update = ['last_seen' => current_time('mysql')];

        // Mark provisioned
        if (in_array('provisioned', $dev_cols)) {
            $mirror_update['provisioned'] = 1;
        } elseif (in_array('status', $dev_cols)) {
            $mirror_update['status'] = 'provisioned';
        }

        // Update both site_url and wordpress_api_url columns if present
        if (!empty($site_url)) {
            if (in_array('site_url', $dev_cols)) $mirror_update['site_url'] = $site_url;
            if (in_array('wordpress_api_url', $dev_cols)) $mirror_update['wordpress_api_url'] = $site_url;
        }
        if (!empty($unit_name) && in_array('unit_name', $dev_cols)) $mirror_update['unit_name'] = $unit_name;
        if (in_array('provisioned_at', $dev_cols)) $mirror_update['provisioned_at'] = current_time('mysql');

        if (!empty($unit_id)) {
            $wpdb->update($dev_table, $mirror_update, ['unit_id' => $unit_id]);
            error_log("tmon-admin: mirrored provision data to tmon_devices for unit_id={$unit_id}");
        } elseif (!empty($machine_id)) {
            $wpdb->update($dev_table, $mirror_update, ['machine_id' => $machine_id]);
            error_log("tmon-admin: mirrored provision data to tmon_devices for machine_id={$machine_id}");
        } else {
            error_log("tmon-admin: No unit_id/machine_id available to mirror to tmon_devices.");
        }
    }

    // Append auditing history of this provisioning action
    $history = get_option('tmon_admin_provision_history', []);
    $history[] = [
        'ts' => current_time('mysql'),
        'user' => wp_get_current_user()->user_login,
        'unit_id' => $unit_id,
        'machine_id' => $machine_id,
        'site_url' => $site_url,
        'unit_name' => $unit_name,
        'meta' => $meta,
    ];
    update_option('tmon_admin_provision_history', array_slice($history, -500)); // keep last 500 entries

    // Add admin notice for save success
    add_action('admin_notices', function() {
        echo '<div class="updated"><p>Provisioning saved and queued for next device check-in.</p></div>';
    });

    // Redirect back with status
    wp_safe_redirect(add_query_arg('saved', '1', wp_get_referer() ?: admin_url('admin.php?page=tmon-admin-provisioning')));
    exit;
});

// AJAX: Enqueue from inline edit
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
        $key1 = $machine_id ?: '';
        $key2 = $unit_id ?: '';
        $payload = $meta;
        $payload['site_url'] = $site_url;
        $payload['unit_name'] = $unit_name;
        $payload['requested_by_user'] = wp_get_current_user()->user_login;

        if ($key1) {
            tmon_admin_enqueue_provision($key1, $payload);
            error_log('tmon-admin: Ajax enqueued for ' . $key1);
        }
        if ($key2 && $key2 !== $key1) {
            tmon_admin_enqueue_provision($key2, $payload);
            error_log('tmon-admin: Ajax enqueued for ' . $key2);
        }

        // Mirror to tmon_devices as above
        global $wpdb;
        $dev_table = $wpdb->prefix . 'tmon_devices';
        if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $dev_table))) {
            $dev_cols = $wpdb->get_col("SHOW COLUMNS FROM {$dev_table}");
            $mirror_update = ['last_seen' => current_time('mysql')];
            if (in_array('provisioned', $dev_cols)) $mirror_update['provisioned'] = 1;
            elseif (in_array('status', $dev_cols)) $mirror_update['status'] = 'provisioned';
            if (!empty($site_url) && in_array('site_url', $dev_cols)) $mirror_update['site_url'] = $site_url;
            if (!empty($site_url) && in_array('wordpress_api_url', $dev_cols)) $mirror_update['wordpress_api_url'] = $site_url;
            if (!empty($unit_name) && in_array('unit_name', $dev_cols)) $mirror_update['unit_name'] = $unit_name;
            if (in_array('provisioned_at', $dev_cols)) $mirror_update['provisioned_at'] = current_time('mysql');

            if (!empty($unit_id)) $wpdb->update($dev_table, $mirror_update, ['unit_id' => $unit_id]);
            elseif (!empty($machine_id)) $wpdb->update($dev_table, $mirror_update, ['machine_id' => $machine_id]);
        }

        wp_send_json_success(['message' => 'queued & mirrored']);
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

    // Settings, Audit, etc.
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

// Replace the previous single 'Provisioning' page with three pages:
// - tmon_admin_provisioning_page (UI for adding/updating provisioning)
// - tmon_admin_provisioned_devices_page (lists devices; fallback to hub REST if DB missing)
// - tmon_admin_provisioning_activity_page (pending queue + history)
// - tmon_admin_provisioning_history_page (historical events)

function tmon_admin_provisioning_activity_page() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    $queue = get_option('tmon_admin_pending_provision', []);
    $history = get_option('tmon_admin_provision_history', []);
    echo '<div class="wrap"><h1>Provisioning Activity</h1>';
    // Pending queue table
    echo '<h2>Pending Provision Queue</h2>';
    echo '<table class="widefat"><thead><tr><th>Key</th><th>Payload</th><th>Actions</th></tr></thead><tbody>';
    foreach ((array)$queue as $k => $payload) {
        echo '<tr>';
        echo '<td>'.esc_html($k).'</td>';
        echo '<td><pre>'.esc_html(wp_json_encode($payload)).'</pre></td>';
        echo '<td>';
        echo '<button class="button tmon-pending-requeue" data-key="'.esc_attr($k).'">Re-enqueue</button> ';
        echo '<button class="button tmon-pending-delete" data-key="'.esc_attr($k).'">Delete</button>';
        echo '</td>';
        echo '</tr>';
    }
    echo '</tbody></table>';

    // History table
    echo '<h2>Provisioning History</h2>';
    echo '<table class="widefat"><thead><tr><th>Time</th><th>User</th><th>Unit ID</th><th>Machine ID</th><th>Site URL</th><th>Notes</th></tr></thead><tbody>';
    foreach (array_reverse((array)$history) as $h) {
        echo '<tr>';
        echo '<td>'.esc_html($h['ts'] ?? '').'</td>';
        echo '<td>'.esc_html($h['user'] ?? '').'</td>';
        echo '<td>'.esc_html($h['unit_id'] ?? '').'</td>';
        echo '<td>'.esc_html($h['machine_id'] ?? '').'</td>';
        echo '<td>'.esc_html($h['site_url'] ?? '').'</td>';
        echo '<td><pre>'.esc_html(wp_json_encode($h['meta'] ?? '')).'</pre></td>';
        echo '</tr>';
    }
    echo '</tbody></table>';
    echo '</div>';

    // JS for re-enqueue/delete actions calls tmon_admin_manage_pending AJAX endpoint (already implemented)
    echo <<<JS
<script>
(function($){
    $('.tmon-pending-delete').on('click', function(){
        var key = $(this).data('key');
        if (!confirm('Delete pending provision for ' + key + '?')) return;
        $.post(ajaxurl, { action:'tmon_admin_manage_pending', manage_action:'delete', key:key, _ajax_nonce:'".wp_create_nonce('tmon_admin_provision_ajax')."' }, function(resp){
            if (resp.success) location.reload();
            else alert('Failed: '+(resp.data.message||'unknown'));
        });
    });
    $('.tmon-pending-requeue').on('click', function(){ var key = $(this).data('key'); var payload = prompt('JSON payload to reenqueue (leave empty to reuse stored):'); try { if (payload) payload = JSON.parse(payload); else payload = ''; } catch(e){ alert('Invalid JSON'); return; } $.post(ajaxurl, { action:'tmon_admin_manage_pending', manage_action:'reenqueue', key:key, payload: JSON.stringify(payload), _ajax_nonce:'".wp_create_nonce('tmon_admin_provision_ajax')."' }, function(resp){ if (resp.success) location.reload(); else alert('Failed'); }); });
})(jQuery);
</script>
JS;
}

// The existing "Provisioning" page function should remain but be renamed logically if desired.
// Also implement tmon_admin_provisioning_history_page and tmon_admin_provisioned_devices_page (see provisioning.php)
