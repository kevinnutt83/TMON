<?php
if (!defined('ABSPATH')) exit;

// Ensure provisioned_devices table has expected columns even on older installs
function tmon_admin_maybe_migrate_provisioned_devices() {
    global $wpdb;
    $table = $wpdb->prefix . 'tmon_provisioned_devices';
    $exists = $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table));
    if (!$exists) return; // created by installer elsewhere

    $have = [];
    $cols = $wpdb->get_results("SHOW COLUMNS FROM $table", ARRAY_A);
    foreach (($cols?:[]) as $c) { $have[strtolower($c['Field'])] = true; }

    // Add missing columns one by one (id/unit_id/machine_id assumed present)
    if (empty($have['role'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN role VARCHAR(32) DEFAULT 'base'");
    }
    if (empty($have['company_id'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN company_id BIGINT UNSIGNED NULL");
    }
    if (empty($have['plan'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN plan VARCHAR(64) DEFAULT 'standard'");
    }
    if (empty($have['status'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN status VARCHAR(32) DEFAULT 'active'");
    }
    if (empty($have['notes'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN notes TEXT");
    }
    if (empty($have['created_at'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP");
    }
    if (empty($have['updated_at'])) {
        // Some MySQL variants require separate ADD then MODIFY for ON UPDATE
        $wpdb->query("ALTER TABLE $table ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP");
        $wpdb->query("ALTER TABLE $table MODIFY COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP");
    }
    if (empty($have['site_url'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN site_url VARCHAR(255) DEFAULT ''");
    }
    if (empty($have['unit_name'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN unit_name VARCHAR(128) DEFAULT ''");
    }
    // NEW: firmware metadata
    if (empty($have['firmware'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN firmware VARCHAR(128) DEFAULT ''");
    }
    if (empty($have['firmware_url'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN firmware_url VARCHAR(255) DEFAULT ''");
    }
    if (empty($have['settings_staged'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN settings_staged TINYINT(1) DEFAULT 0");
    }
    // NEW: normalized machine/unit ids for consistent matching
    if (empty($have['machine_id_norm'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN machine_id_norm VARCHAR(64) DEFAULT ''");
    }
    if (empty($have['unit_id_norm'])) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN unit_id_norm VARCHAR(64) DEFAULT ''");
    }

    // Backfill existing rows with normalized values (safe, idempotent)
    $rows = $wpdb->get_results("SELECT id, machine_id, unit_id FROM {$table}", ARRAY_A);
    if ($rows) {
        foreach ($rows as $r) {
            $norm_machine = '';
            if (!empty($r['machine_id'])) $norm_machine = tmon_admin_normalize_mac($r['machine_id']);
            $norm_unit = '';
            if (!empty($r['unit_id'])) $norm_unit = tmon_admin_normalize_key($r['unit_id']);
            if ($norm_machine || $norm_unit) {
                $wpdb->update($table, ['machine_id_norm' => $norm_machine, 'unit_id_norm' => $norm_unit], ['id' => intval($r['id'])]);
            }
        }
    }

    // Ensure unique index on (unit_id, machine_id)
    $indexes = $wpdb->get_results("SHOW INDEX FROM $table", ARRAY_A);
    $hasUnitMachineIdx = false;
    foreach (($indexes?:[]) as $idx) {
        if (isset($idx['Key_name']) && $idx['Key_name'] === 'unit_machine') { $hasUnitMachineIdx = true; break; }
    }
    if (!$hasUnitMachineIdx) {
        // Create named unique index if both columns exist
        $colsCheck = $wpdb->get_col("SHOW COLUMNS FROM $table LIKE 'unit_id'");
        $colsCheck2 = $wpdb->get_col("SHOW COLUMNS FROM $table LIKE 'machine_id'");
        if (!empty($colsCheck) && !empty($colsCheck2)) {
            $wpdb->query("ALTER TABLE $table ADD UNIQUE KEY unit_machine (unit_id, machine_id)");
        }
    }
}

add_action('admin_init', function() {
    if (get_option('tmon_admin_schema_provisioned') !== '1') {
        tmon_admin_install_schema();
        update_option('tmon_admin_schema_provisioned', '1');
    }
    // Always run a lightweight migration to avoid 'Unknown column' errors on updated sites
    tmon_admin_maybe_migrate_provisioned_devices();
});

// Migration: ensure tmon_devices has a provisioned column for device mirror status
function tmon_admin_maybe_migrate_tmon_devices() {
    global $wpdb;
    $table = $wpdb->prefix . 'tmon_devices';
    $exists = $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table));
    if (!$exists) return;
    $cols = $wpdb->get_col($wpdb->prepare("SHOW COLUMNS FROM $table LIKE %s", 'provisioned'));
    if (empty($cols)) {
        $wpdb->query("ALTER TABLE $table ADD COLUMN provisioned TINYINT(1) DEFAULT 0");
    }
}
add_action('admin_init', function() {
    // ...existing installation logic ...
    tmon_admin_maybe_migrate_tmon_devices();
});

// DB migration for tmon_devices fields (provisioned/provisioned_at/wordpress_api_url)
function tmon_admin_maybe_migrate_tmon_devices_columns() {
    global $wpdb;
    $table = $wpdb->prefix . 'tmon_devices';
    $exists = $wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table));
    if (!$exists) return;
    $cols = [];
    foreach ($wpdb->get_results("SHOW COLUMNS FROM $table", ARRAY_A) as $c) { $cols[strtolower($c['Field'])] = true; }
    if (empty($cols['provisioned'])) $wpdb->query("ALTER TABLE $table ADD COLUMN provisioned TINYINT(1) DEFAULT 0");
    if (empty($cols['wordpress_api_url'])) $wpdb->query("ALTER TABLE $table ADD COLUMN wordpress_api_url VARCHAR(255) DEFAULT ''");
    if (empty($cols['provisioned_at'])) $wpdb->query("ALTER TABLE $table ADD COLUMN provisioned_at DATETIME DEFAULT NULL");
}
add_action('admin_init', 'tmon_admin_maybe_migrate_tmon_devices_columns');

// Helper: Get all devices, provisioned and unprovisioned
function tmon_admin_get_all_devices() {
    global $wpdb;
    $dev_table = $wpdb->prefix . 'tmon_devices';
    $prov_table = $wpdb->prefix . 'tmon_provisioned_devices';
	// Include provisioned site_url (fallback to d.wordpress_api_url when missing)
	$sql = "SELECT d.id as device_id, d.unit_id, d.machine_id, d.unit_name, d.role as device_role, d.plan as device_plan, d.last_seen, d.wordpress_api_url,
		   p.id as provision_id, p.role, p.company_id, p.plan, p.status, p.notes, p.created_at, p.updated_at,
		   COALESCE(NULLIF(p.site_url,''), d.wordpress_api_url) AS site_url, d.wordpress_api_url AS original_api_url,
		   p.provisioned, p.provisioned_at
		   FROM $dev_table d
		   LEFT JOIN $prov_table p ON d.unit_id = p.unit_id AND d.machine_id = p.machine_id
		   ORDER BY d.id DESC";
	return $wpdb->get_results($sql, ARRAY_A);
}

// Safe getter to avoid undefined index notices
if (!function_exists('tmon_admin_arr_get')) {
	function tmon_admin_arr_get($arr, $key, $default='') {
		return (is_array($arr) && array_key_exists($key, $arr)) ? $arr[$key] : $default;
	}
}

// Notice renderer
if (!function_exists('tmon_admin_render_provision_notice')) {
	function tmon_admin_render_provision_notice() {
		if (!current_user_can('manage_options')) return;
		$state = isset($_GET['provision']) ? sanitize_text_field($_GET['provision']) : '';
		if ($state === 'queued') { echo '<div class="notice notice-success"><p>Provisioning queued and saved.</p></div>'; }
		if ($state === 'failed') { echo '<div class="notice notice-error"><p>Provisioning save failed.</p></div>'; }
	}
}

// Primary Provisioning page renderer
if (!function_exists('tmon_admin_provisioning_page')) {
	function tmon_admin_provisioning_page() {
		tmon_admin_render_provisioning_page();
	}
}
if (!function_exists('tmon_admin_provisioned_devices_page')) {
	function tmon_admin_provisioned_devices_page() {
		if (function_exists('tmon_admin_render_provisioned_devices')) {
			tmon_admin_render_provisioned_devices();
		} else {
			echo '<div class="wrap"><h1>Provisioned Devices</h1><p>Renderer not loaded.</p></div>';
		}
	}
}
if (!function_exists('tmon_admin_provisioning_activity_page')) {
	function tmon_admin_provisioning_activity_page() {
		echo '<div class="wrap"><h1>Provisioning Activity</h1><p>Queue and active jobs appear here.</p></div>';
	}
}
if (!function_exists('tmon_admin_provisioning_history_page')) {
	function tmon_admin_provisioning_history_page() {
		echo '<div class="wrap"><h1>Provisioning History</h1><p>Recent provisioning events will render here.</p></div>';
	}
}

// Safe content renderers (already guarded earlier; keep guards to avoid duplicates)
if (!function_exists('tmon_admin_render_provisioning_page')) {
	function tmon_admin_render_provisioning_page() {
		$all_devices = tmon_admin_get_all_devices();
		$has_devices = !empty($all_devices);
		$table_id = 'tmon-provisioning-devices';
		$form_action = admin_url('admin-post.php');
		$nonce = wp_create_nonce('tmon_admin_provision_device');

		echo '<div class="wrap"><h1>Device Provisioning</h1>';
		tmon_admin_render_provision_notice();
		echo '<p class="description">Manage devices, stage settings, and send provisioning updates from a single view.</p>';
		echo '<nav class="tmon-tabs"><a href="#tmon-prov-list">Devices</a> | <a href="#tmon-prov-form">Save & Provision</a> | <a href="#tmon-prov-history">History</a></nav>';

		echo '<h2 id="tmon-prov-list">Devices</h2>';
		echo '<p class="description">If registrations are missing, ensure devices table exists and mirrors provisioned records. This list includes staged/provisioned flags.</p>';
		echo '<table class="wp-list-table widefat striped" id="'.esc_attr($table_id).'">';
		echo '<thead><tr>';
		echo '<th>ID</th><th>Unit ID</th><th>Machine ID</th><th>Name</th><th>Plan</th><th>Status</th><th>Site</th><th>Staged</th><th>Provisioned</th><th>Last Seen</th><th>Created</th><th>Updated</th>';
		echo '</tr></thead><tbody>';
		if ($has_devices) {
			foreach ($all_devices as $r) {
				$id          = tmon_admin_arr_get($r, 'id', 0);
				$unit_id     = tmon_admin_arr_get($r, 'unit_id', '');
				$machine_id  = tmon_admin_arr_get($r, 'machine_id', '');
				$name        = tmon_admin_arr_get($r, 'unit_name', '');
				$plan        = tmon_admin_arr_get($r, 'plan', tmon_admin_arr_get($r, 'device_plan', ''));
				$status      = tmon_admin_arr_get($r, 'status', '');
				$site_url    = tmon_admin_arr_get($r, 'site_url', '');
				$staged_raw  = tmon_admin_arr_get($r, 'settings_staged', '');
				$staged_flag = $staged_raw ? 'Yes' : 'No';
				$prov_flag   = tmon_admin_arr_get($r, 'provisioned', 0) ? 'Yes' : 'No';
				$last_seen   = tmon_admin_arr_get($r, 'last_seen', '');
				$created_at  = tmon_admin_arr_get($r, 'created_at', '');
				$updated_at  = tmon_admin_arr_get($r, 'updated_at', '');
				echo '<tr>';
				echo '<td>'.intval($id).'</td>';
				echo '<td>'.esc_html($unit_id).'</td>';
				echo '<td>'.esc_html($machine_id).'</td>';
				echo '<td>'.esc_html($name).'</td>';
				echo '<td>'.esc_html($plan).'</td>';
				echo '<td>'.esc_html($status).'</td>';
				echo '<td>'.esc_html($site_url).'</td>';
				echo '<td>'.esc_html($staged_flag).'</td>';
				echo '<td>'.esc_html($prov_flag).'</td>';
				echo '<td>'.esc_html($last_seen).'</td>';
				echo '<td>'.esc_html($created_at).'</td>';
				echo '<td>'.esc_html($updated_at).'</td>';
				echo '</tr>';
			}
		} else {
			echo '<tr><td colspan="11"><em>No devices found. Use "Save & Provision" to add new devices.</em></td></tr>';
		}
		echo '</tbody></table>';

		echo '<h2 id="tmon-prov-form">Save & Provision</h2>';
		echo '<details open class="tmon-card"><summary>Enter device details</summary>';
		echo '<form method="post" action="'.esc_url($form_action).'">';
		echo '<input type="hidden" name="action" value="tmon_admin_provision_device">';
		echo '<input type="hidden" name="_wpnonce" value="'.esc_attr($nonce).'">';
		echo '<input type="hidden" name="id" value="">';
		echo '<table class="form-table">';
		echo '<tr><th scope="row"><label for="unit_id">Unit ID</label></th><td><input name="unit_id" type="text" id="unit_id" value="" class="regular-text" required><p class="description">Unique identifier (serial/assigned ID).</p></td></tr>';
		echo '<tr><th scope="row"><label for="machine_id">Machine ID</label></th><td><input name="machine_id" type="text" id="machine_id" value="" class="regular-text" required><p class="description">MAC or hardware ID.</p></td></tr>';
		echo '<tr><th scope="row"><label for="unit_name">Device Name</label></th><td><input name="unit_name" type="text" id="unit_name" value="" class="regular-text"></td></tr>';
		echo '<tr><th scope="row"><label for="plan">Plan</label></th><td><input name="plan" type="text" id="plan" value="" class="regular-text" placeholder="standard"></td></tr>';
		echo '<tr><th scope="row"><label for="role">Role</label></th><td><input name="role" type="text" id="role" value="" class="regular-text" placeholder="base"></td></tr>';
		echo '<tr><th scope="row"><label for="site_url">Site URL</label></th><td><input name="site_url" type="url" id="site_url" value="" class="regular-text" placeholder="https://example.com"></td></tr>';
		echo '<tr><th scope="row"><label for="settings_staged">Stage settings</label></th><td><label><input name="settings_staged" type="checkbox" id="settings_staged" value="1"> Mark settings as staged for next push</label></td></tr>';
		echo '</table>';
		echo '<p class="submit"><input type="submit" name="save_provision" id="save_provision" class="button button-primary" value="Save & Provision"></p>';
		echo '</form>';
		echo '</details>';

		echo '<h2 id="tmon-prov-history">Provisioning History</h2>';
		echo '<p><a href="'.esc_url(admin_url('admin.php?page=tmon-admin-provisioning-history')).'" class="button">View Provisioning History</a></p>';

		echo '</div>';

		add_action('admin_footer', function() use ($table_id) {
			?>
			<script>
			jQuery(document).ready(function($) {
				$('#<?php echo esc_js($table_id); ?>').DataTable({
					order: [[0, 'desc']],
					columnDefs: [{ visible: false, targets: [0] }]
				});
			});
			</script>
			<?php
		});
	}
}
if (!function_exists('tmon_admin_render_provisioned_devices')) {
	function tmon_admin_render_provisioned_devices() {
		// ...existing code...
	}
}
if (!function_exists('tmon_admin_render_provisioning_activity')) {
	function tmon_admin_render_provisioning_activity() {
		$nonce = wp_create_nonce('tmon_admin_ajax');
		// ...existing code...
	}
}
if (!function_exists('tmon_admin_render_provisioning_history')) {
	function tmon_admin_render_provisioning_history() {
		$nonce = wp_create_nonce('tmon_admin_ajax');
		// ...existing code...
	}
}

// --- PATCH: Handle POST with redirect-after-POST pattern ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && function_exists('tmon_admin_verify_nonce') && tmon_admin_verify_nonce('tmon_admin_provision')) {
    $action = sanitize_text_field($_POST['action'] ?? '');
    $do_provision = isset($_POST['save_provision']);
    $redirect_url = remove_query_arg(['provision'], wp_get_referer() ?: admin_url('admin.php?page=tmon-admin-provisioning'));

    // --- UPDATE DEVICE ROW (table row form) ---
    if ($action === 'update') {
        $id = intval($_POST['id'] ?? 0);
        // Load DB row early to provide fallback values for payloads & mirroring
        $row_tmp = [];
        if ($id > 0) {
            $row_tmp = $wpdb->get_row($wpdb->prepare("SELECT * FROM {$prov_table} WHERE id = %d LIMIT 1", $id), ARRAY_A) ?: [];
        }
        // Compute normalized or fallback ids for the row
        $unit_id = sanitize_text_field($_POST['unit_id'] ?? $row_tmp['unit_id'] ?? '');
        $machine_id = sanitize_text_field($_POST['machine_id'] ?? $row_tmp['machine_id'] ?? '');
        // Ensure we have a value for unit_name (use posted or fallback to DB row)
        $unit_name = sanitize_text_field($_POST['unit_name'] ?? $row_tmp['unit_name'] ?? '');
        $unit_norm = tmon_admin_normalize_key($unit_id);
        $mac_norm = tmon_admin_normalize_mac($machine_id);

        // Ensure $exists is defined for this branch (look up by keys)
        // $exists is computed later and update/insert logic handled below; no direct $data upsert here.
  
         // Always set these so later mirror updates have canonical id vars
         $row_unit_id = $unit_id;
         $row_machine_id = $machine_id;
  
        // Update staged flags using normalized columns
        if ($do_provision) {
            if (!empty($mac_norm)) {
                $wpdb->update($prov_table, ['settings_staged'=>1,'updated_at'=>current_time('mysql')], ['machine_id_norm' => $mac_norm]);
            } else {
                $wpdb->update($prov_table, ['settings_staged'=>1,'updated_at'=>current_time('mysql')], ['unit_id_norm' => $unit_norm]);
            }
        }

        // --- INSERT/UPDATE DEVICE HISTORY RECORD ---
        // Always log provisioning attempts, even for existing devices
        $history_data = [
            'unit_id' => $unit_id,
            'machine_id' => $machine_id,
            'action' => $do_provision ? 'save_provision' : 'update',
            'user' => wp_get_current_user()->user_login,
            'meta' => [
                'plan' => sanitize_text_field($_POST['plan'] ?? ''),
                'role' => sanitize_text_field($_POST['role'] ?? ''),
                'site_url' => esc_url_raw($_POST['site_url'] ?? ''),
                'settings_staged' => !empty($_POST['settings_staged']) ? 1 : 0,
            ],
        ];
        tmon_admin_append_provision_history($history_data);

        // --- REDIRECT AFTER SAVE ---
        // Redirect to the same page with a success flag
        wp_safe_redirect(add_query_arg(['provision' => 'saved'], $redirect_url));
        exit;
    }
}

// CSV export for provisioning history
add_action('admin_init', function(){
	if (!current_user_can('manage_options')) return;
	if (isset($_GET['page']) && $_GET['page']==='tmon-admin-provisioning' && isset($_GET['export']) && $_GET['export']==='provision-history') {
		global $wpdb;
		$table = $wpdb->prefix . 'tmon_provision_history';
		$rows = $wpdb->get_results("SELECT id, unit_id, machine_id, action, user, created_at FROM {$table} ORDER BY id DESC LIMIT 1000", ARRAY_A) ?: array();
		header('Content-Type: text/csv');
		header('Content-Disposition: attachment; filename="tmon-provision-history.csv"');
		$out = fopen('php://output', 'w');
		fputcsv($out, array('id','unit_id','machine_id','action','user','created_at'));
		foreach ($rows as $r) { fputcsv($out, array($r['id'],$r['unit_id'],$r['machine_id'],$r['action'],$r['user'],$r['created_at'])); }
		fclose($out);
		exit;
	}
});

// Ensure firmware metadata transients are set when manifest fetch succeeds
add_action('wp_ajax_tmon_admin_fetch_github_manifest', function(){
	// ...existing fetch code...
	// On success:
	// set_transient('tmon_admin_firmware_version', $version, 12 * HOUR_IN_SECONDS);
	// set_transient('tmon_admin_firmware_version_ts', current_time('mysql'), 12 * HOUR_IN_SECONDS);
	if (!empty($version) && !empty($manifest)) {
		set_transient('tmon_admin_firmware_version', $version, 12 * HOUR_IN_SECONDS);
		set_transient('tmon_admin_firmware_version_ts', current_time('mysql'), 12 * HOUR_IN_SECONDS);
		wp_send_json_success(['version'=>$version,'manifest'=>$manifest]);
	}
	wp_send_json_error(['message'=>'Failed to fetch firmware metadata'], 400);
});

// Save & Provision — persist and log, then redirect with notice
add_action('admin_post_tmon_admin_provision_device', function(){
	if (!current_user_can('manage_options')) wp_die('Forbidden');
	check_admin_referer('tmon_admin_provision_device');
	global $wpdb;
	tmon_admin_ensure_table();

	$unit_id    = sanitize_text_field(isset($_POST['unit_id']) ? $_POST['unit_id'] : '');
	$machine_id = sanitize_text_field(isset($_POST['machine_id']) ? $_POST['machine_id'] : '');
	$unit_name  = sanitize_text_field(isset($_POST['unit_name']) ? $_POST['unit_name'] : '');
	$plan       = sanitize_text_field(isset($_POST['plan']) ? $_POST['plan'] : '');
	$role       = sanitize_text_field(isset($_POST['role']) ? $_POST['role'] : '');
	$site_url   = esc_url_raw(isset($_POST['site_url']) ? $_POST['site_url'] : '');
	$settings_staged = isset($_POST['settings_staged']) ? wp_unslash($_POST['settings_staged']) : '';

	$ok = false;
	if ($unit_id && $machine_id) {
		$prov = $wpdb->prefix . 'tmon_provisioned_devices';
		$wpdb->query($wpdb->prepare(
			"INSERT INTO {$prov} (unit_id,machine_id,unit_name,plan,role,site_url,settings_staged,status,created_at,updated_at)
			 VALUES (%s,%s,%s,%s,%s,%s,%s,'queued',NOW(),NOW())
			 ON DUPLICATE KEY UPDATE unit_name=VALUES(unit_name), plan=VALUES(plan), role=VALUES(role),
			 site_url=VALUES(site_url), settings_staged=VALUES(settings_staged), status='queued', updated_at=NOW()",
			$unit_id, $machine_id, $unit_name, $plan, $role, $site_url, $settings_staged
		));
		$dev = $wpdb->prefix . 'tmon_devices';
		$wpdb->query($wpdb->prepare(
			"UPDATE {$dev} SET unit_name=%s, plan=%s, role=%s, wordpress_api_url=%s WHERE unit_id=%s OR machine_id=%s",
			$unit_name, $plan, $role, $site_url, $unit_id, $machine_id
		));
		tmon_admin_append_provision_history(array(
			'user' => wp_get_current_user()->user_login,
			'unit_id' => $unit_id,
			'machine_id' => $machine_id,
			'action' => 'save_and_provision',
			'meta' => array('unit_name'=>$unit_name,'plan'=>$plan,'role'=>$role,'site_url'=>$site_url),
		));
		$ok = true;
	}

	$redir = wp_get_referer() ?: admin_url('admin.php?page=tmon-admin-provisioning');
	wp_safe_redirect(add_query_arg(array('provision' => $ok ? 'queued' : 'failed'), $redir));
	exit;
});

// Admin REST — device confirm-applied: update records + history
add_action('rest_api_init', function(){
	register_rest_route('tmon-admin/v1', '/device/confirm-applied', array(
		'methods' => 'POST',
		'callback' => function($request){
			$unit_id    = sanitize_text_field($request->get_param('unit_id'));
			$machine_id = sanitize_text_field($request->get_param('machine_id'));
			$site_url   = esc_url_raw($request->get_param('wordpress_api_url'));
			$role       = sanitize_text_field($request->get_param('role'));
			$plan       = sanitize_text_field($request->get_param('plan'));
			$firmware   = sanitize_text_field($request->get_param('firmware_version'));
			global $wpdb;
			$dev_table  = $wpdb->prefix . 'tmon_devices';
			$prov_table = $wpdb->prefix . 'tmon_provisioned_devices';

			// Mirror updates
			if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $dev_table))) {
				$mirror = array('provisioned'=>1, 'last_seen'=>current_time('mysql'));
				if ($site_url) $mirror['wordpress_api_url'] = $site_url;
				if ($plan)     $mirror['plan'] = $plan;
				if ($role)     $mirror['role'] = $role;
				$wpdb->update($dev_table, $mirror, array('unit_id' => $unit_id));
				$wpdb->update($dev_table, $mirror, array('machine_id' => $machine_id));
			}
			if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $prov_table))) {
				$upd = array('status'=>'active','site_url'=>$site_url,'updated_at'=>current_time('mysql'));
				if ($plan)     $upd['plan'] = $plan;
				if ($role)     $upd['role'] = $role;
				if ($firmware) $upd['firmware'] = $firmware;
				$wpdb->update($prov_table, $upd, array('unit_id' => $unit_id));
				$wpdb->update($prov_table, $upd, array('machine_id' => $machine_id));
			}

			return rest_ensure_response(true);
		},
	));
});

// Guard undefined array keys when reading queue/device arrays
function tmon_admin_arr_get($arr, $key, $default=''){ return isset($arr[$key]) ? $arr[$key] : $default; }

// Use tmon_admin_arr_get() where provisioning code reads $row['id'] or $row['settings_staged']
// Example:
// $id = tmon_admin_arr_get($row, 'id', 0);
// $staged = tmon_admin_arr_get($row, 'settings_staged', '{}');
