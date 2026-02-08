# Minimal MicroPython provisioning client that uses the canonical micropython/settings.py values.

import json
import os
from platform_compat import requests as _pc_requests  # CHANGED

# CHANGED: CPython/Zero fallback when platform_compat.requests is None
requests = _pc_requests
if requests is None:
    try:
        import requests as _py_requests  # type: ignore
        requests = _py_requests  # type: ignore
    except Exception:
        requests = None  # type: ignore

# Import device settings robustly: prefer local settings module; fallback to micropython.settings
device_settings = None
try:
    import settings as local_settings  # when module is executed in its dir
    device_settings = local_settings
except Exception:
    try:
        from micropython import settings as local_settings  # package-style import
        device_settings = local_settings
    except Exception:
        device_settings = None

# Resolve configuration from settings or sensible defaults
DEFAULT_BASE = getattr(device_settings, 'TMON_ADMIN_API_URL', "https://tmonsystems.com") if device_settings else "https://tmonsystems.com"

# CHANGED: default paths should include Admin provisioning endpoint(s) first
_DEFAULT_PROVISION_PATHS = [
    '/wp-json/tmon-admin/v1/device/provision',
    '/wp-json/tmon-admin/v1/device/provision/',  # tolerate trailing slash
    # legacy/alternate routes (keep as fallbacks)
    '/wp-json/tmon/v1/device/provision',
    '/wp-json/tmon/v1/provision',
]
API_PATHS = getattr(device_settings, 'PROVISION_PATHS', _DEFAULT_PROVISION_PATHS) if device_settings else _DEFAULT_PROVISION_PATHS

REQUEST_TIMEOUT = getattr(device_settings, 'HTTP_TIMEOUT_S', 20) if device_settings else 20
CHUNK_SIZE = getattr(device_settings, 'FIRMWARE_DOWNLOAD_CHUNK_SIZE', 1024) if device_settings else 1024

def _attempt_endpoint(base_url, endpoint, params=None, json_body=None, timeout=REQUEST_TIMEOUT):
    url = base_url.rstrip("/") + endpoint
    try:
        if requests is None:
            return None, "no_http_client"

        if json_body is not None:
            # CHANGED: urequests often lacks json=/timeout=
            try:
                resp = requests.post(url, json=json_body, timeout=timeout)
            except TypeError:
                try:
                    body = json.dumps(json_body or {})
                except Exception:
                    body = "{}"
                try:
                    resp = requests.post(url, data=body)
                except TypeError:
                    resp = requests.post(url, data=body)
        else:
            if params:
                qs = "&".join("{}={}".format(k, v) for k, v in params.items())
                url = url + "?" + qs
            try:
                resp = requests.get(url, timeout=timeout)
            except TypeError:
                resp = requests.get(url)

        if not resp:
            return None, "no_response"

        code = getattr(resp, "status_code", None)

        # CHANGED: read/parse body BEFORE closing resp (works for both requests and urequests variants).
        parsed = None
        text = ""
        try:
            # Prefer response-provided json() when available
            if hasattr(resp, "json") and callable(getattr(resp, "json")):
                try:
                    parsed = resp.json()
                except Exception:
                    parsed = None
        except Exception:
            parsed = None

        if parsed is None:
            # Try .text then .content (requests) then .content-like (urequests)
            try:
                text = getattr(resp, "text", "") or ""
            except Exception:
                text = ""
            if not text:
                raw = b""
                try:
                    raw = getattr(resp, "content", b"") or b""
                except Exception:
                    raw = b""
                if raw:
                    try:
                        text = raw.decode("utf-8", "ignore")
                    except Exception:
                        text = ""
            if text:
                try:
                    parsed = json.loads(text)
                except Exception:
                    parsed = None

        try:
            resp.close()
        except Exception:
            pass

        if code not in (200, 201):
            return None, "http_error_%s" % code

        if isinstance(parsed, (dict, list)):
            return parsed, None
        return None, "json_parse_failed"

    except Exception as e:
        return None, str(e)
    finally:
        try:
            import gc
            gc.collect()
        except Exception:
            pass

