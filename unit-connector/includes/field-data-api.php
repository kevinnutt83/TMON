<?php
// REST API for field data and data history log upload
// Permission: allow logged-in users locally, else require hub read auth (token/keys)
if (!function_exists('tmon_uc_read_permission')) {
function tmon_uc_read_permission($request) {
    if (is_user_logged_in()) return true;
    if (function_exists('tmon_uc_admin_read_auth')) return tmon_uc_admin_read_auth($request);
    return false;
}}

add_action('rest_api_init', function() {
    register_rest_route('tmon/v1', '/device/field-data', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_receive_field_data',
        'permission_callback' => '__return_true',
    ]);
    register_rest_route('tmon/v1', '/device/data-history', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_receive_data_history',
        'permission_callback' => '__return_true',
    ]);
    register_rest_route('tmon/v1', '/device/history', [
        'methods' => 'GET',
        'callback' => 'tmon_uc_get_device_history',
        // Publicly readable so front-end shortcodes can fetch without special headers
        'permission_callback' => '__return_true',
        'args' => [
            'unit_id' => ['required' => true],
            'hours' => ['required' => false],
        ],
    ]);

    // Token-protected CSV export (normalized fields); optional unit_id/time-window filters and gzip
    register_rest_route('tmon/v1', '/admin/field-data.csv', [
        'methods' => 'GET',
        'callback' => 'tmon_uc_rest_export_field_data',
        'permission_callback' => 'tmon_uc_read_permission',
        'args' => [
            'unit_id' => ['required' => false],
            'since'   => ['required' => false],
            'until'   => ['required' => false],
            'hours'   => ['required' => false],
            'gzip'    => ['required' => false],
        ],
    ]);

    // Token-protected JSON listing of recent field data rows (for Admin hub UI aggregation)
    register_rest_route('tmon/v1', '/admin/field-data', [
        'methods' => 'GET',
        'callback' => 'tmon_uc_rest_list_field_data',
        'permission_callback' => 'tmon_uc_read_permission',
        'args' => [
            'unit_id' => ['required' => false],
            'hours'   => ['required' => false],
            'limit'   => ['required' => false],
        ],
    ]);
});

function tmon_uc_rest_list_field_data($request) {
    global $wpdb;
    $unit_id = sanitize_text_field($request->get_param('unit_id') ?? '');
    $hours = intval($request->get_param('hours') ?? 24);
    if ($hours <= 0) $hours = 24;
    $limit = intval($request->get_param('limit') ?? 200);
    $limit = max(1, min(2000, $limit));
    $since = gmdate('Y-m-d H:i:s', time() - ($hours * 3600));
    $table = $wpdb->prefix.'tmon_field_data';
    $where = ['created_at >= %s'];
    $args = [$since];
    if ($unit_id) { $where[] = 'unit_id = %s'; $args[] = $unit_id; }
    $sql = "SELECT unit_id, data, created_at FROM $table WHERE ".implode(' AND ', $where)." ORDER BY created_at DESC LIMIT $limit";
    $rows = $wpdb->get_results($wpdb->prepare($sql, ...$args), ARRAY_A);
    $out = [];
    foreach ($rows as $r) {
        $payload = json_decode($r['data'], true);
        if (!is_array($payload)) $payload = [];
        // Merge created_at as ts_iso for UI, include unit_id
        $payload['unit_id'] = $r['unit_id'];
        $payload['ts_iso'] = $r['created_at'];
        $out[] = $payload;
    }
    return rest_ensure_response(['status'=>'ok','rows'=>$out]);
}

