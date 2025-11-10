<?php
/**
 * Plugin Name: TMON Admin (Core Hub)
 * Description: Central hub for provisioning, authorization, aggregation, suspension.
 * Version: 1.0.0
 */
if (!defined('ABSPATH')) { exit; }

// Basic REST route for device suspension (simplified)
add_action('rest_api_init', function() {
  // Per-UC last sync map endpoint
  register_rest_route('tmon-admin/v1', '/uc/last-syncs', [
    'methods' => 'GET',
    'permission_callback' => function() {
      if (current_user_can('manage_options')) return true;
      $hdrs = function_exists('getallheaders') ? getallheaders() : [];
      $admin_key = get_option('tmon_admin_uc_key');
      $sent = $hdrs['X-TMON-ADMIN'] ?? ($_SERVER['HTTP_X_TMON_ADMIN'] ?? '');
      return $admin_key && hash_equals($admin_key, (string)$sent);
    },
    'callback' => function($req) {
      $map = get_option('tmon_admin_uc_thresholds_sync_map', []);
      if (!is_array($map)) $map = [];
      // Convert to structured array sorted desc by ts
      arsort($map);
      $out = [];
      foreach ($map as $uc_id => $ts) {
        $out[] = [
          'uc_id' => $uc_id,
          'last_sync_ts' => intval($ts),
          'last_sync_iso' => $ts ? date_i18n('Y-m-d H:i:s', intval($ts)) : null,
          'age_human' => $ts ? human_time_diff(intval($ts)) . ' ago' : null,
        ];
      }
      return [ 'uc_syncs' => $out, 'count' => count($out) ];
    }
  ]);
  // Read-only thresholds/settings endpoint for firmware sync
  register_rest_route('tmon-admin/v1', '/settings/thresholds', [
    'methods' => 'GET',
    'permission_callback' => function() {
        // Allow admin user or shared key header (same key used for UC forwarding)
        if (current_user_can('manage_options')) return true;
        $hdrs = function_exists('getallheaders') ? getallheaders() : [];
        $admin_key = get_option('tmon_admin_uc_key');
        $sent = $hdrs['X-TMON-ADMIN'] ?? ($_SERVER['HTTP_X_TMON_ADMIN'] ?? '');
        return $admin_key && hash_equals($admin_key, (string)$sent);
    },
    'callback' => function($req) {
        // Return frost/heat thresholds + intervals used by firmware
        $resp = [
          'frost' => [
            'active_temp_f' => intval(get_option('tmon_frost_active_temp', 70)),
            'clear_temp_f'  => intval(get_option('tmon_frost_clear_temp', 73)),
            'lora_interval_s' => intval(get_option('tmon_frost_lora_interval', 60)),
          ],
          'heat' => [
            'active_temp_f' => intval(get_option('tmon_heat_active_temp', 90)),
            'clear_temp_f'  => intval(get_option('tmon_heat_clear_temp', 87)),
            'lora_interval_s' => intval(get_option('tmon_heat_lora_interval', 120)),
          ],
          'version' => '1.0.0'
        ];
        return $resp;
    }
  ]);
  register_rest_route('tmon-admin/v1', '/device/suspend', [
    'methods' => 'POST',
    'permission_callback' => function() { return current_user_can('manage_options'); },
    'callback' => function($req) {
      global $wpdb;
      $unit_id = sanitize_text_field($req->get_param('unit_id'));
      $suspend = $req->get_param('suspend') === '1';
      if (!$unit_id) {
        return new WP_Error('no_unit', 'Missing unit_id', ['status' => 400]);
      }
      // Table create simplified (real plugin would have activation hook)
      $table = $wpdb->prefix . 'tmon_devices';
      $wpdb->query("CREATE TABLE IF NOT EXISTS $table (
        id INT AUTO_INCREMENT PRIMARY KEY,
        unit_id VARCHAR(64) UNIQUE,
        unit_name VARCHAR(128),
        company VARCHAR(128) NULL,
        site VARCHAR(128) NULL,
        zone VARCHAR(128) NULL,
        cluster VARCHAR(128) NULL,
        last_seen DATETIME,
        suspended TINYINT(1) DEFAULT 0,
        status VARCHAR(32)
      )");
      $row = $wpdb->get_row($wpdb->prepare("SELECT * FROM $table WHERE unit_id=%s", $unit_id));
      if (!$row) {
        $wpdb->insert($table, [
          'unit_id' => $unit_id,
          'unit_name' => $unit_id,
          'last_seen' => current_time('mysql'),
          'suspended' => $suspend ? 1 : 0,
          'status' => 'ok'
        ]);
      } else {
        $wpdb->update($table, [ 'suspended' => $suspend ? 1 : 0 ], [ 'unit_id' => $unit_id ]);
      }
      return [ 'unit_id' => $unit_id, 'suspended' => $suspend ];
    }
  ]);
  // Firmware & device schema upgrade helper (idempotent)
  add_action('plugins_loaded', function(){
    global $wpdb;
    $table = $wpdb->prefix . 'tmon_devices';
    $exists = $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table));
    if ($exists) {
      $cols = $wpdb->get_results("DESCRIBE $table", ARRAY_A);
      $present = [];
      foreach ($cols as $c){ $present[$c['Field']] = true; }
      $needed = [
        'company' => 'ALTER TABLE '.$table.' ADD COLUMN company VARCHAR(128) NULL',
        'site' => 'ALTER TABLE '.$table.' ADD COLUMN site VARCHAR(128) NULL',
        'zone' => 'ALTER TABLE '.$table.' ADD COLUMN zone VARCHAR(128) NULL',
        'cluster' => 'ALTER TABLE '.$table.' ADD COLUMN cluster VARCHAR(128) NULL',
        'firmware_version' => 'ALTER TABLE '.$table.' ADD COLUMN firmware_version VARCHAR(32) NULL'
      ];
      foreach ($needed as $col => $sql){
        if (empty($present[$col])) { $wpdb->query($sql); }
      }
    }
  });
  // Read device suspension state
  register_rest_route('tmon-admin/v1', '/device/state', [
    'methods' => 'GET',
    'permission_callback' => function() {
      if (current_user_can('manage_options')) return true;
      $hdrs = function_exists('getallheaders') ? getallheaders() : [];
      $admin_key = get_option('tmon_admin_uc_key');
      $sent = $hdrs['X-TMON-ADMIN'] ?? ($_SERVER['HTTP_X_TMON_ADMIN'] ?? '');
      return $admin_key && hash_equals($admin_key, (string)$sent);
    },
    'callback' => function($req) {
      global $wpdb;
      $unit_id = sanitize_text_field($req->get_param('unit_id'));
      if (!$unit_id) return new WP_Error('no_unit','Missing unit_id',[ 'status'=>400 ]);
      $table = $wpdb->prefix . 'tmon_devices';
      $wpdb->query("CREATE TABLE IF NOT EXISTS $table (
        id INT AUTO_INCREMENT PRIMARY KEY,
        unit_id VARCHAR(64) UNIQUE,
        unit_name VARCHAR(128),
        company VARCHAR(128) NULL,
        site VARCHAR(128) NULL,
        zone VARCHAR(128) NULL,
        cluster VARCHAR(128) NULL,
        last_seen DATETIME,
        suspended TINYINT(1) DEFAULT 0,
        status VARCHAR(32)
      )");
      $row = $wpdb->get_row($wpdb->prepare("SELECT suspended FROM $table WHERE unit_id=%s", $unit_id));
      $s = $row ? (intval($row->suspended) === 1) : false;
      return [ 'unit_id' => $unit_id, 'suspended' => $s ];
    }
  ]);
  // Field data ingestion (normalized records forwarded from Unit Connector)
  register_rest_route('tmon-admin/v1', '/field-data', [
    'methods' => 'POST',
    'permission_callback' => function() {
        // Accept either admin auth (logged-in) or shared key header
        if (current_user_can('manage_options')) return true;
        $hdrs = function_exists('getallheaders') ? getallheaders() : [];
        $admin_key = get_option('tmon_admin_uc_key');
        $sent = $hdrs['X-TMON-ADMIN'] ?? ($_SERVER['HTTP_X_TMON_ADMIN'] ?? '');
        return $admin_key && hash_equals($admin_key, (string)$sent);
    },
    'callback' => function($req) {
        global $wpdb;
        $body = $req->get_json_params();
        if (!is_array($body)) return new WP_Error('invalid_body','Expected JSON object',['status'=>400]);
        $table = $wpdb->prefix . 'tmon_field_data';
        // Create table if missing (lightweight schema)
        $wpdb->query("CREATE TABLE IF NOT EXISTS $table (id BIGINT AUTO_INCREMENT PRIMARY KEY, unit_id VARCHAR(64), created_at DATETIME DEFAULT CURRENT_TIMESTAMP, data LONGTEXT)");
        $unit_id = sanitize_text_field($body['unit_id'] ?? '');
        // Upsert device record with last_seen and name
        $dev_table = $wpdb->prefix . 'tmon_devices';
        $wpdb->query("CREATE TABLE IF NOT EXISTS $dev_table (
          id INT AUTO_INCREMENT PRIMARY KEY,
          unit_id VARCHAR(64) UNIQUE,
          unit_name VARCHAR(128),
          company VARCHAR(128) NULL,
          site VARCHAR(128) NULL,
          zone VARCHAR(128) NULL,
          cluster VARCHAR(128) NULL,
          firmware_version VARCHAR(32) NULL,
          last_seen DATETIME,
          suspended TINYINT(1) DEFAULT 0,
          status VARCHAR(32)
        )");
        $unit_name = sanitize_text_field($body['name'] ?? $unit_id);
        $fw_version = '';
        if (isset($body['firmware_version'])) { $fw_version = sanitize_text_field($body['firmware_version']); }
        elseif (isset($body['FIRMWARE_VERSION'])) { $fw_version = sanitize_text_field($body['FIRMWARE_VERSION']); }
        $exists = $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $dev_table WHERE unit_id=%s", $unit_id));
        if (intval($exists) > 0) {
          $wpdb->update($dev_table, [ 'unit_name' => $unit_name, 'firmware_version' => $fw_version, 'last_seen' => current_time('mysql') ], [ 'unit_id' => $unit_id ]);
        } else {
          if (!empty($unit_id)) {
            $wpdb->insert($dev_table, [ 'unit_id' => $unit_id, 'unit_name' => $unit_name, 'firmware_version' => $fw_version, 'last_seen' => current_time('mysql'), 'suspended' => 0, 'status' => 'ok' ]);
          }
        }
        // Capture UC ID from header or payload for per-UC tracking
        $hdrs = function_exists('getallheaders') ? getallheaders() : [];
        $uc_id = isset($hdrs['X-TMON-UC']) ? $hdrs['X-TMON-UC'] : ($_SERVER['HTTP_X_TMON_UC'] ?? '');
        if (!$uc_id) {
          $uc_id = sanitize_text_field($body['uc_id'] ?? '');
        } else {
          $uc_id = sanitize_text_field($uc_id);
        }
        $wpdb->insert($table, [
            'unit_id' => $unit_id,
            'data' => wp_json_encode($body),
        ]);
    // Update global last thresholds sync time if payload contains threshold markers
    $fa = $body['frost_active_temp'] ?? ($body['FROSTWATCH_ACTIVE_TEMP'] ?? null);
    $ha = $body['heat_active_temp'] ?? ($body['HEATWATCH_ACTIVE_TEMP'] ?? null);
    if ($fa !== null || $ha !== null || !empty($body['thresholds_summary'])) {
      update_option('tmon_admin_last_thresholds_sync_ts', time());
          if ($uc_id) {
            $map = get_option('tmon_admin_uc_thresholds_sync_map', []);
            if (!is_array($map)) { $map = []; }
            $map[$uc_id] = time();
            update_option('tmon_admin_uc_thresholds_sync_map', $map);
          }
    }
        do_action('tmon_admin_receive_field_data', $unit_id, $body);
        return ['stored' => true];
    }
  ]);
  // Hierarchy skeleton endpoints (Phase 1 minimal)
  register_rest_route('tmon-admin/v1', '/hierarchy', [
    'methods' => WP_REST_Server::READABLE,
    'permission_callback' => function(){ return current_user_can('manage_options'); },
    'callback' => function($req){
      $h = get_option('tmon_admin_hierarchy', []);
      if (!is_array($h)) $h = [];
      return [ 'hierarchy' => $h, 'counts' => [
        'companies' => isset($h['companies']) ? count($h['companies']) : 0,
        'locations' => isset($h['locations']) ? count($h['locations']) : 0,
        'zones' => isset($h['zones']) ? count($h['zones']) : 0,
        'groups' => isset($h['groups']) ? count($h['groups']) : 0,
      ]];
    }
  ]);
  register_rest_route('tmon-admin/v1', '/hierarchy', [
    'methods' => WP_REST_Server::CREATABLE,
    'permission_callback' => function(){ return current_user_can('manage_options'); },
    'callback' => function($req){
      $type = sanitize_key($req->get_param('type'));
      $id = sanitize_key($req->get_param('id'));
      $name = sanitize_text_field($req->get_param('name'));
      $parent = sanitize_key($req->get_param('parent'));
      if (!$type || !$id || !$name) return new WP_Error('invalid_hierarchy','Missing type/id/name',[ 'status'=>400 ]);
      $allowed = ['company'=>'companies','location'=>'locations','zone'=>'zones','group'=>'groups'];
      if (!isset($allowed[$type])) return new WP_Error('bad_type','Invalid type',[ 'status'=>400 ]);
      $store_key = $allowed[$type];
      $h = get_option('tmon_admin_hierarchy', []);
      if (!is_array($h)) $h = [];
      if (!isset($h[$store_key])) $h[$store_key] = [];
      if (isset($h[$store_key][$id])) return new WP_Error('exists','ID already exists',[ 'status'=>409 ]);
      $entry = [ 'id'=>$id, 'name'=>$name ];
      // Link to parent lineage
      if ($type === 'location') $entry['company'] = $parent;
      if ($type === 'zone') $entry['location'] = $parent;
      if ($type === 'group') $entry['zone'] = $parent;
      $h[$store_key][$id] = $entry;
      update_option('tmon_admin_hierarchy', $h);
      return [ 'created' => true, 'entry' => $entry ];
    }
  ]);
});

