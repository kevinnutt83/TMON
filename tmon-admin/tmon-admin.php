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
if (!function_exists('tmon_admin_enqueue_provision')) {
    function tmon_admin_enqueue_provision($key, $payload) {
        if (!$key || !is_string($key)) return false;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue)) $queue = [];
        $payload['requested_at'] = current_time('mysql');
        $payload['status'] = 'pending';
        $queue[$key] = $payload;
        update_option('tmon_admin_pending_provision', $queue);
        error_log('tmon-admin: enqueue_provision called for key=' . $key . ' payload=' . wp_json_encode($payload));
        return true;
    }
}

if (!function_exists('tmon_admin_get_pending_provision')) {
    function tmon_admin_get_pending_provision($key) {
        if (!$key || !is_string($key)) return null;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue)) return null;
        return isset($queue[$key]) ? $queue[$key] : null;
    }
}

if (!function_exists('tmon_admin_dequeue_provision')) {
    function tmon_admin_dequeue_provision($key) {
        if (!$key || !is_string($key)) return null;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue) || !isset($queue[$key])) return null;
        $entry = $queue[$key];
        unset($queue[$key]);
        update_option('tmon_admin_pending_provision', $queue);
        error_log('tmon-admin: dequeue_provision removed key=' . $key);
        return $entry;
    }
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

// AJAX: Manage pending queue entry (reenqueue/delete)
add_action('wp_ajax_tmon_admin_manage_pending', function() {
    if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'forbidden']);
    check_ajax_referer('tmon_admin_provision_ajax');

    $key = $_POST['key'] ?? '';
    $action = $_POST['manage_action'] ?? '';
    $payload = $_POST['payload'] ?? '';

    $key_norm = tmon_admin_normalize_key($key);
    if ($action === 'delete') {
        tmon_admin_dequeue_provision($key_norm);
        wp_send_json_success(['message' => 'deleted']);
    } elseif ($action === 'reenqueue') {
        $data = null;
        if ($payload) {
            $data = json_decode($payload, true);
            if (!is_array($data)) $data = null;
        }
        if ($data) {
            tmon_admin_enqueue_provision($key_norm, $data);
            wp_send_json_success(['message' => 'reenqueued']);
        }
        wp_send_json_error(['message' => 'invalid payload']);
    }
    wp_send_json_error(['message' => 'unknown action']);
});

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
if (!function_exists('tmon_admin_enqueue_provision')) {
    function tmon_admin_enqueue_provision($key, $payload) {
        if (!$key || !is_string($key)) return false;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue)) $queue = [];
        $payload['requested_at'] = current_time('mysql');
        $payload['status'] = 'pending';
        $queue[$key] = $payload;
        update_option('tmon_admin_pending_provision', $queue);
        error_log('tmon-admin: enqueue_provision called for key=' . $key . ' payload=' . wp_json_encode($payload));
        return true;
    }
}

if (!function_exists('tmon_admin_get_pending_provision')) {
    function tmon_admin_get_pending_provision($key) {
        if (!$key || !is_string($key)) return null;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue)) return null;
        return isset($queue[$key]) ? $queue[$key] : null;
    }
}

if (!function_exists('tmon_admin_dequeue_provision')) {
    function tmon_admin_dequeue_provision($key) {
        if (!$key || !is_string($key)) return null;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue) || !isset($queue[$key])) return null;
        $entry = $queue[$key];
        unset($queue[$key]);
        update_option('tmon_admin_pending_provision', $queue);
        error_log('tmon-admin: dequeue_provision removed key=' . $key);
        return $entry;
    }
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

// AJAX: Manage pending queue entry (reenqueue/delete)
add_action('wp_ajax_tmon_admin_manage_pending', function() {
    if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'forbidden']);
    check_ajax_referer('tmon_admin_provision_ajax');

    $key = $_POST['key'] ?? '';
    $action = $_POST['manage_action'] ?? '';
    $payload = $_POST['payload'] ?? '';

    $key_norm = tmon_admin_normalize_key($key);
    if ($action === 'delete') {
        tmon_admin_dequeue_provision($key_norm);
        wp_send_json_success(['message' => 'deleted']);
    } elseif ($action === 'reenqueue') {
        $data = null;
        if ($payload) {
            $data = json_decode($payload, true);
            if (!is_array($data)) $data = null;
        }
        if ($data) {
            tmon_admin_enqueue_provision($key_norm, $data);
            wp_send_json_success(['message' => 'reenqueued']);
        }
        wp_send_json_error(['message' => 'invalid payload']);
    }
    wp_send_json_error(['message' => 'unknown action']);
});

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
if (!function_exists('tmon_admin_enqueue_provision')) {
    function tmon_admin_enqueue_provision($key, $payload) {
        if (!$key || !is_string($key)) return false;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue)) $queue = [];
        $payload['requested_at'] = current_time('mysql');
        $payload['status'] = 'pending';
        $queue[$key] = $payload;
        update_option('tmon_admin_pending_provision', $queue);
        error_log('tmon-admin: enqueue_provision called for key=' . $key . ' payload=' . wp_json_encode($payload));
        return true;
    }
}

