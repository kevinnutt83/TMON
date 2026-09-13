<?php
/**
 * TMON Unit Connector — device dispatch overlay
 * Unifies staged settings + commands + provision for base/wifi/remote delivery.
 */
if (!defined('ABSPATH')) {
    exit;
}

if (!function_exists('tmon_uc_dispatch_allowed_keys')) {
    function tmon_uc_dispatch_allowed_keys() {
        $keys = array(
            'NODE_TYPE', 'UNIT_Name', 'UNIT_ID', 'SAMPLE_TEMP', 'SAMPLE_HUMID', 'SAMPLE_BAR',
            'ENABLE_OLED', 'ENGINE_ENABLED', 'ENABLE_FROSTWATCH', 'FROSTWATCH_ACTIVE_TEMP',
            'FROSTWATCH_ALERT_TEMP', 'FROSTWATCH_ACTION_TEMP', 'FROSTWATCH_STANDDOWN_TEMP',
            'ENABLE_HEATWATCH', 'HEATWATCH_ACTIVE_TEMP', 'HEATWATCH_ALERT_TEMP',
            'HEATWATCH_ACTION_TEMP', 'HEATWATCH_STANDDOWN_TEMP', 'RELAY_PIN1', 'RELAY_PIN2',
            'RELAY_RUNTIME_LIMITS', 'WIFI_SSID', 'WIFI_PASS', 'ENABLE_sensorBME280',
            'ENABLE_WIFI', 'ENABLE_LORA', 'DEVICE_SUSPENDED', 'FIELD_DATA_HMAC_ENABLED',
            'FIELD_DATA_HMAC_SECRET', 'WORDPRESS_API_URL', 'TMON_ADMIN_API_URL',
            'LORA_SYNC_RATE', 'REMOTE_SYNC_INTERVAL_S', 'LORA_CHUNK_SIZE',
            'LORA_MAX_PACKET_SIZE', 'LORA_ENABLE_CAD', 'LORA_SLOT_SPACING_S',
            'LORA_SESSION_BUSY_TIMEOUT_S', 'FREQ', 'SF', 'BW', 'CR', 'POWER', 'SYNC_WORD',
            'ENABLE_DIAGNOSTICS_UPLOAD', 'FIELD_DATA_SEND_INTERVAL', 'COMPANY', 'SITE',
            'ZONE', 'CLUSTER',
        );
        return apply_filters('tmon_staged_settings_allowed_keys', $keys);
    }
}

if (!function_exists('tmon_uc_dispatch_sanitize_settings')) {
    function tmon_uc_dispatch_sanitize_settings($settings) {
        if (!is_array($settings)) {
            return array();
        }
        $allowed = tmon_uc_dispatch_allowed_keys();
        $safe = array();
        foreach ($settings as $k => $v) {
            $k = sanitize_text_field((string) $k);
            if ($k === '' || !in_array($k, $allowed, true)) {
                continue;
            }
            if (is_string($v) && in_array(strtolower($v), array('true', 'false', '1', '0', 'yes', 'no'), true)) {
                $v = in_array(strtolower($v), array('true', '1', 'yes'), true);
            }
            $safe[$k] = $v;
        }
        if (($safe['NODE_TYPE'] ?? '') === 'remote') {
            $safe['ENABLE_WIFI'] = false;
        }
        return $safe;
    }
}

if (!function_exists('tmon_uc_dispatch_stage_settings')) {
    function tmon_uc_dispatch_stage_settings($unit_id, $settings, $who = '') {
        $unit_id = sanitize_text_field((string) $unit_id);
        $settings = tmon_uc_dispatch_sanitize_settings($settings);
        if ($unit_id === '' || empty($settings)) {
            return new WP_Error('invalid', 'unit_id and settings required');
        }
        $machine_id = '';
        if (function_exists('uc_devices_ensure_table')) {
            uc_devices_ensure_table();
        }
        global $wpdb;
        $table = $wpdb->prefix . 'tmon_uc_devices';
        $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table} WHERE unit_id=%s LIMIT 1", $unit_id), ARRAY_A);
        if (is_array($row) && !empty($row['machine_id'])) {
            $machine_id = sanitize_text_field((string) $row['machine_id']);
        }
        $payload = wp_json_encode($settings);
        $now = current_time('mysql', true);
        if ($row) {
            $wpdb->update($table, array(
                'staged_settings' => $payload,
                'staged_at' => $now,
            ), array('unit_id' => $unit_id));
        } else {
            $wpdb->insert($table, array(
                'unit_id' => $unit_id,
                'machine_id' => $machine_id,
                'staged_settings' => $payload,
                'staged_at' => $now,
            ));
        }
        $map = get_option('tmon_uc_staged_settings', array());
        if (!is_array($map)) {
            $map = array();
        }
        $map[$unit_id] = array(
            'settings' => $settings,
            'ts' => time(),
            'who' => $who,
            'machine_id' => $machine_id,
            'role' => is_array($row) ? ($row['role'] ?? '') : '',
        );
        update_option('tmon_uc_staged_settings', $map, false);
        do_action('tmon_staged_settings_updated', $unit_id, $settings);
        return array('ok' => true, 'unit_id' => $unit_id, 'settings' => $settings);
    }
}