// Admin menu: Devices page
add_action('admin_menu', function() {
  add_menu_page('TMON Admin', 'TMON Admin', 'manage_options', 'tmon-admin', function() {
    echo '<div class="wrap"><h1>TMON Admin Hub</h1><p>Core provisioning and telemetry hub.</p></div>';
  });
  add_submenu_page('tmon-admin', 'Devices', 'Devices', 'manage_options', 'tmon-admin-devices', function() {
    include __DIR__ . '/admin/devices.php';
  });
  // Field Data Viewer submenu
  add_submenu_page('tmon-admin', 'Field Data Viewer', 'Field Data Viewer', 'manage_options', 'tmon-admin-field-data-viewer', function(){
      global $wpdb;
      $table = $wpdb->prefix . 'tmon_field_data';
      $wpdb->query("CREATE TABLE IF NOT EXISTS $table (id BIGINT AUTO_INCREMENT PRIMARY KEY, unit_id VARCHAR(64), created_at DATETIME DEFAULT CURRENT_TIMESTAMP, data LONGTEXT)");
      // Viewer with filters (unit, date range) + pagination
      $unit_filter = isset($_GET['unit_id']) ? sanitize_text_field($_GET['unit_id']) : '';
      $start = isset($_GET['start']) ? sanitize_text_field($_GET['start']) : '';
      $end = isset($_GET['end']) ? sanitize_text_field($_GET['end']) : '';
      $page = isset($_GET['paged']) ? max(1, intval($_GET['paged'])) : 1;
      $per_page = isset($_GET['per_page']) ? max(1, min(500, intval($_GET['per_page']))) : 100;
      $offset = ($page - 1) * $per_page;

      $conditions = [];
      $params = [];
      if ($unit_filter !== '') { $conditions[] = 'unit_id = %s'; $params[] = $unit_filter; }
      if ($start !== '') { $conditions[] = 'created_at >= %s'; $params[] = $start; }
      if ($end !== '') { $conditions[] = 'created_at <= %s'; $params[] = $end; }
      $where = $conditions ? ('WHERE ' . implode(' AND ', $conditions)) : '';

      // Count
      if ($params) {
        $count_sql = call_user_func_array([$wpdb,'prepare'], array_merge(["SELECT COUNT(*) FROM $table $where"], $params));
        $total = intval($wpdb->get_var($count_sql));
      } else {
        $total = intval($wpdb->get_var("SELECT COUNT(*) FROM $table"));
      }
      // CSV export
      if (isset($_GET['export_csv']) && $_GET['export_csv'] == '1') {
        // Build rows for export using same filters
        if ($params) {
          $select_sql = call_user_func_array([$wpdb,'prepare'], array_merge(["SELECT * FROM $table $where ORDER BY id DESC"], $params));
        } else {
          $select_sql = "SELECT * FROM $table ORDER BY id DESC";
        }
        $rows = $wpdb->get_results($select_sql, ARRAY_A);
        header('Content-Type: text/csv');
        header('Content-Disposition: attachment; filename="tmon_field_data_export.csv"');
        $out = fopen('php://output', 'w');
        fputcsv($out, ['id','created_at','unit_id','temp_f','humidity','pressure','voltage','origin','thresholds']);
        foreach ($rows as $r) {
          $d = json_decode($r['data'], true);
          if (!is_array($d)) $d = [];
          $origin = 'unknown';
          if (!empty($d['machine_id'])) { $origin = 'remote'; }
          elseif (!empty($d['NODE_TYPE'])) { $origin = strtolower($d['NODE_TYPE'])==='remote' ? 'remote':'base'; }
          $tf = isset($d['t_f']) ? $d['t_f'] : ($d['cur_temp_f'] ?? '');
          $hum = isset($d['hum']) ? $d['hum'] : ($d['cur_humid'] ?? '');
          $pres = isset($d['bar']) ? $d['bar'] : ($d['cur_bar_pres'] ?? '');
          $volt = isset($d['v']) ? $d['v'] : ($d['sys_voltage'] ?? '');
          $fa = $d['frost_active_temp'] ?? ($d['FROSTWATCH_ACTIVE_TEMP'] ?? '');
          $fc = $d['frost_clear_temp'] ?? ($d['FROSTWATCH_CLEAR_TEMP'] ?? '');
          $ha = $d['heat_active_temp'] ?? ($d['HEATWATCH_ACTIVE_TEMP'] ?? '');
          $hc = $d['heat_clear_temp'] ?? ($d['HEATWATCH_CLEAR_TEMP'] ?? '');
          $thr = "F:{$fa}/{$fc};H:{$ha}/{$hc}";
          fputcsv($out, [intval($r['id']), $r['created_at'], $r['unit_id'], $tf, $hum, $pres, $volt, $origin, $thr]);
        }
        fclose($out);
        exit;
      }
      // Rows
      if ($params) {
        $select_sql = call_user_func_array([$wpdb,'prepare'], array_merge(["SELECT * FROM $table $where ORDER BY id DESC LIMIT %d OFFSET %d"], $params, [$per_page, $offset]));
      } else {
        $select_sql = $wpdb->prepare("SELECT * FROM $table ORDER BY id DESC LIMIT %d OFFSET %d", $per_page, $offset);
      }
      $rows = $wpdb->get_results($select_sql, ARRAY_A);
      $total_pages = max(1, ceil($total / $per_page));
  echo '<div class="wrap"><h1>Field Data Viewer</h1>';
      // Show last thresholds sync time (global)
      $last_thr_ts = intval(get_option('tmon_admin_last_thresholds_sync_ts', 0));
      if ($last_thr_ts > 0) {
        echo '<p><strong>Last thresholds sync:</strong> '.esc_html(date_i18n('Y-m-d H:i:s', $last_thr_ts)).' ('.esc_html(human_time_diff($last_thr_ts)).' ago)</p>';
      } else {
        echo '<p><strong>Last thresholds sync:</strong> Never</p>';
      }
      // Per-UC last sync table
      $map = get_option('tmon_admin_uc_thresholds_sync_map', []);
      if (is_array($map) && !empty($map)) {
        // sort by latest first
        arsort($map);
        echo '<h3>Per-Unit Connector Last Sync</h3>';
        echo '<table class="widefat"><thead><tr><th>UC ID</th><th>Last Sync</th><th>Age</th></tr></thead><tbody>';
        foreach ($map as $ucid => $ts) {
          $ts_i = intval($ts);
          $when = $ts_i ? date_i18n('Y-m-d H:i:s', $ts_i) : 'Never';
          $age = $ts_i ? human_time_diff($ts_i) . ' ago' : '';
          echo '<tr><td>'.esc_html($ucid).'</td><td>'.esc_html($when).'</td><td>'.esc_html($age).'</td></tr>';
        }
        echo '</tbody></table>';
        echo '<p><em>UC ID best practices:</em> Use a short, unique identifier per Unit Connector site (e.g., <code>uc-east-1</code>). Avoid spaces, prefer lowercase, and rotate only when migrating to a new UC instance.</p>';
      }
      echo '<form method="get" style="margin-bottom:15px;">';
      echo '<input type="hidden" name="page" value="tmon-admin-field-data-viewer" />';
      echo '<label>Unit ID: <input type="text" name="unit_id" value="'.esc_attr($unit_filter).'" /></label> ';
      echo '<label>Start (YYYY-MM-DD HH:MM:SS): <input type="text" name="start" placeholder="2025-01-01 00:00:00" value="'.esc_attr($start).'" /></label> ';
      echo '<label>End (YYYY-MM-DD HH:MM:SS): <input type="text" name="end" placeholder="2025-12-31 23:59:59" value="'.esc_attr($end).'" /></label> ';
      echo '<label>Per Page: <input style="width:80px" type="number" name="per_page" value="'.esc_attr($per_page).'" /></label> ';
      echo '<input type="submit" class="button" value="Filter" />';
      echo '</form>';
      echo '<p>Total records: '.esc_html($total).' | Page '.esc_html($page).' of '.esc_html($total_pages).'</p>';
      if (!$rows) { echo '<p><em>No data found.</em></p></div>'; return; }
  echo '<table class="widefat"><thead><tr><th>ID</th><th>Created</th><th>Unit</th><th>Temp F</th><th>Humidity</th><th>Pressure</th><th>Voltage</th><th>Origin</th><th>Firmware</th><th>Suspended</th><th>Status</th><th>Thresholds</th></tr></thead><tbody>';
      foreach ($rows as $r) {
          $d = json_decode($r['data'], true);
          if (!is_array($d)) $d = [];
          $origin = 'unknown';
          if (!empty($d['machine_id'])) { $origin = 'remote'; }
          elseif (!empty($d['NODE_TYPE'])) { $origin = strtolower($d['NODE_TYPE'])==='remote' ? 'remote':'base'; }
          $tf = isset($d['t_f']) ? $d['t_f'] : ($d['cur_temp_f'] ?? '');
          $hum = isset($d['hum']) ? $d['hum'] : ($d['cur_humid'] ?? '');
          $pres = isset($d['bar']) ? $d['bar'] : ($d['cur_bar_pres'] ?? '');
          $volt = isset($d['v']) ? $d['v'] : ($d['sys_voltage'] ?? '');
      $thr = '';
      $fa = $d['frost_active_temp'] ?? ($d['FROSTWATCH_ACTIVE_TEMP'] ?? null);
      $fc = $d['frost_clear_temp'] ?? ($d['FROSTWATCH_CLEAR_TEMP'] ?? null);
      $fi = $d['frost_interval_s'] ?? ($d['FROSTWATCH_LORA_INTERVAL'] ?? null);
      $ha = $d['heat_active_temp'] ?? ($d['HEATWATCH_ACTIVE_TEMP'] ?? null);
      $hc = $d['heat_clear_temp'] ?? ($d['HEATWATCH_CLEAR_TEMP'] ?? null);
      $hi = $d['heat_interval_s'] ?? ($d['HEATWATCH_LORA_INTERVAL'] ?? null);
      if ($fa || $ha) {
      $thr = 'F:' . esc_html((string)$fa) . '/' . esc_html((string)$fc) . ' (' . esc_html((string)$fi) . 's) ' .
           'H:' . esc_html((string)$ha) . '/' . esc_html((string)$hc) . ' (' . esc_html((string)$hi) . 's)';
      }
          $fw = isset($d['firmware_version']) ? $d['firmware_version'] : (isset($d['FIRMWARE_VERSION']) ? $d['FIRMWARE_VERSION'] : '');
          $susp = '';
          if (isset($d['device_suspended'])) {
            $susp = $d['device_suspended'] ? '<span style="color:#c00;font-weight:bold">Yes</span>' : 'No';
          } elseif (isset($d['UNIT_SUSPENDED'])) {
            $susp = $d['UNIT_SUSPENDED'] ? '<span style="color:#c00;font-weight:bold">Yes</span>' : 'No';
          }
          echo '<tr>';
          // Device status lookup
          $dev_table = $wpdb->prefix . 'tmon_devices';
          $dev_row = $wpdb->get_row($wpdb->prepare("SELECT suspended, status, firmware_version FROM $dev_table WHERE unit_id=%s", $r['unit_id']), ARRAY_A);
          $status_label = $dev_row && !empty($dev_row['status']) ? esc_html($dev_row['status']) : '';
          echo '<td>'.intval($r['id']).'</td><td>'.esc_html($r['created_at']).'</td><td><a href="'.esc_url(add_query_arg('detail_unit', urlencode($r['unit_id']), admin_url('admin.php?page=tmon-admin-field-data-viewer'))).'" title="View details">'.esc_html($r['unit_id']).'</a></td>';
          echo '<td>'.esc_html($tf).'</td><td>'.esc_html($hum).'</td><td>'.esc_html($pres).'</td><td>'.esc_html($volt).'</td><td>'.esc_html($origin).'</td><td>'.esc_html($fw).'</td><td>'.$susp.'</td><td>'.$status_label.'</td><td>'.$thr.'</td>';
          echo '</tr>';
      }
      echo '</tbody></table>';
      if ($total_pages > 1) {
        $base_url = admin_url('admin.php?page=tmon-admin-field-data-viewer');
        if ($unit_filter !== '') $base_url = add_query_arg('unit_id', urlencode($unit_filter), $base_url);
        $base_url = add_query_arg('per_page', $per_page, $base_url);
        echo '<div class="tablenav"><div class="tablenav-pages">';
        for ($p=1; $p <= $total_pages; $p++) {
          $link = add_query_arg('paged', $p, $base_url);
          $class = $p === $page ? ' class="current-page"' : '';
          echo '<a'.$class.' style="margin-right:4px" href="'.esc_url($link).'">'.intval($p).'</a>';
        }
        echo '</div></div>';
      }
      echo '</div>';
  });
});

