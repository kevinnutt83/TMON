<?php
/**
 * Plugin Name: TMON Unit Connector
 * Description: Receives device field data and forwards to Admin hub.
 * Version: 1.0.0
 */
if (!defined('ABSPATH')) { exit; }

// Helper: normalize a single payload for reuse and unit tests
if (!function_exists('tmon_uc_normalize_payload')) {
  function tmon_uc_normalize_payload($data, $defaults = []) {
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
    // Firmware version and suspension state passthrough when present
    if (isset($data['FIRMWARE_VERSION']) || isset($data['firmware_version'])) {
      $norm['firmware_version'] = $data['FIRMWARE_VERSION'] ?? $data['firmware_version'];
    }
    if (isset($data['UNIT_SUSPENDED']) || isset($data['device_suspended'])) {
      $norm['device_suspended'] = isset($data['UNIT_SUSPENDED']) ? (bool)$data['UNIT_SUSPENDED'] : (bool)$data['device_suspended'];
    }
    // Surface applied thresholds if present
    $norm['frost_active_temp'] = $data['FROSTWATCH_ACTIVE_TEMP'] ?? ($data['frost_active_temp'] ?? null);
    $norm['frost_clear_temp']  = $data['FROSTWATCH_CLEAR_TEMP'] ?? ($data['frost_clear_temp'] ?? null);
    $norm['frost_interval_s']  = $data['FROSTWATCH_LORA_INTERVAL'] ?? ($data['frost_interval_s'] ?? null);
    $norm['heat_active_temp']  = $data['HEATWATCH_ACTIVE_TEMP'] ?? ($data['heat_active_temp'] ?? null);
    $norm['heat_clear_temp']   = $data['HEATWATCH_CLEAR_TEMP'] ?? ($data['heat_clear_temp'] ?? null);
    $norm['heat_interval_s']   = $data['HEATWATCH_LORA_INTERVAL'] ?? ($data['heat_interval_s'] ?? null);
    // Compact thresholds summary
    if ($norm['frost_active_temp'] !== null || $norm['heat_active_temp'] !== null) {
      $fA = $norm['frost_active_temp'];
      $fC = $norm['frost_clear_temp'];
      $fI = $norm['frost_interval_s'];
      $hA = $norm['heat_active_temp'];
      $hC = $norm['heat_clear_temp'];
      $hI = $norm['heat_interval_s'];
      $norm['thresholds_summary'] = 'F:' . ($fA ?? '-') . '/' . ($fC ?? '-') . '/' . ($fI ?? '-') . ';H:' . ($hA ?? '-') . '/' . ($hC ?? '-') . '/' . ($hI ?? '-');
    } else {
      $norm['thresholds_summary'] = null;
    }
    return $norm;
  }
}

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
      // include last_sync metadata when returning cached
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
        // Cache short TTL (configurable, minutes)
        $ttl_minutes = intval(get_option('tmon_uc_threshold_cache_ttl', 5));
        $ttl_seconds = max(30, $ttl_minutes * 60);
        $wrapped = ['payload' => $json, 'last_sync' => time()];
        set_transient($cache_key, $wrapped, $ttl_seconds);
        return $wrapped;
  }
  ]);
  // Flush thresholds cache (admin-only)
  register_rest_route('tmon/v1', '/admin/thresholds/flush', [
    'methods' => 'POST',
    'permission_callback' => function() { return current_user_can('manage_options'); },
    'callback' => function($req) {
      delete_transient('tmon_uc_thresholds_cache');
      return ['flushed' => true];
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
        if (isset($data['FIRMWARE_VERSION']) || isset($data['firmware_version'])) {
          $norm['firmware_version'] = $data['FIRMWARE_VERSION'] ?? $data['firmware_version'];
        }
        if (isset($data['UNIT_SUSPENDED']) || isset($data['device_suspended'])) {
          $norm['device_suspended'] = isset($data['UNIT_SUSPENDED']) ? (bool)$data['UNIT_SUSPENDED'] : (bool)$data['device_suspended'];
        }
        // Surface applied thresholds if present
        $norm['frost_active_temp'] = $data['FROSTWATCH_ACTIVE_TEMP'] ?? ($data['frost_active_temp'] ?? null);
        $norm['frost_clear_temp']  = $data['FROSTWATCH_CLEAR_TEMP'] ?? ($data['frost_clear_temp'] ?? null);
        $norm['frost_interval_s']  = $data['FROSTWATCH_LORA_INTERVAL'] ?? ($data['frost_interval_s'] ?? null);
        $norm['heat_active_temp']  = $data['HEATWATCH_ACTIVE_TEMP'] ?? ($data['heat_active_temp'] ?? null);
        $norm['heat_clear_temp']   = $data['HEATWATCH_CLEAR_TEMP'] ?? ($data['heat_clear_temp'] ?? null);
        $norm['heat_interval_s']   = $data['HEATWATCH_LORA_INTERVAL'] ?? ($data['heat_interval_s'] ?? null);
        // Compact thresholds summary string (for quick display/debug)
        if ($norm['frost_active_temp'] !== null || $norm['heat_active_temp'] !== null) {
          $fA = $norm['frost_active_temp'];
          $fC = $norm['frost_clear_temp'];
          $fI = $norm['frost_interval_s'];
          $hA = $norm['heat_active_temp'];
          $hC = $norm['heat_clear_temp'];
          $hI = $norm['heat_interval_s'];
          $norm['thresholds_summary'] = 'F:' . ($fA ?? '-') . '/' . ($fC ?? '-') . '/' . ($fI ?? '-') . ';H:' . ($hA ?? '-') . '/' . ($hC ?? '-') . '/' . ($hI ?? '-');
        } else {
          $norm['thresholds_summary'] = null;
        }

        // Store locally and forward
        do_action('tmon_uc_receive_field_data', $norm);

        $admin_url = get_option('tmon_uc_admin_url');
        $admin_key = get_option('tmon_uc_admin_key');
        $uc_id = get_option('tmon_uc_id', '');
        if ($admin_url && $admin_key && wp_http_validate_url($admin_url)) {
          $endpoint = rtrim($admin_url,'/') . '/wp-json/tmon-admin/v1/field-data';
          $args = [
            'timeout' => 10,
            'headers' => [
              'Content-Type' => 'application/json',
              'X-TMON-ADMIN' => $admin_key,
              // Identify this Unit Connector to Admin
              'X-TMON-UC' => $uc_id ? $uc_id : 'default'
            ],
            // Also embed UC id inside payload for redundancy
            'body' => wp_json_encode($uc_id ? array_merge($norm, ['uc_id' => $uc_id]) : $norm),
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
        // Ask Admin for suspension state (batch uses outer unit_id)
        $suspended = false;
        $admin_url = get_option('tmon_uc_admin_url');
        $admin_key = get_option('tmon_uc_admin_key');
        if ($admin_url && $admin_key && $defaults['unit_id']) {
          $endpoint = rtrim($admin_url,'/') . '/wp-json/tmon-admin/v1/device/state?unit_id=' . urlencode($defaults['unit_id']);
          $resp2 = wp_remote_get($endpoint, [ 'timeout' => 8, 'headers' => [ 'X-TMON-ADMIN' => $admin_key ]]);
          if (!is_wp_error($resp2) && wp_remote_retrieve_response_code($resp2) === 200) {
            $st = json_decode(wp_remote_retrieve_body($resp2), true);
            if (is_array($st) && array_key_exists('suspended', $st)) { $suspended = !empty($st['suspended']); }
          }
        }
        return ['ok' => true, 'count' => count($payload['data']), 'device_suspended' => $suspended];
      }

      // Single record path
      $process_one($payload, []);
      // Single record: check suspension for this unit
      $suspended = false;
      $admin_url = get_option('tmon_uc_admin_url');
      $admin_key = get_option('tmon_uc_admin_key');
      $uid = is_array($payload) ? ($payload['unit_id'] ?? '') : '';
      if ($admin_url && $admin_key && $uid) {
        $endpoint = rtrim($admin_url,'/') . '/wp-json/tmon-admin/v1/device/state?unit_id=' . urlencode($uid);
        $resp2 = wp_remote_get($endpoint, [ 'timeout' => 8, 'headers' => [ 'X-TMON-ADMIN' => $admin_key ]]);
        if (!is_wp_error($resp2) && wp_remote_retrieve_response_code($resp2) === 200) {
          $st = json_decode(wp_remote_retrieve_body($resp2), true);
          if (is_array($st) && array_key_exists('suspended', $st)) { $suspended = !empty($st['suspended']); }
        }
      }
      return ['ok' => true, 'count' => 1, 'device_suspended' => $suspended];
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
          update_option('tmon_uc_id', sanitize_text_field($_POST['tmon_uc_id'] ?? ''));
          // Cache TTL option
          update_option('tmon_uc_threshold_cache_ttl', intval($_POST['tmon_uc_threshold_cache_ttl'] ?? 5));
          // Clear thresholds cache on settings change
          delete_transient('tmon_uc_thresholds_cache');
          echo '<div class="updated"><p>Settings saved.</p></div>';
        }
        // Manual flush action
        if (isset($_POST['tmon_uc_flush_cache']) && check_admin_referer('tmon_uc_settings_flush')) {
          delete_transient('tmon_uc_thresholds_cache');
          echo '<div class="updated"><p>Thresholds cache flushed.</p></div>';
        }
        // Suspension status check
        $susp_unit = '';
        $susp_state = null;
        if (isset($_POST['tmon_uc_check_suspend']) && check_admin_referer('tmon_uc_settings_suspend')) {
          $susp_unit = sanitize_text_field($_POST['susp_unit_id'] ?? '');
          $admin_url_chk = get_option('tmon_uc_admin_url');
          $admin_key_chk = get_option('tmon_uc_admin_key');
          if ($susp_unit && $admin_url_chk && $admin_key_chk) {
            $endpoint = rtrim($admin_url_chk,'/') . '/wp-json/tmon-admin/v1/device/state?unit_id=' . urlencode($susp_unit);
            $resp = wp_remote_get($endpoint, [ 'timeout' => 10, 'headers' => [ 'X-TMON-ADMIN' => $admin_key_chk ] ]);
            if (!is_wp_error($resp) && wp_remote_retrieve_response_code($resp) === 200) {
              $st = json_decode(wp_remote_retrieve_body($resp), true);
              if (is_array($st) && array_key_exists('suspended',$st)) {
                $susp_state = !empty($st['suspended']);
              }
            } else {
              echo '<div class="notice notice-error"><p>Failed to query Admin for suspension state.</p></div>';
            }
          }
        }
        $admin_url = esc_url(get_option('tmon_uc_admin_url',''));
        $admin_key = esc_html(get_option('tmon_uc_admin_key',''));
  $device_key = esc_html(get_option('tmon_uc_device_key',''));
  $uc_id = esc_html(get_option('tmon_uc_id',''));
        $ttl = intval(get_option('tmon_uc_threshold_cache_ttl', 5));
        $cached = get_transient('tmon_uc_thresholds_cache');
        $last_sync_ts = is_array($cached) ? ($cached['last_sync'] ?? null) : null;
        $last_sync_human = $last_sync_ts ? date_i18n('Y-m-d H:i:s', $last_sync_ts) : 'Never';
        $age_str = '';
        if ($last_sync_ts) {
          $diff = time() - $last_sync_ts;
          $age_str = ' ('.human_time_diff($last_sync_ts).' ago)';
        }
        echo '<div class="wrap"><h1>TMON Unit Connector Settings</h1><form method="post">';
        wp_nonce_field('tmon_uc_settings_save');
  echo '<table class="form-table"><tr><th scope="row"><label for="tmon_uc_admin_url">Admin Hub URL</label></th><td><input type="url" name="tmon_uc_admin_url" id="tmon_uc_admin_url" class="regular-text" value="'.$admin_url.'" placeholder="https://admin.example.com" /></td></tr>';
        echo '<tr><th scope="row"><label for="tmon_uc_admin_key">Admin Shared Key</label></th><td><input type="text" name="tmon_uc_admin_key" id="tmon_uc_admin_key" class="regular-text" value="'.$admin_key.'" /></td></tr>';
  echo '<tr><th scope="row"><label for="tmon_uc_id">Unit Connector ID</label></th><td><input type="text" name="tmon_uc_id" id="tmon_uc_id" class="regular-text" value="'.$uc_id.'" placeholder="uc-1" /><p class="description">Used to track per-UC thresholds sync in Admin.</p></td></tr>';
        echo '<tr><th scope="row"><label for="tmon_uc_threshold_cache_ttl">Thresholds cache TTL (minutes)</label></th><td><input type="number" min="0" name="tmon_uc_threshold_cache_ttl" id="tmon_uc_threshold_cache_ttl" class="regular-text" value="'.esc_attr($ttl).'" /></td></tr>';
        echo '<tr><th scope="row"><label for="tmon_uc_device_key">Device POST Key (X-TMON-DEVICE)</label></th><td><input type="text" name="tmon_uc_device_key" id="tmon_uc_device_key" class="regular-text" value="'.$device_key.'" /></td></tr>';
        echo '</table><p><input type="submit" name="tmon_uc_save" class="button button-primary" value="Save Changes" /></p></form>';
        echo '<h2>Thresholds Cache</h2>';
        echo '<p>Last sync: <strong>'.$last_sync_human.'</strong>'.$age_str.'</p>';
        echo '<form method="post" style="margin-top:10px;">';
        wp_nonce_field('tmon_uc_settings_flush');
        echo '<p><input type="submit" name="tmon_uc_flush_cache" class="button" value="Flush Cache Now" /></p></form>';
        echo '<h2>Suspension Status Test</h2>';
        echo '<form method="post" style="margin-top:10px;">';
        wp_nonce_field('tmon_uc_settings_suspend');
        echo '<p><label for="susp_unit_id">Unit ID</label> <input type="text" name="susp_unit_id" id="susp_unit_id" value="'.esc_attr($susp_unit).'" /> ';
        echo '<input type="submit" name="tmon_uc_check_suspend" class="button" value="Check" /></p>';
        if ($susp_state !== null) {
          echo '<p>Status: '.($susp_state ? '<span style="color:#c00;font-weight:bold">Suspended</span>' : '<span style="color:#090;">Enabled</span>').'</p>';
        }
        echo '</form>';
        echo '<h2>Forwarding Status</h2><p>Records will forward when both URL and key are set.</p>';
        echo '<p>Device POSTs must include header <code>X-TMON-DEVICE</code> matching the configured Device POST Key.</p>';
        echo '</div>';
      }
    );
  });
});

