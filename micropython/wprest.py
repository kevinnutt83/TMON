# Firmware Version: v2.06.0
# wprest.py
# Handles WordPress REST API communication for TMON MicroPython device

try:
    import urequests as requests
except Exception:
    requests = None

try:
    import uasyncio as asyncio
except Exception:
    asyncio = None

try:
    import ujson as json
except Exception:
    import json  # type: ignore

try:
    import gc
except Exception:
    gc = None

import settings

def _gc_collect():
    try:
        if gc:
            gc.collect()
    except Exception:
        pass

def _base_url():
    return str(getattr(settings, 'WORDPRESS_API_URL', '') or '').rstrip('/')

WORDPRESS_API_URL = _base_url()

def _auth_headers():
    # Support Application Password basic auth (if configured)
    try:
        user = str(getattr(settings, 'WORDPRESS_USERNAME', '') or getattr(settings, 'WORDPRESS_APP_USER', '') or '')
        pwd = str(getattr(settings, 'WORDPRESS_PASSWORD', '') or getattr(settings, 'WORDPRESS_APP_PASS', '') or '')
        if not (user and pwd):
            return {}
        try:
            import ubinascii
            token = ubinascii.b2a_base64((user + ':' + pwd).encode()).decode().strip()
        except Exception:
            import binascii
            token = binascii.b2a_base64((user + ':' + pwd).encode()).decode().strip()
        return {'Authorization': 'Basic ' + token}
    except Exception:
        return {}

async def _sleep0():
    if asyncio:
        await asyncio.sleep(0)

def get_jwt_token(*_a, **_kw):
    # Legacy import used by field_data_test.py; keep as stub.
    return None

async def register_with_wp():
    if not requests or not _base_url():
        return False
    r = None
    try:
        body = {
            'unit_id': getattr(settings, 'UNIT_ID', ''),
            'unit_name': getattr(settings, 'UNIT_Name', ''),
            'node_type': getattr(settings, 'NODE_TYPE', ''),
            'firmware_version': getattr(settings, 'FIRMWARE_VERSION', ''),
        }
        try:
            r = requests.post(_base_url() + '/wp-json/tmon/v1/device/register', headers=_auth_headers(), json=body, timeout=10)
        except TypeError:
            r = requests.post(_base_url() + '/wp-json/tmon/v1/device/register', headers=_auth_headers(), json=body)
        return bool(r) and getattr(r, 'status_code', 0) in (200, 201)
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        await _sleep0()

async def heartbeat_ping():
    if not requests or not _base_url():
        return False
    r = None
    try:
        body = {'unit_id': getattr(settings, 'UNIT_ID', '')}
        r = requests.post(_base_url() + '/wp-json/tmon/v1/device/heartbeat', headers=_auth_headers(), json=body)
        return bool(r) and getattr(r, 'status_code', 0) in (200, 201)
    except Exception:
        return False
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        await _sleep0()

async def send_settings_to_wp():
    if not requests or not _base_url():
        return False
    r = None
    try:
        body = {'unit_id': getattr(settings, 'UNIT_ID', ''), 'settings': {}}
        r = requests.post(_base_url() + '/wp-json/tmon/v1/device/settings', headers=_auth_headers(), json=body)
        return bool(r) and getattr(r, 'status_code', 0) in (200, 201)
    except Exception:
        return False
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        await _sleep0()

async def fetch_settings_from_wp():
    if not requests or not _base_url():
        return None
    r = None
    try:
        uid = getattr(settings, 'UNIT_ID', '')
        r = requests.get(_base_url() + f'/wp-json/tmon/v1/device/settings/{uid}', headers=_auth_headers())
        if not r or getattr(r, 'status_code', 0) != 200:
            return None
        try:
            return r.json()
        except Exception:
            try:
                return json.loads(getattr(r, 'text', '') or '{}')
            except Exception:
                return None
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        await _sleep0()

async def send_data_to_wp():
    """Upload a bounded batch of field_data.log lines."""
    if not requests or not _base_url():
        return False
    path = getattr(settings, 'FIELD_DATA_LOG', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/field_data.log')
    max_lines = int(getattr(settings, 'FIELD_DATA_MAX_BATCH', 50))
    lines = []
    try:
        with open(path, 'r') as f:
            for _ in range(max_lines):
                ln = f.readline()
                if not ln:
                    break
                lines.append(ln.strip())
    except Exception:
        return False
    if not lines:
        return True
    r = None
    try:
        body = {'unit_id': getattr(settings, 'UNIT_ID', ''), 'lines': lines}
        r = requests.post(_base_url() + '/wp-json/tmon/v1/device/field-data-batch', headers=_auth_headers(), json=body)
        return bool(r) and getattr(r, 'status_code', 0) in (200, 201)
    except Exception:
        return False
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        await _sleep0()

async def poll_ota_jobs():
    return True

async def fetch_staged_settings():
    if not requests or not _base_url():
        return None
    r = None
    try:
        uid = getattr(settings, 'UNIT_ID', '')
        r = requests.get(_base_url() + f'/wp-json/tmon/v1/device/staged-settings?unit_id={uid}', headers=_auth_headers())
        if not r or getattr(r, 'status_code', 0) != 200:
            return None
        try:
            return r.json()
        except Exception:
            try:
                return json.loads(getattr(r, 'text', '') or '{}')
            except Exception:
                return None
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        await _sleep0()

async def poll_device_commands():
    # Minimal: fetch and ignore if endpoint exists
    if not requests or not _base_url():
        return False
    r = None
    try:
        uid = getattr(settings, 'UNIT_ID', '')
        r = requests.get(_base_url() + f'/wp-json/tmon/v1/device/commands?unit_id={uid}', headers=_auth_headers())
        return bool(r) and getattr(r, 'status_code', 0) == 200
    except Exception:
        return False
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        await _sleep0()
