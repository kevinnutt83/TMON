<?php
if (!defined('ABSPATH')) exit;

// Ensure provisioned_devices table has expected columns even on older installs
function tmon_admin_maybe_migrate_provisioned_devices() {
    global $wpdb;
    $table = $wpdb->prefix . 'tmon_provisioned_devices';
    $exists = $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table));
    if (!$exists) return; // created by installer elsewhere

    $have = [];
    $cols = $wpdb->get_results("SHOW COLUMNS FROM $table", ARRAY_A);
    foreach (($cols?:[]) as $c) { $have[strtolower($c['Field'])] = true; }

    // Add missing columns one by one (id/unit_id/machine_id assumed present)
    if (empty($have['role'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN role VARCHAR(32) DEFAULT 'base'");
    }
    if (empty($have['company_id'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN company_id BIGINT UNSIGNED NULL");
    }
    if (empty($have['plan'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN plan VARCHAR(64) DEFAULT 'standard'");
    }
    if (empty($have['status'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN status VARCHAR(32) DEFAULT 'active'");
    }
    if (empty($have['notes'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN notes TEXT");
    }
    if (empty($have['created_at'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP");
    }
    if (empty($have['updated_at'])) {
        // Some MySQL variants require separate ADD then MODIFY for ON UPDATE
        $wpdb->query("ALTER TABLE $table ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP");
        $wpdb->query("ALTER TABLE $table MODIFY COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP");
    }

    // Ensure unique index on (unit_id, machine_id)
    $indexes = $wpdb->get_results("SHOW INDEX FROM $table", ARRAY_A);
    $hasUnitMachineIdx = false;
    foreach (($indexes?:[]) as $idx) {
        if (isset($idx['Key_name']) && $idx['Key_name'] === 'unit_machine') { $hasUnitMachineIdx = true; break; }
    }
    if (!$hasUnitMachineIdx) {
        // Create named unique index if both columns exist
        $colsCheck = $wpdb->get_col("SHOW COLUMNS FROM $table LIKE 'unit_id'");
        $colsCheck2 = $wpdb->get_col("SHOW COLUMNS FROM $table LIKE 'machine_id'");
        if (!empty($colsCheck) && !empty($colsCheck2)) {
            $wpdb->query("ALTER TABLE $table ADD UNIQUE KEY unit_machine (unit_id, machine_id)");
        }
    }
}

add_action('admin_init', function() {
    if (get_option('tmon_admin_schema_provisioned') !== '1') {
        tmon_admin_install_schema();
        update_option('tmon_admin_schema_provisioned', '1');
    }
    // Always run a lightweight migration to avoid 'Unknown column' errors on updated sites
    tmon_admin_maybe_migrate_provisioned_devices();
});

// Helper: Get all devices, provisioned and unprovisioned
function tmon_admin_get_all_devices() {
    global $wpdb;
    $dev_table = $wpdb->prefix . 'tmon_devices';
    $prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
    // Correct SQL: select from tmon_devices, left join provisioned_devices
    $sql = "SELECT d.unit_id, d.machine_id, d.unit_name, p.id as provision_id, p.role, p.company_id, p.plan, p.status, p.notes, p.created_at, p.updated_at, d.wordpress_api_url
            FROM $dev_table d
            LEFT JOIN $prov_table p ON d.unit_id = p.unit_id
            ORDER BY d.unit_id ASC";
    return $wpdb->get_results($sql, ARRAY_A);
}

// Provisioning page UI
function tmon_admin_provisioning_page() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    global $wpdb;

    $table = $wpdb->prefix . 'tmon_provisioned_devices';

    // Handle actions
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && function_exists('tmon_admin_verify_nonce') && tmon_admin_verify_nonce('tmon_admin_provision')) {
        $action = sanitize_text_field($_POST['action'] ?? '');

        // --- PROVISION DEVICE FORM (top of page) ---
        if ($action === 'create') {
            $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
            $machine_id = sanitize_text_field($_POST['machine_id'] ?? '');
            $role = sanitize_text_field($_POST['role'] ?? 'base');
            $company_id = intval($_POST['company_id'] ?? 0);
            $plan = sanitize_text_field($_POST['plan'] ?? 'standard');
            $status = sanitize_text_field($_POST['status'] ?? 'active');
            $notes = sanitize_textarea_field($_POST['notes'] ?? '');
            if ($unit_id && $machine_id) {
                // Upsert: update if exists, else insert
                $exists = $wpdb->get_var($wpdb->prepare("SELECT id FROM $table WHERE unit_id=%s AND machine_id=%s", $unit_id, $machine_id));
                $fields = [
                    'unit_id' => $unit_id,
                    'machine_id' => $machine_id,
                    'role' => $role,
                    'company_id' => $company_id,
                    'plan' => $plan,
                    'status' => $status,
                    'notes' => $notes
                ];
                if ($exists) {
                    $wpdb->update($table, $fields, ['id' => $exists]);
                    echo '<div class="updated"><p>Provisioned device updated.</p></div>';
                } else {
                    $wpdb->insert($table, $fields);
                    if (!empty($wpdb->last_error)) {
                        echo '<div class="notice notice-error"><p>Database error: '.esc_html($wpdb->last_error).'</p></div>';
                    } else {
                        echo '<div class="updated"><p>Provisioned device created.</p></div>';
                    }
                }
            }
        }

        // --- UPDATE DEVICE ROW (table row form) ---
        elseif ($action === 'update') {
            $id = intval($_POST['id'] ?? 0);
            $role = sanitize_text_field($_POST['role'] ?? 'base');
            $plan = sanitize_text_field($_POST['plan'] ?? 'standard');
            $status = sanitize_text_field($_POST['status'] ?? 'active');
            $company_id = intval($_POST['company_id'] ?? 0);
            $notes = sanitize_textarea_field($_POST['notes'] ?? '');
            if ($id) {
                $fields = [
                    'role' => $role,
                    'plan' => $plan,
                    'status' => $status,
                    'company_id' => $company_id,
                    'notes' => $notes
                ];
                $result = $wpdb->update($table, $fields, ['id' => $id]);
                if ($result !== false && $result > 0) {
                    echo '<div class="updated"><p>Provisioned device updated.</p></div>';
                } else {
                    echo '<div class="notice notice-error"><p>Failed to update device or no changes made.</p></div>';
                }
            }
        } elseif ($action === 'push_config') {
            // Push configuration to a Unit Connector site as a settings_update command
            $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
            $role = sanitize_text_field($_POST['role'] ?? 'base');
            $site_url = esc_url_raw($_POST['site_url'] ?? '');
            if ($unit_id && $site_url) {
                $endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/device/command';
                $payload = [
                    'unit_id' => $unit_id,
                    'command' => 'settings_update',
                    'params' => [
                        'NODE_TYPE' => $role,
                        'WIFI_DISABLE_AFTER_PROVISION' => ($role === 'remote'),
                    ],
                ];
                // Optional unit name passthrough when present in POST
                $maybe_name = isset($_POST['unit_name']) ? sanitize_text_field($_POST['unit_name']) : '';
                if ($maybe_name !== '') { $payload['params']['UNIT_Name'] = $maybe_name; }
                // This endpoint requires manage_options on UC; cross-site will likely fail unless authenticated; best-effort without auth
                $resp = wp_remote_post($endpoint, [
                    'timeout' => 20,
                    'headers' => ['Content-Type'=>'application/json'],
                    'body' => wp_json_encode($payload),
                ]);
                $ok = !is_wp_error($resp) && wp_remote_retrieve_response_code($resp) == 200;
                do_action('tmon_admin_audit', 'push_config', sprintf('unit_id=%s role=%s name=%s site=%s', $unit_id, $role, $maybe_name, $site_url));
                echo $ok ? '<div class="updated"><p>Configuration pushed to Unit Connector.</p></div>' : '<div class="error"><p>Push failed: '.esc_html(is_wp_error($resp)?$resp->get_error_message():wp_remote_retrieve_body($resp)).'</p></div>';
            } else {
                echo '<div class="error"><p>Unit ID and Site URL required to push configuration.</p></div>';
            }
        } elseif ($action === 'send_to_uc_registry') {
            // Register device in UC and set initial settings (role + optional GPS)
            $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
            $unit_name = sanitize_text_field($_POST['unit_name'] ?? '');
            $role = sanitize_text_field($_POST['role'] ?? 'base');
            $company_id = intval($_POST['company_id'] ?? 0);
            $company_name = sanitize_text_field($_POST['company_name'] ?? '');
            $site_url = esc_url_raw($_POST['site_url'] ?? '');
            $gps_lat = isset($_POST['gps_lat']) && $_POST['gps_lat'] !== '' ? floatval($_POST['gps_lat']) : null;
            $gps_lng = isset($_POST['gps_lng']) && $_POST['gps_lng'] !== '' ? floatval($_POST['gps_lng']) : null;
            if ($unit_id && $site_url) {
                $headers = ['Content-Type'=>'application/json'];
                $pairings = get_option('tmon_admin_uc_sites', []);
                $uc_key = is_array($pairings) && isset($pairings[$site_url]['uc_key']) ? $pairings[$site_url]['uc_key'] : '';
                if ($uc_key) $headers['X-TMON-ADMIN'] = $uc_key;
                // 1) Upsert company in UC hierarchy (optional)
                if ($company_id && $company_name) {
                    $comp_endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/company/upsert';
                    $comp_resp = wp_remote_post($comp_endpoint, [
                        'timeout'=>20,
                        'headers'=>$headers,
                        'body'=>wp_json_encode(['company_id'=>$company_id,'name'=>$company_name])
                    ]);
                    // ignore non-200 but log for admin notice
                }
                // 2) Register in UC registry
                $reg_endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/device/register';
                $reg_body = ['unit_id'=>$unit_id];
                if (!empty($unit_name)) { $reg_body['unit_name'] = $unit_name; }
                if ($company_id) $reg_body['company_id'] = $company_id;
                if ($company_name) $reg_body['company_name'] = $company_name;
                $reg_resp = wp_remote_post($reg_endpoint, [
                    'timeout'=>20,
                    'headers'=>$headers,
                    'body'=>wp_json_encode($reg_body)
                ]);
                $reg_ok = !is_wp_error($reg_resp) && wp_remote_retrieve_response_code($reg_resp) == 200;
                // 3) Push settings (role + GPS)
                $settings = ['NODE_TYPE'=>$role, 'WIFI_DISABLE_AFTER_PROVISION'=>($role==='remote')];
                if (!empty($unit_name)) { $settings['UNIT_Name'] = $unit_name; }
                if ($company_id) { $settings['COMPANY_ID'] = $company_id; }
                if (!is_null($gps_lat) && !is_null($gps_lng)) { $settings['GPS_LAT']=$gps_lat; $settings['GPS_LNG']=$gps_lng; }
                $set_endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/device/settings';
                $set_resp = wp_remote_post($set_endpoint, [
                    'timeout'=>20,
                    'headers'=>$headers,
                    'body'=>wp_json_encode(['unit_id'=>$unit_id,'settings'=>$settings])
                ]);
                $set_ok = !is_wp_error($set_resp) && wp_remote_retrieve_response_code($set_resp) == 200;
                do_action('tmon_admin_audit', 'send_to_uc_registry', sprintf('unit_id=%s name=%s role=%s site=%s gps=(%s,%s)', $unit_id, $unit_name, $role, $site_url, (string)$gps_lat, (string)$gps_lng));
                if ($reg_ok && $set_ok) {
                    echo '<div class="updated"><p>Sent to UC registry and settings applied.</p></div>';
                } else {
                    $err = '';
                    if (is_wp_error($reg_resp)) $err .= ' Register error: '.$reg_resp->get_error_message();
                    if (is_wp_error($set_resp)) $err .= ' Settings error: '.$set_resp->get_error_message();
                    echo '<div class="error"><p>One or more actions failed.'.$err.'</p></div>';
                }
            } else {
                echo '<div class="error"><p>Unit ID and Site URL required.</p></div>';
            }
        } elseif ($action === 'push_role_gps_direct') {
            $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
            $role = sanitize_text_field($_POST['role'] ?? 'base');
            $site_url = esc_url_raw($_POST['site_url'] ?? '');
            $gps_lat = isset($_POST['gps_lat']) && $_POST['gps_lat'] !== '' ? floatval($_POST['gps_lat']) : null;
            $gps_lng = isset($_POST['gps_lng']) && $_POST['gps_lng'] !== '' ? floatval($_POST['gps_lng']) : null;
            $gps_alt_m = isset($_POST['gps_alt_m']) && $_POST['gps_alt_m'] !== '' ? floatval($_POST['gps_alt_m']) : null;
            $gps_accuracy_m = isset($_POST['gps_accuracy_m']) && $_POST['gps_accuracy_m'] !== '' ? floatval($_POST['gps_accuracy_m']) : null;
            if ($unit_id && $site_url && !is_null($gps_lat) && !is_null($gps_lng)) {
                // push role via UC admin settings
                $headers = ['Content-Type'=>'application/json'];
                $pairings = get_option('tmon_admin_uc_sites', []);
                $uc_key = is_array($pairings) && isset($pairings[$site_url]['uc_key']) ? $pairings[$site_url]['uc_key'] : '';
                if ($uc_key) $headers['X-TMON-ADMIN'] = $uc_key;
                $set_endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/device/settings';
                $settings = ['NODE_TYPE'=>$role, 'GPS_LAT'=>$gps_lat, 'GPS_LNG'=>$gps_lng];
                // Allow optional Unit Name on direct push too
                $maybe_name = isset($_POST['unit_name']) ? sanitize_text_field($_POST['unit_name']) : '';
                if ($maybe_name !== '') { $settings['UNIT_Name'] = $maybe_name; }
                if (!is_null($gps_alt_m)) $settings['GPS_ALT_M'] = $gps_alt_m;
                if (!is_null($gps_accuracy_m)) $settings['GPS_ACCURACY_M'] = $gps_accuracy_m;
                $set_resp = wp_remote_post($set_endpoint, [
                    'timeout'=>20,
                    'headers'=>$headers,
                    'body'=>wp_json_encode(['unit_id'=>$unit_id,'settings'=>$settings])
                ]);
                $ok = !is_wp_error($set_resp) && wp_remote_retrieve_response_code($set_resp) == 200;
                do_action('tmon_admin_audit', 'push_role_gps_direct', sprintf('unit_id=%s name=%s role=%s site=%s gps=(%s,%s)', $unit_id, $maybe_name, $role, $site_url, (string)$gps_lat, (string)$gps_lng));
                echo $ok ? '<div class="updated"><p>Role + GPS pushed directly.</p></div>' : '<div class="error"><p>Push failed: '.esc_html(is_wp_error($set_resp)?$set_resp->get_error_message():wp_remote_retrieve_body($set_resp)).'</p></div>';
            } else {
                echo '<div class="error"><p>Unit ID, Site URL, GPS Lat/Lng required.</p></div>';
            }
        } elseif ($action === 'refresh_known_ids') {
            // Pull devices from paired UC sites and cache in option
            $sites = get_option('tmon_admin_uc_sites', []);
            $agg = [];
            if (is_array($sites)) {
                foreach ($sites as $site_url => $info) {
                    $endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/devices';
                    $headers = ['Content-Type' => 'application/json'];
                    // Preferred: per-site read token (X-TMON-READ) set during pairing response
                    if (!empty($info['read_token'])) { $headers['X-TMON-READ'] = $info['read_token']; }
                    // Fallback: hub shared key (X-TMON-HUB)
                    if (empty($headers['X-TMON-READ'])) {
                        $hub_key = get_option('tmon_admin_uc_key');
                        if ($hub_key) { $headers['X-TMON-HUB'] = $hub_key; }
                    }
                    // Last fallback: UC site key if available (X-TMON-ADMIN)
                    if (!empty($info['uc_key']) && empty($headers['X-TMON-ADMIN']) && empty($headers['X-TMON-READ'])) { $headers['X-TMON-ADMIN'] = $info['uc_key']; }
                    $resp = wp_remote_get($endpoint, ['timeout' => 15, 'headers' => $headers]);
                    if (!is_wp_error($resp) && wp_remote_retrieve_response_code($resp) === 200) {
                        $body = json_decode(wp_remote_retrieve_body($resp), true);
                        if (is_array($body) && !empty($body['devices']) && is_array($body['devices'])) {
                            foreach ($body['devices'] as $d) {
                                $uid = $d['unit_id'] ?? '';
                                if ($uid) { $agg[$uid] = $d; }
                            }
                        }
                    }
                }
            }
            update_option('tmon_admin_known_ids_cache', $agg, false);
            echo '<div class="updated"><p>Refreshed known IDs from paired UCs (best effort).</p></div>';
        } elseif ($action === 'hier_sync') {
            $site_url = esc_url_raw($_POST['site_url'] ?? '');
            $entity = sanitize_text_field($_POST['entity'] ?? 'company');
            $id = intval($_POST['id'] ?? 0);
            $parent_id = intval($_POST['parent_id'] ?? 0);
            $name = sanitize_text_field($_POST['name'] ?? '');
            if ($site_url && $id && $name) {
                $pairings = get_option('tmon_admin_uc_sites', []);
                $uc_key = is_array($pairings) && isset($pairings[$site_url]['uc_key']) ? $pairings[$site_url]['uc_key'] : '';
                $headers = ['Content-Type'=>'application/json'];
                if ($uc_key) $headers['X-TMON-ADMIN'] = $uc_key;
                $map = [
                    'company' => ['path' => '/wp-json/tmon/v1/admin/company/upsert', 'payload' => ['company_id' => $id, 'name' => $name]],
                    'site'    => ['path' => '/wp-json/tmon/v1/admin/site/upsert',    'payload' => ['id'=>$id,'company_id'=>$parent_id,'name'=>$name]],
                    'zone'    => ['path' => '/wp-json/tmon/v1/admin/zone/upsert',    'payload' => ['id'=>$id,'site_id'=>$parent_id,'name'=>$name]],
                    'cluster' => ['path' => '/wp-json/tmon/v1/admin/cluster/upsert', 'payload' => ['id'=>$id,'zone_id'=>$parent_id,'name'=>$name]],
                    'unit'    => ['path' => '/wp-json/tmon/v1/admin/unit/upsert',    'payload' => ['id'=>$id,'cluster_id'=>$parent_id,'name'=>$name]],
                ];
                if (!isset($map[$entity])) {
                    echo '<div class="error"><p>Invalid entity.</p></div>';
                } else {
                    $ep = rtrim($site_url, '/') . $map[$entity]['path'];
                    $resp = wp_remote_post($ep, ['timeout'=>20,'headers'=>$headers,'body'=>wp_json_encode($map[$entity]['payload'])]);
                    $ok = !is_wp_error($resp) && wp_remote_retrieve_response_code($resp) == 200;
                    echo $ok ? '<div class="updated"><p>Hierarchy pushed.</p></div>' : '<div class="error"><p>Push failed: '.esc_html(is_wp_error($resp)?$resp->get_error_message():wp_remote_retrieve_body($resp)).'</p></div>';
                }
            } else {
                echo '<div class="error"><p>Site URL, ID, and Name are required.</p></div>';
            }
        }
    }

    // Handle claim approvals/denials
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && function_exists('tmon_admin_verify_nonce') && tmon_admin_verify_nonce('tmon_admin_claim')) {
        $action = sanitize_text_field($_POST['action'] ?? '');
        $claim_id = intval($_POST['claim_id'] ?? 0);
        if ($claim_id && in_array($action, ['approve_claim','deny_claim'], true)) {
            $claims_table = $wpdb->prefix . 'tmon_claim_requests';
            $claim_row = $wpdb->get_row($wpdb->prepare("SELECT * FROM $claims_table WHERE id=%d", $claim_id), ARRAY_A);
            if ($claim_row) {
                if ($action === 'approve_claim') {
                    // Ensure provisioned entry exists
                    $prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
                    $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $prov_table WHERE unit_id=%s AND machine_id=%s", $claim_row['unit_id'], $claim_row['machine_id']));
                    if (!$exists) {
                        $wpdb->insert($prov_table, [
                            'unit_id' => $claim_row['unit_id'],
                            'machine_id' => $claim_row['machine_id'],
                            'status' => 'active',
                            'notes' => 'Claim approved for user #'.$claim_row['user_id']
                        ]);
                    } else {
                        $wpdb->update($prov_table, ['status' => 'active'], ['unit_id' => $claim_row['unit_id'], 'machine_id' => $claim_row['machine_id']]);
                    }
                    $wpdb->update($claims_table, ['status' => 'approved'], ['id' => $claim_id]);
                    echo '<div class="notice notice-success is-dismissible"><p>Claim approved.</p></div>';
                } else {
                    $wpdb->update($claims_table, ['status' => 'denied'], ['id' => $claim_id]);
                    echo '<div class="notice notice-warning is-dismissible"><p>Claim denied.</p></div>';
                }
            }
        }
    }

    // Render UI
    echo '<div class="wrap"><h1>Provisioning</h1>';
    // Standalone refresh known IDs form (outside of create form to avoid nested forms)
    echo '<h2>Known IDs</h2>';
    echo '<form method="post" style="margin-bottom:12px">';
    wp_nonce_field('tmon_admin_provision');
    echo '<input type="hidden" name="action" value="refresh_known_ids" />';
    submit_button('Refresh from paired UC sites', 'secondary', '', false);
    echo '</form>';

    echo '<h2>Add Provisioned Device</h2>';
    echo '<form method="post">';
    wp_nonce_field('tmon_admin_provision');
    echo '<input type="hidden" name="action" value="create" />';
    echo '<table class="form-table">';
    // Compact search filters to help narrow large fleets
    echo '<tr><th scope="row">Filters</th><td>';
    echo ' Role <select id="tmon_filter_role"><option value="">Any</option><option value="base">base</option><option value="remote">remote</option><option value="wifi">wifi</option></select>';
    echo ' Company ID <input id="tmon_filter_company" type="number" class="small-text" placeholder="any" />';
    echo ' <span class="description">Type at least 2 characters in Unit/Machine fields to search. Results may be truncated; refine your query.</span>';
    echo '</td></tr>';
    // Build datalists from local mirror and cached remote pull if available
    $known_units = [];
    $known_machines = [];
    if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $wpdb->prefix.'tmon_devices'))) {
        // Ensure expected columns exist before selecting
        $cols = $wpdb->get_col("SHOW COLUMNS FROM {$wpdb->prefix}tmon_devices LIKE 'unit_id'");
        $cols2 = $wpdb->get_col("SHOW COLUMNS FROM {$wpdb->prefix}tmon_devices LIKE 'machine_id'");
        $cols3 = $wpdb->get_col("SHOW COLUMNS FROM {$wpdb->prefix}tmon_devices LIKE 'unit_name'");
        if (!empty($cols) && !empty($cols2)) {
            $known = $wpdb->get_results("SELECT unit_id, machine_id" . (!empty($cols3)?", unit_name":"") . " FROM {$wpdb->prefix}tmon_devices ORDER BY unit_id ASC", ARRAY_A);
            foreach ($known as $kv) {
                if (!empty($kv['unit_id'])) $known_units[$kv['unit_id']] = isset($kv['unit_name']) && $kv['unit_name'] ? $kv['unit_name'] : $kv['unit_id'];
                if (!empty($kv['machine_id'])) $known_machines[$kv['machine_id']] = $kv['unit_id'];
            }
        }
    }
    $remote_known = get_option('tmon_admin_known_ids_cache', []);
    if (is_array($remote_known)) {
        foreach ($remote_known as $uid => $d) {
            if (!isset($known_units[$uid])) $known_units[$uid] = isset($d['unit_name']) ? $d['unit_name'] : $uid;
            if (!empty($d['machine_id']) && !isset($known_machines[$d['machine_id']])) $known_machines[$d['machine_id']] = $uid;
        }
    }
    echo '<tr><th scope="row">Unit ID</th><td>';
    echo '<input id="tmon_unit_id" name="unit_id" list="tmon_known_unit_ids" type="text" class="regular-text" required placeholder="e.g., 123456">';
    echo '<datalist id="tmon_known_unit_ids">';
    foreach ($known_units as $uid => $uname) {
        echo '<option value="'.esc_attr($uid).'">'.esc_html($uname).'</option>';
    }
    echo '</datalist>';
    echo '</td></tr>';
    echo '<tr><th scope="row">Machine ID</th><td>';
    echo '<input id="tmon_machine_id" name="machine_id" list="tmon_known_machine_ids" type="text" class="regular-text" required placeholder="e.g., 30:AE:A4:...">';
    echo '<datalist id="tmon_known_machine_ids">';
    foreach ($known_machines as $mid => $uidmap) {
        echo '<option value="'.esc_attr($mid).'">'.esc_html($uidmap).'</option>';
    }
    echo '</datalist>';
    echo '</td></tr>';
    // Inline JS to power dynamic typeahead via admin-ajax
    $ajax_url = admin_url('admin-ajax.php');
    $nonce = wp_create_nonce('tmon_admin_known_units');
    $ajax_url_js = wp_json_encode(esc_url($ajax_url));
    $nonce_js = wp_json_encode($nonce);
    echo <<<EOT
<script>(function(){
    const unitInput = document.getElementById("tmon_unit_id");
    const unitList = document.getElementById("tmon_known_unit_ids");
    const machInput = document.getElementById("tmon_machine_id");
    const machList = document.getElementById("tmon_known_machine_ids");
    const filterRole = document.getElementById("tmon_filter_role");
    const filterCompany = document.getElementById("tmon_filter_company");
    const nonce = {$nonce_js};
    const ajaxUrl = {$ajax_url_js};
    let timer;
    function debounce(fn){ clearTimeout(timer); timer = setTimeout(fn, 250); }
    function fetchKnown(q, page=1, perPage=50){
        if(!q || q.length < 2) return Promise.resolve([]);
        const params = new URLSearchParams();
        params.set("action","tmon_admin_known_units");
        params.set("q", q);
        params.set("nonce", nonce);
        params.set("page", String(page));
        params.set("per_page", String(perPage));
        if(filterRole && filterRole.value) params.set("role", filterRole.value);
        if(filterCompany && filterCompany.value) params.set("company_id", filterCompany.value);
        const url = ajaxUrl + "?" + params.toString();
        return fetch(url, { credentials: "same-origin" }).then(r=>r.json()).then(j=> j && j.success ? (j.data.items||[]) : []).catch(()=>[]);
    }
    function updateUnitList(items){
        if(!unitList) return; unitList.innerHTML="";
        items.forEach(it=>{ const opt=document.createElement("option"); opt.value=it.unit_id; opt.textContent=it.name||it.unit_id; unitList.appendChild(opt); });
        if(items.length >= 50 && unitInput){ unitInput.title = "More results available; refine your search."; } else if (unitInput) { unitInput.title = ""; }
    }
    function updateMachList(items){
        if(!machList) return; machList.innerHTML="";
        const seen={};
        items.forEach(it=>{ if(it.machine_id && !seen[it.machine_id]){ seen[it.machine_id]=1; const opt=document.createElement("option"); opt.value=it.machine_id; opt.textContent=it.unit_id; machList.appendChild(opt); } });
        if(items.length >= 50 && machInput){ machInput.title = "More results available; refine your search."; } else if (machInput) { machInput.title = ""; }
    }
    function refreshUnit(){ fetchKnown(unitInput.value).then(list=>{ updateUnitList(list); }); }
    function refreshMach(){ fetchKnown(machInput.value).then(list=>{ updateMachList(list); }); }
    if(unitInput){ unitInput.addEventListener("input", ()=> debounce(refreshUnit)); }
    if(machInput){ machInput.addEventListener("input", ()=> debounce(refreshMach)); }
    if(filterRole){ filterRole.addEventListener("change", ()=>{ if(unitInput && unitInput.value.length>=2) refreshUnit(); if(machInput && machInput.value.length>=2) refreshMach(); }); }
    if(filterCompany){ filterCompany.addEventListener("input", ()=> debounce(()=>{ if(unitInput && unitInput.value.length>=2) refreshUnit(); if(machInput && machInput.value.length>=2) refreshMach(); })); }
})();</script>
EOT;
    echo '<tr><th scope="row">Role</th><td><select name="role"><option value="base">base</option><option value="remote">remote</option><option value="wifi">wifi</option></select></td></tr>';
    echo '<tr><th scope="row">Company ID</th><td><input name="company_id" type="number" class="small-text"></td></tr>';
    echo '<tr><th scope="row">Plan</th><td><select name="plan"><option>standard</option><option>pro</option><option>enterprise</option></select></td></tr>';
    echo '<tr><th scope="row">Status</th><td><select name="status"><option>active</option><option>suspended</option><option>expired</option></select></td></tr>';
    echo '<tr><th scope="row">Notes</th><td><textarea name="notes" class="large-text"></textarea></td></tr>';
    echo '</table>';
    submit_button('Provision Device');
    echo '</form>';

    echo '<h2>Provisioned Devices</h2>';
    // Build a map of current known names from Admin's device registry (if present)
    $names_map = [];
    $adm_dev_table = $wpdb->prefix . 'tmon_devices';
    $adm_dev_exists = $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $adm_dev_table));
    if ($adm_dev_exists) {
        $name_rows = $wpdb->get_results("SELECT unit_id, unit_name FROM {$adm_dev_table}", ARRAY_A);
        if (is_array($name_rows)) {
            foreach ($name_rows as $nr) {
                if (!empty($nr['unit_id'])) { $names_map[$nr['unit_id']] = $nr['unit_name'] ?? ''; }
            }
        }
    }

    // Load provisioned and unprovisioned devices and merge for display
    $prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
    $dev_table  = $wpdb->prefix . 'tmon_devices';
    $rows = [];

    // 1) Provisioned devices (joined with tmon_devices for friendly name)
    if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $prov_table))) {
        // Only join columns that exist in tmon_devices
        $dev_cols = $wpdb->get_col("SHOW COLUMNS FROM {$dev_table}");
        $has_unit_name = in_array('unit_name', $dev_cols);
        $select_cols = "p.*";
        if ($has_unit_name) {
            $select_cols .= ", d.unit_name AS unit_name";
        }
        $prov_sql = "SELECT $select_cols FROM {$prov_table} p LEFT JOIN {$dev_table} d ON p.unit_id = d.unit_id ORDER BY p.created_at DESC";
        $prov_rows = $wpdb->get_results($prov_sql, ARRAY_A);
        if (is_array($prov_rows)) {
            foreach ($prov_rows as $pr) {
                $pr['unit_name'] = $pr['unit_name'] ?? ($names_map[$pr['unit_id']] ?? '');
                $pr['wordpress_api_url'] = ''; // Not available, avoid error
            }
            $rows = array_merge($rows, $prov_rows);
        }
    }

    // 2) Unprovisioned devices (present in tmon_devices but not in tmon_provisioned_devices)
    if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $dev_table))) {
        $dev_cols = $wpdb->get_col("SHOW COLUMNS FROM {$dev_table}");
        $has_unit_name = in_array('unit_name', $dev_cols);
        $has_last_seen = in_array('last_seen', $dev_cols);
        // Only select columns that exist
        $select_cols = "unit_id, machine_id";
        if ($has_unit_name) $select_cols .= ", unit_name";
        if ($has_last_seen) $select_cols .= ", last_seen";
        // Build list of provisioned unit_ids to exclude
        $prov_ids = [];
        if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $prov_table))) {
            $prov_ids = $wpdb->get_col("SELECT unit_id FROM {$prov_table}");
        }
        if (!empty($prov_ids)) {
            $placeholders = implode(',', array_fill(0, count($prov_ids), '%s'));
            $sql = $wpdb->prepare("SELECT $select_cols FROM {$dev_table} WHERE unit_id NOT IN ($placeholders) ORDER BY unit_id ASC", ...$prov_ids);
        } else {
            $sql = "SELECT $select_cols FROM {$dev_table} ORDER BY unit_id ASC";
        }
        $dev_rows = $wpdb->get_results($sql, ARRAY_A);
        if (is_array($dev_rows)) {
            foreach ($dev_rows as $dr) {
                $rows[] = [
                    'id' => 0,
                    'unit_id' => $dr['unit_id'],
                    'machine_id' => $dr['machine_id'] ?? '',
                    'role' => '',
                    'company_id' => '',
                    'plan' => '',
                    'status' => 'unprovisioned',
                    'notes' => '',
                    'created_at' => $has_last_seen ? ($dr['last_seen'] ?? '') : '',
                    'updated_at' => $has_last_seen ? ($dr['last_seen'] ?? '') : '',
                    'unit_name' => $has_unit_name ? ($dr['unit_name'] ?? ($names_map[$dr['unit_id']] ?? '')) : ($names_map[$dr['unit_id']] ?? ''),
                    'wordpress_api_url' => '', // Not available, avoid error
                ];
            }
        }
    }

    // If still empty, show helpful admin notice (rendered later with table empty state)
    // $rows now contains both provisioned and unprovisioned devices for display

    // $table is now always defined before this query
    echo '<table class="wp-list-table widefat"><thead><tr><th>ID</th><th>Unit ID</th><th>Name</th><th>Machine ID</th><th>Role</th><th>Company ID</th><th>Plan</th><th>Status</th><th>Notes</th><th>Created</th><th>Updated</th><th>Actions</th></tr></thead><tbody>';
    foreach ($rows as $r) {
        echo '<tr>';
        echo '<td>'.intval($r['id']).'</td>';
        echo '<td>'.esc_html($r['unit_id']).'</td>';
        $cur_name = isset($names_map[$r['unit_id']]) ? $names_map[$r['unit_id']] : '';
        echo '<td>'.esc_html($cur_name).'</td>';
        echo '<td>'.esc_html($r['machine_id']).'</td>';
        echo '<td>'.esc_html($r['role']).'</td>';
        echo '<td>'.esc_html($r['company_id']).'</td>';
        echo '<td>'.esc_html($r['plan']).'</td>';
        echo '<td>'.esc_html($r['status']).'</td>';
        echo '<td>'.esc_html($r['notes']).'</td>';
        echo '<td>'.esc_html($r['created_at']).'</td>';
        echo '<td>'.esc_html($r['updated_at']).'</td>';
        echo '<td>';
        echo '<form method="post" style="display:inline-block;margin-right:6px;">';
        wp_nonce_field('tmon_admin_provision');
        echo '<input type="hidden" name="action" value="delete" />';
        echo '<input type="hidden" name="id" value="'.intval($r['id']).'" />';
        submit_button('Delete', 'delete', '', false);
        echo '</form>';
        echo '<form method="post" style="display:inline-block;">';
        wp_nonce_field('tmon_admin_provision');
        echo '<input type="hidden" name="action" value="update" />';
        echo '<input type="hidden" name="id" value="'.intval($r['id']).'" />';
        // Correct dropdown rendering to avoid parse error
        echo ' Role <select name="role">';
        echo '<option value="base"' . ( ($r['role'] === 'base') ? ' selected' : '' ) . '>base</option>';
        echo '<option value="remote"' . ( ($r['role'] === 'remote') ? ' selected' : '' ) . '>remote</option>';
        echo '<option value="wifi"' . ( ($r['role'] === 'wifi') ? ' selected' : '' ) . '>wifi</option>';
        echo '</select>';
        echo ' Plan <select name="plan">';
        echo '<option value="standard"' . ( ($r['plan'] === 'standard') ? ' selected' : '' ) . '>standard</option>';
        echo '<option value="pro"' . ( ($r['plan'] === 'pro') ? ' selected' : '' ) . '>pro</option>';
        echo '<option value="enterprise"' . ( ($r['plan'] === 'enterprise') ? ' selected' : '' ) . '>enterprise</option>';
        echo '</select>';
        echo ' Status <select name="status">';
        echo '<option value="active"' . ( ($r['status'] === 'active') ? ' selected' : '' ) . '>active</option>';
        echo '<option value="suspended"' . ( ($r['status'] === 'suspended') ? ' selected' : '' ) . '>suspended</option>';
        echo '<option value="expired"' . ( ($r['status'] === 'expired') ? ' selected' : '' ) . '>expired</option>';
        echo '</select>';
        echo ' Company <input name="company_id" type="number" class="small-text" value="'.intval($r['company_id']).'" />';
        echo ' Notes <input name="notes" type="text" class="regular-text" value="'.esc_attr($r['notes']).'" />';
        submit_button('Update', 'primary', '', false);
        echo '</form>';
        // Push config to UC
        echo '<form method="post" style="display:block;margin-top:6px;">';
        wp_nonce_field('tmon_admin_provision');
        echo '<input type="hidden" name="action" value="push_config" />';
        echo '<input type="hidden" name="unit_id" value="'.esc_attr($r['unit_id']).'" />';
        echo '<input type="hidden" name="role" value="'.esc_attr($r['role']).'" />';
        echo ' Unit Name <input name="unit_name" type="text" class="regular-text" placeholder="Optional display name" value="'.esc_attr($cur_name).'" />';
        // Paired UC sites datalist
        $paired = get_option('tmon_admin_uc_sites', []);
        echo ' UC Site URL <input name="site_url" list="tmon_paired_sites" type="url" class="regular-text" placeholder="https://uc.example.com" />';
        echo '<datalist id="tmon_paired_sites">';
        if (is_array($paired)) { foreach ($paired as $purl => $info) { echo '<option value="'.esc_attr($purl).'">'.esc_html($info['paired_at'] ?? '').'</option>'; } }
        echo '</datalist>';
        submit_button('Push Config to UC', 'secondary', '', false);
        echo '</form>';

        // Send to UC registry + optional GPS + company association
        echo '<form method="post" style="display:block;margin-top:6px;">';
        wp_nonce_field('tmon_admin_provision');
        echo '<input type="hidden" name="action" value="send_to_uc_registry" />';
        echo '<input type="hidden" name="unit_id" value="'.esc_attr($r['unit_id']).'" />';
        echo ' Unit Name <input name="unit_name" type="text" class="regular-text" placeholder="Optional display name" value="'.esc_attr($cur_name).'" />';
        echo ' Company Name <input name="company_name" type="text" class="regular-text" placeholder="Acme Inc." />';
        echo ' Company ID <input name="company_id" type="number" class="small-text" value="'.intval($r['company_id']).'" />';
        echo ' Role <select name="role"><option value="base" '.selected($r['role],'base',false).'>base</option><option value="remote" '.selected($r['role],'remote',false).'>remote</option></select>';
        echo ' GPS Lat <input name="gps_lat" type="text" class="small-text" placeholder="38.8977" />';
        echo ' GPS Lng <input name="gps_lng" type="text" class="small-text" placeholder="-77.0365" />';
        echo ' UC Site URL <input name="site_url" list="tmon_paired_sites" type="url" class="regular-text" placeholder="https://uc.example.com" />';
        submit_button('Send to UC registry', 'secondary', '', false);
        echo '</form>';

        // Direct Role + GPS override push (no device poll required)
        echo '<form method="post" style="display:block;margin-top:6px;">';
        wp_nonce_field('tmon_admin_provision');
        echo '<input type="hidden" name="action" value="push_role_gps_direct" />';
        echo '<input type="hidden" name="unit_id" value="'.esc_attr($r['unit_id']).'" />';
        echo ' Role <select name="role"><option value="base" '.selected($r['role],'base',false).'>base</option><option value="remote" '.selected($r['role],'remote',false).'>remote</option></select>';
        echo ' Unit Name <input name="unit_name" type="text" class="regular-text" placeholder="Optional display name" value="'.esc_attr($cur_name).'" />';
        echo ' GPS Lat <input name="gps_lat" type="text" class="small-text" placeholder="38.8977" />';
        echo ' GPS Lng <input name="gps_lng" type="text" class="small-text" placeholder="-77.0365" />';
        echo ' GPS Alt (m) <input name="gps_alt_m" type="text" class="small-text" placeholder="" />';
        echo ' GPS Acc (m) <input name="gps_accuracy_m" type="text" class="small-text" placeholder="" />';
        echo ' UC Site URL <input name="site_url" list="tmon_paired_sites" type="url" class="regular-text" placeholder="https://uc.example.com" />';
        submit_button('Push Role + GPS (direct)', 'secondary', '', false);
        echo '</form>';
        echo '</td>';
        echo '</tr>';
    }
    echo '</tbody></table>';

    // Data Maintenance (Admin-side purge UI)
    echo '<h2>Data Maintenance</h2>';
    echo '<form method="post" onsubmit="return confirm(\'This will delete ALL provisioning and audit data on this Admin site. Continue?\');" style="margin-bottom:10px">';
    wp_nonce_field('tmon_admin_purge_all');
    echo '<input type="hidden" name="tmon_admin_action" value="purge_all" />';
    submit_button('Purge ALL Admin data', 'delete', 'submit', false);
    echo '</form>';
    echo '<form method="post" onsubmit="return confirm(\'This will delete data for the specified Unit ID. Continue?\');">';
    wp_nonce_field('tmon_admin_purge_unit');
    echo '<input type="hidden" name="tmon_admin_action" value="purge_unit" />';
    echo 'Unit ID <input type="text" name="unit_id" class="regular-text" placeholder="123456" /> ';
    submit_button('Purge by Unit ID', 'delete', 'submit', false);
    echo '</form>';

    // Hierarchy Sync to UC
    echo '<h2>Hierarchy Sync to UC</h2>';
    echo '<p>Push simple hierarchy records (company/site/zone/cluster/unit) to a paired Unit Connector.</p>';
    echo '<form method="post" style="margin-bottom:8px">';
    wp_nonce_field('tmon_admin_provision');
    echo '<input type="hidden" name="action" value="hier_sync" />';
    echo 'UC Site URL <input name="site_url" list="tmon_paired_sites" type="url" class="regular-text" placeholder="https://uc.example.com" /> ';
    echo 'Entity <select name="entity"><option>company</option><option>site</option><option>zone</option><option>cluster</option><option>unit</option></select> ';
    echo 'ID <input name="id" type="number" class="small-text" /> ';
    echo 'Parent ID <input name="parent_id" type="number" class="small-text" placeholder="company_id/site_id/zone_id/cluster_id as applicable" /> ';
    echo 'Name <input name="name" type="text" class="regular-text" /> ';
    submit_button('Push', 'secondary', '', false);
    echo '</form>';

    // Claims section
    echo '<h2>Device Claims</h2>';
    // Persisted preferences per admin user
    $current_user_id = get_current_user_id();
    $saved_status = $current_user_id ? get_user_meta($current_user_id, 'tmon_claim_status', true) : '';
    $saved_pp = $current_user_id ? intval(get_user_meta($current_user_id, 'tmon_claim_pp', true)) : 0;
    // Optional reset of saved prefs
    if (isset($_GET['claim_reset']) && intval($_GET['claim_reset']) === 1 && $current_user_id) {
        delete_user_meta($current_user_id, 'tmon_claim_status');
        delete_user_meta($current_user_id, 'tmon_claim_pp');
        $saved_status = '';
        $saved_pp = 0;
    }
    // Filter UI
    $status_filter = isset($_GET['claim_status']) ? sanitize_text_field($_GET['claim_status']) : ($saved_status ?: 'pending');
    $valid_status = ['all','pending','approved','denied'];
    if (!in_array($status_filter, $valid_status, true)) { $status_filter = 'pending'; }
    // Per-page value: GET > saved > default
    $claim_pp   = isset($_GET['claim_pp']) ? max(1, min(100, intval($_GET['claim_pp']))) : ($saved_pp ?: 20);
    // Save prefs when explicitly provided through GET
    if ($current_user_id) {
        if (isset($_GET['claim_status'])) { update_user_meta($current_user_id, 'tmon_claim_status', $status_filter); }
        if (isset($_GET['claim_pp'])) { update_user_meta($current_user_id, 'tmon_claim_pp', $claim_pp); }
    }
    echo '<form method="get" style="margin:8px 0">';
    // preserve page slug and reset pagination on filter submit
    echo '<input type="hidden" name="page" value="tmon-admin-provisioning" />';
    echo '<input type="hidden" name="claim_page" value="1" />';
    // Status selector
    echo 'Show: <select name="claim_status">';
    foreach ($valid_status as $st) {
        $sel = $status_filter === $st ? ' selected' : '';
        echo '<option value="'.esc_attr($st).'"'.$sel.'>'.esc_html(ucfirst($st)).'</option>';
    }
    echo '</select> ';
    // Per-page selector
    $pp_options = [10,20,50,100];
    echo 'Per page: <select name="claim_pp">';
    foreach ($pp_options as $opt) {
        $sel = ($claim_pp === $opt) ? ' selected' : '';
        echo '<option value="'.intval($opt).'"'.$sel.'>'.intval($opt).'</option>';
    }
    echo '</select> ';
    // Search box
    $claim_search = isset($_GET['claim_search']) ? sanitize_text_field($_GET['claim_search']) : '';
    echo ' Search: <input type="search" name="claim_search" value="' . esc_attr($claim_search) . '" placeholder="unit_id or machine_id" /> ';
    submit_button('Filter', 'secondary', '', false);
    // Reset link
    $reset_url = add_query_arg(['page'=>'tmon-admin-provisioning','claim_reset'=>1], admin_url('admin.php'));
    echo '<a href="'.esc_url($reset_url).'" class="button button-link">Reset</a>';
    echo '</form>';
    // Pagination params
    $claim_page = isset($_GET['claim_page']) ? max(1, intval($_GET['claim_page'])) : 1;
    $offset     = ($claim_page - 1) * $claim_pp;

    // Total count for pagination
    $where_count = [];
    $args_count = [];
    if ($status_filter !== 'all') { $where_count[] = 'status=%s'; $args_count[] = $status_filter; }
    if ($claim_search !== '') {
        $like = '%' . $wpdb->esc_like($claim_search) . '%';
        $where_count[] = '(unit_id LIKE %s OR machine_id LIKE %s)';
        $args_count[] = $like; $args_count[] = $like;
    }
    $sql_count = "SELECT COUNT(*) FROM {$wpdb->prefix}tmon_claim_requests" . ( $where_count ? (' WHERE ' . implode(' AND ', $where_count)) : '' );
    $total_count = $args_count ? (int) $wpdb->get_var($wpdb->prepare($sql_count, ...$args_count)) : (int) $wpdb->get_var($sql_count);
    $total_pages = max(1, (int) ceil($total_count / $claim_pp));

    // Query to display claims
    $sql_claims = "SELECT * FROM {$wpdb->prefix}tmon_claim_requests";
    $where = [];
    $args = [];
    if ($status_filter !== 'all') { $where[] = 'status=%s'; $args[] = $status_filter; }
    if ($claim_search !== '') { $where[] = '(unit_id LIKE %s OR machine_id LIKE %s)'; $args[] = $like; $args[] = $like; }
    if ($where) { $sql_claims .= ' WHERE ' . implode(' AND ', $where); }
    $sql_claims .= " ORDER BY created_at DESC LIMIT %d OFFSET %d";
    $args[] = $claim_pp;
    $args[] = $offset;
    $claims = $wpdb->get_results($wpdb->prepare($sql_claims, ...$args), ARRAY_A);

    // Pagination nav builder
    $base_url = admin_url('admin.php');
    $nav_base = add_query_arg([
        'page' => 'tmon-admin-provisioning',
        'claim_status' => $status_filter,
        'claim_pp' => $claim_pp,
        'claim_search' => $claim_search,
    ], $base_url);
    $prev_url = ($claim_page > 1) ? add_query_arg('claim_page', $claim_page - 1, $nav_base) : '';
    $next_url = ($claim_page < $total_pages) ? add_query_arg('claim_page', $claim_page + 1, $nav_base) : '';
    $first_url = add_query_arg('claim_page', 1, $nav_base);
    $last_url = add_query_arg('claim_page', $total_pages, $nav_base);

    $render_nav = function() use ($claim_page, $total_pages, $prev_url, $next_url, $first_url, $last_url, $total_count) {
        echo '<div class="tablenav"><div class="tablenav-pages">';
        echo '<span class="displaying-num">Total ' . intval($total_count) . ' items</span> ';
        echo '<span class="displaying-num">Page ' . intval($claim_page) . ' of ' . intval($total_pages) . '</span> ';
        echo '<span class="pagination-links">';
        echo $claim_page > 1 ? '<a class="first-page" href="'.esc_url($first_url).'">&laquo;</a> ' : '<span class="tablenav-pages-navspan">&laquo;</span> ';
        echo $prev_url ? '<a class="prev-page" href="'.esc_url($prev_url).'">&lsaquo;</a> ' : '<span class="tablenav-pages-navspan">&lsaquo;</span> ';
        echo $next_url ? '<a class="next-page" href="'.esc_url($next_url).'">&rsaquo;</a> ' : '<span class="tablenav-pages-navspan">&rsaquo;</span> ';
        echo $claim_page < $total_pages ? '<a class="last-page" href="'.esc_url($last_url).'">&raquo;</a>' : '<span class="tablenav-pages-navspan">&raquo;</span>';
        echo '</span></div></div>';
    };

    // Top nav
    $render_nav();
    echo '<table class="wp-list-table widefat"><thead><tr><th>ID</th><th>Unit ID</th><th>Machine ID</th><th>User ID</th><th>Status</th><th>Created</th><th>Actions</th></tr></thead><tbody>';
    foreach ($claims as $c) {
        echo '<tr>';
        echo '<td>'.intval($c['id']).'</td>';
        echo '<td>'.esc_html($c['unit_id']).'</td>';
        echo '<td>'.esc_html($c['machine_id']).'</td>';
        echo '<td>'.esc_html($c['user_id']).'</td>';
        echo '<td>'.esc_html($c['status']).'</td>';
        echo '<td>'.esc_html($c['created_at']).'</td>';
        echo '<td>';
        if ($c['status'] === 'pending') {
            echo '<form method="post" style="display:inline-block;margin-right:6px;">';
            wp_nonce_field('tmon_admin_claim');
            echo '<input type="hidden" name="action" value="approve_claim" />';
            echo '<input type="hidden" name="claim_id" value="'.intval($c['id']).'" />';
            submit_button('Approve', 'primary', '', false);
            echo '</form>';
            echo '<form method="post" style="display:inline-block;">';
            wp_nonce_field('tmon_admin_claim');
            echo '<input type="hidden" name="action" value="deny_claim" />';
            echo '<input type="hidden" name="claim_id" value="'.intval($c['id']).'" />';
            submit_button('Deny', 'delete', '', false);
            echo '</form>';
        }
        echo '</td>';
        echo '</tr>';
    }
    echo '</tbody></table>';
    // Bottom nav
    $render_nav();

    echo '</div>';
}

