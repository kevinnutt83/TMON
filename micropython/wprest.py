# TMON Verion 2.00.1d - WordPress REST API integration for device registration, field data upload, and settings sync. Implements multiple auth modes (Basic, Hub token, Read token, Admin token) and endpoint fallbacks for compatibility with different server configurations. Includes error handling and backlogging of failed attempts for later retry.

import gc
try:
    import uasyncio as asyncio
except Exception:
    try:
        import asyncio
    except Exception:
        asyncio = None
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

from utils import (
    debug_print,
    get_machine_id,
    persist_unit_id,
    persist_unit_name,
    persist_custom_settings,
    append_to_backlog,
    read_backlog,
    clear_backlog,
    format_exception,
    log_exception,
)
from config_persist import read_json_safe, write_json_atomic
import settings
import os

WORDPRESS_API_URL = getattr(settings, 'WORDPRESS_API_URL', '')
WORDPRESS_USERNAME = getattr(settings, 'WORDPRESS_USERNAME', None)
WORDPRESS_PASSWORD = getattr(settings, 'WORDPRESS_PASSWORD', None)
LAST_REST_ERROR = {}
REST_ERROR_STREAK = 0
LAST_REST_SUCCESS_TS = 0
LAST_DIAG_PUSH_TS = 0
_DIAG_PUSH_ACTIVE = False


def _current_wp_url():
    try:
        return (getattr(settings, 'WORDPRESS_API_URL', '') or '').strip()
    except Exception:
        return ''

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


def _extract_response(resp, max_chars=400):
    """Best-effort response parser used for resilient logging/decision making."""
    code = 0
    text = ''
    parsed = {}
    try:
        code = int(getattr(resp, 'status_code', 0) or 0)
    except Exception:
        code = 0
    try:
        text = (getattr(resp, 'text', '') or '')[:max_chars]
    except Exception:
        text = ''
    try:
        j = resp.json()
        if isinstance(j, dict):
            parsed = j
        elif isinstance(j, list):
            parsed = {'items': j}
    except Exception:
        try:
            if text:
                j = json.loads(text)
                if isinstance(j, dict):
                    parsed = j
                elif isinstance(j, list):
                    parsed = {'items': j}
        except Exception:
            parsed = {}
    return code, text, parsed


def _now_ts():
    try:
        import utime as _t
        return int(_t.time())
    except Exception:
        return 0


def _set_last_rest_error(operation, code=0, path='', message='', detail=None):
    global LAST_REST_ERROR, REST_ERROR_STREAK
    try:
        ts = _now_ts()
        REST_ERROR_STREAK = int(REST_ERROR_STREAK or 0) + 1
        LAST_REST_ERROR = {
            'operation': operation,
            'code': int(code or 0),
            'path': str(path or ''),
            'message': str(message or ''),
            'detail': detail if isinstance(detail, dict) else {'detail': str(detail or '')},
            'ts': ts,
            'streak': int(REST_ERROR_STREAK or 0),
        }
    except Exception:
        pass


def _mark_rest_success():
    global REST_ERROR_STREAK, LAST_REST_SUCCESS_TS
    try:
        REST_ERROR_STREAK = 0
        LAST_REST_SUCCESS_TS = _now_ts()
    except Exception:
        pass


async def _record_rest_failure(operation, code=0, path='', message='request_failed', detail=None):
    _set_last_rest_error(operation, code, path, message, detail)
    try:
        await _maybe_send_failure_diagnostics(operation, code, path, message)
    except Exception as e:
        await log_exception('_record_rest_failure', e)


