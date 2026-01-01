# Firmware Version: v2.06.0
# wprest.py
# Handles WordPress REST API communication for TMON MicroPython device

import gc
try:
    import urequests as requests
except Exception:
    try:
        import requests  # type: ignore
    except Exception:
        requests = None

import settings
try:
    import ujson as json
except Exception:
    import json

try:
    import uasyncio as asyncio
except Exception:
    import asyncio

from utils import debug_print, get_machine_id, persist_unit_id, persist_unit_name, append_to_backlog, read_backlog, clear_backlog
import os

# Canonical base URL (may be updated by utils.persist_wordpress_api_url / provisioning)
WORDPRESS_API_URL = getattr(settings, 'WORDPRESS_API_URL', '').rstrip('/')

def _auth_headers():
    """Build HTTP auth headers for native WP Application Passwords or basic auth."""
    headers = {
        'User-Agent': 'TMON-Device/' + getattr(settings, 'FIRMWARE_VERSION', 'unknown'),
        'Accept': 'application/json',
    }
    try:
        if getattr(settings, 'FIELD_DATA_USE_APP_PASSWORD', False):
            import ubinascii as _ub
            user = getattr(settings, 'FIELD_DATA_APP_USER', '') or getattr(settings, 'WORDPRESS_USERNAME', '')
            pw = getattr(settings, 'FIELD_DATA_APP_PASS', '') or getattr(settings, 'WORDPRESS_PASSWORD', '')
            if user and pw:
                raw = ('%s:%s' % (user, pw)).encode('utf-8')
                token = _ub.b2a_base64(raw).decode().strip()
                headers['Authorization'] = 'Basic ' + token
    except Exception:
        # Fallback: no auth header
        pass
    return headers

async def register_with_wp():
    """One-time or periodic device registration with the Unit Connector site."""
    if not WORDPRESS_API_URL or not requests:
        return
    try:
        url = WORDPRESS_API_URL + '/wp-json/tmon/v1/device/register'
        payload = {
            'unit_id': getattr(settings, 'UNIT_ID', ''),
            'machine_id': getattr(settings, 'MACHINE_ID', ''),
            'firmware_version': getattr(settings, 'FIRMWARE_VERSION', ''),
            'node_type': getattr(settings, 'NODE_TYPE', ''),
        }
        resp = requests.post(url, json=payload, headers=_auth_headers(), timeout=10)
        try:
            await debug_print(f"wp: register status {getattr(resp, 'status_code', 'NA')}", "WIFI")
        finally:
            try:
                resp.close()
            except Exception:
                pass
    except Exception as e:
        await debug_print(f"wp: register error {e}", "ERROR")

async def send_settings_to_wp():
    """POST a snapshot of current settings (best-effort; mainly for base/wifi nodes)."""
    if not WORDPRESS_API_URL or not requests:
        return
    try:
        url = WORDPRESS_API_URL + '/wp-json/tmon/v1/device/settings'
        data = {
            'unit_id': getattr(settings, 'UNIT_ID', ''),
            'node_type': getattr(settings, 'NODE_TYPE', ''),
            'firmware_version': getattr(settings, 'FIRMWARE_VERSION', ''),
        }
        resp = requests.post(url, json=data, headers=_auth_headers(), timeout=10)
        try:
            await debug_print(f"wp: send_settings status {getattr(resp, 'status_code', 'NA')}", "WIFI")
        finally:
            try:
                resp.close()
            except Exception:
                pass
    except Exception as e:
        await debug_print(f"wp: send_settings error {e}", "ERROR")

async def send_data_to_wp():
    """Placeholder for field-data uploads; base firmware uses utils.send_field_data_log instead."""
    # Intentionally left minimal; real implementation should batch field_data.log.
    await asyncio.sleep(0)

async def poll_ota_jobs():
    """Placeholder OTA job poll; real implementation can query UC for pending OTA tasks."""
    await asyncio.sleep(0)

async def handle_ota_job(job):
    """Handle a single OTA job (stub)."""
    await asyncio.sleep(0)

async def fetch_staged_settings():
    """Fetch staged settings for this unit from UC (stubbed to no-op)."""
    return None

async def poll_device_commands():
    """Poll queued device commands from UC (stubbed to no-op)."""
    await asyncio.sleep(0)

def get_jwt_token():
    """Legacy helper kept for compatibility; returns None (JWT not used)."""
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
        from utils import is_http_allowed_for_node
        if not is_http_allowed_for_node():
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
