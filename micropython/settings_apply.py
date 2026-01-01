# Apply staged settings safely and persist applied snapshot

try:
    import urequests as requests  # optional, only for future confirm hooks
except Exception:
    try:
        import requests  # type: ignore
    except Exception:
        requests = None

try:
    import settings
except Exception:
    settings = None

from config_persist import read_json, write_json
from utils import debug_print, persist_suspension_state

# --- Coercion helpers ---

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

# Conservative allowlist: key -> coercion function
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
    # Higher-level settings that must be applied
    'NODE_TYPE': _to_str,
    'UNIT_Name': _to_str,
    'WORDPRESS_API_URL': _to_str,
}

# WiFi credentials are sensitive; only allow if explicitly permitted and on base/unprovisioned
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
    """Apply a single key/value to settings when allowed. Returns True if applied."""
    if settings is None:
        return False
    try:
        # Special handling: DEVICE_SUSPENDED must also persist flag
        if k == 'DEVICE_SUSPENDED':
            val = _to_bool(v)
            try:
                setattr(settings, 'DEVICE_SUSPENDED', val)
            except Exception:
                pass
            try:
                persist_suspension_state(val)
            except Exception:
                pass
            return True

        # General allowlist
        if k in ALLOWLIST:
            coerce = ALLOWLIST[k]
            val = coerce(v)
            try:
                setattr(settings, k, val)
                return True
            except Exception:
                return False

        # Sensitive WiFi credentials
        if k in SENSITIVE and _can_apply_wifi_credentials():
            coerce = SENSITIVE[k]
            val = coerce(v)
            try:
                setattr(settings, k, val)
                return True
            except Exception:
                return False
    except Exception:
        return False
    return False

def _filter_and_apply(incoming: dict):
    """Filter incoming dict through allowlist and apply to settings."""
    applied = {}
    for k, v in (incoming or {}).items():
        try:
            if _apply_key(k, v):
                applied[k] = v
        except Exception:
            # keep going on individual failures
            pass
    return applied

def load_applied_settings_on_boot():
    """Re-apply previously applied snapshot (idempotent)."""
    if settings is None:
        return
    path = getattr(settings, 'REMOTE_SETTINGS_APPLIED_FILE', '/logs/remote_settings.applied.json')
    try:
        data = read_json(path, None)
        if isinstance(data, dict):
            snap = data.get('applied') if isinstance(data.get('applied'), dict) else data
            if isinstance(snap, dict):
                _filter_and_apply(snap)
    except Exception:
        pass

async def apply_staged_settings_once():
    """Apply staged settings from file once, then move them to applied snapshot."""
    if settings is None:
        return False
    staged_path = getattr(settings, 'REMOTE_SETTINGS_STAGED_FILE', '/logs/remote_settings.staged.json')
    applied_path = getattr(settings, 'REMOTE_SETTINGS_APPLIED_FILE', '/logs/remote_settings.applied.json')
    try:
        # Prefer per-unit staged file if present
        unit_id = str(getattr(settings, 'UNIT_ID', ''))
        per_unit = getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/device_settings-' + unit_id + '.json'
        staged = read_json(per_unit, None)
        if not isinstance(staged, dict):
            staged = read_json(staged_path, None)
        if not isinstance(staged, dict) or not staged:
            return False

        await debug_print('settings_apply: staged settings found, applying', 'PROVISION')
        applied = _filter_and_apply(staged)

        meta = {
            'applied': applied,
            'ts': None,
        }
        try:
            write_json(applied_path, meta)
        except Exception:
            pass

        # Remove staged files so we don't re-apply
        import os
        for p in (staged_path, per_unit):
            try:
                os.remove(p)
            except Exception:
                pass

        await debug_print('settings_apply: applied %d keys' % len(applied), 'PROVISION')
        return True
    except Exception as e:
        await debug_print('settings_apply: failed apply_staged_settings_once: %s' % e, 'ERROR')
        return False

async def settings_apply_loop(interval_s: int = 60):
    """Periodically check for staged settings and apply them."""
    while True:
        try:
            await apply_staged_settings_once()
        except Exception as e:
            try:
                await debug_print('settings_apply_loop error: %s' % e, 'ERROR')
            except Exception:
                pass
        # Honor settings-controlled interval if present
        try:
            delay = int(interval_s or 60)
        except Exception:
            delay = 60
        import uasyncio as _a
        await _a.sleep(delay)
