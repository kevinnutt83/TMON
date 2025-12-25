<?php
// OTA page template
?>
<div class="wrap">
    <h1>Over The Air (OTA) Updates</h1>
    <p>Send files, commands, and data to TMON devices. Request files from devices.</p>
    <form id="tmon-ota-upload-form" enctype="multipart/form-data">
        <input type="file" name="ota_file" required />
        <select name="unit_id" id="tmon-ota-unit-id">
            <option value="">All Units</option>
        </select>
        <input type="text" name="command" placeholder="Command to send (optional)" />
        <button type="submit">Send OTA</button>
    </form>
    <div id="tmon-ota-status"></div>
    <script>
    jQuery(document).ready(function($){
        // Populate unit ID dropdown
        $.get(ajaxurl, { action: 'tmon_uc_get_devices' }, function(resp) {
            if(resp.devices) {
                var $sel = $('#tmon-ota-unit-id');
                resp.devices.forEach(function(dev) {
                    $sel.append('<option value="'+dev.unit_id+'">'+dev.unit_id+' - '+dev.unit_name+'</option>');
                });
            }
        });
        $('#tmon-ota-upload-form').on('submit', function(e){
            e.preventDefault();
            var formData = new FormData(this);
            $.ajax({
                url: '/wp-json/tmon/v1/device/ota',
                method: 'POST',
                data: formData,
                processData: false,
                contentType: false,
                success: function(resp){
                    $('#tmon-ota-status').html('<pre>'+JSON.stringify(resp,null,2)+'</pre>');
                },
                error: function(xhr){
                    $('#tmon-ota-status').text('OTA failed: ' + xhr.statusText);
                }
            });
        });
    });
    </script>
</div>
