<?php
/**
 * Plugin Name: TMON Unit Connector
 * Description: Receives device field data and forwards to Admin hub.
 * Version: 1.0.0
 */
if (!defined('ABSPATH')) { exit; }

add_action('rest_api_init', function() {
  register_rest_route('tmon/v1', '/device/field-data', [
    'methods' => 'POST',
    'permission_callback' => '__return_true', // Replace with key/header auth
    'callback' => function($req) {
      $data = $req->get_json_params();
      if (!is_array($data)) {
        return new WP_Error('invalid_payload','Expected JSON object',['status'=>400]);
      }
      // Basic normalization of remote-style payload
      $norm = [
        'unit_id' => $data['unit_id'] ?? '',
        'machine_id' => $data['machine_id'] ?? ($data['mid'] ?? ''),
        'name' => $data['name'] ?? '',
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

      // Store locally (simplified; real implementation would use custom table)
      do_action('tmon_uc_receive_field_data', $norm);

      // Optional forward to Admin hub if configured
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
          // Log lightweight failure; avoid noisy fatal
          do_action('tmon_uc_forward_error', $norm['unit_id'], $resp->get_error_message());
        } else {
          do_action('tmon_uc_forward_success', $norm['unit_id'], wp_remote_retrieve_response_code($resp));
        }
      }
      return ['ok' => true];
    }
  ]);
});

