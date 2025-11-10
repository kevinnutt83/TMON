<?php
// REST API for company and device management
add_action('rest_api_init', function() {
    register_rest_route('tmon/v1', '/company', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_create_company',
        'permission_callback' => function() { return current_user_can('manage_options'); },
    ]);
    register_rest_route('tmon/v1', '/unit', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_create_unit',
        'permission_callback' => function() { return current_user_can('manage_options'); },
    ]);
    register_rest_route('tmon/v1', '/unit/assign', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_assign_unit',
        'permission_callback' => function() { return current_user_can('manage_options'); },
    ]);
    register_rest_route('tmon/v1', '/company/(?P<id>\d+)/units', [
        'methods' => 'GET',
        'callback' => 'tmon_uc_get_company_units',
        'permission_callback' => function() { return current_user_can('manage_options'); },
    ]);
    register_rest_route('tmon/v1', '/unit/(?P<id>\d+)', [
        'methods' => 'GET',
        'callback' => 'tmon_uc_get_unit',
        'permission_callback' => function() { return current_user_can('manage_options'); },
    ]);
});

function tmon_uc_create_company($request) {
    global $wpdb;
    $data = $request->get_json_params();
    $wpdb->insert(
        $wpdb->prefix . 'tmon_company',
        [
            'name' => sanitize_text_field($data['name']),
            'description' => sanitize_text_field($data['description']),
            'address' => sanitize_text_field($data['address']),
            'gps_lat' => floatval($data['gps_lat']),
            'gps_lng' => floatval($data['gps_lng']),
            'timezone' => sanitize_text_field($data['timezone'])
        ]
    );
    return rest_ensure_response(['status' => 'ok', 'id' => $wpdb->insert_id]);
}

function tmon_uc_create_unit($request) {
    global $wpdb;
    $data = $request->get_json_params();
    $wpdb->insert(
        $wpdb->prefix . 'tmon_unit',
        [
            'name' => sanitize_text_field($data['name']),
            'description' => sanitize_text_field($data['description']),
            'company_id' => intval($data['company_id']),
            'unit_id' => sanitize_text_field($data['unit_id']),
            'status' => 'active',
            'created_at' => current_time('mysql')
        ]
    );
    return rest_ensure_response(['status' => 'ok', 'id' => $wpdb->insert_id]);
}

function tmon_uc_assign_unit($request) {
    global $wpdb;
    $data = $request->get_json_params();
    $wpdb->update(
        $wpdb->prefix . 'tmon_unit',
        ['company_id' => intval($data['company_id'])],
        ['id' => intval($data['unit_id'])]
    );
    return rest_ensure_response(['status' => 'ok']);
}

function tmon_uc_get_company_units($request) {
    global $wpdb;
    $company_id = intval($request['id']);
    $units = $wpdb->get_results("SELECT * FROM {$wpdb->prefix}tmon_unit WHERE company_id = $company_id", ARRAY_A);
    return rest_ensure_response(['units' => $units]);
}

function tmon_uc_get_unit($request) {
    global $wpdb;
    $unit_id = intval($request['id']);
    $unit = $wpdb->get_row("SELECT * FROM {$wpdb->prefix}tmon_unit WHERE id = $unit_id", ARRAY_A);
    return rest_ensure_response(['unit' => $unit]);
}
// AJAX: Get OTA jobs for admin info page
add_action('wp_ajax_tmon_uc_get_ota_jobs', function() {
    global $wpdb;
    $rows = $wpdb->get_results("SELECT id, unit_id, job_type, status, created_at FROM {$wpdb->prefix}tmon_ota_jobs ORDER BY created_at DESC LIMIT 100", ARRAY_A);
    wp_send_json(['jobs' => $rows]);
});

// AJAX: Enqueue relay command (immediate or scheduled) from frontend controls
add_action('wp_ajax_tmon_uc_relay_command', function(){
    if (! (current_user_can('manage_options') || current_user_can('edit_tmon_units')) ) {
        wp_send_json_error(['message' => 'forbidden'], 403);
    }
    $nonce = isset($_POST['nonce']) ? sanitize_text_field($_POST['nonce']) : '';
    if (!$nonce || !wp_verify_nonce($nonce, 'tmon_uc_relay')) {
        wp_send_json_error(['message' => 'bad nonce'], 400);
    }
    $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
    $relay_num = sanitize_text_field($_POST['relay_num'] ?? '1');
    $state = sanitize_text_field($_POST['state'] ?? 'on');
    $runtime_min = intval($_POST['runtime_min'] ?? '0');
    $schedule_at = sanitize_text_field($_POST['schedule_at'] ?? '');
    if (!$unit_id || !in_array($state, ['on','off','toggle'], true)) {
        wp_send_json_error(['message' => 'invalid input'], 400);
    }
    // If scheduled, create a WP cron single event to enqueue later; else enqueue now
    if ($schedule_at) {
        $ts = strtotime($schedule_at);
        if ($ts && $ts > time() - 60) {
            wp_schedule_single_event($ts, 'tmon_uc_enqueue_relay_job_event', [
                $unit_id, $relay_num, $state, $runtime_min
            ]);
            wp_send_json_success(['scheduled' => true, 'at' => date('c', $ts)]);
        }
        // bad schedule time falls through to immediate
    }
    $ok = tmon_uc_enqueue_relay_job($unit_id, $relay_num, $state, $runtime_min);
    if ($ok) wp_send_json_success(['scheduled' => false]);
    wp_send_json_error(['message' => 'enqueue failed'], 500);
});

// Helper to enqueue a toggle_relay job into device command queue
function tmon_uc_enqueue_relay_job($unit_id, $relay_num, $state, $runtime_min = 0) {
    global $wpdb;
    $params = [
        'relay_num' => (string)$relay_num,
        'state' => (string)$state,
        'runtime' => (string)max(0, intval($runtime_min))
    ];
    $ins = $wpdb->insert(
        $wpdb->prefix . 'tmon_device_commands',
        [
            'device_id' => $unit_id,
            'command' => 'toggle_relay',
            'params' => wp_json_encode($params),
            'created_at' => current_time('mysql'),
        ]
    );
    return (bool)$ins;
}

