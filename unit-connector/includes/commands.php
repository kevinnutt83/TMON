<?php
if (!defined('ABSPATH')) { exit; }

// Ensure device data table exists (used by REST: tmon_uc_api_device_data)
if (!function_exists('tmon_uc_ensure_device_data_table')) {
	function tmon_uc_ensure_device_data_table() {
		global $wpdb;
		$table = $wpdb->prefix . 'tmon_device_data'; // matches mp_tmon_device_data when prefix=mp_
		$charset = $wpdb->get_charset_collate();

		// Create/upgrade base schema
		$sql = "CREATE TABLE IF NOT EXISTS {$table} (
			id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
			unit_id VARCHAR(16) NOT NULL,
			machine_id VARCHAR(64) NULL,
			role VARCHAR(32) NULL,
			ts DATETIME NULL,
			recorded_at DATETIME NULL,
			timestamp INT UNSIGNED NULL,
			temp_c FLOAT NULL,
			temp_f FLOAT NULL,
			humid FLOAT NULL,
			bar_pres FLOAT NULL,
			sys_voltage FLOAT NULL,
			wifi_rssi INT NULL,
			lora_rssi INT NULL,
			free_mem INT NULL,
			error_count INT NULL,
			last_error VARCHAR(255) NULL,
			data LONGTEXT NULL,
			payload LONGTEXT NULL,
			PRIMARY KEY (id),
			KEY idx_unit (unit_id),
			KEY idx_machine (machine_id),
			KEY idx_ts (recorded_at),
			KEY idx_ts_alt (ts)
		) {$charset};";
		require_once ABSPATH . 'wp-admin/includes/upgrade.php';
		dbDelta($sql);

		// Defensive: ensure columns/indexes exist; avoid duplicate key errors
		$cols = $wpdb->get_results("SHOW FULL COLUMNS FROM {$table}", ARRAY_A) ?: array();
		$col_names = array_map(function($c){ return $c['Field']; }, $cols);

		$indexes = $wpdb->get_results("SHOW INDEX FROM {$table}", ARRAY_A) ?: array();
		$idx_names = array();
		foreach ($indexes as $idx) {
			if (!empty($idx['Key_name'])) {
				$idx_names[] = $idx['Key_name'];
			}
		}

		// Add 'data' column if missing
		if (!in_array('data', $col_names, true)) {
			$wpdb->query("ALTER TABLE {$table} ADD COLUMN data LONGTEXT NULL");
		}
		// Add 'recorded_at' column if missing
		if (!in_array('recorded_at', $col_names, true)) {
			$wpdb->query("ALTER TABLE {$table} ADD COLUMN recorded_at DATETIME NULL");
			// Refresh column list
			$cols = $wpdb->get_results("SHOW FULL COLUMNS FROM {$table}", ARRAY_A) ?: array();
			$col_names = array_map(function($c){ return $c['Field']; }, $cols);
		}
		// Add idx_ts on recorded_at if missing (avoid duplicate key error)
		if (!in_array('idx_ts', $idx_names, true) && in_array('recorded_at', $col_names, true)) {
			$wpdb->query("ALTER TABLE {$table} ADD KEY idx_ts (recorded_at)");
		}
	}
}
add_action('admin_init', 'tmon_uc_ensure_device_data_table');
add_action('rest_api_init', 'tmon_uc_ensure_device_data_table');

// Back-compat inserter used by REST handler tmon_uc_api_device_data
if (!function_exists('tmon_uc_device_data_insert')) {
	function tmon_uc_device_data_insert($unit_id, $machine_id, $data_json, $recorded_at = null) {
		global $wpdb;
		$table = $wpdb->prefix . 'tmon_device_data';
		tmon_uc_ensure_device_data_table();
		$recorded_at = $recorded_at ? $recorded_at : current_time('mysql');
		return $wpdb->insert($table, array(
			'unit_id'     => sanitize_text_field($unit_id),
			'machine_id'  => $machine_id ? sanitize_text_field($machine_id) : null,
			'data'        => wp_unslash($data_json),
			'recorded_at' => $recorded_at,
		), array('%s','%s','%s','%s'));
	}
}

