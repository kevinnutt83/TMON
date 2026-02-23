# TMON Verion 2.00.1d - WordPress REST API integration for device registration, field data upload, and settings sync. Implements multiple auth modes (Basic, Hub token, Read token, Admin token) and endpoint fallbacks for compatibility with different server configurations. Includes error handling and backlogging of failed attempts for later retry.

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

from utils import debug_print, get_machine_id, persist_unit_id, persist_unit_name, append_to_backlog, read_backlog, clear_backlog
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

async def register_with_wp():
    """Register/check-in device with the configured WordPress/TMON Admin hub (best-effort).
    Tries multiple known admin endpoints to work around differing hub API routes.
    """
    try:
        # REMOTE nodes: once provisioned, must not perform HTTP calls
        try:
            from utils import is_http_allowed_for_node
            if not is_http_allowed_for_node():
                await debug_print('wprest: http disabled for remote node (provisioned)', 'WARN')
                return False
        except Exception:
            pass

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
            candidates.append(getattr(settings, 'ADMIN_REGISTER_PATH', '/wp-json/tmon-admin/v1/device/register'))
            candidates.append(getattr(settings, 'ADMIN_V2_CHECKIN_PATH', '/wp-json/tmon-admin/v2/device/checkin'))
        except Exception:
            candidates = ['/wp-json/tmon-admin/v1/device/check-in', '/wp-json/tmon-admin/v1/device/register', '/wp-json/tmon-admin/v2/device/checkin']

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
                # Parse and persist name if present
                try:
                    if status in (200, 201):
                        try:
                            j = resp.json()
                        except Exception:
                            j = {}
                        unit_name = (j.get('unit_name') or '').strip()
                        if unit_name:
                            try:
                                from utils import persist_unit_name
                                persist_unit_name(unit_name)
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    if resp:
                        resp.close()
                except Exception:
                    pass
                if status in (200, 201):
                    await debug_print(f'wprest: register ok via {path}', 'INFO')
                    try:
                        from oled import display_message
                        await display_message("Registered", 2)
                    except Exception:
                        pass
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
        from utils import is_http_allowed_for_node
        if not is_http_allowed_for_node():
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
        from utils import is_http_allowed_for_node
        if not is_http_allowed_for_node():
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
                except Exception as e:
                    await debug_print(f'wprest: send_settings {p} auth={mode} exc {e}', 'ERROR')
        # If all failed, append to backlog for retry
        try:
            append_to_backlog(payload)
            await debug_print('wprest: send_settings failed all; backlogged', 'WARN')
        except Exception:
            pass
        await debug_print(f'wprest: send_settings failed last {last_response}', 'ERROR')
        return False
    except Exception as e:
        await debug_print(f'wprest: send_settings exc {e}', 'ERROR')
        return False

# Addition for OTA polling
async def poll_ota_jobs():
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return []
    try:
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/ota_jobs/{settings.UNIT_ID}', headers=_auth_headers())
        if resp.status_code == 200:
            return resp.json().get('jobs', [])
        else:
            await debug_print(f'Failed to poll OTA jobs: {resp.status_code}', 'ERROR')
            return []
    except Exception as e:
        await debug_print(f'Failed to poll OTA jobs: {e}', 'ERROR')
        return []