async def _maybe_send_failure_diagnostics(operation, code=0, path='', message=''):
    global LAST_DIAG_PUSH_TS, _DIAG_PUSH_ACTIVE, REST_ERROR_STREAK
    try:
        if _DIAG_PUSH_ACTIVE:
            return False
        threshold = int(getattr(settings, 'DIAGNOSTIC_FAILURE_STREAK', 3))
        cooldown_s = int(getattr(settings, 'DIAGNOSTIC_FAILURE_COOLDOWN_S', 300))
        streak = int(REST_ERROR_STREAK or 0)
        if streak < max(1, threshold):
            return False
        now = _now_ts()
        if LAST_DIAG_PUSH_TS and now and (now - int(LAST_DIAG_PUSH_TS)) < max(0, cooldown_s):
            return False
        _DIAG_PUSH_ACTIVE = True
        extra = {
            'trigger': 'rest_failure_streak',
            'operation': str(operation or ''),
            'code': int(code or 0),
            'path': str(path or ''),
            'message': str(message or ''),
            'streak': streak,
        }
        ok = await send_diagnostics_to_wp(extra=extra)
        if ok:
            LAST_DIAG_PUSH_TS = now
            REST_ERROR_STREAK = 0
        return bool(ok)
    except Exception as e:
        await log_exception('_maybe_send_failure_diagnostics', e)
        return False
    finally:
        _DIAG_PUSH_ACTIVE = False


def get_last_rest_error():
    try:
        return dict(LAST_REST_ERROR)
    except Exception:
        return {}

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
                if asyncio:
                    await asyncio.sleep_ms(5)
                if status in (200, 201):
                    _mark_rest_success()
                    await debug_print(f'wprest: register ok via {path}', 'INFO')
                    try:
                        from oled import display_message
                        await display_message("Registered", 2)
                    except Exception:
                        pass
                    return True
                # Log diagnostic per-candidate
                if status == 404:
                    await _record_rest_failure('register_with_wp', status, path, 'endpoint_not_found')
                    await debug_print(f'wprest: register endpoint {path} not found (404)', 'WARN')
                elif status == 401:
                    await _record_rest_failure('register_with_wp', status, path, 'unauthorized')
                    await debug_print(f'wprest: register endpoint {path} returned 401 Unauthorized. Check FIELD_DATA_APP_PASS / credentials.', 'WARN')
                else:
                    await _record_rest_failure('register_with_wp', status, path, 'unexpected_status', {'body': body_snip})
                    await debug_print(f'wprest: register failed {status} for {path} ({body_snip})', 'WARN')
            except Exception as e:
                await _record_rest_failure('register_with_wp', 0, path, 'request_exception', {'exception': format_exception(e)})
                await debug_print(f'wprest: register attempt {path} exception: {format_exception(e)}', 'ERROR')
        await debug_print('wprest: register_all_attempts_failed', 'ERROR')
        try:
            from oled import display_message
            await display_message("Register Failed", 2)
        except Exception:
            pass
        return False
    except Exception as e:
        await _record_rest_failure('register_with_wp', 0, '', 'unhandled_exception', {'exception': format_exception(e)})
        await log_exception('register_with_wp', e)
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
            if asyncio:
                await asyncio.sleep_ms(5)
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
                code, body, parsed = _extract_response(resp)
                if resp:
                    try:
                        resp.close()
                    except Exception:
                        pass
                if asyncio:
                    await asyncio.sleep_ms(5)
                ok_resp = (code in (200, 201)) or (isinstance(parsed, dict) and parsed.get('status') == 'ok')
                if ok_resp:
                    _mark_rest_success()
                    clear_backlog()
                    await debug_print('wprest: field data posted', 'INFO')
                    return True
                if code == 401:
                    await _record_rest_failure('send_data_to_wp', code, '/wp-json/tmon/v1/device/field-data', 'unauthorized')
                    await debug_print('wprest: field data POST returned 401 Unauthorized. Verify FIELD_DATA_APP_PASS / credentials for the site.', 'WARN')
                else:
                    await _record_rest_failure('send_data_to_wp', code, '/wp-json/tmon/v1/device/field-data', 'unexpected_status', {'body': body})
                    await debug_print(f'wprest: send_field_data failed {code} {body}', 'WARN')
            except Exception as e:
                await _record_rest_failure('send_data_to_wp', 0, '/wp-json/tmon/v1/device/field-data', 'request_exception', {'exception': format_exception(e)})
                await debug_print(f'wprest: send_field_data err {format_exception(e)}', 'ERROR')
        if asyncio:
            await asyncio.sleep_ms(5)
        return False
    except Exception as e:
        await _record_rest_failure('send_data_to_wp', 0, '', 'unhandled_exception', {'exception': format_exception(e)})
        await log_exception('send_data_to_wp', e)
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
                    if asyncio:
                        await asyncio.sleep_ms(5)
                    await debug_print(f'wprest: send_settings try {p} auth={mode} -> {code} ({body[:200]})', 'HTTP')
                    last_response = (code, body, mode, p)
                    if code in (200, 201):
                        _mark_rest_success()
                        await debug_print(f'wprest: send_settings succeeded via {p} auth={mode}', 'INFO')
                        try:
                            from oled import display_message
                            await display_message("Settings Sent", 2)
                        except Exception:
                            pass
                        return True
                    elif code not in (404, 405):
                        await _record_rest_failure('send_settings_to_wp', code, p, 'unexpected_status', {'auth': str(mode), 'body': body})
                except Exception as e:
                    await _record_rest_failure('send_settings_to_wp', 0, p, 'request_exception', {'auth': str(mode), 'exception': format_exception(e)})
                    await debug_print(f'wprest: send_settings {p} auth={mode} exc {format_exception(e)}', 'ERROR')
        # If all failed, append to backlog for retry
        try:
            append_to_backlog(payload)
            await debug_print('wprest: send_settings failed all; backlogged', 'WARN')
        except Exception:
            pass
        await debug_print(f'wprest: send_settings failed last {last_response}', 'ERROR')
        return False
    except Exception as e:
        await _record_rest_failure('send_settings_to_wp', 0, '', 'unhandled_exception', {'exception': format_exception(e)})
        await log_exception('send_settings_to_wp', e)
        return False

