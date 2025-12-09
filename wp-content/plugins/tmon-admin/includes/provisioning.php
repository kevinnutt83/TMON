<?php
// TMON Admin — Provisioning

add_action('tmon_admin_provisioning_page', function () {
	static $printed = false; if ($printed) return; $printed = true;

	$device_id = isset($_GET['id']) ? sanitize_text_field(wp_unslash($_GET['id'])) : '';
	$settings_staged = [];
	if (isset($_POST['settings_staged'])) {
		$raw = wp_unslash($_POST['settings_staged']);
		if (is_string($raw)) {
			$tmp = json_decode($raw, true);
			if (is_array($tmp)) { $settings_staged = $tmp; }
		} elseif (is_array($raw)) {
			$settings_staged = $raw;
		}
	}

	echo '<div class="wrap tmon-wrap"><h1>Provisioning</h1>';
	echo '<style>.tmon-provision-container{max-width:100%;overflow:auto}.tmon-table-section{margin-top:16px}</style>';
	echo '<div class="tmon-provision-container">';

	echo '<div class="tmon-table-section"></div>';

	echo '<div class="tmon-table-section"></div>';

	echo '</div></div>';
});

add_action('tmon_admin_provisioning_history_page', function () {
	static $printed = false; if ($printed) return; $printed = true;
});
add_action('tmon_admin_provisioning_activity_page', function () {
	static $printed = false; if ($printed) return; $printed = true;
});