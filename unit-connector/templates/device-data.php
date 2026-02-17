<?php
if (!current_user_can('manage_options')) { wp_die('Insufficient permissions'); }
$devices = [];
global $wpdb;
$rows = $wpdb->get_results("SELECT unit_id, unit_name FROM {$wpdb->prefix}tmon_devices ORDER BY unit_name ASC, unit_id ASC", ARRAY_A);
if ($rows) {
    foreach ($rows as $row) {
        $label = $row['unit_name'] ? ($row['unit_name'] . ' (' . $row['unit_id'] . ')') : $row['unit_id'];
        $devices[] = ['unit_id' => $row['unit_id'], 'label' => $label, 'unit_name' => $row['unit_name']];
    }
}
if (empty($devices)) {
    echo '<div class="wrap"><h1>Device Data</h1><p><em>No devices found. Refresh from Admin hub first.</em></p></div>';
    return;
}
$nonce = wp_create_nonce('tmon_uc_device_data');
?>
<div class="wrap tmon-device-data">
    <h1>Device Data &amp; Settings</h1>
    <p>Select a device to view history, latest data, and stage settings back to Admin.</p>

    <!-- Replace local 'tmon_ds_unit' select (removed) with a single page-level picker
         that is the single source-of-truth for the device-data page. -->
    <?php
    global $wpdb;
    $units = $wpdb->get_results("SELECT unit_id, unit_name FROM {$wpdb->prefix}tmon_devices ORDER BY unit_name ASC, unit_id ASC", ARRAY_A);
    ?>
    <label for="tmon-unit-picker">Device</label>
    <select id="tmon-unit-picker" class="tmon-unit-picker" style="margin-bottom:8px;">
        <option value="">-- choose unit --</option>
        <?php foreach ($units as $u) : 
            $uid = esc_attr($u['unit_id']);
            $label = $u['unit_name'] ? esc_html($u['unit_name'] . ' (' . $u['unit_id'] . ')') : esc_html($u['unit_id']);
        ?>
            <option value="<?php echo $uid; ?>" data-unit-name="<?php echo esc_attr($u['unit_name']); ?>"><?php echo $label; ?></option>
        <?php endforeach; ?>
    </select>

    <script>
        // Ensure other inline scripts see the picker immediately and fire an initial load.
        (function(){
            var p = document.getElementById('tmon-unit-picker');
            if (!p) return;

            // Keep default selection only. Initial change dispatch is handled in the later settings script.
            if (!p.value && p.options && p.options.length) {
                for (var i = 0; i < p.options.length; i++) {
                    if (p.options[i].value) { p.value = p.options[i].value; break; }
                }
            }

            try { p.dispatchEvent(new Event('change')); } catch(e) { try { $(p).trigger('change'); } catch(_){} }
        })();
    </script>

    <div class="tmon-device-panels" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px;">
        <div class="card" style="padding:12px;">
            <?php echo do_shortcode('[tmon_device_history hours="24" refresh_s="60"]'); ?>
        </div>
        <div class="card" style="padding:12px;">
            <?php echo do_shortcode('[tmon_device_sdata refresh_s="45"]'); ?>
        </div>
    </div>

    <div class="card" id="tmon-settings-card" data-nonce="<?php echo esc_attr($nonce); ?>" style="margin-top:16px;padding:12px;">
        <h2>Settings</h2>
        <p class="description">Review applied vs staged settings, then stage updates to Admin for device pickup.</p>
        <p><strong>Machine ID:</strong> <span id="tmon-device-machine"></span> &nbsp; <strong>Last Seen:</strong> <span id="tmon-device-updated"></span></p>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div>
                <h3>Applied (device)</h3>
                <pre id="tmon-settings-applied" style="min-height:160px;background:#f6f7f7;padding:8px;overflow:auto;"></pre>
            </div>
            <div>
                <h3>Staged (UC/Admin)</h3>
                <pre id="tmon-settings-staged" style="min-height:160px;background:#f6f7f7;padding:8px;overflow:auto;"></pre>
            </div>
        </div>
        <h3>Stage new settings JSON</h3>
        <textarea id="tmon-settings-editor" rows="8" style="width:100%;font-family:monospace;"></textarea>
        <p class="description">Staging saves to the UC mirror and forwards to the Admin hub reprovision endpoint.</p>
        <p>
            <button class="button" id="tmon-settings-load">Reload current</button>
            <button class="button button-primary" id="tmon-settings-push">Stage &amp; Push</button>
            <span id="tmon-settings-status" class="tmon-status-info" style="margin-left:8px;"></span>
        </p>
    </div>

    <!-- Device Settings editor (shortcode) -->
    <h2>Device Settings (Stage for next check-in)</h2>
    <?php echo do_shortcode('[tmon_device_settings]'); ?>

    <?php
    // Unit Name quick-update (stage for next check-in)
    $unit = isset($_GET['unit_id']) ? sanitize_text_field($_GET['unit_id']) : (isset($_GET['unit']) ? sanitize_text_field($_GET['unit']) : '');
    $staged_map = get_option('tmon_uc_staged_settings', array());
    $staged_name = '';
    if ($unit && is_array($staged_map) && isset($staged_map[$unit]['settings']['UNIT_Name'])) {
    	$staged_name = $staged_map[$unit]['settings']['UNIT_Name'];
    } else {
    	// best-effort fallback: try provisioning index helper
    	if (function_exists('tmon_admin_get_device')) {
    		$dev = tmon_admin_get_device($unit);
    		if ($dev) $staged_name = $dev['unit_name'] ?? '';
    	}
    }
    ?>
    <div id="tmon-unit-name-update" style="margin-top:12px;">
    	<label for="tmon_unit_name_input"><strong>Unit Name</strong></label><br/>
    	<input id="tmon_unit_name_input" class="regular-text" value="<?php echo esc_attr($staged_name); ?>" />
    	<button id="tmon_update_unit_name_btn" class="button">Update name</button>
    	<span id="tmon_unit_name_status" style="margin-left:12px;"></span>
    </div>

    <script>
    (function(){
    	const btn = document.getElementById('tmon_update_unit_name_btn');
    	const input = document.getElementById('tmon_unit_name_input');
    	const status = document.getElementById('tmon_unit_name_status');
    	const picker = document.getElementById('tmon-unit-picker');
    	const nonce = '<?php echo wp_create_nonce('tmon_uc_nonce'); ?>';
    	if (!btn || !input || !status || !picker) return;

    	function syncFromPicker(){
    		var opt = picker.options && picker.selectedIndex >= 0 ? picker.options[picker.selectedIndex] : null;
    		input.value = opt ? (opt.getAttribute('data-unit-name') || '') : '';
    		status.textContent = '';
    	}
    	picker.addEventListener('change', syncFromPicker);
    	syncFromPicker();

    	btn.addEventListener('click', function(e){
    		e.preventDefault();
    		const unit = picker.value || '';
    		if (!unit) { alert('No unit selected'); return; }
    		const name = input.value || '';
    		status.textContent = 'Saving...';
    		const body = new URLSearchParams();
    		body.append('action','tmon_uc_update_unit_name');
    		body.append('unit_id', unit);
    		body.append('unit_name', name);
    		body.append('security', nonce);
    		fetch(ajaxurl, {
    			method: 'POST',
    			credentials: 'same-origin',
    			body: body
    		}).then(function(resp){
    			return resp.json().catch(function(){ return resp.text(); });
    		}).then(function(j){
    			if (j && j.success) {
    				status.textContent = 'Saved';
    				var opt = picker.options[picker.selectedIndex];
    				if (opt) {
    					opt.setAttribute('data-unit-name', name);
    					opt.textContent = name ? (name + ' (' + unit + ')') : unit;
    				}
    			} else {
    				status.textContent = 'Update failed';
    			}
    		}).catch(function(err){
    			status.textContent = 'Update failed';
    			console.error(err);
    		});
    	});
    })();
    </script>
