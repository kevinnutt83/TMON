<?php
if (!defined('ABSPATH')) exit;

// Default hub URL (tmon-admin site)
if (!function_exists('tmon_uc_get_default_hub_url')) {
	function tmon_uc_get_default_hub_url() {
		return 'https://tmonsystems.com';
	}
}

// Return canonical hub URL (constant override -> option -> default).
if (!function_exists('tmon_uc_get_hub_url')) {
	function tmon_uc_get_hub_url() {
		if (defined('TMON_HUB_URL') && TMON_HUB_URL) {
			return untrailingslashit(TMON_HUB_URL);
		}
		$opt = get_option('tmon_uc_hub_url', '');
		// If empty, set to default and persist
		if (empty($opt)) {
			$def = tmon_uc_get_default_hub_url();
			update_option('tmon_uc_hub_url', $def);
			return $def;
		}
		// Auto-correct deprecated hosts (movealong.us) -> default hub
		if (stripos($opt, 'movealong.us') !== false) {
			$def = tmon_uc_get_default_hub_url();
			update_option('tmon_uc_hub_url', $def);
			error_log("tmon-unit-connector: replaced deprecated hub URL '{$opt}' with '{$def}'.");
			add_action('admin_notices', function() use ($opt, $def) {
				if (!is_admin()) return;
				if (function_exists('current_user_can') && !current_user_can('manage_options')) return;
				echo '<div class="notice notice-warning"><p>TMON Unit Connector replaced deprecated hub URL "'.esc_html($opt).'" with "'.esc_html($def) . '". Verify your hub settings if necessary.</p></div>';
			});
			return $def;
		}
		return untrailingslashit($opt);
	}
}

if (!function_exists('tmon_uc_set_hub_url')) {
	function tmon_uc_set_hub_url($url) {
		$url = untrailingslashit(esc_url_raw($url));
		update_option('tmon_uc_hub_url', $url);
		error_log("tmon-unit-connector: hub URL explicitly set to {$url}");
	}
}

// Local admin key helper (constant override -> option -> empty)
if (!function_exists('tmon_uc_get_local_admin_key')) {
	function tmon_uc_get_local_admin_key() {
		if (defined('TMON_LOCAL_ADMIN_KEY') && TMON_LOCAL_ADMIN_KEY) return TMON_LOCAL_ADMIN_KEY;
		return get_option('tmon_uc_local_admin_key', '');
	}
}

// ------------------------
// Time helpers: parse & format MySQL DATETIME stored in WP site timezone
// ------------------------
if (!function_exists('tmon_uc_mysql_to_utc_timestamp')) {
	/**
	 * Convert a MySQL DATETIME string (stored using WP site timezone settings) into a UTC epoch timestamp.
	 * Returns 0 on failure.
	 *
	 * @param string|null $mysql_dt MySQL DATETIME (e.g., '2025-12-19 08:00:00').
	 * @return int UTC epoch seconds
	 */
	function tmon_uc_mysql_to_utc_timestamp($mysql_dt) {
		if (empty($mysql_dt)) return 0;
		$tz_string = get_option('timezone_string', '');
		// Prefer explicit timezone_string (DST-aware)
		if (!empty($tz_string)) {
			try {
				$dt = DateTime::createFromFormat('Y-m-d H:i:s', (string)$mysql_dt, new DateTimeZone($tz_string));
				if ($dt !== false) {
					return (int)$dt->getTimestamp();
				}
			} catch (Exception $e) {
				// fall through to gmt_offset fallback
			}
		}
		// Fallback: interpret as site-local using gmt_offset
		$offset_seconds = (int) round((float) get_option('gmt_offset', 0) * 3600);
		$ts = strtotime($mysql_dt);
		if ($ts === false) return 0;
		// strtotime likely interpreted the string in server timezone (often UTC),
		// so adjust by subtracting the site offset: ts_site_local => ts_utc = ts - offset_seconds
		return (int) ($ts - $offset_seconds);
	}
}

if (!function_exists('tmon_uc_format_mysql_datetime')) {
	/**
	 * Format a MySQL DATETIME (stored using WP site timezone) into a site-local string.
	 *
	 * @param string|null $mysql_dt
	 * @param string $format PHP date format (default uses WP date/time options)
	 * @return string formatted datetime or empty string
	 */
	function tmon_uc_format_mysql_datetime($mysql_dt = null, $format = null) {
		if (empty($mysql_dt)) return '';
		if ($format === null) $format = get_option('date_format') . ' ' . get_option('time_format');
		$ts = tmon_uc_mysql_to_utc_timestamp($mysql_dt);
		if (!$ts) return (string)$mysql_dt;
		return date_i18n($format, (int) $ts);
	}
}

