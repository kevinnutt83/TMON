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
    $sql = "SELECT d.unit_id, d.machine_id, d.unit_name, p.id as provision_id, p.role, p.company_id, p.plan, p.status, p.notes, p.created_at, p.updated_at, 
            COALESCE(NULLIF(p.site_url,''), d.wordpress_api_url) AS site_url, d.wordpress_api_url AS original_api_url
            FROM $dev_table d
            LEFT JOIN $prov_table p ON d.unit_id = p.unit_id AND d.machine_id = p.machine_id
            ORDER BY d.unit_id ASC";
    return $wpdb->get_results($sql, ARRAY_A);
}

// Provisioning page UI
function tmon_admin_provisioning_page() {
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    global $wpdb;

    // Show queue diagnostics at top of the page to help debugging
    $queue = get_option('tmon_admin_pending_provision', []);
    $queue_count = (is_array($queue)) ? count($queue) : 0;
    $last_ts = '';
    if ($queue_count) {
        // try to find most-recent requested_at across queued entries
        $most_recent = 0;
        foreach ($queue as $key => $payload) {
            $t = strtotime($payload['requested_at'] ?? '1970-01-01 00:00:00');
            if ($t && $t > $most_recent) $most_recent = $t;
        }
        if ($most_recent) $last_ts = date('Y-m-d H:i:s', $most_recent);
    }

    // Small admin notice area with queued count and latest queue timestamp
    echo '<div class="notice notice-info inline" style="margin-bottom:10px;">';
    echo '<p><strong>Provisioning queue:</strong> ' . intval($queue_count) . ' pending payload' . ($queue_count !== 1 ? 's' : '') . '.';
    if ($last_ts) echo ' (<em>last queued at ' . esc_html($last_ts) . '</em>)';
    echo '</p>';
    echo '<p class="description">Provisioning "Save & Provision" enqueues payloads for devices; use the Provisioning Activity page to review or re-enqueue / delete.</p>';
    echo '</div>';

    // Remove purge forms from this page (moved to Settings). Provide a hint.
    echo '<p class="description"><em>Data maintenance (purge & other destructive ops) moved to <a href="'.esc_url(admin_url('admin.php?page=tmon-admin-settings')).'">Settings</a> to avoid accidental data loss.</em></p>';

    $prov_table = $wpdb->prefix . 'tmon_provisioned_devices'; // PATCH: ensure $prov_table is available to all branches below
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

    // --- LIST DEVICES TABLE ---
    $all_devices = tmon_admin_get_all_devices();
    $has_devices = !empty($all_devices);
    $table_id = 'tmon-provisioning-devices';
    echo '<div class="wrap"><h1>Device Provisioning</h1>';

    // Table: device list
    echo '<table class="wp-list-table widefat striped" id="'.esc_attr($table_id).'">';
    echo '<thead><tr>';
    echo '<th>ID</th><th>Unit ID</th><th>Machine ID</th><th>Name</th><th>Plan</th><th>Status</th><th>Site</th><th>Staged</th><th>Can Bill</th><th>Created</th><th>Updated</th>';
    echo '</tr></thead><tbody>';
    if ($has_devices) {
        foreach ($all_devices as $r) {
            $name = !empty($r['unit_name_dev']) ? $r['unit_name_dev'] : (!empty($r['unit_name']) ? $r['unit_name'] : '');
            $canBill = isset($r['canBill']) ? (intval($r['canBill']) ? 'Yes' : 'No') : 'No';
            $staged = !empty($r['settings_staged']) ? 'Yes' : 'No';
            echo '<tr>';
            echo '<td>'.intval($r['id']).'</td>';
            echo '<td>'.esc_html($r['unit_id']).'</td>';
            echo '<td>'.esc_html($r['machine_id']).'</td>';
            echo '<td>'.esc_html($name).'</td>';
            echo '<td>'.esc_html($r['plan']).'</td>';
            echo '<td>'.esc_html($r['status']).'</td>';
            echo '<td>'.esc_html(isset($r['site_url']) ? $r['site_url'] : '').'</td>';
            echo '<td>'.esc_html($staged).'</td>';
            echo '<td>'.esc_html($canBill).'</td>';
            echo '<td>'.esc_html($r['created_at']).'</td>';
            echo '<td>'.esc_html($r['updated_at']).'</td>';
            echo '</tr>';
        }
    } else {
        echo '<tr><td colspan="11"><em>No devices found. Use "Save & Provision" to add new devices.</em></td></tr>';
    }
    echo '</tbody></table>';

    // --- SAVE & PROVISION FORM ---
    // Show form to add new or update existing device provisioning
    $form_action = admin_url('admin-post.php');
    $nonce = wp_create_nonce('tmon_admin_provision_device');
    echo '<h2>'.($has_devices ? 'Update' : 'Add').' Device Provisioning</h2>';
    echo '<form method="post" action="'.esc_url($form_action).'">';
    echo '<input type="hidden" name="action" value="tmon_admin_provision_device">';
    echo '<input type="hidden" name="_wpnonce" value="'.esc_attr($nonce).'">';
    // Device ID (hidden for existing devices)
    echo '<input type="hidden" name="id" value="'.esc_attr($has_devices ? $all_devices[0]['id'] : '').'">';
    // Unit ID
    echo '<table class="form-table"><tr>';
    echo '<th scope="row"><label for="unit_id">Unit ID</label></th>';
    echo '<td><input name="unit_id" type="text" id="unit_id" value="'.esc_attr($has_devices ? $all_devices[0]['unit_id'] : '').'" class="regular-text" required>';
    echo '<p class="description">Unique identifier for the unit (e.g., serial number).</p>';
    echo '</td></tr>';
    // Machine ID
    echo '<tr>';
    echo '<th scope="row"><label for="machine_id">Machine ID</label></th>';
    echo '<td><input name="machine_id" type="text" id="machine_id" value="'.esc_attr($has_devices ? $all_devices[0]['machine_id'] : '').'" class="regular-text" required>';
    echo '<p class="description">MAC address or unique machine identifier.</p>';
    echo '</td></tr>';
    // Device Name
    echo '<tr>';
    echo '<th scope="row"><label for="unit_name">Device Name</label></th>';
    echo '<td><input name="unit_name" type="text" id="unit_name" value="'.esc_attr($has_devices ? $all_devices[0]['unit_name'] : '').'" class="regular-text">';
    echo '<p class="description">Friendly name for the device (optional).</p>';
    echo '</td></tr>';
    // Plan
    echo '<tr>';
    echo '<th scope="row"><label for="plan">Plan</label></th>';
    echo '<td><input name="plan" type="text" id="plan" value="'.esc_attr($has_devices ? $all_devices[0]['plan'] : '').'" class="regular-text">';
    echo '<p class="description">Provisioning plan (e.g., standard, premium).</p>';
    echo '</td></tr>';
    // Role
    echo '<tr>';
    echo '<th scope="row"><label for="role">Role</label></th>';
    echo '<td><input name="role" type="text" id="role" value="'.esc_attr($has_devices ? $all_devices[0]['role'] : '').'" class="regular-text">';
    echo '<p class="description">Device role (e.g., base, extender).</p>';
    echo '</td></tr>';
    // Site URL
    echo '<tr>';
    echo '<th scope="row"><label for="site_url">Site URL</label></th>';
    echo '<td><input name="site_url" type="url" id="site_url" value="'.esc_url($has_devices ? $all_devices[0]['site_url'] : '').'" class="regular-text">';
    echo '<p class="description">URL of the site to provision (fallback to WordPress API URL if empty).</p>';
    echo '</td></tr>';
    // Settings Staged
    echo '<tr>';
    echo '<th scope="row"><label for="settings_staged">Settings Staged</label></th>';
    echo '<td>';
    echo '<input name="settings_staged" type="checkbox" id="settings_staged" value="1" '.checked($has_devices && $all_devices[0]['settings_staged'], 1, false).'> ';
    echo '<label for="settings_staged">Check to stage settings for provisioning.</label>';
    echo '</td></tr>';
    echo '</table>';

    // Submit button
    echo '<p class="submit">';
    echo '<input type="submit" name="save_provision" id="save_provision" class="button button-primary" value="'.esc_attr($has_devices ? 'Update & Provision' : 'Save & Provision').'">';
    echo '</p>';

    echo '</form>';

    // --- PROVISIONING HISTORY LINK ---
    // Link to the provisioning history page
    echo '<h2>Provisioning History</h2>';
    echo '<p><a href="'.esc_url(admin_url('admin.php?page=tmon-admin-provisioning-history')).'" class="button">View Provisioning History</a></p>';

    echo '</div>';

    // --- DATA TABLES SCRIPT ---
    // Enqueue DataTables script for device list table
    add_action('admin_footer', function() use ($table_id) {
        ?>
        <script>
        jQuery(document).ready(function($) {
            $('#<?php echo esc_js($table_id); ?>').DataTable({
                "order": [[ 0, "desc" ]], // Order by ID descending
                "columnDefs": [
                    { "visible": false, "targets": [0] } // Hide ID column
                ]
            });
        });
        </script>
        <?php
    });
}