# Addition for OTA polling
async def poll_ota_jobs():
    wp_url = _current_wp_url()
    if not wp_url:
        await debug_print('No WordPress API URL set', 'ERROR')
        return []
    unit_id = getattr(settings, 'UNIT_ID', '')
    candidate_paths = [
        f'/wp-json/tmon/v1/device/ota_jobs/{unit_id}',
        f'/wp-json/tmon-admin/v1/device/ota-jobs/{unit_id}',
        f'/wp-json/unit-connector/v1/device/ota-jobs/{unit_id}',
    ]
    max_attempts = int(getattr(settings, 'OTA_POLL_MAX_ATTEMPTS', 3))
    base_backoff = float(getattr(settings, 'OTA_POLL_RETRY_BASE_S', 2))
    for attempt in range(max_attempts):
        for p in candidate_paths:
            resp = None
            try:
                url = wp_url.rstrip('/') + p
                try:
                    resp = requests.get(url, headers=_auth_headers(), timeout=8)
                except TypeError:
                    resp = requests.get(url, headers=_auth_headers())
                code, _body_text, parsed = _extract_response(resp, max_chars=1200)
                if code == 200:
                    jobs = parsed.get('jobs', []) if isinstance(parsed, dict) else []
                    try:
                        resp.close()
                    except Exception:
                        pass
                    if asyncio:
                        await asyncio.sleep_ms(5)
                    _mark_rest_success()
                    return jobs if isinstance(jobs, list) else []
                if code not in (404, 405):
                    await _record_rest_failure('poll_ota_jobs', code, p, 'unexpected_status')
                    await debug_print(f'poll_ota_jobs {p} returned {code}', 'WARN')
            except Exception as e:
                await _record_rest_failure('poll_ota_jobs', 0, p, 'request_exception', {'attempt': attempt + 1, 'exception': format_exception(e)})
                await debug_print(f'poll_ota_jobs attempt {attempt+1} path {p} err: {format_exception(e)}', 'ERROR')
            finally:
                try:
                    if resp:
                        resp.close()
                except Exception:
                    pass
                if asyncio:
                    await asyncio.sleep_ms(5)
        if attempt < max_attempts - 1:
            delay = base_backoff * (2 ** attempt)
            if asyncio:
                await asyncio.sleep(delay)
    await debug_print('poll_ota_jobs exhausted retries', 'WARN')
    return []


