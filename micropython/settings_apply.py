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
    # Added allowlist entries for higher-level settings that must be applied
    'NODE_TYPE': _to_str,
    'UNIT_Name': _to_str,
    'WORDPRESS_API_URL': _to_str,
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
            # Special handling: NODE_TYPE changes should be persisted and may immediately alter behavior
            if k == 'NODE_TYPE':
                try:
                    from utils import persist_node_type
                    persist_node_type(coerced)
                    # If role is remote, ensure WiFi disabled (best-effort)
                    if str(coerced).lower() == 'remote':
                        try:
                            from wifi import disable_wifi
                            disable_wifi()
                            settings.ENABLE_WIFI = False
                        except Exception:
                            pass
                except Exception:
                    pass
            # Special handling: WORDPRESS_API_URL should be persisted for device
            if k == 'WORDPRESS_API_URL':
                try:
                    from utils import persist_wordpress_api_url
                    persist_wordpress_api_url(coerced)
                except Exception:
                    pass
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
            # If NODE_TYPE is remote, proactively disable WiFi on boot
            try:
                if getattr(settings, 'NODE_TYPE', '').lower() == 'remote':
                    try:
                        from wifi import disable_wifi
                        disable_wifi()
                        settings.ENABLE_WIFI = False
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass

def _post_command_confirm(payload):
    """Best-effort: POST a command-complete / ack to the configured WP URL."""
    try:
        # import in-function to avoid circular deps on device
        try:
            import urequests as requests
        except Exception:
            import requests
        wp_url = getattr(settings, 'WORDPRESS_API_URL', '') or ''
        if not wp_url:
            return False
        headers = {'Content-Type': 'application/json'}
        # Try primary endpoint
        try:
            resp = requests.post(wp_url.rstrip('/') + '/wp-json/tmon/v1/device/command-complete', headers=headers, json=payload, timeout=8)
            ok = getattr(resp, 'status_code', 0) in (200, 201)
            try:
                if resp: resp.close()
            except Exception:
                pass
            if ok:
                return True
        except Exception:
            pass
        # Fallback to legacy ack endpoint
        try:
            legacy = {'command_id': payload.get('job_id') or payload.get('command_id'), 'ok': payload.get('ok', False), 'result': payload.get('result','')}
            resp2 = requests.post(wp_url.rstrip('/') + '/wp-json/tmon/v1/device/ack', headers=headers, json=legacy, timeout=8)
            ok2 = getattr(resp2, 'status_code', 0) in (200, 201)
            try:
                if resp2: resp2.close()
            except Exception:
                pass
            return ok2
        except Exception:
            return False
    except Exception:
        return False

def _append_staged_audit(unit_id, action, details):
    """Append an audit line to LOG_DIR/staged_settings_audit.log for traceability."""
    try:
        import utime as _t
        ts = int(_t.time()) if hasattr(_t, 'time') else 0
    except Exception:
        ts = 0
    try:
        path = getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/staged_settings_audit.log'
        line = {'ts': ts, 'unit_id': str(unit_id), 'action': action, 'details': details}
        try:
            import ujson as _j
            s = _j.dumps(line)
        except Exception:
            import json as _j
            s = _j.dumps(line)
        with open(path, 'a') as af:
            af.write(s + '\n')
    except Exception:
        pass