// Record firmware fetch transients when AJAX handler succeeds
add_action('wp_ajax_tmon_admin_fetch_github_manifest', function(){
	if (!current_user_can('manage_options')) wp_send_json_error(['message'=>'Forbidden'], 403);
	// ...existing fetch logic...
	// Assume $version and $manifest populated on success
	// ...existing code...
	if (!empty($version) && !empty($manifest)) {
		set_transient('tmon_admin_firmware_version', $version, 12 * HOUR_IN_SECONDS);
		set_transient('tmon_admin_firmware_version_ts', current_time('mysql'), 12 * HOUR_IN_SECONDS);
		wp_send_json_success(['version'=>$version,'manifest'=>$manifest]);
	}
	wp_send_json_error(['message'=>'Failed to fetch firmware metadata'], 400);
});

// Inline notice renderer for Save & Provision results; call this in your page renderer.
if (!function_exists('tmon_admin_render_provision_notice')) {
	function tmon_admin_render_provision_notice() {
		if (!current_user_can('manage_options')) return;
		$state = isset($_GET['provision']) ? sanitize_text_field($_GET['provision']) : '';
		if ($state === 'queued') {
			echo '<div class="notice notice-success"><p>Provisioning queued and saved.</p></div>';
		} elseif ($state === 'failed') {
			echo '<div class="notice notice-error"><p>Provisioning save failed.</p></div>';
		}
	}
}

