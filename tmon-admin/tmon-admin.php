<?php
/**
 * Plugin Name: TMON Admin
 * Description: Admin dashboard and management tools for TMON Unit Connector and IoT devices.
 * Version: 0.2.0
 * Author: TMON DevOps
 */
/*
README (minimal)

Key endpoints (tmon-admin/v1):
- GET /status — Health check.

Hooks used by Unit Connector:
- filter tmon_admin_authorize_device ($allowed, $unit_id, $machine_id): Return false to block device posts.
- action tmon_admin_receive_field_data ($unit_id, $record): Receive normalized field data for admin workflows.

Provisioning:
- Database table: wp_tmon_provisioned_devices (unit_id, machine_id, company_id, plan, status, notes).
- Admin UI: TMON Admin → Provisioning.
*/

// Ensure ABSPATH is defined
if (!defined('ABSPATH')) exit;

// Define required plugin constants early (fix: undefined constant)
if (!defined('TMON_ADMIN_VERSION')) {
	define('TMON_ADMIN_VERSION', '0.2.0');
}
if (!defined('TMON_ADMIN_PATH')) {
	define('TMON_ADMIN_PATH', plugin_dir_path(__FILE__));
}
if (!defined('TMON_ADMIN_URL')) {
	define('TMON_ADMIN_URL', plugin_dir_url(__FILE__));
}

// Guard include loader to prevent accidental redeclare.
if (!function_exists('tmon_admin_include_files')) {
	function tmon_admin_include_files() {
		require_once TMON_ADMIN_PATH . 'includes/db.php';
		require_once TMON_ADMIN_PATH . 'includes/admin-dashboard.php';
		require_once TMON_ADMIN_PATH . 'includes/settings.php';
		require_once TMON_ADMIN_PATH . 'includes/api.php';

		// Centralized AJAX handlers & CLI diagnostics
		require_once TMON_ADMIN_PATH . 'includes/ajax-handlers.php';
		require_once TMON_ADMIN_PATH . 'includes/cli-commands.php';

		require_once TMON_ADMIN_PATH . 'includes/provisioning.php';
		require_once TMON_ADMIN_PATH . 'includes/ai.php';
		require_once TMON_ADMIN_PATH . 'includes/audit.php';
		require_once TMON_ADMIN_PATH . 'includes/api-uc.php'; // NEW: UC handoff & command endpoints
		require_once TMON_ADMIN_PATH . 'includes/notifications.php';
		require_once TMON_ADMIN_PATH . 'includes/ota.php';
		require_once TMON_ADMIN_PATH . 'includes/files.php';
		require_once TMON_ADMIN_PATH . 'includes/groups.php';
		require_once TMON_ADMIN_PATH . 'includes/custom-code.php';
		require_once TMON_ADMIN_PATH . 'includes/export.php';
		require_once TMON_ADMIN_PATH . 'includes/ai-feedback.php';
		require_once TMON_ADMIN_PATH . 'includes/dashboard-widgets.php';
		require_once TMON_ADMIN_PATH . 'includes/field-data-api.php';
		// Admin pages
		require_once TMON_ADMIN_PATH . 'admin/location.php';
		require_once TMON_ADMIN_PATH . 'admin/firmware.php';
	}
}
tmon_admin_include_files();

// Activation installs/updates DB schema + version.
if (!has_action('activate_' . plugin_basename(__FILE__))) {
	register_activation_hook(__FILE__, function () {
		if (function_exists('tmon_admin_install_schema')) {
			tmon_admin_install_schema();
		}
		update_option('tmon_admin_version', TMON_ADMIN_VERSION);
	});
}

// Upgrade path on version change.
add_action('plugins_loaded', function () {
	$stored = get_option('tmon_admin_version');
	if ($stored !== TMON_ADMIN_VERSION) {
		if (function_exists('tmon_admin_install_schema')) {
			tmon_admin_install_schema();
		}
		update_option('tmon_admin_version', TMON_ADMIN_VERSION);
	}
});

// Enqueue assets; fix localization ($l10n must be an array).
add_action('admin_enqueue_scripts', function () {
	wp_enqueue_style('tmon-admin', TMON_ADMIN_URL . 'assets/admin.css', [], TMON_ADMIN_VERSION);
	wp_enqueue_script('tmon-admin', TMON_ADMIN_URL . 'assets/admin.js', ['jquery'], TMON_ADMIN_VERSION, true);

	$localized = [
		'ajaxUrl' => admin_url('admin-ajax.php'),
		'nonce'   => wp_create_nonce('tmon-admin'),
		// Add REST root and a manifest fetch nonce for admin.js to call the REST endpoint directly
		'restRoot' => esc_url_raw( rest_url() ),
		'restNonce' => wp_create_nonce('wp_rest'),
		'manifestNonce' => wp_create_nonce('tmon_admin_manifest'),
		'provisionNonce' => wp_create_nonce('tmon_admin_provision_ajax'),
	];
	wp_localize_script('tmon-admin', 'TMON_ADMIN', $localized);
});