</div>
<script>
(function(){
    var picker = document.getElementById('tmon-unit-picker');
    if (!picker) return;

    var settingsApplied = document.getElementById('tmon-settings-applied');
    var settingsStaged = document.getElementById('tmon-settings-staged');
    var settingsEditor = document.getElementById('tmon-settings-editor');
    var settingsLoad = document.getElementById('tmon-settings-load');
    var settingsPush = document.getElementById('tmon-settings-push');
    var settingsStatus = document.getElementById('tmon-settings-status');

    function fetchSettings(unit) {
        if (!unit) {
            if (settingsApplied) settingsApplied.textContent = 'Select a unit';
            if (settingsStaged) settingsStaged.textContent = 'Select a unit';
            if (settingsEditor) settingsEditor.value = '';
            if (settingsStatus) settingsStatus.textContent = '';
            return;
        }
        settingsApplied.textContent = 'Loading...';
        settingsStaged.textContent = 'Loading...';
        settingsEditor.value = '';
        settingsStatus.textContent = '';
        fetch(ajaxurl + '?action=tmon_uc_get_settings&unit_id=' + encodeURIComponent(unit))
        .then(r=>r.json()).then(function(res){
            console.log('Settings AJAX response:', res); // <-- Add this line for debugging
            if(res && res.success){
                settingsApplied.textContent = JSON.stringify(res.applied, null, 2);
                settingsStaged.textContent = JSON.stringify(res.staged, null, 2);
                settingsEditor.value = JSON.stringify(res.applied, null, 2);
            } else {
                settingsApplied.textContent = 'Error loading';
                settingsStaged.textContent = 'Error loading';
                settingsEditor.value = '';
            }
        }).catch(function(){
            settingsApplied.textContent = 'Error loading';
            settingsStaged.textContent = 'Error loading';
            settingsEditor.value = '';
        });
    }

    if (settingsLoad) settingsLoad.addEventListener('click', function(){ fetchSettings(picker.value); });
    picker.addEventListener('change', function(){ fetchSettings(picker.value); });

    // Initial picker default + initial load after listeners are attached
    if (!picker.value && picker.options && picker.options.length) {
        for (var i = 0; i < picker.options.length; i++) {
            if (picker.options[i].value) { picker.value = picker.options[i].value; break; }
        }
    }
    try { picker.dispatchEvent(new Event('change')); } catch(e) {}
})();
</script>
