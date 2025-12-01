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
    if (empty($have['site_url'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN site_url VARCHAR(255) DEFAULT ''");
    }
    if (empty($have['unit_name'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN unit_name VARCHAR(128) DEFAULT ''");
    }
    // NEW: firmware metadata
    if (empty($have['firmware'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN firmware VARCHAR(128) DEFAULT ''");
    }
    if (empty($have['firmware_url'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN firmware_url VARCHAR(255) DEFAULT ''");
    }
    if (empty($have['settings_staged'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN settings_staged TINYINT(1) DEFAULT 0");
    }
    // NEW: normalized machine/unit ids for consistent matching
    if (empty($have['machine_id_norm'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN machine_id_norm VARCHAR(64) DEFAULT ''");
    }
    if (empty($have['unit_id_norm'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN unit_id_norm VARCHAR(64) DEFAULT ''");
    }

    // Backfill existing rows with normalized values (safe, idempotent)
    $rows = $wpdb->get_results("SELECT id, machine_id, unit_id FROM {$table}", ARRAY_A);
    if ($rows) {
        foreach ($rows as $r) {
            $norm_machine = '';
            if (!empty($r['machine_id'])) $norm_machine = tmon_admin_normalize_mac($r['machine_id']);
            $norm_unit = '';
            if (!empty($r['unit_id'])) $norm_unit = tmon_admin_normalize_key($r['unit_id']);
            if ($norm_machine || $norm_unit) {
                $wpdb->update($table, ['machine_id_norm' => $norm_machine, 'unit_id_norm' => $norm_unit], ['id' => intval($r['id'])]);
            }
        }
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

// Migration: ensure tmon_devices has a provisioned column for device mirror status
function tmon_admin_maybe_migrate_tmon_devices() {
    global $wpdb;
    $table = $wpdb->prefix . 'tmon_devices';
    $exists = $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table));
    if (!$exists) return;
    $cols = $wpdb->get_col($wpdb->prepare("SHOW COLUMNS FROM $table LIKE %s", 'provisioned'));
    if (empty($cols)) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN provisioned TINYINT(1) DEFAULT 0");
    }
}
add_action('admin_init', function() {
    // ...existing installation logic ...
    tmon_admin_maybe_migrate_tmon_devices();
});

// DB migration for tmon_devices fields (provisioned/provisioned_at/wordpress_api_url)
function tmon_admin_maybe_migrate_tmon_devices_columns() {
    global $wpdb;
    $table = $wpdb->prefix . 'tmon_devices';
    $exists = $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table));
    if (!$exists) return;
    $cols = [];
    foreach ($wpdb->get_results("SHOW COLUMNS FROM $table", ARRAY_A) as $c) { $cols[strtolower($c['Field'])] = true; }
    if (empty($cols['provisioned'])) $wpdb->query("ALTER TABLE $table ADD COLUMN provisioned TINYINT(1) DEFAULT 0");
    if (empty($cols['wordpress_api_url'])) $wpdb->query("ALTER TABLE $table ADD COLUMN wordpress_api_url VARCHAR(255) DEFAULT ''");
    if (empty($cols['provisioned_at'])) $wpdb->query("ALTER TABLE $table ADD COLUMN provisioned_at DATETIME DEFAULT NULL");
}
add_action('admin_init', 'tmon_admin_maybe_migrate_tmon_devices_columns');

// Helper: Get all devices, provisioned and unprovisioned
function tmon_admin_get_all_devices() {
    global $wpdb;
    $dev_table = $wpdb->prefix . 'tmon_devices';
    $prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
    // Include provisioned site_url (fallback to d.wordpress_api_url when missing)
    $sql = "SELECT d.unit_id, d.machine_id, d.unit_name, p.id as provision_id, p.role, p.company_id, p.plan, p.status, p.notes, p.created_at, p.updated_at, 
            COALESCE(NULLIF(p.site_url,''), d.wordpress_api_url) AS site_url, d.wordpress_api_url AS original_api_url
            FROM $dev_table d
            LEFT JOIN $prov_table p ON d.unit_id = p.unit_id AND d.machine_id = p.machine_id
            ORDER BY d.unit_id ASC";
    return $wpdb->get_results($sql, ARRAY_A);
}

// Provisioning page UI
function tmon_admin_provisioning_page() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    global $wpdb;

    // Show queue diagnostics at top of the page to help debugging
    $queue = get_option('tmon_admin_pending_provision', []);
    $queue_count = (is_array($queue)) ? count($queue) : 0;
    $last_ts = '';
    if ($queue_count) {
        // try to find most-recent requested_at across queued entries
        $most_recent = 0;
        foreach ($queue as $key => $payload) {
            $t = strtotime($payload['requested_at'] ?? '1970-01-01 00:00:00');
            if ($t && $t > $most_recent) $most_recent = $t;
        }
        if ($most_recent) $last_ts = date('Y-m-d H:i:s', $most_recent);
    }

    // Small admin notice area with queued count and latest queue timestamp
    echo '<div class="notice notice-info inline" style="margin-bottom:10px;">';
    echo '<p><strong>Provisioning queue:</strong> ' . intval($queue_count) . ' pending payload' . ($queue_count !== 1 ? 's' : '') . '.';
    if ($last_ts) echo ' (<em>last queued at ' . esc_html($last_ts) . '</em>)';
    echo '</p>';
    echo '<p class="description">Provisioning "Save & Provision" enqueues payloads for devices; use the Provisioning Activity page to review or re-enqueue / delete.</p>';
    echo '</div>';

    // Remove purge forms from this page (moved to Settings). Provide a hint.
    echo '<p class="description"><em>Data maintenance (purge & other destructive ops) moved to <a href="'.esc_url(admin_url('admin.php?page=tmon-admin-settings')).'">Settings</a> to avoid accidental data loss.</em></p>';

    $prov_table = $wpdb->prefix . 'tmon_provisioned_devices'; // PATCH: ensure $prov_table is available to all branches below
    // --- PATCH: Handle POST with redirect-after-POST pattern ---
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && function_exists('tmon_admin_verify_nonce') && tmon_admin_verify_nonce('tmon_admin_provision')) {
        $action = sanitize_text_field($_POST['action'] ?? '');
        $do_provision = isset($_POST['save_provision']);
        $redirect_url = remove_query_arg(['provision'], wp_get_referer() ?: admin_url('admin.php?page=tmon-admin-provisioning'));

        // --- UPDATE DEVICE ROW (table row form) ---
        if ($action === 'update') {
            $id = intval($_POST['id'] ?? 0);
            // Load DB row early to provide fallback values for payloads & mirroring
            $row_tmp = [];
            if ($id > 0) {
                $row_tmp = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$prov_table} WHERE id = %d LIMIT 1", $id), ARRAY_A) ?: [];
            }
            // Compute normalized or fallback ids for the row
            $unit_id = sanitize_text_field($_POST['unit_id'] ?? $row_tmp['unit_id'] ?? '');
            $machine_id = sanitize_text_field($_POST['machine_id'] ?? $row_tmp['machine_id'] ?? '');
            // Ensure we have a value for unit_name (use posted or fallback to DB row)
            $unit_name = sanitize_text_field($_POST['unit_name'] ?? $row_tmp['unit_name'] ?? '');
            $unit_norm = tmon_admin_normalize_key($unit_id);
            $mac_norm = tmon_admin_normalize_mac($machine_id);

            // Ensure $exists is defined for this branch (look up by keys)
            // $exists is computed later and update/insert logic handled below; no direct $data upsert here.
 
             // Always set these so later mirror updates have canonical id vars
             $row_unit_id = $unit_id;
             $row_machine_id = $machine_id;
 
            // Update staged flags using normalized columns
            if ($do_provision) {
                if (!empty($mac_norm)) {
                    $wpdb->update($prov_table, ['settings_staged'=>1,'updated_at'=>current_time('mysql')], ['machine_id_norm' => $mac_norm]);
                } else {
                    $wpdb->update($prov_table, ['settings_staged'=>1,'updated_at'=>current_time('mysql')], ['machine_id' => $machine_id]);
                }
                if (!empty($unit_norm)) {
                    $wpdb->update($prov_table, ['settings_staged'=>1,'updated_at'=>current_time('mysql')], ['unit_id_norm' => $unit_norm]);
                } else {
                    $wpdb->update($prov_table, ['settings_staged'=>1,'updated_at'=>current_time('mysql')], ['unit_id' => $unit_id]);
                }
                error_log("tmon-admin: set settings_staged=1 normalized unit_norm={$unit_norm} machine_norm={$mac_norm}");
            }
            // If inline Save & Provision was clicked, mark staged and enqueue payload
            if ($do_provision) {
                // mark staged on DB entry
                $row_id = $exists ?: $wpdb->insert_id;
                // FIXED: ensure proper parentheses in IF statement
                if ($row_id) {
                    $wpdb->update($prov_table, ['settings_staged' => 1, 'updated_at' => current_time('mysql')], ['id' => intval($row_id)]);
                    error_log(sprintf("tmon-admin: set settings_staged=1 for prov_row id=%d unit_id=%s machine_id=%s user=%s", intval($row_id), esc_html($unit_id), esc_html($machine_id), wp_get_current_user()->user_login));
                }
                // build payload to enqueue
                $payload = [
                    'site_url' => $site_url,
                    'wordpress_api_url' => $site_url,
                    'unit_name' => $unit_name, // ensure posted unit_name used
                    'firmware' => $firmware,
                    'firmware_url' => $firmware_url,
                    'role' => $role,
                    'plan' => $plan,
                    'notes' => $notes,
                    'requested_by_user' => wp_get_current_user()->user_login ?: 'system',
                    'requested_at' => current_time('mysql'),
                    'unit_id' => $unit_id,
                    'machine_id' => $machine_id,
                    'unit_id_norm' => $unit_norm,
                    'machine_id_norm' => $mac_norm,
                ];
                // Enqueue for both machine and unit (best-effort)
                if (!empty($machine_id)) {
                    tmon_admin_enqueue_provision($machine_id, $payload);
                    error_log("tmon-admin: inline provisioning enqueued for machine_id={$machine_id} payload_keys=".(isset($payload['machine_id'])? 'yes':'no') . ',' . (isset($payload['unit_id']) ? 'yes':'no'));
                }
                if (!empty($unit_id) && $unit_id !== $machine_id) {
                    tmon_admin_enqueue_provision($unit_id, $payload);
                    error_log("tmon-admin: inline provisioning enqueued for unit_id={$unit_id} payload_keys=".(isset($payload['machine_id'])? 'yes':'no') . ',' . (isset($payload['unit_id']) ? 'yes':'no'));
                }
                // Mirror to tmon_devices if present
                $dev_table = $wpdb->prefix . 'tmon_devices';
                if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $dev_table))) {
                    $dev_cols = $wpdb->get_col("SHOW COLUMNS FROM {$dev_table}");
                    $mirror = ['last_seen' => current_time('mysql')];
                    if (in_array('provisioned', $dev_cols)) $mirror['provisioned'] = 1; else $mirror['status'] = 'provisioned';
                    if (!empty($payload['site_url']) && in_array('site_url', $dev_cols)) $mirror['site_url'] = $payload['site_url'];
                    if (!empty($payload['site_url']) && in_array('wordpress_api_url', $dev_cols)) $mirror['wordpress_api_url'] = $payload['site_url'];
                    if (!empty($payload['unit_name']) && in_array('unit_name', $dev_cols)) $mirror['unit_name'] = $payload['unit_name'];
                    if (in_array('provisioned_at', $dev_cols)) $mirror['provisioned_at'] = current_time('mysql');
                    if (!empty($row_unit_id)) $wpdb->update($dev_table, $mirror, ['unit_id' => $row_unit_id]);
                    elseif (!empty($row_machine_id)) $wpdb->update($dev_table, $mirror, ['machine_id' => $row_machine_id]);
                }
                // Optionally push to UC site if site_url available (best-effort)
                if (!empty($site_url)) {
                    tmon_admin_push_to_uc_site($row_unit_id, $site_url, $role, $row_tmp['unit_name'] ?? $row_unit_id, intval($company_id ?? 0), null, null, $firmware, $firmware_url);
                }
            } else {
                // If not provisioning, just redirect
                $redirect_url = add_query_arg('provision', 'success', $redirect_url);
                wp_redirect($redirect_url);
                exit;
            }
        }  // end if ($action === 'update')
        elseif ($action === 'delete') {
             // --- NEW: Delete per-row handler (supports provisioned entries by id or unit/machine combo) ---
             $id = intval($_POST['id'] ?? 0);
             if ($id > 0) {
                 // Delete provisioned row by id
                 $wpdb->delete($prov_table, ['id' => $id]);
                 $redirect_url = add_query_arg('provision', 'success', $redirect_url);
                 wp_redirect($redirect_url);
                 exit;
             }
             // fallback: accept unit_id+machine_id to delete unprovisioned local mirror row or provisioned row if present
             $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
             $machine_id = sanitize_text_field($_POST['machine_id'] ?? '');
             if ($unit_id && $machine_id) {
                 // prefer to delete from provisioned table if entry exists
                 $exists = $wpdb->get_var($wpdb->prepare("SELECT id FROM $prov_table WHERE unit_id=%s AND machine_id=%s", $unit_id, $machine_id));
                 if ($exists) {
                     $wpdb->delete($prov_table, ['id' => intval($exists)]);
                     $redirect_url = add_query_arg('provision', 'success', $redirect_url);
                     wp_redirect($redirect_url);
                     exit;
                 }
                 // else delete from local devices mirror if present
                 $dev_table = $wpdb->prefix . 'tmon_devices';
                 if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $dev_table))) {
                     $deleted = $wpdb->delete($dev_table, ['unit_id' => $unit_id, 'machine_id' => $machine_id]);
                     $redirect_url = add_query_arg('provision', $deleted ? 'success' : 'fail', $redirect_url);
                     wp_redirect($redirect_url);
                     exit;
                 }
             }
             // If no valid deletion criteria, mark fail
             $redirect_url = add_query_arg('provision', 'fail', $redirect_url);
             wp_redirect($redirect_url);
             exit;
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
                $resp_code = !is_wp_error($resp) ? wp_remote_retrieve_response_code($resp) : 0;
                $ok = !is_wp_error($resp) && in_array($resp_code, [200, 201], true);
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
                $reg_code = !is_wp_error($reg_resp) ? wp_remote_retrieve_response_code($reg_resp) : 0;
                $reg_ok = !is_wp_error($reg_resp) && in_array($reg_code, [200, 201], true);
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
                $set_code = !is_wp_error($set_resp) ? wp_remote_retrieve_response_code($set_resp) : 0;
                $set_ok = !is_wp_error($set_resp) && in_array($set_code, [200, 201], true);
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
                $set_code = !is_wp_error($set_resp) ? wp_remote_retrieve_response_code($set_resp) : 0;
                $ok = !is_wp_error($set_resp) && in_array($set_code, [200, 201], true);
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
                    $resp_code = !is_wp_error($resp) ? wp_remote_retrieve_response_code($resp) : 0;
                    if (!is_wp_error($resp) && in_array($resp_code, [200, 201], true)) {
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
                    $ep_code = !is_wp_error($resp) ? wp_remote_retrieve_response_code($resp) : 0;
                    $ok = !is_wp_error($resp) && in_array($ep_code, [200, 201], true);
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

    // PATCH: Show admin notices after redirect
    if (isset($_GET['provision'])) {
        if ($_GET['provision'] === 'success') {
            echo '<div class="updated"><p>Device provisioned or updated successfully.</p></div>';
        } elseif ($_GET['provision'] === 'fail') {
            echo '<div class="error"><p>Failed to provision or update device. Please check required fields.</p></div>';
        }
    }

    // Add top-page notices for queued and queued-notified
    if (isset($_GET['provision']) && $_GET['provision'] === 'queued') {
        echo '<div class="updated inline"><p>Device provisioning queued; devices will receive on next check-in.</p></div>';
    }
    if (isset($_GET['provision']) && $_GET['provision'] === 'queued-notified') {
        echo '<div class="updated inline"><p>Device provisioning queued and UC notified (push attempt made).</p></div>';
    }

    // Render UI
    echo '<div class="wrap tmon-admin"><h1>Provisioning</h1>';
    // Standalone refresh known IDs form (outside of create form to avoid nested forms)
    echo '<h2>Known IDs</h2>';
    echo '<form method="post" style="margin-bottom:12px">';
    wp_nonce_field('tmon_admin_provision');
    echo '<input type="hidden" name="action" value="refresh_known_ids" />';
    submit_button('Refresh from paired UC sites', 'secondary', '', false);
    echo '</form>';

    // --- Unified Provisioning Form ---
    echo '<h2>Add or Update Provisioned Device</h2>';
    echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '" class="tmon-provision-form">';
    wp_nonce_field('tmon_admin_provision_device');
    echo '<input type="hidden" name="action" value="tmon_admin_provision_device" />';
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
    // Unit ID datalist (fixed: output <option> tags and close tags)
    echo '<tr><th scope="row">Unit ID</th><td>';
    echo '<input id="tmon_unit_id" name="unit_id" list="tmon_known_unit_ids" type="text" class="regular-text" required placeholder="e.g., 123456">';
    echo '<datalist id="tmon_known_unit_ids">';
    foreach ($known_units as $uid => $uname) {
        echo '<option value="'.esc_attr($uid).'">'.esc_html($uname).'</option>';
    }
    echo '</datalist>';
    echo '</td></tr>';

    // Machine ID datalist (reinserted where it was missing)
    echo '<tr><th scope="row">Machine ID</th><td>';
    echo '<input id="tmon_machine_id" name="machine_id" list="tmon_known_machine_ids" type="text" class="regular-text" required placeholder="e.g., 30:AE:A4:...">';
    echo '<datalist id="tmon_known_machine_ids">';
    foreach ($known_machines as $mid => $uidmap) {
        echo '<option value="'.esc_attr($mid).'">'.esc_html($uidmap).'</option>';
    }
    echo '</datalist>';
    echo '</td></tr>';

    echo '<tr><th scope="row">Role</th><td><select name="role"><option value="base">base</option><option value="remote">remote</option><option value="wifi">wifi</option></select></td></tr>';
    echo '<tr><th scope="row">Company ID</th><td><input name="company_id" type="number" class="small-text"></td></tr>';
    echo '<tr><th scope="row">Plan</th><td><select name="plan"><option>standard</option><option>pro</option><option>enterprise</option></select></td></tr>';
    echo '<tr><th scope="row">Status</th><td><select name="status"><option>active</option><option>suspended</option><option>expired</option></select></td></tr>';
    echo '<tr><th scope="row">Notes</th><td><textarea name="notes" class="large-text"></textarea></td></tr>';
    echo '<tr><th scope="row">Site URL</th><td><input name="site_url" type="url" class="regular-text" placeholder="https://example.com" /></td></tr>';
    echo '<tr><th scope="row">Unit Name</th><td><input name="unit_name" type="text" class="regular-text" placeholder="Optional display name"></td></tr>';
    // NEW: Firmware fields for create/update form
    echo '<tr><th scope="row">Firmware Version</th><td>';
    echo '<input name="firmware" id="tmon_firmware" type="text" class="regular-text" placeholder="e.g., 1.2.3" />';
    echo ' <button type="button" class="button tmon_fetch_github_btn" data-target="#tmon_firmware">Fetch from GitHub</button>';
    echo '</td></tr>';
    echo '<tr><th scope="row">Firmware URL</th><td>';
    echo '<input name="firmware_url" id="tmon_firmware_url" type="url" class="regular-text" placeholder="https://example.com/firmware.bin" />';
    echo ' <button type="button" class="button tmon_fetch_github_btn" data-target="#tmon_firmware_url">Fetch from GitHub</button>';
    echo '</td></tr>';
    echo '</table>';
    echo '<div class="tmon-form-actions">';
    submit_button('Save', 'secondary', 'submit', false);
    submit_button('Save & Provision to UC', 'primary', 'save_provision', false);
    echo '</div>';
    echo '</form>';

    // --- Provisioned Devices Table ---
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
        $select_cols = "d.unit_id, d.machine_id";
        if ($has_unit_name) $select_cols .= ", d.unit_name";
        if ($has_last_seen) $select_cols .= ", d.last_seen";
        // Use LEFT JOIN to exclude rows that are provisioned by both unit_id + machine_id
        if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $prov_table))) {
            $sql = "SELECT $select_cols FROM {$dev_table} d
                    LEFT JOIN {$prov_table} p ON d.unit_id = p.unit_id AND d.machine_id = p.machine_id
                    WHERE p.id IS NULL
                    ORDER BY d.unit_id ASC";
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
    echo '<table class="wp-list-table widefat"><thead><tr><th>ID</th><th>Unit ID</th><th>Name</th><th>Machine ID</th><th>Site URL</th><th>Role</th><th>Company ID</th><th>Plan</th><th>Status</th><th>Notes</th><th>Created</th><th>Updated</th><th>Actions</th></tr></thead><tbody>';
    foreach ($rows as $r) {
        echo '<tr>';
        echo '<td>'.intval($r['id']).'</td>';
        echo '<td>'.esc_html($r['unit_id']).'</td>';
        $cur_name = isset($names_map[$r['unit_id']]) ? $names_map[$r['unit_id']] : '';
        echo '<td>'.esc_html($cur_name).'</td>';
        // echo Machine ID cell already exists
        echo '<td>'.esc_html($r['machine_id']).'</td>';
        // New Site URL cell (use coalesced value)
        echo '<td>' . esc_url($r['site_url'] ?? ($r['wordpress_api_url'] ?? '')) . '</td>';
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
        // FIX: Wrap "base", "remote", and "wifi" in quotes to avoid syntax errors
        echo ' Role <select name="role">';
        echo '<option value="base"' . (($r['role'] === 'base') ? ' selected' : '') . '>base</option>';
        echo '<option value="remote"' . (($r['role'] === 'remote') ? ' selected' : '') . '>remote</option>';
        echo '<option value="wifi"' . (($r['role'] === 'wifi') ? ' selected' : '') . '>wifi</option>';
        echo '</select>';
        echo ' Plan <select name="plan">';
        echo '<option value="standard"' . ($r['plan'] === "standard" ? ' selected="selected"' : '') . '>standard</option>';
        echo '<option value="pro"' . ($r['plan'] === "pro" ? ' selected="selected"' : '') . '>pro</option>';
        echo '<option value="enterprise"' . ($r['plan'] === "enterprise" ? ' selected="selected"' : '') . '>enterprise</option>';
        echo '</select>';
        echo ' Status <select name="status">';
        echo '<option value="active"' . ($r['status'] === "active" ? ' selected="selected"' : '') . '>active</option>';
        echo '<option value="suspended"' . ($r['status'] === "suspended" ? ' selected="selected"' : '') . '>suspended</option>';
        echo '<option value="expired"' . ($r['status'] === "expired" ? ' selected="selected"' : '') . '>expired</option>';
        echo '</select>';
        echo ' Company <input name="company_id" type="number" class="small-text" value="'.intval($r['company_id']).'" />';
        echo ' Notes <input name="notes" type="text" class="regular-text" value="'.esc_attr($r['notes']).'" />';
        echo ' Site URL <input name="site_url" type="url" class="regular-text" value="'.esc_attr($r['site_url'] ?? ($r['wordpress_api_url'] ?? '')).'"/>';
        echo ' Unit Name <input name="unit_name" type="text" class="regular-text" value="'.esc_attr($r['unit_name'] ?? '').'" />';
        // NEW: per-row firmware fields
        echo ' Firmware <input name="firmware" type="text" class="regular-text tmon_row_firmware" value="'.esc_attr($r['firmware'] ?? '').'" placeholder="1.2.3" /> ';
        echo ' Firmware URL <input name="firmware_url" type="url" class="regular-text tmon_row_firmware_url" value="'.esc_attr($r['firmware_url'] ?? '').'" placeholder="https://..." /> ';
        echo ' <button type="button" class="button tmon_fetch_github_btn_row" data-row="'.intval($r['id']).'">Fetch from GitHub</button>';
        echo '<div class="tmon-form-actions">';
        submit_button('Save', 'secondary', 'submit', false);
        submit_button('Save & Provision to UC', 'primary', 'save_provision', false);
        echo '</div>';
        echo '</form>';
        // Remove other per-row forms (push config, send registry, push role+gps) for clarity
        echo '</td>';
        echo '</tr>';
    }
    echo '</tbody></table>';

    // Data Maintenance (Admin-side purge UI)
    // Removed: now handled in Settings

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

    // --- Insert JS here: ensure it runs in admin context (wp_create_nonce is available) ---
    $fetch_nonce = wp_create_nonce('tmon_admin_fetch_github');
    $admin_ajax_url = wp_json_encode(esc_url(admin_url('admin-ajax.php')));
    $fetch_nonce_js = wp_json_encode($fetch_nonce);
    echo <<<EOT
<script>
(function(){
    const ajaxUrl = {$admin_ajax_url};
    const fetchNonce = {$fetch_nonce_js};

    async function fetchGithubAndFill(row=null) {
        const params = new URLSearchParams();
        params.set('action','tmon_admin_fetch_github_manifest');
        params.set('nonce', fetchNonce);

        // Try POST first (more robust)
        try {
            const resp = await fetch(ajaxUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
                body: params.toString(),
                credentials: 'same-origin'
            });
            if (!resp.ok) {
                // Try to read text body to show diagnostic info
                const text = await resp.text().catch(()=>'(no body)');
                console.error('GitHub manifest fetch failed (POST):', resp.status, text);
                // fallback to GET attempt
                return fallbackGet(row, params);
                                                                                                                                                                                                                                                                                                                                                                                                                         }
            const json = await resp.json().catch(()=>null);
            if (!json || !json.success) {
                console.warn('GitHub manifest returned no data or not success:', json);
                alert('Failed to fetch firmware metadata from GitHub.');
                return;
            }
            fillInputs(json, row);
        } catch (err) {
            console.error('GitHub manifest fetch error (POST):', err);
            // fallback to GET attempt
            return fallbackGet(row, params);
        }
    }

    async function fallbackGet(row, params) {
        // Try GET as a fallback, to show whether server accepts GET
        try {
            const resp = await fetch(ajaxUrl + '?' + params.toString(), {
                method: 'GET',
                credentials: 'same-origin'
            });
            if (!resp.ok) {
                const text = await resp.text().catch(()=>'(no body)');
                console.error('GitHub manifest fetch failed (GET):', resp.status, text);
                alert('Failed to fetch firmware metadata from GitHub (server returned ' + resp.status + ')');
                return;
            }
            const json = await resp.json().catch(()=>null);
            if (!json || !json.success) {
                console.warn('GitHub manifest returned no data or not success:', json);
                alert('Failed to fetch firmware metadata from GitHub.');
                return;
            }
            fillInputs(json, row);
        } catch (err) {
            console.error('GitHub manifest fetch error (GET):', err);
            alert('Error contacting server for GitHub manifest.');
            return;
        }
    }

    function fillInputs(json, row=null) {
        const ver = json.data.version || '';
        const url = json.data.firmware_url || '';
        if (row) {
            const verEl = row.querySelector('.tmon_row_firmware');
            const urlEl = row.querySelector('.tmon_row_firmware_url');
            if (verEl) verEl.value = ver;
            if (urlEl) urlEl.value = url;
        } else {
            const verEl = document.querySelector('#tmon_firmware');
            const urlEl = document.querySelector('#tmon_firmware_url');
            if (verEl) verEl.value = ver;
            if (urlEl) urlEl.value = url;
        }
    }

    // Top form fetch button(s)
    document.querySelectorAll('.tmon_fetch_github_btn').forEach(function(btn){
        btn.addEventListener('click', function(e){
            e.preventDefault();
            fetchGithubAndFill(null);
        });
    });

    // Per-row fetch buttons
    document.querySelectorAll('.tmon_fetch_github_btn_row').forEach(function(btn){
        btn.addEventListener('click', function(e){
            e.preventDefault();
            const row = btn.closest('tr');
            if (!row) return;
            fetchGithubAndFill(row);
        });
    });
})();
</script>
EOT;

    // --- Diagnostic form handler (admin-side) ---
    if ($_SERVER['REQUEST_METHOD'] === 'POST'
        && function_exists('tmon_admin_verify_nonce')
        && tmon_admin_verify_nonce('tmon_admin_provision_diag')) {

        $diag_key = sanitize_text_field($_POST['diag_key'] ?? '');
        if ($diag_key) {
            $k = function_exists('tmon_admin_normalize_key') ? tmon_admin_normalize_key($diag_key) : strtolower(trim($diag_key));
            $queued = function_exists('tmon_admin_get_pending_provision') ? tmon_admin_get_pending_provision($k) : null;

            // DB lookup (case-insensitive) for both unit_id and machine_id
            $prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
            $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$prov_table} WHERE LOWER(machine_id)=LOWER(%s) OR LOWER(unit_id)=LOWER(%s) LIMIT 1", $k, $k), ARRAY_A);
            $staged = intval($row['settings_staged'] ?? 0) === 1;

            // Last few history entries for the key
            $history = get_option('tmon_admin_provision_history', []);
            $matching_history = [];
            if (is_array($history)) {
                foreach (array_reverse($history) as $h) {
                    if (isset($h['unit_id']) && (strcasecmp($h['unit_id'], $k) === 0)) {
                        $matching_history[] = $h; if (count($matching_history) >= 10) break;
                    }
                    if (isset($h['machine_id']) && (strcasecmp($h['machine_id'], $k) === 0)) {
                        $matching_history[] = $h; if (count($matching_history) >= 10) break;
                    }
                }
            }
            // Render diagnostics immediately above the page; admin page will display this (escaped)
            echo '<div class="notice notice-info inline"><p><strong>Provisioning Diagnostic:</strong></p>';
            echo '<pre style="max-width:100%;white-space:pre-wrap;">' . esc_html( wp_json_encode([
                'key' => $k, 'queued' => $queued, 'db_row' => $row ? $row : null, 'staged_db' => $staged, 'history' => $matching_history
            ], JSON_PRETTY_PRINT) ) . '</pre></div>';
            error_log("tmon-admin: admin diagnostic for key={$k} (queued=" . ($queued? '1' : '0') . " staged_db=" . ($staged ? '1':'0') . ")");
        } else {
            echo '<div class="notice notice-warning inline"><p>Provisioning Diagnostic: No key provided.</p></div>';
        }
    }

    // Diagnostic & Debug section
    echo '<h2>Diagnostic & Debug</h2>';
    echo '<p>Enter a Unit ID or Machine ID and click Diagnose to inspect queued payloads, DB staging flag, and recent provisioning history for that key.</p>';
    echo '<form method="post" style="margin-bottom:12px">';
    wp_nonce_field('tmon_admin_provision_diag');
    echo '<input type="hidden" name="action" value="diagnose_provision" />';
    echo '<input type="text" name="diag_key" placeholder="unit id or machine id" class="regular-text" />';
    submit_button('Diagnose Provisoning Key', 'secondary', 'diagnose', false);
    echo '</form>';

    // --- Debug: REST API call history ---
    echo '<h2>API Call History</h2>';
    $history = get_option('tmon_admin_api_history', []);
    if (!is_array($history)) $history = [];
    if (count($history) === 0) {
        echo '<p class="description">No recent API calls found. Trigger a check-in or other actions to log API call history.</p>';
    } else {
        echo '<table class="wp-list-table widefat"><thead><tr><th>Time</th><th>Type</th><th>Key</th><th>Payload</th><th>Status</th><th>Response</th></tr></thead><tbody>';
        foreach (array_reverse($history) as $h) {
            $time = esc_html($h['time'] ?? '');
            $type = esc_html($h['type'] ?? '');
            $key = esc_html($h['key'] ?? '');
            $payload = esc_html(wp_json_encode($h['payload'] ?? [], JSON_PRETTY_PRINT));
            $status = esc_html($h['status'] ?? '');
            $response = esc_html($h['response'] ?? '');
            echo "<tr>
                    <td>$time</td>
                    <td>$type</td>
                    <td>$key</td>
                    <td><pre>$payload</pre></td>
                    <td>$status</td>
                    <td><pre>$response</pre></td>
                  </tr>";
        }
        echo '</tbody></table>';
    }

    // --- Debug: Recent Provisioning History ---
    echo '<h2>Recent Provisioning History</h2>';
    $prov_history = get_option('tmon_admin_provision_history', []);
    if (!is_array($prov_history)) $prov_history = [];
    if (count($prov_history) === 0) {
        echo '<p class="description">No recent provisioning history found. Provision devices to generate history records.</p>';
    } else {
        echo '<table class="wp-list-table widefat"><thead><tr><th>Time</th><th>Unit ID</th><th>Machine ID</th><th>Status</th><th>Notes</th></tr></thead><tbody>';
        foreach (array_reverse($prov_history) as $h) {
            $time = esc_html($h['time'] ?? '');
            $unit_id = esc_html($h['unit_id'] ?? '');
            $machine_id = esc_html($h['machine_id'] ?? '');
            $status = esc_html($h['status'] ?? '');
            $notes = esc_html($h['notes'] ?? '');
            echo "<tr>
                    <td>$time</td>
                    <td>$unit_id</td>
                    <td>$machine_id</td>
                    <td>$status</td>
                    <td>$notes</td>
                  </tr>";
        }
        echo '</tbody></table>';
    }

    echo '</div>'; // end of provisioning page markup
}

