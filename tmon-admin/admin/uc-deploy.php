<?php
// TMON Admin: Deploy/Update Unit Connector to remote sites
add_action('admin_menu', function(){
    add_submenu_page('tmon-admin', 'Deploy Unit Connector', 'Deploy UC', 'manage_options', 'tmon-admin-deploy-uc', 'tmon_admin_deploy_uc_page');
});

function tmon_admin_deploy_uc_page(){
    if (!current_user_can('manage_options')) wp_die('Forbidden');
    echo '<div class="wrap"><h1>Deploy / Update Unit Connector</h1>';
    echo '<p class="description">Push the latest Unit Connector package to a paired site. Uses hub shared secret to sign payloads.</p>';

    $pairings = get_option('tmon_admin_uc_sites', []);
    $sites = [];
    if (is_array($pairings)) { foreach ($pairings as $url => $_) { $sites[] = $url; } }

    // Paired Unit Connectors summary (option map + table fallback)
    echo '<h2>Paired Unit Connectors</h2>';
    $rows = [];
    if (function_exists('tmon_admin_ensure_tables')) { tmon_admin_ensure_tables(); }
    global $wpdb;
    $uc_table = $wpdb->prefix . 'tmon_uc_sites';
    if ($wpdb && $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $uc_table))) {
        $rows = $wpdb->get_results("SELECT normalized_url, hub_key, read_token, COALESCE(last_seen, created_at) AS seen, created_at FROM {$uc_table} ORDER BY COALESCE(last_seen, created_at) DESC LIMIT 200", ARRAY_A);
    }
    if (!$rows && is_array($pairings)) {
        foreach ($pairings as $url => $meta) {
            $rows[] = [
                'normalized_url' => $url,
                'hub_key' => $meta['uc_key'] ?? '',
                'read_token' => $meta['read_token'] ?? '',
                'seen' => $meta['paired_at'] ?? '',
                'created_at' => $meta['paired_at'] ?? '',
            ];
        }
    }
    echo '<table class="widefat striped"><thead><tr><th>URL</th><th>Hub Key</th><th>Read Token</th><th>Paired/Last Seen</th></tr></thead><tbody>';
    if ($rows) {
        foreach ($rows as $r) {
            echo '<tr>';
            echo '<td>'.esc_html($r['normalized_url'] ?? '').'</td>';
            echo '<td><code>'.esc_html($r['hub_key'] ?? '').'</code></td>';
            echo '<td><code>'.esc_html($r['read_token'] ?? '').'</code></td>';
            echo '<td>'.esc_html($r['seen'] ?? $r['created_at'] ?? '').'</td>';
            echo '</tr>';
        }
    } else {
        echo '<tr><td colspan="4"><em>No paired Unit Connectors yet.</em></td></tr>';
    }
    echo '</tbody></table>';

    if (isset($_POST['tmon_deploy_uc'])) {
        if (!function_exists('tmon_admin_verify_nonce') || !tmon_admin_verify_nonce('tmon_admin_deploy_uc')) {
            echo '<div class="notice notice-error"><p>Security check failed. Please refresh and try again.</p></div>';
        } else {
            $site_url = esc_url_raw($_POST['site_url'] ?? '');
            $package_url = esc_url_raw($_POST['package_url'] ?? '');
            $action = sanitize_text_field($_POST['action_type'] ?? 'install');
            $sha256 = sanitize_text_field($_POST['sha256'] ?? '');
            $auth = sanitize_text_field($_POST['auth'] ?? '');
            if ($site_url && $package_url && function_exists('tmon_admin_uc_push_request')) {
                $result = tmon_admin_uc_push_request($site_url, $package_url, $action, $auth, $sha256);
                if (is_wp_error($result)) {
                    echo '<div class="notice notice-error"><p>'.esc_html($result->get_error_message()).'</p></div>';
                } else {
                    $cls = $result['success'] ? 'updated' : 'notice notice-error';
                    $msg = $result['success'] ? 'Push request sent.' : 'Push failed.';
                    echo '<div class="'.$cls.'"><p>'.$msg.' HTTP '.intval($result['code']).': '.esc_html($result['body']).'</p></div>';
                }
            } else {
                echo '<div class="notice notice-error"><p>Site URL and Package URL are required.</p></div>';
            }
        }
    }

    echo '<form method="post">';
    wp_nonce_field('tmon_admin_deploy_uc');
    echo '<table class="form-table">';
    echo '<tr><th>Target Site URL</th><td><input type="url" name="site_url" class="regular-text" list="tmon_uc_sites" placeholder="https://example.com" required>';    
    echo '<datalist id="tmon_uc_sites">';
    foreach ($sites as $s) { echo '<option value="'.esc_attr($s).'"></option>'; }
    echo '</datalist><p class="description">Must be a paired UC site.</p></td></tr>';
    echo '<tr><th>Package URL (.zip)</th><td><input type="url" name="package_url" class="regular-text" placeholder="https://hub.example.com/assets/tmon-unit-connector.zip" required><p class="description">Publicly accessible zip for UC.</p></td></tr>';
    echo '<tr><th>SHA256 (optional)</th><td><input type="text" name="sha256" class="regular-text" placeholder=""></td></tr>';
    echo '<tr><th>Action</th><td><select name="action_type"><option value="install">Install</option><option value="update">Update</option></select></td></tr>';
    echo '<tr><th>Authorization (optional)</th><td><input type="text" name="auth" class="regular-text" placeholder="Bearer ..."><p class="description">Optional header if the target site requires it.</p></td></tr>';
    echo '</table>';
    submit_button('Send');
    echo '</form>';
    echo '<h2>Recent Activity</h2>';
    global $wpdb;
    if (function_exists('tmon_admin_audit_ensure_tables')) {
        tmon_admin_audit_ensure_tables();
    }
    $audit_table = function_exists('tmon_admin_audit_table_name') ? tmon_admin_audit_table_name() : ($wpdb->prefix . 'tmon_admin_audit');
    $rows = [];
    if ($wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $audit_table))) {
        $rows = $wpdb->get_results($wpdb->prepare("SELECT ts AS created_at, action, COALESCE(context, extra) AS details FROM {$audit_table} WHERE action=%s ORDER BY ts DESC LIMIT 50", 'uc_confirm'), ARRAY_A);
    }
    echo '<table class="widefat"><thead><tr><th>Time</th><th>Details</th></tr></thead><tbody>';
    foreach ($rows as $r) echo '<tr><td>'.esc_html($r['created_at']).'</td><td><code>'.esc_html($r['details']).'</code></td></tr>';
    if (empty($rows)) echo '<tr><td colspan="2"><em>No confirmations yet.</em></td></tr>';
    echo '</tbody></table>';
    echo '</div>';
}

