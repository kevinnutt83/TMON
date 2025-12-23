<?php
// Minimal Unit Connector v1 REST API routes used by devices.
// - Exposes endpoints under both tmon/v1 and unit-connector/v1 for broad compatibility.
// - Permission callback accepts a configured confirm token, certain headers, Basic/Bearer Authorization (Application Passwords), or manage_options users.

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Return configured token(s) for server-side checks. Admins can set option 'tmon_rest_admin_token' in WP options
 * (or filter it) - default empty.
 */
function tmon_uc_get_admin_token() {
	// Try multiple option names for compatibility with different installs / naming
	$candidates = array(
		'tmon_rest_admin_token',
		'tmon_admin_confirm_token',
		'tmon_uc_admin_token',
		'tmon_admin_token',
		'tmon_unit_token'
	);
	foreach ( $candidates as $opt ) {
		$val = get_option( $opt, '' );
		if ( $val && is_string( $val ) ) {
			$val = trim( $val );
			if ( $val !== '' ) return $val;
		}
	}
	// allow filter override
	$filtered = apply_filters( 'tmon_uc_admin_token', '' );
	if ( is_string( $filtered ) && trim( $filtered ) !== '' ) {
		return trim( $filtered );
	}
	return '';
}

/**
 * Permission callback: accept:
 *  - X-TMON-ADMIN / X-TMON-CONFIRM / X-TMON-HUB / X-TMON-READ / X-TMON-API-Key header matching option token,
 *  - Authorization header (Basic/Bearer) to allow Application Passwords,
 *  - logged-in users with 'manage_options'.
 */
function tmon_uc_rest_permission_check( $request ) {
	$token = tmon_uc_get_admin_token();
	$headers = $request->get_headers();

	// header variants (lowercase keys as returned by WP)
	$try_names = array( 'x-tmon-admin', 'x-tmon-confirm', 'x-tmon-hub', 'x-tmon-read', 'x-tmon-api-key', 'x-tmon-verify', 'x-http-authorization' );

	// If a configured token exists, require a matching header
	if ( $token ) {
		foreach ( $try_names as $hn ) {
			if ( isset( $headers[ $hn ] ) && ! empty( $headers[ $hn ][0] ) ) {
				if ( trim( $headers[ $hn ][0] ) === $token ) {
					return true;
				}
			}
		}
	} else {
		// No configured token: accept any non-empty confirm-like header as a pragmatic fallback.
		// This helps when Authorization headers are stripped by proxies but the confirm header is present.
		foreach ( $try_names as $hn ) {
			if ( isset( $headers[ $hn ] ) && ! empty( $headers[ $hn ][0] ) ) {
				// best-effort: allow but log for operators
				if ( function_exists( 'error_log' ) ) {
					error_log( 'tmon_uc: accepting confirm header fallback for ' . $hn );
				}
				return true;
			}
		}
	}

	// Basic/Bearer auth - allow (so Application Passwords / Bearer tokens can be used)
	if ( isset( $headers['authorization'] ) && ! empty( $headers['authorization'][0] ) ) {
		$auth = strtolower( $headers['authorization'][0] );
		if ( substr( $auth, 0, 6 ) === 'basic ' || substr( $auth, 0, 7 ) === 'bearer ' ) {
			return true;
		}
	}

	// logged-in administrators allowed for testing/console access
	if ( is_user_logged_in() && current_user_can( 'manage_options' ) ) {
		return true;
	}

	return new WP_Error( 'rest_forbidden', 'Forbidden', array( 'status' => 403 ) );
}

/**
 * Helper: read JSON body safely
 */
function tmon_uc_get_body_json( $request ) {
	$params = $request->get_json_params();
	if ( is_array( $params ) ) {
		return $params;
	}
	$body = $request->get_body();
	$decoded = json_decode( $body, true );
	return is_array( $decoded ) ? $decoded : array();
}

/* ---------- Handlers ---------- */

function tmon_uc_handle_checkin( $request ) {
	$body = tmon_uc_get_body_json( $request );
	$machine_id = isset( $body['machine_id'] ) ? sanitize_text_field( $body['machine_id'] ) : '';
	$unit_id    = isset( $body['unit_id'] ) ? sanitize_text_field( $body['unit_id'] ) : '';
	// Minimal response: report site_url and provisioned/staged flags if any server-side logic exists
	$res = array(
		'provisioned'  => true,
		'staged_exists'=> false,
		'site_url'     => get_home_url(),
		'unit_id'      => $unit_id ?: '',
	);
	return rest_ensure_response( $res );
}