/**
 * Push device registration + settings to a Unit Connector site.
 * Returns true on success.
 */
function tmon_admin_push_to_uc_site($unit_id, $site_url, $role = 'base', $maybe_name = '', $company_id = 0, $gps_lat = null, $gps_lng = null, $firmware = '', $firmware_url = '') {
	global $wpdb;
	if (empty($unit_id) || empty($site_url)) return false;
	$headers = ['Content-Type'=>'application/json'];
	$pairings = get_option('tmon_admin_uc_sites', []);
	$uc_key = is_array($pairings) && isset($pairings[$site_url]['uc_key']) ? $pairings[$site_url]['uc_key'] : '';

	// Register device
	$reg_endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/device/register';
	$reg_body = ['unit_id' => $unit_id];
	if (!empty($maybe_name)) $reg_body['unit_name'] = $maybe_name;
	if ($company_id) $reg_body['company_id'] = $company_id;
	$reg_resp = wp_remote_post($reg_endpoint, ['timeout'=>20,'headers'=>$headers,'body'=>wp_json_encode($reg_body)]);
	$reg_code = !is_wp_error($reg_resp) ? wp_remote_retrieve_response_code($reg_resp) : 0;
	$reg_ok = !is_wp_error($reg_resp) && in_array($reg_code, [200, 201], true);

	// Push settings (NODE_TYPE and optional GPS + company + firmware)
	$settings = ['NODE_TYPE'=>$role, 'WIFI_DISABLE_AFTER_PROVISION'=>($role === 'remote')];
	if (!empty($maybe_name)) { $settings['UNIT_Name'] = $maybe_name; }
	if ($company_id) { $settings['COMPANY_ID'] = $company_id; }
	if (!is_null($gps_lat) && !is_null($gps_lng)) { $settings['GPS_LAT']=$gps_lat; $settings['GPS_LNG']=$gps_lng; }
	if (!empty($firmware)) { $settings['FIRMWARE'] = $firmware; }
	if (!empty($firmware_url)) { $settings['FIRMWARE_URL'] = $firmware_url; }
	$set_endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/admin/device/settings';
	$set_resp = wp_remote_post($set_endpoint, ['timeout'=>20,'headers'=>$headers,'body'=>wp_json_encode(['unit_id'=>$unit_id,'settings'=>$settings])]);
	$set_code = !is_wp_error($set_resp) ? wp_remote_retrieve_response_code($set_resp) : 0;
	$set_ok = !is_wp_error($set_resp) && in_array($set_code, [200, 201], true);

	do_action('tmon_admin_audit', 'send_to_uc_registry', sprintf('unit_id=%s name=%s role=%s site=%s firmware=%s firmware_url=%s', $unit_id, $maybe_name, $role, $site_url, $firmware, $firmware_url));
	return ($reg_ok && $set_ok);
}

