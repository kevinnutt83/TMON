<?php
// Unit Connector Hub pairing focus page
?>
<div class="wrap tmon-admin-page">
    <h1>Hub Pairing</h1>
    <?php if (isset($_GET['paired'])): ?>
        <?php if (intval($_GET['paired']) === 1): ?>
            <div class="notice notice-success is-dismissible"><p>Paired with Hub successfully.</p></div>
        <?php else: ?>
            <div class="notice notice-error is-dismissible"><p>Pairing failed<?php echo isset($_GET['msg']) ? ': ' . esc_html($_GET['msg']) : '.'; ?></p></div>
        <?php endif; ?>
    <?php endif; ?>
    <?php if (isset($_GET['keygen'])): ?>
        <div class="notice notice-success is-dismissible"><p>Shared key regenerated.</p></div>
    <?php endif; ?>
    <?php if (isset($_GET['tmon_refresh'])): ?>
        <div class="notice notice-success is-dismissible"><p>Devices refreshed from Admin hub.</p></div>
    <?php endif; ?>
    <script>
    (function(){
        setTimeout(function(){
            document.querySelectorAll('.notice.is-dismissible').forEach(function(n){ n.classList.add('hidden'); });
        }, 6000);
    })();
    </script>
    <?php
    $hub_url = trim(get_option('tmon_uc_hub_url', home_url()));
    $normalized = function_exists('tmon_uc_normalize_url') ? tmon_uc_normalize_url($hub_url) : '';
    $pair_url = wp_nonce_url(admin_url('admin-post.php?action=tmon_uc_pair_with_hub'), 'tmon_uc_pair_with_hub');
    $refresh_url = wp_nonce_url(admin_url('admin-post.php?action=tmon_uc_refresh_devices'), 'tmon_uc_refresh_devices');
    $keygen_url = wp_nonce_url(admin_url('admin-post.php?action=tmon_uc_generate_key'), 'tmon_uc_generate_key');
    $local_key = get_option('tmon_uc_admin_key', '');
    $hub_key = get_option('tmon_uc_hub_shared_key', '');
    $read_token = get_option('tmon_uc_hub_read_token', '');
    ?>
    <div class="tmon-card" style="max-width:820px;margin-bottom:18px;">
        <h2>Connection Overview</h2>
        <p><strong>Hub URL:</strong> <?php echo esc_html($hub_url ?: 'not set'); ?><?php if ($normalized): ?> <span style="color:#555;">(<?php echo esc_html($normalized); ?>)</span><?php endif; ?></p>
        <p><strong>Local Admin Key:</strong> <?php echo $local_key ? '<code>'.esc_html($local_key).'</code>' : '<em>not set</em>'; ?></p>
        <p><strong>Hub Shared Key:</strong> <?php echo $hub_key ? '<code>'.esc_html($hub_key).'</code>' : '<em>not received</em>'; ?></p>
        <p><strong>Hub Read Token:</strong> <?php echo $read_token ? '<code>'.esc_html($read_token).'</code>' : '<em>not received</em>'; ?></p>
        <p style="margin-top:12px;">
            <a class="button button-primary" href="<?php echo esc_url($pair_url); ?>">Pair with Hub</a>
            <a class="button" href="<?php echo esc_url($refresh_url); ?>">Refresh Devices</a>
            <a class="button" href="<?php echo esc_url($keygen_url); ?>">Generate New Admin Key</a>
        </p>
        <p class="description">Pairing posts your site URL and local key to the Admin hub. Use Refresh after pairing to pull provisioned devices.</p>
    </div>

    <div class="tmon-card" style="max-width:820px;margin-bottom:18px;">
        <h2>Hub Configuration</h2>
        <form method="post" action="options.php">
            <?php settings_fields('tmon_uc_settings'); ?>
            <table class="form-table">
                <tr valign="top">
                    <th scope="row">TMON Admin Hub URL</th>
                    <td><input type="url" name="tmon_uc_hub_url" class="regular-text" value="<?php echo esc_attr($hub_url); ?>" placeholder="https://admin.example.com" /></td>
                </tr>
                <tr valign="top">
                    <th scope="row">Shared Key (X-TMON-ADMIN)</th>
                    <td><input type="text" name="tmon_uc_admin_key" class="regular-text" value="<?php echo esc_attr($local_key); ?>" /></td>
                </tr>
                <tr valign="top">
                    <th scope="row">Remove all plugin data on deactivation</th>
                    <td><input type="checkbox" name="tmon_uc_remove_data_on_deactivate" value="1" <?php checked(1, get_option('tmon_uc_remove_data_on_deactivate', 0)); ?> /></td>
                </tr>
                <tr valign="top">
                    <th scope="row">Enable plugin auto-updates</th>
                    <td><input type="checkbox" name="tmon_uc_auto_update" value="1" <?php checked(1, get_option('tmon_uc_auto_update', 0)); ?> /></td>
                </tr>
            </table>
            <?php submit_button('Save Hub Settings'); ?>
        </form>
    </div>

    <div class="tmon-card" style="max-width:820px;">
        <h2>Paired Hubs</h2>
        <table class="widefat striped">
            <thead><tr><th>Hub URL</th><th>Normalized</th><th>Paired At</th><th>Read Token</th></tr></thead>
            <tbody>
            <?php
            $paired = get_option('tmon_uc_paired_sites', []);
            if (is_array($paired) && !empty($paired)) {
                foreach ($paired as $norm => $info) {
                    echo '<tr>';
                    echo '<td>'.esc_html($info['site'] ?? '').'</td>';
                    echo '<td><code>'.esc_html($norm).'</code></td>';
                    echo '<td>'.esc_html($info['paired_at'] ?? '').'</td>';
                    echo '<td><code>'.esc_html($info['read_token'] ?? '').'</code></td>';
                    echo '</tr>';
                }
            } else {
                echo '<tr><td colspan="4"><em>No paired hubs recorded yet.</em></td></tr>';
            }
            ?>
            </tbody>
        </table>
        <p class="description">If you do not see your Admin hub here after pairing, confirm the Hub URL and Admin key match on both sides.</p>
    </div>
</div>