// Enqueue compact UI assets on TMON Admin pages (provisioning/devices/logs)
add_action('admin_enqueue_scripts', function(){
	$page = isset($_GET['page']) ? $_GET['page'] : '';
	$targets = array('tmon-admin-provisioning','tmon-admin-devices','tmon-admin-command-logs');
	if (in_array($page, $targets, true)) {
		wp_enqueue_style('tmon-admin-core', TMON_ADMIN_URL . 'assets/css/tmon.css', array(), TMON_ADMIN_VERSION);
		wp_enqueue_script('tmon-admin-provision-modal', TMON_ADMIN_URL . 'assets/js/provision-modal.js', array('jquery'), TMON_ADMIN_VERSION, true);
		wp_localize_script('tmon-admin-provision-modal', 'tmonProvisionData', array(
			'ajax_url' => admin_url('admin-ajax.php'),
			'nonce'    => wp_create_nonce('tmon_admin_ajax'),
		));
	}
});

// Command Logs menu and page
add_action('admin_menu', function(){
	add_menu_page('TMON Command Logs', 'TMON Command Logs', 'manage_options', 'tmon-admin-command-logs', function(){
		?>
		<div class="wrap">
			<h1>Command Logs</h1>
			<div class="tmon-filter-form">
				<form id="tmon-command-filter">
					<div>
						<div><label>Unit ID</label><input type="text" name="unit_id" /></div>
						<div>
							<label>Status</label>
							<select name="status">
								<option value="">Any</option>
								<option>staged</option>
								<option>queued</option>
								<option>claimed</option>
								<option>applied</option>
								<option>failed</option>
							</select>
						</div>
						<div>
							<button type="submit" class="button button-primary">Filter</button>
							<a id="tmon-command-export" href="#" class="button">Export CSV</a>
						</div>
					</div>
				</form>
			</div>
			<div class="tmon-responsive-table">
				<table class="wp-list-table widefat striped tmon-stack-table">
					<thead><tr><th>ID</th><th>Unit ID</th><th>Command</th><th>Params</th><th>Status</th><th>Updated</th></tr></thead>
					<tbody id="tmon-command-rows"><tr><td colspan="6">Loading…</td></tr></tbody>
				</table>
			</div>
		</div>
		<script>
		(function($){
			function loadLogs(q, cb){
				$.post(ajaxurl, {
					action: 'tmon_admin_get_command_logs',
					_wpnonce: '<?php echo esc_js( wp_create_nonce('tmon_admin_ajax') ); ?>',
					unit_id: q.unit_id,
					status: q.status
				}, function(res){
					var tb = $('#tmon-command-rows'); tb.empty();
					var rows = (res && res.success && res.data) ? res.data : [];
					if (rows.length){
						rows.forEach(function(r){
							tb.append('<tr><td>'+r.id+'</td><td>'+r.unit_id+'</td><td>'+r.command+'</td><td><code>'+ (r.params||'').replace(/</g,'&lt;') +'</code></td><td><span class="tmon-status-badge tmon-status-'+r.status+'">'+r.status+'</span></td><td>'+r.updated_at+'</td></tr>');
						});
					} else {
						tb.append('<tr><td colspan="6">No records found.</td></tr>');
					}
					if (cb) cb(rows);
				});
			}
			$('#tmon-command-filter').on('submit', function(e){
				e.preventDefault();
				var q = { unit_id: this.unit_id.value.trim(), status: this.status.value };
				loadLogs(q, function(rows){
					$('#tmon-command-export').off('click').on('click', function(ev){
						ev.preventDefault();
						var csv = 'id,unit_id,command,params,status,updated_at\n';
						rows.forEach(function(r){
							var cols = [r.id, r.unit_id, r.command, (r.params||'').replace(/\n/g,' '), r.status, r.updated_at].map(function(x){
								var s = String(x||'').replace(/"/g,'""');
								return '"' + s + '"';
							});
							csv += cols.join(',') + '\n';
						});
						var blob = new Blob([csv], {type:'text/csv'});
						var url = URL.createObjectURL(blob);
						var a = document.createElement('a');
						a.href = url; a.download = 'tmon-command-logs.csv'; a.click();
						URL.revokeObjectURL(url);
					});
				});
			});
			loadLogs({ unit_id: '', status: '' });
		})(jQuery);
		</script>
		<?php
	});
});

// AJAX: Command logs
add_action('wp_ajax_tmon_admin_get_command_logs', function(){
	check_ajax_referer('tmon_admin_ajax');
	if (!current_user_can('manage_options')) {
		wp_send_json_error(array('message' => 'Forbidden'), 403);
	}
	global $wpdb;
	$table = $wpdb->prefix . 'tmon_device_commands';
	$where = '1=1';
	$params = array();

	$unit_id = isset($_POST['unit_id']) ? sanitize_text_field($_POST['unit_id']) : '';
	$status  = isset($_POST['status']) ? sanitize_text_field($_POST['status']) : '';

	if ($unit_id !== '') { $where .= ' AND device_id=%s'; $params[] = $unit_id; }
	if ($status !== '')  { $where .= ' AND status=%s'; $params[] = $status; }

	$sql = "SELECT id, device_id AS unit_id, command, params, status, updated_at FROM {$table} WHERE {$where} ORDER BY updated_at DESC LIMIT 200";
	$rows = $params ? $wpdb->get_results($wpdb->prepare($sql, $params), ARRAY_A) : $wpdb->get_results($sql, ARRAY_A);
	wp_send_json_success($rows ?: array());
});

// Firmware fetch notice (reads transients set by AJAX handler)
add_action('admin_notices', function(){
	if (!current_user_can('manage_options')) return;
	$ver = get_transient('tmon_admin_firmware_version');
	$ts  = get_transient('tmon_admin_firmware_version_ts');
	if ($ver) {
		echo '<div class="notice notice-info"><p>Firmware manifest fetched: version ' . esc_html($ver) . ' at ' . esc_html($ts ?: current_time('mysql')) . '</p></div>';
	}
});

// Admin menu registration (keeps admin pages reachable)
if (!has_action('admin_menu', 'tmon_admin_menu')) {
	add_action('admin_menu', 'tmon_admin_menu');
	function tmon_admin_menu() {
		$notices = get_option('tmon_admin_notifications', []);
		$unread = 0;
		foreach ($notices as $n) { if (empty($n['read'])) $unread++; }
		$menu_title = 'TMON Admin' . ($unread ? ' <span class="update-plugins count-1" style="vertical-align:middle"><span class="plugin-count">'.intval($unread).'</span></span>' : '');

		add_menu_page(
			'TMON Admin',
			$menu_title,
			'manage_options',
			'tmon-admin',
			'tmon_admin_dashboard_page',
			'dashicons-admin-generic',
			2
		);

		add_submenu_page('tmon-admin', 'TMON Settings', 'Settings', 'manage_options', 'tmon-admin-settings', 'tmon_admin_settings_page');
		add_submenu_page('tmon-admin', 'Audit Log', 'Audit Log', 'manage_options', 'tmon-admin-audit', 'tmon_admin_audit_page');
		add_submenu_page('tmon-admin', 'Notifications', 'Notifications', 'manage_options', 'tmon-admin-notifications', 'tmon_admin_notifications_page');
		add_submenu_page('tmon-admin', 'OTA Jobs', 'OTA Jobs', 'manage_options', 'tmon-admin-ota', 'tmon_admin_ota_page');
		add_submenu_page('tmon-admin', 'Files', 'Files', 'manage_options', 'tmon-admin-files', 'tmon_admin_files_page');
		add_submenu_page('tmon-admin', 'Groups', 'Groups', 'manage_options', 'tmon-admin-groups', 'tmon_admin_groups_page');

		// Provisioning: top subpage with children
		add_submenu_page('tmon-admin', 'Provisioning', 'Provisioning', 'manage_options', 'tmon-admin-provisioning', 'tmon_admin_provisioning_page');
		add_submenu_page('tmon-admin', 'Provisioned Devices', 'Provisioned Devices', 'manage_options', 'tmon-admin-provisioned', 'tmon_admin_provisioned_devices_page');
		add_submenu_page('tmon-admin', 'Provisioning Activity', 'Provisioning Activity', 'manage_options', 'tmon-admin-provisioning-activity', 'tmon_admin_provisioning_activity_page');
		add_submenu_page('tmon-admin', 'Provisioning History', 'Provisioning History', 'manage_options', 'tmon-admin-provisioning-history', 'tmon_admin_provisioning_history_page');

		add_submenu_page('tmon-admin', 'Device Location', 'Device Location', 'manage_options', 'tmon-admin-location', 'tmon_admin_location_page');
		add_submenu_page('tmon-admin', 'UC Pairings', 'UC Pairings', 'manage_options', 'tmon-admin-pairings', 'tmon_admin_pairings_page');
	}
}

// Main menu and pages
add_action('admin_menu', function(){
	// Main TMON Admin menu → Dashboard page
	add_menu_page('TMON Admin', 'TMON Admin', 'manage_options', 'tmon-admin-dashboard', 'tmon_admin_dashboard_page', 'dashicons-admin-generic', 58);

	// Submenus
	add_submenu_page('tmon-admin-dashboard', 'Firmware', 'Firmware', 'manage_options', 'tmon-admin-firmware', 'tmon_admin_firmware_page');
	add_submenu_page('tmon-admin-dashboard', 'Provisioning', 'Provisioning', 'manage_options', 'tmon-admin-provisioning', 'tmon_admin_provisioning_page');
	add_submenu_page('tmon-admin-dashboard', 'Provisioned Devices', 'Provisioned Devices', 'manage_options', 'tmon-admin-provisioned', 'tmon_admin_provisioned_devices_page');
	add_submenu_page('tmon-admin-dashboard', 'Provisioning Activity', 'Provisioning Activity', 'manage_options', 'tmon-admin-provisioning-activity', 'tmon_admin_provisioning_activity_page');
	add_submenu_page('tmon-admin-dashboard', 'Provisioning History', 'Provisioning History', 'manage_options', 'tmon-admin-provisioning-history', 'tmon_admin_provisioning_history_page');
	add_submenu_page('tmon-admin-dashboard', 'Notifications', 'Notifications', 'manage_options', 'tmon-admin-notifications', 'tmon_admin_notifications_page');
	add_submenu_page('tmon-admin-dashboard', 'OTA', 'OTA', 'manage_options', 'tmon-admin-ota', 'tmon_admin_ota_page');
	add_submenu_page('tmon-admin-dashboard', 'Files', 'Files', 'manage_options', 'tmon-admin-files', 'tmon_admin_files_page');
	add_submenu_page('tmon-admin-dashboard', 'Groups', 'Groups', 'manage_options', 'tmon-admin-groups', 'tmon_admin_groups_page');
	add_submenu_page('tmon-admin-dashboard', 'Command Logs', 'Command Logs', 'manage_options', 'tmon-admin-command-logs', 'tmon_admin_command_logs_page');
});

// Dashboard renderer
function tmon_admin_dashboard_page(){
	?>
	<div class="wrap">
		<h1>TMON Admin Dashboard</h1>
		<?php if (function_exists('tmon_admin_render_provision_notice')) { tmon_admin_render_provision_notice(); } ?>
		<div class="tmon-grid tmon-grid-2">
			<div class="tmon-card">
				<h2>Registered Unit Connectors</h2>
				<?php tmon_admin_render_uc_list(); ?>
			</div>
			<div class="tmon-card">
				<h2>Device Alerts & Health</h2>
				<?php tmon_admin_render_device_alerts(); ?>
			</div>
			<div class="tmon-card">
				<h2>Logs</h2>
				<div style="max-height:280px; overflow:auto"><?php tmon_admin_render_recent_logs(); ?></div>
			</div>
		</div>
	</div>
	<?php
}

// Firmware page: version, README, downloads
function tmon_admin_firmware_page(){
	$ver = get_transient('tmon_admin_firmware_version');
	$ts  = get_transient('tmon_admin_firmware_version_ts');
	$readme_url = 'https://raw.githubusercontent.com/kevinnutt83/TMON/main/README.md';
	$manifest_url = 'https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/manifest.json';
	$version_txt = 'https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/version.txt';
	$readme = wp_remote_retrieve_body( wp_remote_get($readme_url, ['timeout'=>10]) );
	$manifest = wp_remote_retrieve_body( wp_remote_get($manifest_url, ['timeout'=>10]) );
	?>
	<div class="wrap">
		<h1>TMON Firmware</h1>
		<p>Current version: <strong><?php echo esc_html($ver ?: 'unknown'); ?></strong> (last fetch: <?php echo esc_html($ts ?: 'n/a'); ?>)</p>
		<p>
			<a class="button" href="<?php echo esc_url($version_txt); ?>" target="_blank">version.txt</a>
			<a class="button" href="<?php echo esc_url($manifest_url); ?>" target="_blank">manifest.json</a>
			<a class="button" href="https://github.com/kevinnutt83/TMON/tree/main/micropython" target="_blank">Browse Micropython Repo</a>
		</p>
		<h2>README</h2>
		<div class="tmon-card" style="max-height:480px;overflow:auto;white-space:pre-wrap"><?php echo wp_kses_post( nl2br( esc_html( $readme ?: 'README not available' ) ) ); ?></div>
		<h2>Manifest Files</h2>
		<div class="tmon-card" style="max-height:480px;overflow:auto;white-space:pre"><?php echo wp_kses_post( esc_html( $manifest ?: 'Manifest not available' ) ); ?></div>
	</div>
	<?php
}

// Notifications page
function tmon_admin_notifications_page(){
	?>
	<div class="wrap">
		<h1>Notifications</h1>
		<?php tmon_admin_render_notifications(); ?>
	</div>
	<?php
}

// OTA page
function tmon_admin_ota_page(){
	?>
	<div class="wrap">
		<h1>OTA Management</h1>
		<?php tmon_admin_render_ota_jobs_and_actions(); ?>
	</div>
	<?php
}

// Files page
function tmon_admin_files_page(){
	?>
	<div class="wrap">
		<h1>Device Files</h1>
		<?php tmon_admin_render_files_table(); ?>
	</div>
	<?php
}

// Groups page
function tmon_admin_groups_page(){
	?>
	<div class="wrap">
		<h1>Groups & Hierarchy</h1>
		<?php tmon_admin_render_groups_hierarchy(); ?>
	</div>
	<?php
}

// Provisioning pages (renderers exist in includes/provisioning.php)
function tmon_admin_provisioning_page(){ if (function_exists('tmon_admin_render_provisioning_page')) tmon_admin_render_provisioning_page(); }
function tmon_admin_provisioned_devices_page(){ if (function_exists('tmon_admin_render_provisioned_devices')) tmon_admin_render_provisioned_devices(); else echo '<div class="wrap"><h1>Provisioned Devices</h1><p>Renderer not loaded.</p></div>'; }
function tmon_admin_provisioning_activity_page(){ if (function_exists('tmon_admin_render_provisioning_activity')) tmon_admin_render_provisioning_activity(); else echo '<div class="wrap"><h1>Provisioning Activity</h1><p>Renderer not loaded.</p></div>'; }
function tmon_admin_provisioning_history_page(){ if (function_exists('tmon_admin_render_provisioning_history')) tmon_admin_render_provisioning_history(); else echo '<div class="wrap"><h1>Provisioning History</h1><p>Renderer not loaded.</p></div>'; }

// Command Logs submenu page: delegate to existing implementation
function tmon_admin_command_logs_page(){ do_action('tmon_admin_render_command_logs'); }

// Settings: Clear Audit Log alongside Purge Data
add_action('admin_post_tmon_admin_clear_audit', function(){
	if (!current_user_can('manage_options')) wp_die('Forbidden');
	check_admin_referer('tmon_admin_clear_audit');
	global $wpdb; $tbl = $wpdb->prefix.'tmon_admin_audit';
	$wpdb->query("TRUNCATE TABLE {$tbl}");
	wp_safe_redirect( add_query_arg(array('page'=>'tmon-admin-dashboard','audit'=>'cleared'), admin_url('admin.php')) ); exit;
});

// Audit CSV export
add_action('admin_post_tmon_admin_export_audit', function(){
	if (!current_user_can('manage_options')) wp_die('Forbidden');
	check_admin_referer('tmon_admin_export_audit');
	global $wpdb; $tbl = $wpdb->prefix.'tmon_admin_audit';
	$rows = $wpdb->get_results("SELECT id, actor, action, context, created_at FROM {$tbl} ORDER BY id DESC", ARRAY_A);
	$csv = "id,actor,action,context,created_at\n";
	foreach ($rows as $r) {
		$csv .= '"' . implode('","', array_map(function($v){ return str_replace('"','""', (string)$v); }, $r)) . '"' . "\n";
	}
	header('Content-Type: text/csv'); header('Content-Disposition: attachment; filename="tmon-admin-audit.csv"');
	echo $csv; exit;
});

// Helpers to render UC list and health/logs (stub implementations)
function tmon_admin_render_uc_list(){
	$sites = get_option('tmon_uc_pairings', array());
	if (empty($sites)) { echo '<p>No Unit Connectors paired yet.</p>'; return; }
	echo '<table class="wp-list-table widefat striped"><thead><tr><th>Hub URL</th><th>Normalized</th><th>Paired At</th><th>Read Token</th></tr></thead><tbody>';
	foreach ($sites as $s) {
		echo '<tr><td>'.esc_html($s['hub_url'] ?? '').'</td><td>'.esc_html($s['normalized'] ?? '').'</td><td>'.esc_html($s['paired_at'] ?? '').'</td><td><code>'.esc_html($s['read_token'] ?? '').'</code></td></tr>';
	}
	echo '</tbody></table>';
}
function tmon_admin_render_device_alerts(){
	// Display alerts stub; replace with actual queries
	echo '<ul><li>No alerts.</li></ul>';
}
function tmon_admin_render_recent_logs(){
	// Display recent logs stub; replace with actual logs store
	echo '<pre>Logs will appear here.</pre>';
}

// Ensure schema is present before any UI/REST interaction
add_action('admin_init', function () {
	if (function_exists('tmon_admin_install_schema')) {
		ob_start();
		tmon_admin_install_schema();
		// Drop any unexpected echoes such as “tmon_admin_ensure_columns executed (idempotent).”
		@ob_end_clean();
	}
});
add_action('rest_api_init', function () {
	if (function_exists('tmon_admin_install_schema')) {
		ob_start();
		tmon_admin_install_schema();
		@ob_end_clean();
	}
});

// Minimal audit logger (best-effort) to populate audit entries
if (!function_exists('tmon_admin_audit_log')) {
	function tmon_admin_audit_log($action, $context = null, $args = array()) {
		global $wpdb;
		if (!function_exists('tmon_admin_audit_ensure_tables')) return;
		tmon_admin_audit_ensure_tables();
		$table = $wpdb->prefix . 'tmon_admin_audit';
		$wpdb->insert($table, array(
			'ts' => current_time('mysql'),
			'user_id' => get_current_user_id() ?: null,
			'action' => sanitize_text_field($action),
			'context' => $context ? sanitize_text_field($context) : null,
			'unit_id' => isset($args['unit_id']) ? sanitize_text_field($args['unit_id']) : null,
			'machine_id' => isset($args['machine_id']) ? sanitize_text_field($args['machine_id']) : null,
			'extra' => isset($args['extra']) ? wp_json_encode($args['extra']) : null,
		));
	}
}

// Safe wrappers for pages to avoid critical errors when includes are incomplete
if (!function_exists('tmon_admin_notifications_page')) {
	function tmon_admin_notifications_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>Notifications</h1>';
		echo '<div class="card" style="padding:12px;"><p><em>Page loaded. Ensure includes/notifications.php is active for full features.</em></p></div>';
		echo '</div>';
	}
}
if (!function_exists('tmon_admin_ota_page')) {
	function tmon_admin_ota_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>OTA Jobs</h1>';
		echo '<div class="card" style="padding:12px;"><p><em>Page loaded. Ensure includes/ota.php supplies job listings.</em></p></div>';
		echo '</div>';
	}
}
if (!function_exists('tmon_admin_files_page')) {
	function tmon_admin_files_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>Files</h1>';
		echo '<div class="card" style="padding:12px;"><p><em>Page loaded. Ensure includes/files.php provides handlers.</em></p></div>';
		echo '</div>';
	}
}
if (!function_exists('tmon_admin_groups_page')) {
	function tmon_admin_groups_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		echo '<div class="wrap"><h1>Groups</h1>';
		echo '<div class="card" style="padding:12px;"><p><em>Page loaded. Ensure includes/groups.php provides content.</em></p></div>';
		echo '</div>';
	}
}
if (!function_exists('tmon_admin_pairings_page')) {
	function tmon_admin_pairings_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		$pairings = tmon_admin_uc_pairings_get();

		echo '<div class="wrap"><h1>UC Pairings</h1>';
		echo '<div class="card" style="padding:12px;"><h2 style="margin-top:0;">Registered Unit Connectors</h2>';

		if (empty($pairings)) {
			// If a last UC URL exists, hint that verification is pending
			$uc_guess = get_option('tmon_admin_last_uc_url');
			if ($uc_guess) {
				echo '<p><em>Pairing issued to ' . esc_html($uc_guess) . ' — awaiting verification.</em></p>';
			} else {
				echo '<p><em>No Unit Connectors paired yet.</em></p>';
			}
		} else {
			echo '<table class="widefat striped"><thead><tr>';
			echo '<th>Key ID</th><th>UC URL</th><th>Site Name</th><th>Shared Key</th><th>Created</th><th>Last Verified</th><th>Status</th>';
			echo '</tr></thead><tbody>';
			foreach ($pairings as $key_id => $info) {
				$status = !empty($info['active']) ? 'Active' : 'Awaiting Verify';
				echo '<tr>';
				echo '<td>' . esc_html($key_id) . '</td>';
				echo '<td>' . esc_html($info['uc_url'] ?? $key_id) . '</td>';
				echo '<td>' . esc_html($info['site_name'] ?? '') . '</td>';
				echo '<td><code>' . esc_html($info['key'] ?? '') . '</code></td>';
				echo '<td>' . esc_html($info['created'] ?? '') . '</td>';
				echo '<td>' . esc_html($info['last_verified'] ?? '') . '</td>';
				echo '<td>' . esc_html($status) . '</td>';
				echo '</tr>';
			}
			echo '</tbody></table>';
		}
		echo '</div>';
		echo '</div>';
	}
}

