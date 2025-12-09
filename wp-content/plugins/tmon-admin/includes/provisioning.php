<?php
// TMON Admin — Provisioning

add_action('tmon_admin_provisioning_page', function () {
	static $printed = false; if ($printed) return; $printed = true;

	$id = isset($_GET['id']) ? sanitize_text_field(wp_unslash($_GET['id'])) : '';
	$settings_staged = [];
	if (isset($_POST['settings_staged'])) {
		$raw = wp_unslash($_POST['settings_staged']);
		if (is_string($raw)) {
			$decoded = json_decode($raw, true);
			if (is_array($decoded)) $settings_staged = $decoded;
		} elseif (is_array($raw)) {
			$settings_staged = $raw;
		}
	}

	echo '<div class="wrap tmon-wrap"><h1>Provisioning</h1>';
	echo '<div class="tmon-provision-container">';

	// ...existing code that renders the Save & Provision form...

	// Begin unprovisioned devices table (wrapped)
	echo '<div class="tmon-table-section">';
	// ...existing code to render Unprovisioned table...
	echo '</div>';

	// Begin provisioned devices table (wrapped)
	echo '<div class="tmon-table-section">';
	// ...existing code to render Provisioned table...
	echo '</div>';

	echo '</div></div>'; // close container and wrap
});

// History and Activity pages should not double-render
add_action('tmon_admin_provisioning_history_page', function () {
	static $printed = false; if ($printed) return; $printed = true;
	// ...existing code that prints the history table once...
});
add_action('tmon_admin_provisioning_activity_page', function () {
	static $printed = false; if ($printed) return; $printed = true;
	// ...existing code that prints the activity table once...
});

// ...existing code...