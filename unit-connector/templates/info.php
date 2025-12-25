<?php
// Information page template
?>
<div class="wrap">
    <h1>TMON Device Information</h1>
    <p>WordPress info, API status, total units connected, and drill-down to device data.</p>
    <div id="tmon-device-list"></div>
    <div id="tmon-device-details"></div>
    <h2>OTA Jobs</h2>
    <div id="tmon-ota-jobs">
        <table class="widefat">
            <thead><tr><th>ID</th><th>Unit ID</th><th>Job Type</th><th>Status</th><th>Created</th><th>Actions</th></tr></thead>
            <tbody></tbody>
        </table>
    </div>
    <h2>File Management</h2>
    <div id="tmon-file-management">
        <form id="tmon-file-upload-form" enctype="multipart/form-data">
            <input type="file" name="file" required />
            <button type="submit">Upload File</button>
        </form>
        <div id="tmon-file-list"></div>
    </div>
    <h2>Group Management</h2>
    <div id="tmon-group-management">
        <div id="tmon-group-list"></div>
        <button id="tmon-add-group">Add Group</button>
    </div>
    <script>
    jQuery(function($){
        // OTA Jobs Table
        $.get(ajaxurl, { action: 'tmon_uc_get_ota_jobs' }, function(resp) {
            if(resp.jobs) {
                var $tbody = $('#tmon-ota-jobs tbody');
                resp.jobs.forEach(function(job){
                    $tbody.append('<tr><td>'+job.id+'</td><td>'+job.unit_id+'</td><td>'+job.job_type+'</td><td>'+job.status+'</td><td>'+job.created_at+'</td><td><button data-id="'+job.id+'" class="tmon-ota-complete">Mark Complete</button></td></tr>');
                });
            }
        });
        // File Management (list files - placeholder)
        $('#tmon-file-upload-form').on('submit', function(e){
            e.preventDefault();
            // Implement file upload AJAX here
            alert('File upload not implemented.');
        });
        // Group Management (list groups - placeholder)
        $('#tmon-add-group').on('click', function(){
            alert('Add group not implemented.');
        });
    });
    </script>
</div>
