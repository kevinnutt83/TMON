<?php
/**
 * Plugin Name: TMON Admin (Core Hub)
 * Description: Central hub for provisioning, authorization, aggregation, suspension.
 * Version: 1.0.0
 */
if (!defined('ABSPATH')) { exit; }

// Basic REST route for device suspension (simplified)
add_action('rest_api_init', function() {
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
      $wpdb->query("CREATE TABLE IF NOT EXISTS $table (id INT AUTO_INCREMENT PRIMARY KEY, unit_id VARCHAR(64) UNIQUE, unit_name VARCHAR(128), last_seen DATETIME, suspended TINYINT(1) DEFAULT 0, status VARCHAR(32))");
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
        $wpdb->insert($table, [
            'unit_id' => $unit_id,
            'data' => wp_json_encode($body),
        ]);
        do_action('tmon_admin_receive_field_data', $unit_id, $body);
        return ['stored' => true];
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
        // Build rows again (we already have $rows) and output CSV
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
    echo '<table class="widefat"><thead><tr><th>ID</th><th>Created</th><th>Unit</th><th>Temp F</th><th>Humidity</th><th>Pressure</th><th>Voltage</th><th>Origin</th><th>Thresholds</th></tr></thead><tbody>';
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
          echo '<tr>';
      echo '<td>'.intval($r['id']).'</td><td>'.esc_html($r['created_at']).'</td><td>'.esc_html($r['unit_id']).'</td>';
      echo '<td>'.esc_html($tf).'</td><td>'.esc_html($hum).'</td><td>'.esc_html($pres).'</td><td>'.esc_html($volt).'</td><td>'.esc_html($origin).'</td><td>'.$thr.'</td>';
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
