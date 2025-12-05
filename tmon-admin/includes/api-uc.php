<?php
if (!defined('ABSPATH')) { exit; }

function tmon_admin_validate_uc_key($request) {
	$key = isset($_SERVER['HTTP_X_TMON_HUB']) ? sanitize_text_field($_SERVER['HTTP_X_TMON_HUB']) : '';
	if (!$key) { return new WP_Error('no_key', 'Missing UC key'); }
	$valid = get_option('tmon_uc_shared_key');
	if (!$valid || !hash_equals($valid, $key)) {
		return new WP_Error('bad_key', 'Invalid UC key');
	}
	return true;
}

add_action('rest_api_init', function () {
	// UC pulls devices (assigned + unassigned)
	register_rest_route('tmon-admin/v1', '/uc/devices', array(
		'methods' => 'GET',
		'callback' => function ($request) {
			$auth = tmon_admin_validate_uc_key($request);
			if (is_wp_error($auth)) { return $auth; }
			global $wpdb;
			$tbl = $wpdb->prefix . 'tmon_devices';
			$rows = $wpdb->get_results("SELECT unit_id, machine_id, unit_name, role, assigned_to_uc FROM $tbl ORDER BY id DESC LIMIT 500", ARRAY_A);
			$out = array();
			foreach ($rows as $r) {
				$out[] = array(
					'unit_id' => $r['unit_id'],
					'machine_id' => $r['machine_id'],
					'unit_name' => $r['unit_name'],
					'role' => $r['role'],
					'assigned' => !empty($r['assigned_to_uc']) ? 1 : 0,
				);
			}
			return rest_ensure_response($out);
		},
		'permission_callback' => '__return_true',
	));

	// UC stages reprovision
	register_rest_route('tmon-admin/v1', '/uc/reprovision', array(
		'methods' => 'POST',
		'callback' => function ($request) {
			$auth = tmon_admin_validate_uc_key($request);
			if (is_wp_error($auth)) { return $auth; }
			$unit_id = sanitize_text_field($request->get_param('unit_id'));
			$machine_id = sanitize_text_field($request->get_param('machine_id'));
			$settings = $request->get_param('settings');
			if (!$unit_id || !$machine_id || !$settings) {
				return new WP_Error('bad_req', 'Missing required params');
			}
			global $wpdb;
			$tbl = $wpdb->prefix . 'tmon_devices';
			$wpdb->update($tbl, array(
				'settings_staged' => wp_json_encode($settings),
				'staged_at' => current_time('mysql'),
			), array('unit_id' => $unit_id, 'machine_id' => $machine_id));
			$queue_tbl = $wpdb->prefix . 'tmon_admin_pending_provision';
			$wpdb->insert($queue_tbl, array(
				'unit_id' => $unit_id,
				'machine_id' => $machine_id,
				'payload' => wp_json_encode($settings),
				'enqueued_at' => current_time('mysql'),
				'type' => 'reprovision'
			));
			if (function_exists('tmon_admin_audit_log')) {
				tmon_admin_audit_log('uc_reprovision', 'UC staged settings', array(
					'unit_id' => $unit_id,
					'machine_id' => $machine_id,
					'extra' => array('settings' => $settings)
				));
			}
			return rest_ensure_response(array('status' => 'ok'));
		},
		'permission_callback' => '__return_true',
	));

	// UC pushes command/variables/functions/firmware update
	register_rest_route('tmon-admin/v1', '/uc/command', array(
		'methods' => 'POST',
		'callback' => function ($request) {
			$auth = tmon_admin_validate_uc_key($request);
			if (is_wp_error($auth)) { return $auth; }
			$unit_id = sanitize_text_field($request->get_param('unit_id'));
			$machine_id = sanitize_text_field($request->get_param('machine_id'));
			$type = sanitize_text_field($request->get_param('type')); // set_var|run_func|firmware_update|relay_ctrl...
			$data = $request->get_param('data'); // arbitrary JSON payload
			if (!$unit_id || !$machine_id || !$type) {
				return new WP_Error('bad_req', 'Missing required params');
			}
			global $wpdb;
			$queue_tbl = $wpdb->prefix . 'tmon_admin_pending_commands';
			$wpdb->insert($queue_tbl, array(
				'unit_id' => $unit_id,
				'machine_id' => $machine_id,
				'type' => $type,
				'payload' => wp_json_encode($data),
				'enqueued_at' => current_time('mysql')
			));
			if (function_exists('tmon_admin_audit_log')) {
				tmon_admin_audit_log('uc_command', $type, array(
					'unit_id' => $unit_id,
					'machine_id' => $machine_id,
					'extra' => array('payload' => $data)
				));
			}
			return rest_ensure_response(array('status' => 'ok'));
		},
		'permission_callback' => '__return_true',
	));
});
