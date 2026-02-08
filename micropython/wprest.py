# Firmware Version: v2.06.0
# wprest.py
# Handles WordPress REST API communication for TMON MicroPython device

import gc
from platform_compat import requests as _pc_requests, time as _pc_time, asyncio as _pc_asyncio  # CHANGED
import sys  # NEW

try:
    import ujson as json
except Exception:
    import json

import settings
import os

# CHANGED: determine runtime early so we can safely import CPython-only libs conditionally
def _is_micropython() -> bool:
    try:
        return str(getattr(sys.implementation, "name", "")).lower() == "micropython"
    except Exception:
        return False

_IS_MICROPYTHON = _is_micropython()

# CHANGED: CPython-only urllib imports must not run on MicroPython
if not _IS_MICROPYTHON:
    import urllib.request  # type: ignore
    import urllib.error  # type: ignore
    import urllib.parse  # type: ignore
else:
    urllib = None  # type: ignore

# CHANGED: Guard utils import so Zero can still check-in/provision even if other code paths
# (e.g., neopixel usage inside utils.flash_led) are problematic at runtime.
try:
    from utils import (
        debug_print,
        get_machine_id,
        persist_unit_id,
        persist_unit_name,
        append_to_backlog,
        read_backlog,
        clear_backlog,
    )
except Exception:
    async def debug_print(msg, tag="DEBUG"):
        try:
            print(f"[{tag}] {msg}")
        except Exception:
            pass

    def get_machine_id():
        try:
            return getattr(settings, "MACHINE_ID", "") or ""
        except Exception:
            return ""

    def persist_unit_id(_uid):
        return None

    def persist_unit_name(_name):
        return None

    def append_to_backlog(_entry):
        return False

    def read_backlog():
        return []

    def clear_backlog():
        return True

WORDPRESS_API_URL = getattr(settings, 'WORDPRESS_API_URL', '')
WORDPRESS_USERNAME = getattr(settings, 'WORDPRESS_USERNAME', None)
WORDPRESS_PASSWORD = getattr(settings, 'WORDPRESS_PASSWORD', None)

# CHANGED: CPython/Zero fallback for HTTP + time when platform_compat provides None
requests = _pc_requests
time = _pc_time
if requests is None:
    try:
        import requests as _py_requests  # type: ignore
        requests = _py_requests  # type: ignore
    except Exception:
        requests = None  # type: ignore
if time is None:
    try:
        import time as _py_time  # type: ignore
        time = _py_time  # type: ignore
    except Exception:
        time = None  # type: ignore

# CHANGED: prefer a to_thread-capable asyncio on CPython even if platform_compat shims are minimal
try:
    import asyncio as _py_asyncio  # type: ignore
except Exception:
    _py_asyncio = None  # type: ignore

def _to_thread_asyncio():
    try:
        if (not _IS_MICROPYTHON) and _pc_asyncio and hasattr(_pc_asyncio, "to_thread"):
            return _pc_asyncio
    except Exception:
        pass
    try:
        if (not _IS_MICROPYTHON) and _py_asyncio and hasattr(_py_asyncio, "to_thread"):
            return _py_asyncio
    except Exception:
        pass
    return None

# Minimal async HTTP client wrappers are not necessary when using urequests synchronously,
# but we wrap calls with try/except and timeouts where possible for safety.

