# Apply staged settings safely and persist applied snapshot
try:
    import ujson as json
except Exception:
    import json

try:
    import uos as os
except Exception:
    import os

import settings
from config_persist import read_json, write_json
from utils import debug_print, persist_suspension_state

# Conservative allowlist: key -> coercion function
def _to_bool(v):
    try:
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        s = str(v).strip().lower()
        return s in ('1', 'true', 'yes', 'on')
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
}

# WiFi credentials are sensitive; only allow if explicitly permitted and on base or unprovisioned
SENSITIVE = {
    'WIFI_SSID': _to_str,
    'WIFI_PASS': _to_str,
}

def _can_apply_wifi_credentials():
    try:
        if getattr(settings, 'NODE_TYPE', 'base') == 'base':
            return True
        # For remotes, only if not yet provisioned
        return not bool(getattr(settings, 'UNIT_PROVISIONED', False))
    except Exception:
        return False

def _apply_key(k, v):
    try:
        if k == 'DEVICE_SUSPENDED':
            setattr(settings, k, bool(_to_bool(v)))
            try:
                persist_suspension_state(getattr(settings, k))
            except Exception:
                pass
            return True
        # general allowlist
        if k in ALLOWLIST:
            coerced = ALLOWLIST[k](v)
            setattr(settings, k, coerced)
            return True
        # sensitive items
        if k in SENSITIVE and _can_apply_wifi_credentials():
            coerced = SENSITIVE[k](v)
            setattr(settings, k, coerced)
            return True
    except Exception:
        return False
    return False

def _filter_and_apply(incoming: dict):
    applied = {}
    for k, v in (incoming or {}).items():
        try:
            if _apply_key(k, v):
                applied[k] = getattr(settings, k)
        except Exception:
            pass
    return applied

def load_applied_settings_on_boot():
    path = getattr(settings, 'REMOTE_SETTINGS_APPLIED_FILE', '/logs/remote_settings.applied.json')
    try:
        data = read_json(path, None)
        if isinstance(data, dict):
            _filter_and_apply(data)
    except Exception:
        pass

async def apply_staged_settings_once():
    staged_path = getattr(settings, 'REMOTE_SETTINGS_STAGED_FILE', '/logs/remote_settings.staged.json')
    applied_path = getattr(settings, 'REMOTE_SETTINGS_APPLIED_FILE', '/logs/remote_settings.applied.json')
    try:
        # Load staged
        staged = read_json(staged_path, None)
        if not isinstance(staged, dict):
            return False
        applied = _filter_and_apply(staged)
        # Persist applied snapshot
        meta = {
            'applied': applied,
            'ts': None,
        }
        try:
            import utime as _t
            meta['ts'] = int(_t.time())
        except Exception:
            pass
        write_json(applied_path, meta)
        # Remove staged file to prevent re-apply
        try:
            os.remove(staged_path)
        except Exception:
            pass
        await debug_print('Settings: staged settings applied', 'INFO')
        return True
    except Exception as e:
        await debug_print('Settings: apply failed: %s' % e, 'ERROR')
        return False

async def settings_apply_loop(interval_s: int = 60):
    # Periodically check for staged settings and apply
    while True:
        try:
            await apply_staged_settings_once()
        except Exception:
            pass
        try:
            import uasyncio as _a
            await _a.sleep(int(interval_s))
        except Exception:
            break
