<?php
if (!defined('ABSPATH')) { exit; }

// Canonical command pipeline marker used to disable duplicate legacy handlers.
if (!defined('TMON_UC_COMMANDS_CANONICAL')) {
	define('TMON_UC_COMMANDS_CANONICAL', true);
}

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

// Legacy /tmon/v1 command routes removed; canonical handlers are registered below.

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

if (!function_exists('tmon_uc_enqueue_local_command')) {
	function tmon_uc_enqueue_local_command($unit_id, $command, $payload = array()) {
		global $wpdb;
		$unit_id = sanitize_text_field((string) $unit_id);
		$command = sanitize_text_field((string) $command);
		if ($unit_id === '' || $command === '') {
			return new WP_Error('bad_request', 'unit_id and command are required');
		}
		$table = $wpdb->prefix . 'tmon_device_commands';
		$ok = $wpdb->insert($table, array(
			'device_id' => $unit_id,
			'command' => $command,
			'params' => wp_json_encode(is_array($payload) ? $payload : array()),
			'status' => 'queued',
			'created_at' => current_time('mysql'),
			'updated_at' => current_time('mysql'),
		));
		if (!$ok) {
			return new WP_Error('db_insert_failed', 'Failed to queue command');
		}
		return intval($wpdb->insert_id);
	}
}

