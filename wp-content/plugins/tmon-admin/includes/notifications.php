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
	if (!tmon_admin_table_exists($table)) {
		echo '<div class="wrap"><h1>Notifications</h1><p>Notifications table missing.</p></div>';
		return;
	}

	$rows = $wpdb->get_results("SELECT id, title, message, level, created_at, read_at FROM $table ORDER BY created_at DESC LIMIT 200");

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