// Handle Admin purge actions from UI
add_action('admin_init', function(){
    if (!current_user_can('manage_options')) return;
    if (isset($_POST['tmon_admin_action']) && $_POST['tmon_admin_action'] === 'purge_all' && check_admin_referer('tmon_admin_purge_all')) {
        global $wpdb;
        $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_provisioned_devices");
        $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_claim_requests");
        $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_audit");
        if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $wpdb->prefix.'tmon_devices'))) {
            $wpdb->query("DELETE FROM {$wpdb->prefix}tmon_devices");
        }
        add_action('admin_notices', function(){ echo '<div class="updated"><p>Admin data purged.</p></div>'; });
    }
    if (isset($_POST['tmon_admin_action']) && $_POST['tmon_admin_action'] === 'purge_unit' && check_admin_referer('tmon_admin_purge_unit')) {
        global $wpdb;
        $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
        if ($unit_id) {
            $wpdb->delete($wpdb->prefix.'tmon_provisioned_devices', ['unit_id'=>$unit_id]);
            $wpdb->query($wpdb->prepare("DELETE FROM {$wpdb->prefix}tmon_claim_requests WHERE unit_id=%s", $unit_id));
            if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $wpdb->prefix.'tmon_devices'))) {
                $wpdb->delete($wpdb->prefix.'tmon_devices', ['unit_id'=>$unit_id]);
            }
        }
        add_action('admin_notices', function(){ echo '<div class="updated"><p>Unit data purged.</p></div>'; });
    }
});

