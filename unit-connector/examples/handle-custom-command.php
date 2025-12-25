<?php
/**
 * Example: Extend UC device command handler to support a custom command.
 */

add_action('rest_api_init', function(){
    register_rest_route('tmon/v1', '/device/custom-command', [
        'methods' => 'POST',
        'permission_callback' => function(){
            // Allow with admin OR hub key OR read token (choose your model)
            return current_user_can('manage_options') || !empty($_SERVER['HTTP_X_TMON_HUB']);
        },
        'callback' => function(WP_REST_Request $req){
            $unit_id = sanitize_text_field($req->get_param('unit_id'));
            $command = sanitize_text_field($req->get_param('command'));
            $params = (array) $req->get_param('params');
            // Example custom action: queue a blink_led command for the device
            global $wpdb;
            $table = $wpdb->prefix . 'tmon_device_commands';
            $wpdb->insert($table, [
                'unit_id' => $unit_id,
                'command' => $command ?: 'blink_led',
                'params' => wp_json_encode($params ?: ['times' => 1]),
                'status' => 'queued',
            ]);
            return new WP_REST_Response(['queued' => true], 200);
        }
    ]);
});
