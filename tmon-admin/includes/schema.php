<?php
/**
 * TMON Admin Schema
 *
 * Handles the creation and updating of the database schema for TMON Admin.
 *
 * @package TMON\Admin
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit; // Exit if accessed directly.
}

/**
 * tmon_admin_install_schema
 *
 * Creates and updates the database tables required for TMON Admin.
 */
function tmon_admin_install_schema() {
	global $wpdb;
	$charset_collate = $wpdb->get_charset_collate();

	// Create tmon_devices table if it doesn't exist
	$table_name = $wpdb->prefix . 'tmon_devices';
	$sql = "CREATE TABLE IF NOT EXISTS $table_name (
		id mediumint(9) NOT NULL AUTO_INCREMENT,
		device_name tinytext NOT NULL,
		device_type tinytext NOT NULL,
		provisioned tinyint(1) DEFAULT 0,
		provisioned_at datetime DEFAULT NULL,
		wordpress_api_url varchar(255) DEFAULT '',
		PRIMARY KEY  (id)
	) $charset_collate;";
	require_once( ABSPATH . 'wp-admin/includes/upgrade.php' );
	dbDelta( $sql );

	// Create tmon_provisioned_devices table if it doesn't exist
	$table_name = $wpdb->prefix . 'tmon_provisioned_devices';
	$sql = "CREATE TABLE IF NOT EXISTS $table_name (
		id mediumint(9) NOT NULL AUTO_INCREMENT,
		device_id mediumint(9) NOT NULL,
		settings_staged tinyint(1) DEFAULT 0,
		PRIMARY KEY  (id)
	) $charset_collate;";
	dbDelta( $sql );

	// Ensure tmon_devices includes provisioned fields
	$dev_table = $wpdb->prefix . 'tmon_devices';
	if ( $wpdb->get_var( $wpdb->prepare( "SHOW TABLES LIKE %s", $dev_table ) ) ) {
		$cols = $wpdb->get_col( "SHOW COLUMNS FROM {$dev_table}" );
		if ( ! in_array( 'provisioned', $cols ) ) $wpdb->query( "ALTER TABLE {$dev_table} ADD COLUMN provisioned TINYINT(1) DEFAULT 0" );
		if ( ! in_array( 'provisioned_at', $cols ) ) $wpdb->query( "ALTER TABLE {$dev_table} ADD COLUMN provisioned_at DATETIME DEFAULT NULL" );
		if ( ! in_array( 'wordpress_api_url', $cols ) ) $wpdb->query( "ALTER TABLE {$dev_table} ADD COLUMN wordpress_api_url VARCHAR(255) DEFAULT ''" );
	}

	// Ensure settings_staged exists in provisioned table
	$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
	$cols = $wpdb->get_col( "SHOW COLUMNS FROM {$prov_table}" );
	if ( ! in_array( 'settings_staged', $cols ) ) $wpdb->query( "ALTER TABLE {$prov_table} ADD COLUMN settings_staged TINYINT(1) DEFAULT 0" );
}
