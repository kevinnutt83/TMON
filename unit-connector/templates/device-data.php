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
            // Fire change to trigger guarded listeners (fetchSettings/loadUnit/etc.)
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
    	const unit = '<?php echo esc_js($unit); ?>';
    	const nonce = '<?php echo wp_create_nonce('tmon_uc_nonce'); ?>';

    	btn.addEventListener('click', function(e){
    		e.preventDefault();
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
    			status.textContent = 'Settings AJAX response: ' + (j && j.data ? JSON.stringify(j.data) : JSON.stringify(j));
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
    // --- Editable unit name logic ---
    var picker = document.getElementById('tmon-unit-picker');
    var nameEdit = document.getElementById('tmon-unit-name-edit');
    var nameSave = document.getElementById('tmon-unit-name-save');
    var nameStatus = document.getElementById('tmon-unit-name-status');
    function updateNameInput() {
        var opt = picker.options[picker.selectedIndex];
        nameEdit.value = opt ? (opt.getAttribute('data-unit-name') || '') : '';
        nameStatus.textContent = '';
    }
    picker.addEventListener('change', updateNameInput);
    updateNameInput();
    nameSave.addEventListener('click', function(){
        var unit = picker.value;
        var newName = nameEdit.value.trim();
        nameStatus.textContent = 'Saving...';
        fetch(ajaxurl + '?action=tmon_uc_update_unit_name', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: 'unit_id=' + encodeURIComponent(unit) + '&unit_name=' + encodeURIComponent(newName) + '&_wpnonce=<?php echo esc_js($nonce); ?>'
        }).then(r=>r.json()).then(function(res){
            if(res && res.success){
                nameStatus.textContent = 'Saved!';
                // Update dropdown label
                var opt = picker.options[picker.selectedIndex];
                if(opt) {
                    opt.setAttribute('data-unit-name', newName);
                    opt.textContent = newName ? (newName + ' (' + unit + ')') : unit;
                }
            } else {
                nameStatus.textContent = 'Error saving';
            }
        }).catch(function(){ nameStatus.textContent = 'Error'; });
    });

    // --- Settings panels logic ---
    var settingsApplied = document.getElementById('tmon-settings-applied');
    var settingsStaged = document.getElementById('tmon-settings-staged');
    var settingsEditor = document.getElementById('tmon-settings-editor');
    var settingsLoad = document.getElementById('tmon-settings-load');
    var settingsPush = document.getElementById('tmon-settings-push');
    var settingsStatus = document.getElementById('tmon-settings-status');
    var card = document.getElementById('tmon-settings-card');
    function fetchSettings(unit) {
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
    picker.addEventListener('change', function(){ fetchSettings(picker.value); });
    settingsLoad.addEventListener('click', function(){ fetchSettings(picker.value); });
    // Initial load
    fetchSettings(picker.value);

    settingsPush.addEventListener('click', function(){
        var unit = picker.value;
        var json;
        try { json = JSON.parse(settingsEditor.value); }
        catch(e){ settingsStatus.textContent = 'Invalid JSON'; return; }
        settingsStatus.textContent = 'Staging...';
        fetch(ajaxurl + '?action=tmon_uc_stage_settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: 'unit_id=' + encodeURIComponent(unit) + '&settings=' + encodeURIComponent(JSON.stringify(json)) + '&_wpnonce=<?php echo esc_js($nonce); ?>'
        }).then(r=>r.json()).then(function(res){
            if(res && res.success){
                settingsStatus.textContent = 'Staged!';
                fetchSettings(unit);
            } else {
                settingsStatus.textContent = 'Error staging';
            }
        }).catch(function(){ settingsStatus.textContent = 'Error'; });
    });
})();
</script>

<!-- Ensure a stable global picker reference early so other inline scripts won't throw -->
<script>
(function(){
	// If a page-level picker exists in DOM, expose it as window.picker immediately.
	try { if (!window.picker) window.picker = document.getElementById('tmon-unit-picker') || null; } catch(e) {}
})();
</script>

<script>
(function(){
	// Make the primary top picker drive the device settings panel (guarded).
	// Use a local lookup so this block doesn't depend on a bare `picker` variable being defined elsewhere.
	var pickerEl = (typeof picker !== 'undefined' && picker) ? picker : (document.getElementById ? document.getElementById('tmon-unit-picker') : null);

	if (pickerEl) {
		// when user changes the global picker, keep UI in sync and refresh data
		pickerEl.addEventListener('change', function(){
			try {
				var v = pickerEl.value;
				var uidInput = document.getElementById('tmon_unit_id');
				if (uidInput) uidInput.value = v;
				if (typeof fetchSettings === 'function') fetchSettings(v);
				if (typeof loadUnit === 'function') loadUnit(v);
			} catch (e) { console.warn('tmon: picker change handler error', e); }
		});

		// run updates on initial page load (single-source update)
		(function(){
			try {
				var initial = pickerEl.value || (pickerEl.options && pickerEl.options.length ? pickerEl.options[0].value : '');
				if (initial) {
					if (typeof fetchSettings === 'function') fetchSettings(initial);
				 if (typeof loadUnit === 'function') loadUnit(initial);
				}
			} catch (e) { console.warn('tmon: initial picker load error', e); }
		})();
	} else {
		// No global picker present: disable settings controls to avoid confusion
		var statusEl = document.getElementById('tmon_ds_status');
		if (statusEl) statusEl.textContent = 'Page-level Unit selector (id="tmon-unit-picker") not found; add it to use this panel.';
		var btns = document.querySelectorAll('#tmon_ds_load, #tmon_ds_save');
		Array.prototype.forEach.call(btns, function(b){ if (b) b.disabled = true; });
	}
})();
</script>