// Cron handler to enqueue scheduled relay jobs
add_action('tmon_uc_enqueue_relay_job_event', function($unit_id, $relay_num, $state, $runtime_min){
    tmon_uc_enqueue_relay_job($unit_id, $relay_num, $state, $runtime_min);
}, 10, 4);
// JWT authentication for REST API
// JWT verification helpers
function tmon_uc_get_auth_header() {
    $headers = function_exists('getallheaders') ? getallheaders() : [];
    if (isset($headers['Authorization'])) return $headers['Authorization'];
    if (isset($_SERVER['HTTP_AUTHORIZATION'])) return $_SERVER['HTTP_AUTHORIZATION'];
    if (isset($_SERVER['REDIRECT_HTTP_AUTHORIZATION'])) return $_SERVER['REDIRECT_HTTP_AUTHORIZATION'];
    return '';
}

function tmon_uc_b64url_decode($data) {
    $remainder = strlen($data) % 4;
    if ($remainder) {
        $padlen = 4 - $remainder;
        $data .= str_repeat('=', $padlen);
    }
    $data = strtr($data, '-_', '+/');
    return base64_decode($data);
}

function tmon_uc_jwt_verify($request) {
    if (is_user_logged_in()) return true;
    $auth = tmon_uc_get_auth_header();
    if (!$auth || stripos($auth, 'Bearer ') !== 0) return false;
    $token = trim(substr($auth, 7));
    $parts = explode('.', $token);
    if (count($parts) !== 3) return false;
    list($h64, $p64, $s64) = $parts;
    $header = json_decode(tmon_uc_b64url_decode($h64), true);
    $payload = json_decode(tmon_uc_b64url_decode($p64), true);
    $sig = tmon_uc_b64url_decode($s64);
    if (!is_array($header) || !is_array($payload)) return false;
    $alg = isset($header['alg']) ? $header['alg'] : '';
    if ($alg !== 'HS256') return false; // support HS256 only
    $secret = defined('JWT_AUTH_SECRET_KEY') ? JWT_AUTH_SECRET_KEY : (defined('TMON_JWT_SECRET') ? TMON_JWT_SECRET : 'changeme');
    $data = $h64 . '.' . $p64;
    $expected = hash_hmac('sha256', $data, $secret, true);
    if (!hash_equals($expected, $sig)) return false;
    // Time-based checks with leeway
    $now = time();
    $leeway = defined('TMON_JWT_LEEWAY') ? intval(TMON_JWT_LEEWAY) : 30; // seconds
    if (isset($payload['nbf']) && ($now + $leeway) < intval($payload['nbf'])) return false;
    if (isset($payload['exp']) && ($now - $leeway) > intval($payload['exp'])) return false;
    return true;
}

// Helper callbacks
function tmon_uc_is_logged_in() { return is_user_logged_in(); }
function tmon_uc_admin_cap() { return current_user_can('manage_options'); }
// Admin integration auth: allow cross-site calls with pre-shared key
function tmon_uc_admin_integration_auth($request) {
    if (current_user_can('manage_options')) return true;
    $headers = function_exists('getallheaders') ? getallheaders() : [];
    $key = '';
    if (isset($headers['X-TMON-ADMIN'])) $key = $headers['X-TMON-ADMIN'];
    elseif (isset($_SERVER['HTTP_X_TMON_ADMIN'])) $key = $_SERVER['HTTP_X_TMON_ADMIN'];
    $expected = get_option('tmon_uc_admin_key');
    if ($expected && hash_equals($expected, (string)$key)) return true;
    return false;
}

// Read-only auth: accept either X-TMON-ADMIN (UC admin key) or X-TMON-HUB (hub shared key)
function tmon_uc_admin_read_auth($request) {
    if (tmon_uc_admin_integration_auth($request)) return true;
    $headers = function_exists('getallheaders') ? getallheaders() : [];
    $hub = '';
    if (isset($headers['X-TMON-HUB'])) $hub = $headers['X-TMON-HUB'];
    elseif (isset($_SERVER['HTTP_X_TMON_HUB'])) $hub = $_SERVER['HTTP_X_TMON_HUB'];
    $expected_hub = get_option('tmon_uc_hub_shared_key');
    if ($expected_hub && hash_equals($expected_hub, (string)$hub)) return true;
    // Dedicated read token header
    $read = '';
    if (isset($headers['X-TMON-READ'])) $read = $headers['X-TMON-READ'];
    elseif (isset($_SERVER['HTTP_X_TMON_READ'])) $read = $_SERVER['HTTP_X_TMON_READ'];
    $expected_read = get_option('tmon_uc_hub_read_token');
    if ($expected_read && hash_equals($expected_read, (string)$read)) return true;
    return false;
}
// Basic error logging
function tmon_uc_log_error($msg) {
    if (WP_DEBUG) {
        error_log('[TMON Unit Connector] ' . $msg);
    }
}
// Heartbeat/ping endpoint for real-time device status
add_action('rest_api_init', function() {
    register_rest_route('tmon/v1', '/device/ping', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_device_ping',
        'permission_callback' => 'tmon_uc_jwt_verify',
    ]);
});