// Ensure commands queue table exists
add_action('init', function () {
	global $wpdb;
	$table = $wpdb->prefix . 'tmon_device_commands';
	$charset = $wpdb->get_charset_collate();
	$sql = "CREATE TABLE IF NOT EXISTS {$table} (
		id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
		device_id VARCHAR(64) NOT NULL,
		command VARCHAR(64) NOT NULL,
		params LONGTEXT NULL,
		status VARCHAR(32) DEFAULT 'queued',
		result LONGTEXT NULL,
		executed_status VARCHAR(32) NULL,
		executed_at DATETIME NULL,
		created_at DATETIME NOT NULL,
		updated_at DATETIME NULL,
		PRIMARY KEY (id),
		KEY idx_dev (device_id),
		KEY idx_status (status)
	) {$charset};";
	require_once ABSPATH . 'wp-admin/includes/upgrade.php';
	dbDelta($sql);

	// Backfill missing columns on older installs
	$cols = $wpdb->get_results("SHOW COLUMNS FROM {$table}", ARRAY_A) ?: array();
	$names = array_map(function($c){ return $c['Field']; }, $cols);
	if (!in_array('executed_at', $names, true)) {
		$wpdb->query("ALTER TABLE {$table} ADD COLUMN executed_at DATETIME NULL AFTER updated_at");
	}
	if (!in_array('executed_status', $names, true)) {
		$wpdb->query("ALTER TABLE {$table} ADD COLUMN executed_status VARCHAR(32) NULL AFTER status");
	}
	if (!in_array('result', $names, true)) {
		$wpdb->query("ALTER TABLE {$table} ADD COLUMN result LONGTEXT NULL AFTER params");
	}
});

// Enqueue command (from Admin forwarder or local UI)
add_action('rest_api_init', function () {
	register_rest_route('tmon-uc/v1', '/device/command', array(
		'methods'  => 'POST',
		'callback' => function ($req) {
			// Optional: authenticate Admin via X-TMON-HUB
			$shared = isset($_SERVER['HTTP_X_TMON_HUB']) ? sanitize_text_field($_SERVER['HTTP_X_TMON_HUB']) : '';
			$key_opt = get_option('tmon_uc_shared_key');
			if ($shared && (!$key_opt || !hash_equals($key_opt, $shared))) {
				return new WP_Error('forbidden', 'Unauthorized hub', array('status' => 403));
			}
			$device_id = sanitize_text_field($req->get_param('unit_id') ?: $req->get_param('device_id'));
			$cmd = sanitize_text_field($req->get_param('type') ?: $req->get_param('command'));
			$params = $req->get_param('data') ?: $req->get_param('params') ?: array();
			if (!$device_id || !$cmd) {
				return new WP_Error('bad_request', 'unit_id and command required', array('status' => 400));
			}
			global $wpdb;
			$table = $wpdb->prefix . 'tmon_device_commands';
			$wpdb->insert($table, array(
				'device_id' => $device_id,
				'command'   => $cmd,
				'params'    => wp_json_encode($params),
				'status'    => 'queued',
				'created_at'=> current_time('mysql'),
				'updated_at'=> current_time('mysql'),
			));
			return rest_ensure_response(array('status' => 'ok', 'id' => (int)$wpdb->insert_id));
		},
		'permission_callback' => '__return_true',
	));
});

