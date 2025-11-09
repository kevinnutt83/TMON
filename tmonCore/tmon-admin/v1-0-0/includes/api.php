<?php
// TMON Admin REST API Endpoints
add_action('rest_api_init', function() {
    register_rest_route('tmon-admin/v1', '/status', [
        'methods' => 'GET',
        'callback' => function() {
            return ['status' => 'ok', 'time' => current_time('mysql')];
        },
        'permission_callback' => '__return_true',
    ]);

    // Aggregate field data from paired Unit Connectors for Admin UI
    register_rest_route('tmon-admin/v1', '/field-data', [
        'methods' => 'GET',
        'permission_callback' => function(){ return current_user_can('manage_options'); },
        'callback' => function($request){
            $hours = intval($request->get_param('hours') ?? 24);
            if ($hours <= 0) $hours = 24;
            $limit = intval($request->get_param('limit') ?? 500);
            $limit = max(1, min(5000, $limit));
            $unit_id = sanitize_text_field($request->get_param('unit_id') ?? '');
            $sites = get_option('tmon_admin_uc_sites', []);
            if (!is_array($sites) || empty($sites)) {
                return rest_ensure_response(['rows'=>[]]);
            }
            $all = [];
            foreach ($sites as $site_url => $meta) {
                $read_token = $meta['read_token'] ?? '';
                if (!$site_url) continue;
                $endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/field-data?hours=' . intval($hours) . '&limit=' . intval($limit) . ($unit_id? ('&unit_id='.rawurlencode($unit_id)) : '');
                $resp = wp_remote_get($endpoint, [
                    'timeout' => 15,
                    'headers' => array_filter([
                        'Accept' => 'application/json',
                        // Prefer dedicated read token if set; fall back to hub key
                        'X-TMON-READ' => $read_token ?: '',
                        'X-TMON-HUB'  => get_option('tmon_admin_uc_key') ?: '',
                    ]),
                ]);
                if (is_wp_error($resp)) continue;
                $code = wp_remote_retrieve_response_code($resp);
                if ($code !== 200) continue;
                $body = json_decode(wp_remote_retrieve_body($resp), true);
                if (is_array($body) && isset($body['rows']) && is_array($body['rows'])) {
                    foreach ($body['rows'] as $row) {
                        if (is_array($row)) { $row['__site'] = $site_url; $all[] = $row; }
                    }
                }
            }
            // Normalize a consistent display name on each row
            foreach ($all as &$row) {
                if (is_array($row)) {
                    if (empty($row['name'])) {
                        $row['name'] = !empty($row['unit_name']) ? $row['unit_name'] : (!empty($row['unit_id']) ? $row['unit_id'] : '');
                    }
                }
            }
            unset($row);
            // Sort by ts_iso desc
            usort($all, function($a,$b){
                $ta = isset($a['ts_iso']) ? strtotime($a['ts_iso']) : 0;
                $tb = isset($b['ts_iso']) ? strtotime($b['ts_iso']) : 0;
                return $tb <=> $ta;
            });
            return rest_ensure_response(['rows'=>$all]);
        }
    ]);
    // Public claim request endpoint (authenticated user recommended)
    register_rest_route('tmon-admin/v1', '/claim', [
        'methods' => 'POST',
        'callback' => function($request) {
            if (!is_user_logged_in()) {
                return new WP_REST_Response(['status' => 'error', 'message' => 'Login required'], 401);
            }
            global $wpdb;
            $unit_id = sanitize_text_field($request->get_param('unit_id'));
            $machine_id = sanitize_text_field($request->get_param('machine_id'));
            if (!$unit_id || !$machine_id) {
                return rest_ensure_response(['status' => 'error', 'message' => 'Missing unit_id or machine_id']);
            }
            $user_id = get_current_user_id();
            $wpdb->insert($wpdb->prefix.'tmon_claim_requests', [
                'unit_id' => $unit_id,
                'machine_id' => $machine_id,
                'user_id' => $user_id,
                'status' => 'pending',
            ]);
            return rest_ensure_response(['status' => 'ok', 'id' => $wpdb->insert_id]);
        },
        'permission_callback' => '__return_true',
    ]);

    // Ingest unknown device reports from Unit Connectors (auto-provisioning queue)
    register_rest_route('tmon-admin/v1', '/ingest-unknown', [
        'methods' => 'POST',
        'callback' => function($request) {
            global $wpdb;
            $unit_id = sanitize_text_field($request->get_param('unit_id'));
            $machine_id = sanitize_text_field($request->get_param('machine_id'));
            $site_url = esc_url_raw($request->get_param('site_url'));
            if (!$unit_id) return rest_ensure_response(['status' => 'error', 'message' => 'Missing unit_id']);
            // Log to audit for admin review
            $wpdb->insert($wpdb->prefix.'tmon_audit', [
                'user_id' => 0,
                'action' => 'ingest_unknown_device',
                'details' => wp_json_encode(['unit_id' => $unit_id, 'machine_id' => $machine_id, 'site_url' => $site_url])
            ]);
            // Optionally, create a pending provision record if not exists
            $prov = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM {$wpdb->prefix}tmon_provisioned_devices WHERE unit_id=%s", $unit_id));
            if (!$prov) {
                $wpdb->insert($wpdb->prefix.'tmon_provisioned_devices', [
                    'unit_id' => $unit_id,
                    'machine_id' => $machine_id,
                    'status' => 'pending',
                    'notes' => 'auto-ingested from ' . $site_url,
                ]);
            }
            return rest_ensure_response(['status' => 'ok']);
        },
        'permission_callback' => '__return_true',
    ]);

    // Proxy claim endpoint: UC forwards claims here using shared hub key header
    register_rest_route('tmon-admin/v1', '/proxy/claim', [
        'methods' => 'POST',
        'permission_callback' => '__return_true',
        'callback' => function($request) {
            // Authenticate via shared hub key
            $expected = get_option('tmon_admin_uc_key', '');
            $provided = '';
            if (function_exists('getallheaders')) {
                $headers = getallheaders();
                $provided = $headers['X-TMON-HUB'] ?? ($headers['x-tmon-hub'] ?? '');
            } else {
                $provided = $_SERVER['HTTP_X_TMON_HUB'] ?? '';
            }
            if (!$expected || !$provided || !hash_equals((string)$expected, (string)$provided)) {
                return new WP_REST_Response(['status' => 'forbidden', 'message' => 'Invalid hub key'], 403);
            }
            // Accept claim parameters
            $unit_id = sanitize_text_field($request->get_param('unit_id'));
            $machine_id = sanitize_text_field($request->get_param('machine_id'));
            $user_hint = sanitize_text_field($request->get_param('user_hint'));
            $site_url = esc_url_raw($request->get_param('site_url'));
            if (!$unit_id || !$machine_id) {
                return new WP_REST_Response(['status' => 'error', 'message' => 'unit_id and machine_id required'], 400);
            }
            global $wpdb;
            $wpdb->insert($wpdb->prefix.'tmon_claim_requests', [
                'unit_id' => $unit_id,
                'machine_id' => $machine_id,
                'user_id' => 0,
                'status' => 'pending',
                'notes' => sprintf('via proxy from %s %s', $site_url ?: 'unknown', $user_hint ? ('user: '.$user_hint) : ''),
            ]);
            return rest_ensure_response(['status' => 'ok', 'id' => $wpdb->insert_id]);
        }
    ]);

    // UC remote install/update request: Admin → UC
    register_rest_route('tmon-admin/v1', '/uc/push', [
        'methods' => 'POST',
        'callback' => function($request){
            if (!current_user_can('manage_options')) return new WP_REST_Response(['status'=>'forbidden'], 403);
            $site_url = esc_url_raw($request->get_param('site_url'));
            $package_url = esc_url_raw($request->get_param('package_url'));
            $action = sanitize_text_field($request->get_param('action') ?: 'install'); // install|update
            $sha256 = sanitize_text_field($request->get_param('sha256') ?: '');
            $auth = $request->get_param('auth'); // optional Authorization header value for spoke
            if (!$site_url || !$package_url) return rest_ensure_response(['status'=>'error','message'=>'Missing site_url or package_url']);
            // Construct signed payload
            $secret = defined('TMON_HUB_SHARED_SECRET') ? TMON_HUB_SHARED_SECRET : wp_salt('auth');
            $payload = [
                'ts' => time(),
                'action' => $action,
                'package_url' => $package_url,
                'callback' => rest_url('tmon-admin/v1/uc/confirm'),
            ];
            if ($sha256) { $payload['sha256'] = $sha256; }
            $sig = hash_hmac('sha256', wp_json_encode($payload), $secret);
            $endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/uc/pull-install';
            $resp = wp_remote_post($endpoint, [
                'timeout' => 20,
                'headers' => array_filter(['Content-Type'=>'application/json','Authorization' => $auth ? $auth : '']),
                'body' => wp_json_encode(['payload'=>$payload,'sig'=>$sig]),
            ]);
            $ok = !is_wp_error($resp) && wp_remote_retrieve_response_code($resp) == 200;
            return rest_ensure_response(['status' => $ok ? 'ok' : 'error', 'response' => is_wp_error($resp) ? $resp->get_error_message() : wp_remote_retrieve_body($resp)]);
        },
        'permission_callback' => '__return_true',
    ]);

    // UC confirms back
    register_rest_route('tmon-admin/v1', '/uc/confirm', [
        'methods' => 'POST',
        'callback' => function($request){
            $site_url = esc_url_raw($request->get_param('site_url'));
            $status = sanitize_text_field($request->get_param('status'));
            $details = $request->get_param('details');
            // Audit
            global $wpdb;
            $wpdb->insert($wpdb->prefix.'tmon_audit', [
                'user_id' => get_current_user_id(),
                'action' => 'uc_confirm',
                'details' => wp_json_encode(['site_url'=>$site_url,'status'=>$status,'details'=>$details])
            ]);
            return rest_ensure_response(['status' => 'ok']);
        },
        'permission_callback' => '__return_true',
    ]);

    // Pairing: UC calls hub; hub saves mapping and responds with hub_key
    register_rest_route('tmon-admin/v1', '/uc/pair', [
        'methods' => 'POST',
        'permission_callback' => '__return_true',
        'callback' => function($request){
            $site_url = esc_url_raw($request->get_param('site_url'));
            $uc_key = sanitize_text_field($request->get_param('uc_key'));
            if (!$site_url || !$uc_key) return new WP_REST_Response(['status'=>'error','message'=>'site_url and uc_key required'], 400);
            // Persist mapping in options (simple store)
            $map = get_option('tmon_admin_uc_sites', []);
            if (!is_array($map)) $map = [];
            // Generate a per-UC read token for listing devices securely from hub
            $read_token = '';
            try { $read_token = bin2hex(random_bytes(24)); } catch (Exception $e) { $read_token = wp_generate_password(48, false, false); }
            $map[$site_url] = [
                'uc_key' => $uc_key,
                'paired_at' => current_time('mysql'),
                'read_token' => $read_token,
            ];
            update_option('tmon_admin_uc_sites', $map);
            // Return hub key for UC to store
            $hub_key = get_option('tmon_admin_uc_key');
            if (!$hub_key) {
                try { $hub_key = bin2hex(random_bytes(24)); } catch (Exception $e) { $hub_key = wp_generate_password(48, false, false); }
                update_option('tmon_admin_uc_key', $hub_key);
            }
            return rest_ensure_response(['status'=>'ok','hub_key'=>$hub_key, 'read_token'=>$read_token]);
        }
    ]);

    // Device first-boot check-in (WiFi): unit posts unit_id + machine_id
    register_rest_route('tmon-admin/v1', '/device/check-in', [
        'methods' => 'POST',
        'callback' => function($request){
            global $wpdb;
            $unit_id_in = sanitize_text_field($request->get_param('unit_id'));
            $machine_id = sanitize_text_field($request->get_param('machine_id'));
            if (!$machine_id) return rest_ensure_response(['status'=>'error','message'=>'Missing machine_id']);

            $table = $wpdb->prefix.'tmon_provisioned_devices';

            // Allocate next UNIT_ID (6 digits), ensuring uniqueness
            $alloc_unit_id = function() use ($wpdb, $table) {
                $seq = intval(get_option('tmon_admin_next_unit_seq', 1));
                for ($i=0; $i<1000000; $i++) {
                    $candidate = str_pad((string)$seq, 6, '0', STR_PAD_LEFT);
                    $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $table WHERE unit_id=%s", $candidate));
                    if (!$exists) { update_option('tmon_admin_next_unit_seq', ($seq>=999999?1:($seq+1))); return $candidate; }
                    $seq = ($seq>=999999?1:($seq+1));
                }
                return null;
            };

            $needs_alloc = (empty($unit_id_in) || strtolower($unit_id_in) === 'none');
            $unit_id = $needs_alloc ? $alloc_unit_id() : $unit_id_in;
            if (!$unit_id) return rest_ensure_response(['status'=>'error','message'=>'Unable to allocate UNIT_ID']);

            // Prefer existing row by machine_id; else by unit_id; else insert
            $row_mid = $wpdb->get_row($wpdb->prepare("SELECT id FROM $table WHERE machine_id=%s", $machine_id), ARRAY_A);
            $row_uid = $wpdb->get_row($wpdb->prepare("SELECT id FROM $table WHERE unit_id=%s", $unit_id), ARRAY_A);
            if ($row_mid) {
                $wpdb->update($table, ['unit_id'=>$unit_id, 'status'=>'registered', 'updated_at'=>current_time('mysql')], ['id'=>$row_mid['id']]);
            } elseif ($row_uid) {
                $wpdb->update($table, ['machine_id'=>$machine_id, 'status'=>'registered', 'updated_at'=>current_time('mysql')], ['id'=>$row_uid['id']]);
            } else {
                $wpdb->insert($table, [
                    'unit_id'=>$unit_id,'machine_id'=>$machine_id,'status'=>'registered',
                    'notes'=>'first-boot check-in','created_at'=>current_time('mysql'),'updated_at'=>current_time('mysql'),
                ]);
            }

            // Mirror to devices table for visibility
            $dtable = $wpdb->prefix.'tmon_devices';
            $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $dtable WHERE unit_id=%s", $unit_id));
            if (!$exists) {
                $wpdb->insert($dtable, ['unit_id'=>$unit_id,'unit_name'=>$unit_id,'last_seen'=>current_time('mysql'),'suspended'=>0,'settings'=>wp_json_encode([])]);
            } else {
                $wpdb->update($dtable, ['last_seen'=>current_time('mysql')], ['unit_id'=>$unit_id]);
            }

            do_action('tmon_admin_notify', 'provisioning', "Device checked in: $unit_id", ['unit_id'=>$unit_id,'machine_id'=>$machine_id]);

            // Return assigned UNIT_ID so device can persist it; profile stub reserved for future use
            return rest_ensure_response(['status'=>'ok','assigned_unit_id'=>$unit_id]);
        },
        'permission_callback' => '__return_true',
    ]);

    // Device suspend/enable toggle (admin action)
    register_rest_route('tmon-admin/v1', '/device/suspend', [
        'methods' => 'POST',
        'permission_callback' => function(){ return current_user_can('manage_options'); },
        'callback' => function($request){
            global $wpdb;
            $unit_id = sanitize_text_field($request->get_param('unit_id'));
            $suspend = strtolower(sanitize_text_field($request->get_param('suspend')));
            if (!$unit_id || !in_array($suspend, ['0','1','true','false','yes','no'], true)) {
                return rest_ensure_response(['status'=>'error','message'=>'unit_id and suspend required']);
            }
            $flag = in_array($suspend, ['1','true','yes'], true) ? 1 : 0;
            // Update devices table
            $wpdb->update($wpdb->prefix.'tmon_devices', ['suspended'=>$flag,'last_seen'=>current_time('mysql')], ['unit_id'=>$unit_id]);
            // Mirror provisioning status if provisioned
            $prov_tbl = $wpdb->prefix.'tmon_provisioned_devices';
            $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $prov_tbl WHERE unit_id=%s", $unit_id));
            if ($exists) {
                $wpdb->update($prov_tbl, ['status' => $flag ? 'suspended' : 'active', 'updated_at'=>current_time('mysql')], ['unit_id'=>$unit_id]);
            }
            do_action('tmon_admin_notify', 'suspend', ($flag? 'Device suspended':'Device enabled').": $unit_id", ['unit_id'=>$unit_id,'suspended'=>$flag]);
            return rest_ensure_response(['status'=>'ok','unit_id'=>$unit_id,'suspended'=>$flag]);
        }
    ]);

    // GPS override helper: admin can push GPS directly to a Unit Connector device settings
    register_rest_route('tmon-admin/v1', '/device/gps-override', [
        'methods' => 'POST',
        'permission_callback' => function() { return current_user_can('manage_options'); },
        'callback' => function($request){
            $params = $request->get_json_params();
            $unit_id = sanitize_text_field($params['unit_id'] ?? '');
            $site_url = esc_url_raw($params['site_url'] ?? '');
            $lat = isset($params['gps_lat']) ? floatval($params['gps_lat']) : null;
            $lng = isset($params['gps_lng']) ? floatval($params['gps_lng']) : null;
            $alt = isset($params['gps_alt_m']) ? floatval($params['gps_alt_m']) : null;
            $acc = isset($params['gps_accuracy_m']) ? floatval($params['gps_accuracy_m']) : null;
            if (!$unit_id || !$site_url || is_null($lat) || is_null($lng)) {
                return new WP_REST_Response(['status'=>'error','message'=>'unit_id, site_url, gps_lat, gps_lng required'], 400);
            }
            $settings = ['GPS_LAT'=>$lat, 'GPS_LNG'=>$lng];
            if (!is_null($alt)) $settings['GPS_ALT_M'] = $alt;
            if (!is_null($acc)) $settings['GPS_ACCURACY_M'] = $acc;
            $endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/device/settings';
            $headers = ['Content-Type'=>'application/json'];
            $admin_key = get_option('tmon_admin_uc_key');
            if ($admin_key) $headers['X-TMON-ADMIN'] = $admin_key;
            $resp = wp_remote_post($endpoint, [
                'timeout' => 20,
                'headers' => $headers,
                'body' => wp_json_encode(['unit_id'=>$unit_id, 'settings'=>$settings]),
            ]);
            if (is_wp_error($resp)) return new WP_REST_Response(['status'=>'error','message'=>$resp->get_error_message()], 500);
            $code = wp_remote_retrieve_response_code($resp);
            if ($code !== 200) return new WP_REST_Response(['status'=>'error','message'=>wp_remote_retrieve_body($resp)], $code);
            return rest_ensure_response(['status'=>'ok']);
        }
    ]);

    // Read-only: list provisioned devices for Unit Connector (authenticated via hub shared key)
    register_rest_route('tmon-admin/v1', '/provisioned-devices', [
        'methods' => 'GET',
        'permission_callback' => '__return_true',
        'callback' => function($request){
            // Authenticate via shared hub key in header X-TMON-HUB
            $expected = get_option('tmon_admin_uc_key', '');
            $provided = '';
            if (function_exists('getallheaders')) {
                $headers = getallheaders();
                $provided = $headers['X-TMON-HUB'] ?? ($headers['x-tmon-hub'] ?? '');
            } else {
                $provided = $_SERVER['HTTP_X_TMON_HUB'] ?? '';
            }
            if (!$expected || !$provided || !hash_equals((string)$expected, (string)$provided)) {
                return new WP_REST_Response(['status'=>'forbidden','message'=>'Invalid hub key'], 403);
            }
            global $wpdb;
            $table = $wpdb->prefix.'tmon_provisioned_devices';
            $exists = $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table));
            if (!$exists) {
                return rest_ensure_response(['status'=>'ok', 'devices'=>[]]);
            }
            $rows = $wpdb->get_results("SELECT id, unit_id, machine_id, role, company_id, plan, status, notes, created_at, updated_at FROM $table ORDER BY created_at DESC", ARRAY_A);
            return rest_ensure_response(['status'=>'ok', 'devices'=> is_array($rows)? $rows : []]);
        }
    ]);

    // Purge data (Admin side): dangerous operations to clean up data; protected by manage_options
    register_rest_route('tmon-admin/v1', '/purge/all', [
        'methods' => 'POST',
        'permission_callback' => function() { return current_user_can('manage_options'); },
        'callback' => function($request){
            global $wpdb;
            // Provisioning and claims
            $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_provisioned_devices");
            $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_claim_requests");
            // Audit log
            $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_audit");
            // Device registry copy (if present here)
            if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $wpdb->prefix.'tmon_devices'))) {
                $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_devices");
            }
            return rest_ensure_response(['status' => 'ok']);
        }
    ]);
});

