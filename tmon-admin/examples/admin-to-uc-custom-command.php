<?php
/**
 * Example: From TMON Admin, send a custom command to a Unit Connector.
 * - On UC, you should implement a /device/command handler that accepts { unit_id, command, params }
 */

function tmon_admin_send_custom_command_to_uc($site_url, $unit_id, $command, $params = []){
    $endpoint = rtrim($site_url, '/') . '/wp-json/tmon/v1/device/command';
    $payload = [ 'unit_id' => $unit_id, 'command' => $command, 'params' => $params ];
    $headers = [ 'Content-Type' => 'application/json' ];
    // Optionally include an auth header if your UC expects it, e.g. a hub key
    $hub_key = get_option('tmon_admin_hub_shared_key');
    if ($hub_key) { $headers['X-TMON-HUB'] = $hub_key; }
    $resp = wp_remote_post($endpoint, [
        'timeout' => 20,
        'headers' => $headers,
        'body' => wp_json_encode($payload),
    ]);
    if (is_wp_error($resp)) return $resp;
    $code = wp_remote_retrieve_response_code($resp);
    $body = json_decode(wp_remote_retrieve_body($resp), true);
    return [ 'code' => $code, 'body' => $body ];
}

// Usage:
// $res = tmon_admin_send_custom_command_to_uc('https://uc.example.com', '170170', 'blink_led', ['times' => 3]);
// error_log(print_r($res, true));
