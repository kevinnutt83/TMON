<?php
/**
 * TMON Admin Notifications
 *
 * Displays and manages notifications for the TMON Admin.
 *
 * @package TMON\Admin
 */

add_action('tmon_admin_notifications_page', function () {
	static $printed = false; if ($printed) return; $printed = true;
	global $wpdb;

	$table = $wpdb->prefix . 'tmon_notifications';

	// Ensure table exists (idempotent)
	$exists = (bool) $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $table));
	if (!$exists) {
		require_once ABSPATH . 'wp-admin/includes/upgrade.php';
		$charset = $wpdb->get_charset_collate();
		$sql = "CREATE TABLE {$table} (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			title VARCHAR(255) NOT NULL,
			message LONGTEXT NULL,
			level VARCHAR(32) NOT NULL DEFAULT 'info',
			created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
			read_at DATETIME NULL,
			PRIMARY KEY (id),
			KEY idx_created (created_at),
			KEY idx_read (read_at)
		) {$charset};";
		dbDelta($sql);
	}

	$rows = $wpdb->get_results("SELECT id, title, message, level, created_at, read_at FROM {$table} ORDER BY created_at DESC LIMIT 200");

	echo '<div class="wrap"><h1>Notifications</h1>';
	echo '<table class="widefat striped"><thead><tr><th>ID</th><th>Title</th><th>Level</th><th>Created</th><th>Read</th></tr></thead><tbody>';
	if ($rows) {
		foreach ($rows as $r) {
			echo '<tr><td>' . intval($r->id) . '</td><td>' . esc_html($r->title) . '</td><td>' . esc_html($r->level) . '</td><td>' . esc_html($r->created_at) . '</td><td>' . esc_html($r->read_at) . '</td></tr>';
		}
	} else {
		echo '<tr><td colspan="5">No notifications</td></tr>';
	}
	echo '</tbody></table></div>';
});