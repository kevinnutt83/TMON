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
});