if (!function_exists('tmon_uc_dispatch_read_staged')) {
    function tmon_uc_dispatch_read_staged($unit_id = '', $machine_id = '') {
        $unit_id = sanitize_text_field((string) $unit_id);
        $machine_id = sanitize_text_field((string) $machine_id);
        $map = get_option('tmon_uc_staged_settings', array());
        if (!is_array($map)) {
            $map = array();
        }
        $entry = null;
        $matched = '';
        if ($unit_id !== '' && isset($map[$unit_id])) {
            $entry = $map[$unit_id];
            $matched = $unit_id;
        } elseif ($machine_id !== '') {
            if (isset($map[$machine_id])) {
                $entry = $map[$machine_id];
                $matched = $machine_id;
            } else {
                foreach ($map as $key => $candidate) {
                    if (is_array($candidate) && isset($candidate['machine_id']) && (string) $candidate['machine_id'] === $machine_id) {
                        $entry = $candidate;
                        $matched = (string) $key;
                        break;
                    }
                }
            }
        }
        if (!$entry) {
            global $wpdb;
            $table = $wpdb->prefix . 'tmon_uc_devices';
            $row = null;
            if ($unit_id !== '') {
                $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table} WHERE unit_id=%s LIMIT 1", $unit_id), ARRAY_A);
            }
            if (!$row && $machine_id !== '') {
                $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table} WHERE machine_id=%s LIMIT 1", $machine_id), ARRAY_A);
            }
            if (is_array($row) && !empty($row['staged_settings'])) {
                $decoded = json_decode($row['staged_settings'], true);
                if (is_array($decoded) && $decoded) {
                    $entry = array(
                        'settings' => $decoded,
                        'ts' => isset($row['staged_at']) ? strtotime($row['staged_at']) : null,
                        'who' => 'devices-table',
                        'machine_id' => $row['machine_id'] ?? '',
                        'role' => $row['role'] ?? '',
                    );
                    $matched = $row['unit_id'] ?? $unit_id;
                }
            }
        }
        if (!$entry) {
            return null;
        }
        $settings_payload = (is_array($entry) && isset($entry['settings']) && is_array($entry['settings'])) ? $entry['settings'] : $entry;
        return array(
            'unit_id' => $matched,
            'staged_exists' => true,
            'staged' => $settings_payload,
            'settings' => $settings_payload,
            'meta' => array(
                'ts' => $entry['ts'] ?? null,
                'who' => $entry['who'] ?? '',
                'role' => $entry['role'] ?? '',
                'machine_id' => $entry['machine_id'] ?? $machine_id,
            ),
        );
    }
}

if (!function_exists('tmon_uc_dispatch_clear_staged')) {
    function tmon_uc_dispatch_clear_staged($unit_id = '', $machine_id = '') {
        $unit_id = sanitize_text_field((string) $unit_id);
        $machine_id = sanitize_text_field((string) $machine_id);
        if (function_exists('tmon_uc_clear_staged_settings_core')) {
            if ($unit_id !== '') {
                tmon_uc_clear_staged_settings_core($unit_id);
            }
            if ($machine_id !== '' && $machine_id !== $unit_id) {
                tmon_uc_clear_staged_settings_core($machine_id);
            }
        } else {
            $map = get_option('tmon_uc_staged_settings', array());
            if (is_array($map)) {
                if ($unit_id !== '') {
                    unset($map[$unit_id]);
                }
                if ($machine_id !== '') {
                    unset($map[$machine_id]);
                }
                update_option('tmon_uc_staged_settings', $map, false);
            }
        }
        global $wpdb;
        $table = $wpdb->prefix . 'tmon_uc_devices';
        if ($unit_id !== '') {
            $wpdb->update($table, array('staged_settings' => null, 'staged_at' => null), array('unit_id' => $unit_id));
        }
        if ($machine_id !== '') {
            $wpdb->update($table, array('staged_settings' => null, 'staged_at' => null), array('machine_id' => $machine_id));
        }
        return true;
    }
}