if (!function_exists('tmon_admin_get_pending_provision')) {
    function tmon_admin_get_pending_provision($key) {
        if (!$key || !is_string($key)) return null;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue)) return null;
        return isset($queue[$key]) ? $queue[$key] : null;
    }
}

if (!function_exists('tmon_admin_dequeue_provision')) {
    function tmon_admin_dequeue_provision($key) {
        if (!$key || !is_string($key)) return null;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue) || !isset($queue[$key])) return null;
        $entry = $queue[$key];
        unset($queue[$key]);
        update_option('tmon_admin_pending_provision', $queue);
        error_log('tmon-admin: dequeue_provision removed key=' . $key);
        return $entry;
    }
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

// AJAX: Manage pending queue entry (reenqueue/delete)
add_action('wp_ajax_tmon_admin_manage_pending', function() {
    if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'forbidden']);
    check_ajax_referer('tmon_admin_provision_ajax');

    $key = $_POST['key'] ?? '';
    $action = $_POST['manage_action'] ?? '';
    $payload = $_POST['payload'] ?? '';

    $key_norm = tmon_admin_normalize_key($key);
    if ($action === 'delete') {
        tmon_admin_dequeue_provision($key_norm);
        wp_send_json_success(['message' => 'deleted']);
    } elseif ($action === 'reenqueue') {
        $data = null;
        if ($payload) {
            $data = json_decode($payload, true);
            if (!is_array($data)) $data = null;
        }
        if ($data) {
            tmon_admin_enqueue_provision($key_norm, $data);
            wp_send_json_success(['message' => 'reenqueued']);
        }
        wp_send_json_error(['message' => 'invalid payload']);
    }
    wp_send_json_error(['message' => 'unknown action']);
});

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
if (!function_exists('tmon_admin_enqueue_provision')) {
    function tmon_admin_enqueue_provision($key, $payload) {
        if (!$key || !is_string($key)) return false;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue)) $queue = [];
        $payload['requested_at'] = current_time('mysql');
        $payload['status'] = 'pending';
        $queue[$key] = $payload;
        update_option('tmon_admin_pending_provision', $queue);
        error_log('tmon-admin: enqueue_provision called for key=' . $key . ' payload=' . wp_json_encode($payload));
        return true;
    }
}

if (!function_exists('tmon_admin_get_pending_provision')) {
    function tmon_admin_get_pending_provision($key) {
        if (!$key || !is_string($key)) return null;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue)) return null;
        return isset($queue[$key]) ? $queue[$key] : null;
    }
}

if (!function_exists('tmon_admin_dequeue_provision')) {
    function tmon_admin_dequeue_provision($key) {
        if (!$key || !is_string($key)) return null;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue) || !isset($queue[$key])) return null;
        $entry = $queue[$key];
        unset($queue[$key]);
        update_option('tmon_admin_pending_provision', $queue);
        error_log('tmon-admin: dequeue_provision removed key=' . $key);
        return $entry;
    }
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

// AJAX: Manage pending queue entry (reenqueue/delete)
add_action('wp_ajax_tmon_admin_manage_pending', function() {
    if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'forbidden']);
    check_ajax_referer('tmon_admin_provision_ajax');

    $key = $_POST['key'] ?? '';
    $action = $_POST['manage_action'] ?? '';
    $payload = $_POST['payload'] ?? '';

    $key_norm = tmon_admin_normalize_key($key);
    if ($action === 'delete') {
        tmon_admin_dequeue_provision($key_norm);
        wp_send_json_success(['message' => 'deleted']);
    } elseif ($action === 'reenqueue') {
        $data = null;
        if ($payload) {
            $data = json_decode($payload, true);
            if (!is_array($data)) $data = null;
        }
        if ($data) {
            tmon_admin_enqueue_provision($key_norm, $data);
            wp_send_json_success(['message' => 'reenqueued']);
        }
        wp_send_json_error(['message' => 'invalid payload']);
    }
    wp_send_json_error(['message' => 'unknown action']);
});

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
if (!function_exists('tmon_admin_enqueue_provision')) {
    function tmon_admin_enqueue_provision($key, $payload) {
        if (!$key || !is_string($key)) return false;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue)) $queue = [];
        $payload['requested_at'] = current_time('mysql');
        $payload['status'] = 'pending';
        $queue[$key] = $payload;
        update_option('tmon_admin_pending_provision', $queue);
        error_log('tmon-admin: enqueue_provision called for key=' . $key . ' payload=' . wp_json_encode($payload));
        return true;
    }
}