// Compatibility: device polls commands via POST /tmon/v1/device/commands with unit_id
add_action('rest_api_init', function(){
	register_rest_route('tmon/v1', '/device/commands', array(
		'methods' => 'POST',
		'permission_callback' => '__return_true',
		'callback' => function($req){
			global $wpdb;
			$table = $wpdb->prefix . 'tmon_device_commands';
			$unit = sanitize_text_field($req->get_param('unit_id') ?: $req->get_param('device_id'));
			if (!$unit) return rest_ensure_response(array());
			$rows = $wpdb->get_results($wpdb->prepare(
				"SELECT id, command, params FROM {$table} WHERE device_id=%s AND (status='queued' OR status='claimed') ORDER BY id ASC LIMIT 20",
				$unit
			), ARRAY_A);
			if ($rows) {
				$ids = wp_list_pluck($rows, 'id');
				$wpdb->query("UPDATE {$table} SET status='claimed', updated_at=NOW() WHERE id IN (".implode(',', array_map('intval', $ids)).")");
			}
			$cmds = array();
			foreach ($rows as $r) {
				$payload = json_decode($r['params'], true);
				if (!is_array($payload)) { $payload = array(); }
				$cmds[] = array(
					'id' => intval($r['id']),
					'type' => $r['command'],
					'payload' => $payload,
				);
			}
			return rest_ensure_response($cmds);
		}
	));
	register_rest_route('tmon/v1', '/device/command-result', array(
		'methods' => 'POST',
		'permission_callback' => '__return_true',
		'callback' => function($req){
			global $wpdb;
			$table = $wpdb->prefix . 'tmon_device_commands';
			$id = intval($req->get_param('id') ?: $req->get_param('job_id'));
			$status = sanitize_text_field($req->get_param('status') ?: 'done');
			$result = $req->get_param('result');
			if ($id <= 0) return rest_ensure_response(array('status'=>'error','message'=>'id required'));
			$wpdb->update($table, array(
				'status' => $status,
				'executed_status' => $status,
				'updated_at' => current_time('mysql'),
				'executed_at' => current_time('mysql'),
				'result' => is_scalar($result) ? strval($result) : wp_json_encode($result),
			), array('id' => $id));
			return rest_ensure_response(array('status'=>'ok'));
		}
	));
});

// Devices poll for commands (returns queued or claimed for retry)
add_action('rest_api_init', function () {
	register_rest_route('tmon-uc/v1', '/device/commands', array(
		'methods'  => 'POST',
		'callback' => function ($req) {
			$device_id = sanitize_text_field($req->get_param('unit_id') ?: $req->get_param('device_id'));
			if (!$device_id) {
				return new WP_Error('bad_request', 'unit_id required', array('status' => 400));
			}
			global $wpdb;
			$table = $wpdb->prefix . 'tmon_device_commands';
			$rows = $wpdb->get_results($wpdb->prepare(
				"SELECT id, command, params FROM {$table} 
				 WHERE device_id=%s AND (status='queued' OR status='claimed') 
				 ORDER BY id ASC LIMIT 10", $device_id
			), ARRAY_A);
			return rest_ensure_response(array('status' => 'ok', 'commands' => $rows ?: array()));
		},
		'permission_callback' => '__return_true',
	));
});

// Device claims a command (prevents concurrent execution)
add_action('rest_api_init', function () {
	register_rest_route('tmon-uc/v1', '/device/command-claim', array(
		'methods'  => 'POST',
		'callback' => function ($req) {
			$id = intval($req->get_param('id'));
			$device_id = sanitize_text_field($req->get_param('unit_id') ?: $req->get_param('device_id'));
			if ($id <= 0 || !$device_id) {
				return new WP_Error('bad_request', 'id and unit_id required', array('status' => 400));
			}
			global $wpdb;
			$table = $wpdb->prefix . 'tmon_device_commands';
			$updated = $wpdb->update($table, array(
				'status'     => 'claimed',
				'updated_at' => current_time('mysql'),
			), array('id' => $id, 'device_id' => $device_id, 'status' => 'queued'));
			return rest_ensure_response(array('status' => $updated ? 'ok' : 'stale'));
		},
		'permission_callback' => '__return_true',
	));
});

