<?php
// TMON Admin Files Page
if (!function_exists('tmon_admin_get_files')) return;
$files = tmon_admin_get_files();
$dir = WP_CONTENT_DIR . '/tmon-admin-packages';
echo '<div class="wrap"><h1>Files (Staging UC Packages)</h1>';
if (isset($_GET['uploaded'])) {
    if (intval($_GET['uploaded']) === 1) echo '<div class="updated"><p>File uploaded.</p></div>'; else echo '<div class="error"><p>Upload failed.</p></div>';
}
echo '<p>Packages directory: <code>' . esc_html($dir) . '</code></p>';
echo '<form method="post" action="' . esc_url(admin_url('admin-post.php')) . '" enctype="multipart/form-data">';
wp_nonce_field('tmon_admin_file_upload');
echo '<input type="hidden" name="action" value="tmon_admin_file_upload_post" />';
echo '<input type="file" name="package" accept=".zip,.tar,.gz,.bin,.json" required /> ';
submit_button('Upload Package', 'primary', '', false);
echo '</form>';
echo '<h2>Staged Files</h2>';
echo '<table class="widefat"><thead><tr><th>Time</th><th>Name</th><th>Type</th><th>Path</th></tr></thead><tbody>';
foreach ($files as $file) {
    echo '<tr><td>' . esc_html($file['timestamp']) . '</td><td>' . esc_html($file['name'] ?? '') . '</td><td>' . esc_html($file['type'] ?? '') . '</td><td><code>' . esc_html($file['path'] ?? '') . '</code></td></tr>';
}
echo '</tbody></table></div>';