async def send_ota_job_status(job_id, status, info=None):
    """Report OTA job status back to the hub (best-effort).
       `status` should be one of: 'started','downloaded','applied','failed'.
    """
    try:
        wp_url = _current_wp_url()
        if not wp_url:
            await debug_print('send_ota_job_status: no WP url', 'WARN')
            return False
        payload = {
            'unit_id': getattr(settings, 'UNIT_ID', ''),
            'job_id': job_id,
            'status': status,
            'info': info or {}
        }
        # Candidate endpoint paths
        candidate_paths = [
            '/wp-json/tmon/v1/device/ota-job-status',
            '/wp-json/tmon-admin/v1/device/ota-job-status',
            '/wp-json/unit-connector/v1/device/ota-job-status'
        ]
        max_attempts = int(getattr(settings, 'OTA_STATUS_MAX_ATTEMPTS', 3))
        base_backoff = float(getattr(settings, 'OTA_STATUS_RETRY_BASE_S', 1.5))
        for attempt in range(max_attempts):
            for p in candidate_paths:
                resp = None
                try:
                    url = wp_url.rstrip('/') + p
                    hdrs = _auth_headers()
                    try:
                        resp = requests.post(url, json=payload, headers=hdrs, timeout=8)
                    except TypeError:
                        resp = requests.post(url, json=payload, headers=hdrs)
                    code, _body_text, parsed = _extract_response(resp)
                    if code in (200, 201):
                        _mark_rest_success()
                        await debug_print(f'send_ota_job_status ok via {p}', 'HTTP')
                        return True
                    if code == 202 and isinstance(parsed, dict) and parsed.get('status') in ('queued', 'accepted', 'ok'):
                        _mark_rest_success()
                        await debug_print(f'send_ota_job_status accepted via {p}', 'HTTP')
                        return True
                    if code not in (404, 405):
                        await _record_rest_failure('send_ota_job_status', code, p, 'unexpected_status', {'attempt': attempt + 1})
                        await debug_print(f'send_ota_job_status {p} -> {code}', 'WARN')
                except Exception as e:
                    await _record_rest_failure('send_ota_job_status', 0, p, 'request_exception', {'attempt': attempt + 1, 'exception': format_exception(e)})
                    await debug_print(f'send_ota_job_status attempt {attempt+1} {p} exc: {format_exception(e)}', 'ERROR')
                finally:
                    try:
                        if resp:
                            resp.close()
                    except Exception:
                        pass
                    if asyncio:
                        await asyncio.sleep_ms(5)
            if attempt < max_attempts - 1:
                delay = base_backoff * (2 ** attempt)
                if asyncio:
                    await asyncio.sleep(delay)
        await debug_print('send_ota_job_status all attempts failed', 'WARN')
        return False
    except Exception as e:
        await _record_rest_failure('send_ota_job_status', 0, '', 'unhandled_exception', {'exception': format_exception(e)})
        await log_exception('send_ota_job_status', e)
        return False


