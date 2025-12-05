<?php
// TMON Admin Audit Logging
// Usage: do_action('tmon_admin_audit', $action, $details, $user_id);
add_action('tmon_admin_audit', function($action, $details = '', $user_id = null) {
    $logs = get_option('tmon_admin_audit_logs', []);
    $logs[] = [
        'timestamp' => current_time('mysql'),
        'user_id' => $user_id ?: get_current_user_id(),
        'action' => $action,
        'details' => $details,
    ];
    update_option('tmon_admin_audit_logs', $logs);
});

// Helper: Get audit logs
function tmon_admin_get_audit_logs($limit = 100) {
    $logs = get_option('tmon_admin_audit_logs', []);
    return array_slice(array_reverse($logs), 0, $limit);
}

if (!defined('ABSPATH')) { exit; }

function tmon_admin_audit_table_name() {
	global $wpdb;
	return $wpdb->prefix . 'tmon_admin_audit';
}

function tmon_admin_audit_ensure_tables() {
	global $wpdb;
	$table = tmon_admin_audit_table_name();
	$charset = $wpdb->get_charset_collate();
	$sql = "CREATE TABLE IF NOT EXISTS $table (
		id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
		ts DATETIME NOT NULL,
		user_id BIGINT UNSIGNED NULL,
		action VARCHAR(96) NOT NULL,
		context VARCHAR(191) NULL,
		device VARCHAR(64) NULL,
		unit_id VARCHAR(16) NULL,
		machine_id VARCHAR(32) NULL,
		ip VARCHAR(64) NULL,
		extra LONGTEXT NULL,
		PRIMARY KEY (id),
		KEY idx_ts (ts),
		KEY idx_action (action),
		KEY idx_unit (unit_id),
		KEY idx_machine (machine_id)
	) $charset;";
	require_once ABSPATH . 'wp-admin/includes/upgrade.php';
	dbDelta($sql);
}

function tmon_admin_audit_log($action, $context = null, $args = array()) {
	global $wpdb;
	$table = tmon_admin_audit_table_name();
	$user = get_current_user_id();
	$row = array(
		'ts' => current_time('mysql'),
		'user_id' => $user ?: null,
		'action' => sanitize_text_field($action),
		'context' => $context ? sanitize_text_field($context) : null,
		'device' => isset($args['device']) ? sanitize_text_field($args['device']) : null,
		'unit_id' => isset($args['unit_id']) ? sanitize_text_field($args['unit_id']) : null,
		'machine_id' => isset($args['machine_id']) ? sanitize_text_field($args['machine_id']) : null,
		'ip' => isset($_SERVER['REMOTE_ADDR']) ? sanitize_text_field($_SERVER['REMOTE_ADDR']) : null,
		'extra' => isset($args['extra']) ? wp_json_encode($args['extra']) : null,
	);
	$wpdb->insert($table, $row);
}

function tmon_admin_audit_page() {
	if (!current_user_can('manage_options')) {
		wp_die(__('Insufficient permissions', 'tmon'));
	}
	tmon_admin_audit_ensure_tables();
	global $wpdb;
	$table = tmon_admin_audit_table_name();

	$per_page = 50;
	$page = isset($_GET['paged']) ? max(1, intval($_GET['paged'])) : 1;
	$offset = ($page - 1) * $per_page;

	$where = '1=1';
	$params = array();
	if (!empty($_GET['q'])) {
		$q = '%' . $wpdb->esc_like(sanitize_text_field($_GET['q'])) . '%';
		$where .= " AND (action LIKE %s OR context LIKE %s OR unit_id LIKE %s OR machine_id LIKE %s)";
		array_push($params, $q, $q, $q, $q);
	}
	$total = (int) $wpdb->get_var($wpdb->prepare("SELECT COUNT(*) FROM $table WHERE $where", $params));
	$rows = $wpdb->get_results($wpdb->prepare("SELECT * FROM $table WHERE $where ORDER BY id DESC LIMIT %d OFFSET %d", array_merge($params, array($per_page, $offset))), ARRAY_A);

	echo '<div class="wrap"><h1>' . esc_html__('TMON Audit', 'tmon') . '</h1>';
	echo '<form method="get"><input type="hidden" name="page" value="tmon-admin-audit" />';
	echo '<p><input type="text" name="q" value="' . esc_attr(isset($_GET['q']) ? $_GET['q'] : '') . '" placeholder="Search action, unit, machine..." />';
	submit_button(__('Filter'), 'secondary', '', false);
	echo '</p></form>';

	echo '<table class="widefat striped"><thead><tr>';
	echo '<th>' . esc_html__('Time', 'tmon') . '</th>';
	echo '<th>' . esc_html__('User', 'tmon') . '</th>';
	echo '<th>' . esc_html__('Action', 'tmon') . '</th>';
	echo '<th>' . esc_html__('Context', 'tmon') . '</th>';
	echo '<th>' . esc_html__('Unit', 'tmon') . '</th>';
	echo '<th>' . esc_html__('Machine', 'tmon') . '</th>';
	echo '<th>' . esc_html__('IP', 'tmon') . '</th>';
	echo '</tr></thead><tbody>';
	if ($rows) {
		foreach ($rows as $r) {
			$user = $r['user_id'] ? get_user_by('id', $r['user_id']) : null;
			echo '<tr>';
			echo '<td>' . esc_html($r['ts']) . '</td>';
			echo '<td>' . esc_html($user ? $user->user_login : '-') . '</td>';
			echo '<td>' . esc_html($r['action']) . '</td>';
			echo '<td>' . esc_html($r['context']) . '</td>';
			echo '<td>' . esc_html($r['unit_id']) . '</td>';
			echo '<td>' . esc_html($r['machine_id']) . '</td>';
			echo '<td>' . esc_html($r['ip']) . '</td>';
			echo '</tr>';
		}
	} else {
		echo '<tr><td colspan="7">' . esc_html__('No audit entries found.', 'tmon') . '</td></tr>';
	}
	echo '</tbody></table>';

	$pages = max(1, ceil($total / $per_page));
	if ($pages > 1) {
		echo '<div class="tablenav"><div class="tablenav-pages">';
		for ($i = 1; $i <= $pages; $i++) {
			$url = esc_url(add_query_arg(array('page' => 'tmon-admin-audit', 'paged' => $i)));
			echo $i == $page ? "<span class='tablenav-pages-navspan'>$i</span> " : "<a class='tablenav-pages-navspan' href='$url'>$i</a> ";
		}
		echo '</div></div>';
	}
	echo '</div>';
}
