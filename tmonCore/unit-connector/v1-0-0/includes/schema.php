<?php
// DB schema for TMON organizational hierarchy and device data
// Call tmon_uc_install_schema() from the main plugin activation hook
function tmon_uc_install_schema() {
    global $wpdb;
    $charset_collate = $wpdb->get_charset_collate();

    // Field Data Table
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_field_data (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        unit_id VARCHAR(64),
        data LONGTEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    ) $charset_collate;");

    // Devices registry (duplicated here for fresh installs)
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_devices (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
        unit_id VARCHAR(64) NOT NULL UNIQUE,
        machine_id VARCHAR(64) NULL UNIQUE,
        unit_name VARCHAR(128),
        company VARCHAR(128),
        site VARCHAR(128),
        zone VARCHAR(128),
        cluster VARCHAR(128),
        last_seen DATETIME,
        settings LONGTEXT,
        status LONGTEXT,
        suspended TINYINT(1) DEFAULT 0,
        PRIMARY KEY (id)
    ) $charset_collate;");

    // Lightweight upgrade: add machine_id column if missing on existing installs
    try {
        $table = $wpdb->prefix.'tmon_devices';
        $col = $wpdb->get_var($wpdb->prepare("SHOW COLUMNS FROM `$table` LIKE %s", 'machine_id'));
        if (!$col) {
            $wpdb->query("ALTER TABLE `$table` ADD COLUMN machine_id VARCHAR(64) NULL UNIQUE AFTER unit_id");
        }
    } catch (Exception $e) {
        // ignore if not supported
    }

    // OTA jobs
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_ota_jobs (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        unit_id VARCHAR(64) NOT NULL,
        job_type VARCHAR(64) NOT NULL,
        payload LONGTEXT,
        status VARCHAR(32) DEFAULT 'pending',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        completed_at DATETIME NULL
    ) $charset_collate;");

    // Device commands (for queued actions)
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_device_commands (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        device_id VARCHAR(64) NOT NULL,
        command VARCHAR(64) NOT NULL,
        params LONGTEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        executed_at DATETIME NULL
    ) $charset_collate;");

    // Company
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_company (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255),
        description TEXT,
        notes TEXT,
        address VARCHAR(255),
        gps_lat DOUBLE,
        gps_lng DOUBLE,
        timezone VARCHAR(64),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) $charset_collate;");

    // Site
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_site (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        company_id BIGINT UNSIGNED,
        name VARCHAR(255),
        description TEXT,
        notes TEXT,
        address VARCHAR(255),
        gps_lat DOUBLE,
        gps_lng DOUBLE,
        timezone VARCHAR(64),
        overhead_map_url VARCHAR(255),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (company_id) REFERENCES {$wpdb->prefix}tmon_company(id) ON DELETE CASCADE
    ) $charset_collate;");

    // Zone
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_zone (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        site_id BIGINT UNSIGNED,
        name VARCHAR(255),
        description TEXT,
        notes TEXT,
        address VARCHAR(255),
        gps_lat DOUBLE,
        gps_lng DOUBLE,
        timezone VARCHAR(64),
        overhead_map_url VARCHAR(255),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (site_id) REFERENCES {$wpdb->prefix}tmon_site(id) ON DELETE CASCADE
    ) $charset_collate;");

    // Cluster
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_cluster (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        zone_id BIGINT UNSIGNED,
        name VARCHAR(255),
        description TEXT,
        notes TEXT,
        address VARCHAR(255),
        gps_lat DOUBLE,
        gps_lng DOUBLE,
        timezone VARCHAR(64),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (zone_id) REFERENCES {$wpdb->prefix}tmon_zone(id) ON DELETE CASCADE
    ) $charset_collate;");

    // Unit
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_unit (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        cluster_id BIGINT UNSIGNED,
        name VARCHAR(255),
        description TEXT,
        notes TEXT,
        address VARCHAR(255),
        gps_lat DOUBLE,
        gps_lng DOUBLE,
        timezone VARCHAR(64),
        status VARCHAR(32),
        last_seen DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (cluster_id) REFERENCES {$wpdb->prefix}tmon_cluster(id) ON DELETE CASCADE
    ) $charset_collate;");

    // Audit
    $wpdb->query("CREATE TABLE IF NOT EXISTS {$wpdb->prefix}tmon_audit (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        user_id BIGINT UNSIGNED,
        action VARCHAR(255),
        details TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    ) $charset_collate;");
}
