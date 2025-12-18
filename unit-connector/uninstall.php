<?php
// Uninstall handler for TMON Unit Connector — remove DB, options, files
if (!defined('WP_UNINSTALL_PLUGIN')) {
    exit;
}

// Try to include cleanup helper if available
$inc = __DIR__ . '/includes/cleanup.php';
if (file_exists($inc)) {
    include_once $inc;
    if (function_exists('tmon_uc_remove_all_data')) {
        tmon_uc_remove_all_data(true);
    }
} else {
    // Best-effort inline fallback cleanup if helper missing
    global $wpdb;
    $tables = [
        'tmon_field_data','tmon_devices','tmon_ota_jobs','tmon_device_commands',
        'tmon_company','tmon_site','tmon_zone','tmon_cluster','tmon_unit','tmon_audit',
        'tmon_device_data','tmon_staged_settings','tmon_uc_devices'
    ];
    foreach ($tables as $t) {
        $wpdb->query("DROP TABLE IF EXISTS {$wpdb->prefix}{$t}");
    }
    // delete options by pattern
    $rows = $wpdb->get_col( $wpdb->prepare("SELECT option_name FROM {$wpdb->options} WHERE option_name LIKE %s", 'tmon_uc_%') );
    if (is_array($rows)) foreach ($rows as $opt) delete_option($opt);
    // remove directories
    try {
        $fld = WP_CONTENT_DIR . '/tmon-field-logs';
        if (is_dir($fld)) {
            foreach (glob($fld . '/*') as $f) { @unlink($f); }
            @rmdir($fld);
        }
        $upload_dir = wp_upload_dir();
        if (!empty($upload_dir['basedir'])) {
            $td = trailingslashit($upload_dir['basedir']) . 'tmon_device_files';
            if (is_dir($td)) {
                foreach (glob($td . '/*') as $f) { @unlink($f); }
                @rmdir($td);
            }
        }
    } catch (Exception $e) {
        // best-effort
    }
    // remove roles
    if (function_exists('remove_role')) {
        remove_role('tmon_manager');
        remove_role('tmon_operator');
    }
}
