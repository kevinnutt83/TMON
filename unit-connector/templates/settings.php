<?php
// Settings page template
?>
<div class="wrap tmon-admin-page">
    <h1>TMON Unit Connector Settings</h1>
    <p class="description">Pairing and connection diagnostics moved to the Hub Pairing page under TMON Devices.</p>
    <?php if (isset($_GET['purge'])): ?>
        <div class="notice notice-warning is-dismissible"><p><?php echo $_GET['purge']==='all' ? 'All Unit Connector data purged.' : 'Unit data purged.'; ?></p></div>
    <?php endif; ?>
    <?php if (isset($_GET['tmon_cfg'])): ?>
        <?php if ($_GET['tmon_cfg'] === 'staged'): ?>
            <div class="notice notice-success is-dismissible"><p>Settings staged for Unit ID: <?php echo esc_html($_GET['unit_id'] ?? ''); ?></p></div>
        <?php elseif ($_GET['tmon_cfg'] === 'pushed'): ?>
            <div class="notice notice-success is-dismissible"><p>Staged settings pushed to Admin hub.</p></div>
        <?php else: ?>
            <div class="notice notice-error is-dismissible"><p>Settings staging failed<?php echo isset($_GET['msg']) ? ': ' . esc_html($_GET['msg']) : '.'; ?></p></div>
        <?php endif; ?>
    <?php endif; ?>
    <script>
    (function(){
        // Auto-hide admin notices after 6 seconds
        setTimeout(function(){
            document.querySelectorAll('.notice.is-dismissible').forEach(function(n){
                n.classList.add('hidden');
            });
        }, 6000);
    })();
    </script>

    <form method="post" action="options.php">
        <?php settings_fields('tmon_uc_settings'); ?>
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

    <h2>Device Configuration (Staged Settings)</h2>
    <p class="description">Staged settings UI has moved to the Device Data page to keep one canonical workflow.</p>
    <p>
        <a class="button button-primary" href="<?php echo esc_url(admin_url('admin.php?page=tmon-device-data')); ?>">Open Device Data</a>
    </p>

    <hr>
    <h2>Data Maintenance</h2>
    <?php do_settings_sections('tmon_uc_purge_page'); ?>
</div>
