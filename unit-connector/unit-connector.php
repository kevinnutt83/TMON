<?php
if (!defined('ABSPATH')) exit;

define('TMON_UC_VERSION', '0.1.0');
define('TMON_UC_DIR', __DIR__);
define('TMON_UC_URL', plugin_dir_url(__FILE__));

require_once TMON_UC_DIR . '/includes/commands.php';
require_once TMON_UC_DIR . '/includes/api.php';

add_action('rest_api_init', function () {
	if (function_exists('tmon_uc_register_rest_routes')) {
		tmon_uc_register_rest_routes();
	}
});

/**
 * Admin assets (relay buttons + other admin UX).
 */
add_action('admin_enqueue_scripts', function () {
	wp_enqueue_script(
		'tmon-uc-admin',
		TMON_UC_URL . 'assets/admin.js',
		['jquery'],
		TMON_UC_VERSION,
		true
	);

	wp_enqueue_style(
		'tmon-uc-admin',
		TMON_UC_URL . 'assets/admin.css',
		[],
		TMON_UC_VERSION
	);

	wp_localize_script('tmon-uc-admin', 'TMON_UC', [
		'ajaxUrl' => admin_url('admin-ajax.php'),
		'nonce'   => wp_create_nonce('tmon_uc_admin'),
	]);
});

/**
 * AJAX: enqueue a relay toggle command for a unit_id.
 * Expects: unit_id, relay (1-8), state (on/off), runtime_s (optional, default 0)
 */
add_action('wp_ajax_tmon_uc_toggle_relay', function () {
	if (!current_user_can('manage_options')) {
		wp_send_json_error(['message' => 'forbidden'], 403);
	}

	check_ajax_referer('tmon_uc_admin', 'nonce');

	$unit_id   = isset($_POST['unit_id']) ? sanitize_text_field(wp_unslash($_POST['unit_id'])) : '';
	$relay     = isset($_POST['relay']) ? sanitize_text_field(wp_unslash($_POST['relay'])) : '';
	$state     = isset($_POST['state']) ? sanitize_text_field(wp_unslash($_POST['state'])) : '';
	$runtime_s = isset($_POST['runtime_s']) ? sanitize_text_field(wp_unslash($_POST['runtime_s'])) : '0';

	if ($unit_id === '' || $relay === '' || $state === '') {
		wp_send_json_error(['message' => 'missing_params'], 400);
	}
	if (!preg_match('/^[1-8]$/', (string)$relay)) {
		wp_send_json_error(['message' => 'invalid_relay'], 400);
	}
	$state = strtolower($state);
	if (!in_array($state, ['on', 'off'], true)) {
		wp_send_json_error(['message' => 'invalid_state'], 400);
	}
	if (!preg_match('/^\d+$/', (string)$runtime_s)) {
		$runtime_s = '0';
	}

	$cmd_id = tmon_uc_enqueue_command($unit_id, 'toggle_relay', [
		// relay.py expects strings: toggle_relay(relay_num, state, runtime)
		'relay_num' => (string)$relay,
		'state'     => (string)$state,
		'runtime'   => (string)$runtime_s,
	]);

	if (!$cmd_id) {
		wp_send_json_error(['message' => 'enqueue_failed'], 500);
	}

	wp_send_json_success([
		'message' => 'queued',
		'unit_id' => $unit_id,
		'command' => 'toggle_relay',
		'command_id' => $cmd_id,
	]);
});