function tmon_uc_api_device_ping($request) {
    global $wpdb;
    $params = $request->get_json_params();
    $unit_id = isset($params['unit_id']) ? sanitize_text_field($params['unit_id']) : '';
    if ($unit_id) {
        $wpdb->update($wpdb->prefix . 'tmon_devices', ['last_seen' => current_time('mysql')], ['unit_id' => $unit_id]);
        // Optional: also track last_seen in a transient cache for quick scans
        set_transient('tmon_last_seen_' . $unit_id, time(), 6 * HOUR_IN_SECONDS);
        return rest_ensure_response(['status' => 'ok']);
    }
    return rest_ensure_response(['status' => 'error', 'message' => 'Missing unit_id']);
}
// Endpoint for device to poll for pending OTA jobs
add_action('rest_api_init', function() {
    register_rest_route('tmon/v1', '/device/ota-jobs/(?P<unit_id>[\w-]+)', [
        'methods' => 'GET',
        'callback' => 'tmon_uc_api_device_ota_jobs',
        'permission_callback' => 'tmon_uc_jwt_verify',
    ]);
    register_rest_route('tmon/v1', '/device/ota-job-complete', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_device_ota_job_complete',
        'permission_callback' => 'tmon_uc_jwt_verify',
    ]);
    // Offline devices query
    register_rest_route('tmon/v1', '/devices/offline', [
        'methods' => 'GET',
        'callback' => 'tmon_uc_api_offline_devices',
        'permission_callback' => 'tmon_uc_admin_cap',
        'args' => [
            'minutes' => ['required' => false],
        ],
    ]);
});

function tmon_uc_api_device_ota_jobs($request) {
    global $wpdb;
    $unit_id = $request->get_param('unit_id');
    $jobs = $wpdb->get_results($wpdb->prepare("SELECT id, job_type, payload FROM {$wpdb->prefix}tmon_ota_jobs WHERE unit_id = %s AND status = 'pending'", $unit_id));
    $result = [];
    foreach ($jobs as $job) {
        $result[] = [
            'id' => $job->id,
            'job_type' => $job->job_type,
            'payload' => json_decode($job->payload, true),
        ];
    }
    return rest_ensure_response(['status' => 'ok', 'jobs' => $result]);
}

function tmon_uc_api_device_ota_job_complete($request) {
    global $wpdb;
    $params = $request->get_json_params();
    $job_id = isset($params['job_id']) ? intval($params['job_id']) : 0;
    if ($job_id) {
        $wpdb->update(
            $wpdb->prefix . 'tmon_ota_jobs',
            ['status' => 'completed', 'completed_at' => current_time('mysql')],
            ['id' => $job_id]
        );
        return rest_ensure_response(['status' => 'ok']);
    }
    return rest_ensure_response(['status' => 'error', 'message' => 'Missing job_id']);
}

function tmon_uc_api_offline_devices($request) {
    global $wpdb;
    $minutes = intval($request->get_param('minutes')) ?: 30;
    $threshold = gmdate('Y-m-d H:i:s', time() - $minutes * 60);
    $rows = $wpdb->get_results($wpdb->prepare("SELECT unit_id, unit_name, last_seen FROM {$wpdb->prefix}tmon_devices WHERE (last_seen IS NULL OR last_seen < %s) AND suspended = 0", $threshold), ARRAY_A);
    return rest_ensure_response(['status' => 'ok', 'minutes' => $minutes, 'devices' => $rows]);
}

// Cron: scan for offline devices and emit notifications
if (!wp_next_scheduled('tmon_uc_scan_offline_event')) {
    wp_schedule_event(time() + 60, 'hourly', 'tmon_uc_scan_offline_event');
}
add_action('tmon_uc_scan_offline_event', function(){
    global $wpdb;
    $minutes = intval(get_option('tmon_uc_offline_threshold_minutes', 30)) ?: 30;
    $threshold = gmdate('Y-m-d H:i:s', time() - $minutes * 60);
    $rows = $wpdb->get_results($wpdb->prepare("SELECT unit_id, unit_name, last_seen, settings FROM {$wpdb->prefix}tmon_devices WHERE (last_seen IS NULL OR last_seen < %s) AND suspended = 0", $threshold), ARRAY_A);
    if (!empty($rows)) {
        // Notify TMON Admin
        do_action('tmon_admin_notify', 'offline', sprintf('%d device(s) offline > %d min', count($rows), $minutes), ['devices' => $rows, 'minutes' => $minutes]);
        // Notify per-device recipients, else fall back to site admins
        $fallback_admins = wp_list_pluck(get_users(['role' => 'administrator']), 'user_email');
        foreach ($rows as $row) {
            $emails = [];
            if (!empty($row['settings'])) {
                $s = json_decode($row['settings'], true);
                if (is_array($s) && !empty($s['notify_overrides']['emails'])) {
                    $emails = array_filter($s['notify_overrides']['emails'], function($e){ return is_email($e); });
                }
            }
            if (empty($emails)) $emails = $fallback_admins;
            foreach ($emails as $em) {
                @wp_mail($em, '[TMON] Device offline', sprintf("Unit %s (%s) is offline more than %d minutes.", $row['unit_id'], $row['unit_name'], $minutes));
            }
        }
    }
});

// Device Commands API: enqueue, poll, and complete
add_action('rest_api_init', function() {
    register_rest_route('tmon/v1', '/device/command', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_device_command_enqueue',
        'permission_callback' => 'tmon_uc_admin_cap',
    ]);
    register_rest_route('tmon/v1', '/device/commands/(?P<unit_id>[\w-]+)', [
        'methods' => 'GET',
        'callback' => 'tmon_uc_api_device_commands_poll',
        'permission_callback' => 'tmon_uc_jwt_verify',
    ]);
    register_rest_route('tmon/v1', '/device/command-complete', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_device_command_complete',
        'permission_callback' => 'tmon_uc_jwt_verify',
    ]);
});