// Legacy provisioning form renderer (restores previous structure but uses current Save & Provision logic)
if (!function_exists('tmon_admin_render_legacy_provision_form')) {
	function tmon_admin_render_legacy_provision_form($device = array()) {
		if (!current_user_can('manage_options')) wp_die('Forbidden');
		$defaults = array(
			'unit_id'    => '',
			'unit_name'  => '',
			'machine_id' => '',
			'site_url'   => '',
			'role'       => 'base',
			'company_id' => '',
			'plan'       => 'standard',
			'status'     => 'pending',
			'notes'      => '',
			'checkin_time' => '',
			'firmware'   => '',
		);
		$d = wp_parse_args($device, $defaults);
		echo '<div class="wrap">';
		echo '<h1>Device Provisioning</h1>';
		tmon_admin_render_provision_notice();
		echo '<div class="tmon-card tmon-provision-compact">';
		echo '<form id="tmon-provision-form" method="post" action="' . esc_url(admin_url('admin-post.php')) . '">';
		wp_nonce_field('tmon_admin_provision_device');
		echo '<input type="hidden" name="action" value="tmon_admin_provision_device">';

		echo '<table class="form-table"><tbody>';

		echo '<tr><th scope="row"><label for="unit_id">Unit ID</label></th><td><input name="unit_id" id="unit_id" class="regular-text" value="'.esc_attr($d['unit_id']).'" required></td></tr>';
		echo '<tr><th scope="row"><label for="unit_name">Unit Name</label></th><td><input name="unit_name" id="unit_name" class="regular-text" value="'.esc_attr($d['unit_name']).'"></td></tr>';
		echo '<tr><th scope="row"><label for="machine_id">Machine ID</label></th><td><input name="machine_id" id="machine_id" class="regular-text" value="'.esc_attr($d['machine_id']).'" required></td></tr>';
		echo '<tr><th scope="row"><label for="site_url">Unit Connector Site URL</label></th><td><input name="site_url" id="site_url" class="regular-text" value="'.esc_attr($d['site_url']).'" required></td></tr>';

		echo '<tr><th scope="row"><label for="role">Role</label></th><td><select name="role" id="role">';
		$roles = array('base' => 'base', 'remote' => 'remote', 'gateway' => 'gateway');
		foreach ($roles as $val => $label) echo '<option value="'.esc_attr($val).'" '.selected($d['role'],$val,false).'>'.esc_html($label).'</option>';
		echo '</select></td></tr>';

		echo '<tr><th scope="row"><label for="company_id">Company ID</label></th><td><input name="company_id" id="company_id" type="number" class="small-text" value="'.esc_attr($d['company_id']).'"></td></tr>';

		echo '<tr><th scope="row"><label for="plan">Plan</label></th><td><select name="plan" id="plan">';
		$plans = array('standard'=>'standard','pro'=>'pro');
		foreach ($plans as $val => $label) echo '<option value="'.esc_attr($val).'" '.selected($d['plan'],$val,false).'>'.esc_html($label).'</option>';
		echo '</select></td></tr>';

		echo '<tr><th scope="row"><label for="status">Status</label></th><td><select name="status" id="status">';
		$statuses = array('pending'=>'pending','active'=>'active','provisioned'=>'provisioned','registered'=>'registered');
		foreach ($statuses as $val => $label) echo '<option value="'.esc_attr($val).'" '.selected($d['status'],$val,false).'>'.esc_html($label).'</option>';
		echo '</select></td></tr>';

		echo '<tr><th scope="row"><label for="notes">Notes</label></th><td><textarea name="notes" id="notes" class="large-text">'.esc_textarea($d['notes']).'</textarea></td></tr>';

		echo '<tr><th scope="row"><label for="checkin_time">Check-in Time</label></th><td><input name="checkin_time" id="checkin_time" class="regular-text" value="'.esc_attr($d['checkin_time']).'" readonly></td></tr>';

		if (!empty($d['firmware'])) {
			echo '<tr><th scope="row"><label for="firmware">Firmware</label></th><td><input name="firmware" id="firmware" class="regular-text" value="'.esc_attr($d['firmware']).'"></td></tr>';
		}

		// Staged settings JSON (optional)
		echo '<tr><th scope="row"><label for="settings_staged">Staged Settings (JSON)</label></th><td><textarea name="settings_staged" id="settings_staged" class="large-text" rows="6"></textarea><p class="description">Optional JSON to stage to device via UC.</p></td></tr>';

		echo '</tbody></table>';

		echo '<p class="submit">';
		echo '<button type="submit" class="button button-primary">Save & Provision</button> ';
		echo '<a class="button" href="'.esc_url(add_query_arg(array('export'=>'provision-history'), admin_url('admin.php?page=tmon-admin-provisioning'))).'">Export History (CSV)</a>';
		echo '</p>';

		echo '</form></div></div>';
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
	// set_transient('tmon_admin_firmware_version_ts', current_time('mysql'), 12 * H
			$join_name = ($has_dev && in_array('unit_name', $dev_cols)) ? ", d.unit_name AS unit_name_dev" : "";
			$join_bill = ($has_dev && in_array('canBill', $dev_cols)) ? ", d.canBill AS canBill" : "";
			$sql = "SELECT p.id,p.unit_id,p.machine_id,p.plan,p.status,p.site_url,p.unit_name,p.settings_staged,p.created_at,p.updated_at{$join_name}{$join_bill}
			        FROM {$prov_table} p LEFT JOIN {$dev_table} d ON d.unit_id=p.unit_id AND d.machine_id=p.machine_id
			        ORDER BY p.created_at DESC";
			$rows = $wpdb->get_results($sql, ARRAY_A);
		}

		echo '<div class="wrap"><h1>Provisioned Devices</h1>';
		if (!$rows) { echo '<p><em>No provisioned devices found.</em></p></div>'; return; }
		echo '<table class="wp-list-table widefat striped"><thead><tr>';
		echo '<th>ID</th><th>Unit ID</th><th>Machine ID</th><th>Name</th><th>Plan</th><th>Status</th><th>Site</th><th>Staged</th><th>Can Bill</th><th>Created</th><th>Updated</th>';
		echo '</tr></thead><tbody>';
		foreach ($rows as $r) {
			$name = !empty($r['unit_name_dev']) ? $r['unit_name_dev'] : (!empty($r['unit_name']) ? $r['unit_name'] : '');
			$canBill = isset($r['canBill']) ? (intval($r['canBill']) ? 'Yes' : 'No') : 'No';
			$staged = !empty($r['settings_staged']) ? 'Yes' : 'No';
			echo '<tr>';
			echo '<td>'.intval($r['id']).'</td>';
			echo '<td>'.esc_html($r['unit_id']).'</td>';
			echo '<td>'.esc_html($r['machine_id']).'</td>';
			echo '<td>'.esc_html($name).'</td>';
			echo '<td>'.esc_html($r['plan']).'</td>';
			echo '<td>'.esc_html($r['status']).'</td>';
			echo '<td>'.esc_html(isset($r['site_url']) ? $r['site_url'] : '').'</td>';
			echo '<td>'.esc_html($staged).'</td>';
			echo '<td>'.esc_html($canBill).'</td>';
			echo '<td>'.esc_html($r['created_at']).'</td>';
			echo '<td>'.esc_html($r['updated_at']).'</td>';
			echo '</tr>';
		}
		echo '</tbody></table></div>';
	}
}

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
