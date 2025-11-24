# Minimal MicroPython provisioning client (GET/POST-compatible)
# Requires urequests; adapt network/connect code to your hardware

import urequests as requests
import json
import time
from firmware_updater import download_and_apply_firmware

# If TLS is required, ensure the firmware supports certs or use ip-based connections
DEFAULT_BASE = "https://example.com"  # replace with admin base URL as configured
API_PATHS = [
    "/wp-json/tmon/v1/device/provision",
    "/wp-json/tmon/v1/provision",  # backwards compatibility alias
]

def _attempt_endpoint(base_url, endpoint, params=None, json_body=None, timeout=10):
    url = base_url.rstrip("/") + endpoint
    try:
        if json_body is not None:
            resp = requests.post(url, json=json_body, timeout=timeout)
        else:
            # Use GET with query string if params provided
            if params:
                qs = "&".join("{}={}".format(k, v) for k, v in params.items())
                url = url + "?" + qs
            resp = requests.get(url, timeout=timeout)
        if not resp:
            return None, 'no_response'
        code = resp.status_code
        if code not in (200, 201):
            text = resp.text if hasattr(resp, 'text') else ''
            return None, 'http_error_%s' % code
        return resp.json(), None
    except Exception as e:
        return None, str(e)

def fetch_provisioning(unit_id=None, machine_id=None, base_url=DEFAULT_BASE, force=False):
    """
    Try to fetch provisioning settings. Returns dict or None.
    Preferences: try strict params; use GET if possible.
    """
    if not (unit_id or machine_id):
        return None

    params = {}
    if unit_id:
        params['unit_id'] = unit_id
    if machine_id:
        params['machine_id'] = machine_id

    if force:
        params['force'] = '1'

    for path in API_PATHS:
        body, err = _attempt_endpoint(base_url, path, params=params)
        if err is None and body and 'provisioned' in body:
            if body.get('provisioned') is not True:
                return None
            # 'settings' may be null if no staged settings
            settings = body.get('settings')
            if not settings:
                return None
            return settings
    # Fallback to POST attempt (some devices prefer or servers accept POST only)
    json_body = params
    for path in API_PATHS:
        body, err = _attempt_endpoint(base_url, path, json_body=json_body)
        if err is None and body and 'provisioned' in body:
            if body.get('provisioned') is not True:
                return None
            settings = body.get('settings')
            if not settings:
                return None
            return settings
    return None

def apply_settings(settings):
    """
    Apply device settings. This is domain-specific:
    - NODE_TYPE -> set device mode
    - WIFI_DISABLE_AFTER_PROVISION -> disabling WiFi after provisioning
    - FIRMWARE / FIRMWARE_URL -> trigger firmware update
    - UNIT_Name -> display name / identification
    This function should be adapted to the device hardware and software stack.
    """
    if not isinstance(settings, dict):
        return False

    # Example: apply Node Type (placeholder)
    node_type = settings.get('NODE_TYPE')
    if node_type:
        # e.g., set device role, update internal config
        print("Setting NODE_TYPE:", node_type)

    unit_name = settings.get('UNIT_Name')
    if unit_name:
        print("Setting UNIT_Name:", unit_name)

    # Firmware update: if FIRMWARE_URL provided, download + apply
    fw_url = settings.get('FIRMWARE_URL') or settings.get('firmware_url')
    fw_ver = settings.get('FIRMWARE') or settings.get('firmware')
    if fw_url:
        print("Firmware: version=%s url=%s" % (fw_ver, fw_url))
        try:
            download_and_apply_firmware(fw_url, fw_ver)
        except Exception as e:
            print("Firmware update failed:", e)

    # Example additional settings
    disable_wifi = settings.get('WIFI_DISABLE_AFTER_PROVISION', False)
    if disable_wifi:
        print("Configured to disable WiFi after provisioning (implement accordingly).")

    # Persist or apply other settings per device requirements
    return True

if __name__ == "__main__":
    # Example invocation - replace with real unit_id + machine_id from your device
    import sys
    unit = sys.argv[1] if len(sys.argv) > 1 else None
    mac = sys.argv[2] if len(sys.argv) > 2 else None
    s = fetch_provisioning(unit_id=unit, machine_id=mac, base_url=DEFAULT_BASE)
    if s:
        apply_settings(s)
    else:
        print("No staged provisioning settings found.")
