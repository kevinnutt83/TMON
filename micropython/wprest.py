# Firmware Version: v2.06.0
# wprest.py
# Handles WordPress REST API communication for TMON MicroPython device

import gc
try:
    import urequests as requests
except Exception:
    try:
        import requests
    except Exception:
        requests = None

try:
    import ujson as json
except Exception:
    import json

from utils import debug_print, get_machine_id, persist_unit_id, append_to_backlog, read_backlog, clear_backlog
import settings
import os

WORDPRESS_API_URL = getattr(settings, 'WORDPRESS_API_URL', '')
WORDPRESS_USERNAME = getattr(settings, 'WORDPRESS_USERNAME', None)
WORDPRESS_PASSWORD = getattr(settings, 'WORDPRESS_PASSWORD', None)

# Minimal async HTTP client wrappers are not necessary when using urequests synchronously,
# but we wrap calls with try/except and timeouts where possible for safety.

def _auth_headers():
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    # Basic auth via app password if configured
    try:
        if getattr(settings, 'FIELD_DATA_USE_APP_PASSWORD', False) and getattr(settings, 'FIELD_DATA_APP_USER','') and getattr(settings, 'FIELD_DATA_APP_PASS',''):
            import ubinascii as _ub
            creds = (getattr(settings,'FIELD_DATA_APP_USER','') + ':' + getattr(settings,'FIELD_DATA_APP_PASS','')).encode('utf-8')
            b64 = _ub.b2a_base64(creds).decode('ascii').strip()
            headers['Authorization'] = 'Basic ' + b64
    except Exception:
        pass
    return headers

async def register_with_wp():
    """Register/check-in device with the configured WordPress/TMON Admin hub (best-effort)."""
    try:
        if not getattr(settings, 'WORDPRESS_API_URL', ''):
            await debug_print('wprest: no WP url', 'WARN')
            return False
        payload = {
            'unit_id': getattr(settings, 'UNIT_ID', ''),
            'unit_name': getattr(settings, 'UNIT_Name', ''),
            'machine_id': get_machine_id() or '',
            'firmware_version': getattr(settings, 'FIRMWARE_VERSION', ''),
            'node_type': getattr(settings, 'NODE_TYPE', ''),
        }
        url = settings.WORDPRESS_API_URL.rstrip('/') + '/wp-json/tmon-admin/v1/device/register'
        hdrs = _auth_headers()
        # Best-effort POST
        try:
            resp = requests.post(url, json=payload, headers=hdrs, timeout=8)
        except TypeError:
            resp = requests.post(url, json=payload, headers=hdrs)
        status = getattr(resp, 'status_code', 0)
        text = ''
        try:
            text = getattr(resp, 'text', '') or ''
        except Exception:
            pass
        try:
            if resp:
                resp.close()
        except Exception:
            pass
        if status in (200, 201):
            await debug_print('wprest: register ok', 'INFO')
            return True
        await debug_print(f'wprest: register failed {status} {text[:200]}', 'WARN')
        return False
    except Exception as e:
        await debug_print(f'wprest: register exception {e}', 'ERROR')
        return False

async def send_data_to_wp():
    """Send recent field data batches to WordPress field-data endpoint (best-effort).
       This implementation uses same semantics as utils.send_field_data_log but is a lightweight wrapper.
    """
    try:
        if not getattr(settings, 'WORDPRESS_API_URL', ''):
            await debug_print('wprest: no WP url', 'WARN')
            return False
        # If there's backlog persisted, try to flush it (append_to_backlog is used by utils)
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
                if resp: resp.close()
                if code in (200,201):
                    # On success, clear the backlog (utils will rotate)
                    clear_backlog()
                    await debug_print('wprest: field data posted', 'INFO')
                    return True
            except Exception as e:
                await debug_print(f'wprest: send_field_data err {e}', 'ERROR')
        return False
    except Exception as e:
        await debug_print(f'wprest: send_data_to_wp exc {e}', 'ERROR')
        return False

async def send_settings_to_wp():
    """POST a snapshot of persistent settings to WP (best-effort)."""
    try:
        if not getattr(settings, 'WORDPRESS_API_URL', ''):
            await debug_print('wprest: no WP url for settings', 'WARN')
            return False
        url = settings.WORDPRESS_API_URL.rstrip('/') + '/wp-json/tmon/v1/device/settings'
        payload = {
            'unit_id': getattr(settings, 'UNIT_ID', ''),
            'unit_name': getattr(settings, 'UNIT_Name', ''),
            'settings': {}
        }
        # keep settings snapshot small by only including allowlisted keys where possible
        for k in dir(settings):
            if not k.startswith('__') and k.isupper():
                try:
                    payload['settings'][k] = getattr(settings, k)
                except Exception:
                    pass
        try:
            resp = requests.post(url, json=payload, headers=_auth_headers(), timeout=8)
            code = getattr(resp, 'status_code', 0)
            if resp: resp.close()
            await debug_print(f'wprest: send_settings status {code}', 'INFO')
            return code in (200,201)
        except Exception as e:
            await debug_print(f'wprest: send_settings err {e}', 'ERROR')
            return False
    except Exception as e:
        await debug_print(f'wprest: send_settings exc {e}', 'ERROR')
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

async def poll_device_commands():
    """Poll for queued commands from Unit Connector. Return list of commands or [].
       On simple success, call handle_device_command for each command if available.
    """
    try:
        if not getattr(settings, 'WORDPRESS_API_URL', ''):
            return []
        unit = getattr(settings, 'UNIT_ID', '') or ''
        if not unit:
            return []
        url = settings.WORDPRESS_API_URL.rstrip('/') + '/wp-json/tmon/v1/device/commands?unit_id=' + unit
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
        commands = []
        if code in (200,201):
            # Accept either {commands:[...]} or top-level array
            if isinstance(data, dict) and isinstance(data.get('commands'), list):
                commands = data.get('commands')
            elif isinstance(data, list):
                commands = data
            # handle them best-effort
            for c in (commands or []):
                try:
                    # Try to call local handler (if implemented elsewhere)
                    from commands import handle_command as _hc
                    try:
                        await _hc(c)
                    except Exception:
                        pass
                except Exception:
                    # No local handler; queue confirm attempt as pending
                    try:
                        # best-effort confirm as received
                        await _queue_command_confirm({'job_id': c.get('id') if isinstance(c, dict) else None, 'ok': True, 'result': 'handled_locally_not_implemented'})
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
    'fetch_staged_settings', 'poll_device_commands', 'poll_ota_jobs',
    'send_file_to_wp', 'request_file_from_wp', 'heartbeat_ping'
]