// Handle Admin purge actions from UI
add_action('admin_init', function(){
    if (!current_user_can('manage_options')) return;
    // Remove duplicate purge logic (moved to settings.php)
    # previously handled purge_all / purge_unit here; this logic is now centralized in includes/settings.php
});

// Add missing callback used by admin menu: Provisioning History page
if (!function_exists('tmon_admin_provisioning_history_page')) {
	function tmon_admin_provisioning_history_page() {
		if (!current_user_can('manage_options')) {
			wp_die('Forbidden');
		}

		// Fetch history option
		$history = get_option('tmon_admin_provision_history', []);
		if (!is_array($history)) $history = [];

		echo '<div class="wrap"><h1>TMON Admin — Provisioning History</h1>';
		if (empty($history)) {
			echo '<p>No provisioning history available.</p>';
			echo '</div>';
			return;
		}

		echo '<table class="wp-list-table widefat fixed striped"><thead><tr>';
		echo '<th style="width:160px">Timestamp</th>';
		echo '<th>Acting User</th>';
		echo '<th style="width:120px">Unit ID</th>';
		echo '<th style="width:220px">Machine ID</th>';
		echo '<th>Action</th>';
		echo '<th>Site</th>';
		echo '<th>Payload / Meta</th>';
		echo '</tr></thead><tbody>';

		// Display most recent first
		foreach (array_reverse($history) as $item) {
			$ts = esc_html($item['ts'] ?? $item['time'] ?? '');
			$user = esc_html($item['user'] ?? '');
			$unit = esc_html($item['unit_id'] ?? '');
			$machine = esc_html($item['machine_id'] ?? '');
			$action = esc_html($item['action'] ?? '');
			$site = esc_html($item['site'] ?? '');
			$meta = $item['meta'] ?? $item['payload'] ?? null;
			if (is_array($meta) || is_object($meta)) {
				$meta_json = esc_html(wp_json_encode($meta, JSON_PRETTY_PRINT));
			} else {
				$meta_json = esc_html((string)$meta);
			}

			echo '<tr>';
			echo '<td>' . $ts . '</td>';
			echo '<td>' . $user . '</td>';
			echo '<td>' . $unit . '</td>';
			echo '<td>' . $machine . '</td>';
			echo '<td>' . $action . '</td>';
			echo '<td>' . $site . '</td>';
			echo '<td><pre style="white-space:pre-wrap;max-width:520px;">' . $meta_json . '</pre></td>';
			echo '</tr>';
		}

		echo '</tbody></table>';
		echo '</div>';
	}
}

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