function tmon_uc_api_device_command_enqueue($request) {
    global $wpdb;
    $params = $request->get_json_params();
    $unit_id = isset($params['unit_id']) ? sanitize_text_field($params['unit_id']) : '';
    $command = isset($params['command']) ? sanitize_text_field($params['command']) : '';
    $cmd_params = isset($params['params']) ? $params['params'] : [];
    if (!$unit_id || !$command) {
        return rest_ensure_response(['status' => 'error', 'message' => 'Missing unit_id or command']);
    }
    $wpdb->insert(
        $wpdb->prefix . 'tmon_device_commands',
        [
            'device_id' => $unit_id,
            'command' => $command,
            'params' => wp_json_encode($cmd_params),
            'created_at' => current_time('mysql'),
        ]
    );
    return rest_ensure_response(['status' => 'ok', 'id' => $wpdb->insert_id]);
}

function tmon_uc_api_device_commands_poll($request) {
    global $wpdb;
    $unit_id = $request->get_param('unit_id');
    if (!$unit_id) {
        return rest_ensure_response(['status' => 'error', 'message' => 'Missing unit_id']);
    }
    $rows = $wpdb->get_results($wpdb->prepare(
        "SELECT id, command, params, created_at FROM {$wpdb->prefix}tmon_device_commands WHERE device_id = %s AND executed_at IS NULL ORDER BY id ASC LIMIT 20",
        $unit_id
    ), ARRAY_A);
    $jobs = [];
    foreach ($rows as $r) {
        $jobs[] = [
            'id' => intval($r['id']),
            'command' => $r['command'],
            'params' => json_decode($r['params'], true) ?: [],
            'created_at' => $r['created_at'],
        ];
    }
    return rest_ensure_response(['status' => 'ok', 'jobs' => $jobs]);
}

function tmon_uc_api_device_command_complete($request) {
    global $wpdb;
    $params = $request->get_json_params();
    $job_id = isset($params['job_id']) ? intval($params['job_id']) : 0;
    $ok = isset($params['ok']) ? intval(!!$params['ok']) : null;
    $result = isset($params['result']) ? $params['result'] : null;
    if (!$job_id) {
        return rest_ensure_response(['status' => 'error', 'message' => 'Missing job_id']);
    }
    // Merge completion info into params to avoid schema changes
    $row = $wpdb->get_row($wpdb->prepare("SELECT params FROM {$wpdb->prefix}tmon_device_commands WHERE id = %d", $job_id));
    $p = [];
    if ($row && !empty($row->params)) {
        $decoded = json_decode($row->params, true);
        if (is_array($decoded)) $p = $decoded;
    }
    $p['__ok'] = $ok;
    if (!is_null($result)) $p['__result'] = $result;
    $wpdb->update(
        $wpdb->prefix . 'tmon_device_commands',
        [
            'params' => wp_json_encode($p),
            'executed_at' => current_time('mysql')
        ],
        ['id' => $job_id]
    );
    return rest_ensure_response(['status' => 'ok']);
}
// AJAX endpoints for frontend shortcodes
add_action('wp_ajax_tmon_uc_get_devices', 'tmon_uc_get_devices');
add_action('wp_ajax_nopriv_tmon_uc_get_devices', 'tmon_uc_get_devices');
function tmon_uc_get_devices() {
    global $wpdb;
    $rows = $wpdb->get_results("SELECT unit_id, unit_name, company, site, zone, cluster, suspended FROM {$wpdb->prefix}tmon_devices");
    $devices = [];
    foreach ($rows as $row) {
        $devices[] = [
            'unit_id' => $row->unit_id,
            'unit_name' => $row->unit_name,
            'company' => $row->company,
            'site' => $row->site,
            'zone' => $row->zone,
            'cluster' => $row->cluster,
            'suspended' => $row->suspended,
        ];
    }
    wp_send_json(['devices' => $devices]);
}
add_action('wp_ajax_tmon_uc_get_device_status', 'tmon_uc_get_device_status');
add_action('wp_ajax_nopriv_tmon_uc_get_device_status', 'tmon_uc_get_device_status');
function tmon_uc_get_device_status() {
    global $wpdb;
    $unit_id = isset($_POST['unit_id']) ? sanitize_text_field($_POST['unit_id']) : '';
    if ($unit_id) {
        $row = $wpdb->get_row($wpdb->prepare("SELECT status FROM {$wpdb->prefix}tmon_devices WHERE unit_id = %s", $unit_id));
        $status = $row ? json_decode($row->status, true) : [];
        wp_send_json(['status' => $status]);
    } else {
        wp_send_json(['status' => []]);
    }
}
function tmon_uc_api_device_add($request) {
    // Device logic: handle device registration, status, commands, etc.
    function tmon_uc_register_device($device_id, $meta = []) {
        global $wpdb;
        $table = $wpdb->prefix.'tmon_devices';
        $wpdb->insert($table, array_merge(['device_id'=>$device_id], $meta));
    }

    function tmon_uc_update_device($device_id, $meta = []) {
        global $wpdb;
        $table = $wpdb->prefix.'tmon_devices';
        $wpdb->update($table, $meta, ['device_id'=>$device_id]);
    }

    function tmon_uc_remove_device($device_id) {
        global $wpdb;
        $table = $wpdb->prefix.'tmon_devices';
        $wpdb->delete($table, ['device_id'=>$device_id]);
    }

    function tmon_uc_send_command($device_id, $command, $params = []) {
        // Store command for device to poll
        global $wpdb;
        $table = $wpdb->prefix.'tmon_device_commands';
        $wpdb->insert($table, [
            'device_id'=>$device_id,
            'command'=>$command,
            'params'=>maybe_serialize($params),
            'created_at'=>current_time('mysql'),
        ]);
    }
    return rest_ensure_response(['status' => 'ok']);
}
function tmon_uc_api_device_remove($request) {
    global $wpdb;
    $params = $request->get_json_params();
    $unit_id = isset($params['unit_id']) ? sanitize_text_field($params['unit_id']) : '';
    if ($unit_id) {
        $wpdb->delete($wpdb->prefix . 'tmon_devices', ['unit_id' => $unit_id]);
        $wpdb->delete($wpdb->prefix . 'tmon_device_data', ['unit_id' => $unit_id]);
        return rest_ensure_response(['status' => 'ok']);
    }
    return rest_ensure_response(['status' => 'error', 'message' => 'Missing unit_id']);
}
function tmon_uc_api_device_suspend($request) {
    global $wpdb;
    $params = $request->get_json_params();
    $unit_id = isset($params['unit_id']) ? sanitize_text_field($params['unit_id']) : '';
    $suspend = isset($params['suspend']) ? intval($params['suspend']) : 1;
    if ($unit_id) {
           $wpdb->update($wpdb->prefix . 'tmon_devices', ['suspended' => $suspend], ['unit_id' => $unit_id]);
        return rest_ensure_response(['status' => 'ok']);
    }
    return rest_ensure_response(['status' => 'error', 'message' => 'Missing unit_id']);
}
function tmon_uc_api_device_remote_access($request) {
    // Placeholder for remote access logic (e.g., trigger reverse tunnel, send command, etc.)
    return rest_ensure_response(['status' => 'ok']);
}
function tmon_uc_api_device_ota($request) {
    global $wpdb;
    $params = $request->get_json_params();
    $unit_id = isset($params['unit_id']) ? sanitize_text_field($params['unit_id']) : '';
    $job_type = isset($params['job_type']) ? sanitize_text_field($params['job_type']) : '';
    $payload = isset($params['payload']) ? wp_json_encode($params['payload']) : '';
    if ($unit_id && $job_type && $payload) {
        $wpdb->insert(
            $wpdb->prefix . 'tmon_ota_jobs',
            [
                'unit_id' => $unit_id,
                'job_type' => $job_type,
                'payload' => $payload,
                'status' => 'pending',
                'created_at' => current_time('mysql'),
            ]
        );
        return rest_ensure_response(['status' => 'ok']);
    }
    return rest_ensure_response(['status' => 'error', 'message' => 'Missing unit_id, job_type, or payload']);
}
// Core device and group management logic
// Device registration, group hierarchy, settings sync, data upload, OTA, file send/request, suspend, remove, remote access
// (see above for registration, update, remove)
function tmon_uc_sync_settings($device_id, $settings) {
    global $wpdb;
    $table = $wpdb->prefix.'tmon_devices';
    $wpdb->update($table, ['settings'=>maybe_serialize($settings)], ['device_id'=>$device_id]);
}