// Add a submenu for UC Site Data
add_action('admin_menu', function(){
    add_submenu_page('tmon-admin', 'UC Site Data', 'UC Site Data', 'manage_options', 'tmon-admin-uc-data', 'tmon_admin_uc_site_data_page');
});

function tmon_admin_uc_site_data_page(){
    if (!current_user_can('manage_options')) wp_die('Forbidden');

    // Handle "refresh device counts" POST
    if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['tmon_refresh_counts'])) {
        if (!function_exists('tmon_admin_verify_nonce') || !tmon_admin_verify_nonce('tmon_admin_uc_refresh')) {
            echo '<div class="notice notice-error"><p>Security check failed. Please refresh and try again.</p></div>';
        } else {
            $paired = get_option('tmon_admin_uc_sites', []);
            if (!is_array($paired)) $paired = [];
            $updated = 0;
            foreach ($paired as $url => &$info) {
                $count = null;
                $endpoint = rtrim($url, '/') . '/wp-json/tmon/v1/admin/site/devices';
                $remote = wp_remote_get($endpoint, ['timeout' => 5]);
                if (!is_wp_error($remote) && in_array(intval(wp_remote_retrieve_response_code($remote)), [200,201], true)) {
                    $body = wp_remote_retrieve_body($remote);
                    $j = json_decode($body, true);
                    if (is_array($j)) {
                        if (isset($j['count'])) $count = intval($j['count']);
                        elseif (isset($j['devices']) && is_array($j['devices'])) $count = count($j['devices']);
                        elseif (array_values($j) === $j) $count = count($j);
                    }
                }
                $info['devices'] = $count !== null ? intval($count) : '';
                $updated++;
            }
            unset($info);
            update_option('tmon_admin_uc_sites', $paired);
            echo '<div class="updated"><p>Refreshed device counts for '.intval($updated).' site(s).</p></div>';
        }
    }

    // Parameters
    $filter = isset($_GET['filter']) ? sanitize_text_field($_GET['filter']) : 'all'; // all|paired|unpaired
    $q = isset($_GET['q']) ? sanitize_text_field($_GET['q']) : '';
    $paged = max(1, intval($_GET['paged'] ?? 1));
    $per_page = 10;

    // Load pairings
    $paired = get_option('tmon_admin_uc_sites', []);
    if (!is_array($paired)) $paired = [];

    // Display cron last-run summary (if present)
    $last_run = get_option('tmon_admin_hourly_last_run', 0);
    $sites_count = get_option('tmon_admin_uc_sites_count', null);
    if ($last_run) {
        echo '<div class="notice notice-info"><p>Hourly cron last run: '.esc_html(date('Y-m-d H:i:s', intval($last_run))).' (sites: '.esc_html(intval($sites_count ?? count($paired))).')</p></div>';
    }

    // Normalize into rows
    $rows = [];
    foreach ($paired as $url => $info) {
        $is_paired = !empty($info['uc_key']) || !empty($info['paired_at']);
        $rows[] = [
            'url' => $url,
            'paired' => $is_paired,
            'paired_at' => $info['paired_at'] ?? '',
            'uc_key' => isset($info['uc_key']) ? 'yes' : '',
            'last_push' => $info['last_push'] ?? '',
            'devices' => isset($info['devices']) ? intval($info['devices']) : (isset($info['device_count']) ? intval($info['device_count']) : '')
        ];
    }

    // Filtering & search
    if ($filter === 'paired') {
        $rows = array_filter($rows, function($r){ return $r['paired']; });
    } elseif ($filter === 'unpaired') {
        $rows = array_filter($rows, function($r){ return !$r['paired']; });
    }
    if ($q !== '') {
        $q_l = strtolower($q);
        $rows = array_filter($rows, function($r) use ($q_l){ return false !== strpos(strtolower($r['url']), $q_l); });
    }

    $total = count($rows);
    $pages = max(1, ceil($total / $per_page));
    $offset = ($paged - 1) * $per_page;
    $rows = array_slice(array_values($rows), $offset, $per_page);

    echo '<div class="wrap"><h1>UC Site Data</h1>';
    echo '<form method="get" action="">';
    echo '<input type="hidden" name="page" value="tmon-admin-uc-data">';
    echo '<p class="search-box">';
    echo '<input type="search" name="q" value="'.esc_attr($q).'" placeholder="Search site URL" />';
    echo ' <select name="filter"><option value="all"'.($filter==='all'?' selected':'').'>All</option><option value="paired"'.($filter==='paired'?' selected':'').'>Paired</option><option value="unpaired"'.($filter==='unpaired'?' selected':'').'>Unpaired</option></select> ';
    echo '<button class="button">Filter</button></p>';
    echo '</form>';

    // Refresh counts form (POST)
    echo '<form method="post" style="margin:8px 0">';
    if (function_exists('wp_nonce_field')) wp_nonce_field('tmon_admin_uc_refresh');
    echo '<button class="button" name="tmon_refresh_counts" value="1">Refresh device counts (best-effort)</button>';
    echo '</form>';

    echo '<table class="widefat fixed striped"><thead><tr><th>Site URL</th><th>Paired</th><th>Paired At</th><th>UC Key</th><th>Devices</th><th>Last Push</th></tr></thead><tbody>';
    if ($rows) {
        foreach ($rows as $r) {
            $site_attr = esc_attr($r['url']);
            $devices_display = ($r['devices'] !== '' ? esc_html($r['devices']) : '<em>n/a</em>');
            // Per-site refresh button + status span (JS will update .tmon-dev-count)
            echo '<tr>';
            echo '<td><a href="'.esc_url($r['url']).'" target="_blank">'.esc_html($r['url']).'</a></td>';
            echo '<td>'.($r['paired']?'<span style="color:#2ecc71">Yes</span>':'<span style="color:#e67e22">No</span>').'</td>';
            echo '<td>'.esc_html($r['paired_at']).'</td>';
            echo '<td>'.esc_html($r['uc_key']).'</td>';
            echo '<td>';
            echo '<span class="tmon-dev-count" data-site="'.esc_attr($r['url']).'">'.$devices_display.'</span> ';
            echo '<button type="button" class="button tmon-uc-refresh-btn" data-site="'.$site_attr.'">Refresh</button> ';
            echo '<span class="tmon-uc-refresh-status" aria-hidden="true" style="margin-left:6px"></span>';
            echo '</td>';
            echo '<td>'.esc_html($r['last_push']).'</td>';
            echo '</tr>';
        }
    } else {
        echo '<tr><td colspan="6"><em>No sites found.</em></td></tr>';
    }
    echo '</tbody></table>';

    // Pagination
    echo '<p style="margin-top:8px;">';
    $base_url = remove_query_arg(['paged']);
    for ($i=1;$i<=$pages;$i++) {
        if ($i == $paged) {
            echo '<span class="button disabled" style="margin-right:4px;">'.$i.'</span>';
        } else {
            $link = add_query_arg(['paged'=>$i,'q'=>$q,'filter'=>$filter], $base_url);
            echo '<a class="button" href="'.esc_url($link).'" style="margin-right:4px;">'.$i.'</a>';
        }
    }
    echo '</p>';

    echo '</div>';
}

