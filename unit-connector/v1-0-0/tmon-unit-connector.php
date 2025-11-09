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
    'permission_callback' => '__return_true', // real plugin would verify key/header
    'callback' => function($req) {
      $data = $req->get_json_params();
      // TODO: Normalize and forward to Admin hub (simplified placeholder)
      do_action('tmon_uc_receive_field_data', $data);
      return ['ok' => true];
    }
  ]);
});
