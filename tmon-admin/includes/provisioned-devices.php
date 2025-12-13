<?php
// Schema ensure helpers (run on admin_init; silent and idempotent).
if (!function_exists('tmon_admin_ensure_tables')) {
	function tmon_admin_pe_table_exists($table) {
		global $wpdb;
		return (bool) $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $table));
	}
	function tmon_admin_pe_column_exists($table, $column) {
		global $wpdb;
		return (bool) $wpdb->get_var($wpdb->prepare("SHOW COLUMNS FROM `$table` LIKE %s", $column));
	}
	function tmon_admin_ensure_tables() {
		global $wpdb;
		require_once ABSPATH . 'wp-admin/includes/upgrade.php';
		$charset = $wpdb->get_charset_collate();
		$p = $wpdb->prefix;

		// 1) Notifications table (fixes: "twp_tmon_notifications doesn't exist")
		$notifications = "{$p}tmon_notifications";
		if (!tmon_admin_pe_table_exists($notifications)) {
			dbDelta("CREATE TABLE $notifications (
				id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
				title VARCHAR(255) NOT NULL,
				message LONGTEXT NULL,
				level VARCHAR(32) NOT NULL DEFAULT 'info',
				created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
				read_at DATETIME NULL,
				PRIMARY KEY (id),
				KEY idx_created (created_at),
				KEY idx_read (read_at)
			) $charset;");
		}

		// 2) Provisioned devices table (fixes: "twp_tmon_provisioned_devices doesn't exist")
		$prov = "{$p}tmon_provisioned_devices";
		if (!tmon_admin_pe_table_exists($prov)) {
			dbDelta("CREATE TABLE $prov (
				id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
				unit_id VARCHAR(64) NOT NULL,
				machine_id VARCHAR(64) NOT NULL,
				unit_name VARCHAR(191) NULL,
				role VARCHAR(64) NULL,
				company_id BIGINT UNSIGNED NULL,
				plan VARCHAR(64) NULL,
				status VARCHAR(32) NOT NULL DEFAULT 'staged',
				notes LONGTEXT NULL,
				site_url VARCHAR(255) NULL,
				wordpress_api_url VARCHAR(255) NULL,
				provisioned TINYINT(1) NOT NULL DEFAULT 0,
				provisioned_at DATETIME NULL,
				created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
				updated_at DATETIME NULL,
				PRIMARY KEY (id),
				UNIQUE KEY uniq_unit_machine (unit_id, machine_id),
				KEY idx_company (company_id),
				KEY idx_status (status),
				KEY idx_created (created_at)
			) $charset;");
		}

		// 3) OTA jobs table (ensure 'action' column exists)
		$ota = "{$p}tmon_ota_jobs";
		if (!tmon_admin_pe_table_exists($ota)) {
			dbDelta("CREATE TABLE $ota (
				id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
				unit_id VARCHAR(64) NOT NULL,
				action VARCHAR(64) NOT NULL,
				args LONGTEXT NULL,
				status VARCHAR(32) NOT NULL DEFAULT 'queued',
				created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
				updated_at DATETIME NULL,
				PRIMARY KEY (id),
				KEY idx_unit (unit_id),
				KEY idx_status (status),
				KEY idx_created (created_at)
			) $charset;");
		} else {
			if (!tmon_admin_pe_column_exists($ota, 'action')) {
				$wpdb->query("ALTER TABLE $ota ADD COLUMN action VARCHAR(64) NOT NULL AFTER unit_id");
			}
			if (!tmon_admin_pe_column_exists($ota, 'updated_at')) {
				$wpdb->query("ALTER TABLE $ota ADD COLUMN updated_at DATETIME NULL AFTER created_at");
				$wpdb->query("UPDATE $ota SET updated_at = created_at WHERE updated_at IS NULL");
			}
		}

		// 4) Device commands: ensure status/updated_at exist or create table if missing
		$cmd = "{$p}tmon_device_commands";
		if (!tmon_admin_pe_table_exists($cmd)) {
			dbDelta("CREATE TABLE $cmd (
				id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
				device_id VARCHAR(64) NOT NULL,
				command VARCHAR(191) NOT NULL,
				params LONGTEXT NULL,
				status VARCHAR(32) NOT NULL DEFAULT 'staged',
				created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
				updated_at DATETIME NULL,
				PRIMARY KEY (id),
				KEY idx_device (device_id),
				KEY idx_status (status),
				KEY idx_created (created_at)
			) $charset;");
		} else {
			if (!tmon_admin_pe_column_exists($cmd, 'status')) {
				$wpdb->query("ALTER TABLE $cmd ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'staged'");
				$wpdb->query("UPDATE $cmd SET status = 'staged' WHERE status IS NULL OR status = ''");
			}
			if (!tmon_admin_pe_column_exists($cmd, 'updated_at')) {
				$wpdb->query("ALTER TABLE $cmd ADD COLUMN updated_at DATETIME NULL AFTER created_at");
				$wpdb->query("UPDATE $cmd SET updated_at = created_at WHERE updated_at IS NULL");
			}
		}

		// 5) Companies hierarchy (lightweight, used by Groups/Hierarchy)
		$companies = "{$p}tmon_companies";
		if (!tmon_admin_pe_table_exists($companies)) {
			dbDelta("CREATE TABLE $companies (
				id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
				name VARCHAR(191) NOT NULL,
				slug VARCHAR(191) NOT NULL,
				created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
				PRIMARY KEY (id),
				UNIQUE KEY uniq_slug (slug),
				KEY idx_created (created_at)
			) $charset;");
		}
	}
	add_action('admin_init', 'tmon_admin_ensure_tables', 1);
}