// enqueue per-page JS & CSS for UC Site Data
add_action('admin_enqueue_scripts', function($hook){
	// only load on our UC Site Data page
	if (isset($_GET['page']) && $_GET['page'] === 'tmon-admin-uc-data') {
		// assets path: plugin directory assets/
		$base = plugin_dir_url(__FILE__) . '../assets/';
		wp_enqueue_script('tmon-uc-refresh', $base . 'uc-refresh.js', [], '1.0', true);
		wp_enqueue_style('tmon-uc-refresh-css', $base . 'uc-refresh.css', [], '1.0');
		wp_localize_script('tmon-uc-refresh', 'tmonUcRefresh', [
			'ajax_url' => admin_url('admin-ajax.php'),
			'nonce'    => wp_create_nonce('tmon_admin_uc_refresh'),
		]);
	}
});

// AJAX handler for per-site device count refresh
add_action('wp_ajax_tmon_refresh_site_count', function(){
	if (!current_user_can('manage_options')) {
		wp_send_json_error('Forbidden', 403);
	}

	$nonce = $_REQUEST['_wpnonce'] ?? '';
	if (!wp_verify_nonce($nonce, 'tmon_admin_uc_refresh')) {
		wp_send_json_error('Invalid nonce', 403);
	}

	$site_url = $_REQUEST['site'] ?? '';
	$site_url = filter_var($site_url, FILTER_SANITIZE_URL);
	if (!filter_var($site_url, FILTER_VALIDATE_URL)) {
		wp_send_json_error('Invalid site URL', 400);
	}

	// Build auth headers from pairing metadata where available
	$headers = ['timeout' => 10];
	$pairings = get_option('tmon_admin_uc_sites', []);
	if (is_array($pairings) && isset($pairings[$site_url])) {
		$meta = $pairings[$site_url];
		// Prefer explicit read token (Bearer) if present
		if (!empty($meta['read_token'])) {
			$headers['headers'] = ['Authorization' => 'Bearer ' . $meta['read_token']];
		} elseif (!empty($meta['uc_key'])) {
			$headers['headers'] = ['X-TMON-HUB' => $meta['uc_key']];
		} elseif (!empty($meta['hub_key'])) {
			$headers['headers'] = ['X-TMON-HUB' => $meta['hub_key']];
		}
	} else {
		// Try global hub key fallback
		$hub_key = get_option('tmon_admin_hub_shared_key', '');
		if ($hub_key) {
			$headers['headers'] = ['X-TMON-HUB' => $hub_key];
		}
	}

	// Candidate endpoints (try multiple common variants to avoid 404)
	$candidates = [
		'/wp-json/tmon/v1/admin/site/devices',
		'/wp-json/tmon/v1/admin/site/devices-count',
		'/wp-json/tmon-admin/v1/site/devices',
		'/wp-json/tmon-admin/v1/site/devices-count',
		'/wp-json/tmon/v1/site/devices',
		'/wp-json/tmon-admin/v1/site/devices?count=1'
	];

	$count = null;
	$errors = [];
	foreach ($candidates as $path) {
		$endpoint = rtrim($site_url, '/') . $path;
		$remote = wp_remote_get($endpoint, $headers);
		$code = intval(wp_remote_retrieve_response_code($remote));
		if (in_array($code, [200,201], true)) {
			$body = wp_remote_retrieve_body($remote);
			$parsed = null;
			// Try to decode JSON
			if ($body) {
				$json = json_decode($body, true);
				if (json_last_error() === JSON_ERROR_NONE) {
					$parsed = $json;
				}
			}
			// Accept multiple shapes
			if (is_array($parsed)) {
				// {count: n}
				if (isset($parsed['count']) && is_numeric($parsed['count'])) {
					$count = intval($parsed['count']);
				}
				// {total: n}
				elseif (isset($parsed['total']) && is_numeric($parsed['total'])) {
					$count = intval($parsed['total']);
				}
				// {devices: [...]}
				elseif (isset($parsed['devices']) && is_array($parsed['devices'])) {
					$count = count($parsed['devices']);
				}
				// top-level array
				elseif (array_values($parsed) === $parsed) {
					$count = count($parsed);
				}
			}
			// Fall back: server may return plain integer in text
			if ($count === null && is_numeric(trim($body))) {
				$count = intval(trim($body));
			}
			if ($count !== null) {
				break;
			}
			// If we have a 200 but cannot parse, record and continue trying other endpoints
			$errors[] = "200 but unknown body at {$endpoint}";
		} else {
			$errors[] = "HTTP {$code} at {$endpoint}";
		}
	}

	if ($count !== null) {
		wp_send_json_success(['count' => $count]);
	} else {
		// Return helpful debug info
		wp_send_json_error(['message' => 'Failed to fetch device count', 'errors' => array_values($errors)], 502);
	}
});
