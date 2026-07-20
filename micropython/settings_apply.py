# TMON Verion 2.00.1d - Settings application module for TMON MicroPython firmware. This module is responsible for safely applying staged settings received from the server, with a conservative allowlist of configurable parameters and coercion functions. It includes logic to persist applied settings, compute diffs from previous applied snapshots, and perform a soft reset if critical settings are changed. The module also includes safeguards for applying sensitive WiFi credentials only when appropriate, and attempts to confirm applied commands back to the server. GC management is included to ensure stability during potentially heavy operations on resource-constrained hardware.

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
from config_persist import read_json, read_json_safe, write_json, write_json_atomic
from utils import debug_print, persist_suspension_state, load_persisted_custom_settings, record_exception, log_exception
# NEW: GC helper
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
    'FIELD_DATA_MAX_ATTEMPTS': _to_int,
    'FIELD_DATA_RETRY_BASE_S': _to_int,
    'FIELD_DATA_MAX_BACKOFF_S': _to_int,
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
    'LORA_MAX_RETRIES': _to_int,
    'LORA_RETRY_BASE_DELAY_S': _to_int,
    'LORA_MAX_BACKOFF_S': _to_int,
    'LORA_HEARTBEAT_INTERVAL_S': _to_int,
    'LORA_MISSED_SYNC_THRESHOLD': _to_int,
    'LORA_CRC_ENABLED': _to_bool,
    'DIAGNOSTIC_SEND_INTERVAL_S': _to_int,
    'DIAGNOSTIC_MAX_ATTEMPTS': _to_int,
    'DIAGNOSTIC_RETRY_BASE_S': _to_int,
    'DIAGNOSTIC_FAILURE_STREAK': _to_int,
    'DIAGNOSTIC_FAILURE_COOLDOWN_S': _to_int,
    'ENABLE_DIAGNOSTICS_UPLOAD': _to_bool,
    'COMMANDS_POLL_INTERVAL_S': _to_int,
    'COMMANDS_POLL_JITTER_S': _to_float,
    'COMMANDS_MAX_PER_POLL': _to_int,
    'COMMAND_CONFIRM_DELAY_S': _to_float,
    'COMMANDS_RESULT_TIMEOUT_S': _to_int,
    'COMMAND_ACK_UNSUPPORTED': _to_bool,
    # Added allowlist entries for higher-level settings that must be applied
    'NODE_TYPE': _to_str,
    'UNIT_Name': _to_str,
    'WORDPRESS_API_URL': _to_str,
    'LORA_NETWORK_NAME': _to_str,
    'LORA_NETWORK_PASSWORD': _to_str,
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
    except Exception as e:
        record_exception('settings_apply._can_apply_wifi_credentials', e, status='WARN')
        return False

def _apply_key(k, v):
    try:
        if k == 'DEVICE_SUSPENDED':
            setattr(settings, k, bool(_to_bool(v)))
            try:
                persist_suspension_state(getattr(settings, k))
            except Exception as e:
                record_exception('settings_apply._apply_key.persist_suspension_state', e, status='WARN')
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
                        except Exception as e:
                            record_exception('settings_apply._apply_key.disable_wifi', e, status='WARN')
                except Exception as e:
                    record_exception('settings_apply._apply_key.persist_node_type', e, status='WARN')
            # Special handling: WORDPRESS_API_URL should be persisted for device
            if k == 'WORDPRESS_API_URL':
                try:
                    from utils import persist_wordpress_api_url
                    persist_wordpress_api_url(coerced)
                except Exception as e:
                    record_exception('settings_apply._apply_key.persist_wordpress_api_url', e, status='WARN')
            return True
        # sensitive items
        if k in SENSITIVE and _can_apply_wifi_credentials():
            coerced = SENSITIVE[k](v)
            setattr(settings, k, coerced)
            return True
    except Exception as e:
        record_exception('settings_apply._apply_key', e)
        return False
    return False