// --- PATCH: Add AJAX endpoint to fetch firmware information from GitHub ---
add_action('wp_ajax_tmon_admin_fetch_github_manifest', function() {
    if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'forbidden'], 403);
    check_ajax_referer('tmon_admin_fetch_github', 'nonce');

    // Preferred: manifest JSON in micropython repo; fallback to version.txt
    $base_raw = 'https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/';
    $manifest_url = $base_raw . 'manifest.json';
    $ver_url = $base_raw . 'version.txt';
    $firmware_url = '';
    $version = '';

    // Try manifest.json first
    $resp = wp_remote_get($manifest_url, ['timeout' => 10]);
    if (!is_wp_error($resp) && wp_remote_retrieve_response_code($resp) == 200) {
        $body = wp_remote_retrieve_body($resp);
        $m = json_decode($body, true);
        if (is_array($m)) {
            // common manifest shapes: {'version': '...', 'files': [{'path':'firmware.bin'}]} or {'firmware':'firmware.bin', 'version':'...'}
            if (!empty($m['version'])) { $version = sanitize_text_field($m['version']); }
            if (!empty($m['firmware'])) {
                $firmware_url = $base_raw . ltrim($m['firmware'], '/');
            } elseif (!empty($m['files']) && is_array($m['files'])) {
                // attempt to find the first file that looks like a firmware binary
                foreach ($m['files'] as $f) {
                    if (is_array($f) && !empty($f['path'])) {
                        $p = $f['path'];
                    } elseif (is_string($f)) {
                        $p = $f;
                    } else { $p = ''; }
                    if ($p && preg_match('/firmware|.bin|.hex|.img/i', $p)) {
                        $firmware_url = $base_raw . ltrim($p, '/');
                        break;
                    }
                }
            }
        }
    }

    // fallback to version.txt to get just the version
    if (empty($version) || empty($firmware_url)) {
        $resp2 = wp_remote_get($ver_url, ['timeout' => 10]);
        if (!is_wp_error($resp2) && wp_remote_retrieve_response_code($resp2) == 200) {
            $body2 = trim(wp_remote_retrieve_body($resp2));
            if ($body2) {
                if (empty($version)) $version = sanitize_text_field($body2);
                // Construct a default firmware filename if manifest not present
                if (empty($firmware_url)) {
                    // Assume commonly named firmware binary in repo root
                    $firmware_url = $base_raw . 'firmware.bin';
                }
            }
        }
    }

    if (empty($version) && empty($firmware_url)) {
        wp_send_json_error(['message' => 'manifest or version file not found'], 404);
    }

    wp_send_json_success(['version' => $version, 'firmware_url' => esc_url_raw($firmware_url)]);
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
            unit_id_norm VARCHAR(64) DEFAULT '',
            machine_id_norm VARCHAR(64) DEFAULT '',
            role VARCHAR(32) DEFAULT 'base',
            company_id BIGINT UNSIGNED DEFAULT NULL,
            plan VARCHAR(64) DEFAULT 'standard',
            status VARCHAR(32) DEFAULT 'active',
            notes TEXT,
            firmware VARCHAR(128) DEFAULT '',
            firmware_url VARCHAR(255) DEFAULT '',
            site_url VARCHAR(255) DEFAULT '',
            unit_name VARCHAR(128) DEFAULT '',
            settings_staged TINYINT(1) DEFAULT 0,
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