// Devices admin page enhancements (bulk suspend + detail view)
add_action('admin_init', function(){
  if (!is_admin()) return;
  if (!current_user_can('manage_options')) return;
  global $wpdb;
  $table = $wpdb->prefix . 'tmon_devices';
  // Bulk action
  if (isset($_POST['tmon_bulk_suspend']) && check_admin_referer('tmon_bulk_suspend_action')) {
    $ids = isset($_POST['tmon_units']) && is_array($_POST['tmon_units']) ? array_map('sanitize_text_field', $_POST['tmon_units']) : [];
    $mode = sanitize_text_field($_POST['bulk_mode'] ?? 'suspend');
    foreach ($ids as $uid){
      if (!$uid) continue;
      $wpdb->update($table, ['suspended' => $mode==='suspend'?1:0], ['unit_id' => $uid]);
    }
    wp_redirect(add_query_arg('bulk_done','1', admin_url('admin.php?page=tmon-admin-devices')));
    exit;
  }
});

// Cron: mark stale/offline
add_action('init', function(){
  if (!wp_next_scheduled('tmon_admin_cron_health')) {
    wp_schedule_event(time()+300, 'five_minutes', 'tmon_admin_cron_health');
  }
});
add_filter('cron_schedules', function($s){
  if (!isset($s['five_minutes'])){
    $s['five_minutes'] = ['interval' => 300, 'display' => 'Every 5 Minutes'];
  }
  return $s;
});
add_action('tmon_admin_cron_health', function(){
  global $wpdb;
  $table = $wpdb->prefix . 'tmon_devices';
  $threshold_stale = time() - 600; // 10 min
  $threshold_offline = time() - 3600; // 60 min
  $rows = $wpdb->get_results("SELECT unit_id, UNIX_TIMESTAMP(last_seen) AS ls FROM $table", ARRAY_A);
  foreach ($rows as $r){
    $ls = intval($r['ls']);
    $status = 'ok';
    if ($ls < $threshold_offline) {
      $status = 'offline';
    } elseif ($ls < $threshold_stale) {
      $status = 'stale';
    }
    $wpdb->update($table, ['status' => $status], ['unit_id' => $r['unit_id']]);
  }
});
