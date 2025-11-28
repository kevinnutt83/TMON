// ...existing schema code...
// ensure device mirror columns
global $wpdb;
$table = $wpdb->prefix . 'tmon_devices';
if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table))) {
    $cols = array_column($wpdb->get_results("SHOW COLUMNS FROM $table", ARRAY_A), 'Field');
    if (!in_array('provisioned', $cols)) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN provisioned TINYINT(1) DEFAULT 0");
    }
    if (!in_array('wordpress_api_url', $cols)) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN wordpress_api_url VARCHAR(255) DEFAULT ''");
    }
    if (!in_array('provisioned_at', $cols)) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN provisioned_at DATETIME DEFAULT NULL");
    }
}

// Also ensure settings_staged in tmon_provisioned_devices
$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
$cols = array_column($wpdb->get_results("SHOW COLUMNS FROM $prov_table", ARRAY_A), 'Field');
if (!in_array('settings_staged', $cols)) {
    $wpdb->query("ALTER TABLE $prov_table ADD COLUMN settings_staged TINYINT(1) DEFAULT 0");
}
