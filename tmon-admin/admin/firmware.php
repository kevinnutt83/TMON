<?php
// Compatibility shim: delegate firmware rendering to the shared action-based handler.
if (!function_exists('tmon_admin_firmware_page')) {
	function tmon_admin_firmware_page() {
		do_action('tmon_admin_firmware_page');
	}
}
