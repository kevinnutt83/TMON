# TMON v2.01.0 - Settings application module
# Safely applies staged settings from server with conservative allowlist.
# Persists snapshot, computes diffs, handles critical changes with soft reset.
# WordPress API calls untouched. Added GC calls for stability.
import uasyncio as asyncio
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
from utils import maybe_gc

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
    'NODE_TYPE': _to_str,
    'UNIT_Name': _to_str,
    'WORDPRESS_API_URL': _to_str,
    'APP_MODE': _to_str,
    'LORA_SYNC_RATE': _to_int,
    'FIELD_DATA_SEND_INTERVAL': _to_int,
}

SENSITIVE = {
    'WIFI_SSID': _to_str,
    'WIFI_PASS': _to_str,
}

def _can_apply_wifi_credentials():
    try:
        if getattr(settings, 'NODE_TYPE', 'base') == 'base':
            return True
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
        if k in ALLOWLIST:
            coerced = ALLOWLIST[k](v)
            setattr(settings, k, coerced)
            if k == 'NODE_TYPE':
                try:
                    from utils import persist_node_type
                    persist_node_type(coerced)
                    if str(coerced).lower() == 'remote':
                        try:
                            from wifi import disable_wifi
                            disable_wifi()
                            settings.ENABLE_WIFI = False
                        except Exception:
                            pass
                except Exception:
                    pass
            if k == 'WORDPRESS_API_URL':
                try:
                    from utils import persist_wordpress_api_url
                    persist_wordpress_api_url(coerced)
                except Exception:
                    pass
            return True
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
            if getattr(settings, 'NODE_TYPE', '').lower() == 'remote':
                try:
                    from wifi import disable_wifi
                    disable_wifi()
                    settings.ENABLE_WIFI = False
                except Exception:
                    pass
        maybe_gc("settings_apply_boot", min_interval_ms=2000, mem_free_below=55 * 1024)
    except Exception:
        pass

async def apply_staged_settings_once():
    staged_path = getattr(settings, 'REMOTE_SETTINGS_STAGED_FILE', '/logs/remote_settings.staged.json')
    applied_path = getattr(settings, 'REMOTE_SETTINGS_APPLIED_FILE', '/logs/remote_settings.applied.json')
    try:
        unit_staged = getattr(settings, 'LOG_DIR', '/logs') + '/device_settings-' + str(getattr(settings, 'UNIT_ID', '')) + '.json'
        staged = None
        try:
            staged = read_json(staged_path, None)
        except Exception:
            staged = None
        if not isinstance(staged, dict):
            try:
                staged_unit = read_json(unit_staged, None)
                if isinstance(staged_unit, dict):
                    try:
                        write_json(staged_path, staged_unit)
                    except Exception:
                        pass
                    staged = staged_unit
            except Exception:
                staged = None
        if not isinstance(staged, dict):
            return False

        prev_applied = {}
        try:
            prev_meta = read_json(applied_path, None)
            if isinstance(prev_meta, dict) and isinstance(prev_meta.get('applied'), dict):
                prev_applied = prev_meta.get('applied') or {}
        except Exception:
            pass

        prev_snapshot = {}
        for k in ALLOWLIST.keys():
            if hasattr(settings, k):
                prev_snapshot[k] = getattr(settings, k)
        try:
            write_json(getattr(settings,'REMOTE_SETTINGS_PREV_FILE','/logs/remote_settings.prev.json'), prev_snapshot)
        except Exception:
            pass

        applied = _filter_and_apply(staged)

        meta = {'applied': applied, 'ts': int(time.time()) if 'time' in globals() else 0}
        try:
            changed_keys = [k for k, v in applied.items() if k not in prev_applied or prev_applied.get(k) != v]
            added_keys = [k for k in applied if k not in prev_applied]
            ignored_keys = [k for k in (staged or {}) if k not in applied]
            meta['changed_keys'] = changed_keys
            meta['added_keys'] = added_keys
            meta['ignored_keys'] = ignored_keys
        except Exception:
            pass

        write_json(applied_path, meta)
        try:
            os.remove(staged_path)
        except Exception:
            pass

        maybe_gc("settings_apply_once", min_interval_ms=3000, mem_free_below=55 * 1024)

        # Reboot on critical changes
        REBOOT_KEYS = {'NODE_TYPE', 'WIFI_SSID', 'WIFI_PASS', 'RELAY_PIN1', 'RELAY_PIN2', 'ENGINE_ENABLED', 'ENABLE_OLED', 'ENABLE_LORA', 'ENABLE_WIFI'}
        if set(applied.keys()) & REBOOT_KEYS:
            await debug_print('Settings applied include critical keys; performing soft reset', 'PROVISION')
            try:
                machine.soft_reset()
            except Exception:
                pass

        await debug_print('Settings: staged settings applied', 'INFO')
        return True
    except Exception as e:
        # Rollback
        try:
            prev = read_json(getattr(settings,'REMOTE_SETTINGS_PREV_FILE','/logs/remote_settings.prev.json'), {})
            if isinstance(prev, dict):
                for k, v in prev.items():
                    try:
                        setattr(settings, k, v)
                    except Exception:
                        pass
        except Exception:
            pass
        await debug_print(f'Settings: apply failed, rollback executed: {e}', 'ERROR')
        return False

async def settings_apply_loop(interval_s: int = 60):
    while True:
        try:
            await apply_staged_settings_once()
        except Exception:
            pass
        await asyncio.sleep(interval_s)

# ===================== End of settings_apply.py =====================
