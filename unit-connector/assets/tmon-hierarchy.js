// JS for TMON Hierarchy drag-and-drop and map interface
jQuery(document).ready(function($){
    if (typeof window.L === 'undefined') {
        console.warn('TMON hierarchy map disabled: Leaflet not loaded');
        return;
    }
    if($('#tmon-map-container').length) {
        var map = L.map('tmon-map-container').setView([37.0902, -95.7129], 4); // Default USA
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
        }).addTo(map);
        // TODO: Load zones, clusters, units from AJAX and add markers/polygons
        // Load hierarchy from REST API
        $.get('/wp-json/tmon/v1/hierarchy', function(resp){
            if(resp.success && resp.data) {
                // Render org tree (basic example)
                $('#tmon-hierarchy-app').html('<pre>'+JSON.stringify(resp.data, null, 2)+'</pre>');
                // TODO: Render as interactive tree, allow drag/drop, edit, delete
                // TODO: Render markers/polygons for each org level on map
            }
        });
        // TODO: Allow uploading overhead images for zones, overlay on map
        // TODO: Click/drag to edit, set GPS, demarcate clusters/units
        // TODO: AJAX CRUD for all org levels
    }
    // Keyboard shortcuts for hierarchy UI
    $(document).on('keydown', function(e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        if (e.key === 'n') { $('#tmon-hierarchy-app .add-btn').click(); }
        if (e.key === 'e') { $('#tmon-hierarchy-app .edit-btn').click(); }
        if (e.key === 'd') { $('#tmon-hierarchy-app .delete-btn').click(); }
    });
    // Tooltips for all actions
    $(document).on('mouseenter', '.add-btn', function(){ $(this).attr('title','Add new'); });
    $(document).on('mouseenter', '.edit-btn', function(){ $(this).attr('title','Edit'); });
    $(document).on('mouseenter', '.delete-btn', function(){ $(this).attr('title','Delete'); });
});
