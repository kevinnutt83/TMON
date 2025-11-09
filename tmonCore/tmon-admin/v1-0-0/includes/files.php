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