// --- NEW/ENSURE: Queue helpers + normalized key helper ---
// Provide lightweight queue helpers using normalized key semantics so queuing & dequeuing is consistent.
if (!function_exists('tmon_admin_normalize_queue_key')) {
    function tmon_admin_normalize_queue_key($key) {
        $k = (string) $key;
        $k = trim($k);
        if ($k === '') return '';
        // If it looks like a MAC (hex groups, contains ':' or '-' or length > 8) prefer normalize_mac
        if (function_exists('tmon_admin_normalize_mac') && (strpos($k, ':') !== false || strpos($k, '-') !== false || preg_match('/^[0-9a-fA-F:.\-]{6,}$/', $k))) {
            return tmon_admin_normalize_mac($k);
        }
        if (function_exists('tmon_admin_normalize_key')) {
            return tmon_admin_normalize_key($k);
        }
        return strtolower($k);
    }
}

if (!function_exists('tmon_admin_enqueue_provision')) {
    function tmon_admin_enqueue_provision($raw_key, array $payload) {
        $k = tmon_admin_normalize_queue_key($raw_key);
        if ($k === '') return false;
        $q = get_option('tmon_admin_pending_provision', []);
        if (!is_array($q)) $q = [];
        // Keep original payload but persist normalized keys for better lookup
        if (!isset($payload['unit_id_norm']) && !empty($payload['unit_id'])) $payload['unit_id_norm'] = tmon_admin_normalize_queue_key($payload['unit_id']);
        if (!isset($payload['machine_id_norm']) && !empty($payload['machine_id'])) $payload['machine_id_norm'] = tmon_admin_normalize_queue_key($payload['machine_id']);
        $q[$k] = $payload;
        update_option('tmon_admin_pending_provision', $q, false);
        return true;
    }
}