function tmon_uc_handle_field_data( $request ) {
	$body = tmon_uc_get_body_json( $request );
	$unit = isset( $body['unit_id'] ) ? sanitize_text_field( $body['unit_id'] ) : '';
	// Keep last payload for operators: store in option (small, safe)
	if ( ! empty( $unit ) ) {
		update_option( 'tmon_last_fielddata_' . $unit, $body );
	} else {
		update_option( 'tmon_last_fielddata_raw', $body );
	}
	return rest_ensure_response( array( 'status' => 'ok', 'received' => true, 'unit_id' => $unit ) );
}

function tmon_uc_handle_commands_get( $request ) {
	global $wpdb;
	$unit = sanitize_text_field( $request->get_param( 'unit_id' ) ?: '' );
	$commands = array();

	$table = $wpdb->prefix . 'tmon_device_commands';
	// If table exists, try to return queued commands for unit
	$exists = $wpdb->get_var( $wpdb->prepare( "SHOW TABLES LIKE %s", $wpdb->esc_like( $table ) ) );
	if ( $exists ) {
		$sql = $wpdb->prepare( "SELECT id, command, params FROM {$table} WHERE device_id = %s AND status = %s ORDER BY id ASC LIMIT 50", $unit, 'queued' );
		$rows = $wpdb->get_results( $sql, ARRAY_A );
		foreach ( $rows as $r ) {
			$p = array();
			if ( ! empty( $r['params'] ) ) {
				$p = json_decode( $r['params'], true ) ?: array();
			}
			$commands[] = array( 'id' => intval( $r['id'] ), 'command' => $r['command'], 'params' => $p );
		}
	}
	return rest_ensure_response( array( 'commands' => $commands ) );
}

function tmon_uc_handle_commands_post( $request ) {
	$body = tmon_uc_get_body_json( $request );
	$unit = isset( $body['unit_id'] ) ? sanitize_text_field( $body['unit_id'] ) : '';
	// Mirror GET behavior; some devices POST unit_id expecting command list
	$query = new WP_REST_Request( 'GET', '/tmon/v1/device/commands' );
	$query->set_param( 'unit_id', $unit );
	return tmon_uc_handle_commands_get( $query );
}

function tmon_uc_handle_command_confirm( $request ) {
	global $wpdb;
	$body = tmon_uc_get_body_json( $request );
	$job_id = isset( $body['job_id'] ) ? intval( $body['job_id'] ) : 0;
	$ok = isset( $body['ok'] ) ? boolval( $body['ok'] ) : false;
	$result = isset( $body['result'] ) ? sanitize_text_field( $body['result'] ) : '';

	$table = $wpdb->prefix . 'tmon_device_commands';
	$exists = $wpdb->get_var( $wpdb->prepare( "SHOW TABLES LIKE %s", $wpdb->esc_like( $table ) ) );
	if ( $exists && $job_id ) {
		$wpdb->update( $table, array( 'status' => 'executed', 'executed_at' => current_time( 'mysql' ), 'params' => wp_json_encode( array( '__ok' => $ok, '__result' => $result ) ) ), array( 'id' => $job_id ) );
		return rest_ensure_response( array( 'status' => 'ok', 'updated' => $job_id ) );
	}
	// fallback: nothing to update
	return rest_ensure_response( array( 'status' => 'queued_for_retry', 'job_id' => $job_id ) );
}

function tmon_uc_handle_settings_applied( $request ) {
	$body = tmon_uc_get_body_json( $request );
	$unit = isset( $body['unit_id'] ) ? sanitize_text_field( $body['unit_id'] ) : '';
	// Store snapshot for auditing
	$meta_key = 'tmon_settings_applied_' . ( $unit ? $unit : 'unknown' );
	update_option( $meta_key, array( 'payload' => $body, 'ts' => time() ) );
	return rest_ensure_response( array( 'status' => 'ok', 'unit_id' => $unit ) );
}

function tmon_uc_handle_settings_get( $request ) {
	$unit = sanitize_text_field( $request->get_param( 'unit_id' ) ?: '' );
	$res = array( 'unit_id' => $unit, 'settings' => array() );
	// If an applied snapshot exists, return it
	if ( $unit ) {
		$meta = get_option( 'tmon_settings_applied_' . $unit, null );
		if ( $meta && isset( $meta['payload']['settings'] ) ) {
			$res['settings'] = $meta['payload']['settings'];
		}
	}
	return rest_ensure_response( $res );
}