add_action('admin_post_tmon_uc_stage_settings', function () {
    if (!current_user_can('manage_options')) {
        return;
    }
    $unit_id = isset($_POST['unit_id']) ? sanitize_text_field(wp_unslash($_POST['unit_id'])) : '';
    $settings = array();
    if (function_exists('tmon_uc_merge_settings_from_post') && function_exists('tmon_uc_settings_schema')) {
        $settings = tmon_uc_merge_settings_from_post(tmon_uc_settings_schema());
    } elseif (!empty($_POST['RAW_SETTINGS_JSON'])) {
        $decoded = json_decode(wp_unslash($_POST['RAW_SETTINGS_JSON']), true);
        if (is_array($decoded)) {
            $settings = $decoded;
        }
    }
    if ($unit_id && $settings) {
        tmon_uc_dispatch_stage_settings($unit_id, $settings, wp_get_current_user()->user_login);
    }
}, 1);

add_action('tmon_staged_settings_updated', function ($unit_id, $settings) {
    if (!is_array($settings) || !$unit_id) {
        return;
    }
    $map = get_option('tmon_uc_staged_settings', array());
    if (!is_array($map)) {
        $map = array();
    }
    if (!isset($map[$unit_id]) || !is_array($map[$unit_id])) {
        tmon_uc_dispatch_stage_settings($unit_id, $settings, 'rest');
    }
}, 10, 2);