def _filter_and_apply(incoming: dict):
    applied = {}
    for k, v in (incoming or {}).items():
        try:
            if _apply_key(k, v):
                applied[k] = getattr(settings, k)
        except Exception as e:
            record_exception(f'settings_apply._filter_and_apply.{k}', e, status='WARN')
    return applied

def load_applied_settings_on_boot():
    path = getattr(settings, 'REMOTE_SETTINGS_APPLIED_FILE', '/logs/remote_settings.applied.json')
    try:
        data = read_json_safe(path, None)
        if isinstance(data, dict):
            _filter_and_apply(data)
            try:
                load_persisted_custom_settings()
            except Exception as e:
                record_exception('settings_apply.load_applied_settings_on_boot.load_custom_settings', e, status='WARN')
            # If NODE_TYPE is remote, proactively disable WiFi on boot
            try:
                if getattr(settings, 'NODE_TYPE', '').lower() == 'remote':
                    try:
                        from wifi import disable_wifi
                        disable_wifi()
                        settings.ENABLE_WIFI = False
                    except Exception as e:
                        record_exception('settings_apply.load_applied_settings_on_boot.disable_wifi', e, status='WARN')
            except Exception as e:
                record_exception('settings_apply.load_applied_settings_on_boot.remote_wifi_policy', e, status='WARN')
        # NEW: GC after boot-time apply snapshot
        try:
            maybe_gc("settings_apply_boot", min_interval_ms=2000, mem_free_below=55 * 1024)
        except Exception:
            pass
    except Exception as e:
        record_exception('settings_apply.load_applied_settings_on_boot', e)

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
                        write_json_atomic(staged_path, staged_unit)
                    except Exception:
                        pass
                    staged = staged_unit
            except Exception:
                staged = None
        if not isinstance(staged, dict):
            return False
        # Load previous applied snapshot for diffing (optional)
        prev_applied_meta = read_json_safe(applied_path, None)
        prev_applied = {}
        if isinstance(prev_applied_meta, dict) and isinstance(prev_applied_meta.get('applied'), dict):
            prev_applied = prev_applied_meta.get('applied') or {}
        # Snapshot previous settings for rollback
        prev_snapshot = {}
        for k in ALLOWLIST.keys():
            if hasattr(settings, k):
                prev_snapshot[k] = getattr(settings, k)
        try:
            write_json_atomic(getattr(settings,'REMOTE_SETTINGS_PREV_FILE','/logs/remote_settings.prev.json'), prev_snapshot)
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
        write_json_atomic(applied_path, meta)
        # Remove staged file to prevent re-apply
        try:
            os.remove(staged_path)
        except Exception:
            pass

        # NEW: GC after apply + snapshot + delete staged
        try:
            maybe_gc("settings_apply_once", min_interval_ms=3000, mem_free_below=55 * 1024)
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
                except Exception as e:
                    await log_exception('settings_apply.apply_staged_settings_once.confirm_command', e, status='WARN')
            # Append audit entry for applied settings + command confirms
            try:
                _append_staged_audit(getattr(settings, 'UNIT_ID', ''), 'apply', {'applied_keys': list(applied.keys()), 'commands_confirmed': confirmed, 'added': meta.get('added_keys',[]), 'changed': meta.get('changed_keys',[]), 'ignored': meta.get('ignored_keys',[])})
            except Exception:
                pass
        except Exception as e:
            await log_exception('settings_apply.apply_staged_settings_once.command_confirm_block', e, status='WARN')

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
                    except Exception as ie:
                        record_exception(f'settings_apply.rollback.{k}', ie, status='WARN')
        except Exception as re:
            record_exception('settings_apply.rollback', re, status='WARN')
        await debug_print('Settings: apply failed, rollback executed: %s' % e, 'ERROR')
        return False

async def settings_apply_loop(interval_s: int = 60):
    # Periodically check for staged settings and apply
    while True:
        try:
            await apply_staged_settings_once()
        except Exception as e:
            await log_exception('settings_apply.settings_apply_loop', e)
        try:
            import uasyncio as _a
            await _a.sleep(int(interval_s))
        except Exception:
            break
