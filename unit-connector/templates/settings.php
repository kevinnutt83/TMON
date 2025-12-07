<?php
// Settings page template
?>
<div class="wrap tmon-admin-page">
    <h1>TMON Unit Connector Settings</h1>
    <?php if (isset($_GET['keygen'])): ?>
        <div class="notice notice-success is-dismissible"><p>Shared key generated.</p></div>
    <?php endif; ?>
    <?php if (isset($_GET['paired'])): ?>
        <?php if (intval($_GET['paired']) === 1): ?>
            <div class="notice notice-success is-dismissible"><p>Paired with Hub successfully.</p></div>
        <?php else: ?>
            <div class="notice notice-error is-dismissible"><p>Pairing failed<?php echo isset($_GET['msg']) ? ': ' . esc_html($_GET['msg']) : '.'; ?></p></div>
        <?php endif; ?>
    <?php endif; ?>
    <?php if (isset($_GET['purge'])): ?>
        <div class="notice notice-warning is-dismissible"><p><?php echo $_GET['purge']==='all' ? 'All Unit Connector data purged.' : 'Unit data purged.'; ?></p></div>
    <?php endif; ?>
    <?php if (isset($_GET['tmon_cfg'])): ?>
        <?php if ($_GET['tmon_cfg'] === 'staged'): ?>
            <div class="notice notice-success is-dismissible"><p>Settings staged for Unit ID: <?php echo esc_html($_GET['unit_id'] ?? ''); ?></p></div>
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

    <h2>Device Configuration (Staged Settings)</h2>
    <p class="description">Stage configuration values that devices will fetch and apply on next sync.</p>
    <form method="post" action="<?php echo esc_url(admin_url('admin-post.php')); ?>">
        <?php wp_nonce_field('tmon_uc_stage_settings'); ?>
        <input type="hidden" name="action" value="tmon_uc_stage_settings" />
        <table class="form-table">
            <tr>
                <th scope="row">Unit ID</th>
                <td><input type="text" name="unit_id" class="regular-text" required placeholder="e.g., 123456"></td>
            </tr>
            <?php
            if (function_exists('tmon_uc_settings_schema')) {
                $schema = tmon_uc_settings_schema();
                foreach ($schema as $key => $meta) {
                    echo '<tr><th scope="row">'.esc_html($meta['label']).'</th><td>';
                    $type = $meta['type'];
                    $desc = isset($meta['desc']) ? $meta['desc'] : '';
                    if ($type === 'bool') {
                        echo '<label><input type="checkbox" name="'.esc_attr($key).'" value="1"> Enable</label>';
                    } elseif ($type === 'enum' && !empty($meta['enum']) && is_array($meta['enum'])) {
                        echo '<select name="'.esc_attr($key).'">';
                        foreach ($meta['enum'] as $opt) {
                            echo '<option value="'.esc_attr($opt).'">'.esc_html($opt).'</option>';
                        }
                        echo '</select>';
                    } else {
                        $inputType = $type === 'number' ? 'number' : ($type === 'url' ? 'url' : 'text');
                        echo '<input type="'.$inputType.'" name="'.esc_attr($key).'" class="regular-text">';
                    }
                    if ($desc) echo '<p class="description">'.esc_html($desc).'</p>';
                    echo '</td></tr>';
                }
            }
            ?>
        </table>
        <?php submit_button('Stage Settings'); ?>
    </form>
</div>