if (!function_exists('tmon_admin_get_pending_provision')) {
    function tmon_admin_get_pending_provision($raw_key) {
        $k = tmon_admin_normalize_queue_key($raw_key);
        $q = get_option('tmon_admin_pending_provision', []);
        if (!is_array($q)) return null;
        return $q[$k] ?? null;
    }
}

if (!function_exists('tmon_admin_dequeue_provision')) {
    function tmon_admin_dequeue_provision($raw_key) {
        $k = tmon_admin_normalize_queue_key($raw_key);
        if ($k === '') return false;
        $q = get_option('tmon_admin_pending_provision', []);
        if (!is_array($q)) return false;
        if (!isset($q[$k])) return false;
        unset($q[$k]);
        update_option('tmon_admin_pending_provision', $q, false);
        return true;
    }
}

// Consumer helper: returns queue key + payload for given machine_id/unit_id
if (!function_exists('tmon_admin_find_queued_payload_for_device')) {
    function tmon_admin_find_queued_payload_for_device($machine_id, $unit_id) {
        $q = get_option('tmon_admin_pending_provision', []);
        if (!is_array($q) || empty($q)) return null;
        $cands = [];
        if (!empty($machine_id)) {
            $cands[] = tmon_admin_normalize_queue_key($machine_id);
            $cands[] = tmon_admin_normalize_mac($machine_id);
        }
        if (!empty($unit_id)) {
            $cands[] = tmon_admin_normalize_queue_key($unit_id);
            $cands[] = tmon_admin_normalize_key($unit_id);
        }
        // raw lower-case fallback
        if (!empty($machine_id)) $cands[] = strtolower(trim($machine_id));
        if (!empty($unit_id)) $cands[] = strtolower(trim($unit_id));
        $cands = array_values(array_unique(array_filter($cands)));
        foreach ($cands as $ck) {
            if ($ck === '') continue;
            if (isset($q[$ck]) && is_array($q[$ck])) {
                return [$ck, $q[$ck]];
            }
        }
        // fallback: find a payload that contains normalized fields matching our candidates
        foreach ($q as $key => $payload) {
            foreach ($cands as $ck) {
                if ($ck === '') continue;
                if (!empty($payload['machine_id_norm']) && strcasecmp($payload['machine_id_norm'], $ck) === 0) return [$key, $payload];
                if (!empty($payload['unit_id_norm']) && strcasecmp($payload['unit_id_norm'], $ck) === 0) return [$key, $payload];
            }
        }
        return null;
    }
}

