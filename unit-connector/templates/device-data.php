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
    <label for="tmon-unit-picker" class="screen-reader-text">Device</label>
    <select id="tmon-unit-picker" style="min-width:260px;">
        <?php foreach ($devices as $d): ?>
            <option value="<?php echo esc_attr($d['unit_id']); ?>" data-unit-name="<?php echo esc_attr($d['unit_name']); ?>"><?php echo esc_html($d['label']); ?></option>
        <?php endforeach; ?>
    </select>
    <input type="text" id="tmon-unit-name-edit" style="min-width:180px;" placeholder="Edit unit name">
    <button class="button" id="tmon-unit-name-save">Save Name</button>
    <span id="tmon-unit-name-status" style="margin-left:8px;"></span>

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
