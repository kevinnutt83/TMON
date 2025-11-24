# Minimal MicroPython provisioning client for the mircopython package.
# Uses existing settings variables from mircopython/settings.py where available.

import json
try:
    import urequests as requests
except Exception:
    import requests  # fallback for non-MicroPython environments for testing
try:
    import settings as settings  # canonical project settings
except Exception:
    settings = None

try:
    from firmware_updater import download_and_apply_firmware
except Exception:
    # Provide a no-op fallback so code does not break during tests
    def download_and_apply_firmware(url, version_hint=None, chunk_size=1024):
        print("No firmware_updater available. Skipping download:", url)
        return True

# Resolve base URL and API paths from settings; fall back to sensible defaults if missing
DEFAULT_BASE = getattr(settings, 'TMON_ADMIN_API_URL', "https://example.com") if settings else "https://example.com"
API_PATHS = getattr(settings, 'PROVISION_PATHS', ['/wp-json/tmon/v1/device/provision', '/wp-json/tmon/v1/provision']) if settings else ['/wp-json/tmon/v1/device/provision', '/wp-json/tmon/v1/provision']
REQUEST_TIMEOUT = getattr(settings, 'HTTP_TIMEOUT_S', 10) if settings else 10
CHUNK_SIZE = getattr(settings, 'FIRMWARE_DOWNLOAD_CHUNK_SIZE', 1024) if settings else 1024

def _attempt_endpoint(base_url, endpoint, params=None, json_body=None, timeout=REQUEST_TIMEOUT):
    url = base_url.rstrip("/") + endpoint
    try:
        if json_body is not None:
            resp = requests.post(url, json=json_body, timeout=timeout)
        else:
            if params:
                qs = "&".join("{}={}".format(k, v) for k, v in params.items())
                url = url + "?" + qs
            resp = requests.get(url, timeout=timeout)
        if not resp:
            return None, 'no_response'
        code = getattr(resp, 'status_code', None)
        if code not in (200, 201):
            return None, 'http_error_%s' % code
        # For urequests on MicroPython: resp.json() may raise; handle carefully
        try:
            return resp.json(), None
        except Exception:
            # Fallback: parse text
            try:
                return json.loads(getattr(resp, 'text', '{}')), None
            except Exception as e:
                return None, str(e)
    except Exception as e:
        return None, str(e)

def fetch_provisioning(unit_id=None, machine_id=None, base_url=None, force=False):
    """
    Fetch provisioning settings from Admin (supports GET and POST on two paths).
    Accepts either unit_id or machine_id (or uses values from settings if not provided).
    """
    base = base_url or DEFAULT_BASE

    # Permissive: read from settings if not provided explicitly
    if not unit_id and settings and getattr(settings, 'UNIT_ID', None):
        unit_id = getattr(settings, 'UNIT_ID', None)
    if not machine_id and settings and getattr(settings, 'MACHINE_ID', None):
        machine_id = getattr(settings, 'MACHINE_ID', None)

    if not (unit_id or machine_id):
        return None

    params = {}
    if unit_id:
        params['unit_id'] = unit_id
    if machine_id:
        params['machine_id'] = machine_id
    if force:
        params['force'] = '1'

    # Try GET on each path then POST on each path (backwards compatible)
    for path in API_PATHS:
        body, err = _attempt_endpoint(base, path, params=params)
        if err is None and body and 'provisioned' in body:
            if body.get('provisioned') is not True:
                return None
            settings_doc = body.get('settings') or {}
            return settings_doc

    # Fallback to POST attempts
    json_body = params
    for path in API_PATHS:
        body, err = _attempt_endpoint(base, path, json_body=json_body)
        if err is None and body and 'provisioned' in body:
            if body.get('provisioned') is not True:
                return None
            settings_doc = body.get('settings') or {}
            return settings_doc
    return None

def apply_settings(settings_doc):
    """
    Apply device settings returned by Admin:
    - handles UNIT_Name, NODE_TYPE
    - triggers firmware download when FIRMWARE_URL present
    """
    if not isinstance(settings_doc, dict):
        return False

    # NODE_TYPE
    node_type = settings_doc.get('NODE_TYPE')
    if node_type:
        # Hardware-specific: implement setting role here
        print("Set NODE_TYPE:", node_type)

    # UNIT name
    unit_name = settings_doc.get('UNIT_Name')
    if unit_name:
        print("Set UNIT_Name:", unit_name)

    # Sites and notes are informational
    # Firmware update (if provided)
    fw_url = settings_doc.get('FIRMWARE_URL') or settings_doc.get('firmware_url')
    fw_ver = settings_doc.get('FIRMWARE') or settings_doc.get('firmware')
    if fw_url:
        print("Firmware requested:", fw_ver, fw_url)
        try:
            download_and_apply_firmware(fw_url, fw_ver, chunk_size=CHUNK_SIZE)
        except Exception as e:
            print("Firmware update error:", e)

    # WIFI disable toggle if present (implementation device-specific)
    disable_wifi = settings_doc.get('WIFI_DISABLE_AFTER_PROVISION', False)
    if disable_wifi:
        print("Configured to disable WiFi after provisioning; implement as needed.")

    return True

if __name__ == "__main__":
    import sys
    unit = sys.argv[1] if len(sys.argv) > 1 else None
    mac = sys.argv[2] if len(sys.argv) > 2 else None
    s = fetch_provisioning(unit_id=unit, machine_id=mac, base_url=None)
    if s:
        apply_settings(s)
    else:
        print("No staged provisioning settings found.")