add_action('rest_api_init', function () {
    register_rest_route('tmon/v1', '/device/staged-settings', array(
        'methods' => 'GET',
        'permission_callback' => '__return_true',
        'callback' => function (WP_REST_Request $req) {
            $unit_id = sanitize_text_field((string) ($req->get_param('unit_id') ?: ''));
            $machine_id = sanitize_text_field((string) ($req->get_param('machine_id') ?: ''));
            $found = tmon_uc_dispatch_read_staged($unit_id, $machine_id);
            if (!$found) {
                return new WP_REST_Response(array('staged_exists' => false, 'staged' => null), 200);
            }
            return new WP_REST_Response($found, 200);
        },
    ));

    register_rest_route('tmon/v1', '/admin/device/settings-staged', array(
        'methods' => 'POST',
        'permission_callback' => function () {
            return current_user_can('manage_options');
        },
        'callback' => function (WP_REST_Request $req) {
            $body = $req->get_json_params();
            if (!is_array($body)) {
                $body = array();
            }
            $unit = sanitize_text_field((string) ($body['unit_id'] ?? $body['device_id'] ?? ''));
            $settings = array();
            if (isset($body['settings']) && is_array($body['settings'])) {
                $settings = $body['settings'];
            } elseif (!empty($body['settings']) && is_string($body['settings'])) {
                $decoded = json_decode(wp_unslash($body['settings']), true);
                $settings = is_array($decoded) ? $decoded : array();
            } elseif (!empty($body['payload']) && is_array($body['payload'])) {
                $settings = $body['payload'];
            }
            $result = tmon_uc_dispatch_stage_settings($unit, $settings, wp_get_current_user()->user_login);
            if (is_wp_error($result)) {
                return $result;
            }
            return new WP_REST_Response($result, 200);
        },
    ));

    $applied_cb = function (WP_REST_Request $req) {
        $body = $req->get_json_params();
        if (!is_array($body)) {
            $body = array();
        }
        $unit_id = sanitize_text_field((string) ($body['unit_id'] ?? $body['device_id'] ?? ''));
        $machine_id = sanitize_text_field((string) ($body['machine_id'] ?? ''));
        $status = sanitize_text_field((string) ($body['status'] ?? 'applied'));
        if ($unit_id === '' && $machine_id === '') {
            return new WP_REST_Response(array('ok' => false, 'message' => 'unit_id or machine_id required'), 400);
        }
        if (in_array($status, array('applied', 'success', 'ok', 'consumed'), true)) {
            tmon_uc_dispatch_clear_staged($unit_id, $machine_id);
        }
        return new WP_REST_Response(array('ok' => true, 'status' => 'consumed', 'unit_id' => $unit_id), 200);
    };

    register_rest_route('tmon/v1', '/device/settings-applied', array(
        'methods' => 'POST',
        'permission_callback' => '__return_true',
        'callback' => $applied_cb,
    ));
    register_rest_route('tmon/v1', '/admin/device/settings-applied', array(
        'methods' => 'POST',
        'permission_callback' => '__return_true',
        'callback' => $applied_cb,
    ));

    $provision_cb = function (WP_REST_Request $req) {
        $unit_id = sanitize_text_field((string) ($req->get_param('unit_id') ?: ''));
        $machine_id = sanitize_text_field((string) ($req->get_param('machine_id') ?: ''));
        if ($unit_id === '' && $machine_id === '') {
            $body = $req->get_json_params();
            if (is_array($body)) {
                $unit_id = sanitize_text_field((string) ($body['unit_id'] ?? ''));
                $machine_id = sanitize_text_field((string) ($body['machine_id'] ?? ''));
            }
        }
        global $wpdb;
        $table = $wpdb->prefix . 'tmon_uc_devices';
        $row = null;
        if ($unit_id !== '') {
            $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table} WHERE unit_id=%s LIMIT 1", $unit_id), ARRAY_A);
        }
        if (!$row && $machine_id !== '') {
            $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$table} WHERE machine_id=%s LIMIT 1", $machine_id), ARRAY_A);
        }
        $staged = tmon_uc_dispatch_read_staged($unit_id ?: ($row['unit_id'] ?? ''), $machine_id ?: ($row['machine_id'] ?? ''));
        $settings = $staged ? $staged['settings'] : array();
        if (is_array($row) && empty($settings) && !empty($row['staged_settings'])) {
            $decoded = json_decode($row['staged_settings'], true);
            if (is_array($decoded)) {
                $settings = $decoded;
            }
        }
        $assigned = is_array($row) ? !empty($row['assigned']) : false;
        return new WP_REST_Response(array(
            'ok' => true,
            'provisioned' => $assigned || !empty($settings),
            'staged_exists' => !empty($settings),
            'unit_id' => is_array($row) ? ($row['unit_id'] ?? $unit_id) : $unit_id,
            'machine_id' => is_array($row) ? ($row['machine_id'] ?? $machine_id) : $machine_id,
            'role' => is_array($row) ? ($row['role'] ?? '') : '',
            'wordpress_api_url' => is_array($row) ? ($row['wordpress_api_url'] ?? home_url()) : home_url(),
            'site_url' => home_url(),
            'settings' => $settings,
            'staged' => $settings,
        ), 200);
    };

    register_rest_route('tmon/v1', '/device/provision', array(
        'methods' => array('GET', 'POST'),
        'permission_callback' => '__return_true',
        'callback' => $provision_cb,
    ));
    register_rest_route('tmon/v1', '/provision', array(
        'methods' => array('GET', 'POST'),
        'permission_callback' => '__return_true',
        'callback' => $provision_cb,
    ));

    $commands_cb = function (WP_REST_Request $req) {
        global $wpdb;
        $body = $req->get_json_params();
        if (!is_array($body)) {
            $body = array();
        }
        $unit_id = sanitize_text_field((string) (
            $req->get_param('unit_id')
            ?: ($body['unit_id'] ?? '')
            ?: ($body['device_id'] ?? '')
        ));
        $claim = !empty($body['claim']) || $req->get_param('claim') === '1' || $req->get_param('claim') === true;
        $limit = intval($body['limit'] ?? $req->get_param('limit') ?? 10);
        if ($limit < 1) {
            $limit = 10;
        }
        if ($limit > 50) {
            $limit = 50;
        }
        if ($unit_id === '') {
            return new WP_Error('bad_request', 'unit_id required', array('status' => 400));
        }
        $table = $wpdb->prefix . 'tmon_device_commands';
        $rows = $wpdb->get_results($wpdb->prepare(
            "SELECT id, command, params, status FROM {$table}
             WHERE device_id=%s AND status IN ('queued','claimed')
             ORDER BY id ASC LIMIT %d",
            $unit_id,
            $limit
        ), ARRAY_A);
        $commands = array();
        $ids = array();
        foreach (($rows ?: array()) as $row) {
            $params = array();
            if (!empty($row['params'])) {
                $decoded = json_decode($row['params'], true);
                $params = is_array($decoded) ? $decoded : array();
            }
            $commands[] = array(
                'id' => intval($row['id']),
                'type' => $row['command'],
                'command' => $row['command'],
                'params' => $params,
                'payload' => $params,
                'status' => $row['status'],
            );
            $ids[] = intval($row['id']);
        }
        if ($claim && $ids) {
            $id_list = implode(',', array_map('intval', $ids));
            $wpdb->query("UPDATE {$table} SET status='claimed', updated_at=UTC_TIMESTAMP() WHERE id IN ({$id_list}) AND status='queued'");
        }
        return rest_ensure_response(array('status' => 'ok', 'commands' => $commands, 'claimed' => $claim));
    };

    register_rest_route('tmon/v1', '/device/commands', array(
        'methods' => array('GET', 'POST'),
        'permission_callback' => '__return_true',
        'callback' => $commands_cb,
    ));
}, 30);