// Provisioned Devices page with action buttons
add_action('tmon_admin_provisioned_devices_page', function () {
	static $printed = false; if ($printed) return; $printed = true;
	global $wpdb;

	$prov = $wpdb->prefix . 'tmon_provisioned_devices';
	$mirror = $wpdb->prefix . 'tmon_devices';
	$rows = [];
	if (tmon_admin_pe_table_exists($prov)) {
		$rows = $wpdb->get_results("SELECT id, unit_id, machine_id, unit_name, provisioned_at, status, site_url FROM $prov ORDER BY provisioned_at DESC LIMIT 200");
	} elseif (tmon_admin_pe_table_exists($mirror)) {
		$rows = $wpdb->get_results("SELECT id, unit_id, machine_id, unit_name, provisioned_at, status, wordpress_api_url AS site_url FROM $mirror ORDER BY provisioned_at DESC LIMIT 200");
	}

	echo '<div class="wrap"><h1>Provisioned Devices</h1>';
	if (isset($_GET['prov_notice'])) {
		$notice = sanitize_text_field($_GET['prov_notice']);
		$class = (strpos($notice, 'error:') === 0) ? 'notice-error' : 'notice-success';
		echo '<div class="notice ' . esc_attr($class) . '"><p>' . esc_html($notice) . '</p></div>';
	}

	echo '<table class="widefat striped"><thead><tr><th>ID</th><th>UNIT_ID</th><th>MACHINE_ID</th><th>Name</th><th>Status</th><th>Site</th><th>Provisioned</th><th>Actions</th></tr></thead><tbody>';
	if ($rows) {
		foreach ($rows as $r) {
			$id = intval($r->id);
			$unit_id = esc_html($r->unit_id);
			$machine = esc_html($r->machine_id);
			$name = esc_html($r->unit_name);
			$status = esc_html($r->status ?? '');
			$site = esc_html($r->site_url ?? '');
			$prov_at = esc_html($r->provisioned_at);
			$refresh_url = wp_nonce_url(admin_url('admin-post.php?action=tmon_admin_refresh_device&device_id='.$id), 'tmon_admin_refresh_device_'.$id);
			$reprovision_url = wp_nonce_url(admin_url('admin-post.php?action=tmon_admin_reprovision_device&device_id='.$id), 'tmon_admin_reprovision_device_'.$id);
			$unprovision_url = wp_nonce_url(admin_url('admin-post.php?action=tmon_admin_unprovision_device&device_id='.$id), 'tmon_admin_unprovision_device_'.$id);
			echo '<tr>';
			echo '<td>' . $id . '</td><td>' . $unit_id . '</td><td>' . $machine . '</td><td>' . $name . '</td><td>' . $status . '</td><td>' . $site . '</td><td>' . $prov_at . '</td>';
			echo '<td>';
			echo '<a class="button" href="' . esc_url($refresh_url) . '">Refresh</a> ';
			echo '<a class="button" href="' . esc_url($reprovision_url) . '">Reprovision</a> ';
			echo '<a class="button button-secondary" href="' . esc_url($unprovision_url) . '" onclick="return confirm(\'Unprovision this device?\');">Unprovision</a>';
			echo '</td>';
			echo '</tr>';
		}
	} else {
		echo '<tr><td colspan="8">No provisioned devices found.</td></tr>';
	}
	echo '</tbody></table>';
	echo '</div>';
});