// Ensure hub URL is canonical on admin_init (best-effort, non-destructive)
add_action('admin_init', function(){
	$current = get_option('tmon_uc_hub_url', '');
	$default = tmon_uc_get_default_hub_url();
	// If unset or deprecated host, set to canonical default
	if (empty($current) || stripos($current, 'movealong.us') !== false) {
		update_option('tmon_uc_hub_url', $default);
		error_log("tmon-unit-connector: ensured hub URL is {$default} (was '{$current}').");
	}
	// Lightweight AJAX diagnostics to help find failing admin-ajax requests (opt-in only, skip noisy polling)
	if (defined('DOING_AJAX') && DOING_AJAX && get_option('tmon_uc_debug_ajax')) {
		$act_raw = isset($_REQUEST['action']) ? wp_unslash($_REQUEST['action']) : '';
		$act = is_string($act_raw) ? sanitize_key($act_raw) : '';
		$skip = array(
			'tmon_pending_commands_summary_refresh',
			'tmon_device_status_refresh',
			'tmon_uc_device_bundle',
			'tmon_uc_queue_refresh',
		);
		$skip_prefixes = array(
			'tmon_pending_commands_',
			'tmon_device_status_',
			'tmon_uc_device_',
			'tmon_uc_queue_',
		);
		$is_skipped = in_array($act, $skip, true);
		if (!$is_skipped) {
			foreach ($skip_prefixes as $prefix) {
				if (strpos($act, $prefix) === 0) {
					$is_skipped = true;
					break;
				}
			}
		}

		if ($act && !$is_skipped) {
			// Log only tmon-related requests when ajax debugging is enabled.
			if (strpos($act, 'tmon') === 0 || strpos($act, 'tmon_') === 0) {
				$method = isset($_SERVER['REQUEST_METHOD']) ? sanitize_text_field(wp_unslash($_SERVER['REQUEST_METHOD'])) : 'POST';
				error_log("tmon-unit-connector: AJAX action '{$act}' invoked via {$method}. Refer to admin-ajax.php response for details.");
			}
		}
	}
});


/*
 * ============================================================
 * TMON CANONICAL HUB INTEGRATION
 * ============================================================
 */

if (!function_exists('tmon_uc_get_hub_shared_key')) {

    function tmon_uc_get_hub_shared_key() {

        /*
         * Constant override is useful for deployments where secrets
         * are stored in wp-config.php instead of the database.
         */
        if (
            defined('TMON_HUB_SHARED_SECRET')
            && TMON_HUB_SHARED_SECRET
        ) {
            return (string) TMON_HUB_SHARED_SECRET;
        }

        /*
         * Canonical Unit Connector option.
         */
        $key =
            get_option(
                'tmon_uc_admin_key',
                ''
            );

        if ($key !== '') {
            return (string) $key;
        }

        /*
         * Backward compatibility with existing installs.
         */
        $legacy =
            get_option(
                'tmon_uc_shared_key',
                ''
            );

        if ($legacy !== '') {
            return (string) $legacy;
        }

        $legacy2 =
            get_option(
                'tmon_admin_uc_key',
                ''
            );

        if ($legacy2 !== '') {
            return (string) $legacy2;
        }

        return '';
    }
}


if (!function_exists('tmon_uc_get_hub_headers')) {

    function tmon_uc_get_hub_headers() {

        $key =
            tmon_uc_get_hub_shared_key();

        $headers = array(
            'Accept' =>
                'application/json',
            'Content-Type' =>
                'application/json',
        );

        if ($key !== '') {

            $headers['X-TMON-HUB'] =
                $key;
        }

        return $headers;
    }
}


if (!function_exists('tmon_uc_set_hub_shared_key')) {

    function tmon_uc_set_hub_shared_key($key) {

        $key =
            trim(
                sanitize_text_field(
                    (string) $key
                )
            );

        if ($key === '') {

            return false;
        }

        /*
         * Canonical.
         */
        update_option(
            'tmon_uc_admin_key',
            $key,
            false
        );

        /*
         * Keep legacy option synchronized during migration.
         */
        update_option(
            'tmon_uc_shared_key',
            $key,
            false
        );

        return true;
    }
}


