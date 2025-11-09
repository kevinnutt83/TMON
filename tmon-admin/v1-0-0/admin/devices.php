<?php
if (!defined('ABSPATH')) exit;
if (!current_user_can('manage_options')) { echo '<div class="notice notice-error"><p>Forbidden</p></div>'; return; }

global $wpdb;
$table = $wpdb->prefix . 'tmon_devices';
$rows = [];
if ($wpdb->get_var($wpdb->prepare("SHOW TABLES LIKE %s", $table))) {
  $rows = $wpdb->get_results("SELECT unit_id, unit_name, last_seen, suspended, status FROM $table ORDER BY last_seen DESC", ARRAY_A);
}

// Handle suspend/enable form POST
if (isset($_POST['tmon_suspend_toggle']) && check_admin_referer('tmon_device_suspend')) {
  $unit_id = sanitize_text_field($_POST['unit_id'] ?? '');
  $want = sanitize_text_field($_POST['want'] ?? '');
  if ($unit_id && in_array($want, ['suspend','enable'], true)) {
    $endpoint = rest_url('tmon-admin/v1/device/suspend');
    $resp = wp_remote_post($endpoint, [
      'timeout' => 15,
      'body' => [
        'unit_id' => $unit_id,
        'suspend' => $want === 'suspend' ? '1' : '0'
      ]
    ]);
    echo '<div class="updated"><p>' . esc_html($unit_id) . ' ' . ($want === 'suspend' ? 'suspended' : 'enabled') . '</p></div>';
  }
}
?>
<div class="wrap">
  <h1>Devices</h1>
  <p>Toggle suspension state for registered devices. Suspension prevents data acceptance (authorization filter) while maintaining visibility.</p>
  <table class="widefat">
    <thead><tr><th>Unit ID</th><th>Name</th><th>Last Seen</th><th>Suspended</th><th>Actions</th></tr></thead>
    <tbody>
    <?php if (!$rows): ?>
      <tr><td colspan="5"><em>No devices found.</em></td></tr>
    <?php else: foreach ($rows as $r): ?>
      <tr>
        <td><?php echo esc_html($r['unit_id']); ?></td>
        <td><?php echo esc_html($r['unit_name']); ?></td>
        <td><?php echo esc_html($r['last_seen']); ?></td>
        <td><?php echo intval($r['suspended']) ? '<span style="color:#c00">Yes</span>' : 'No'; ?></td>
        <td>
          <form method="post" style="display:inline-block;">
            <?php wp_nonce_field('tmon_device_suspend'); ?>
            <input type="hidden" name="tmon_suspend_toggle" value="1" />
            <input type="hidden" name="unit_id" value="<?php echo esc_attr($r['unit_id']); ?>" />
            <input type="hidden" name="want" value="<?php echo intval($r['suspended']) ? 'enable' : 'suspend'; ?>" />
            <?php submit_button(intval($r['suspended']) ? 'Enable' : 'Suspend', 'secondary', '', false); ?>
          </form>
        </td>
      </tr>
    <?php endforeach; endif; ?>
    </tbody>
  </table>
</div>