// Admin-AJAX: Known Units typeahead for large datasets
add_action('wp_ajax_tmon_admin_known_units', function(){
    if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'forbidden'], 403);
    $nonce = isset($_GET['nonce']) ? sanitize_text_field(wp_unslash($_GET['nonce'])) : '';
    if (!wp_verify_nonce($nonce, 'tmon_admin_known_units')) wp_send_json_error(['message' => 'bad_nonce'], 403);
    global $wpdb;
    $q = isset($_GET['q']) ? sanitize_text_field(wp_unslash($_GET['q'])) : '';
    $page = isset($_GET['page']) ? max(1, intval($_GET['page'])) : 1;
    $per_page = isset($_GET['per_page']) ? max(1, min(200, intval($_GET['per_page']))) : 50;
    $limit = $per_page;
    $offset = ($page - 1) * $per_page;
    $filter_role = isset($_GET['role']) ? sanitize_text_field(wp_unslash($_GET['role'])) : '';
    $filter_company = isset($_GET['company_id']) ? intval($_GET['company_id']) : 0;
    $items = [];
    if ($q !== '') {
        $like = '%' . $wpdb->esc_like($q) . '%';
        // Local mirror (if present)
        if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $wpdb->prefix.'tmon_devices'))) {
            // NOTE: Optional filters role/company may not exist; ignoring at SQL level for local mirror to keep compatibility.
            $rows = $wpdb->get_results($wpdb->prepare(
                "SELECT unit_id, unit_name, machine_id, last_seen FROM {$wpdb->prefix}tmon_devices WHERE unit_id LIKE %s OR unit_name LIKE %s OR machine_id LIKE %s ORDER BY last_seen DESC LIMIT %d OFFSET %d",
                $like, $like, $like, $limit, $offset
            ), ARRAY_A);
            foreach ((array)$rows as $r) {
                $items[] = [
                    'unit_id' => $r['unit_id'],
                    'name' => $r['unit_name'] ?: $r['unit_id'],
                    'machine_id' => $r['machine_id'] ?: '',
                    'last_seen' => $r['last_seen'] ?: '',
                ];
            }
        }
        // Merge cached remote known ids
        if (count($items) < $limit) {
            $cache = get_option('tmon_admin_known_ids_cache', []);
            if (is_array($cache)) {
                $count_added = 0;
                $i = 0;
                foreach ($cache as $uid => $d) {
                    $name = isset($d['unit_name']) ? $d['unit_name'] : $uid;
                    $mid = isset($d['machine_id']) ? $d['machine_id'] : '';
                    $role_ok = true; $company_ok = true;
                    if ($filter_role && isset($d['role'])) { $role_ok = (strtolower($d['role']) === strtolower($filter_role)); }
                    if ($filter_company && isset($d['company_id'])) { $company_ok = (intval($d['company_id']) === $filter_company); }
                    if (
                        stripos($uid, $q) !== false ||
                        ($name && stripos($name, $q) !== false) ||
                        ($mid && stripos($mid, $q) !== false)
                    ) {
                        if ($role_ok && $company_ok) {
                            // emulate pagination across cache: skip until we reach offset remaining after local rows
                            if ($i++ < $offset) continue;
                            $items[] = [ 'unit_id' => $uid, 'name' => $name, 'machine_id' => $mid, 'last_seen' => $d['last_seen'] ?? '' ];
                            $count_added++;
                            if (count($items) >= $limit) break;
                        }
                    }
                }
            }
        }
    }
    // Deduplicate by unit_id
    $dedup = [];
    $out = [];
    foreach ($items as $it) { if (!isset($dedup[$it['unit_id']])) { $dedup[$it['unit_id']] = 1; $out[] = $it; } }
    wp_send_json_success(['items' => $out, 'page' => $page, 'per_page' => $per_page]);
});