if (!function_exists('tmon_uc_clear_hub_shared_key')) {

    function tmon_uc_clear_hub_shared_key() {

        delete_option(
            'tmon_uc_admin_key'
        );

        delete_option(
            'tmon_uc_shared_key'
        );

        return true;
    }
}


/*
 * Validate a hub request.
 */
if (!function_exists('tmon_uc_validate_hub_request')) {

    function tmon_uc_validate_hub_request(
        WP_REST_Request $request
    ) {

        $expected =
            tmon_uc_get_hub_shared_key();

        if ($expected === '') {

            return new WP_Error(
                'hub_not_configured',
                'Unit Connector hub key is not configured.',
                array(
                    'status' => 503,
                )
            );
        }

        $provided =
            $request->get_header(
                'X-TMON-HUB'
            );

        if ($provided === '') {

            $provided =
                $_SERVER['HTTP_X_TMON_HUB']
                ?? '';
        }

        if ($provided === '') {

            return new WP_Error(
                'missing_hub_key',
                'Missing X-TMON-HUB header.',
                array(
                    'status' => 401,
                )
            );
        }

        if (
            !hash_equals(
                (string) $expected,
                (string) $provided
            )
        ) {

            return new WP_Error(
                'invalid_hub_key',
                'Invalid hub key.',
                array(
                    'status' => 403,
                )
            );
        }

        return true;
    }
}

if (!function_exists('tmon_uc_build_hub_device_snapshot')) {

    function tmon_uc_build_hub_device_snapshot(
        $unit_id
    ) {

        global $wpdb;

        $unit_id =
            sanitize_text_field(
                (string) $unit_id
            );

        if ($unit_id === '') {
            return array();
        }

        $device =
            $wpdb->get_row(
                $wpdb->prepare(
                    "SELECT *
                     FROM {$wpdb->prefix}tmon_devices
                     WHERE unit_id = %s
                     LIMIT 1",
                    $unit_id
                ),
                ARRAY_A
            );

        $diagnostics =
            get_option(
                'tmon_uc_device_diagnostics',
                array()
            );

        if (!is_array($diagnostics)) {
            $diagnostics = array();
        }

        $diag =
            isset($diagnostics[$unit_id])
            && is_array($diagnostics[$unit_id])
                ? $diagnostics[$unit_id]
                : array();

        $lora =
            get_option(
                'tmon_uc_lora_status',
                array()
            );

        if (!is_array($lora)) {
            $lora = array();
        }

        $lora_status =
            isset($lora[$unit_id])
            && is_array($lora[$unit_id])
                ? (
                    is_array(
                        $lora[$unit_id]['status']
                        ?? null
                    )
                        ? $lora[$unit_id]['status']
                        : array()
                )
                : array();

        $latest =
            $wpdb->get_row(
                $wpdb->prepare(
                    "SELECT *
                     FROM {$wpdb->prefix}tmon_device_data
                     WHERE unit_id = %s
                     ORDER BY id DESC
                     LIMIT 1",
                    $unit_id
                ),
                ARRAY_A
            );

        $latest_data = array();

        if (
            is_array($latest)
            && !empty($latest['data'])
        ) {

            $decoded =
                json_decode(
                    $latest['data'],
                    true
                );

            if (is_array($decoded)) {
                $latest_data =
                    $decoded;
            }
        }

        return array(
            'unit_id' =>
                $unit_id,

            'machine_id' =>
                (string) (
                    $device['machine_id']
                    ?? ''
                ),

            'unit_name' =>
                (string) (
                    $device['unit_name']
                    ?? ''
                ),

            'role' =>
                (string) (
                    $device['role']
                    ?? (
                        $device['node_type']
                        ?? ''
                    )
                ),

            'company' =>
                (string) (
                    $device['company']
                    ?? ''
                ),

            'site' =>
                (string) (
                    $device['site']
                    ?? ''
                ),

            'zone' =>
                (string) (
                    $device['zone']
                    ?? ''
                ),

            'cluster' =>
                (string) (
                    $device['cluster']
                    ?? ''
                ),

            'suspended' =>
                !empty(
                    $device['suspended']
                ),

            'last_seen' =>
                (string) (
                    $device['last_seen']
                    ?? ''
                ),

            'settings' =>
                !empty($device['settings'])
                    ? json_decode(
                        $device['settings'],
                        true
                    )
                    : array(),

            'diagnostics' =>
                $diag,

            'lora' =>
                $lora_status,

            'latest_data' =>
                $latest_data,

            'reported_at' =>
                current_time(
                    'mysql'
                ),
        );
    }
}