async def apply_staged_settings_once():
    staged_path = getattr(settings, 'REMOTE_SETTINGS_STAGED_FILE', '/logs/remote_settings.staged.json')
    applied_path = getattr(settings, 'REMOTE_SETTINGS_APPLIED_FILE', '/logs/remote_settings.applied.json')
    try:
        # If no global staged file, check per-unit staged file written by UC/base
        unit_staged = getattr(settings, 'LOG_DIR', '/logs') + '/device_settings-' + str(getattr(settings, 'UNIT_ID', '')) + '.json'
        staged = None
        try:
            staged = read_json(staged_path, None)
        except Exception:
            staged = None
        if not isinstance(staged, dict):
            # Try unit-specific file
            try:
                staged_unit = read_json(unit_staged, None)
                if isinstance(staged_unit, dict):
                    # persist to canonical staged file to keep behavior consistent
                    try:
                        write_json(staged_path, staged_unit)
                    except Exception:
                        pass
                    staged = staged_unit
            except Exception:
                staged = None
        if not isinstance(staged, dict):
            return False
        # Load previous applied snapshot for diffing (optional)
        prev_applied_meta = read_json(applied_path, None)
        prev_applied = {}
        if isinstance(prev_applied_meta, dict) and isinstance(prev_applied_meta.get('applied'), dict):
            prev_applied = prev_applied_meta.get('applied') or {}
        # Snapshot previous settings for rollback
        prev_snapshot = {}
        for k in ALLOWLIST.keys():
            if hasattr(settings, k):
                prev_snapshot[k] = getattr(settings, k)
        try:
            write_json(getattr(settings,'REMOTE_SETTINGS_PREV_FILE','/logs/remote_settings.prev.json'), prev_snapshot)
        except Exception:
            pass
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
        # Compute diff summary
        try:
            changed_keys = []
            added_keys = []
            for k, v in applied.items():
                if k not in prev_applied:
                    added_keys.append(k)
                elif prev_applied.get(k) != v:
                    changed_keys.append(k)
            ignored_keys = [k for k in (staged or {}).keys() if k not in applied]
            meta['changed_keys'] = changed_keys
            meta['added_keys'] = added_keys
            meta['ignored_keys'] = ignored_keys
        except Exception:
            pass
        write_json(applied_path, meta)
        # Remove staged file to prevent re-apply
        try:
            os.remove(staged_path)
        except Exception:
            pass

        # NEW: Reboot policy: if applied included critical keys, perform a soft reset
        try:
            REBOOT_KEYS = set(['NODE_TYPE','WIFI_SSID','WIFI_PASS','RELAY_PIN1','RELAY_PIN2','ENGINE_ENABLED','ENABLE_OLED','ENABLE_LORA','ENABLE_WIFI'])
            applied_keys = set(list(applied.keys()))
            if applied_keys & REBOOT_KEYS:
                await debug_print('Settings applied include critical keys; performing soft reset', 'PROVISION')
                try:
                    import machine
                    # best-effort single soft reset
                    machine.soft_reset()
                except Exception:
                    # if machine not available (desktop), skip
                    pass
        except Exception:
            pass

        # NEW: If staged included commands, attempt to confirm/clear them on the server
        try:
            cmds = staged.get('commands', []) if isinstance(staged, dict) else []
            confirmed = 0
            for c in (cmds or []):
                try:
                    job_id = c.get('id') or c.get('job_id') or c.get('command_id')
                    payload = {'job_id': job_id, 'ok': True, 'result': 'applied_via_staged_settings'}
                    if job_id:
                        if _post_command_confirm(payload):
                            confirmed += 1
                        else:
                            # best-effort only; log failure
                            await debug_print(f'Failed to confirm staged command {job_id}', 'WARN')
                except Exception:
                    pass
            # Append audit entry for applied settings + command confirms
            try:
                _append_staged_audit(getattr(settings, 'UNIT_ID', ''), 'apply', {'applied_keys': list(applied.keys()), 'commands_confirmed': confirmed, 'added': meta.get('added_keys',[]), 'changed': meta.get('changed_keys',[]), 'ignored': meta.get('ignored_keys',[])})
            except Exception:
                pass
        except Exception:
            pass

        try:
            msg = 'Settings applied: ' \
                  + ('a=' + ','.join(meta.get('added_keys', [])) if meta.get('added_keys') else 'a=0') \
                  + ' ' \
                  + ('c=' + ','.join(meta.get('changed_keys', [])) if meta.get('changed_keys') else 'c=0') \
                  + ' ' \
                  + ('i=' + ','.join(meta.get('ignored_keys', [])) if meta.get('ignored_keys') else 'i=0')
        except Exception:
            msg = 'Settings: staged settings applied'
        await debug_print(msg, 'INFO')
        return True
    except Exception as e:
        # Rollback to previous snapshot
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
        await debug_print('Settings: apply failed, rollback executed: %s' % e, 'ERROR')
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