def _auth_headers(mode=None):
    """Return headers for different auth modes:
       mode=None or 'auto' => prefer app-password Basic if configured.
       'none' => no auth
       'basic' => Basic auth using FIELD_DATA_APP_USER / FIELD_DATA_APP_PASS or WORDPRESS_USERNAME/PASSWORD
       'hub' => X-TMON-HUB header using any available hub shared key setting
       'read' => read token as X-TMON-READ or Bearer authorization
       'admin' => admin confirm header (used by Unit Connector Admin routes)
       'api_key' => generic API key header
    """
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    try:
        # no auth requested
        if mode == 'none':
            return headers
        # Basic app password / username fallback
        if mode in (None, 'auto', 'basic'):
            user = getattr(settings, 'FIELD_DATA_APP_USER', '') or getattr(settings, 'WORDPRESS_USERNAME', '') or ''
            pwd  = getattr(settings, 'FIELD_DATA_APP_PASS', '') or getattr(settings, 'WORDPRESS_PASSWORD', '') or ''
            if user and pwd:
                try:
                    creds = (str(user) + ':' + str(pwd)).encode('utf-8')
                    try:
                        import ubinascii as _ub  # MicroPython
                        b64 = _ub.b2a_base64(creds).decode('ascii').strip()
                    except Exception:
                        import base64 as _b64  # CPython (Zero)
                        b64 = _b64.b64encode(creds).decode('ascii').strip()
                    h = dict(headers)
                    h['Authorization'] = 'Basic ' + b64
                    return h
                except Exception:
                    pass
            if mode == 'basic':
                return headers
        # Hub shared key header
        if mode == 'hub':
            hub_key = getattr(settings, 'TMON_HUB_SHARED_KEY', None) or getattr(settings, 'TMON_HUB_KEY', None) or getattr(settings, 'WORDPRESS_HUB_KEY', None)
            if hub_key:
                h = dict(headers); h['X-TMON-HUB'] = str(hub_key); return h
        # Read token header (bearer or x-tmon-read)
        if mode == 'read':
            read = getattr(settings, 'TMON_HUB_READ_TOKEN', None) or getattr(settings, 'WORDPRESS_READ_TOKEN', None)
            if read:
                h = dict(headers); h['X-TMON-READ'] = str(read); h['Authorization'] = 'Bearer ' + str(read); return h
        # Admin confirm header (used by Unit Connector Admin routes)
        if mode == 'admin':
            token = getattr(settings, 'TMON_ADMIN_CONFIRM_TOKEN', None) or getattr(settings, 'WORDPRESS_ADMIN_TOKEN', None)
            if token:
                h = dict(headers)
                # Provide both common header names and a Bearer form to maximize compatibility with different plugin expectations
                admin_key = getattr(settings, 'REST_HEADER_ADMIN_KEY', 'X-TMON-ADMIN')
                confirm_key = getattr(settings, 'REST_HEADER_CONFIRM', 'X-TMON-CONFIRM')
                h[admin_key] = str(token)
                h[confirm_key] = str(token)
                # also include Authorization Bearer fallback
                h['Authorization'] = 'Bearer ' + str(token)
                return h
        # Generic API key header
        if mode == 'api_key':
            apik = getattr(settings, 'WORDPRESS_API_KEY', None) or getattr(settings, 'TMON_API_KEY', None)
            if apik:
                h = dict(headers); h[getattr(settings, 'REST_HEADER_API_KEY', 'X-TMON-API-Key')] = str(apik); return h
    except Exception:
        pass
    # default: return headers w/o auth
    return headers

# CHANGED: minimal urllib-based response shim to preserve current call sites
class _UrlLibResp:
    def __init__(self, code=0, text="", content=None):
        self.status_code = int(code or 0)
        self.text = text or ""
        self.content = content if content is not None else (self.text.encode("utf-8", "ignore") if isinstance(self.text, str) else b"")

    def json(self):
        return json.loads(self.text or "{}")

    def close(self):
        return None

