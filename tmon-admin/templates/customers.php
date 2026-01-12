<?php
if (!defined('ABSPATH')) exit;

if (!current_user_can('manage_options')) {
	wp_die('Forbidden');
}

$action = isset($_POST['tmon_action']) ? sanitize_text_field(wp_unslash($_POST['tmon_action'])) : '';
if ($action) {
	check_admin_referer('tmon_admin_customers');
}

if ($action === 'create_customer') {
	$name = sanitize_text_field(wp_unslash($_POST['name'] ?? ''));
	$uc_url = esc_url_raw(wp_unslash($_POST['unit_connector_url'] ?? ''));
	tmon_admin_upsert_customer([
		'id' => '',
		'name' => $name,
		'unit_connector_url' => $uc_url,
	]);
} elseif ($action === 'delete_customer') {
	$id = sanitize_text_field(wp_unslash($_POST['id'] ?? ''));
	tmon_admin_delete_customer($id);
}

$customers = tmon_admin_get_customers();
?>
<div class="wrap">
	<h1>Customers</h1>

	<p>Customers are organizational roots (company profile) used by Unit Connector users to group devices into locations/zones/groups.</p>

	<h2>Add Customer</h2>
	<form method="post">
		<?php wp_nonce_field('tmon_admin_customers'); ?>
		<input type="hidden" name="tmon_action" value="create_customer" />
		<table class="form-table" role="presentation">
			<tr>
				<th scope="row"><label for="tmon_name">Name</label></th>
				<td><input name="name" id="tmon_name" class="regular-text" required /></td>
			</tr>
			<tr>
				<th scope="row"><label for="tmon_uc_url">Unit Connector URL</label></th>
				<td><input name="unit_connector_url" id="tmon_uc_url" class="regular-text" placeholder="https://customer-site.example" /></td>
			</tr>
		</table>
		<?php submit_button('Add Customer'); ?>
	</form>

	<h2>Customer List</h2>
	<table class="wp-list-table widefat fixed striped">
		<thead>
			<tr>
				<th>ID</th>
				<th>Name</th>
				<th>Unit Connector URL</th>
				<th>Actions</th>
			</tr>
		</thead>
		<tbody>
		<?php if (!$customers): ?>
			<tr><td colspan="4"><em>No customers yet.</em></td></tr>
		<?php else: foreach ($customers as $c): ?>
			<tr>
				<td><?php echo esc_html($c['id']); ?></td>
				<td><?php echo esc_html($c['name']); ?></td>
				<td><?php echo esc_html($c['unit_connector_url'] ?? ''); ?></td>
				<td>
					<form method="post" style="display:inline">
						<?php wp_nonce_field('tmon_admin_customers'); ?>
						<input type="hidden" name="tmon_action" value="delete_customer" />
						<input type="hidden" name="id" value="<?php echo esc_attr($c['id']); ?>" />
						<?php submit_button('Delete', 'delete', 'submit', false); ?>
					</form>
				</td>
			</tr>
		<?php endforeach; endif; ?>
		</tbody>
	</table>
</div>
