<?php
// REST API for field data and data history log upload (admin plugin)
add_action('rest_api_init', function() {
    register_rest_route('tmon-admin/v1', '/field-data', [
        'methods' => 'GET',
        'callback' => 'tmon_admin_get_field_data',
        'permission_callback' => function() { return current_user_can('manage_options'); },
    ]);
    register_rest_route('tmon-admin/v1', '/data-history', [
        'methods' => 'GET',
        'callback' => 'tmon_admin_get_data_history',
        'permission_callback' => function() { return current_user_can('manage_options'); },
    ]);
    register_rest_route('tmon-admin/v1', '/field-data', [
        'methods' => 'DELETE',
        'callback' => 'tmon_admin_delete_field_data_api',
        'permission_callback' => function() { return current_user_can('manage_options'); },
        'args' => [ 'file' => [ 'required' => true ] ],
    ]);
    register_rest_route('tmon-admin/v1', '/data-history', [
        'methods' => 'DELETE',
        'callback' => 'tmon_admin_delete_data_history_api',
        'permission_callback' => function() { return current_user_can('manage_options'); },
        'args' => [ 'file' => [ 'required' => true ] ],
    ]);
});

function tmon_admin_delete_field_data_api($request) {
    $file = sanitize_file_name($request->get_param('file'));
    $log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
    $path = realpath($log_dir . '/' . $file);
    if ($path && strpos($path, realpath($log_dir)) === 0 && file_exists($path)) {
        unlink($path);
        return rest_ensure_response(['deleted' => true]);
    }
    return rest_ensure_response(['deleted' => false]);
}

function tmon_admin_delete_data_history_api($request) {
    $file = sanitize_file_name($request->get_param('file'));
    $log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
    $path = realpath($log_dir . '/' . $file);
    if ($path && strpos($path, realpath($log_dir)) === 0 && file_exists($path)) {
        unlink($path);
        return rest_ensure_response(['deleted' => true]);
    }
    return rest_ensure_response(['deleted' => false]);
}

function tmon_admin_get_field_data($request) {
    $log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
    $files = glob($log_dir . '/field_data_*.log');
    $data = [];
    foreach ($files as $file) {
        $unit_id = basename($file, '.log');
        $unit_id = str_replace('field_data_', '', $unit_id);
        $lines = file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
        foreach ($lines as $line) {
            $row = json_decode($line, true);
            if ($row) $data[] = array_merge(['unit_id' => $unit_id], $row);
        }
    }
    // Also load CSV files if present (written by Unit Connector)
    $csvs = glob($log_dir . '/field_data_*.csv');
    foreach ($csvs as $csv) {
        $unit_id = basename($csv, '.csv');
        $unit_id = str_replace('field_data_', '', $unit_id);
        if (!file_exists($csv)) continue;
        if (($fh = fopen($csv, 'r')) !== false) {
            $headers = fgetcsv($fh);
            if (is_array($headers)) {
                while (($row = fgetcsv($fh)) !== false) {
                    $assoc = [];
                    foreach ($headers as $i => $h) { $assoc[$h] = $row[$i] ?? null; }
                    $assoc['unit_id'] = $unit_id;
                    $data[] = $assoc;
                }
            }
            fclose($fh);
        }
    }
    return rest_ensure_response($data);
}

function tmon_admin_get_data_history($request) {
    $log_dir = WP_CONTENT_DIR . '/tmon-field-logs';
    $files = glob($log_dir . '/data_history_*.log');
    $data = [];
    foreach ($files as $file) {
        $unit_id = basename($file);
        $lines = file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
        $data[] = [
            'file' => $unit_id,
            'lines' => $lines,
        ];
    }
    return rest_ensure_response($data);
}
