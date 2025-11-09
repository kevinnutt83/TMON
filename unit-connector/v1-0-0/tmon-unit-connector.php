<?php
/**
 * Plugin Name: TMON Unit Connector
 * Description: Receives device field data and forwards to Admin hub.
 * Version: 1.0.0
 */
if (!defined('ABSPATH')) { exit; }

add_action('rest_api_init', function() {
  // Proxy: expose Admin thresholds to devices via UC (auth by device key)
  register_rest_route('tmon/v1', '/admin/thresholds', [
  'methods' => 'GET',
  'permission_callback' => function(){
    if (current_user_can('manage_options')) return true;
    $headers = function_exists('getallheaders') ? getallheaders() : [];
    $sent = $headers['X-TMON-DEVICE'] ?? ($_SERVER['HTTP_X_TMON_DEVICE'] ?? '');
    $expected = get_option('tmon_uc_device_key');
    return $expected && hash_equals($expected, (string)$sent);
  },
  'callback' => function($req){
    $admin_url = get_option('tmon_uc_admin_url');
    $admin_key = get_option('tmon_uc_admin_key');
    if (!$admin_url || !$admin_key || !wp_http_validate_url($admin_url)) {
      return new WP_Error('uc_not_configured','Admin URL/key not set',['status'=>500]);
    }
    // Try transient cache first
    $cache_key = 'tmon_uc_thresholds_cache';
    $cached = get_transient($cache_key);
    if (is_array($cached)) {
      return $cached;
    }
    $endpoint = rtrim($admin_url,'/').'/wp-json/tmon-admin/v1/settings/thresholds';
    $resp = wp_remote_get($endpoint, [
      'timeout' => 10,
      'headers' => [ 'X-TMON-ADMIN' => $admin_key ]
    ]);
    if (is_wp_error($resp)) {
      return new WP_Error('admin_fetch_failed',$resp->get_error_message(),['status'=>502]);
    }
    $code = wp_remote_retrieve_response_code($resp);
    $body = wp_remote_retrieve_body($resp);
    $json = json_decode($body, true);
    if ($code !== 200 || !is_array($json)) {
      return new WP_Error('bad_admin_response','Unexpected Admin response',['status'=>502]);
    }
    // Cache short TTL (5 minutes)
    set_transient($cache_key, $json, 5 * MINUTE_IN_SECONDS);
    return $json;
  }
  ]);
  register_rest_route('tmon/v1', '/device/field-data', [
    'methods' => 'POST',
    'permission_callback' => function() {
        // Require shared device key header unless user is admin
        if (current_user_can('manage_options')) return true;
        $headers = function_exists('getallheaders') ? getallheaders() : [];
        $sent = $headers['X-TMON-DEVICE'] ?? ($_SERVER['HTTP_X_TMON_DEVICE'] ?? '');
        $expected = get_option('tmon_uc_device_key');
        return $expected && hash_equals($expected, (string)$sent);
    },
    'callback' => function($req) {
      $payload = $req->get_json_params();
      if (!is_array($payload)) {
        return new WP_Error('invalid_payload','Expected JSON object',["status"=>400]);
      }

      $process_one = function($data, $defaults = []){
        // Basic normalization of remote-style payload
        $norm = [
          'unit_id' => $data['unit_id'] ?? ($defaults['unit_id'] ?? ''),
          'machine_id' => $data['machine_id'] ?? ($data['mid'] ?? ($defaults['machine_id'] ?? '')),
          'name' => $data['name'] ?? ($defaults['name'] ?? ''),
          'timestamp' => $data['ts'] ?? ($data['timestamp'] ?? time()),
          'temp_f' => $data['t_f'] ?? ($data['cur_temp_f'] ?? null),
          'temp_c' => $data['t_c'] ?? ($data['cur_temp_c'] ?? null),
          'humidity' => $data['hum'] ?? ($data['cur_humid'] ?? null),
          'pressure' => $data['bar'] ?? ($data['cur_bar_pres'] ?? null),
          'voltage_v' => $data['v'] ?? ($data['sys_voltage'] ?? null),
          'free_mem' => $data['fm'] ?? ($data['free_mem'] ?? null),
          'lora_rssi' => $data['lora_SigStr'] ?? null,
          'wifi_rssi' => $data['wifi_rssi'] ?? null,
          'gps_lat' => $data['gps_lat'] ?? null,
          'gps_lng' => $data['gps_lng'] ?? null,
          'gps_alt_m' => $data['gps_alt_m'] ?? null,
          'gps_accuracy_m' => $data['gps_accuracy_m'] ?? null,
          'gps_last_fix_ts' => $data['gps_last_fix_ts'] ?? null,
        ];
        // Surface applied thresholds if present
        $norm['frost_active_temp'] = $data['FROSTWATCH_ACTIVE_TEMP'] ?? ($data['frost_active_temp'] ?? null);
        $norm['frost_clear_temp']  = $data['FROSTWATCH_CLEAR_TEMP'] ?? ($data['frost_clear_temp'] ?? null);
        $norm['frost_interval_s']  = $data['FROSTWATCH_LORA_INTERVAL'] ?? ($data['frost_interval_s'] ?? null);
        $norm['heat_active_temp']  = $data['HEATWATCH_ACTIVE_TEMP'] ?? ($data['heat_active_temp'] ?? null);
        $norm['heat_clear_temp']   = $data['HEATWATCH_CLEAR_TEMP'] ?? ($data['heat_clear_temp'] ?? null);
        $norm['heat_interval_s']   = $data['HEATWATCH_LORA_INTERVAL'] ?? ($data['heat_interval_s'] ?? null);

        // Store locally and forward
        do_action('tmon_uc_receive_field_data', $norm);

        $admin_url = get_option('tmon_uc_admin_url');
        $admin_key = get_option('tmon_uc_admin_key');
        if ($admin_url && $admin_key && wp_http_validate_url($admin_url)) {
          $endpoint = rtrim($admin_url,'/') . '/wp-json/tmon-admin/v1/field-data';
          $args = [
            'timeout' => 10,
            'headers' => [
              'Content-Type' => 'application/json',
              'X-TMON-ADMIN' => $admin_key,
            ],
            'body' => wp_json_encode($norm),
          ];
          $resp = wp_remote_post($endpoint, $args);
          if (is_wp_error($resp)) {
            do_action('tmon_uc_forward_error', $norm['unit_id'], $resp->get_error_message());
          } else {
            do_action('tmon_uc_forward_success', $norm['unit_id'], wp_remote_retrieve_response_code($resp));
          }
        }
      };

      // If batched payload with 'data' array, process each entry
      if (isset($payload['data']) && is_array($payload['data'])) {
        $defaults = [
          'unit_id' => $payload['unit_id'] ?? '',
          'machine_id' => $payload['machine_id'] ?? ($payload['mid'] ?? ''),
          'name' => $payload['name'] ?? '',
        ];
        foreach ($payload['data'] as $entry) {
          if (is_array($entry)) {
            $process_one($entry, $defaults);
          }
        }
        return ['ok' => true, 'count' => count($payload['data'])];
      }

      // Single record path
      $process_one($payload, []);
      return ['ok' => true, 'count' => 1];
    }
  ]);
  // Admin URL/Key settings page
  add_action('admin_menu', function(){
    add_submenu_page(
      'options-general.php',
      'TMON Unit Connector',
      'TMON Unit Connector',
      'manage_options',
      'tmon-unit-connector-settings',
      function(){
        if (!current_user_can('manage_options')) return;
        if (isset($_POST['tmon_uc_save']) && check_admin_referer('tmon_uc_settings_save')) {
          update_option('tmon_uc_admin_url', esc_url_raw($_POST['tmon_uc_admin_url'] ?? ''));
          update_option('tmon_uc_admin_key', sanitize_text_field($_POST['tmon_uc_admin_key'] ?? ''));
          update_option('tmon_uc_device_key', sanitize_text_field($_POST['tmon_uc_device_key'] ?? ''));
          // Clear thresholds cache on settings change
          delete_transient('tmon_uc_thresholds_cache');
          echo '<div class="updated"><p>Settings saved.</p></div>';
        }
        $admin_url = esc_url(get_option('tmon_uc_admin_url',''));
        $admin_key = esc_html(get_option('tmon_uc_admin_key',''));
        $device_key = esc_html(get_option('tmon_uc_device_key',''));
        echo '<div class="wrap"><h1>TMON Unit Connector Settings</h1><form method="post">';
        wp_nonce_field('tmon_uc_settings_save');
        echo '<table class="form-table"><tr><th scope="row"><label for="tmon_uc_admin_url">Admin Hub URL</label></th><td><input type="url" name="tmon_uc_admin_url" id="tmon_uc_admin_url" class="regular-text" value="'.$admin_url.'" placeholder="https://admin.example.com" /></td></tr>';
        echo '<tr><th scope="row"><label for="tmon_uc_admin_key">Admin Shared Key</label></th><td><input type="text" name="tmon_uc_admin_key" id="tmon_uc_admin_key" class="regular-text" value="'.$admin_key.'" /></td></tr>';
        echo '<tr><th scope="row"><label for="tmon_uc_device_key">Device POST Key (X-TMON-DEVICE)</label></th><td><input type="text" name="tmon_uc_device_key" id="tmon_uc_device_key" class="regular-text" value="'.$device_key.'" /></td></tr>';
        echo '</table><p><input type="submit" name="tmon_uc_save" class="button button-primary" value="Save Changes" /></p></form>';
        echo '<h2>Forwarding Status</h2><p>Records will forward when both URL and key are set.</p>';
        echo '<p>Device POSTs must include header <code>X-TMON-DEVICE</code> matching the configured Device POST Key.</p>';
        echo '</div>';
      }
    );
  });
});