function tmon_uc_upload_data($device_id, $data) {
    global $wpdb;
    $table = $wpdb->prefix.'tmon_device_data';
    $wpdb->insert($table, [
        'device_id'=>$device_id,
        'data'=>maybe_serialize($data),
        'created_at'=>current_time('mysql'),
    ]);
}

function tmon_uc_ota_job($device_id, $firmware_url) {
    global $wpdb;
    $table = $wpdb->prefix.'tmon_ota_jobs';
    $wpdb->insert($table, [
        'device_id'=>$device_id,
        'firmware_url'=>$firmware_url,
        'status'=>'pending',
        'created_at'=>current_time('mysql'),
    ]);
}

function tmon_uc_file_send($device_id, $file_url) {
    // Store file send job for device
    global $wpdb;
    $table = $wpdb->prefix.'tmon_file_jobs';
    $wpdb->insert($table, [
        'device_id'=>$device_id,
        'file_url'=>$file_url,
        'status'=>'pending',
        'created_at'=>current_time('mysql'),
    ]);
}

function tmon_uc_suspend_device($device_id) {
    global $wpdb;
    $table = $wpdb->prefix.'tmon_devices';
    $wpdb->update($table, ['status'=>'suspended'], ['device_id'=>$device_id]);
}

function tmon_uc_remote_access($device_id) {
    // Placeholder for remote access logic
    return 'Remote access not implemented.';
}