// Guard: page callback
if (!function_exists('tmon_uc_commands_page')) {
	function tmon_uc_commands_page() {
		if (!current_user_can('manage_options')) { wp_die(__('Insufficient permissions', 'tmon')); }
		$msgs = array();

		if (isset($_POST['tmon_uc_send_cmd']) && check_admin_referer('tmon_uc_cmd')) {
			$unit = sanitize_text_field($_POST['unit_id'] ?? '');
			$type = sanitize_text_field($_POST['cmd_type']);
			$payload = array();
			switch ($type) {
				case 'set_var':
					$payload = array(
						'key' => sanitize_text_field($_POST['var_key'] ?? ''),
						'value' => wp_unslash($_POST['var_value'] ?? ''),
					);
					break;
				case 'settings_update':
					$raw_json = wp_unslash($_POST['settings_json'] ?? '{}');
					$decoded = json_decode($raw_json, true);
					$payload = is_array($decoded) ? $decoded : array();
					break;
				case 'relay_ctrl':
					$payload = array(
						'relay_num' => intval($_POST['relay_num'] ?? 1),
						'state' => sanitize_text_field($_POST['relay_state'] ?? 'off'),
						'runtime' => strval(intval($_POST['relay_runtime'] ?? 0)),
					);
					break;
				default:
					$payload = array();
					break;
			}
			$queued = tmon_uc_enqueue_local_command($unit, $type, $payload);
			if (is_wp_error($queued)) {
				$msgs[] = array('type' => 'error', 'text' => esc_html($queued->get_error_message()));
			} else {
				$msgs[] = array('type' => 'updated', 'text' => sprintf(__('Command queued locally. ID: %d', 'tmon'), intval($queued)));
			}
		}

		echo '<div class="wrap"><h1>' . esc_html__('TMON UC Commands', 'tmon') . '</h1>';
		foreach ($msgs as $m) {
			echo '<div class="' . esc_attr($m['type']) . ' notice is-dismissible"><p>' . esc_html($m['text']) . '</p></div>';
		}
		echo '<div class="card" style="padding:12px;">';
		echo '<h2>' . esc_html__('Send Command to Device', 'tmon') . '</h2>';
		echo '<p>' . esc_html__('Commands queued here are delivered through the same DB queue polled by firmware.', 'tmon') . '</p>';
		echo '<form method="post">';
		wp_nonce_field('tmon_uc_cmd');
		echo '<p><label>UNIT_ID <input type="text" name="unit_id" required /></label></p>';
		echo '<p><label>Type ';
		echo '<select name="cmd_type" id="tmon-cmd-type">';
		echo '<option value="set_var">Set Variable</option>';
		echo '<option value="settings_update">Settings Update (JSON)</option>';
		echo '<option value="relay_ctrl">Relay Control</option>';
		echo '</select></label></p>';
		echo '<div id="cmd-fields">';
		echo '<p class="tmon-cmd-set-var"><label>Variable Key <input type="text" name="var_key" /></label> ';
		echo '<label>Variable Value <input type="text" name="var_value" /></label></p>';
		echo '<p class="tmon-cmd-settings"><label>Settings JSON <input type="text" class="large-text" name="settings_json" value="{}" /></label></p>';
		echo '<p class="tmon-cmd-relay"><label>Relay # <input type="number" min="1" max="8" name="relay_num" value="1" /></label> ';
		echo '<label>State <select name="relay_state"><option value="on">On</option><option value="off">Off</option></select></label></p>';
		echo '<p class="tmon-cmd-relay"><label>Runtime (s) <input type="number" min="0" step="1" name="relay_runtime" value="0" /></label></p>';
		echo '</div>';
		submit_button(__('Send Command', 'tmon'), 'primary', 'tmon_uc_send_cmd', false);
		echo '</form>';
		echo '<script>(function(){var sel=document.getElementById("tmon-cmd-type");if(!sel){return;}var vis=function(cls,on){var els=document.querySelectorAll(cls);for(var i=0;i<els.length;i++){els[i].style.display=on?"block":"none";}};var sync=function(){var t=sel.value;vis(".tmon-cmd-set-var",t==="set_var");vis(".tmon-cmd-settings",t==="settings_update");vis(".tmon-cmd-relay",t==="relay_ctrl");};sel.addEventListener("change",sync);sync();})();</script>';
		echo '</div>';

		global $wpdb;
		$table = $wpdb->prefix . 'tmon_device_commands';
		$pending = $wpdb->get_results("SELECT id, device_id, command, params, created_at FROM {$table} WHERE status IN ('queued','claimed') ORDER BY id DESC LIMIT 25", ARRAY_A);
		echo '<h2>' . esc_html__('Recent Pending Commands', 'tmon') . '</h2>';
		echo '<table class="widefat striped"><thead><tr><th>ID</th><th>Unit ID</th><th>Command</th><th>Params</th><th>Status</th><th>Created</th></tr></thead><tbody>';
		if ($pending) {
			foreach ($pending as $r) {
				echo '<tr>';
				echo '<td>' . intval($r['id']) . '</td>';
				echo '<td>' . esc_html($r['device_id']) . '</td>';
				echo '<td>' . esc_html($r['command']) . '</td>';
				echo '<td><code>' . esc_html($r['params']) . '</code></td>';
				echo '<td>' . esc_html('pending') . '</td>';
				echo '<td>' . esc_html(tmon_uc_format_mysql_datetime($r['created_at'])) . '</td>';
				echo '</tr>';
			}
		} else {
			echo '<tr><td colspan="6">' . esc_html__('No pending commands.', 'tmon') . '</td></tr>';
		}
		echo '</tbody></table>';
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
	$col = $wpdb->get_var($wpdb->prepare("SHOW COLUMNS FROM {$table} LIKE %s", 'updated_at')) ? 'updated_at' : 'created_at';
	$wpdb->query("UPDATE {$table} SET status='queued' WHERE status='claimed' AND {$col} < (NOW() - INTERVAL 5 MINUTE)");
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

// Unit Connector: basic device commands & confirmations endpoints.
//
// Minimal, backward-compatible handlers:
//  - POST /wp-json/tmon/v1/device/commands  -> returns pending commands for unit_id
//  - POST /wp-json/tmon/v1/device/command-complete -> acknowledges completion
//  - POST /wp-json/tmon/v1/device/ack -> legacy alias to the above
//
// Commands are stored in DB table {$wpdb->prefix}tmon_device_commands.
// Legacy option map support is retained for backward compatibility with older installs.
// Confirmations are appended to option 'tmon_device_command_confirms' for audit/history.

if ( ! function_exists( 'tmon_uc_cmd_confirm_hmac_secret' ) ) {
	function tmon_uc_cmd_confirm_hmac_secret() {
		$opt = (string) get_option( 'tmon_uc_command_confirm_hmac_secret', '' );
		if ( '' === $opt ) {
			$opt = (string) get_option( 'tmon_uc_field_data_hmac_secret', '' );
		}
		if ( '' === $opt && defined( 'TMON_FIELD_DATA_HMAC_SECRET' ) ) {
			$opt = (string) TMON_FIELD_DATA_HMAC_SECRET;
		}
		return $opt;
	}
}

if ( ! function_exists( 'tmon_uc_verify_command_confirm_sig' ) ) {
	function tmon_uc_verify_command_confirm_sig( $params, $unit_id, $job_id, $ok, $status ) {
		$required = (int) get_option( 'tmon_uc_command_confirm_hmac_required', 0 ) === 1;
		$secret = tmon_uc_cmd_confirm_hmac_secret();
		if ( '' === $secret ) {
			return ! $required;
		}

		$sig = isset( $params['sig'] ) ? strtolower( sanitize_text_field( (string) $params['sig'] ) ) : '';
		if ( '' === $sig ) {
			return ! $required;
		}

		$sig_v = isset( $params['sig_v'] ) ? intval( $params['sig_v'] ) : 0;
		if ( 2 !== $sig_v ) {
			return false;
		}

		$sig_ts = isset( $params['sig_ts'] ) ? intval( $params['sig_ts'] ) : 0;
		if ( $sig_ts <= 0 ) {
			return false;
		}
		$max_age = max( 30, intval( get_option( 'tmon_uc_command_confirm_hmac_max_age', 900 ) ) );
		$now = time();
		if ( abs( $now - $sig_ts ) > $max_age ) {
			return false;
		}

		$unit_id = sanitize_text_field( (string) $unit_id );
		$machine_id = isset( $params['machine_id'] ) ? sanitize_text_field( (string) $params['machine_id'] ) : '';
		$job_id = (string) $job_id;
		$status = sanitize_text_field( (string) $status );
		$ok_bit = $ok ? '1' : '0';

		$device_secret = hash( 'sha256', $secret . '|' . $unit_id . '|' . $machine_id );
		$canon = implode( '|', array( $unit_id, $machine_id, $job_id, $ok_bit, $status, (string) $sig_ts ) );
		$digest = hash( 'sha256', $device_secret . '|' . $canon );

		$len = min( strlen( $sig ), strlen( $digest ) );
		if ( $len <= 0 ) {
			return false;
		}
		return hash_equals( substr( $digest, 0, $len ), substr( $sig, 0, $len ) );
	}
}
//
// Register REST routes
add_action( 'rest_api_init', function () {
	register_rest_route( 'tmon/v1', '/device/commands', array(
		'methods'             => 'POST',
		'callback'            => 'tmon_uc_get_device_commands',
		'permission_callback' => '__return_true',
	) );
	register_rest_route( 'tmon/v1', '/device/command-complete', array(
		'methods'             => 'POST',
		'callback'            => 'tmon_uc_handle_command_complete',
		'permission_callback' => '__return_true',
	) );
	// Legacy alias
	register_rest_route( 'tmon/v1', '/device/ack', array(
		'methods'             => 'POST',
		'callback'            => 'tmon_uc_handle_command_complete',
		'permission_callback' => '__return_true',
	) );
} );

// Return pending commands for the given unit (payload: { unit_id: '...' , limit: n })
function tmon_uc_get_device_commands( WP_REST_Request $req ) {
	$params = $req->get_json_params();
	$unit_id = isset( $params['unit_id'] ) ? sanitize_text_field( $params['unit_id'] ) : '';
	$limit = isset( $params['limit'] ) ? intval( $params['limit'] ) : 50;
	if ( ! $unit_id ) {
		return new WP_REST_Response( array( 'error' => 'missing unit_id' ), 400 );
	}
	global $wpdb;
	$table = $wpdb->prefix . 'tmon_device_commands';
	$rows = $wpdb->get_results(
		$wpdb->prepare(
			"SELECT id, command, params FROM {$table} WHERE device_id=%s AND (status='queued' OR status='claimed') ORDER BY id ASC LIMIT %d",
			$unit_id,
			max(1, min(100, $limit))
		),
		ARRAY_A
	);
	$ids = array();
	$out = array();
	foreach ( (array) $rows as $r ) {
		$payload = json_decode( (string) ($r['params'] ?? '{}'), true );
		if ( ! is_array( $payload ) ) {
			$payload = array();
		}
		$id = intval( $r['id'] ?? 0 );
		if ( $id > 0 ) {
			$ids[] = $id;
		}
		$out[] = array(
			'id' => $id,
			'type' => (string) ($r['command'] ?? ''),
			'command' => (string) ($r['command'] ?? ''),
			'payload' => $payload,
			'params' => $payload,
			'data' => $payload,
		);
	}
	if ( ! empty( $ids ) ) {
		$wpdb->query( "UPDATE {$table} SET status='claimed', updated_at=NOW() WHERE id IN (" . implode(',', array_map('intval', $ids)) . ")" );
	}
	return rest_ensure_response( array( 'commands' => $out ) );
}

// Mark command processed for the given unit/job and record confirmation (best-effort, idempotent)
function tmon_uc_mark_command_processed( $unit_id, $job_id, $ok = true, $result = '' ) {
	if ( ! $job_id ) {
		return false;
	}
	$unit_id = $unit_id ? sanitize_text_field( $unit_id ) : '';
	global $wpdb;
	$table = $wpdb->prefix . 'tmon_device_commands';
	$row = $wpdb->get_row( $wpdb->prepare( "SELECT id, params, device_id FROM {$table} WHERE id=%d", intval( $job_id ) ), ARRAY_A );
	if ( $row ) {
		if ( ! $unit_id ) {
			$unit_id = sanitize_text_field( (string) ($row['device_id'] ?? '') );
		}
		$params = json_decode( (string) ($row['params'] ?? '{}'), true );
		if ( ! is_array( $params ) ) {
			$params = array();
		}
		$params['__ok'] = boolval( $ok );
		$params['__result'] = is_scalar( $result ) ? (string) $result : wp_json_encode( $result );
		$wpdb->update(
			$table,
			array(
				'status' => boolval( $ok ) ? 'done' : 'failed',
				'executed_status' => boolval( $ok ) ? 'done' : 'failed',
				'executed_at' => current_time('mysql'),
				'updated_at' => current_time('mysql'),
				'params' => wp_json_encode( $params ),
				'result' => is_scalar( $result ) ? (string) $result : wp_json_encode( $result ),
			),
			array( 'id' => intval( $job_id ) )
		);
	}

	// Legacy option-map confirmation log support for older tooling
	$all = get_option( 'tmon_device_commands', array() );
	if ( isset( $all[ $unit_id ] ) && is_array( $all[ $unit_id ] ) ) {
		foreach ( $all[ $unit_id ] as &$cmd ) {
			if ( (string) ( $cmd['id'] ?? '' ) === (string) $job_id ) {
				$cmd['processed'] = true;
				$cmd['processed_at'] = current_time( 'mysql' );
				$cmd['ok'] = boolval( $ok );
				$cmd['result'] = is_scalar( $result ) ? $result : wp_json_encode( $result );
				break;
			}
		}
		update_option( 'tmon_device_commands', $all );
	}
	// Append to confirms for audit/history
	$confirms = get_option( 'tmon_device_command_confirms', array() );
	$confirms[] = array(
		'unit_id' => $unit_id,
		'job_id'  => (string) $job_id,
		'ok'      => boolval( $ok ),
		'result'  => is_scalar( $result ) ? $result : wp_json_encode( $result ),
		'ts'      => current_time( 'mysql' ),
	);
	update_option( 'tmon_device_command_confirms', $confirms );
	// Allow hooks for other systems to react
	do_action( 'tmon_uc_command_confirmed', $unit_id, $job_id, $ok, $result );
	return true;
}

// REST callback for command-complete / ack endpoints
function tmon_uc_handle_command_complete( WP_REST_Request $req ) {
	$params = $req->get_json_params();
	$job_id = isset( $params['job_id'] ) ? $params['job_id'] : ( isset( $params['command_id'] ) ? $params['command_id'] : '' );
	$unit_id = isset( $params['unit_id'] ) ? sanitize_text_field( $params['unit_id'] ) : '';
	$ok = isset( $params['ok'] ) ? boolval( $params['ok'] ) : false;
	$status = isset( $params['status'] ) ? sanitize_text_field( (string) $params['status'] ) : ( $ok ? 'done' : 'failed' );
	$result = isset( $params['result'] ) ? $params['result'] : '';
	if ( ! $job_id ) {
		return new WP_REST_Response( array( 'error' => 'missing job_id' ), 400 );
	}
	// If unit_id missing, attempt to locate from DB first, then legacy option-map.
	if ( empty( $unit_id ) ) {
		global $wpdb;
		$table = $wpdb->prefix . 'tmon_device_commands';
		$db_row = $wpdb->get_row( $wpdb->prepare( "SELECT device_id FROM {$table} WHERE id=%d", intval( $job_id ) ), ARRAY_A );
		if ( is_array( $db_row ) && ! empty( $db_row['device_id'] ) ) {
			$unit_id = sanitize_text_field( (string) $db_row['device_id'] );
		} else {
			$all = get_option( 'tmon_device_commands', array() );
			foreach ( $all as $u => $list ) {
				foreach ( $list as $cmd ) {
					if ( (string) ( $cmd['id'] ?? '' ) === (string) $job_id ) {
						$unit_id = $u;
						break 2;
					}
				}
			}
		}
	}
	if ( ! tmon_uc_verify_command_confirm_sig( $params, $unit_id, $job_id, $ok, $status ) ) {
		return new WP_REST_Response( array( 'error' => 'invalid_signature' ), 401 );
	}
	tmon_uc_mark_command_processed( $unit_id ?: 'unknown', $job_id, $ok, $result );
	return rest_ensure_response( array( 'status' => 'ok' ) );
}
