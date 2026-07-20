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
$name_nonce = wp_create_nonce('tmon_uc_nonce');
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
    // Unit Name quick-update uses current picker value; no URL coupling.
    ?>
    <div id="tmon-unit-name-update" style="margin-top:12px;">
    	<label for="tmon_unit_name_input"><strong>Unit Name</strong></label><br/>
	<input id="tmon_unit_name_input" class="regular-text" value="" />
    	<button id="tmon_update_unit_name_btn" class="button">Update name</button>
    	<span id="tmon_unit_name_status" style="margin-left:12px;"></span>
    </div>
</div>
<script>
(function(){
    // --- Device Data page state and actions ---
    var picker = document.getElementById('tmon-unit-picker');
    if (!picker) return;

    var nameInput = document.getElementById('tmon_unit_name_input');
    var nameSave = document.getElementById('tmon_update_unit_name_btn');
    var nameStatus = document.getElementById('tmon_unit_name_status');

    var settingsApplied = document.getElementById('tmon-settings-applied');
    var settingsStaged = document.getElementById('tmon-settings-staged');
    var settingsEditor = document.getElementById('tmon-settings-editor');
    var settingsLoad = document.getElementById('tmon-settings-load');
    var settingsPush = document.getElementById('tmon-settings-push');
    var settingsStatus = document.getElementById('tmon-settings-status');

    var machineEl = document.getElementById('tmon-device-machine');
    var updatedEl = document.getElementById('tmon-device-updated');

    function updateNameInputFromPicker() {
        var opt = picker.options[picker.selectedIndex];
        if (nameInput) nameInput.value = opt ? (opt.getAttribute('data-unit-name') || '') : '';
        if (nameStatus) nameStatus.textContent = '';
    }

    function loadBundle(unit) {
        if (!unit) {
            if (machineEl) machineEl.textContent = '';
            if (updatedEl) updatedEl.textContent = '';
            return;
        }
        var body = new URLSearchParams();
        body.append('action', 'tmon_uc_device_bundle');
        body.append('unit_id', unit);
        body.append('nonce', '<?php echo esc_js($nonce); ?>');
        fetch(ajaxurl, {
            method: 'POST',
            credentials: 'same-origin',
            body: body
        }).then(function(r){ return r.json(); }).then(function(res){
            if (!(res && res.success && res.data)) return;
            if (machineEl) machineEl.textContent = res.data.machine_id || '';
            if (updatedEl) updatedEl.textContent = res.data.last_seen || '';
            if (nameInput && !nameInput.value) {
                var stagedName = (res.data.staged && res.data.staged.UNIT_Name) ? String(res.data.staged.UNIT_Name) : '';
                if (stagedName) nameInput.value = stagedName;
            }
        }).catch(function(){});
    }

    function fetchSettings(unit) {
        if (!unit) {
            settingsApplied.textContent = '{}';
            settingsStaged.textContent = '{}';
            settingsEditor.value = '';
            settingsStatus.textContent = '';
            return;
        }
        settingsApplied.textContent = 'Loading...';
        settingsStaged.textContent = 'Loading...';
        settingsEditor.value = '';
        settingsStatus.textContent = '';
        fetch(ajaxurl + '?action=tmon_uc_get_settings&unit_id=' + encodeURIComponent(unit))
        .then(r=>r.json()).then(function(res){
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
    function refreshUnit(unit) {
        updateNameInputFromPicker();
        fetchSettings(unit);
        loadBundle(unit);
    }

    picker.addEventListener('change', function(){ refreshUnit(picker.value); });
    settingsLoad.addEventListener('click', function(){ refreshUnit(picker.value); });

    if (nameSave) {
        nameSave.addEventListener('click', function(e){
            e.preventDefault();
            var unit = picker.value;
            var newName = (nameInput && nameInput.value) ? nameInput.value.trim() : '';
            if (!unit) { alert('Choose a unit first'); return; }
            nameStatus.textContent = 'Saving...';
            var body = new URLSearchParams();
            body.append('action','tmon_uc_update_unit_name');
            body.append('unit_id', unit);
            body.append('unit_name', newName);
            body.append('security', '<?php echo esc_js($name_nonce); ?>');
            fetch(ajaxurl, {
                method: 'POST',
                credentials: 'same-origin',
                body: body
            }).then(function(r){ return r.json(); }).then(function(res){
                if(res && res.success){
                    nameStatus.textContent = 'Saved';
                    var opt = picker.options[picker.selectedIndex];
                    if (opt) {
                        opt.setAttribute('data-unit-name', newName);
                        opt.textContent = newName ? (newName + ' (' + unit + ')') : unit;
                    }
                } else {
                    nameStatus.textContent = 'Error saving';
                }
            }).catch(function(){ nameStatus.textContent = 'Update failed'; });
        });
    }

    settingsPush.addEventListener('click', function(){
        var unit = picker.value;
        var json;
        try { json = JSON.parse(settingsEditor.value); }
        catch(e){ settingsStatus.textContent = 'Invalid JSON'; return; }
        settingsStatus.textContent = 'Staging...';
        var body = new URLSearchParams();
        body.append('action', 'tmon_uc_stage_settings');
        body.append('unit_id', unit);
        body.append('settings_json', JSON.stringify(json));
        body.append('nonce', '<?php echo esc_js($nonce); ?>');
        fetch(ajaxurl, {
            method: 'POST',
            credentials: 'same-origin',
            body: body
        }).then(r=>r.json()).then(function(res){
            if(res && res.success){
                settingsStatus.textContent = 'Staged!';
                refreshUnit(unit);
            } else {
                settingsStatus.textContent = (res && res.data && res.data.message) ? res.data.message : 'Error staging';
            }
        }).catch(function(){ settingsStatus.textContent = 'Error'; });
    });

    // Initial load
    refreshUnit(picker.value);
})();
</script>