// REST API endpoints registration
add_action('rest_api_init', function() {
    register_rest_route('tmon/v1', '/device/register', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_device_register',
        'permission_callback' => 'tmon_uc_jwt_verify',
    ]);
    register_rest_route('tmon/v1', '/device/settings', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_device_settings',
        'permission_callback' => 'tmon_uc_jwt_verify',
    ]);
    register_rest_route('tmon/v1', '/device/settings/(?P<unit_id>[\w-]+)', [
        'methods' => 'GET',
        'callback' => 'tmon_uc_api_device_settings_get',
        'permission_callback' => 'tmon_uc_jwt_verify',
    ]);
    register_rest_route('tmon/v1', '/device/data', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_device_data',
        'permission_callback' => 'tmon_uc_jwt_verify',
    ]);
    register_rest_route('tmon/v1', '/device/file', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_device_file_upload',
        'permission_callback' => 'tmon_uc_jwt_verify',
    ]);
    register_rest_route('tmon/v1', '/device/file/(?P<unit_id>[\w-]+)/(?P<filename>[\w.-]+)', [
        'methods' => 'GET',
        'callback' => 'tmon_uc_api_device_file_download',
        'permission_callback' => 'tmon_uc_jwt_verify',
    ]);
    register_rest_route('tmon/v1', '/device/add', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_device_add',
        'permission_callback' => 'tmon_uc_admin_cap',
    ]);
    register_rest_route('tmon/v1', '/device/remove', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_device_remove',
        'permission_callback' => 'tmon_uc_admin_cap',
    ]);
    register_rest_route('tmon/v1', '/device/suspend', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_device_suspend',
        'permission_callback' => 'tmon_uc_admin_cap',
    ]);
    register_rest_route('tmon/v1', '/device/remote-access', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_device_remote_access',
        'permission_callback' => 'tmon_uc_admin_cap',
    ]);
    // OTA endpoint
    register_rest_route('tmon/v1', '/device/ota', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_api_device_ota',
        'permission_callback' => 'tmon_uc_admin_cap',
    ]);

    // Admin-only helpers for cross-site provisioning (invoked by TMON Admin)
    register_rest_route('tmon/v1', '/admin/device/register', [
        'methods' => 'POST',
        'callback' => function($request){
            if (!tmon_uc_admin_integration_auth($request)) return new WP_REST_Response(['status'=>'forbidden'], 403);
            global $wpdb;
            $params = $request->get_json_params();
            $unit_id = isset($params['unit_id']) ? sanitize_text_field($params['unit_id']) : '';
            $unit_name = isset($params['unit_name']) ? sanitize_text_field($params['unit_name']) : $unit_id;
            $company_id = isset($params['company_id']) ? intval($params['company_id']) : 0;
            $company_name = isset($params['company_name']) ? sanitize_text_field($params['company_name']) : ($company_id ? ('Company #'.$company_id) : '');
            if (!$unit_id) return rest_ensure_response(['status'=>'error', 'message'=>'Missing unit_id']);
            $wpdb->replace(
                $wpdb->prefix . 'tmon_devices',
                [
                    'unit_id' => $unit_id,
                    'unit_name' => $unit_name,
                    'company' => $company_name,
                    'last_seen' => current_time('mysql'),
                    'suspended' => 0,
                ]
            );
            return rest_ensure_response(['status'=>'ok']);
        },
        'permission_callback' => '__return_true',
    ]);
    register_rest_route('tmon/v1', '/admin/device/settings', [
        'methods' => 'POST',
        'callback' => function($request){
            if (!tmon_uc_admin_integration_auth($request)) return new WP_REST_Response(['status'=>'forbidden'], 403);
            global $wpdb;
            $params = $request->get_json_params();
            $unit_id = isset($params['unit_id']) ? sanitize_text_field($params['unit_id']) : '';
            $settings_arr = isset($params['settings']) && is_array($params['settings']) ? $params['settings'] : [];
            $settings = $settings_arr ? wp_json_encode($settings_arr) : '';
            if (!$unit_id) return rest_ensure_response(['status'=>'error','message'=>'Missing unit_id']);
            // If settings include a name field, persist to unit_name column as well
            $maybe_name = '';
            if (isset($settings_arr['UNIT_Name']) && $settings_arr['UNIT_Name'] !== '') {
                $maybe_name = sanitize_text_field($settings_arr['UNIT_Name']);
            } elseif (isset($settings_arr['unit_name']) && $settings_arr['unit_name'] !== '') {
                $maybe_name = sanitize_text_field($settings_arr['unit_name']);
            }
            $data = ['settings'=>$settings, 'last_seen'=>current_time('mysql')];
            if ($maybe_name !== '') { $data['unit_name'] = $maybe_name; }
            $wpdb->update($wpdb->prefix.'tmon_devices', $data, ['unit_id'=>$unit_id]);
            return rest_ensure_response(['status'=>'ok']);
        },
        'permission_callback' => '__return_true',
    ]);

    // Upsert a company record (by id) for hierarchy tying
    register_rest_route('tmon/v1', '/admin/company/upsert', [
        'methods' => 'POST',
        'callback' => function($request){
            if (!tmon_uc_admin_integration_auth($request)) return new WP_REST_Response(['status'=>'forbidden'], 403);
            global $wpdb;
            $p = $request->get_json_params();
            $company_id = isset($p['company_id']) ? intval($p['company_id']) : 0;
            $name = isset($p['name']) ? sanitize_text_field($p['name']) : '';
            if (!$company_id || !$name) return rest_ensure_response(['status'=>'error','message'=>'company_id and name required']);
            $table = $wpdb->prefix.'tmon_company';
            $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $table WHERE id=%d", $company_id));
            if ($exists) {
                $wpdb->update($table, ['name'=>$name], ['id'=>$company_id]);
            } else {
                $wpdb->query($wpdb->prepare("INSERT INTO $table (id, name, created_at, updated_at) VALUES (%d, %s, %s, %s)", $company_id, $name, current_time('mysql'), current_time('mysql')));
            }
            return rest_ensure_response(['status'=>'ok']);
        },
        'permission_callback' => '__return_true',
    ]);

    // List known devices (unit_id, machine_id, name, last_seen) for Admin provisioning dropdowns
    register_rest_route('tmon/v1', '/admin/devices', [
        'methods' => 'GET',
        'callback' => function($request){
            if (!tmon_uc_admin_read_auth($request)) return new WP_REST_Response(['status'=>'forbidden'], 403);
            global $wpdb;
            $rows = $wpdb->get_results("SELECT unit_id, machine_id, unit_name, last_seen FROM {$wpdb->prefix}tmon_devices ORDER BY unit_id ASC", ARRAY_A);
            return rest_ensure_response(['status' => 'ok', 'devices' => is_array($rows) ? $rows : []]);
        },
        'permission_callback' => '__return_true',
    ]);

    // Upsert hierarchy entities: site, zone, cluster, unit
    register_rest_route('tmon/v1', '/admin/site/upsert', [
        'methods' => 'POST',
        'callback' => function($request){
            if (!tmon_uc_admin_integration_auth($request)) return new WP_REST_Response(['status'=>'forbidden'], 403);
            global $wpdb;
            $p = $request->get_json_params();
            $id = isset($p['id']) ? intval($p['id']) : 0;
            $company_id = isset($p['company_id']) ? intval($p['company_id']) : 0;
            $name = isset($p['name']) ? sanitize_text_field($p['name']) : '';
            if (!$id || !$company_id || !$name) return rest_ensure_response(['status'=>'error','message'=>'id, company_id, name required']);
            $table = $wpdb->prefix.'tmon_site';
            $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $table WHERE id=%d", $id));
            $data = ['company_id'=>$company_id,'name'=>$name,'updated_at'=>current_time('mysql')];
            if ($exists) { $wpdb->update($table, $data, ['id'=>$id]); }
            else { $wpdb->query($wpdb->prepare("INSERT INTO $table (id, company_id, name, created_at, updated_at) VALUES (%d, %d, %s, %s, %s)", $id, $company_id, $name, current_time('mysql'), current_time('mysql'))); }
            return rest_ensure_response(['status'=>'ok']);
        },
        'permission_callback' => '__return_true',
    ]);
    register_rest_route('tmon/v1', '/admin/zone/upsert', [
        'methods' => 'POST',
        'callback' => function($request){
            if (!tmon_uc_admin_integration_auth($request)) return new WP_REST_Response(['status'=>'forbidden'], 403);
            global $wpdb;
            $p = $request->get_json_params();
            $id = isset($p['id']) ? intval($p['id']) : 0;
            $site_id = isset($p['site_id']) ? intval($p['site_id']) : 0;
            $name = isset($p['name']) ? sanitize_text_field($p['name']) : '';
            if (!$id || !$site_id || !$name) return rest_ensure_response(['status'=>'error','message'=>'id, site_id, name required']);
            $table = $wpdb->prefix.'tmon_zone';
            $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $table WHERE id=%d", $id));
            $data = ['site_id'=>$site_id,'name'=>$name,'updated_at'=>current_time('mysql')];
            if ($exists) { $wpdb->update($table, $data, ['id'=>$id]); }
            else { $wpdb->query($wpdb->prepare("INSERT INTO $table (id, site_id, name, created_at, updated_at) VALUES (%d, %d, %s, %s, %s)", $id, $site_id, $name, current_time('mysql'), current_time('mysql'))); }
            return rest_ensure_response(['status'=>'ok']);
        },
        'permission_callback' => '__return_true',
    ]);
    register_rest_route('tmon/v1', '/admin/cluster/upsert', [
        'methods' => 'POST',
        'callback' => function($request){
            if (!tmon_uc_admin_integration_auth($request)) return new WP_REST_Response(['status'=>'forbidden'], 403);
            global $wpdb;
            $p = $request->get_json_params();
            $id = isset($p['id']) ? intval($p['id']) : 0;
            $zone_id = isset($p['zone_id']) ? intval($p['zone_id']) : 0;
            $name = isset($p['name']) ? sanitize_text_field($p['name']) : '';
            if (!$id || !$zone_id || !$name) return rest_ensure_response(['status'=>'error','message'=>'id, zone_id, name required']);
            $table = $wpdb->prefix.'tmon_cluster';
            $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $table WHERE id=%d", $id));
            $data = ['zone_id'=>$zone_id,'name'=>$name,'updated_at'=>current_time('mysql')];
            if ($exists) { $wpdb->update($table, $data, ['id'=>$id]); }
            else { $wpdb->query($wpdb->prepare("INSERT INTO $table (id, zone_id, name, created_at, updated_at) VALUES (%d, %d, %s, %s, %s)", $id, $zone_id, $name, current_time('mysql'), current_time('mysql'))); }
            return rest_ensure_response(['status'=>'ok']);
        },
        'permission_callback' => '__return_true',
    ]);
    register_rest_route('tmon/v1', '/admin/unit/upsert', [
        'methods' => 'POST',
        'callback' => function($request){
            if (!tmon_uc_admin_integration_auth($request)) return new WP_REST_Response(['status'=>'forbidden'], 403);
            global $wpdb;
            $p = $request->get_json_params();
            $id = isset($p['id']) ? intval($p['id']) : 0;
            $cluster_id = isset($p['cluster_id']) ? intval($p['cluster_id']) : 0;
            $name = isset($p['name']) ? sanitize_text_field($p['name']) : '';
            if (!$id || !$cluster_id || !$name) return rest_ensure_response(['status'=>'error','message'=>'id, cluster_id, name required']);
            $table = $wpdb->prefix.'tmon_unit';
            $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $table WHERE id=%d", $id));
            $data = ['cluster_id'=>$cluster_id,'name'=>$name,'updated_at'=>current_time('mysql')];
            if ($exists) { $wpdb->update($table, $data, ['id'=>$id]); }
            else { $wpdb->query($wpdb->prepare("INSERT INTO $table (id, cluster_id, name, created_at, updated_at) VALUES (%d, %d, %s, %s, %s)", $id, $cluster_id, $name, current_time('mysql'), current_time('mysql'))); }
            return rest_ensure_response(['status'=>'ok']);
        },
        'permission_callback' => '__return_true',
    ]);

    // Set/rotate read token from Hub (Admin) for read-only listings
    register_rest_route('tmon/v1', '/admin/read-token/set', [
        'methods' => 'POST',
        'callback' => function($request){
            if (!tmon_uc_admin_integration_auth($request)) return new WP_REST_Response(['status'=>'forbidden'], 403);
            $p = $request->get_json_params();
            $token = isset($p['read_token']) ? sanitize_text_field($p['read_token']) : '';
            // Empty token = revoke
            update_option('tmon_uc_hub_read_token', $token);
            return rest_ensure_response(['status'=>'ok']);
        },
        'permission_callback' => '__return_true',
    ]);
});

