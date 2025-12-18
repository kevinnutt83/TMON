<?php
// AJAX handlers for Device Data admin page
add_action('wp_ajax_tmon_uc_device_bundle', function(){
    if (!current_user_can('manage_options')) {
        wp_send_json_error(['message' => 'forbidden'], 403);
    }
    check_ajax_referer('tmon_uc_device_data', 'nonce');
    $unit_id = isset($_POST['unit_id']) ? sanitize_text_field(wp_unslash($_POST['unit_id'])) : '';
    if (!$unit_id) {
        wp_send_json_error(['message' => 'unit_id required'], 400);
    }
    global $wpdb;
    $device = $wpdb->get_row($wpdb->prepare("SELECT unit_id, machine_id, unit_name, settings, last_seen FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $unit_id), ARRAY_A);
    $settings = [];
    if ($device && !empty($device['settings'])) {
        $tmp = json_decode($device['settings'], true);
        if (is_array($tmp)) { $settings = $tmp; }
    }
    $machine_id = $device['machine_id'] ?? '';
    uc_devices_ensure_table();
    $uc_table = $wpdb->prefix . 'tmon_uc_devices';
    $staged_row = $wpdb->get_row($wpdb->prepare("SELECT staged_settings, staged_at, machine_id FROM {$uc_table} WHERE unit_id=%s OR machine_id=%s LIMIT 1", $unit_id, $machine_id), ARRAY_A);
    $staged = [];
    if ($staged_row && !empty($staged_row['staged_settings'])) {
        $tmp = json_decode($staged_row['staged_settings'], true);
        if (is_array($tmp)) { $staged = $tmp; }
    }
    if (!$machine_id && $staged_row && !empty($staged_row['machine_id'])) {
        $machine_id = $staged_row['machine_id'];
    }
    $latest = $wpdb->get_row($wpdb->prepare("SELECT created_at FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s ORDER BY created_at DESC LIMIT 1", $unit_id), ARRAY_A);
    wp_send_json_success([
        'unit_id' => $unit_id,
        'machine_id' => $machine_id,
        'settings' => $settings,
        'staged' => $staged,
        'staged_at' => $staged_row['staged_at'] ?? '',
        'last_seen' => $device['last_seen'] ?? ($latest['created_at'] ?? ''),
    ]);
});

add_action('wp_ajax_tmon_uc_stage_settings', function(){
    if (!current_user_can('manage_options')) {
        wp_send_json_error(['message' => 'forbidden'], 403);
    }
    check_ajax_referer('tmon_uc_device_data', 'nonce');
    $unit_id = isset($_POST['unit_id']) ? sanitize_text_field(wp_unslash($_POST['unit_id'])) : '';
    $settings_json = isset($_POST['settings_json']) ? wp_unslash($_POST['settings_json']) : '';
    if (!$unit_id) {
        wp_send_json_error(['message' => 'unit_id required'], 400);
    }
    $decoded = null;
    if ($settings_json !== '') {
        $decoded = json_decode($settings_json, true);
        if ($decoded === null && json_last_error() !== JSON_ERROR_NONE) {
            wp_send_json_error(['message' => 'Invalid JSON payload'], 400);
        }
    }
    $settings_json = $decoded !== null ? wp_json_encode($decoded) : '{}';

    global $wpdb;
    $device = $wpdb->get_row($wpdb->prepare("SELECT machine_id FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $unit_id), ARRAY_A);
    $machine_id = $device['machine_id'] ?? '';
    uc_devices_ensure_table();
    $uc_table = $wpdb->prefix . 'tmon_uc_devices';
    if (!$machine_id) {
        $alt = $wpdb->get_row($wpdb->prepare("SELECT machine_id FROM {$uc_table} WHERE unit_id=%s", $unit_id), ARRAY_A);
        if ($alt && !empty($alt['machine_id'])) { $machine_id = $alt['machine_id']; }
    }
    // Persist staged settings locally
    $wpdb->query($wpdb->prepare(
        "INSERT INTO {$uc_table} (unit_id, machine_id, staged_settings, staged_at, assigned, updated_at)
         VALUES (%s, %s, %s, NOW(), 1, NOW())
         ON DUPLICATE KEY UPDATE staged_settings=VALUES(staged_settings), staged_at=VALUES(staged_at), machine_id=IF(VALUES(machine_id)!='', VALUES(machine_id), machine_id), updated_at=NOW()",
        $unit_id, $machine_id, $settings_json
    ));

    // Push to Admin hub if credentials exist
    $push_result = uc_push_staged_settings($unit_id, $machine_id, $settings_json);
    if (is_wp_error($push_result)) {
        wp_send_json_error(['message' => $push_result->get_error_message()]);
    }
    wp_send_json_success(['message' => 'Staged and pushed to Admin hub.']);
});