if (!function_exists('tmon_admin_get_pending_provision')) {
    function tmon_admin_get_pending_provision($key) {
        if (!$key || !is_string($key)) return null;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue)) return null;
        return isset($queue[$key]) ? $queue[$key] : null;
    }
}

if (!function_exists('tmon_admin_dequeue_provision')) {
    function tmon_admin_dequeue_provision($key) {
        if (!$key || !is_string($key)) return null;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue) || !isset($queue[$key])) return null;
        $entry = $queue[$key];
        unset($queue[$key]);
        update_option('tmon_admin_pending_provision', $queue);
        error_log('tmon-admin: dequeue_provision removed key=' . $key);
        return $entry;
    }
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

// AJAX: Manage pending queue entry (reenqueue/delete)
add_action('wp_ajax_tmon_admin_manage_pending', function() {
    if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'forbidden']);
    check_ajax_referer('tmon_admin_provision_ajax');

    $key = $_POST['key'] ?? '';
    $action = $_POST['manage_action'] ?? '';
    $payload = $_POST['payload'] ?? '';

    $key_norm = tmon_admin_normalize_key($key);
    if ($action === 'delete') {
        tmon_admin_dequeue_provision($key_norm);
        wp_send_json_success(['message' => 'deleted']);
    } elseif ($action === 'reenqueue') {
        $data = null;
        if ($payload) {
            $data = json_decode($payload, true);
            if (!is_array($data)) $data = null;
        }
        if ($data) {
            tmon_admin_enqueue_provision($key_norm, $data);
            wp_send_json_success(['message' => 'reenqueued']);
        }
        wp_send_json_error(['message' => 'invalid payload']);
    }
    wp_send_json_error(['message' => 'unknown action']);
});

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
if (!function_exists('tmon_admin_enqueue_provision')) {
    function tmon_admin_enqueue_provision($key, $payload) {
        if (!$key || !is_string($key)) return false;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue)) $queue = [];
        $payload['requested_at'] = current_time('mysql');
        $payload['status'] = 'pending';
        $queue[$key] = $payload;
        update_option('tmon_admin_pending_provision', $queue);
        error_log('tmon-admin: enqueue_provision called for key=' . $key . ' payload=' . wp_json_encode($payload));
        return true;
    }
}

if (!function_exists('tmon_admin_get_pending_provision')) {
    function tmon_admin_get_pending_provision($key) {
        if (!$key || !is_string($key)) return null;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue)) return null;
        return isset($queue[$key]) ? $queue[$key] : null;
    }
}

if (!function_exists('tmon_admin_dequeue_provision')) {
    function tmon_admin_dequeue_provision($key) {
        if (!$key || !is_string($key)) return null;
        $queue = get_option('tmon_admin_pending_provision', []);
        if (!is_array($queue) || !isset($queue[$key])) return null;
        $entry = $queue[$key];
        unset($queue[$key]);
        update_option('tmon_admin_pending_provision', $queue);
        error_log('tmon-admin: dequeue_provision removed key=' . $key);
        return $entry;
    }
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

// AJAX: Manage pending queue entry (reenqueue/delete)
add_action('wp_ajax_tmon_admin_manage_pending', function() {
    if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'forbidden']);
    check_ajax_referer('tmon_admin_provision_ajax');

    $key = $_POST['key'] ?? '';
    $action = $_POST['manage_action'] ?? '';
    $payload = $_POST['payload'] ?? '';

    $key_norm = tmon_admin_normalize_key($key);
    if ($action === 'delete') {
        tmon_admin_dequeue_provision($key_norm);
        wp_send_json_success(['message' => 'deleted']);
    } elseif ($action === 'reenqueue') {
        $data = null;
        if ($payload) {
            $data = json_decode($payload, true);
            if (!is_array($data)) $data = null;
        }
        if ($data) {
            tmon_admin_enqueue_provision($key_norm, $data);
            wp_send_json_success(['message' => 'reenqueued']);
        }
        wp_send_json_error(['message' => 'invalid payload']);
    }
    wp_send_json_error(['message' => 'unknown action']);
});

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
    $meta = $_POST['meta'