async def send_diagnostics_to_wp(extra=None):
    """Push compact diagnostics payload to WP/UC/Admin diagnostic routes."""
    try:
        wp_url = _current_wp_url()
        if not wp_url:
            await debug_print('send_diagnostics_to_wp: no WP url', 'WARN')
            return False
        try:
            import sdata as _sd
        except Exception:
            _sd = None
        payload = {
            'unit_id': getattr(settings, 'UNIT_ID', ''),
            'machine_id': get_machine_id() or '',
            'node_type': getattr(settings, 'NODE_TYPE', ''),
            'firmware_version': getattr(settings, 'FIRMWARE_VERSION', ''),
            'uptime_s': int(getattr(_sd, 'script_runtime', 0) if _sd else 0),
            'free_mem': int(getattr(_sd, 'free_mem', 0) if _sd else 0),
            'wifi_rssi': getattr(_sd, 'wifi_rssi', None) if _sd else None,
            'lora_rssi': getattr(_sd, 'lora_SigStr', None) if _sd else None,
            'error_count': int(getattr(_sd, 'error_count', 0) if _sd else 0),
            'last_error': str(getattr(_sd, 'last_error', '') if _sd else ''),
            'rest_error': get_last_rest_error(),
            'extra': extra or {},
        }
        candidate_paths = [
            '/wp-json/tmon/v1/device/diagnostics',
            '/wp-json/tmon-admin/v1/device/diagnostics',
            '/wp-json/unit-connector/v1/device/diagnostics',
        ]
        max_attempts = int(getattr(settings, 'DIAGNOSTIC_MAX_ATTEMPTS', 2))
        base_backoff = float(getattr(settings, 'DIAGNOSTIC_RETRY_BASE_S', 2))
        for attempt in range(max_attempts):
            for p in candidate_paths:
                resp = None
                try:
                    url = wp_url.rstrip('/') + p
                    try:
                        resp = requests.post(url, json=payload, headers=_auth_headers(), timeout=8)
                    except TypeError:
                        resp = requests.post(url, json=payload, headers=_auth_headers())
                    code, _body_text, parsed = _extract_response(resp)
                    if code in (200, 201):
                        _mark_rest_success()
                        await debug_print(f'send_diagnostics_to_wp ok via {p}', 'HTTP')
                        return True
                    if code == 202 and isinstance(parsed, dict) and parsed.get('status') in ('queued', 'accepted', 'ok'):
                        _mark_rest_success()
                        await debug_print(f'send_diagnostics_to_wp accepted via {p}', 'HTTP')
                        return True
                    if code not in (404, 405):
                        _set_last_rest_error('send_diagnostics_to_wp', code, p, 'unexpected_status', {'attempt': attempt + 1})
                except Exception as e:
                    _set_last_rest_error('send_diagnostics_to_wp', 0, p, 'request_exception', {'attempt': attempt + 1, 'exception': format_exception(e)})
                    await log_exception(f'send_diagnostics_to_wp attempt {attempt+1} {p}', e)
                finally:
                    try:
                        if resp:
                            resp.close()
                    except Exception:
                        pass
                    if asyncio:
                        await asyncio.sleep_ms(5)
            if attempt < max_attempts - 1:
                if asyncio:
                    await asyncio.sleep(base_backoff * (2 ** attempt))
        await debug_print('send_diagnostics_to_wp all attempts failed', 'WARN')
        return False
    except Exception as e:
        _set_last_rest_error('send_diagnostics_to_wp', 0, '', 'unhandled_exception', {'exception': format_exception(e)})
        await log_exception('send_diagnostics_to_wp', e)
        return False