// Device posts execution result (done/failed)
add_action('rest_api_init', function () {
	register_rest_route('tmon-uc/v1', '/device/command-result', array(
		'methods'  => 'POST',
		'callback' => function ($req) {
			$id = intval($req->get_param('id'));
			$status = sanitize_text_field($req->get_param('status') ?: 'done');
			$result = $req->get_param('result') ?: array();
			if ($id <= 0) {
				return new WP_Error('bad_request', 'id required', array('status' => 400));
			}
			global $wpdb;
			$table = $wpdb->prefix . 'tmon_device_commands';
			$wpdb->update($table, array(
				'status'     => in_array($status, array('done','failed','expired'), true) ? $status : 'done',
				'updated_at' => current_time('mysql'),
				'params'     => wp_json_encode(array('result' => $result)),
			), array('id' => $id));
			return rest_ensure_response(array('status' => 'ok'));
		},
		'permission_callback' => '__return_true',
	));
});

// Guard: page callback
if (!function_exists('tmon_uc_commands_page')) {
	function tmon_uc_commands_page() {
		if (!current_user_can('manage_options')) { wp_die(__('Insufficient permissions', 'tmon')); }
		$msgs = array();

		if (isset($_POST['tmon_uc_send_cmd']) && check_admin_referer('tmon_uc_cmd')) {
			$unit = sanitize_text_field($_POST['unit_id']);
			$machine = sanitize_text_field($_POST['machine_id']);
			$type = sanitize_text_field($_POST['cmd_type']);
			$payload = array();
			switch ($type) {
				case 'set_var':
					$payload = array('key' => sanitize_text_field($_POST['var_key']), 'value' => wp_unslash($_POST['var_value']));
					break;
				case 'run_func':
					$payload = array('name' => sanitize_text_field($_POST['func_name']), 'args' => wp_unslash($_POST['func_args']));
					break;
				case 'firmware_update':
					$payload = array('version' => sanitize_text_field($_POST['fw_version']));
					break;
				case 'relay_ctrl':
					$payload = array('relay' => intval($_POST['relay_num']), 'state' => sanitize_text_field($_POST['relay_state']));
					break;
			}
			$res = tmon_uc_send_command($unit, $machine, $type, $payload);
			if (is_wp_error($res)) {
				$msgs[] = array('type' => 'error', 'text' => esc_html($res->get_error_message()));
			} else {
				$msgs[] = array('type' => 'updated', 'text' => __('Command dispatched to Admin hub.', 'tmon'));
			}
		}

		echo '<div class="wrap"><h1>' . esc_html__('TMON UC Commands', 'tmon') . '</h1>';
		foreach ($msgs as $m) {
			echo '<div class="' . esc_attr($m['type']) . ' notice is-dismissible"><p>' . esc_html($m['text']) . '</p></div>';
		}
		echo '<div class="card" style="padding:12px;">';
		echo '<h2>' . esc_html__('Send Command to Device', 'tmon') . '</h2>';
		echo '<form method="post">';
		wp_nonce_field('tmon_uc_cmd');
		echo '<p><label>UNIT_ID <input type="text" name="unit_id" required /></label> ';
		echo '<label>MACHINE_ID <input type="text" name="machine_id" required /></label></p>';
		echo '<p><label>Type ';
		echo '<select name="cmd_type">';
		echo '<option value="set_var">Set Variable</option>';
		echo '<option value="run_func">Run Function</option>';
		echo '<option value="firmware_update">Firmware Update</option>';
		echo '<option value="relay_ctrl">Relay Control</option>';
		echo '</select></label></p>';
		echo '<div id="cmd-fields">';
		echo '<p><label>Variable Key <input type="text" name="var_key" /></label> ';
		echo '<label>Variable Value <input type="text" name="var_value" /></label></p>';
		echo '<p><label>Function Name <input type="text" name="func_name" /></label> ';
		echo '<label>Function Args (JSON) <input type="text" name="func_args" /></label></p>';
		echo '<p><label>Firmware Version <input type="text" name="fw_version" /></label></p>';
		echo '<p><label>Relay # <input type="number" min="1" max="8" name="relay_num" /></label> ';
		echo '<label>State <select name="relay_state"><option value="on">On</option><option value="off">Off</option></select></label></p>';
		echo '</div>';
		submit_button(__('Send Command', 'tmon'), 'primary', 'tmon_uc_send_cmd', false);
		echo '</form></div>';
		echo '</div>';
	}
}

