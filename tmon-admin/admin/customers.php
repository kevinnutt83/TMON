<?php
add_action('admin_menu', function(){
    add_submenu_page('tmon-admin', 'Customers', 'Customers', 'manage_options', 'tmon-admin-customers', 'tmon_admin_customers_page');
});

function tmon_admin_customers_page(){
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    global $wpdb;
    if (!function_exists('tmon_admin_ensure_customer_tables')) {
        if (function_exists('tmon_admin_ensure_tables')) tmon_admin_ensure_tables();
    } else {
        tmon_admin_ensure_customer_tables();
    }

    $msg = '';
    if (isset($_POST['tmon_customer_action'])) {
        check_admin_referer('tmon_admin_customers');
        $action = sanitize_text_field($_POST['tmon_customer_action'] ?? '');
        if ($action === 'add_customer') {
            $name = sanitize_text_field($_POST['customer_name'] ?? '');
            $meta = wp_json_encode($_POST['customer_meta'] ?? []);
            if ($name) {
                $wpdb->insert($wpdb->prefix . 'tmon_customers', ['name'=>$name,'meta'=>$meta]);
                echo '<div class="updated"><p>Customer added.</p></div>';
            }
        } elseif ($action === 'add_location') {
            $cust = intval($_POST['customer_id'] ?? 0);
            $name = sanitize_text_field($_POST['location_name'] ?? '');
            $lat = floatval($_POST['lat'] ?? 0);
            $lng = floatval($_POST['lng'] ?? 0);
            $addr = sanitize_text_field($_POST['address'] ?? '');
            $ucsite = sanitize_text_field($_POST['uc_site_url'] ?? '');
            if ($cust && $name) {
                $wpdb->insert($wpdb->prefix . 'tmon_customer_locations', ['customer_id'=>$cust,'name'=>$name,'lat'=>$lat,'lng'=>$lng,'address'=>$addr,'uc_site_url'=>$ucsite]);
                echo '<div class="updated"><p>Location added.</p></div>';
            }
        } elseif ($action === 'sync_uc' && !empty($_POST['site_url'])) {
            $site = esc_url_raw($_POST['site_url']);
            // AJAX endpoint also exists; call helper directly
            $res = tmon_admin_push_locations_to_uc($site);
            if (is_wp_error($res)) echo '<div class="notice notice-error"><p>'.esc_html($res->get_error_message()).'</p></div>';
            else echo '<div class="updated"><p>Sync request sent to '.esc_html($site).'</p></div>';
        }
    }

    // Fetch customers & locations
    $customers = $wpdb->get_results("SELECT id,name,meta,created_at FROM {$wpdb->prefix}tmon_customers ORDER BY id DESC", ARRAY_A);
    $locations = $wpdb->get_results("SELECT id,customer_id,name,lat,lng,address,uc_site_url,created_at FROM {$wpdb->prefix}tmon_customer_locations ORDER BY id DESC", ARRAY_A);
    $paired = get_option('tmon_admin_uc_sites', []);

    echo '<div class="wrap"><h1>Customers & Locations</h1>';
    echo '<h2>Add Customer</h2>';
    echo '<form method="post">';
    wp_nonce_field('tmon_admin_customers');
    echo '<input type="hidden" name="tmon_customer_action" value="add_customer">';
    echo '<table class="form-table"><tr><th>Name</th><td><input name="customer_name" class="regular-text" required></td></tr>';
    echo '<tr><th>Meta (JSON)</th><td><textarea name="customer_meta" rows="3" class="large-text">{}</textarea></td></tr></table>';
    submit_button('Add Customer');
    echo '</form>';

    echo '<h2>Add Location</h2>';
    echo '<form method="post">';
    wp_nonce_field('tmon_admin_customers');
    echo '<input type="hidden" name="tmon_customer_action" value="add_location">';
    echo '<table class="form-table">';
    echo '<tr><th>Customer</th><td><select name="customer_id">';
    foreach ((array)$customers as $c) echo '<option value="'.intval($c['id']).'">'.esc_html($c['name']).'</option>';
    echo '</select></td></tr>';
    echo '<tr><th>Name</th><td><input name="location_name" class="regular-text" required></td></tr>';
    echo '<tr><th>Latitude</th><td><input name="lat" class="regular-text"></td></tr>';
    echo '<tr><th>Longitude</th><td><input name="lng" class="regular-text"></td></tr>';
    echo '<tr><th>Address</th><td><textarea name="address" class="large-text"></textarea></td></tr>';
    echo '<tr><th>UC Site URL (optional)</th><td><input name="uc_site_url" class="regular-text" list="tmon_uc_sites">';
    echo '<datalist id="tmon_uc_sites">';
    foreach ($paired as $url => $meta) echo '<option value="'.esc_attr($url).'"></option>';
    echo '</datalist></td></tr>';
    echo '</table>';
    submit_button('Add Location');
    echo '</form>';

    echo '<h2>Existing Locations</h2>';
    echo '<table class="widefat striped"><thead><tr><th>Customer</th><th>Location</th><th>Lat</th><th>Lng</th><th>UC Site</th><th>Actions</th></tr></thead><tbody>';
    foreach ((array)$locations as $l) {
        $cust_name = $wpdb->get_var($wpdb->prepare("SELECT name FROM {$wpdb->prefix}tmon_customers WHERE id=%d", $l['customer_id']));
        echo '<tr><td>'.esc_html($cust_name).'</td><td>'.esc_html($l['name']).'</td><td>'.esc_html($l['lat']).'</td><td>'.esc_html($l['lng']).'</td><td>'.esc_html($l['uc_site_url']).'</td>';
        echo '<td>';
        if ($l['uc_site_url']) {
            echo '<form method="post" style="display:inline">';
            wp_nonce_field('tmon_admin_customers');
            echo '<input type="hidden" name="tmon_customer_action" value="sync_uc">';
            echo '<input type="hidden" name="site_url" value="'.esc_attr($l['uc_site_url']).'">';
            submit_button('Sync to UC', 'secondary small', '', false);
            echo '</form>';
        }
        echo '</td></tr>';
    }
    if (empty($locations)) echo '<tr><td colspan="6"><em>No locations recorded yet.</em></td></tr>';
    echo '</tbody></table>';

    // Bulk sync to all paired sites
    echo '<h2>Paired Unit Connectors</h2>';
    echo '<form method="post">';
    wp_nonce_field('tmon_admin_customers');
    echo '<table class="widefat"><thead><tr><th>Site URL</th><th>Paired At</th><th>Action</th></tr></thead><tbody>';
    if (is_array($paired) && $paired) {
        foreach ($paired as $url => $meta) {
            echo '<tr><td>'.esc_html($url).'</td><td>'.esc_html($meta['paired_at'] ?? '').'</td><td>';
            echo '<button class="button" name="tmon_customer_action" value="sync_uc"><input type="hidden" name="site_url" value="'.esc_attr($url).'">Sync All Locations</button>';
            echo '</td></tr>';
        }
    } else {
        echo '<tr><td colspan="3"><em>No paired Unit Connectors.</em></td></tr>';
    }
    echo '</tbody></table>';
    echo '</form>';

    // Add a section for recent sync audit
    echo '<h2>Recent Sync Activity</h2>';
    $sync_audit = get_option('tmon_admin_sync_audit', []);
    echo '<table class="widefat striped"><thead><tr><th>Time</th><th>Site</th><th>OK</th><th>Code/Snip</th></tr></thead><tbody id="tmon-sync-audit-body">';
    if (is_array($sync_audit) && $sync_audit) {
        foreach (array_reverse($sync_audit) as $s) {
            echo '<tr><td>'.date('Y-m-d H:i:s', intval($s['ts'])).'</td><td>'.esc_html($s['site']).'</td><td>'.($s['ok']? 'Yes':'No').'</td><td>'.esc_html(isset($s['snip']) ? $s['snip'] : ($s['error'] ?? '')).'</td></tr>';
        }
    } else {
        echo '<tr><td colspan="4"><em>No sync activity recorded yet.</em></td></tr>';
    }
    echo '</tbody></table>';

    // Add AJAX "Sync Now" JS (bind to existing Sync buttons by class)
    ?>
    <script>
    (function(){
        document.querySelectorAll('form input[name="tmon_customer_action"][value="sync_uc"]').forEach(function(btn){
            // find enclosing form and replace with AJAX-enabled button
            var form = btn.closest('form');
            if (!form) return;
            var site = form.querySelector('input[name="site_url"]').value;
            var ajaxBtn = document.createElement('button');
            ajaxBtn.className = 'button';
            ajaxBtn.textContent = 'Sync Now (AJAX)';
            ajaxBtn.type = 'button';
            ajaxBtn.addEventListener('click', function(ev){
                ev.preventDefault();
                ajaxBtn.disabled = true;
                ajaxBtn.textContent = 'Syncing...';
                fetch(ajaxurl, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
                    body: new URLSearchParams({
                        'action': 'tmon_admin_sync_locations',
                        'site_url': site,
                        '_wpnonce': '<?php echo wp_create_nonce("tmon_admin_customers"); ?>'
                    })
                }).then(function(r){ return r.json(); }).then(function(j){
                    ajaxBtn.disabled = false;
                    ajaxBtn.textContent = 'Sync Now (AJAX)';
                    if (j.success) {
                        alert('Sync requested: ' + JSON.stringify(j.data));
                        // refresh audit area (rudimentary: reload page section)
                        location.reload();
                    } else {
                        alert('Sync failed: ' + JSON.stringify(j.data || j));
                    }
                }).catch(function(e){
                    ajaxBtn.disabled = false;
                    ajaxBtn.textContent = 'Sync Now (AJAX)';
                    alert('Sync error: ' + e);
                });
            });
            form.appendChild(document.createTextNode(' '));
            form.appendChild(ajaxBtn);
        });
    })();
    </script>
    <?php

    echo '</div>';
}