if (!function_exists('tmon_admin_find_queued_or_staged')) {
    function tmon_admin_find_queued_or_staged($machine_id, $unit_id) {
        global $wpdb;
        $prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
        // 1) DB normalize candidates
        $norm_candidates = [];
        if (!empty($machine_id)) $norm_candidates[] = tmon_admin_normalize_mac($machine_id);
        if (!empty($machine_id)) $norm_candidates[] = tmon_admin_normalize_key($machine_id);
        if (!empty($unit_id)) $norm_candidates[] = tmon_admin_normalize_key($unit_id);
        $norm_candidates = array_values(array_unique(array_filter($norm_candidates)));
        foreach ($norm_candidates as $ck) {
            $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$prov_table} WHERE settings_staged = 1 AND (machine_id_norm = %s OR unit_id_norm = %s OR LOWER(machine_id)=LOWER(%s) OR LOWER(unit_id)=LOWER(%s) ) LIMIT 1", $ck, $ck, $ck, $ck), ARRAY_A);
            if ($row && intval($row['settings_staged'] ?? 0) === 1) {
                return ['found'=>'db','key'=>$ck,'row'=>$row];
            }
        }
        // 2) queued payload
        if (function_exists('tmon_admin_find_queued_payload_for_device')) {
            $qa = tmon_admin_find_queued_payload_for_device($machine_id, $unit_id);
            if (is_array($qa) && count($qa) >= 2) {
                return ['found'=>'queue','key'=>$qa[0],'queued'=>$qa[1]];
            }
        }
        // 3) nothing
        return ['found'=>false,'key'=>null];
    }
}

