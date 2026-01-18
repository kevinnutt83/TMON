# Apply staged settings safely and persist applied snapshot

try:
    import ujson as json
except Exception:
    import json  # type: ignore

import os
try:
    import utime as time
except Exception:
    import time  # type: ignore

try:
    import uasyncio as asyncio
except Exception:
    asyncio = None

try:
    import gc
except Exception:
    gc = None

import settings

from config_persist import read_json, write_json
from utils import debug_print, persist_suspension_state, persist_unit_name, persist_node_type, persist_wordpress_api_url

def _gc_collect():
    try:
        if gc:
            gc.collect()
    except Exception:
        pass

# Conservative allowlist: key -> coercion function
def _to_bool(v):
    try:
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        return s in ('1', 'true', 'yes', 'on', 'y')
    except Exception:
        return False

def _to_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return int(default)

def _to_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return float(default)

def _to_str(v):
    try:
        return str(v)
    except Exception:
        return ''

ALLOWLIST = {
    'FIELD_DATA_SEND_INTERVAL': _to_int,
    'FIELD_DATA_MAX_BATCH': _to_int,
    'OLED_UPDATE_INTERVAL_S': _to_int,
    'OLED_PAGE_ROTATE_INTERVAL_S': _to_int,
    'OLED_SCROLL_ENABLED': _to_bool,
    'DEVICE_SUSPENDED': _to_bool,
    'WIFI_CONN_RETRIES': _to_int,
    'WIFI_BACKOFF_S': _to_int,
    'WIFI_SIGNAL_SAMPLE_INTERVAL_S': _to_int,
    'GPS_ENABLED': _to_bool,
    'GPS_SOURCE': _to_str,
    'GPS_LAT': _to_float,
    'GPS_LNG': _to_float,
    'NODE_TYPE': _to_str,
    'UNIT_Name': _to_str,
    'WORDPRESS_API_URL': _to_str,
}

# WiFi credentials are sensitive; only allow if explicitly permitted and on base/wifi or unprovisioned
SENSITIVE = {
    'WIFI_SSID': _to_str,
    'WIFI_PASS': _to_str,
}

def _can_apply_wifi_credentials():
    try:
        # allow base/wifi always; allow remote only if explicitly permitted AND not provisioned
        role = str(getattr(settings, 'NODE_TYPE', 'base')).lower()
        if role in ('base', 'wifi'):
            return True
        if bool(getattr(settings, 'ALLOW_REMOTE_WIFI_CREDENTIALS', False)) and not bool(getattr(settings, 'UNIT_PROVISIONED', False)):
            return True
    except Exception:
        pass
    return False

def _apply_key(k, v):
    try:
        # Sensitive keys
        if k in SENSITIVE:
            if not _can_apply_wifi_credentials():
                return False
            val = SENSITIVE[k](v)
            setattr(settings, k, val)
            return True

        # Allowlisted keys
        if k not in ALLOWLIST:
            return False

        val = ALLOWLIST[k](v)
        setattr(settings, k, val)

        # Side effects / persistence for higher-level settings
        try:
            if k == 'DEVICE_SUSPENDED':
                persist_suspension_state(bool(val))
            elif k == 'UNIT_Name':
                persist_unit_name(val)
            elif k == 'NODE_TYPE':
                persist_node_type(val)
            elif k == 'WORDPRESS_API_URL':
                persist_wordpress_api_url(val)
        except Exception:
            pass

        return True
    except Exception:
        return False

def _filter_and_apply(incoming: dict):
    applied = {}
    for k, v in (incoming or {}).items():
        try:
            if _apply_key(k, v):
                applied[k] = getattr(settings, k, None)
        except Exception:
            pass
    return applied

def load_applied_settings_on_boot():
    path = getattr(settings, 'REMOTE_SETTINGS_APPLIED_FILE', '/logs/remote_settings.applied.json')
    try:
        snap = read_json(path, default=None)
        if isinstance(snap, dict) and snap:
            _filter_and_apply(snap)
    except Exception:
        pass
    finally:
        _gc_collect()

