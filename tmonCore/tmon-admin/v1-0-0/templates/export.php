<?php
// TMON Admin Data Export Page
$types = ['audit','notifications','ota','files','groups','custom_code'];
echo '<div class="wrap"><h1>Data Export</h1>';
echo '<form method="post"><select name="type">';
foreach ($types as $t) echo '<option value="' . esc_attr($t) . '">' . esc_html(ucfirst(str_replace('_',' ',$t))) . '</option>';
wp_nonce_field('tmon_admin_export');
echo '</select> <select name="format"><option value="csv">CSV</option><option value="json">JSON</option></select> <button type="submit">Export</button></form>';
if ($_SERVER['REQUEST_METHOD'] === 'POST' && in_array($_POST['type'],$types)) {
    if (!function_exists('tmon_admin_verify_nonce') || !tmon_admin_verify_nonce('tmon_admin_export')) {
        echo '<div class="notice notice-error"><p>Security check failed (nonce). Please refresh the page and try again.</p></div>';
    } else {
    $format = $_POST['format'] === 'json' ? 'json' : 'csv';
    $data = tmon_admin_export_data($_POST['type'], $format);
    echo '<h2>Exported Data</h2><textarea style="width:100%;height:200px;">' . esc_textarea($data) . '</textarea>';
    }
}
echo '</div>';
