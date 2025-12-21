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

    <?php
    // Insert device settings form (admin-only). Minimal, self-contained markup + JS.

    if (!current_user_can('manage_options')) {
        echo '<p><em>Device settings available for administrators only.</em></p>';
        return;
    }

    $known = get_option('tmon_uc_known_units', []); // optional list of known unit_ids (may be empty)
    $nonce = wp_create_nonce('tmon_uc_stage_settings');
    ?>
    <div id="tmon-device-settings" class="tmon-panel">
      <h2>Device Settings (stage for next check-in)</h2>
      <p class="description">Enter Unit ID and adjust settings. These are staged on the server and will be returned to the device on next check-in. Devices will apply and reboot when they receive staged settings.</p>

      <table class="form-table">
        <tr>
          <th><label for="tmon_unit_id">Unit ID</label></th>
          <td>
            <input id="tmon_unit_id" name="unit_id" list="tmon_known_units" class="regular-text" placeholder="e.g. 170170" />
            <datalist id="tmon_known_units">
              <?php foreach ((array)$known as $u) { printf('<option value="%s">', esc_attr($u)); } ?>
            </datalist>
            <button id="tmon_load_unit" class="button">Load</button>
          </td>
        </tr>

        <!-- Settings fields -->
        <tr><th>Node Type</th><td>
          <select id="tmon_NODE_TYPE" class="regular-text">
            <option value="">--</option>
            <option value="base">base</option>
            <option value="wifi">wifi</option>
            <option value="remote">remote</option>
          </select>
        </td></tr>

        <tr><th>Unit Name</th><td><input id="tmon_UNIT_Name" class="regular-text" /></td></tr>

        <tr><th>Sampling: Temperature</th>
          <td><label><input type="checkbox" id="tmon_SAMPLE_TEMP" /> Enabled</label></td></tr>
        <tr><th>Sampling: Humidity</th>
          <td><label><input type="checkbox" id="tmon_SAMPLE_HUMID" /> Enabled</label></td></tr>
        <tr><th>Sampling: Barometer</th>
          <td><label><input type="checkbox" id="tmon_SAMPLE_BAR" /> Enabled</label></td></tr>

        <tr><th>OLED</th><td><label><input type="checkbox" id="tmon_ENABLE_OLED" /> Enabled</label></td></tr>

        <tr><th>Engine Enabled</th><td><label><input type="checkbox" id="tmon_ENGINE_ENABLED" /> Enabled</label></td></tr>
        <tr><th>Engine Force Disabled</th><td><label><input type="checkbox" id="tmon_ENGINE_FORCE_DISABLED" /> Force disabled</label></td></tr>

        <tr><th>WiFi SSID</th><td><input id="tmon_WIFI_SSID" class="regular-text" /></td></tr>
        <tr><th>WiFi Pass</th><td><input id="tmon_WIFI_PASS" class="regular-text" /></td></tr>

        <tr><th>Relay Pin 1</th><td><input id="tmon_RELAY_PIN1" class="regular-text" type="number" /></td></tr>
        <tr><th>Relay Pin 2</th><td><input id="tmon_RELAY_PIN2" class="regular-text" type="number" /></td></tr>

      </table>

      <p>
        <button id="tmon_save_settings" class="button button-primary">Save Staged Settings</button>
        <span id="tmon_status" style="margin-left:12px"></span>
      </p>

      <script>
        (function(){
          const ajaxUrl = '<?php echo admin_url('admin-ajax.php'); ?>';
          const nonce = '<?php echo esc_js($nonce); ?>';

          function _get(id){ return document.getElementById(id); }
          function _show(msg, ok){ const s=_get('tmon_status'); s.textContent=msg; s.style.color = ok ? 'green' : 'red'; setTimeout(()=>s.textContent='', 4000); }

          async function loadUnit(unit_id){
            if (!unit_id) return _show('Enter Unit ID to load', false);
            const fd = new FormData();
            fd.append('action','tmon_uc_get_staged_settings');
            fd.append('unit_id', unit_id);
            try{
              const res = await fetch(ajaxUrl, { method:'POST', credentials:'same-origin', body:fd });
              const json = await res.json();
              if (!json.success) return _show(json.data || 'No staged settings', false);
              const data = json.data || {};
              // populate fields
              _get('tmon_NODE_TYPE').value = data.NODE_TYPE || '';
              _get('tmon_UNIT_Name').value = data.UNIT_Name || '';
              _get('tmon_SAMPLE_TEMP').checked = !!data.SAMPLE_TEMP;
              _get('tmon_SAMPLE_HUMID').checked = !!data.SAMPLE_HUMID;
              _get('tmon_SAMPLE_BAR').checked = !!data.SAMPLE_BAR;
              _get('tmon_ENABLE_OLED').checked = !!data.ENABLE_OLED;
              _get('tmon_ENGINE_ENABLED').checked = !!data.ENGINE_ENABLED;
              _get('tmon_ENGINE_FORCE_DISABLED').checked = !!data.ENGINE_FORCE_DISABLED;
              _get('tmon_WIFI_SSID').value = data.WIFI_SSID || '';
              _get('tmon_WIFI_PASS').value = data.WIFI_PASS || '';
              _get('tmon_RELAY_PIN1').value = data.RELAY_PIN1 || '';
              _get('tmon_RELAY_PIN2').value = data.RELAY_PIN2 || '';
              _show('Loaded staged settings', true);
            }catch(e){ _show('Load failed', false); }
          }

          async function saveForUnit(){
            const unit = _get('tmon_unit_id').value.trim();
            if (!unit) return _show('Unit ID required', false);
            const payload = {
              NODE_TYPE: _get('tmon_NODE_TYPE').value || '',
              UNIT_Name: _get('tmon_UNIT_Name').value || '',
              SAMPLE_TEMP: _get('tmon_SAMPLE_TEMP').checked ? 1 : 0,
              SAMPLE_HUMID: _get('tmon_SAMPLE_HUMID').checked ? 1 : 0,
              SAMPLE_BAR: _get('tmon_SAMPLE_BAR').checked ? 1 : 0,
              ENABLE_OLED: _get('tmon_ENABLE_OLED').checked ? 1 : 0,
              ENGINE_ENABLED: _get('tmon_ENGINE_ENABLED').checked ? 1 : 0,
              ENGINE_FORCE_DISABLED: _get('tmon_ENGINE_FORCE_DISABLED').checked ? 1 : 0,
              WIFI_SSID: _get('tmon_WIFI_SSID').value || '',
              WIFI_PASS: _get('tmon_WIFI_PASS').value || '',
              RELAY_PIN1: _get('tmon_RELAY_PIN1').value || '',
              RELAY_PIN2: _get('tmon_RELAY_PIN2').value || ''
            };
            const fd = new FormData();
            fd.append('action','tmon_uc_stage_device_settings');
            fd.append('unit_id', unit);
            fd.append('settings', JSON.stringify(payload));
            fd.append('_wpnonce', nonce);
            try{
              const res = await fetch(ajaxUrl, { method:'POST', credentials:'same-origin', body:fd });
              const json = await res.json();
              if (json.success) {
                _show('Staged settings saved', true);
              } else {
                _show(json.data || 'Save failed', false);
              }
            }catch(e){
              _show('AJAX error', false);
            }
          }

          document.getElementById('tmon_load_unit').addEventListener('click', function(e){ e.preventDefault(); loadUnit(_get('tmon_unit_id').value.trim()); });
          document.getElementById('tmon_save_settings').addEventListener('click', function(e){ e.preventDefault(); saveForUnit(); });
        })();
      </script>
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
