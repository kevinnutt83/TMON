// Admin and frontend JS for TMON plugin
jQuery(document).ready(function($){
    function renderDeviceList(resp) {
            if (resp.devices && resp.devices.length) {
                // Build group hierarchy
                let companies = {};
                resp.devices.forEach(function(dev){
                    if (!companies[dev.company]) companies[dev.company] = {};
                    if (!companies[dev.company][dev.site]) companies[dev.company][dev.site] = {};
                    if (!companies[dev.company][dev.site][dev.zone]) companies[dev.company][dev.site][dev.zone] = {};
                    if (!companies[dev.company][dev.site][dev.zone][dev.cluster]) companies[dev.company][dev.site][dev.zone][dev.cluster] = [];
                    companies[dev.company][dev.site][dev.zone][dev.cluster].push(dev);
                });
                function renderLevel(obj, level) {
                    let html = '<ul>';
                    for (let key in obj) {
                        if (Array.isArray(obj[key])) {
                            obj[key].forEach(function(dev){
                                html += '<li><a href="#" class="tmon-device-link" data-unit_id="' + dev.unit_id + '">' + dev.unit_name + ' (' + dev.unit_id + ')' + (dev.suspended ? ' <span style="color:red">[Suspended]</span>' : '') + '</a></li>';
                            });
                        } else {
                            html += '<li>' + key + renderLevel(obj[key], level+1) + '</li>';
                        }
                    }
                    html += '</ul>';
                    return html;
                }
                $('#tmon-device-list').html(renderLevel(companies, 0));
                // Device details on click
                $('.tmon-device-link').on('click', function(e){
                    e.preventDefault();
                    let unit_id = $(this).data('unit_id');
                $.post(ajaxurl || window.tmon_uc_ajaxurl, {action: 'tmon_uc_get_device_status', unit_id: unit_id}, function(resp){
                        let html = '<h3>Device Details</h3>';
                        html += '<pre>' + JSON.stringify(resp.status, null, 2) + '</pre>';
                        $('#tmon-device-details').html(html);
                    });
                });
            } else {
                $('#tmon-device-list').html('No devices found.');
            }
    }

    // Device list shortcode AJAX
    if ($('#tmon-device-list').length) {
        function refreshDeviceList() {
            $.post(ajaxurl || window.tmon_uc_ajaxurl, {action: 'tmon_uc_get_devices'}, function(resp){
                renderDeviceList(resp);
            });
        }
        refreshDeviceList();
        // Auto-refresh every 30 seconds
        setInterval(refreshDeviceList, 30000);
    }
    // Device status shortcode AJAX
    if ($('#tmon-device-status').length) {
        function refreshDeviceStatus() {
            $.post(ajaxurl || window.tmon_uc_ajaxurl, {action: 'tmon_uc_get_device_status'}, function(resp){
                if (resp.status) {
                    $('#tmon-device-status').html(JSON.stringify(resp.status));
                } else {
                    $('#tmon-device-status').html('No status found.');
                }
            });
        }
        refreshDeviceStatus();
        setInterval(refreshDeviceStatus, 30000);
    }

    // Device Data admin page: settings load/stage/push
    const dataPage = $('#tmon-settings-card');
    if (dataPage.length) {
        const picker = $('#tmon-unit-picker');
        const statusEl = $('#tmon-settings-status');
        const appliedEl = $('#tmon-settings-applied');
        const stagedEl = $('#tmon-settings-staged');
        const editorEl = $('#tmon-settings-editor');
        const machineEl = $('#tmon-device-machine');
        const updatedEl = $('#tmon-device-updated');
        const nonce = dataPage.data('nonce');

        function setStatus(msg, cls) {
            statusEl.removeClass('tmon-status-ok tmon-status-err tmon-status-info');
            if (cls === 'ok') statusEl.addClass('tmon-status-ok');
            if (cls === 'err') statusEl.addClass('tmon-status-err');
            if (cls === 'info') statusEl.addClass('tmon-status-info');
            statusEl.text(msg || '');
        }

        function loadBundle(unit) {
            if (!unit) { setStatus('Select a device first.', 'info'); return; }
            setStatus('Loading...', 'info');
            $.post(ajaxurl || window.tmon_uc_ajaxurl, {action:'tmon_uc_device_bundle', nonce: nonce, unit_id: unit}, function(resp){
                if (!resp || !resp.success) { setStatus((resp && resp.data && resp.data.message) || 'Load failed.', 'err'); return; }
                const data = resp.data || {};
                machineEl.text(data.machine_id || '');
                updatedEl.text(data.last_seen || '');
                appliedEl.text(JSON.stringify(data.settings || {}, null, 2));
                stagedEl.text(JSON.stringify(data.staged || {}, null, 2));
                const seed = (data.staged && Object.keys(data.staged).length) ? data.staged : (data.settings || {});
                editorEl.val(JSON.stringify(seed, null, 2));
                setStatus('Loaded.', 'ok');
            }).fail(function(){ setStatus('Network error loading device.', 'err'); });
        }

        function pushSettings(unit) {
            if (!unit) { setStatus('Select a device first.', 'info'); return; }
            let parsed;
            const raw = editorEl.val() || '';
            if (raw.trim() === '') { parsed = {}; }
            else {
                try { parsed = JSON.parse(raw); }
                catch (e) { setStatus('Invalid JSON: ' + e.message, 'err'); return; }
            }
            setStatus('Staging & pushing...', 'info');
            $.post(ajaxurl || window.tmon_uc_ajaxurl, {action:'tmon_uc_stage_settings', nonce: nonce, unit_id: unit, settings_json: JSON.stringify(parsed)}, function(resp){
                if (!resp || !resp.success) { setStatus((resp && resp.data && resp.data.message) || 'Push failed.', 'err'); return; }
                setStatus(resp.data && resp.data.message ? resp.data.message : 'Staged and pushed.', 'ok');
                loadBundle(unit);
            }).fail(function(){ setStatus('Network error pushing settings.', 'err'); });
        }

        $('#tmon-settings-load').on('click', function(e){ e.preventDefault(); loadBundle(picker.val()); });
        $('#tmon-settings-push').on('click', function(e){ e.preventDefault(); pushSettings(picker.val()); });
        if (picker.length) { picker.on('change', function(){ loadBundle(picker.val()); }); loadBundle(picker.val()); }
    }
});
