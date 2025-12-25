<?php
// TMON Admin File Management
// Usage: do_action('tmon_admin_file_upload', $file_info);
add_action('tmon_admin_file_upload', function($file_info) {
    $files = get_option('tmon_admin_files', []);
    $file_info['timestamp'] = current_time('mysql');
    $files[] = $file_info;
    update_option('tmon_admin_files', $files);
});

// Helper: Get files
function tmon_admin_get_files() {
    $files = get_option('tmon_admin_files', []);
    return array_reverse($files);
}

// Handle file uploads via admin-post
add_action('admin_post_tmon_admin_upload_file', function(){
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    if (!function_exists('tmon_admin_verify_nonce') || !tmon_admin_verify_nonce('tmon_admin_file_upload')) {
        wp_safe_redirect(admin_url('admin.php?page=tmon-admin-files&uploaded=0&error=nonce'));
        exit;
    }
    if (!isset($_FILES['package']) || empty($_FILES['package']['tmp_name'])) {
        wp_safe_redirect(admin_url('admin.php?page=tmon-admin-files&uploaded=0')); exit;
    }
    $file = $_FILES['package'];
    $name = sanitize_file_name($file['name']);
    $type = $file['type'];
    $dir = WP_CONTENT_DIR . '/tmon-admin-packages';
    if (!file_exists($dir)) wp_mkdir_p($dir);
    $dest = trailingslashit($dir) . $name;
    if (!move_uploaded_file($file['tmp_name'], $dest)) {
        wp_safe_redirect(admin_url('admin.php?page=tmon-admin-files&uploaded=0')); exit;
    }
    do_action('tmon_admin_file_upload', ['name'=>$name,'type'=>$type,'path'=>$dest]);
    wp_safe_redirect(admin_url('admin.php?page=tmon-admin-files&uploaded=1'));
    exit;
});

function tmon_admin_files_page(){
	echo '<div class="wrap"><h1>Device Files</h1>';
	tmon_admin_render_files_table();
	echo '</div>';
}
function tmon_admin_render_files_table(){
	$uploads = wp_get_upload_dir();
	$dir = trailingslashit($uploads['basedir']).'tmon'; wp_mkdir_p($dir);
	$files = glob($dir.'/*') ?: [];
	echo '<table class="wp-list-table widefat striped"><thead><tr><th>File</th><th>Size</th><th>Modified</th><th>Actions</th></tr></thead><tbody>';
	foreach ($files as $f) {
		$rel = str_replace($uploads['basedir'], $uploads['baseurl'], $f);
		echo '<tr><td>'.esc_html(basename($f)).'</td><td>'.esc_html(size_format(filesize($f))).'</td><td>'.esc_html(date('Y-m-d H:i', filemtime($f))).'</td><td>';
		echo '<a class="button" href="'.esc_url($rel).'" target="_blank">Download</a> ';
		echo '<a class="button" href="'.esc_url( add_query_arg(['action'=>'tmon_admin_send_file','file'=>basename($f)], admin_url('admin-ajax.php')) ).'">Send to Device</a> ';
		echo '<a class="button" href="'.esc_url( add_query_arg(['action'=>'tmon_admin_run_file','file'=>basename($f)], admin_url('admin-ajax.php')) ).'">Run on Device</a>';
		echo '</td></tr>';
	}
	echo '</tbody></table>';
}