// Working Firmware page: repo info, releases, docs
if (!function_exists('tmon_admin_firmware_page')) {
	function tmon_admin_firmware_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		$repo = get_option('tmon_admin_repo', 'kevinnutt83/TMON');
		$branch = get_option('tmon_admin_repo_branch', 'main');
		$api_base = 'https://api.github.com/repos/' . $repo;
		$raw_base = 'https://raw.githubusercontent.com/' . $repo . '/' . $branch . '/';

		echo '<div class="wrap"><h1>TMON Firmware</h1>';
		echo '<div class="card" style="padding:12px;"><h2 style="margin-top:0;">Repository</h2>';
		$info = wp_remote_get($api_base, array('timeout' => 15, 'headers' => array('User-Agent' => 'TMON Admin')));
		if (!is_wp_error($info) && wp_remote_retrieve_response_code($info) === 200) {
			$meta = json_decode(wp_remote_retrieve_body($info), true);
			echo '<p><strong>Name:</strong> ' . esc_html($meta['full_name']) . '</p>';
			echo '<p><strong>Default branch:</strong> ' . esc_html($meta['default_branch']) . '</p>';
			echo '<p><a class="button button-primary" target="_blank" href="https://github.com/' . esc_attr($repo) . '">Open Repository</a></p>';
		} else {
			echo '<p><em>Unable to load repository metadata.</em></p>';
		}
		echo '</div>';

		echo '<div class="card" style="padding:12px;"><h2 style="margin-top:0;">Releases</h2>';
		$releases = wp_remote_get($api_base . '/releases', array('timeout' => 20, 'headers' => array('User-Agent' => 'TMON Admin')));
		if (!is_wp_error($releases) && wp_remote_retrieve_response_code($releases) === 200) {
			$list = json_decode(wp_remote_retrieve_body($releases), true);
			if (is_array($list) && !empty($list)) {
				echo '<table class="widefat striped"><thead><tr><th>Tag</th><th>Name</th><th>Published</th><th>Assets</th></tr></thead><tbody>';
				foreach ($list as $rel) {
					$assets = array();
					if (!empty($rel['assets'])) {
						foreach ($rel['assets'] as $a) {
							$assets[] = '<a target="_blank" href="' . esc_url($a['browser_download_url']) . '">' . esc_html($a['name']) . '</a>';
						}
					}
					echo '<tr><td>' . esc_html($rel['tag_name']) . '</td><td>' . esc_html($rel['name']) . '</td><td>' . esc_html($rel['published_at'] ?? '') . '</td><td>' . implode(' | ', $assets) . '</td></tr>';
				}
				echo '</tbody></table>';
			} else {
				echo '<p><em>No releases found.</em></p>';
			}
		} else {
			echo '<p><em>Unable to fetch releases.</em></p>';
		}
		echo '</div>';

		echo '<div class="card" style="padding:12px;"><h2 style="margin-top:0;">Documentation</h2>';
		$readme_url = $raw_base . 'README.md';
		$readme = wp_remote_get($readme_url, array('timeout' => 15, 'headers' => array('User-Agent' => 'TMON Admin')));
		echo '<p><a class="button" target="_blank" href="' . esc_url($readme_url) . '">Open README</a></p>';
		if (!is_wp_error($readme) && wp_remote_retrieve_response_code($readme) === 200) {
			$md = wp_remote_retrieve_body($readme);
			echo '<pre style="max-height:300px;overflow:auto;white-space:pre-wrap;">' . esc_html($md) . '</pre>';
		} else {
			echo '<p><em>README not available.</em></p>';
		}
		$ch_url = $raw_base . 'CHANGELOG.md';
		echo '<p><a class="button" target="_blank" href="' . esc_url($ch_url) . '">Open CHANGELOG</a></p>';
		echo '</div>'; // Documentation card
		echo '</div>'; // wrap
	}
}

