<?php
// Settings page template
?>
<div class="wrap tmon-admin-page">
    <h1>TMON Unit Connector Settings</h1>
    <?php if (isset($_GET['keygen'])): ?>
        <div class="updated"><p>Shared key generated.</p></div>
    <?php endif; ?>
    <?php if (isset($_GET['paired'])): ?>
        <?php if (intval($_GET['paired']) === 1): ?>
            <div class="updated"><p>Paired with Hub successfully.</p></div>
        <?php else: ?>
            <div class="error"><p>Pairing failed<?php echo isset($_GET['msg']) ? ': ' . esc_html($_GET['msg']) : '.'; ?></p></div>
        <?php endif; ?>
    <?php endif; ?>
    <?php if (isset($_GET['purge'])): ?>
        <div class="updated"><p><?php echo $_GET['purge']==='all' ? 'All Unit Connector data purged.' : 'Unit data purged.'; ?></p></div>
    <?php endif; ?>
    <form method="post" action="options.php">
        <?php settings_fields('tmon_uc_settings'); do_settings_sections('tmon_uc_settings'); ?>
        <table class="form-table">
            <tr valign="top">
                <th scope="row">Remove all plugin data on deactivation</th>
                <td><input type="checkbox" name="tmon_uc_remove_data_on_deactivate" value="1" <?php checked(1, get_option('tmon_uc_remove_data_on_deactivate', 0)); ?> /></td>
            </tr>
            <tr valign="top">
                <th scope="row">Enable plugin auto-updates</th>
                <td><input type="checkbox" name="tmon_uc_auto_update" value="1" <?php checked(1, get_option('tmon_uc_auto_update', 0)); ?> /></td>
            </tr>
            <tr valign="top">
                <th scope="row">Hub Shared Key (from Admin)</th>
                <td><input type="text" class="regular-text" value="<?php echo esc_attr(get_option('tmon_uc_hub_shared_key', '')); ?>" readonly></td>
            </tr>
            <tr>
                <th scope="row">Data Maintenance</th>
                <td><em>Use the Purge Tools below to permanently delete device data and logs.</em></td>
            </tr>
        </table>
        <?php submit_button(); ?>
    </form>
    <hr>
    <h2>Data Maintenance</h2>
    <?php do_settings_sections('tmon_uc_purge_page'); ?>
</div>