async def fetch_settings_from_wp():
    """Fetch staged settings from WP/UC/Admin and persist for settings_apply loop."""
    try:
        wp_url = _current_wp_url()
        if not wp_url:
            await debug_print('fetch_settings_from_wp: no WP url', 'WARN')
            return False
        unit_id = str(getattr(settings, 'UNIT_ID', '') or '').strip()
        machine_id = str(getattr(settings, 'MACHINE_ID', '') or get_machine_id() or '').strip()
        if not unit_id and not machine_id:
            return False

        candidates = [
            f"/wp-json/tmon/v1/device/settings/{unit_id}",
            f"/wp-json/tmon/v1/device/staged-settings?unit_id={unit_id}",
            f"/wp-json/tmon-admin/v1/device/settings/{unit_id}",
            f"/wp-json/unit-connector/v1/device/settings/{unit_id}",
        ]
        if machine_id:
            candidates.extend([
                f"/wp-json/tmon/v1/device/staged-settings?machine_id={machine_id}",
                f"/wp-json/tmon/v1/device/settings/{machine_id}",
            ])

        for p in candidates:
            resp = None
            try:
                url = wp_url.rstrip('/') + p
                try:
                    resp = requests.get(url, headers=_auth_headers(), timeout=8)
                except TypeError:
                    resp = requests.get(url, headers=_auth_headers())
                code, _body_text, parsed = _extract_response(resp, max_chars=1200)
                if code in (200, 201) and isinstance(parsed, dict):
                    staged = parsed.get('settings')
                    if not isinstance(staged, dict):
                        staged = parsed.get('staged') if isinstance(parsed.get('staged'), dict) else None
                    if not isinstance(staged, dict):
                        continue
                    try:
                        import ujson as _uj
                    except Exception:
                        _uj = json
                    staged_path = getattr(settings, 'REMOTE_SETTINGS_STAGED_FILE', '/logs/remote_settings.staged.json')
                    _ = _uj
                    write_json_atomic(staged_path, staged)
                    _mark_rest_success()
                    await debug_print(f'fetch_settings_from_wp: staged settings fetched via {p}', 'INFO')
                    return True
            except Exception as e:
                await _record_rest_failure('fetch_settings_from_wp', 0, p, 'request_exception', {'exception': format_exception(e)})
            finally:
                try:
                    if resp:
                        resp.close()
                except Exception:
                    pass
                if asyncio:
                    await asyncio.sleep_ms(5)
        return False
    except Exception as e:
        await _record_rest_failure('fetch_settings_from_wp', 0, '', 'unhandled_exception', {'exception': format_exception(e)})
        await log_exception('fetch_settings_from_wp', e)
        return False


async def _post_command_result(job_id, status='done', result=None):
    wp_url = _current_wp_url()
    if not wp_url:
        return False
    if not requests:
        return False
    timeout_s = int(getattr(settings, 'COMMANDS_RESULT_TIMEOUT_S', 8))
    payload = {
        'id': job_id,
        'job_id': job_id,
        'unit_id': getattr(settings, 'UNIT_ID', ''),
        'device_id': getattr(settings, 'UNIT_ID', ''),
        'status': status,
        'result': result or {},
    }
    paths = [
        '/wp-json/tmon/v1/device/command-result',
        '/wp-json/tmon/v1/device/command/confirm',
        '/wp-json/tmon-uc/v1/device/command-result',
        '/wp-json/unit-connector/v1/device/command-result',
    ]
    for p in paths:
        resp = None
        try:
            try:
                resp = requests.post(wp_url.rstrip('/') + p, json=payload, headers=_auth_headers(), timeout=timeout_s)
            except TypeError:
                resp = requests.post(wp_url.rstrip('/') + p, json=payload, headers=_auth_headers())
            code = int(getattr(resp, 'status_code', 0) or 0)
            if code in (200, 201, 202):
                return True
        except Exception:
            pass
        finally:
            try:
                if resp:
                    resp.close()
            except Exception:
                pass
            if asyncio:
                await asyncio.sleep_ms(2)
    return False