// Ensure menu callback exists to prevent "invalid function name" fatal
if (!function_exists('tmon_admin_provisioned_devices_page')) {
	function tmon_admin_provisioned_devices_page() {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		if (function_exists('tmon_admin_render_provisioned_devices')) {
			tmon_admin_render_provisioned_devices();
		} else {
			echo '<div class="wrap"><h1>Provisioned Devices</h1><div class="notice notice-warning"><p>Renderer not loaded.</p></div></div>';
		}
	}
}

// Robust AJAX: fetch firmware manifest/version with fallback mirrors and headers to avoid GitHub 400s
add_action('wp_ajax_tmon_admin_fetch_github_manifest', function(){
	if (!current_user_can('manage_options')) wp_send_json_error(['message' => 'Forbidden'], 403);

	$version_urls = [
		'https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/version.txt',
		'https://rawcdn.githack.com/kevinnutt83/TMON/main/micropython/version.txt',
		'https://cdn.jsdelivr.net/gh/kevinnutt83/TMON@main/micropython/version.txt',
	];
	$manifest_urls = [
		'https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/manifest.json',
		'https://rawcdn.githack.com/kevinnutt83/TMON/main/micropython/manifest.json',
		'https://cdn.jsdelivr.net/gh/kevinnutt83/TMON@main/micropython/manifest.json',
	];
	$headers = [
		'User-Agent' => 'TMON-Admin/0.2.x',
		'Accept'     => 'application/json',
	];

	$version = null;
	foreach ($version_urls as $u) {
		$r = wp_remote_get($u, ['timeout' => 15, 'headers' => $headers]);
		if (!is_wp_error($r) && wp_remote_retrieve_response_code($r) === 200) {
			$version = trim(wp_remote_retrieve_body($r));
			if ($version) break;
		}
	}
	$manifest = null;
	foreach ($manifest_urls as $u) {
		$r = wp_remote_get($u, ['timeout' => 15, 'headers' => $headers]);
		if (!is_wp_error($r) && wp_remote_retrieve_response_code($r) === 200) {
			$body = wp_remote_retrieve_body($r);
			$m = json_decode($body, true);
			if (is_array($m)) { $manifest = $m; break; }
		}
	}

	if (!$version || !$manifest) {
		wp_send_json_error(['message' => 'Failed to fetch firmware metadata from GitHub (checked mirrors).'], 400);
	}
	wp_send_json_success(['version' => $version, 'manifest' => $manifest]);
});