function tmon_uc_handle_file_post( $request ) {
	// Accept raw body or uploaded 'file' param. Store via wp_handle_upload if available.
	$files = $request->get_file_params();
	$body = $request->get_body();
	$uploaded = false;
	$url = '';
	if ( ! empty( $files['file'] ) && function_exists( 'wp_handle_upload' ) ) {
		$f = $files['file'];
		$overrides = array( 'test_form' => false );
		$move = wp_handle_upload( $f, $overrides );
		if ( isset( $move['url'] ) ) {
			$uploaded = true;
			$url = $move['url'];
		}
	} elseif ( $body ) {
		// Save raw body into uploads folder
		$upload_dir = wp_upload_dir();
		if ( isset( $upload_dir['path'] ) ) {
			$fn = $upload_dir['path'] . '/device_upload_' . time();
			file_put_contents( $fn, $body );
			$uploaded = true;
			$url = ( $upload_dir['url'] ?? '' ) . '/device_upload_' . time();
		}
	}
	return rest_ensure_response( array( 'ok' => $uploaded, 'url' => $url ) );
}

/* ---------- Register routes (tmon/v1 and unit-connector/v1 and admin compatibility) ---------- */
add_action( 'rest_api_init', function () {
	$namespaces = array( 'tmon/v1', 'unit-connector/v1' );
	foreach ( $namespaces as $ns ) {
		register_rest_route( $ns, '/device/field-data', array(
			'methods'             => 'POST',
			'callback'            => 'tmon_uc_handle_field_data',
			'permission_callback' => '__return_true', // device posts may be unauthenticated (we store/inspect)
		) );

		register_rest_route( $ns, '/device/commands', array(
			array( 'methods' => 'GET',  'callback' => 'tmon_uc_handle_commands_get',  'permission_callback' => '__return_true' ),
			array( 'methods' => 'POST', 'callback' => 'tmon_uc_handle_commands_post', 'permission_callback' => '__return_true' ),
		) );

		// Admin-scoped commands (devices try admin path first)
		register_rest_route( $ns, '/admin/device/commands', array(
			array( 'methods' => 'GET',  'callback' => 'tmon_uc_handle_commands_get',  'permission_callback' => '__return_true' ),
			array( 'methods' => 'POST', 'callback' => 'tmon_uc_handle_commands_post', 'permission_callback' => '__return_true' ),
		) );

		register_rest_route( $ns, '/device/command/confirm', array(
			'methods'             => 'POST',
			'callback'            => 'tmon_uc_handle_command_confirm',
			'permission_callback' => 'tmon_uc_rest_permission_check',
		) );

		register_rest_route( $ns, '/device/file', array(
			array( 'methods' => 'POST', 'callback' => 'tmon_uc_handle_file_post', 'permission_callback' => 'tmon_uc_rest_permission_check' ),
			array( 'methods' => 'GET',  'callback' => function( $r ){ return rest_ensure_response( array('ok'=>false,'message'=>'file download not implemented') ); }, 'permission_callback' => '__return_true' ),
		) );

		register_rest_route( $ns, '/admin/device/settings-applied', array(
			'methods'             => 'POST',
			'callback'            => 'tmon_uc_handle_settings_applied',
			'permission_callback' => 'tmon_uc_rest_permission_check',
		) );

		register_rest_route( $ns, '/device/settings/(?P<unit_id>[\w\-\_]+)', array(
			'methods'             => 'GET',
			'callback'            => 'tmon_uc_handle_settings_get',
			'permission_callback' => '__return_true',
			'args'                => array( 'unit_id' => array( 'required' => true ) ),
		) );

		// Admin check-in (compat: tmon-admin/v1 and v2 checkin style)
		register_rest_route( $ns, '/admin/device/check-in', array(
			'methods'             => 'POST',
			'callback'            => 'tmon_uc_handle_checkin',
			'permission_callback' => '__return_true',
		) );
	}

	// Legacy /wp-json/tmon-admin/v1/device/check-in (public)
	register_rest_route( 'tmon-admin/v1', '/device/check-in', array(
		'methods'             => 'POST',
		'callback'            => 'tmon_uc_handle_checkin',
		'permission_callback' => '__return_true',
	) );

	// Backwards compat: v2 checkin path
	register_rest_route( 'tmon-admin/v2', '/device/checkin', array(
		'methods'             => 'POST',
		'callback'            => 'tmon_uc_handle_checkin',
		'permission_callback' => '__return_true',
	) );

} );