// --- Fix: admin_post handler must set row_unit / row_machine and ensure payload includes unit_name so mirroring works ---
add_action('admin_post_tmon_admin_provision_device', function() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    check_admin_referer('tmon_admin_provision_device');
    global $wpdb;

    $unit_id    = sanitize_text_field($_POST['unit_id'] ?? '');
    $machine_id = sanitize_text_field($_POST['machine_id'] ?? '');
    $company_id = intval($_POST['company_id'] ?? 0);
    $plan       = sanitize_text_field($_POST['plan'] ?? 'standard');
    $status     = sanitize_text_field($_POST['status'] ?? 'active');
    $notes      = sanitize_textarea_field($_POST['notes'] ?? '');
    $role       = sanitize_text_field($_POST['role'] ?? 'base');
    $site_url   = esc_url_raw($_POST['site_url'] ?? '');
    $unit_name  = isset($_POST['unit_name']) ? sanitize_text_field($_POST['unit_name']) : '';
    // firmware fields
    $firmware      = sanitize_text_field($_POST['firmware'] ?? '');
    $firmware_url  = esc_url_raw($_POST['firmware_url'] ?? '');
    $save_provision = isset($_POST['save_provision']);

    // Basic validation
    if (!$unit_id || !$machine_id) {
        wp_redirect(add_query_arg('provision', 'fail', wp_get_referer()));
        exit;
    }

    $table = $wpdb->prefix . 'tmon_provisioned_devices';
    $prov_table = $table; // ensure consistent variable name
    $exists = $wpdb->get_var($wpdb->prepare("SELECT id FROM $table WHERE unit_id=%s AND machine_id=%s", $unit_id, $machine_id));

    $data = [
        'unit_id'         => $unit_id,
        'machine_id'      => $machine_id,
        'company_id'      => $company_id,
        'plan'            => $plan,
        'status'          => $status,
        'notes'           => $notes,
        'role'            => $role,
        'site_url'        => $site_url,
        'unit_name'       => $unit_name,
        'firmware'        => $firmware,
        'firmware_url'    => $firmware_url,
        'settings_staged' => 1,
    ];

    // Ensure normalized fields are computed
    $unit_norm = tmon_admin_normalize_key($unit_id);
    $mac_norm = tmon_admin_normalize_mac($machine_id);

    $data['unit_id_norm'] = $unit_norm;
    $data['machine_id_norm'] = $mac_norm;

    if ($exists) {
        $wpdb->update($table, $data, ['id' => $exists]);
    } else {
        $wpdb->insert($table, $data);
    }

    // Always set these so later mirror updates have canonical id vars
    $row_unit_id = $unit_id;
    $row_machine_id = $machine_id;

    // Update staged flags using normalized columns
    if ($save_provision) {
        if (!empty($mac_norm)) {
            $wpdb->update($prov_table, ['settings_staged'=>1,'updated_at'=>current_time('mysql')], ['machine_id_norm' => $mac_norm]);
        } else {
            $wpdb->update($prov_table, ['settings_staged'=>1,'updated_at'=>current_time('mysql')], ['machine_id' => $machine_id]);
        }
        if (!empty($unit_norm)) {
            $wpdb->update($prov_table, ['settings_staged'=>1,'updated_at'=>current_time('mysql')], ['unit_id_norm' => $unit_norm]);
        } else {
            $wpdb->update($prov_table, ['settings_staged'=>1,'updated_at'=>current_time('mysql')], ['unit_id' => $unit_id]);
        }
        error_log("tmon-admin: set settings_staged=1 normalized unit_norm={$unit_norm} machine_norm={$mac_norm}");
    }
    // If inline Save & Provision was clicked, mark staged and enqueue payload
    if ($save_provision) {
        // mark staged on DB entry
        $row_id = $exists ?: $wpdb->insert_id;
        // FIXED: ensure proper parentheses in IF statement
        if ($row_id) {
            $wpdb->update($prov_table, ['settings_staged' => 1, 'updated_at' => current_time('mysql')], ['id' => intval($row_id)]);
            error_log(sprintf("tmon-admin: set settings_staged=1 for prov_row id=%d unit_id=%s machine_id=%s user=%s", intval($row_id), esc_html($unit_id), esc_html($machine_id), wp_get_current_user()->user_login));
        }
        // build payload to enqueue
        $payload = [
            'site_url' => $site_url,
            'wordpress_api_url' => $site_url,
            'unit_name' => $unit_name, // ensure posted unit_name used
            'firmware' => $firmware,
            'firmware_url' => $firmware_url,
            'role' => $role,
            'plan' => $plan,
            'notes' => $notes,
            'requested_by_user' => wp_get_current_user()->user_login ?: 'system',
            'requested_at' => current_time('mysql'),
            'unit_id' => $unit_id,
            'machine_id' => $machine_id,
            'unit_id_norm' => $unit_norm,
            'machine_id_norm' => $mac_norm,
        ];
        // Enqueue for both machine and unit (best-effort)
        if (!empty($machine_id)) {
            tmon_admin_enqueue_provision($machine_id, $payload);
            error_log("tmon-admin: inline provisioning enqueued for machine_id={$machine_id} payload_keys=".(isset($payload['machine_id'])? 'yes':'no') . ',' . (isset($payload['unit_id']) ? 'yes':'no'));
        }
        if (!empty($unit_id) && $unit_id !== $machine_id) {
            tmon_admin_enqueue_provision($unit_id, $payload);
            error_log("tmon-admin: inline provisioning enqueued for unit_id={$unit_id} payload_keys=".(isset($payload['machine_id'])? 'yes':'no') . ',' . (isset($payload['unit_id']) ? 'yes':'no'));
        }
        // Mirror to tmon_devices if present
        $dev_table = $wpdb->prefix . 'tmon_devices';
        if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $dev_table))) {
            $dev_cols = $wpdb->get_col("SHOW COLUMNS FROM {$dev_table}");
            $mirror = ['last_seen' => current_time('mysql')];
            if (in_array('provisioned', $dev_cols)) $mirror['provisioned'] = 1; else $mirror['status'] = 'provisioned';
            if (!empty($payload['site_url']) && in_array('site_url', $dev_cols)) $mirror['site_url'] = $payload['site_url'];
            if (!empty($payload['site_url']) && in_array('wordpress_api_url', $dev_cols)) $mirror['wordpress_api_url'] = $payload['site_url'];
            if (!empty($payload['unit_name']) && in_array('unit_name', $dev_cols)) $mirror['unit_name'] = $payload['unit_name'];
            if (in_array('provisioned_at', $dev_cols)) $mirror['provisioned_at'] = current_time('mysql');
            if (!empty($row_unit_id)) $wpdb->update($dev_table, $mirror, ['unit_id' => $row_unit_id]);
            elseif (!empty($row_machine_id)) $wpdb->update($dev_table, $mirror, ['machine_id' => $row_machine_id]);
        }
        // Attempt push to UC site
        if (!empty($site_url)) {
            tmon_admin_push_to_uc_site($row_unit_id, $site_url, $role, $row_tmp['unit_name'] ?? $row_unit_id, intval($company_id ?? 0), null, null, $firmware, $firmware_url);
        }
    }

    // --- Redirect-after-POST (restored) ---
    $redirect_url = wp_get_referer();
    if (!$redirect_url) {
        $redirect_url = admin_url('admin.php?page=tmon-admin-provisioning');
    }
    // ensure clean provision param
    $redirect_url = remove_query_arg('provision', $redirect_url);

    if ($save_provision) {
        // If site_url provided we attempted UC push; mark queued-notified, else queued
        $status = !empty($site_url) ? 'queued-notified' : 'queued';
        wp_safe_redirect(add_query_arg('provision', $status, $redirect_url));
    } else {
        wp_safe_redirect(add_query_arg('provision', 'success', $redirect_url));
    }
    exit;
});