function tmon_uc_rest_export_field_data($request) {
    global $wpdb;
    $unit_id = sanitize_text_field($request->get_param('unit_id') ?? '');
    $since_param = $request->get_param('since');
    $until_param = $request->get_param('until');
    $hours_param = $request->get_param('hours');
    $gzip_param  = $request->get_param('gzip');

    // Determine time window. created_at is stored with current_time('mysql') (site local time).
    $now_ts = function_exists('current_time') ? current_time('timestamp') : time();
    $since_ts = null;
    $until_ts = null;
    if (!empty($since_param)) {
        $t = strtotime($since_param);
        if ($t !== false) { $since_ts = $t; }
    }
    if (!empty($hours_param) && !$since_ts) {
        $h = intval($hours_param);
        if ($h > 0) { $since_ts = $now_ts - ($h * 3600); }
    }
    if (!empty($until_param)) {
        $t = strtotime($until_param);
        if ($t !== false) { $until_ts = $t; }
    }
    if (!$until_ts) { $until_ts = $now_ts; }
    $since = $since_ts ? date_i18n('Y-m-d H:i:s', $since_ts) : null;
    $until = $until_ts ? date_i18n('Y-m-d H:i:s', $until_ts) : null;

    // Parse gzip flag
    $gzip = false;
    if ($gzip_param !== null) {
        $val = strtolower((string)$gzip_param);
        $gzip = in_array($val, ['1','true','yes','on'], true);
    }

    // Build CSV in memory
    $fh = fopen('php://temp', 'r+');
    // Header row consistent with admin export
    fputcsv($fh, ['created_at','unit_id','origin','timestamp','name','machine_id','temp_f','temp_c','humidity','pressure','voltage_v','wifi_rssi','lora_rssi','free_mem','gps_lat','gps_lng','gps_alt_m','gps_accuracy_m','gps_last_fix_ts']);
    $query = "SELECT unit_id, data, created_at FROM {$wpdb->prefix}tmon_field_data";
    $qargs = [];
    $where = [];
    if ($unit_id) { $where[] = "unit_id=%s"; $qargs[] = $unit_id; }
    if ($since)  { $where[] = "created_at >= %s"; $qargs[] = $since; }
    if ($until)  { $where[] = "created_at <= %s"; $qargs[] = $until; }
    if ($where) { $query .= ' WHERE ' . implode(' AND ', $where); }
    $query .= " ORDER BY created_at ASC";
    $rows = $qargs ? $wpdb->get_results($wpdb->prepare($query, ...$qargs), ARRAY_A) : $wpdb->get_results($query, ARRAY_A);
    foreach ($rows as $r) {
        $d = json_decode($r['data'], true);
        if (!is_array($d)) continue;
        $origin = 'unknown';
        if (!empty($d['machine_id'])) {
            $origin = 'remote';
        } elseif (!empty($d['NODE_TYPE'])) {
            $origin = strtolower($d['NODE_TYPE']) === 'remote' ? 'remote' : 'base';
        } else {
            // Heuristic: if keys look like compact remote telemetry (t_f, hum, bar, v, fm), assume remote
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
        fputcsv($fh, $flat);
    }
    rewind($fh);
    $csv = stream_get_contents($fh);
    fclose($fh);
    // Filename composition
    $filename = 'tmon_field_data' . ($unit_id ? ('_'.$unit_id) : '');
    if ($since_ts || $until_ts) {
        $fn_since = $since_ts ? gmdate('Ymd_His', $since_ts) : 'start';
        $fn_until = $until_ts ? gmdate('Ymd_His', $until_ts) : 'now';
        $filename .= "_{$fn_since}-{$fn_until}";
    }
    $is_gz = $gzip && function_exists('gzencode');
    $body = $is_gz ? gzencode($csv, 6) : $csv;
    $filename .= $is_gz ? '.csv.gz' : '.csv';
    $resp = new WP_REST_Response($body, 200);
    $resp->header('Content-Type', $is_gz ? 'application/gzip' : 'text/csv; charset=utf-8');
    if ($is_gz) { $resp->header('Content-Encoding', 'gzip'); $resp->header('Vary', 'Accept-Encoding'); }
    $resp->header('X-Content-Type-Options', 'nosniff');
    $resp->header('Content-Disposition', 'attachment; filename="'.$filename.'"');
    return $resp;
}

function tmon_uc_receive_field_data($request) {
    global $wpdb;
    $data = $request->get_json_params();
    $log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
    if (!file_exists($log_dir)) {
        mkdir($log_dir, 0777, true);
    }
    $unit_id = isset($data['unit_id']) ? sanitize_text_field($data['unit_id']) : '';
    $machine_id = isset($data['machine_id']) ? sanitize_text_field($data['machine_id']) : '';
    $log_file = $log_dir . "/field_data_{$unit_id}.log";
    // Save inbound JSON envelope (raw for troubleshooting)
    file_put_contents($log_file, wp_json_encode($data) . "\n", FILE_APPEND);

    // Helper: flatten a record to a CSV-ready array with consistent keys
    $flatten = function($rec) {
        if (!is_array($rec)) return [];
        $out = [];
        $out['timestamp'] = $rec['timestamp'] ?? ($rec['time'] ?? current_time('mysql'));
        $out['unit_id']   = $rec['unit_id'] ?? '';
        $out['machine_id']= $rec['machine_id'] ?? '';
        $out['name']      = $rec['name'] ?? '';
        // Common sensor aliases
        $out['temp_f']    = isset($rec['t_f']) ? $rec['t_f'] : ($rec['cur_temp_f'] ?? null);
        $out['temp_c']    = isset($rec['t_c']) ? $rec['t_c'] : ($rec['cur_temp_c'] ?? null);
        $out['humidity']  = isset($rec['hum']) ? $rec['hum'] : ($rec['cur_humid'] ?? null);
        $out['pressure']  = isset($rec['bar']) ? $rec['bar'] : ($rec['cur_bar_pres'] ?? null);
        $out['voltage_v'] = isset($rec['v']) ? $rec['v'] : ($rec['sys_voltage'] ?? null);
        $out['wifi_rssi'] = $rec['wifi_rssi'] ?? null;
        $out['lora_rssi'] = $rec['lora_SigStr'] ?? null;
        $out['free_mem']  = isset($rec['fm']) ? $rec['fm'] : ($rec['free_mem'] ?? null);
        // GPS fields if present
        $out['gps_lat']   = $rec['gps_lat'] ?? ($rec['GPS_LAT'] ?? null);
        $out['gps_lng']   = $rec['gps_lng'] ?? ($rec['GPS_LNG'] ?? null);
        $out['gps_alt_m'] = $rec['gps_alt_m'] ?? ($rec['GPS_ALT_M'] ?? null);
        $out['gps_accuracy_m'] = $rec['gps_accuracy_m'] ?? ($rec['GPS_ACCURACY_M'] ?? null);
        $out['gps_last_fix_ts'] = $rec['gps_last_fix_ts'] ?? ($rec['GPS_LAST_FIX_TS'] ?? null);
        return $out;
    };

    // Helper: write CSV with header if new/empty
    $write_csv = function($csv_file, $row_assoc) {
        if (!$row_assoc) return;
        $is_new = !file_exists($csv_file) || filesize($csv_file) === 0;
        $fh = fopen($csv_file, 'a');
        if ($fh) {
            if ($is_new) {
                fputcsv($fh, array_keys($row_assoc));
            }
            // Sanitize values, cast scalars
            $vals = [];
            foreach ($row_assoc as $v) {
                if (is_array($v) || is_object($v)) {
                    $vals[] = wp_json_encode($v);
                } else {
                    $vals[] = is_scalar($v) ? $v : strval($v);
                }
            }
            fputcsv($fh, $vals);
            fclose($fh);
        }
    };

    // Helper: forward unauthorized device to central admin for provisioning
    $forward_unknown = function($rec_unit, $rec_machine, $payload) {
    $hub = defined('TMON_ADMIN_HUB_URL') ? TMON_ADMIN_HUB_URL : get_option('tmon_uc_hub_url', 'https://tmonsystems.com');
    if (!$hub) { $hub = 'https://tmonsystems.com'; }
        if (!$hub) return; // no hub configured
        $endpoint = rtrim($hub, '/') . '/wp-json/tmon-admin/v1/ingest-unknown';
        $body = [
            'unit_id' => $rec_unit,
            'machine_id' => $rec_machine,
            'site_url' => home_url(),
        ];
        // Best-effort HTTP POST
        wp_remote_post($endpoint, [
            'timeout' => 5,
            'headers' => [ 'Content-Type' => 'application/json' ],
            'body' => wp_json_encode($body),
        ]);
    };

    // Normalize records: support either a single reading or a batch under data
    $records = [];
    if (isset($data['data']) && is_array($data['data'])) {
        $records = $data['data'];
    } else {
        $records = [$data];
    }

    // If machine_id is provided but unit_id is empty or placeholder, try to map
    if ($machine_id && (!$unit_id || $unit_id === '800000' || $unit_id === '999999')) {
        $mapped = $wpdb->get_var($wpdb->prepare("SELECT unit_id FROM {$wpdb->prefix}tmon_devices WHERE machine_id=%s", $machine_id));
        if ($mapped) {
            $unit_id = $mapped;
        }
    }

    $received = 0;
    foreach ($records as $rec) {
        if (!is_array($rec)) continue;
        // REMOTE_NODE_INFO may be on the record (from base) or top-level
        $remote_map = [];
        if (isset($rec['REMOTE_NODE_INFO']) && is_array($rec['REMOTE_NODE_INFO'])) {
            $remote_map = $rec['REMOTE_NODE_INFO'];
        } elseif (isset($data['REMOTE_NODE_INFO']) && is_array($data['REMOTE_NODE_INFO'])) {
            $remote_map = $data['REMOTE_NODE_INFO'];
        }

        // First, persist the primary record (base or direct remote),
        // then persist each embedded remote record if provided.
        $targets = [];
        // Always include the primary record so base station data is stored
        $targets[] = $rec;
        if (!empty($remote_map)) {
            // For each remote embedded record, prepare a per-remote target
            foreach ($remote_map as $rid => $rdata) {
                if (!is_array($rdata)) continue;
                $rdata['unit_id'] = isset($rdata['unit_id']) ? $rdata['unit_id'] : $rid;
                $targets[] = $rdata;
            }
        }

        foreach ($targets as $t) {
            $rec_unit = isset($t['unit_id']) ? sanitize_text_field($t['unit_id']) : $unit_id;
            $rec_machine = isset($t['machine_id']) ? sanitize_text_field($t['machine_id']) : $machine_id;

            // Persist machine_id to unit mapping if both present
            if ($rec_unit && $rec_machine) {
                $row = $wpdb->get_row($wpdb->prepare("SELECT unit_id, machine_id FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s OR machine_id=%s", $rec_unit, $rec_machine), ARRAY_A);
                if ($row) {
                    // Update existing row to ensure mapping is set
                    $wpdb->update($wpdb->prefix.'tmon_devices', ['machine_id'=>$rec_machine, 'last_seen'=>current_time('mysql')], ['unit_id'=>$row['unit_id']]);
                    $rec_unit = $row['unit_id'];
                } else {
                    // Create new mapping row minimally
                    $wpdb->insert($wpdb->prefix.'tmon_devices', [
                        'unit_id' => $rec_unit ?: $machine_id,
                        'machine_id' => $rec_machine,
                        'unit_name' => $rec_unit ?: $rec_machine,
                        'last_seen' => current_time('mysql'),
                        'suspended' => 0,
                    ]);
                }
            }

            // Per-record authorization via tmon-admin
            $authorized = apply_filters('tmon_admin_authorize_device', true, $rec_unit, $rec_machine);
            if (!$authorized) {
                // forward for provisioning and skip local store
                $forward_unknown($rec_unit, $rec_machine, $t);
                continue;
            }
            $rec_json = wp_json_encode($t);
            // Persist raw field data row
            $wpdb->insert(
                $wpdb->prefix . 'tmon_field_data',
                [
                    'unit_id' => $rec_unit,
                    'data' => $rec_json,
                    'created_at' => current_time('mysql')
                ]
            );
            // Append normalized CSV row per received record (per unit)
            $csv_file_unit = $log_dir . "/field_data_{$rec_unit}.csv";
            $write_csv($csv_file_unit, $flatten($t));
            // Ensure device exists; update last_seen and unit_name if provided
            $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $rec_unit));
            $incoming_name = isset($t['name']) ? sanitize_text_field($t['name']) : '';
            if (!$exists) {
                $wpdb->insert($wpdb->prefix.'tmon_devices', [
                    'unit_id' => $rec_unit,
                    'unit_name' => $incoming_name ?: $rec_unit,
                    'last_seen' => current_time('mysql'),
                    'suspended' => 0,
                ]);
            } else {
                $update = ['last_seen' => current_time('mysql')];
                if ($incoming_name) { $update['unit_name'] = $incoming_name; }
                $wpdb->update($wpdb->prefix.'tmon_devices', $update, ['unit_id' => $rec_unit]);
            }
            // Update status JSON with latest GPS if present
            $gps_lat = $t['gps_lat'] ?? ($t['GPS_LAT'] ?? null);
            $gps_lng = $t['gps_lng'] ?? ($t['GPS_LNG'] ?? null);
            if ($gps_lat !== null && $gps_lng !== null) {
                $row = $wpdb->get_row($wpdb->prepare("SELECT status FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $rec_unit));
                $status = $row && $row->status ? json_decode($row->status, true) : [];
                if (!is_array($status)) $status = [];
                $status['gps_lat'] = floatval($gps_lat);
                $status['gps_lng'] = floatval($gps_lng);
                if (isset($t['gps_alt_m']) || isset($t['GPS_ALT_M'])) $status['gps_alt_m'] = floatval($t['gps_alt_m'] ?? $t['GPS_ALT_M']);
                if (isset($t['gps_accuracy_m']) || isset($t['GPS_ACCURACY_M'])) $status['gps_accuracy_m'] = floatval($t['gps_accuracy_m'] ?? $t['GPS_ACCURACY_M']);
                if (isset($t['gps_last_fix_ts']) || isset($t['GPS_LAST_FIX_TS'])) $status['gps_last_fix_ts'] = $t['gps_last_fix_ts'] ?? $t['GPS_LAST_FIX_TS'];
                $wpdb->update($wpdb->prefix.'tmon_devices', ['status' => wp_json_encode($status)], ['unit_id' => $rec_unit]);
            }
            // Forward to tmon-admin for centralized admin processing
            do_action('tmon_admin_receive_field_data', $rec_unit, $t);
            $received++;
        }
    }

    // Include resolved unit_id/machine_id for device to persist mapping
    return rest_ensure_response(['status' => 'ok', 'received' => $received > 0, 'count' => $received, 'unit_id' => $unit_id ?: ($data['unit_id'] ?? ''), 'machine_id' => $machine_id]);
}

function tmon_uc_receive_data_history($request) {
    $unit_id = $request->get_param('unit_id');
    $file = $request->get_file_params()['file'] ?? null;
    $log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
    if (!file_exists($log_dir)) {
        mkdir($log_dir, 0777, true);
    }
    if ($file && $unit_id) {
        $dest = $log_dir . "/data_history_{$unit_id}_" . time() . ".log";
        move_uploaded_file($file['tmp_name'], $dest);
        return rest_ensure_response(['status' => 'ok', 'received' => true]);
    }
    return rest_ensure_response(['status' => 'error', 'received' => false]);
}

function tmon_uc_get_device_history($request) {
    global $wpdb;
    $unit_id = sanitize_text_field($request->get_param('unit_id'));
    $hours = intval($request->get_param('hours')) ?: 24;
    $since = gmdate('Y-m-d H:i:s', time() - $hours * 3600);
    $rows = $wpdb->get_results($wpdb->prepare("SELECT data, created_at FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s AND created_at >= %s ORDER BY created_at ASC", $unit_id, $since), ARRAY_A);
    $points = [];
    foreach ($rows as $r) {
        $d = json_decode($r['data'], true);
        if (!is_array($d)) continue;
        $points[] = [
            't' => $r['created_at'],
            'temp_f' => $d['t_f'] ?? ($d['cur_temp_f'] ?? null),
            'humid' => $d['hum'] ?? ($d['cur_humid'] ?? null),
            'bar' => $d['bar'] ?? ($d['cur_bar_pres'] ?? null),
        ];
    }
    return rest_ensure_response(['status' => 'ok', 'unit_id' => $unit_id, 'hours' => $hours, 'points' => $points]);
}