// Guard: submenu registration (unique hook name)
if (!has_action('admin_menu', 'tmon_uc_register_commands_menu')) {
	add_action('admin_menu', 'tmon_uc_register_commands_menu');
	function tmon_uc_register_commands_menu() {
		add_submenu_page(
			'tmon-uc',
			__('TMON UC Commands', 'tmon'),
			__('Commands', 'tmon'),
			'manage_options',
			'tmon-uc-commands',
			'tmon_uc_commands_page'
		);
	}
}

// Optional: minimal executor for relay commands if device runs UC-side helper
// This allows local execution hooks (e.g., GPIO service) to act immediately when claimed.
add_action('tmon_uc_execute_command', function ($device_id, $cmd, $params, $row_id) {
	// ...existing code or integration to your device service...
	// Example stub for relay_ctrl:
	if ($cmd === 'relay_ctrl') {
		// Expected params: { relay: number, state: 'on'|'off', duration_s?: int }
		// Integrate with local relay service or keep for device-side execution.
		do_action('tmon_uc_relay_control', $device_id, intval($params['relay'] ?? 1), sanitize_text_field($params['state'] ?? 'off'), intval($params['duration_s'] ?? 0), $row_id);
	}
}, 10, 4);

// Safety scheduler: mark old 'claimed' commands back to 'queued' if stuck > 5 minutes
if (!wp_next_scheduled('tmon_uc_command_requeue_cron')) {
	wp_schedule_event(time() + 60, 'hourly', 'tmon_uc_command_requeue_cron');
}
add_action('tmon_uc_command_requeue_cron', function () {
	global $wpdb;
	$table = $wpdb->prefix . 'tmon_device_commands';

	// Determine which timestamp column exists and use it safely.
	$cols = $wpdb->get_results("SHOW COLUMNS FROM {$table}", ARRAY_A);
	$names = array_map(function($c){ return $c['Field']; }, $cols ?: []);
	$ts_col = null;
	if (in_array('updated_at', $names, true)) {
		$ts_col = 'updated_at';
	} elseif (in_array('created_at', $names, true)) {
		$ts_col = 'created_at';
	}

	// Only run the requeue if we have a suitable timestamp column.
	if ($ts_col) {
		$wpdb->query(
			$wpdb->prepare(
				"UPDATE {$table} SET status=%s WHERE status=%s AND {$ts_col} < (NOW() - INTERVAL 5 MINUTE)",
				'queued',
				'claimed'
			)
		);
	}
});

// Ensure shortcode or UI button uses the forwarder with consistent payload
if (!function_exists('tmon_uc_send_command')) {
	function tmon_uc_send_command($unit_id, $machine_id, $type, $payload) {
		$admin = get_option('tmon_admin_hub_url'); // UC setting: Admin hub URL
		$key   = get_option('tmon_uc_shared_key');
		if (!$admin || !$key) { return new WP_Error('no_hub', 'Hub not configured'); }
		$url = trailingslashit($admin) . 'wp-json/tmon-admin/v1/uc/forward-command';
		$args = array(
			'headers' => array('Content-Type' => 'application/json', 'X-TMON-HUB' => $key),
			'body'    => wp_json_encode(array(
				'uc_url'  => site_url(),
				'unit_id' => $unit_id,
				'type'    => $type,
				'data'    => $payload, // e.g., {relay, state, duration_s}
			)),
			'timeout' => 15,
			'method'  => 'POST',
		);
		$resp = wp_remote_post($url, $args);
		if (is_wp_error($resp)) { return $resp; }
		if (wp_remote_retrieve_response_code($resp) !== 200) {
			return new WP_Error('cmd_fail', 'Command forward failed');
		}
		return true;
	}
}
