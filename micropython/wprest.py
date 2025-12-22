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

def _auth_headers(mode=None):
    """Return headers for different auth modes:
       mode=None or 'auto' => prefer app-password Basic if configured.
       'none' => no auth
       'basic' => Basic auth using FIELD_DATA_APP_USER / FIELD_DATA_APP_PASS or WORDPRESS_USERNAME/PASSWORD
       'hub' => X-TMON-HUB header using any available hub shared key setting
       'read' => read token as X-TMON-READ or Bearer authorization
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
                    import ubinascii as _ub
                    creds = (str(user) + ':' + str(pwd)).encode('utf-8')
                    b64 = _ub.b2a_base64(creds).decode('ascii').strip()
                    h = dict(headers)
                    h['Authorization'] = 'Basic ' + b64
                    return h
                except Exception:
                    pass
            # if mode explicitly 'basic' and no creds, fall back to no auth
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
    except Exception:
        pass
    # default: return headers w/o auth
    return headers

async def register_with_wp():
    """Register/check-in device with the configured WordPress/TMON Admin hub (best-effort).
    Tries multiple known admin endpoints to work around differing hub API routes.
    """
    try:
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
        # Candidate register endpoints (order is intentional: legacy -> v2)
        candidates = []
        try:
            candidates.append(getattr(settings, 'ADMIN_REGISTER_PATH', '/wp-json/tmon-admin/v1/device/register'))
            # Common check-in alternative used in other code
            candidates.append('/wp-json/tmon-admin/v1/device/check-in')
            # Versioned admin checkin
            candidates.append(getattr(settings, 'ADMIN_V2_CHECKIN_PATH', '/wp-json/tmon-admin/v2/device/checkin'))
        except Exception:
            candidates = ['/wp-json/tmon-admin/v1/device/register', '/wp-json/tmon-admin/v1/device/check-in', '/wp-json/tmon-admin/v2/device/checkin']

        hdrs = _auth_headers() if callable(_auth_headers) else {}
        for path in candidates:
            try:
                url = base.rstrip('/') + path
                try:
                    resp = requests.post(url, json=payload, headers=hdrs, timeout=8)
                except TypeError:
                    resp = requests.post(url, json=payload, headers=hdrs)
                status = getattr(resp, 'status_code', 0)
                body_snip = ''
                try:
                    body_snip = (getattr(resp, 'text', '') or '')[:400]
                except Exception:
                    body_snip = ''
                try:
                    if resp:
                        resp.close()
                except Exception:
                    pass
                if status in (200, 201):
                    await debug_print(f'wprest: register ok via {path}', 'INFO')
                    return True
                # Log diagnostic per-candidate
                if status == 404:
                    await debug_print(f'wprest: register endpoint {path} not found (404)', 'WARN')
                elif status == 401:
                    await debug_print(f'wprest: register endpoint {path} returned 401 Unauthorized. Check FIELD_DATA_APP_PASS / credentials.', 'WARN')
                else:
                    await debug_print(f'wprest: register failed {status} for {path} ({body_snip})', 'WARN')
            except Exception as e:
                await debug_print(f'wprest: register attempt {path} exception: {e}', 'ERROR')
        await debug_print('wprest: register_all_attempts_failed', 'ERROR')
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
            hdrs = _auth_headers()
        except Exception:
            hdrs = {}
        try:
            # Prefer the admin-style endpoint where UC/Admin exposes device settings APIs.
            candidate_paths = [
                '/wp-json/tmon/v1/admin/device/settings',  # preferred admin endpoint
                '/wp-json/tmon-admin/v1/device/settings',   # legacy/hub-style
                '/wp-json/tmon/v1/device/settings',         # older device-targeted endpoint (may require Basic auth)
            ]
            for p in candidate_paths:
                try:
                    target = settings.WORDPRESS_API_URL.rstrip('/') + p
                    try:
                        resp = requests.post(target, json=payload, headers=hdrs, timeout=8)
                    except TypeError:
                        resp = requests.post(target, json=payload, headers=hdrs)
                    code = getattr(resp, 'status_code', 0)
                    body_snip = (getattr(resp, 'text', '') or '')[:400]
                    if resp: resp.close()
                    await debug_print(f'wprest: send_settings {p} -> {code} ({body_snip[:200]})', 'HTTP')
                    if code in (200, 201):
                        return True
                    if code == 401:
                        # Diagnostic: did we send Authorization? do we have app-pass configured?
                        auth_sent = bool(hdrs.get('Authorization'))
                        user_set = bool(getattr(settings, 'FIELD_DATA_APP_USER', None) or getattr(settings, 'WORDPRESS_USERNAME', None))
                        pass_set = bool(getattr(settings, 'FIELD_DATA_APP_PASS', None))
                        await debug_print(f'wprest: send_settings 401 on {p} (auth_sent={auth_sent} user_set={user_set} pass_set={pass_set})', 'WARN')
                        # Try Basic fallback if possible
                        if not auth_sent and user_set and pass_set:
                            try:
                                import ubinascii as _ub
                                user = getattr(settings, 'FIELD_DATA_APP_USER', '') or getattr(settings, 'WORDPRESS_USERNAME', '')
                                pwd = getattr(settings, 'FIELD_DATA_APP_PASS', '')
                                creds = (str(user) + ':' + str(pwd)).encode('utf-8')
                                b64 = _ub.b2a_base64(creds).decode('ascii').strip()
                                fb = dict(hdrs); fb['Authorization'] = 'Basic ' + b64
                                try:
                                    r2 = requests.post(target, json=payload, headers=fb, timeout=8)
                                except TypeError:
                                    r2 = requests.post(target, json=payload, headers=fb)
                                c2 = getattr(r2, 'status_code', 0)
                                b2 = (getattr(r2, 'text', '') or '')[:400]
                                if r2: r2.close()
                                await debug_print(f'wprest: send_settings fallback Basic auth {p} -> {c2} ({b2[:200]})', 'HTTP')
                                if c2 in (200,201):
                                    return True
                            except Exception as e:
                                await debug_print(f'wprest: fallback Basic auth attempt failed: {e}', 'ERROR')
                    # continue to next candidate on non-success
                except Exception as e:
                    await debug_print(f'wprest: send_settings attempt {p} exception: {e}', 'ERROR')
            # If we reach here, none succeeded. Queue for retry to avoid data loss.
            await debug_print('wprest: send_settings all attempts failed; queuing payload', 'WARN')
            try:
                append_to_backlog({'type': 'settings', 'payload': payload, 'ts': int(time.time())})
            except Exception:
                pass
            return False
        except Exception as e:
            await debug_print(f'wprest: send_settings exc {e}', 'ERROR')
            try:
                append_to_backlog({'type': 'settings', 'payload': payload, 'ts': int(time.time())})
            except Exception:
                pass
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

# New helper: fetch applied settings from WP (used by lora.py)
async def fetch_settings_from_wp():
    """GET applied device settings from WP (best-effort). Returns dict or None."""
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
    'fetch_staged_settings', 'fetch_settings_from_wp', 'poll_device_commands', 'poll_ota_jobs',
    'send_file_to_wp', 'request_file_from_wp', 'heartbeat_ping'
]
