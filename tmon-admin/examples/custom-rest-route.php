<?php
/**
 * Example: Add a simple REST route under /wp-json/tmon/v1/example.
 */

add_action('rest_api_init', function(){
    register_rest_route('tmon/v1', '/example', [
        'methods' => 'GET',
        'permission_callback' => function(){ return current_user_can('manage_options'); },
        'callback' => function(WP_REST_Request $req){
            $name = sanitize_text_field($req->get_param('name')) ?: 'world';
            return new WP_REST_Response(['message' => 'Hello, ' . $name], 200);
        }
    ]);
});