// Fallback helpers to avoid fatal errors if UC helper includes are not loaded
if (!function_exists('tmon_admin_uc_pairings_get')) {
	function tmon_admin_uc_pairings_get() {
		$pair = get_option('tmon_uc_pairings', []);
		return is_array($pair) ? $pair : [];
	}
}
if (!function_exists('tmon_admin_uc_pairings_set')) {
	function tmon_admin_uc_pairings_set($pair) {
		return is_array($pair) ? update_option('tmon_uc_pairings', $pair, false) : false;
	}
}
if (!function_exists('tmon_admin_uc_normalize_url')) {
	function tmon_admin_uc_normalize_url($uc_url) {
		$u = trim((string)$uc_url);
		if ($u === '') return '';
		if (!preg_match('#^https?://#i', $u)) $u = 'https://' . $u;
		$parts = parse_url($u);
		if (!$parts || empty($parts['host'])) return '';
		$host = strtolower($parts['host']);
		$port = isset($parts['port']) ? intval($parts['port']) : null;
		return $port ? ($host . ':' . $port) : $host;
	}
}

// UC Pairing endpoint: register UC site and return shared hub key + read token
add_action('rest_api_init', function () {
	register_rest_route('tmon-admin/v1', '/uc/pair', [
		'methods' => 'POST',
		'callback' => function($request){
			$site_url = esc_url_raw($request->get_param('site_url'));
			$uc_key   = sanitize_text_field($request->get_param('uc_key'));
			if (!$site_url || !$uc_key) return new WP_REST_Response(['status'=>'error','message'=>'site_url and uc_key required'], 400);
			$parts = parse_url($site_url);
			$key_id = !empty($parts['host']) ? strtolower($parts['host']) : '';
			if (isset($parts['port'])) $key_id .= ':' . intval($parts['port']);
			if (!$key_id) return new WP_REST_Response(['status'=>'error','message'=>'invalid site_url'], 400);

			$pairings = get_option('tmon_uc_pairings', []);
			if (!is_array($pairings)) $pairings = [];
			$hub_key = isset($pairings[$key_id]['key']) && $pairings[$key_id]['key'] ? $pairings[$key_id]['key'] : wp_generate_password(48, false, false);
			$read_token = isset($pairings[$key_id]['read_token']) && $pairings[$key_id]['read_token'] ? $pairings[$key_id]['read_token'] : wp_generate_password(32, false, false);

			$pairings[$key_id] = [
				'uc_url'       => $site_url,
				'key'          => $hub_key,
				'read_token'   => $read_token,
				'uc_key'       => $uc_key,
				'created'      => current_time('mysql'),
				'last_verified'=> current_time('mysql'),
				'active'       => 1,
			];
			update_option('tmon_uc_pairings', $pairings, false);
			return rest_ensure_response(['status'=>'ok','hub_key'=>$hub_key,'read_token'=>$read_token]);
		},
		'permission_callback' => '__return_true',
	]);
});