<?php
/**
 * Plugin Name: TMON Admin (Core Hub)
 * Description: Central hub for provisioning, authorization, aggregation, suspension.
 * Version: 1.0.0
 */
if (!defined('ABSPATH')) { exit; }

// Basic REST route for device suspension (simplified)
add_action('rest_api_init', function() {
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
});

// Admin menu: Devices page
add_action('admin_menu', function() {
  add_menu_page('TMON Admin', 'TMON Admin', 'manage_options', 'tmon-admin', function() {
    echo '<div class="wrap"><h1>TMON Admin Hub</h1><p>Core provisioning and telemetry hub.</p></div>';
  });
  add_submenu_page('tmon-admin', 'Devices', 'Devices', 'manage_options', 'tmon-admin-devices', function() {
    include __DIR__ . '/admin/devices.php';
  });
});
