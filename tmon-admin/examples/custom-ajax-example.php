<?php
/**
 * Example: Add a secure admin-ajax handler in a plugin file.
 */

add_action('wp_ajax_tmon_example_echo', function(){
    if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'forbidden'], 403);
    $nonce = isset($_GET['nonce']) ? sanitize_text_field(wp_unslash($_GET['nonce'])) : '';
    if (!wp_verify_nonce($nonce, 'tmon_example_echo')) wp_send_json_error(['message' => 'bad_nonce'], 403);
    $msg = isset($_GET['msg']) ? sanitize_text_field(wp_unslash($_GET['msg'])) : '';
    wp_send_json_success(['echo' => $msg]);
});

// Usage (JS):
// const url = ajaxurl + '?action=tmon_example_echo&nonce=' + nonce + '&msg=' + encodeURIComponent('Hello');
// fetch(url).then(r=>r.json()).then(console.log);