// Fix for parse error: ensure all array values are quoted as strings.
$roles = ['base', 'remote', 'wifi'];

// Previously duplicated core installer name; renamed to avoid fatal.
if (!function_exists('tmon_admin_install_provisioning_schema')) {
    function tmon_admin_install_provisioning_schema() {
        global $wpdb;
        $charset_collate = $wpdb->get_charset_collate();
        $table = $wpdb->prefix . 'tmon_provisioned_devices';
        $sql = "CREATE TABLE IF NOT EXISTS $table (
            id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            unit_id VARCHAR(64) NOT NULL,
            machine_id VARCHAR(64) NOT NULL,
            role VARCHAR(32) DEFAULT 'base',
            company_id BIGINT UNSIGNED DEFAULT NULL,
            plan VARCHAR(64) DEFAULT 'standard',
            status VARCHAR(32) DEFAULT 'active',
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY unit_machine (unit_id, machine_id)
        ) $charset_collate;";
        require_once ABSPATH . 'wp-admin/includes/upgrade.php';
        dbDelta($sql);

        // Claim requests table
        $claim = $wpdb->prefix . 'tmon_claim_requests';
        $sql2 = "CREATE TABLE IF NOT EXISTS $claim (
            id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
            unit_id VARCHAR(64) NOT NULL,
            machine_id VARCHAR(64) NOT NULL,
            user_id BIGINT UNSIGNED NOT NULL,
            status VARCHAR(32) DEFAULT 'pending',
            notes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) $charset_collate;";
        dbDelta($sql2);
    }

    // Run after core schema install.
    add_action('tmon_admin_install_schema_after', 'tmon_admin_install_provisioning_schema');

    // Optional: ensure provisioning tables exist on activation (avoid duplicate core installer call).
    if (!has_action('activate_' . plugin_basename(__FILE__))) {
        register_activation_hook(__FILE__, function() {
            if (function_exists('tmon_admin_install_provisioning_schema')) {
                tmon_admin_install_provisioning_schema();
            }
        });
    }
}