def fetch_provisioning(unit_id=None, machine_id=None, base_url=None, force=False):
    """
    Fetch provisioning settings from Admin. Uses device settings if unit/machine not specified.
    Returns the settings dict or None.
    """
    base = base_url or DEFAULT_BASE

    # fallback to persisted values in settings if not passed
    if not unit_id and device_settings and getattr(device_settings, 'UNIT_ID', None):
        unit_id = getattr(device_settings, 'UNIT_ID', None)
    if not machine_id and device_settings and getattr(device_settings, 'MACHINE_ID', None):
        machine_id = getattr(device_settings, 'MACHINE_ID', None)

    if not (unit_id or machine_id):
        return None

    params = {}
    if unit_id:
        params['unit_id'] = unit_id
    if machine_id:
        params['machine_id'] = machine_id
    if force:
        params['force'] = '1'

    # Try GET on each path first, then fallback to POST
    for path in API_PATHS:
        body, err = _attempt_endpoint(base, path, params=params)
        if err is None and body and 'provisioned' in body:
            site_val = body.get('site_url') or body.get('wordpress_api_url') or ''
            if (body.get('provisioned') or body.get('staged_exists')) and site_val:
                return {
                    'wordpress_api_url': site_val,
                    'site_url': site_val,
                    'NODE_TYPE': body.get('role') or '',
                    'UNIT_Name': body.get('unit_name') or '',
                    'FIRMWARE': body.get('firmware') or '',
                    'FIRMWARE_URL': body.get('firmware_url') or '',
                    'plan': body.get('plan') or '',
                    'WIFI_DISABLE_AFTER_PROVISION': ((body.get('role') or '') == 'remote')
                }
            if not body.get('provisioned'):
                return None
            return body.get('settings') or {}
    json_body = params
    for path in API_PATHS:
        body, err = _attempt_endpoint(base, path, json_body=json_body)
        if err is None and body and 'provisioned' in body:
            site_val = body.get('site_url') or body.get('wordpress_api_url') or ''
            if (body.get('provisioned') or body.get('staged_exists')) and site_val:
                return {
                    'wordpress_api_url': site_val,
                    'site_url': site_val,
                    'NODE_TYPE': body.get('role') or '',
                    'UNIT_Name': body.get('unit_name') or '',
                    'FIRMWARE': body.get('firmware') or '',
                    'FIRMWARE_URL': body.get('firmware_url') or '',
                    'plan': body.get('plan') or '',
                    'WIFI_DISABLE_AFTER_PROVISION': ((body.get('role') or '') == 'remote')
                }
            if not body.get('provisioned'):
                return None
            return body.get('settings') or {}
    return None

# firmware_updater expected in micropython directory; fallback to no-op
try:
    from firmware_updater import download_and_apply_firmware
except Exception:
    def download_and_apply_firmware(url, version_hint=None, chunk_size=CHUNK_SIZE):
        print("No firmware_updater; skipping firmware:", url)
        return True

def apply_settings(settings_doc):
    """
    Apply settings returned by Admin:
    - NODE_TYPE, UNIT_Name
    - FIRMWARE_URL -> call firmware_updater to download to OTA_BACKUP_DIR
    - WIFI_DISABLE_AFTER_PROVISION: device-specific action
    """
    if not isinstance(settings_doc, dict):
        return False

    node_type = settings_doc.get('NODE_TYPE')
    if node_type:
        print("Setting NODE_TYPE:", node_type)

    unit_name = settings_doc.get('UNIT_Name')
    if unit_name:
        print("Setting UNIT_Name:", unit_name)

    fw_url = settings_doc.get('FIRMWARE_URL') or settings_doc.get('firmware_url')
    fw_ver = settings_doc.get('FIRMWARE') or settings_doc.get('firmware')
    if fw_url:
        print("Firmware requested:", fw_ver, fw_url)
        try:
            download_and_apply_firmware(fw_url, fw_ver, chunk_size=CHUNK_SIZE)
        except Exception as e:
            print("Firmware download/apply failed:", e)

    if settings_doc.get('WIFI_DISABLE_AFTER_PROVISION', False):
        print("Configured to disable WiFi after provisioning (device-specific).")

    # NEW: fallback mapping from alternative keys
    if not node_type and settings_doc.get('role'):
        node_type = settings_doc.get('role')
        print("Setting NODE_TYPE (role fallback):", node_type)
    if not unit_name and settings_doc.get('unit_name'):
        unit_name = settings_doc.get('unit_name')
        print("Setting UNIT_Name (unit_name fallback):", unit_name)
    # Persist mapped fields to settings module
    try:
        import settings as _s
        # Persist UNIT_ID if present (best-effort)
        if settings_doc.get('unit_id'):
            try:
                from utils import persist_unit_id
                _s.UNIT_ID = str(settings_doc.get('unit_id'))
                persist_unit_id(_s.UNIT_ID)
            except Exception:
                pass
        if settings_doc.get('plan'): _s.PLAN = settings_doc.get('plan')
        if settings_doc.get('site_url') or settings_doc.get('wordpress_api_url'):
            _s.WORDPRESS_API_URL = settings_doc.get('site_url') or settings_doc.get('wordpress_api_url')
            try:
                path = getattr(_s, 'WORDPRESS_API_URL_FILE', _s.LOG_DIR + '/wordpress_api_url.txt')
                with open(path, 'w') as f:
                    f.write(_s.WORDPRESS_API_URL)
            except Exception:
                pass
        # Persist unit name via utils to maintain consistent behavior
        if unit_name:
            try:
                from utils import persist_unit_name
                persist_unit_name(unit_name)
                _s.UNIT_Name = unit_name
            except Exception:
                pass
        # If role -> persist node type and if remote, optionally disable WiFi
        if node_type:
            try:
                _s.NODE_TYPE = node_type
                from utils import persist_node_type
                persist_node_type(node_type)
                if str(node_type).lower() == 'remote' and settings_doc.get('WIFI_DISABLE_AFTER_PROVISION', False):
                    try:
                        _s.ENABLE_WIFI = False
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass

    # NEW: GC after applying/persisting provisioning settings
    try:
        import gc
        gc.collect()
    except Exception:
        pass

    # Additional device-specific settings application here
    return True

# Exported helpers
__all__ = ['fetch_provisioning', 'apply_settings']
