<?php
// Unit Connector API for remote install/update orchestrated by TMON Admin
add_action('rest_api_init', function(){
    register_rest_route('tmon/v1', '/uc/pull-install', [
        'methods' => 'POST',
        'callback' => 'tmon_uc_pull_install',
        'permission_callback' => '__return_true',
    ]);
});

function tmon_uc_pull_install($request){
    if (!current_user_can('manage_options')) return new WP_REST_Response(['status'=>'forbidden'], 403);
    $payload = $request->get_param('payload');
    $sig = $request->get_param('sig');
    // Optional: require an Authorization bearer (JWT or Application Password) at the spoke
    $require_auth = defined('TMON_UC_PULL_REQUIRE_AUTH') ? TMON_UC_PULL_REQUIRE_AUTH : false;
    if ($require_auth) {
        $auth = isset($_SERVER['HTTP_AUTHORIZATION']) ? $_SERVER['HTTP_AUTHORIZATION'] : '';
        if (!$auth) return new WP_REST_Response(['status'=>'forbidden','message'=>'Missing Authorization'], 403);
    }
    if (!$payload || !$sig) return rest_ensure_response(['status'=>'error','message'=>'Missing payload or sig']);
    $secret = defined('TMON_HUB_SHARED_SECRET') ? TMON_HUB_SHARED_SECRET : wp_salt('auth');
    $calc = hash_hmac('sha256', wp_json_encode($payload), $secret);
    if (!hash_equals($calc, $sig)) return new WP_REST_Response(['status'=>'forbidden'], 403);
    $package_url = esc_url_raw($payload['package_url'] ?? '');
    // Enforce HTTPS package URL
    if (stripos($package_url, 'https://') !== 0) {
        return rest_ensure_response(['status'=>'error','message'=>'HTTPS required for package_url']);
    }
    // Optional: pin package hash via payload['sha256']
    $expected_hash = isset($payload['sha256']) ? strtolower(sanitize_text_field($payload['sha256'])) : '';
    $action = sanitize_text_field($payload['action'] ?? 'install');
    $callback = esc_url_raw($payload['callback'] ?? '');
    if (!$package_url) return rest_ensure_response(['status'=>'error','message'=>'Missing package_url']);

    // Download and install plugin package
    include_once ABSPATH . 'wp-admin/includes/file.php';
    include_once ABSPATH . 'wp-admin/includes/misc.php';
    include_once ABSPATH . 'wp-admin/includes/class-wp-upgrader.php';
    include_once ABSPATH . 'wp-admin/includes/plugin.php';
    WP_Filesystem();
    $upgrader = new Plugin_Upgrader();
    // If hash pinning requested, pre-download and validate
    $result = null;
    if ($expected_hash) {
        $tmp = download_url($package_url);
        if (is_wp_error($tmp)) {
            $result = $tmp;
        } else {
            $data = file_get_contents($tmp);
            $hash = strtolower(hash('sha256', $data));
            if ($hash !== $expected_hash) {
                @unlink($tmp);
                return rest_ensure_response(['status'=>'error','message'=>'Package hash mismatch']);
            }
            $result = $upgrader->install($tmp, ['overwrite_package' => ($action === 'update')]);
        }
    } else {
        $result = $upgrader->install($package_url, ['overwrite_package' => ($action === 'update')]);
    }
    $status = 'ok';
    $details = $result;
    // Activate plugin if install went through and plugin main exists (best-effort)
    if ($result && is_wp_error($result) === false) {
        // Try to find plugin main
        $plugins = get_plugins();
        foreach ($plugins as $file => $data) {
            if (stripos($file, 'tmon-unit-connector.php') !== false) {
                activate_plugin($file);
                break;
            }
        }
    } else {
        $status = 'error';
    }
    // Confirm back to TMON Admin hub
    if ($callback) {
        wp_remote_post($callback, [
            'timeout' => 10,
            'headers' => ['Content-Type'=>'application/json'],
            'body' => wp_json_encode([
                'site_url' => home_url(),
                'status' => $status,
                'details' => is_wp_error($result) ? $result->get_error_message() : $details,
            ]),
        ]);
    }
    return rest_ensure_response(['status' => $status]);
}
