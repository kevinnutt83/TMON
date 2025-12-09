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

if ( ! function_exists('tmon_admin_install_schema') ) {
	function tmon_admin_install_schema() {
		global $wpdb;
		$charset_collate = $wpdb->get_charset_collate();
		require_once ABSPATH . 'wp-admin/includes/upgrade.php';

		// Devices
		$dev = $wpdb->prefix . 'tmon_devices';
		dbDelta("CREATE TABLE {$dev} (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			machine_id VARCHAR(64) NOT NULL,
			unit_id VARCHAR(64) NOT NULL,
			unit_name VARCHAR(100) DEFAULT NULL,
			company VARCHAR(191) DEFAULT NULL,
			site VARCHAR(191) DEFAULT NULL,
			zone VARCHAR(191) DEFAULT NULL,
			cluster VARCHAR(191) DEFAULT NULL,
			suspended TINYINT(1) NOT NULL DEFAULT 0,
			provisioned TINYINT(1) NOT NULL DEFAULT 0,
			last_seen DATETIME NULL DEFAULT NULL,
			wordpress_api_url VARCHAR(255) DEFAULT '',
			settings LONGTEXT NULL,
			canBill TINYINT(1) NOT NULL DEFAULT 0,
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
			UNIQUE KEY uq_machine_id (machine_id),
			UNIQUE KEY uq_unit_id (unit_id),
			PRIMARY KEY  (id)
		) $charset_collate;");

		// Provisioned devices
		$prov = $wpdb->prefix . 'tmon_provisioned_devices';
		dbDelta("CREATE TABLE {$prov} (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			unit_id VARCHAR(64) NOT NULL,
			machine_id VARCHAR(64) NOT NULL,
			unit_name VARCHAR(128) DEFAULT '',
			role VARCHAR(32) DEFAULT 'base',
			company_id BIGINT UNSIGNED NULL,
			plan VARCHAR(64) DEFAULT 'standard',
			status VARCHAR(32) DEFAULT 'active',
			notes TEXT NULL,
			site_url VARCHAR(255) DEFAULT '',
			wordpress_api_url VARCHAR(255) DEFAULT '',
			settings_staged TINYINT(1) DEFAULT 0,
			firmware VARCHAR(128) DEFAULT '',
			firmware_url VARCHAR(255) DEFAULT '',
			machine_id_norm VARCHAR(64) DEFAULT '',
			unit_id_norm VARCHAR(64) DEFAULT '',
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
			PRIMARY KEY (id),
			UNIQUE KEY unit_machine (unit_id, machine_id),
			KEY company_idx (company_id),
			KEY status_idx (status)
		) $charset_collate;");

		// Notifications
		$notifications = $wpdb->prefix . 'tmon_notifications';
		dbDelta("CREATE TABLE {$notifications} (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			title VARCHAR(255) NOT NULL,
			message LONGTEXT NULL,
			level VARCHAR(32) NOT NULL DEFAULT 'info',
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			read_at DATETIME NULL,
			PRIMARY KEY (id),
			KEY idx_created (created_at),
			KEY idx_read (read_at)
		) $charset_collate;");
	}
}
