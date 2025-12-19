<?php
// Simple admin UI to enqueue a device command

// Guard: sender helper
if (!function_exists('tmon_uc_send_command')) {
	function tmon_uc_send_command($unit_id, $machine_id, $type, $payload) {
		// ...existing code...
	}
}

// Guard: page callback
if (!function_exists('tmon_uc_commands_page')) {
	function tmon_uc_commands_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h2>Device Commands</h2>';
		if (isset($_POST['tmon_uc_send_command'])) {
			check_admin_referer('tmon_uc_send_command');
			$unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
			$command = sanitize_text_field($_POST['command'] ?? '');
			$params_raw = wp_unslash($_POST['params'] ?? '{}');
			$params = json_decode($params_raw, true);
			if (!is_array($params)) $params = [];
			if ($unit_id && $command) {
				global $wpdb;
				$wpdb->insert(
					$wpdb->prefix . 'tmon_device_commands',
					[
						'device_id' => $unit_id,
						'command' => $command,
						'params' => wp_json_encode($params),
						'created_at' => current_time('mysql'),
						'status' => 'queued',
					]
				);
				echo '<div class="updated"><p>Command enqueued. ID: '.intval($wpdb->insert_id).'</p></div>';
			} else {
				echo '<div class="error"><p>Missing unit_id or command.</p></div>';
			}
		}
		echo '<form method="post">';
		wp_nonce_field('tmon_uc_send_command');
		echo '<table class="form-table">';
		echo '<tr><th scope="row"><label>Unit ID</label></th><td><input type="text" name="unit_id" class="regular-text" required></td></tr>';
			echo '<tr><th scope="row"><label>Command</label></th><td>';
			echo '<select name="command" id="tmon-command">';
			echo '<option value="toggle_relay" selected>toggle_relay</option>';
			echo '<option value="settings_update">settings_update</option>';
			echo '<option value="set_oled_message">set_oled_message</option>';
			echo '<option value="set_oled_banner">set_oled_banner</option>';
			echo '<option value="clear_oled">clear_oled</option>';
			echo '</select>';
			echo '</td></tr>';
			echo '<tr><th scope="row"><label>Params (JSON)</label></th><td><textarea name="params" rows="5" class="large-text" id="tmon-params">{"relay_num":"1","state":"on","runtime":"5"}</textarea><p class="description">For settings_update, provide a JSON object of settings keys to update, e.g. {"FIELD_DATA_SEND_INTERVAL":60}</p></td></tr>';
		echo '</table>';
		submit_button('Send Command', 'primary', 'tmon_uc_send_command');
		echo '</form>';
		echo <<<HTML
		<script>(function(){
			const cmd = document.getElementById("tmon-command");
			const params = document.getElementById("tmon-params");
			function update(){
				if(cmd.value === 'settings_update'){
					params.value = JSON.stringify({FIELD_DATA_SEND_INTERVAL: 60}, null, 0);
				} else if(cmd.value === 'set_oled_message'){
					params.value = JSON.stringify({message: "Hello from WP", duration: 5}, null, 0);
				} else if(cmd.value === 'set_oled_banner'){
					params.value = JSON.stringify({message: "Status: OK", duration: 5, persist: true}, null, 0);
				} else if(cmd.value === 'clear_oled'){
					params.value = JSON.stringify({}, null, 0);
				} else {
					params.value = JSON.stringify({relay_num:"1", state:"on", runtime:"5"}, null, 0);
				}
			}
			cmd.addEventListener('change', update);
			update();
		})();</script>
		HTML;

		echo '<h3>Recent Pending Commands</h3>';
		global $wpdb;
		$rows = $wpdb->get_results("SELECT id, device_id, command, params, created_at FROM {$wpdb->prefix}tmon_device_commands WHERE status='queued' ORDER BY id DESC LIMIT 20", ARRAY_A);
		echo '<table class="widefat"><thead><tr><th>ID</th><th>Unit ID</th><th>Command</th><th>Params</th><th>Created</th></tr></thead><tbody>';
		foreach ($rows as $r) {
			echo '<tr>';
			echo '<td>'.intval($r['id']).'</td>';
			echo '<td>'.esc_html($r['device_id']).'</td>';
			echo '<td>'.esc_html($r['command']).'</td>';
			echo '<td><code>'.esc_html($r['params']).'</code></td>';
			echo '<td>'.esc_html(tmon_uc_format_mysql_datetime($r['created_at'])).'</td>';
			echo '</tr>';
		}
		echo '</tbody></table>';

		echo '<h3>Recent Executed Commands</h3>';
		$rows2 = $wpdb->get_results("SELECT id, device_id, command, params, created_at, executed_at FROM {$wpdb->prefix}tmon_device_commands WHERE status='executed' ORDER BY id DESC LIMIT 20", ARRAY_A);
		echo '<table class="widefat"><thead><tr><th>ID</th><th>Unit ID</th><th>Command</th><th>Result</th><th>Created</th><th>Executed</th></tr></thead><tbody>';
		foreach ($rows2 as $r) {
			$p = json_decode($r['params'], true);
			$ok = is_array($p) && array_key_exists('__ok', $p) ? ($p['__ok'] ? 'OK' : 'FAIL') : '';
			$res = is_array($p) && array_key_exists('__result', $p) ? $p['__result'] : '';
			echo '<tr>';
			echo '<td>'.intval($r['id']).'</td>';
			echo '<td>'.esc_html($r['device_id']).'</td>';
			echo '<td>'.esc_html($r['command']).'</td>';
			echo '<td>'.esc_html($ok . ($res? (" - ".$res) : "" )).'</td>';
			echo '<td>'.esc_html(tmon_uc_format_mysql_datetime($r['created_at'])).'</td>';
			echo '<td>'.esc_html(tmon_uc_format_mysql_datetime($r['executed_at'])).'</td>';
			echo '</tr>';
		}
		echo '</tbody></table>';
		echo '</div>';
	}
}

// Guard: submenu registration (separate function name to avoid collision)
if (!has_action('admin_menu', 'tmon_uc_register_commands_menu_admin')) {
	add_action('admin_menu', 'tmon_uc_register_commands_menu_admin');
	function tmon_uc_register_commands_menu_admin() {
		// Only register once; if includes already added, this will reuse the same slug without redefining
		if (function_exists('tmon_uc_commands_page')) {
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
}
