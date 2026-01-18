<?php
// Check if the user is allowed to access this page
if (!current_user_can('manage_options')) {
    wp_die(__('You do not have sufficient permissions to access this page.'));
}

if (isset($_GET['provision'])) {
    if ($_GET['provision'] === 'success') {
        echo '<div class="updated"><p>Device provisioned successfully.</p></div>';
    } elseif ($_GET['provision'] === 'fail') {
        echo '<div class="error"><p>Failed to provision device. Please check required fields.</p></div>';
    }
}

// Example provisioning form
?>
<form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
    <?php wp_nonce_field('tmon_admin_provision_device'); ?>
    <input type="hidden" name="action" value="tmon_admin_provision_device" />
    <table class="form-table">
        <tr>
            <th><label for="unit_id">Unit ID</label></th>
            <td>
                <!-- keep compatibility: if your form uses a select, set id/name to unit_id -->
                <input type="text" id="unit_id" name="unit_id" value="<?php echo $unit_val; ?>" class="regular-text" placeholder="UNIT123">
                <p class="description">Enter or select unit id. Selecting a unit will auto-fill Machine ID if available.</p>
            </td>
        </tr>
        <tr>
            <th><label for="machine_id">Machine ID</label></th>
            <td>
                <input type="text" id="machine_id" name="machine_id" value="<?php echo esc_attr( $provision['MACHINE_ID'] ?? '' ); ?>" class="regular-text">
                <p class="description">Hardware machine id (auto-populated when a unit is selected).</p>
            </td>
        </tr>
        <tr>
            <th><label for="company_id">Company ID</label></th>
            <td><input type="number" name="company_id" id="company_id" value=""></td>
        </tr>
        <tr>
            <th><label for="plan">Plan</label></th>
            <td><input type="text" name="plan" id="plan" value=""></td>
        </tr>
        <tr>
            <th><label for="status">Status</label></th>
            <td>
                <select name="status" id="status">
                    <option value="provisioned">Provisioned</option>
                    <option value="pending">Pending</option>
                    <option value="suspended">Suspended</option>
                </select>
            </td>
        </tr>
        <tr>
            <th><label for="notes">Notes</label></th>
            <td><textarea name="notes" id="notes"></textarea></td>
        </tr>
        <tr>
	<th scope="row"><label for="role">Device Type</label></th>
	<td>
		<?php
		// current value may be present in $device or $row depending on context
		$current_role = isset($device['NODE_TYPE']) ? $device['NODE_TYPE'] : (isset($row['NODE_TYPE']) ? $row['NODE_TYPE'] : '');
		if (function_exists('tmon_admin_render_node_role_select')) {
			tmon_admin_render_node_role_select('role', $current_role, array('class' => 'regular-text'));
		} else {
			// fallback: server-side static list (keeps page functional even if helper absent)
			$opts = array('base','wifi','remote');
			echo '<select name="role" id="role" class="regular-text">';
			echo '<option value="">Select a type</option>';
			foreach ($opts as $o) {
				$sel = ($o === $current_role) ? ' selected' : '';
				echo '<option value="'.esc_attr($o).'"'.$sel.'>'.esc_html($o).'</option>';
			}
			echo '</select>';
		}
		?>
	</td>
</tr>
    </table>
    <?php submit_button('Provision Device'); ?>
</form>

<!-- Small inline JS to auto-populate machine_id based on unit_id -->
<script>
(function(){
	const unitEl = document.getElementById('unit_id');
	const midEl  = document.getElementById('machine_id');
	const nonceElVal = '<?php echo esc_js( wp_create_nonce('tmon_admin_provision') ); ?>';
	if (!unitEl || !midEl) return;
	function onUnitChange(ev){
		const unit = unitEl.value ? String(unitEl.value).trim() : '';
		if (!unit) {
			midEl.value = '';
			return;
		}
		// show loading indicator
		midEl.placeholder = 'looking up...';
		const fd = new URLSearchParams();
		fd.append('action', 'tmon_get_device_info');
		fd.append('unit_id', unit);
		fd.append('_wpnonce', nonceElVal);
		fetch(ajaxurl || '<?php echo esc_js( admin_url('admin-ajax.php') ); ?>', {
			method: 'POST',
			credentials: 'same-origin',
			headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
			body: fd.toString()
		}).then(r=>r.json()).then(function(json){
			if (json && json.success && json.data) {
				if (json.data.machine_id) midEl.value = json.data.machine_id;
				if (json.data.unit_name && document.getElementById('unit_name')) {
					document.getElementById('unit_name').value = json.data.unit_name;
				}
			} else {
				// clear placeholder & value if not found
				if (json && json.data && json.data.message) {
					midEl.placeholder = json.data.message;
				} else {
					midEl.placeholder = 'none found';
				}
				// do NOT clobber user-entered machine id (only set when we have a result)
			}
		}).catch(function(err){
			midEl.placeholder = 'lookup err';
		}).finally(function(){
			setTimeout(function(){ midEl.placeholder = ''; }, 900);
		});
	}
	unitEl.addEventListener('change', onUnitChange);
	unitEl.addEventListener('blur', onUnitChange);
})();
</script>