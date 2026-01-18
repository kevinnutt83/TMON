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

	// Export CSV on request
	if (isset($_GET['tmon_audit_export']) && $_GET['tmon_audit_export'] === '1') {
		if (!check_admin_referer('tmon_audit_export')) {
			wp_die('Invalid export request');
		}
		tmon_admin_audit_export_csv();
		exit;
	}

	$per_page = isset($_GET['per_page']) ? max(10, min(200, intval($_GET['per_page']))) : 50;
	$page = isset($_GET['paged']) ? max(1, intval($_GET['paged'])) : 1;
	$offset = ($page - 1) * $per_page;

	$where = array('1=1');
	$params = array();

	$q_val = isset($_GET['q']) ? sanitize_text_field($_GET['q']) : '';
	$action_val = isset($_GET['action_filter']) ? sanitize_text_field($_GET['action_filter']) : '';
	$unit_val = isset($_GET['unit_filter']) ? sanitize_text_field($_GET['unit_filter']) : '';
	$machine_val = isset($_GET['machine_filter']) ? sanitize_text_field($_GET['machine_filter']) : '';

	if ($q_val !== '') {
		$q = '%' . $wpdb->esc_like($q_val) . '%';
		$where[] = '(action LIKE %s OR context LIKE %s OR unit_id LIKE %s OR machine_id LIKE %s OR device LIKE %s OR ip LIKE %s)';
		array_push($params, $q, $q, $q, $q, $q, $q);
	}
	if ($action_val !== '') {
		$where[] = 'action = %s';
		$params[] = $action_val;
	}
	if ($unit_val !== '') {
		$where[] = 'unit_id = %s';
		$params[] = $unit_val;
	}
	if ($machine_val !== '') {
		$where[] = 'machine_id = %s';
		$params[] = $machine_val;
	}

	$where_sql = implode(' AND ', $where);
	$total_sql = $wpdb->prepare("SELECT COUNT(*) FROM $table WHERE $where_sql", $params);
	$total = (int) $wpdb->get_var($total_sql);

	$query_sql = "SELECT * FROM $table WHERE $where_sql ORDER BY id DESC LIMIT %d OFFSET %d";
	$rows = $wpdb->get_results($wpdb->prepare($query_sql, array_merge($params, array($per_page, $offset))), ARRAY_A);

	$actions = $wpdb->get_col("SELECT DISTINCT action FROM $table ORDER BY action ASC LIMIT 200");

	echo '<div class="wrap"><h1>' . esc_html__('TMON Audit', 'tmon') . '</h1>';
	echo '<form method="get" class="tmon-audit-filters"><input type="hidden" name="page" value="tmon-admin-audit" />';
	echo '<p>';
	echo '<label>Search <input type="text" name="q" value="' . esc_attr($q_val) . '" placeholder="action, unit, machine, IP"></label> ';
	echo '<label>Action <select name="action_filter"><option value="">All</option>';
	foreach ($actions as $act) {
		$selected = selected($action_val, $act, false);
		echo '<option value="' . esc_attr($act) . '" ' . $selected . '>' . esc_html($act) . '</option>';
	}
	echo '</select></label> ';
	echo '<label>Unit <input type="text" name="unit_filter" value="' . esc_attr($unit_val) . '" size="10"></label> ';
	echo '<label>Machine <input type="text" name="machine_filter" value="' . esc_attr($machine_val) . '" size="14"></label> ';
	echo '<label>Per page <input type="number" name="per_page" value="' . esc_attr($per_page) . '" min="10" max="200" class="small-text"></label> ';
	submit_button(__('Filter'), 'secondary', '', false);
	$export_url = wp_nonce_url(add_query_arg(array_merge($_GET, ['tmon_audit_export' => '1'])), 'tmon_audit_export');
	echo ' <a class="button" href="' . esc_url($export_url) . '">Export CSV</a>';
	echo '</p></form>';

	echo '<table class="widefat striped"><thead><tr>';
	echo '<th>' . esc_html__('Time', 'tmon') . '</th>';
	echo '<th>' . esc_html__('User', 'tmon') . '</th>';
	echo '<th>' . esc_html__('Action', 'tmon') . '</th>';
	echo '<th>' . esc_html__('Context', 'tmon') . '</th>';
	echo '<th>' . esc_html__('Unit', 'tmon') . '</th>';
	echo '<th>' . esc_html__('Machine', 'tmon') . '</th>';
	echo '<th>' . esc_html__('IP', 'tmon') . '</th>';
	echo '<th>' . esc_html__('Details', 'tmon') . '</th>';
	echo '</tr></thead><tbody>';
	if ($rows) {
		foreach ($rows as $r) {
			$user = $r['user_id'] ? get_user_by('id', $r['user_id']) : null;
			$extra = '';
			if (!empty($r['extra'])) {
				$decoded = json_decode($r['extra'], true);
				$extra = is_array($decoded) ? wp_json_encode($decoded) : $r['extra'];
			}
			echo '<tr>';
			echo '<td>' . esc_html($r['ts']) . '</td>';
			echo '<td>' . esc_html($user ? $user->user_login : '-') . '</td>';
			echo '<td>' . esc_html($r['action']) . '</td>';
			echo '<td>' . esc_html($r['context']) . '</td>';
			echo '<td>' . esc_html($r['unit_id']) . '</td>';
			echo '<td>' . esc_html($r['machine_id']) . '</td>';
			echo '<td>' . esc_html($r['ip']) . '</td>';
			echo '<td><code>' . esc_html($extra) . '</code></td>';
			echo '</tr>';
		}
	} else {
		echo '<tr><td colspan="8">' . esc_html__('No audit entries found.', 'tmon') . '</td></tr>';
	}
	echo '</tbody></table>';

	$pages = max(1, ceil($total / $per_page));
	if ($pages > 1) {
		echo '<div class="tablenav"><div class="tablenav-pages">';
		$links = paginate_links(array(
			'total' => $pages,
			'current' => $page,
			'format' => '&paged=%#%',
			'add_args' => array(
				'page' => 'tmon-admin-audit',
				'q' => $q_val,
				'action_filter' => $action_val,
				'unit_filter' => $unit_val,
				'machine_filter' => $machine_val,
				'per_page' => $per_page,
			),
			'prev_text' => '&laquo;',
			'next_text' => '&raquo;',
		));
		echo $links ? $links : '';
		echo '</div></div>';
	}
	echo '</div>';
}

function tmon_admin_audit_export_csv() {
	if (!current_user_can('manage_options')) {
		wp_die('Forbidden');
	}
	global $wpdb;
	$table = tmon_admin_audit_table_name();
	$rows = $wpdb->get_results("SELECT * FROM $table ORDER BY id DESC LIMIT 10000", ARRAY_A);
	header('Content-Type: text/csv');
	header('Content-Disposition: attachment; filename="tmon-audit.csv"');
	$out = fopen('php://output', 'w');
	fputcsv($out, ['id','ts','user_id','action','context','device','unit_id','machine_id','ip','extra']);
	foreach ($rows as $r) {
		fputcsv($out, [
			$r['id'],
			$r['ts'],
			$r['user_id'],
			$r['action'],
			$r['context'],
			$r['device'],
			$r['unit_id'],
			$r['machine_id'],
			$r['ip'],
			$r['extra'],
		]);
	}
	fclose($out);
}
