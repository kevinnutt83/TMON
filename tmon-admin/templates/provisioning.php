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
            <td><input type="text" name="unit_id" id="unit_id" value="" required></td>
        </tr>
        <tr>
            <th><label for="machine_id">Machine ID</label></th>
            <td><input type="text" name="machine_id" id="machine_id" value="" required></td>
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
    </table>
    <?php submit_button('Provision Device'); ?>
</form>
<?php
// ...existing code...