function tmon_uc_api_device_register($request) {
    global $wpdb;
    $params = $request->get_json_params();
    $unit_id = isset($params['unit_id']) ? sanitize_text_field($params['unit_id']) : '';
    $machine_id = isset($params['machine_id']) ? sanitize_text_field($params['machine_id']) : '';
    $unit_name = isset($params['unit_name']) ? sanitize_text_field($params['unit_name']) : '';
    $company = isset($params['company']) ? sanitize_text_field($params['company']) : '';
    $site = isset($params['site']) ? sanitize_text_field($params['site']) : '';
    $zone = isset($params['zone']) ? sanitize_text_field($params['zone']) : '';
    $cluster = isset($params['cluster']) ? sanitize_text_field($params['cluster']) : '';
    // If machine_id is known and already mapped, reuse its unit_id
    if ($machine_id) {
        $existing = $wpdb->get_row($wpdb->prepare("SELECT unit_id FROM {$wpdb->prefix}tmon_devices WHERE machine_id = %s", $machine_id));
        if ($existing && !empty($existing->unit_id)) {
            $unit_id = $existing->unit_id;
        }
    }
    if (!$unit_id || $unit_id === '800000' || $unit_id === '999999') {
        // Generate unique 6-digit ID
        do {
            $unit_id = str_pad(strval(rand(100000, 999999)), 6, '0', STR_PAD_LEFT);
            $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM {$wpdb->prefix}tmon_devices WHERE unit_id = %s", $unit_id));
        } while ($exists);
    }
    // Insert or update device
    // If there's an existing row for this unit_id or machine_id, preserve mapping
    $table = $wpdb->prefix . 'tmon_devices';
    $row = null;
    if ($machine_id) {
        $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE machine_id = %s", $machine_id), ARRAY_A);
    }
    if (!$row) {
        $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE unit_id = %s", $unit_id), ARRAY_A);
    }
    $data = [
        'unit_id' => $unit_id,
        'machine_id' => $machine_id ?: ($row['machine_id'] ?? null),
        'unit_name' => ($unit_name !== '' ? $unit_name : ($row['unit_name'] ?? '')),
        'company' => $company ?: ($row['company'] ?? ''),
        'site' => $site ?: ($row['site'] ?? ''),
        'zone' => $zone ?: ($row['zone'] ?? ''),
        'cluster' => $cluster ?: ($row['cluster'] ?? ''),
        'last_seen' => current_time('mysql'),
    ];
    if ($row) {
        $wpdb->update($table, $data, ['unit_id' => $row['unit_id']]);
        $unit_id = $row['unit_id'];
    } else {
        $wpdb->insert($table, $data);
    }
    return rest_ensure_response(['status' => 'ok', 'unit_id' => $unit_id, 'machine_id' => $data['machine_id']]);
}
function tmon_uc_api_device_settings($request) {
    global $wpdb;
    $params = $request->get_json_params();
    $unit_id = isset($params['unit_id']) ? sanitize_text_field($params['unit_id']) : '';
    $settings = isset($params['settings']) ? wp_json_encode($params['settings']) : '';
    if ($unit_id && $settings) {
        // Arbitrary settings blob persisted; includes GPS_* overrides if provided
        $data = ['settings' => $settings, 'last_seen' => current_time('mysql')];
        // If the provided settings contain a UNIT_Name or unit_name, reflect it into unit_name column for UI/reporting
        $decoded = json_decode($settings, true);
        if (is_array($decoded)) {
            if (!empty($decoded['UNIT_Name'])) {
                $data['unit_name'] = sanitize_text_field($decoded['UNIT_Name']);
            } elseif (!empty($decoded['unit_name'])) {
                $data['unit_name'] = sanitize_text_field($decoded['unit_name']);
            }
        }
        $wpdb->update(
            $wpdb->prefix . 'tmon_devices',
            $data,
            ['unit_id' => $unit_id]
        );
        return rest_ensure_response(['status' => 'ok']);
    }
    return rest_ensure_response(['status' => 'error', 'message' => 'Missing unit_id or settings']);
}
function tmon_uc_api_device_settings_get($request) {
    global $wpdb;
    $unit_id = $request->get_param('unit_id');
    $row = $wpdb->get_row($wpdb->prepare("SELECT settings, unit_name FROM {$wpdb->prefix}tmon_devices WHERE unit_id = %s", $unit_id));
    $settings = $row && !empty($row->settings) ? json_decode($row->settings, true) : [];
    if (!is_array($settings)) { $settings = []; }
    // Ensure firmware receives UNIT_Name even if only unit_name column is set in DB
    if (!empty($row->unit_name) && empty($settings['UNIT_Name'])) {
        $settings['UNIT_Name'] = $row->unit_name;
    }
    return rest_ensure_response(['status' => 'ok', 'settings' => $settings]);
}
function tmon_uc_api_device_data($request) {
    global $wpdb;
    $params = $request->get_json_params();
    $unit_id = isset($params['unit_id']) ? sanitize_text_field($params['unit_id']) : '';
    $data = isset($params['data']) ? wp_json_encode($params['data']) : '';
    if ($unit_id && $data) {
        $wpdb->insert(
            $wpdb->prefix . 'tmon_device_data',
            [
                'unit_id' => $unit_id,
                'data' => $data,
                'recorded_at' => current_time('mysql'),
            ]
        );
        return rest_ensure_response(['status' => 'ok']);
    }
    return rest_ensure_response(['status' => 'error', 'message' => 'Missing unit_id or data']);
}
function tmon_uc_api_device_file_upload($request) {
    if (empty($_FILES['file'])) {
        return rest_ensure_response(['status' => 'error', 'message' => 'No file uploaded']);
    }
    $file = $_FILES['file'];
    $upload_dir = wp_upload_dir();
    $target = $upload_dir['basedir'] . '/tmon_device_files/';
    if (!file_exists($target)) {
        mkdir($target, 0755, true);
    }
    $filename = basename($file['name']);
    $filepath = $target . $filename;
    if (move_uploaded_file($file['tmp_name'], $filepath)) {
        return rest_ensure_response(['status' => 'ok', 'file' => $filename]);
    }
    return rest_ensure_response(['status' => 'error', 'message' => 'Upload failed']);
}
function tmon_uc_api_device_file_download($request) {
    $filename = sanitize_file_name($request->get_param('filename'));
    $upload_dir = wp_upload_dir();
    $filepath = $upload_dir['basedir'] . '/tmon_device_files/' . $filename;
    if (file_exists($filepath)) {
        $content = file_get_contents($filepath);
        return rest_ensure_response(['status' => 'ok', 'file' => base64_encode($content)]);
    }
    return rest_ensure_response(['status' => 'error', 'message' => 'File not found']);
}