def _post_command_confirm(payload):
    """Best-effort: POST a command-complete / ack to the configured WP URL."""
    try:
        try:
            import urequests as requests
        except Exception:
            requests = None
        if not requests:
            return False
        wp = str(getattr(settings, 'WORDPRESS_API_URL', '') or '').rstrip('/')
        if not wp:
            return False
        # Prefer new endpoint; fallback to legacy ack
        try:
            from wprest import _auth_headers
            hdrs = _auth_headers() if callable(_auth_headers) else {}
        except Exception:
            hdrs = {}
        r = None
        try:
            try:
                r = requests.post(wp + '/wp-json/tmon/v1/device/command-complete', headers=hdrs, json=payload, timeout=8)
            except TypeError:
                r = requests.post(wp + '/wp-json/tmon/v1/device/command-complete', headers=hdrs, json=payload)
            sc = getattr(r, 'status_code', 0)
            if sc == 404:
                try:
                    r.close()
                except Exception:
                    pass
                r = requests.post(wp + '/wp-json/tmon/v1/device/ack', headers=hdrs, json=payload)
            return True
        finally:
            try:
                if r:
                    r.close()
            except Exception:
                pass
            _gc_collect()
    except Exception:
        return False

def _append_staged_audit(unit_id, action, details):
    """Append an audit line to LOG_DIR/staged_settings_audit.log for traceability."""
    try:
        p = getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/staged_settings_audit.log'
        with open(p, 'a') as f:
            f.write(json.dumps({
                'ts': int(time.time()),
                'unit_id': unit_id,
                'action': action,
                'details': details
            }) + '\n')
    except Exception:
        pass
    finally:
        _gc_collect()

async def apply_staged_settings_once():
    """Apply staged settings file if present; persist applied snapshot; clear staged file."""
    unit_id = str(getattr(settings, 'UNIT_ID', '') or '')
    staged_path = getattr(settings, 'REMOTE_SETTINGS_STAGED_FILE', '/logs/remote_settings.staged.json')
    applied_path = getattr(settings, 'REMOTE_SETTINGS_APPLIED_FILE', '/logs/remote_settings.applied.json')

    try:
        # If a per-unit staged file exists (base behavior), move it into canonical path first
        try:
            per_unit = getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + f'/device_settings-{unit_id}.json'
            try:
                os.stat(per_unit)
                try:
                    with open(per_unit, 'r') as f:
                        doc = json.loads(f.read() or '{}')
                    write_json(staged_path, doc)
                    try:
                        os.remove(per_unit)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

        try:
            os.stat(staged_path)
        except Exception:
            return False

        incoming = read_json(staged_path, default=None)
        if not isinstance(incoming, dict) or not incoming:
            try:
                os.remove(staged_path)
            except Exception:
                pass
            return False

        applied = _filter_and_apply(incoming)
        if applied:
            write_json(applied_path, applied)
            _append_staged_audit(unit_id, 'applied', {'keys': list(applied.keys())})
            await debug_print(f"settings_apply: applied {list(applied.keys())}", "INFO")
            # Best-effort confirmation to server
            try:
                _post_command_confirm({'unit_id': unit_id, 'type': 'settings_applied', 'applied': list(applied.keys())})
            except Exception:
                pass

        # Clear staged file after attempt
        try:
            os.remove(staged_path)
        except Exception:
            pass

        return bool(applied)
    except Exception as e:
        _append_staged_audit(unit_id, 'error', {'error': str(e)})
        try:
            await debug_print(f"settings_apply: error {e}", "ERROR")
        except Exception:
            pass
        return False
    finally:
        _gc_collect()
        if asyncio:
            await asyncio.sleep(0)

async def settings_apply_loop(interval_s: int = 60):
    while True:
        try:
            await apply_staged_settings_once()
        except Exception:
            pass
        if asyncio:
            await asyncio.sleep(int(interval_s))
        else:
            break