// Authorization: decide if a device is allowed to post data (fee-for-service, provisioning, etc.)
add_filter('tmon_admin_authorize_device', function($allowed, $unit_id, $machine_id) {
    // Policy: require a matching provisioned record and not suspended/expired
    global $wpdb;
    $prov = $wpdb->get_row($wpdb->prepare("SELECT plan, status, machine_id FROM {$wpdb->prefix}tmon_provisioned_devices WHERE unit_id=%s", $unit_id));
    if (!$prov) return false;
    if (in_array($prov->status, ['suspended','expired'], true)) return false;
    if (!empty($prov->machine_id) && !empty($machine_id) && $prov->machine_id !== $machine_id) return false;
    // Optional: also ensure device registered table exists and not suspended there
    $row = $wpdb->get_row($wpdb->prepare("SELECT suspended FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $unit_id));
    if ($row && intval($row->suspended) === 1) return false;
    return true;
}, 10, 3);

// Receive field data forwarded by unit-connector and perform admin-side tasks
add_action('tmon_admin_receive_field_data', function($unit_id, $rec) {
    global $wpdb;
    // Upsert device name and last_seen
    $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $unit_id));
    if (!$exists) {
        $wpdb->insert($wpdb->prefix.'tmon_devices', [
            'unit_id' => $unit_id,
            'unit_name' => isset($rec['name']) ? sanitize_text_field($rec['name']) : $unit_id,
            'last_seen' => current_time('mysql'),
            'suspended' => 0,
        ]);
    } else {
        $update = ['last_seen' => current_time('mysql')];
        if (!empty($rec['name'])) {
            $update['unit_name'] = sanitize_text_field($rec['name']);
        }
        $wpdb->update($wpdb->prefix.'tmon_devices', $update, ['unit_id' => $unit_id]);
    }

    // TODO: tie into company/unit association tables when present
}, 10, 2);