// Add this function to avoid fatal error if not already defined elsewhere
if (!function_exists('tmon_admin_ensure_columns')) {
    /**
     * Ensure required columns exist in the tmon_provisioned_devices table.
     * Adds missing columns if necessary.
     */
    function tmon_admin_ensure_columns() {
        global $wpdb;
        $table = $wpdb->prefix . 'tmon_provisioned_devices';
        $required = [
            'role' => "ALTER TABLE $table ADD COLUMN role VARCHAR(32) DEFAULT 'base'",
            'company_id' => "ALTER TABLE $table ADD COLUMN company_id BIGINT UNSIGNED NULL",
            'plan' => "ALTER TABLE $table ADD COLUMN plan VARCHAR(64) DEFAULT 'standard'",
            'status' => "ALTER TABLE $table ADD COLUMN status VARCHAR(32) DEFAULT 'active'",
            'notes' => "ALTER TABLE $table ADD COLUMN notes TEXT",
            'created_at' => "ALTER TABLE $table ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP",
            'updated_at' => "ALTER TABLE $table ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP",
        ];
        $cols = $wpdb->get_results("SHOW COLUMNS FROM $table", ARRAY_A);
        $have = [];
        foreach (($cols ?: []) as $c) {
            $have[strtolower($c['Field'])] = true;
        }
        foreach ($required as $col => $sql) {
            if (empty($have[$col])) {
                $wpdb->query($sql);
                // Special handling for updated_at ON UPDATE
                if ($col === 'updated_at') {
                    $wpdb->query("ALTER TABLE $table MODIFY COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP");
                }
            }
        }
        // Ensure unique index on (unit_id, machine_id)
        $indexes = $wpdb->get_results("SHOW INDEX FROM $table", ARRAY_A);
        $hasUnitMachineIdx = false;
        foreach (($indexes ?: []) as $idx) {
            if (isset($idx['Key_name']) && $idx['Key_name'] === 'unit_machine') {
                $hasUnitMachineIdx = true;
                break;
            }
        }
        if (!$hasUnitMachineIdx) {
            $colsCheck = $wpdb->get_col("SHOW COLUMNS FROM $table LIKE 'unit_id'");
            $colsCheck2 = $wpdb->get_col("SHOW COLUMNS FROM $table LIKE 'machine_id'");
            if (!empty($colsCheck) && !empty($colsCheck2)) {
                $wpdb->query("ALTER TABLE $table ADD UNIQUE KEY unit_machine (unit_id, machine_id)");
            }
        }
        return true;
    }
}

// Add fallback for missing admin.css and admin.js to avoid 404 errors in browser console
add_action('admin_enqueue_scripts', function() {
    $plugin_url = plugin_dir_url(__FILE__);
    // Check if CSS exists before enqueue
    $css_path = dirname(__FILE__) . '/../assets/admin.css';
    if (file_exists($css_path)) {
        wp_enqueue_style('tmon-admin-css', $plugin_url . '../assets/admin.css', [], '0.1.2');
    }
    // Check if JS exists before enqueue
    $js_path = dirname(__FILE__) . '/../assets/admin.js';
    if (file_exists($js_path)) {
        wp_enqueue_script('tmon-admin-js', $plugin_url . '../assets/admin.js', [], '0.1.2', true);
    }
});