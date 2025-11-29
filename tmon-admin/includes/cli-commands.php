<?php
if (!defined('WP_CLI') || !WP_CLI) return;

if (!function_exists('tmon_admin_cli_queue')) {
	function tmon_admin_cli_queue($args, $assoc_args) {
		global $wpdb;
		$queue = get_option('tmon_admin_pending_provision', []);
		$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';

		WP_CLI::log('Pending queue entries: ' . (is_array($queue) ? count($queue) : 0));
		if (is_array($queue) && !empty($queue)) {
			foreach ($queue as $k => $p) {
				WP_CLI::line(sprintf("Key: %s | requested_at: %s | payload: %s", $k, ($p['requested_at'] ?? ''), wp_json_encode($p)));
			}
		} else {
			WP_CLI::line('No pending entries.');
		}

		WP_CLI::log('');
		WP_CLI::log("Provisioned devices table snapshot (first 50):");

		if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $prov_table))) {
			$rows = $wpdb->get_results("SELECT unit_id,machine_id,status,site_url,unit_name,settings_staged,updated_at FROM {$prov_table} ORDER BY updated_at DESC LIMIT 50", ARRAY_A);
			foreach ($rows as $r) {
				WP_CLI::line(sprintf("unit=%s machine=%s status=%s staged=%s site=%s name=%s updated=%s", $r['unit_id'], $r['machine_id'], $r['status'], intval($r['settings_staged']), $r['site_url'], $r['unit_name'], $r['updated_at']));
			}
		} else {
			WP_CLI::line('Provisioned devices table not found.');
		}
	}
}
WP_CLI::add_command('tmon-admin queue', 'tmon_admin_cli_queue');
