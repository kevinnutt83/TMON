<?php
// AJAX handlers for Device Data admin page
add_action('wp_ajax_tmon_uc_device_bundle', function(){
    if (!current_user_can('manage_options')) {
        wp_send_json_error(['message' => 'forbidden'], 403);
    }
    check_ajax_referer('tmon_uc_device_data', 'nonce');
    $unit_id = isset($_POST['unit_id']) ? sanitize_text_field(wp_unslash($_POST['unit_id'])) : '';
    if (!$unit_id) {
        wp_send_json_error(['message' => 'unit_id required'], 400);
    }
    global $wpdb;
    $device = $wpdb->get_row($wpdb->prepare("SELECT unit_id, machine_id, unit_name, settings, last_seen FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $unit_id), ARRAY_A);
    $settings = [];
    if ($device && !empty($device['settings'])) {
        $tmp = json_decode($device['settings'], true);
        if (is_array($tmp)) { $settings = $tmp; }
    }
    $machine_id = $device['machine_id'] ?? '';
    uc_devices_ensure_table();
    $uc_table = $wpdb->prefix . 'tmon_uc_devices';
    $staged_row = $wpdb->get_row($wpdb->prepare("SELECT staged_settings, staged_at, machine_id FROM {$uc_table} WHERE unit_id=%s OR machine_id=%s LIMIT 1", $unit_id, $machine_id), ARRAY_A);
    $staged = [];
    if ($staged_row && !empty($staged_row['staged_settings'])) {
        $tmp = json_decode($staged_row['staged_settings'], true);
        if (is_array($tmp)) { $staged = $tmp; }
    }
    if (!$machine_id && $staged_row && !empty($staged_row['machine_id'])) {
        $machine_id = $staged_row['machine_id'];
    }
    $latest = $wpdb->get_row($wpdb->prepare("SELECT created_at FROM {$wpdb->prefix}tmon_field_data WHERE unit_id=%s ORDER BY created_at DESC LIMIT 1", $unit_id), ARRAY_A);
    wp_send_json_success([
        'unit_id' => $unit_id,
        'machine_id' => $machine_id,
        'settings' => $settings,
        'staged' => $staged,
        'staged_at' => tmon_uc_format_mysql_datetime($staged_row['staged_at'] ?? ''),
        'last_seen' => tmon_uc_format_mysql_datetime($device['last_seen'] ?? ($latest['created_at'] ?? '')),
    ]);
});

add_action('wp_ajax_tmon_uc_stage_settings', function(){
    if (!current_user_can('manage_options')) {
        wp_send_json_error(['message' => 'forbidden'], 403);
    }
    check_ajax_referer('tmon_uc_device_data', 'nonce');
    $unit_id = isset($_POST['unit_id']) ? sanitize_text_field(wp_unslash($_POST['unit_id'])) : '';
    $settings_json = isset($_POST['settings_json']) ? wp_unslash($_POST['settings_json']) : '';
    if (!$unit_id) {
        wp_send_json_error(['message' => 'unit_id required'], 400);
    }
    $decoded = null;
    if ($settings_json !== '') {
        $decoded = json_decode($settings_json, true);
        if ($decoded === null && json_last_error() !== JSON_ERROR_NONE) {
            wp_send_json_error(['message' => 'Invalid JSON payload'], 400);
        }
    }
    $settings_json = $decoded !== null ? wp_json_encode($decoded) : '{}';

    global $wpdb;
    $device = $wpdb->get_row($wpdb->prepare("SELECT machine_id FROM {$wpdb->prefix}tmon_devices WHERE unit_id=%s", $unit_id), ARRAY_A);
    $machine_id = $device['machine_id'] ?? '';
    uc_devices_ensure_table();
    $uc_table = $wpdb->prefix . 'tmon_uc_devices';
    if (!$machine_id) {
        $alt = $wpdb->get_row($wpdb->prepare("SELECT machine_id FROM {$uc_table} WHERE unit_id=%s", $unit_id), ARRAY_A);
        if ($alt && !empty($alt['machine_id'])) { $machine_id = $alt['machine_id']; }
    }
    // Persist staged settings locally
    $now_utc = current_time('mysql', true);
    $wpdb->query($wpdb->prepare(
        "INSERT INTO {$uc_table} (unit_id, machine_id, staged_settings, staged_at, assigned, updated_at)
         VALUES (%s, %s, %s, %s, 1, %s)
         ON DUPLICATE KEY UPDATE staged_settings=VALUES(staged_settings), staged_at=VALUES(staged_at), machine_id=IF(VALUES(machine_id)!='', VALUES(machine_id), machine_id), updated_at=VALUES(updated_at)",
        $unit_id, $machine_id, $settings_json, $now_utc, $now_utc
    ));

    // Also write per-device staged settings file for local inspection or base use
    try {
        $settings_array = $decoded !== null ? $decoded : [];
        if (!empty($unit_id) && is_array($settings_array)) {
            $logs_dir = trailingslashit(WP_CONTENT_DIR) . 'tmon-field-logs';
            if (! file_exists($logs_dir)) wp_mkdir_p($logs_dir);
            $file = $logs_dir . '/device_settings-' . sanitize_file_name($unit_id) . '.json';
            file_put_contents($file, wp_json_encode($settings_array));
        }
    } catch (Exception $e) {
        // best-effort; continue
    }

    // Push to Admin hub if credentials exist
    $push_result = uc_push_staged_settings($unit_id, $machine_id, $settings_json);
    if (is_wp_error($push_result)) {
        wp_send_json_error(['message' => $push_result->get_error_message()]);
    }
    wp_send_json_success(['message' => 'Staged and pushed to Admin hub.']);
});

// Render callback for the Device Data admin page (no output at include time)
if (! function_exists('tmon_uc_device_data_page')) {
	function tmon_uc_device_data_page() {
		if (! current_user_can( 'manage_options' ) ) {
			wp_die( 'Forbidden' );
		}

		// Compute nonces/rest root here (only when rendering the page)
		$nonce = '';
		$adminNonce = '';
		$restRoot = '';
		$wpRestNonce = '';
		if ( function_exists( 'wp_create_nonce' ) ) {
			$nonce = wp_create_nonce( 'tmon_uc_nonce' );
			$adminNonce = wp_create_nonce( 'tmon_uc_nonce' );
			$wpRestNonce = wp_create_nonce( 'wp_rest' );
		}
		if ( function_exists( 'get_site_url' ) ) {
			$restRoot = esc_js( get_site_url( null, '/wp-json/' ) );
		}

		// Query units (defensive)
		global $wpdb;
		$units = array();
		try {
			$units = $wpdb->get_results( "SELECT unit_id, unit_name FROM {$wpdb->prefix}tmon_devices ORDER BY unit_name ASC, unit_id ASC", ARRAY_A );
		} catch ( Exception $e ) {
			$units = array();
		}

		// Begin output (only here)
		?>
		<div class="wrap">
			<h1><?php esc_html_e('Device Data & Settings', 'tmon'); ?></h1>

			<label for="tmon-unit-picker">Device</label>
			<select id="tmon-unit-picker" class="tmon-unit-picker" style="margin-bottom:8px;">
				<option value=""><?php esc_html_e('-- choose unit --', 'tmon'); ?></option>
				<?php foreach ( $units as $u ) :
					$uid = esc_attr( $u['unit_id'] );
					$label = $u['unit_name'] ? esc_html( $u['unit_name'] . ' (' . $u['unit_id'] . ')' ) : esc_html( $u['unit_id'] );
				?>
					<option value="<?php echo $uid; ?>" data-unit-name="<?php echo esc_attr($u['unit_name']); ?>"><?php echo $label; ?></option>
				<?php endforeach; ?>
			</select>

			<!-- Dynamic staged-settings editor -->
			<div class="card" id="tmon-settings-card" data-nonce="<?php echo esc_attr($nonce); ?>" style="margin-top:16px;padding:12px;">
				<h2><?php esc_html_e('Settings', 'tmon'); ?></h2>
				<p class="description"><?php esc_html_e('Use the dynamic editor below to stage one or more settings for the selected device. Click + to add entries. Click the X on an entry to remove it. When ready, click "Stage & Push".', 'tmon'); ?></p>
				<p><strong><?php esc_html_e('Machine ID:', 'tmon'); ?></strong> <span id="tmon-device-machine"></span> &nbsp; <strong><?php esc_html_e('Last Seen:', 'tmon'); ?></strong> <span id="tmon-device-updated"></span></p>

				<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;">
					<button id="tmon-add-setting" class="button">+ Add Setting</button>
					<button id="tmon-settings-push" class="button button-primary"><?php esc_html_e('Stage &amp; Push', 'tmon'); ?></button>
					<button id="tmon-settings-load" class="button"><?php esc_html_e('Reload current', 'tmon'); ?></button>
					<span id="tmon-settings-status" style="margin-left:12px;"></span>
				</div>

				<div id="tmon-dynamic-settings-list" style="display:flex;flex-direction:column;gap:10px;"></div>

				<h3 style="margin-top:16px;"><?php esc_html_e('Raw JSON (fallback)', 'tmon'); ?></h3>
				<textarea id="tmon-settings-editor" rows="8" style="width:100%;font-family:monospace;"></textarea>
			</div>

			<!-- Status panes (staged/applied) -->
			<h2 style="margin-top:18px;"><?php esc_html_e('Staged / Applied (Debug)', 'tmon'); ?></h2>
			<div style="display:flex;gap:12px;">
				<div style="flex:1"><h3><?php esc_html_e('Applied', 'tmon'); ?></h3><pre id="tmon-settings-applied" style="background:#fff;padding:8px;border:1px solid #ddd;height:180px;overflow:auto;">{}</pre></div>
				<div style="flex:1"><h3><?php esc_html_e('Staged', 'tmon'); ?></h3><pre id="tmon-settings-staged" style="background:#fff;padding:8px;border:1px solid #ddd;height:180px;overflow:auto;">{}</pre></div>
			</div>
		</div>

		<script>
		(function(){
			const ajaxUrl = '<?php echo admin_url('admin-ajax.php'); ?>';
			const restRoot = '<?php echo $restRoot; ?>';
			const wpNonce = '<?php echo esc_js($wpRestNonce); ?>';
			const adminNonce = '<?php echo esc_js($adminNonce); ?>';

			// Fetch applied/staged helper (existing behavior)
			function fetchSettings(unit){
				const settingsApplied = document.getElementById('tmon-settings-applied');
				const settingsStaged = document.getElementById('tmon-settings-staged');
				settingsApplied.textContent = 'Loading...';
				settingsStaged.textContent = 'Loading...';
				fetch(ajaxUrl + '?action=tmon_uc_get_settings&unit_id=' + encodeURIComponent(unit))
				.then(r=>r.json()).then(function(res){
					if(res && res.success){
						settingsApplied.textContent = JSON.stringify(res.applied, null, 2);
						settingsStaged.textContent = JSON.stringify(res.staged, null, 2);
						// Populate raw editor with applied snapshot as starting point
						document.getElementById('tmon-settings-editor').value = JSON.stringify(res.applied || {}, null, 2);
					} else {
						settingsApplied.textContent = 'Error loading';
						settingsStaged.textContent = 'Error loading';
					}
				}).catch(function(){ settingsApplied.textContent = 'Error loading'; settingsStaged.textContent = 'Error loading'; });
			}

			// Dynamic editor behavior
			let SCHEMA = null; // populated via AJAX
			const listEl = document.getElementById('tmon-dynamic-settings-list');
			const addBtn = document.getElementById('tmon-add-setting');
			const pushBtn = document.getElementById('tmon-settings-push');

			// Add a single setting entry
			function addEntry(key, val){
				const entry = document.createElement('div');
				entry.className = 'tmon-setting-entry';
				entry.style = 'border:1px solid #ddd;padding:8px;position:relative;background:#fff;';
				entry.innerHTML = `
					<button class="tmon-remove-entry" title="Remove" style="position:absolute;right:6px;top:6px;">✕</button>
					<label style="display:block;margin-bottom:6px;">Setting
						<select class="tmon-setting-key" style="width:100%;margin-top:4px;"></select>
					</label>
					<label style="display:block;margin-top:8px;">Value
						<span class="tmon-value-container" style="display:block;margin-top:4px;"></span>
					</label>
				`;
				// populate keys
				const sel = entry.querySelector('.tmon-setting-key');
				Object.keys(SCHEMA || {}).forEach(function(k){
					const opt = document.createElement('option');
					opt.value = k;
					opt.textContent = k + (SCHEMA[k].label ? ' — ' + SCHEMA[k].label : '');
					sel.appendChild(opt);
				});
				// set selected if provided
				if (key) sel.value = key;
				// remove handler
				entry.querySelector('.tmon-remove-entry').addEventListener('click', function(){ entry.remove(); });
				// when key changes, render appropriate input type and set default applied value if known
				sel.addEventListener('change', function(){
					renderValueControl(entry, sel.value, null);
				});
				// initial render
				renderValueControl(entry, sel.value, val);
				listEl.appendChild(entry);
				return entry;
			}

			function renderValueControl(entry, key, value){
				const container = entry.querySelector('.tmon-value-container');
				container.innerHTML = '';
				const meta = (SCHEMA && SCHEMA[key]) ? SCHEMA[key] : {type:'string'};
				const t = (meta.type || 'string');
				// create appropriate control
				if (t === 'bool' || t === 'boolean') {
					const cb = document.createElement('input'); cb.type = 'checkbox'; cb.className='tmon-value-input';
					if (value !== null && value !== undefined) cb.checked = !!value;
					container.appendChild(cb);
				} else if (t === 'number' || t === 'integer' || t === 'float') {
					const num = document.createElement('input'); num.type='number'; num.className='tmon-value-input';
					if (value !== null && value !== undefined) num.value = value;
					container.appendChild(num);
				} else {
					const txt = document.createElement('input'); txt.type='text'; txt.className='tmon-value-input';
					if (value !== null && value !== undefined) txt.value = value;
					container.appendChild(txt);
				}
				// show a small help/description if provided
				if (meta && meta.desc) {
					const d = document.createElement('div'); d.style='font-size:12px;color:#666;margin-top:6px;'; d.textContent = meta.desc;
					container.appendChild(d);
				}
			}

			// Load schema from server
			function loadSchema(cb){
				fetch(ajaxUrl + '?action=tmon_uc_get_settings_schema&nonce=' + encodeURIComponent(adminNonce) , { credentials:'same-origin' })
				.then(r=>r.json()).then(function(j){
					if (j && j.success) {
						SCHEMA = j.data || {};
					} else {
						SCHEMA = {};
					}
					if (typeof cb === 'function') cb();
				}).catch(function(){ SCHEMA = {}; if (typeof cb === 'function') cb(); });
			}

			// Preload current applied values to set as defaults when keys selected
			function getAppliedValues(){
				try {
					const el = document.getElementById('tmon-settings-applied');
					if (!el || !el.textContent) return {};
					return JSON.parse(el.textContent || '{}');
				} catch (e){ return {}; }
			}

			addBtn.addEventListener('click', function(e){
				e.preventDefault();
				const applied = getAppliedValues();
				loadSchema(function(){
					const firstKey = Object.keys(SCHEMA || {})[0] || '';
					const initialVal = applied[firstKey] !== undefined ? applied[firstKey] : '';
					const ent = addEntry(firstKey, initialVal);
					// when key selected, try to populate default from applied values
					ent.querySelector('.tmon-setting-key').addEventListener('change', function(){
						const k = this.value;
						const appliedNow = getAppliedValues();
						const v = (typeof appliedNow[k] !== 'undefined') ? appliedNow[k] : '';
						renderValueControl(ent, k, v);
					});
				});
			});

			// handle staging/push
			pushBtn.addEventListener('click', function(e){
				e.preventDefault();
				const unit = document.getElementById('tmon-unit-picker').value;
				if (!unit) { document.getElementById('tmon-settings-status').textContent = 'Select a unit first'; return; }
				// collect entries
				const entries = document.querySelectorAll('.tmon-setting-entry');
				const settings = {};
				entries.forEach(function(ent){
					const key = ent.querySelector('.tmon-setting-key').value;
					const input = ent.querySelector('.tmon-value-input');
					if (!key || !input) return;
					if (input.type === 'checkbox') settings[key] = !!input.checked;
					else if (input.type === 'number') settings[key] = input.value !== '' ? Number(input.value) : '';
					else settings[key] = input.value;
				});
				// if no dynamic entries, try raw JSON textarea fallback
				if (Object.keys(settings).length === 0) {
					try {
						const raw = document.getElementById('tmon-settings-editor').value || '{}';
						const parsed = JSON.parse(raw);
						if (typeof parsed === 'object') {
							Object.assign(settings, parsed);
						}
					} catch (e) {
						document.getElementById('tmon-settings-status').textContent = 'Invalid JSON in editor';
						return;
					}
				}
				document.getElementById('tmon-settings-status').textContent = 'Staging...';
				// Use REST endpoint (requires X-WP-Nonce) — restRoot is safe string
				fetch((restRoot || '') + 'tmon/v1/admin/device/settings-staged', {
					method: 'POST',
					headers: {'Content-Type':'application/json', 'X-WP-Nonce': wpNonce},
					body: JSON.stringify({ unit_id: unit, settings: settings })
				}).then(r=>r.json()).then(function(j){
					if (j && j.ok) {
						document.getElementById('tmon-settings-status').textContent = 'Staged and pushed to Admin';
						// Refresh staged/applied displays
						fetchSettings(unit);
					} else {
						document.getElementById('tmon-settings-status').textContent = 'Stage failed';
					}
				}).catch(function(e){
					document.getElementById('tmon-settings-status').textContent = 'Stage request failed';
				});
			});

			// "Reload current" button: simple refresh
			document.getElementById('tmon-settings-load').addEventListener('click', function(e){
				const unit = document.getElementById('tmon-unit-picker').value;
				if (!unit) return;
				fetchSettings(unit);
			});

			// When unit changes, refresh displays and clear dynamic list
			document.getElementById('tmon-unit-picker').addEventListener('change', function(){
				const unit = this.value;
				if (unit) fetchSettings(unit);
				listEl.innerHTML = '';
				// preload schema for quicker entry creation
				loadSchema();
			});

			// Initial schema prefetch in background
			loadSchema();
		})();
		</script>
		<?php
	}
}

// Register submenu page in admin (only when in admin context)
if ( is_admin() && ! has_action( 'admin_menu', 'tmon_uc_register_device_data_menu' ) ) {
	add_action('admin_menu', 'tmon_uc_register_device_data_menu');
	function tmon_uc_register_device_data_menu() {
		add_submenu_page(
			'tmon-uc',                          // parent slug (assumed)
			__('Device Data', 'tmon'),         // page title
			__('Device Data', 'tmon'),         // menu title
			'manage_options',                  // capability
			'tmon-uc-device-data',             // menu slug
			'tmon_uc_device_data_page'         // callback
		);
	}
}
