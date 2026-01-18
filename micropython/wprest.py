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

# Export for legacy imports
WORDPRESS_API_URL = _base_url()

def _auth_headers():
    """Basic auth via WP Application Password, if configured."""
    try:
        user = str(getattr(settings, 'WORDPRESS_APP_USER', '') or '')
        pwd = str(getattr(settings, 'WORDPRESS_APP_PASS', '') or '')
        if not user or not pwd:
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

def _req(method, path, payload=None, timeout_s=10):
    if not requests:
        return None
    url = _base_url() + path
    hdrs = _auth_headers()
    try:
        if method == 'GET':
            try:
                r = requests.get(url, headers=hdrs, timeout=timeout_s)
            except TypeError:
                r = requests.get(url, headers=hdrs)
        else:
            try:
                r = requests.post(url, headers=hdrs, json=payload, timeout=timeout_s)
            except TypeError:
                r = requests.post(url, headers=hdrs, json=payload)
        return r
    except Exception:
        return None

async def register_with_wp():
    if not _base_url():
        return False
    body = {
        'unit_id': getattr(settings, 'UNIT_ID', ''),
        'unit_name': getattr(settings, 'UNIT_Name', ''),
        'node_type': getattr(settings, 'NODE_TYPE', ''),
        'firmware_version': getattr(settings, 'FIRMWARE_VERSION', ''),
    }
    r = None
    try:
        r = _req('POST', '/wp-json/tmon/v1/device/register', payload=body, timeout_s=int(getattr(settings, 'HTTP_TIMEOUT_S', 10)))
        ok = bool(r) and getattr(r, 'status_code', 0) in (200, 201)
        return ok
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        await _sleep0()

async def heartbeat_ping():
    if not _base_url():
        return False
    r = None
    try:
        r = _req('POST', '/wp-json/tmon/v1/device/heartbeat', payload={'unit_id': getattr(settings, 'UNIT_ID', '')}, timeout_s=8)
        return bool(r) and getattr(r, 'status_code', 0) in (200, 201)
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        await _sleep0()

async def send_settings_to_wp():
    if not _base_url():
        return False
    # Keep payload bounded
    body = {
        'unit_id': getattr(settings, 'UNIT_ID', ''),
        'unit_name': getattr(settings, 'UNIT_Name', ''),
        'node_type': getattr(settings, 'NODE_TYPE', ''),
        'settings': {
            'FIRMWARE_VERSION': getattr(settings, 'FIRMWARE_VERSION', ''),
            'PLAN': getattr(settings, 'PLAN', ''),
        }
    }
    r = None
    try:
        r = _req('POST', '/wp-json/tmon/v1/device/settings', payload=body, timeout_s=12)
        return bool(r) and getattr(r, 'status_code', 0) in (200, 201)
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        await _sleep0()

async def fetch_settings_from_wp():
    if not _base_url():
        return None
    unit_id = getattr(settings, 'UNIT_ID', '')
    r = None
    try:
        r = _req('GET', f'/wp-json/tmon/v1/device/settings/{unit_id}', timeout_s=12)
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
    """Upload the current field-data log (base/wifi nodes)."""
    if not _base_url():
        return False
    try:
        from utils import _field_data_path
        path = _field_data_path()
    except Exception:
        return False
    # Stream lines in a bounded batch
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
        r = _req('POST', '/wp-json/tmon/v1/device/field-data-batch', payload=body, timeout_s=20)
        ok = bool(r) and getattr(r, 'status_code', 0) in (200, 201)
        # On success, truncate by rewriting remaining content (best-effort, bounded)
        if ok:
            try:
                # rewrite remainder (read-rest bounded)
                rest = []
                with open(path, 'r') as f:
                    # skip what we sent
                    for _ in range(len(lines)):
                        f.readline()
                    for _ in range(int(getattr(settings, 'FIELD_DATA_REWRITE_MAX_LINES', 2000))):
                        ln = f.readline()
                        if not ln:
                            break
                        rest.append(ln)
                with open(path, 'w') as f:
                    for ln in rest:
                        f.write(ln)
            except Exception:
                pass
        return ok
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        await _sleep0()

async def poll_ota_jobs():
    # Minimal stub; OTA apply is handled by ota.py in this repo snapshot.
    return True

async def fetch_staged_settings():
    """GET staged settings; save to staged file for settings_apply loop."""
    if not _base_url():
        return None
    unit_id = getattr(settings, 'UNIT_ID', '')
    r = None
    try:
        r = _req('GET', f'/wp-json/tmon/v1/device/staged-settings?unit_id={unit_id}', timeout_s=15)
        if not r or getattr(r, 'status_code', 0) != 200:
            return None
        try:
            doc = r.json()
        except Exception:
            doc = json.loads(getattr(r, 'text', '') or '{}')
        # Save staged payload (best-effort)
        try:
            from config_persist import write_json
            staged_path = getattr(settings, 'REMOTE_SETTINGS_STAGED_FILE', '/logs/remote_settings.staged.json')
            if isinstance(doc, dict) and doc:
                write_json(staged_path, doc)
        except Exception:
            pass
        return doc
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        await _sleep0()

async def poll_device_commands():
    """Poll queued commands and execute via handle_device_command()."""
    if not _base_url():
        return False
    unit_id = getattr(settings, 'UNIT_ID', '')
    r = None
    try:
        r = _req('GET', f'/wp-json/tmon/v1/device/commands?unit_id={unit_id}', timeout_s=12)
        if not r or getattr(r, 'status_code', 0) != 200:
            return False
        try:
            doc = r.json()
        except Exception:
            doc = json.loads(getattr(r, 'text', '') or '{}')
        cmds = doc.get('commands') if isinstance(doc, dict) else None
        if not cmds:
            return True
        for c in cmds:
            try:
                await handle_device_command(c)
            except Exception:
                pass
        return True
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        await _sleep0()

async def handle_device_command(cmd):
    """Execute one command dict; best-effort ack to WP."""
    if not isinstance(cmd, dict):
        return False
    name = cmd.get('command') or cmd.get('name')
    params = cmd.get('params') or {}
    ok = False
    try:
        if name == 'toggle_relay':
            from relay import toggle_relay
            await toggle_relay(str(params.get('relay', '')), str(params.get('state', 'off')), str(params.get('runtime', '0')))
            ok = True
        elif name == 'set_message':
            try:
                import sdata
                sdata.last_message = str(params.get('message', ''))[:32]
            except Exception:
                pass
            ok = True
        else:
            ok = False
    finally:
        # best-effort completion post
        try:
            await _post_command_complete(cmd, ok)
        except Exception:
            pass
        _gc_collect()
        await _sleep0()
    return ok

async def _post_command_complete(cmd, ok):
    if not _base_url():
        return
    r = None
    try:
        body = {'unit_id': getattr(settings, 'UNIT_ID', ''), 'command': cmd, 'ok': bool(ok)}
        r = _req('POST', '/wp-json/tmon/v1/device/command-complete', payload=body, timeout_s=10)
        if not r or getattr(r, 'status_code', 0) not in (200, 201, 404):
            # fallback legacy endpoint
            r2 = None
            try:
                r2 = _req('POST', '/wp-json/tmon/v1/device/ack', payload=body, timeout_s=10)
            finally:
                try:
                    if r2:
                        r2.close()
                except Exception:
                    pass
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