def _urllib_post(url, payload=None, headers=None, timeout_s=8):
    # CHANGED: defensive no-op on MicroPython (urllib not available there)
    if _IS_MICROPYTHON:
        return _UrlLibResp(0, "urllib_unavailable", None)
    try:
        body = json.dumps(payload or {}).encode("utf-8")
    except Exception:
        body = b"{}"
    hdrs = dict(headers or {})
    try:
        if "Content-Type" not in hdrs:
            hdrs["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            raw = r.read()
            txt = ""
            try:
                txt = raw.decode("utf-8", "ignore")
            except Exception:
                txt = ""
            return _UrlLibResp(getattr(r, "status", 200), txt, raw)
    except urllib.error.HTTPError as e:
        raw = b""
        try:
            raw = e.read()
        except Exception:
            pass
        txt = ""
        try:
            txt = raw.decode("utf-8", "ignore")
        except Exception:
            txt = ""
        return _UrlLibResp(getattr(e, "code", 0), txt, raw)
    except Exception as e:
        return _UrlLibResp(0, str(e), None)

def _urllib_get(url, headers=None, timeout_s=8):
    # CHANGED: defensive no-op on MicroPython (urllib not available there)
    if _IS_MICROPYTHON:
        return _UrlLibResp(0, "urllib_unavailable", None)
    hdrs = dict(headers or {})
    try:
        req = urllib.request.Request(url, headers=hdrs, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            raw = r.read()
            txt = ""
            try:
                txt = raw.decode("utf-8", "ignore")
            except Exception:
                txt = ""
            return _UrlLibResp(getattr(r, "status", 200), txt, raw)
    except urllib.error.HTTPError as e:
        raw = b""
        try:
            raw = e.read()
        except Exception:
            pass
        txt = ""
        try:
            txt = raw.decode("utf-8", "ignore")
        except Exception:
            txt = ""
        return _UrlLibResp(getattr(e, "code", 0), txt, raw)
    except Exception as e:
        return _UrlLibResp(0, str(e), None)

async def _http_post(url, payload=None, headers=None, timeout_s=8):
    """
    CPython: run requests.post in a thread to avoid freezing the event loop.
    MicroPython/urequests: fall back to data=json.dumps(payload) and omit timeout when unsupported.
    """
    # CHANGED: if 'requests' is unavailable on CPython, fall back to urllib (only on CPython)
    if requests is None and not _IS_MICROPYTHON:
        a = _to_thread_asyncio()
        try:
            if a and hasattr(a, "to_thread"):
                return await a.to_thread(_urllib_post, url, payload, headers, timeout_s)
        except Exception:
            pass
        return _urllib_post(url, payload, headers, timeout_s)

    if requests is None:
        return None

    def _do_post():
        if not _IS_MICROPYTHON:
            return requests.post(url, json=payload, headers=headers, timeout=timeout_s)
        try:
            return requests.post(url, json=payload, headers=headers)  # type: ignore[arg-type]
        except TypeError:
            try:
                body = json.dumps(payload or {})
            except Exception:
                body = "{}"
            return requests.post(url, data=body, headers=headers)

    a = _to_thread_asyncio()
    try:
        if (not _IS_MICROPYTHON) and a and hasattr(a, "to_thread"):
            return await a.to_thread(_do_post)
    except Exception:
        pass
    return _do_post()

async def _http_get(url, headers=None, timeout_s=8):
    # CHANGED: if 'requests' is unavailable on CPython, fall back to urllib (only on CPython)
    if requests is None and not _IS_MICROPYTHON:
        a = _to_thread_asyncio()
        try:
            if a and hasattr(a, "to_thread"):
                return await a.to_thread(_urllib_get, url, headers, timeout_s)
        except Exception:
            pass
        return _urllib_get(url, headers, timeout_s)

    if requests is None:
        return None

    def _do_get():
        if not _IS_MICROPYTHON:
            return requests.get(url, headers=headers, timeout=timeout_s)
        try:
            return requests.get(url, headers=headers)  # urequests
        except TypeError:
            return requests.get(url, headers=headers)

    a = _to_thread_asyncio()
    try:
        if (not _IS_MICROPYTHON) and a and hasattr(a, "to_thread"):
            return await a.to_thread(_do_get)
    except Exception:
        pass
    return _do_get()

async def register_with_wp():
    """Register/check-in device with the configured WordPress/TMON Admin hub (best-effort).
    Tries multiple known admin endpoints to work around differing hub API routes.
    """
    try:
        # CHANGED: do not hard-depend on utils.is_http_allowed_for_node()
        if not _http_allowed_for_node():
            await debug_print('wprest: http disabled for remote node (provisioned)', 'WARN')
            return False

        base = getattr(settings, 'TMON_ADMIN_API_URL', '') or getattr(settings, 'WORDPRESS_API_URL', '')
        if not base:
            await debug_print('wprest: no Admin hub URL configured', 'WARN')
            return False
        payload = {
            'unit_id': getattr(settings, 'UNIT_ID', '') or '',
            'unit_name': getattr(settings, 'UNIT_Name', '') or '',
            'machine_id': get_machine_id() or '',
            'firmware_version': getattr(settings, 'FIRMWARE_VERSION', '') or '',
            'node_type': getattr(settings, 'NODE_TYPE', '') or '',
        }
        # Candidate register endpoints (order tuned for common server implementations)
        candidates = []
        try:
            candidates.append('/wp-json/tmon-admin/v1/device/check-in')
            candidates.append('/wp-json/tmon-admin/v1/device/checkin')  # CHANGED: common variant (no dash)
            candidates.append(getattr(settings, 'ADMIN_REGISTER_PATH', '/wp-json/tmon-admin/v1/device/register'))
            candidates.append('/wp-json/tmon-admin/v1/device/check-in/')  # CHANGED: tolerate trailing slash
            candidates.append(getattr(settings, 'ADMIN_V2_CHECKIN_PATH', '/wp-json/tmon-admin/v2/device/checkin'))
        except Exception:
            candidates = [
                '/wp-json/tmon-admin/v1/device/check-in',
                '/wp-json/tmon-admin/v1/device/checkin',
                '/wp-json/tmon-admin/v1/device/register',
                '/wp-json/tmon-admin/v2/device/checkin',
            ]

        # CHANGED: try multiple auth modes; many hubs allow unauth register/check-in
        auth_modes = [None, 'none', 'basic', 'hub', 'admin', 'read', 'api_key']

        last = None
        for path in candidates:
            for mode in auth_modes:
                try:
                    url = base.rstrip('/') + path
                    try:
                        hdrs = _auth_headers(mode)
                    except Exception:
                        hdrs = {}

                    resp = await _http_post(url, payload=payload, headers=hdrs, timeout_s=8)
                    status = getattr(resp, 'status_code', 0) if resp else 0
                    body_snip = ''
                    try:
                        body_snip = (getattr(resp, 'text', '') or '')[:400] if resp else ''
                    except Exception:
                        body_snip = ''

                    try:
                        if resp:
                            resp.close()
                    except Exception:
                        pass

                    last = (path, mode, status, body_snip[:200])

                    if status in (200, 201):
                        await debug_print(f'wprest: register ok via {path} auth={mode}', 'INFO')
                        try:
                            from oled import display_message
                            await display_message("Registered", 2)
                        except Exception:
                            pass
                        return True
                except Exception as e:
                    last = (path, mode, 'exc', str(e)[:200])

        # CHANGED: include last attempt details on ERROR so it shows even with DEBUG=False
        await debug_print(f'wprest: register_all_attempts_failed last={last}', 'ERROR')
        try:
            from oled import display_message
            await display_message("Register Failed", 2)
        except Exception:
            pass
        return False
    except Exception as e:
        await debug_print(f'wprest: register exception {e}', 'ERROR')
        return False

async def send_data_to_wp():
    """Send recent field data batches to WordPress field-data endpoint (best-effort).
       This implementation uses same semantics as utils.send_field_data_log but is a lightweight wrapper.
    """
    try:
        # CHANGED
        if not _http_allowed_for_node():
            await debug_print('wprest: skip send_data (remote node http disabled)', 'WARN')
            return False
    except Exception:
        pass

    try:
        if not getattr(settings, 'WORDPRESS_API_URL', ''):
            await debug_print('wprest: no WP url', 'WARN')
            return False
        backlog = read_backlog()
        if not backlog:
            return False
        url = settings.WORDPRESS_API_URL.rstrip('/') + '/wp-json/tmon/v1/device/field-data'
        hdrs = _auth_headers()
        for payload in backlog:
            try:
                js = json.dumps(payload)
            except Exception:
                js = '{}'
            try:
                resp = requests.post(url, data=js, headers=hdrs, timeout=10)
                code = getattr(resp, 'status_code', 0)
                body = ''
                try:
                    body = (getattr(resp, 'text', '') or '')[:400]
                except Exception:
                    pass
                if resp: resp.close()
                if code in (200,201):
                    clear_backlog()
                    await debug_print('wprest: field data posted', 'INFO')
                    return True
                if code == 401:
                    await debug_print('wprest: field data POST returned 401 Unauthorized. Verify FIELD_DATA_APP_PASS / credentials for the site.', 'WARN')
                else:
                    await debug_print(f'wprest: send_field_data failed {code} {body}', 'WARN')
            except Exception as e:
                await debug_print(f'wprest: send_field_data err {e}', 'ERROR')
        return False
    except Exception as e:
        await debug_print(f'wprest: send_data_to_wp exc {e}', 'ERROR')
        return False

async def send_settings_to_wp():
    """POST a snapshot of persistent settings to WP (best-effort).
       Tries multiple endpoint paths and auth modes (auto/basic/hub/read/none).
       On repeated failure, append payload to backlog for later retry.
    """
    try:
        # CHANGED
        if not _http_allowed_for_node():
            await debug_print('wprest: skip send_settings (remote node http disabled)', 'WARN')
            return False
    except Exception:
        pass

    try:
        wp = getattr(settings, 'WORDPRESS_API_URL', '') or ''
        if not wp:
            await debug_print('wprest: no WP url for settings', 'WARN')
            return False

        payload = {
            'unit_id': getattr(settings, 'UNIT_ID', ''),
            'unit_name': getattr(settings, 'UNIT_Name', ''),
            'settings': {}
        }
        for k in dir(settings):
            if not k.startswith('__') and k.isupper():
                try:
                    payload['settings'][k] = getattr(settings, k)
                except Exception:
                    pass

        # Candidate endpoint variants
        candidate_paths = []
        try:
            candidate_paths.append(getattr(settings, 'UC_SETTINGS_APPLIED_PATH', '/wp-json/tmon/v1/admin/device/settings-applied'))
        except Exception:
            candidate_paths.append('/wp-json/tmon/v1/admin/device/settings-applied')

        candidate_paths.extend([
            '/wp-json/tmon/v1/device/settings-applied',
            '/wp-json/unit-connector/v1/device/settings-applied',
            '/wp-json/tmon-unit-connector/v1/device/settings-applied',
        ])

        try:
            candidate_paths.append(getattr(settings, 'ADMIN_SETTINGS_PATH', '/wp-json/tmon/v1/admin/device/settings'))
        except Exception:
            candidate_paths.append('/wp-json/tmon/v1/admin/device/settings')

        candidate_paths.extend([
            '/wp-json/tmon/v1/device/settings',
            '/wp-json/tmon-admin/v1/device/settings'
        ])

        # Reorder auth modes: try Basic (App Password) first (common for device endpoints),
        # then admin token, then hub/read/none. This reduces 403 when admin token isn't set.
        auth_modes = ['basic', 'admin', 'hub', 'read', None, 'none']

        last_response = None
        for p in candidate_paths:
            target = wp.rstrip('/') + p
            for mode in auth_modes:
                try:
                    hdrs = _auth_headers(mode)
                except Exception:
                    hdrs = {}
                try:
                    try:
                        resp = requests.post(target, json=payload, headers=hdrs, timeout=8)
                    except TypeError:
                        resp = requests.post(target, json=payload, headers=hdrs)
                    code = getattr(resp, 'status_code', 0)
                    body = (getattr(resp, 'text', '') or '')[:400]
                    try:
                        if resp: resp.close()
                    except Exception:
                        pass
                    await debug_print(f'wprest: send_settings try {p} auth={mode} -> {code} ({body[:200]})', 'HTTP')
                    last_response = (code, body, mode, p)
                    if code in (200, 201):
                        await debug_print(f'wprest: send_settings succeeded via {p} auth={mode}', 'INFO')
                        try:
                            from oled import display_message
                            await display_message("Settings Sent", 2)
                        except Exception:
                            pass
                        return True
                    # On 403, try targeted header fallbacks for admin-style endpoints before continuing
                    if code == 403:
                        await debug_print(f"wprest: {p} -> 403, trying header fallbacks", 'WARN')
                        for hdr_mode in ('admin', 'hub', 'api_key', 'read', 'basic'):
                            try:
                                try:
                                    fb_hdrs = _auth_headers(hdr_mode)
                                except Exception:
                                    fb_hdrs = {}
                                try:
                                    try:
                                        resp2 = requests.post(target, json=payload, headers=fb_hdrs, timeout=8)
                                    except TypeError:
                                        resp2 = requests.post(target, json=payload, headers=fb_hdrs)
                                except Exception as e:
                                    await debug_print(f"wprest: header-fallback {hdr_mode} exception: {e}", 'WARN')
                                    resp2 = None
                                code2 = getattr(resp2, 'status_code', 0) if resp2 else 0
                                body2 = (getattr(resp2, 'text', '') or '')[:200] if resp2 else ''
                                try:
                                    if resp2: resp2.close()
                                except Exception:
                                    pass
                                await debug_print(f"wprest: header-fallback {hdr_mode} -> {code2} ({body2[:160]})", 'HTTP')
                                if code2 in (200, 201):
                                    await debug_print(f'wprest: send_settings succeeded via header-fallback {hdr_mode} on {p}', 'INFO')
                                    return True
                            except Exception:
                                pass
                        # fell through, continue trying other candidate paths
                except Exception as e:
                    await debug_print(f'wprest: send_settings attempt {p} auth={mode} exception: {e}', 'ERROR')
                    last_response = ('err', str(e), mode, p)
        await debug_print(f'wprest: send_settings all attempts failed; last={last_response}', 'WARN')
        try:
            from oled import display_message
            await display_message("Settings Failed", 2)
        except Exception:
            pass
        try:
            append_to_backlog({'type': 'settings', 'payload': payload, 'ts': int(time.time())})
        except Exception:
            pass
        return False
    except Exception as e:
        await debug_print(f'wprest: send_settings outer exc {e}', 'ERROR')
        try:
            from oled import display_message
            await display_message("Settings Failed", 2)
        except Exception:
            pass
        try:
            append_to_backlog({'type': 'settings', 'payload': payload, 'ts': int(time.time())})
        except Exception:
            pass
        return False

async def fetch_staged_settings():
    """GET staged settings for this unit (best-effort). Returns dict or None."""
    try:
        if not getattr(settings, 'WORDPRESS_API_URL', ''):
            return None
        unit = getattr(settings, 'UNIT_ID', '') or ''
        q = '?unit_id=' + unit if unit else ''
        url = settings.WORDPRESS_API_URL.rstrip('/') + '/wp-json/tmon/v1/device/staged-settings' + q
        try:
            resp = requests.get(url, headers=_auth_headers(), timeout=6)
        except TypeError:
            resp = requests.get(url, headers=_auth_headers())
        code = getattr(resp, 'status_code', 0)
        body = getattr(resp, 'text', '') or ''
        try:
            data = json.loads(body) if body else None
        except Exception:
            data = None
        try:
            if resp: resp.close()
        except Exception:
            pass
        if code in (200,201) and isinstance(data, dict):
            await debug_print('wprest: fetched staged settings', 'INFO')
            return data
        return None
    except Exception as e:
        await debug_print(f'wprest: fetch_staged_settings exc {e}', 'ERROR')
        return None

# New helper: fetch applied settings from WP (used by lora.py)
async def fetch_settings_from_wp():
    """GET applied device settings from WP (best-effort). Returns dict or None."""
    try:
        # CHANGED
        if not _http_allowed_for_node():
            await debug_print('wprest: skip fetch_settings (remote node http disabled)', 'WARN')
            return None
    except Exception:
        pass

    try:
        if not getattr(settings, 'WORDPRESS_API_URL', ''):
            return None
        unit = getattr(settings, 'UNIT_ID', '') or ''
        if not unit:
            return None
        url = settings.WORDPRESS_API_URL.rstrip('/') + '/wp-json/tmon/v1/device/settings/' + unit
        try:
            resp = requests.get(url, headers=_auth_headers(), timeout=8)
        except TypeError:
            resp = requests.get(url, headers=_auth_headers())
        code = getattr(resp, 'status_code', 0)
        body = getattr(resp, 'text', '') or ''
        try:
            data = json.loads(body) if body else None
        except Exception:
            data = None
        try:
            if resp: resp.close()
        except Exception:
            pass
        if code in (200,201) and isinstance(data, dict):
            await debug_print('wprest: fetched settings', 'INFO')
            return data.get('settings', data) if isinstance(data, dict) else None
        if code == 401:
            await debug_print('wprest: fetch_settings returned 401 Unauthorized. Check configured credentials (FIELD_DATA_APP_PASS).', 'WARN')
        else:
            await debug_print(f'wprest: fetch_settings failed {code}', 'WARN')
        return None
    except Exception as e:
        await debug_print(f'wprest: fetch_settings exc {e}', 'ERROR')
        return None

async def poll_device_commands():
    """Poll for queued commands from Unit Connector. Return list of commands or [].
       On simple success, call handle_device_command for each command if available.
    """
    try:
        # CHANGED
        if not _http_allowed_for_node():
            await debug_print('wprest: skip poll_device_commands (remote node http disabled)', 'WARN')
            return []
    except Exception:
        pass

    try:
        if not getattr(settings, 'WORDPRESS_API_URL', ''):
            return []
        unit = getattr(settings, 'UNIT_ID', '') or ''
        if not unit:
            return []
        # Try several candidate command endpoints (admin-scoped first, then device, then legacy)
        base = settings.WORDPRESS_API_URL.rstrip('/')
        candidate_paths = []
        try:
            # prefer admin-scoped commands path when available on UC deployments
            candidate_paths.append('/wp-json/tmon/v1/admin/device/commands')
        except Exception:
            candidate_paths.append('/wp-json/tmon/v1/admin/device/commands')
        # Add common vendor/plugin name variants
        candidate_paths.extend([
            '/wp-json/unit-connector/v1/device/commands',
            '/wp-json/tmon-unit-connector/v1/device/commands',
            getattr(settings, 'WPREST_COMMANDS_PATH', '/wp-json/tmon/v1/device/commands'),
            '/wp-json/tmon-admin/v1/device/commands'
        ])
        hdrs = {}
        try:
            hdrs = _auth_headers()
        except Exception:
            hdrs = {}
        data = None; code = 0
        tried = []
        # For each candidate, prefer POST {unit_id} then GET fallback
        for p in candidate_paths:
            post_url = base + p
            try:
                try:
                    resp = requests.post(post_url, json={'unit_id': unit}, headers=hdrs, timeout=8)
                except TypeError:
                    resp = requests.post(post_url, json={'unit_id': unit}, headers=hdrs)
                code = getattr(resp, 'status_code', 0)
                body = getattr(resp, 'text', '') or ''
                tried.append(('POST', post_url, code))
                try:
                    data = json.loads(body) if body else None
                except Exception:
                    data = None
                try:
                    if resp: resp.close()
                except Exception:
                    pass
                await debug_print(f"wprest: poll_device_commands POST {p} -> {code}", "HTTP")
                if code in (200,201) and isinstance(data, (dict, list)):
                    break
            except Exception as e:
                await debug_print(f"wprest: poll_device_commands POST {p} err: {e}", "ERROR")
            # try GET fallback for same path
            try:
                get_url = base + p + ('?unit_id=' + unit if '?' not in p else '&unit_id=' + unit)
                try:
                    resp = requests.get(get_url, headers=hdrs, timeout=8)
                except TypeError:
                    resp = requests.get(get_url, headers=hdrs)
                code = getattr(resp, 'status_code', 0)
                body = getattr(resp, 'text', '') or ''
                tried.append(('GET', get_url, code))
                try:
                    data = json.loads(body) if body else None
                except Exception:
                    data = None
                try:
                    if resp: resp.close()
                except Exception:
                    pass
                await debug_print(f"wprest: poll_device_commands GET {p} -> {code}", "HTTP")
                if code in (200,201) and isinstance(data, (dict, list)):
                    break
            except Exception as e:
                await debug_print(f"wprest: poll_device_commands GET {p} err: {e}", "ERROR")
        await debug_print(f"wprest: poll_device_commands attempts: {tried}", "HTTP")
        # Now 'data' may be a list or dict {'commands': [...]}
        commands = []
        if code in (200,201):
            if isinstance(data, dict) and isinstance(data.get('commands'), list):
                commands = data.get('commands')
            elif isinstance(data, list):
                commands = data
            # handle them best-effort
            for c in (commands or []):
                try:
                    from commands import handle_command as _hc
                    try:
                        await _hc(c)
                    except Exception:
                        pass
                except Exception:
                    try:
                        # CHANGED: _queue_command_confirm is sync; do not await it
                        _queue_command_confirm({
                            'job_id': c.get('id') if isinstance(c, dict) else None,
                            'ok': True,
                            'result': 'handled_locally_not_implemented'
                        })
                    except Exception:
                        pass
            return commands
        return []
    except Exception as e:
        await debug_print(f'wprest: poll_device_commands exc {e}', 'ERROR')
        return []
    
async def poll_ota_jobs():
    """Basic poll for OTA jobs; returns list or [] (no-op default)."""
    try:
        # Provide a simple probe hook: GET /wp-json/tmon/v1/device/ota?unit_id=
        if not getattr(settings, 'WORDPRESS_API_URL', ''):
            return []
        unit = getattr(settings, 'UNIT_ID', '') or ''
        url = settings.WORDPRESS_API_URL.rstrip('/') + '/wp-json/tmon/v1/device/ota?unit_id=' + unit
        try:
            resp = requests.get(url, headers=_auth_headers(), timeout=8)
            code = getattr(resp, 'status_code', 0)
            body = getattr(resp, 'text', '') or ''
            try:
                data = json.loads(body) if body else None
            except Exception:
                data = None
            try:
                if resp: resp.close()
            except Exception:
                pass
            if code in (200,201) and isinstance(data, dict) and data.get('jobs'):
                return data.get('jobs')
        except Exception:
            pass
        return []
    except Exception:
        return []

async def send_file_to_wp(filepath):
    """Upload a file to WP (best-effort); returns True on 200/201."""
    try:
        if not getattr(settings, 'WORDPRESS_API_URL', ''):
            return False
        url = settings.WORDPRESS_API_URL.rstrip('/') + '/wp-json/tmon/v1/device/file'
        hdrs = _auth_headers()
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            # Note: simplified; many MicroPython request libs do not support 'files' param
            resp = requests.post(url, headers=hdrs, data=data, timeout=15)
            code = getattr(resp, 'status_code', 0)
            if resp: resp.close()
            return code in (200,201)
        except Exception as e:
            await debug_print(f'wprest: send_file err {e}', 'ERROR')
            return False
    except Exception:
        return False

async def request_file_from_wp(filename):
    """Request a file from WP; returns file bytes or None."""
    try:
        if not getattr(settings, 'WORDPRESS_API_URL', ''):
            return None
        unit = getattr(settings, 'UNIT_ID', '') or ''
        url = settings.WORDPRESS_API_URL.rstrip('/') + f'/wp-json/tmon/v1/device/file/{unit}/{filename}'
        try:
            resp = requests.get(url, headers=_auth_headers(), timeout=15)
            code = getattr(resp, 'status_code', 0)
            if code in (200,201):
                content = getattr(resp, 'content', None) or (getattr(resp, 'text', '').encode('utf-8', 'ignore') if hasattr(resp, 'text') else None)
                try:
                    if resp: resp.close()
                except Exception:
                    pass
                return content
            try:
                if resp: resp.close()
            except Exception:
                pass
            return None
        except Exception as e:
            await debug_print(f'wprest: request_file err {e}', 'ERROR')
            return None
    except Exception:
        return None

# --- Pending command confirmations queue helpers ---
# Persist confirmations locally when immediate confirm POST fails, and flush them on next checkin.

def _pending_confirms_path():
    return getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/pending_command_confirms.json'

def _load_pending_confirms():
    path = _pending_confirms_path()
    try:
        with open(path, 'r') as f:
            return json.loads(f.read())
    except Exception:
        return []

def _save_pending_confirms(arr):
    path = _pending_confirms_path()
    try:
        with open(path, 'w') as f:
            f.write(json.dumps(arr))
    except Exception:
        pass

def _queue_command_confirm(entry):
    try:
        arr = _load_pending_confirms()
        arr.append(entry)
        # bound queue length
        if len(arr) > 200:
            arr = arr[-200:]
        _save_pending_confirms(arr)
        return True
    except Exception:
        return False

def _remove_pending_confirm(job_id):
    try:
        arr = _load_pending_confirms()
        new = [e for e in arr if str(e.get('job_id')) != str(job_id)]
        _save_pending_confirms(new)
        return True
    except Exception:
        return False

async def _flush_pending_command_confirms():
    """Try to POST pending confirms to WP; remove on success."""
    try:
        arr = _load_pending_confirms()
        if not arr:
            return True
        url = settings.WORDPRESS_API_URL.rstrip('/') + '/wp-json/tmon/v1/device/command/confirm'
        hdrs = _auth_headers()
        success_ids = []
        for e in arr:
            try:
                j = {'job_id': e.get('job_id'), 'ok': bool(e.get('ok')), 'result': e.get('result','')}
                resp = requests.post(url, json=j, headers=hdrs, timeout=8)
            except TypeError:
                resp = requests.post(url, json=j, headers=hdrs)
            except Exception:
                resp = None
            code = getattr(resp, 'status_code', 0) if resp else 0
            if resp:
                try:
                    resp.close()
                except Exception:
                    pass
            if code in (200,201):
                success_ids.append(e.get('job_id'))
        if success_ids:
            # prune saved list
            arr = [e for e in arr if e.get('job_id') not in success_ids]
            _save_pending_confirms(arr)
        return True
    except Exception:
        return False

async def _post_command_confirm(payload):
    """Best-effort: POST a command-complete / ack to the configured WP URL."""
    try:
        wp_url = getattr(settings, 'WORDPRESS_API_URL', '') or ''
        if not wp_url:
            return False
        url = wp_url.rstrip('/') + '/wp-json/tmon/v1/device/command/confirm'
        try:
            resp = requests.post(url, json=payload, headers=_auth_headers(), timeout=8)
            code = getattr(resp, 'status_code', 0)
            if resp: resp.close()
            ok = code in (200, 201)
        except Exception:
            ok = False
        if not ok:
            # queue for retry
            _queue_command_confirm(payload)
        return ok
    except Exception:
        return False

# expose small stable names
__all__ = [
    'register_with_wp', 'send_data_to_wp', 'send_settings_to_wp',
    'fetch_staged_settings', 'fetch_settings_from_wp', 'poll_device_commands', 'poll_ota_jobs',
    'send_file_to_wp', 'request_file_from_wp', 'heartbeat_ping'
]

async def heartbeat_ping():
    """Best-effort heartbeat POST to the server's heartbeat endpoint."""
    try:
        # CHANGED
        if not _http_allowed_for_node():
            await debug_print('wprest: skip heartbeat (remote node http disabled)', 'WARN')
            return False
    except Exception:
        pass

    try:
        wp = getattr(settings, 'WORDPRESS_API_URL', '') or ''
        if not wp:
            return False
        url = wp.rstrip('/') + '/wp-json/tmon/v1/device/heartbeat'
        payload = {'unit_id': getattr(settings, 'UNIT_ID', ''), 'machine_id': get_machine_id()}
        hdrs = _auth_headers()
        try:
            resp = requests.post(url, json=payload, headers=hdrs, timeout=6)
        except TypeError:
            resp = requests.post(url, json=payload, headers=hdrs)
        code = getattr(resp, 'status_code', 0)
        try:
            if resp: resp.close()
        except Exception:
            pass
        return code in (200, 201)
    except Exception:
        return False

# --- GC: best-effort cleanup after module import / heavy init ---
try:
    import gc
    gc.collect()
except Exception:
    pass