async def poll_device_commands():
    """Poll WP/UC command queues and stage safe set_var commands for apply loop."""
    try:
        wp_url = _current_wp_url()
        if not wp_url:
            return False

        unit_id = str(getattr(settings, 'UNIT_ID', '') or '').strip()
        machine_id = str(get_machine_id() or '').strip()
        if not unit_id and not machine_id:
            return False

        body = {
            'unit_id': unit_id,
            'device_id': unit_id,
            'machine_id': machine_id,
            'limit': int(getattr(settings, 'COMMANDS_MAX_PER_POLL', 10)),
        }
        local_limit = int(getattr(settings, 'COMMANDS_MAX_PER_POLL', 10))
        paths = [
            '/wp-json/tmon/v1/device/commands',
            '/wp-json/tmon/v1/admin/device/commands',
            '/wp-json/tmon-uc/v1/device/commands',
            '/wp-json/unit-connector/v1/device/commands',
        ]

        commands = []
        for p in paths:
            resp = None
            try:
                try:
                    resp = requests.post(wp_url.rstrip('/') + p, json=body, headers=_auth_headers(), timeout=8)
                except TypeError:
                    resp = requests.post(wp_url.rstrip('/') + p, json=body, headers=_auth_headers())
                code, _body, parsed = _extract_response(resp, max_chars=2000)
                if code in (200, 201) and parsed is not None:
                    if isinstance(parsed, dict) and isinstance(parsed.get('commands'), list):
                        commands = parsed.get('commands')
                    elif isinstance(parsed, list):
                        commands = parsed
                    if commands:
                        break
            except Exception as e:
                await _record_rest_failure('poll_device_commands', 0, p, 'request_exception', {'exception': format_exception(e)})
            finally:
                try:
                    if resp:
                        resp.close()
                except Exception:
                    pass
                if asyncio:
                    await asyncio.sleep_ms(3)

        if not commands:
            return False

        if local_limit > 0 and len(commands) > local_limit:
            commands = commands[:local_limit]

        staged_updates = {}
        processed_ids = []
        handled_any = False
        for cmd in commands:
            if not isinstance(cmd, dict):
                continue
            ctype = str(cmd.get('type') or cmd.get('command') or '').strip().lower()
            payload = cmd.get('payload') if isinstance(cmd.get('payload'), dict) else (
                cmd.get('params') if isinstance(cmd.get('params'), dict) else (
                    cmd.get('data') if isinstance(cmd.get('data'), dict) else {}
                )
            )
            if ctype == 'set_var':
                key = str(payload.get('key') or '').strip()
                if key:
                    staged_updates[key] = payload.get('value')
                    handled_any = True
                    if cmd.get('id') is not None:
                        processed_ids.append(cmd.get('id'))
            else:
                await debug_print(f'poll_device_commands: unsupported command type {ctype}', 'WARN')
                if cmd.get('id') is not None and bool(getattr(settings, 'COMMAND_ACK_UNSUPPORTED', True)):
                    try:
                        await _post_command_result(
                            cmd.get('id'),
                            'rejected',
                            {
                                'reason': 'unsupported_command_type',
                                'type': ctype or 'unknown',
                            },
                        )
                        handled_any = True
                    except Exception:
                        pass
            if asyncio:
                await asyncio.sleep_ms(1)

        if staged_updates:
            staged_path = getattr(settings, 'REMOTE_SETTINGS_STAGED_FILE', '/logs/remote_settings.staged.json')
            current = read_json_safe(staged_path, {})
            if not isinstance(current, dict):
                current = {}
            for k, v in staged_updates.items():
                current[k] = v
            write_json_atomic(staged_path, current)
            try:
                persist_custom_settings(staged_updates)
            except Exception:
                pass
            await debug_print(f'poll_device_commands: staged {len(staged_updates)} set_var updates', 'INFO')

            # Confirm only commands that were transformed into staged settings.
            confirm_delay = float(getattr(settings, 'COMMAND_CONFIRM_DELAY_S', 0.2))
            for jid in list(dict.fromkeys(processed_ids)):
                try:
                    await _post_command_result(jid, 'done', {'staged': True})
                    if confirm_delay > 0 and asyncio:
                        await asyncio.sleep(confirm_delay)
                except Exception:
                    pass
            _mark_rest_success()
            return True

        if handled_any:
            _mark_rest_success()
            return True
        return False
    except Exception as e:
        await _record_rest_failure('poll_device_commands', 0, '', 'unhandled_exception', {'exception': format_exception(e)})
        await log_exception('poll_device_commands', e)
        return False
