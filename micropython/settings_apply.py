# TMON Settings Application Module
#
# Safe staged-settings application for MicroPython firmware.
#
# IMPORTANT:
#   A setting being PRESENT in staged settings does NOT mean it changed.
#   Reboots are therefore based on actual value changes only.
#
# This module:
#   - applies only allowlisted settings
#   - coerces values to their expected types
#   - persists applied settings
#   - calculates actual changes
#   - removes consumed staged settings
#   - reboots only when a critical setting actually changed
#   - rolls runtime settings back if application fails

try:
    import ujson as json
except Exception:
    import json

try:
    import uos as os
except Exception:
    import os

import settings

from config_persist import (
    read_json,
    read_json_safe,
    write_json,
    write_json_atomic,
)

from utils import (
    debug_print,
    persist_suspension_state,
    load_persisted_custom_settings,
    record_exception,
    log_exception,
)

try:
    from utils import maybe_gc
except Exception:
    def maybe_gc(*args, **kwargs):
        return None


# ---------------------------------------------------------------------------
# VALUE COERCION
# ---------------------------------------------------------------------------

def _to_bool(v):
    try:
        if isinstance(v, bool):
            return v

        if isinstance(v, (int, float)):
            return bool(v)

        s = str(v).strip().lower()

        return s in (
            '1',
            'true',
            'yes',
            'on',
        )

    except Exception:
        return False


def _to_int(v, default=0):
    try:
        return int(v)
    except Exception:
        try:
            return int(default)
        except Exception:
            return 0


def _to_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        try:
            return float(default)
        except Exception:
            return 0.0


def _to_str(v):
    try:
        return str(v)
    except Exception:
        return ''


# ---------------------------------------------------------------------------
# ALLOWLIST
# ---------------------------------------------------------------------------

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

    'ENABLE_LORA_OTA': _to_bool,
    'LORA_OTA_CHUNK_SIZE': _to_int,
    'LORA_OTA_MAX_RETRIES': _to_int,

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

    # Higher-level configuration.
    'NODE_TYPE': _to_str,
    'UNIT_Name': _to_str,
    'WORDPRESS_API_URL': _to_str,
    'LORA_NETWORK_NAME': _to_str,
    'LORA_NETWORK_PASSWORD': _to_str,
}


# ---------------------------------------------------------------------------
# SENSITIVE SETTINGS
# ---------------------------------------------------------------------------

SENSITIVE = {
    'WIFI_SSID': _to_str,
    'WIFI_PASS': _to_str,
}


# ---------------------------------------------------------------------------
# SETTINGS WHICH REQUIRE REBOOT WHEN THEY ACTUALLY CHANGE
# ---------------------------------------------------------------------------

REBOOT_KEYS = set([
    'NODE_TYPE',
    'WIFI_SSID',
    'WIFI_PASS',

    'RELAY_PIN1',
    'RELAY_PIN2',

    'ENGINE_ENABLED',

    'ENABLE_OLED',
    'ENABLE_LORA',
    'ENABLE_WIFI',
])


# ---------------------------------------------------------------------------
# WIFI POLICY
# ---------------------------------------------------------------------------

def _can_apply_wifi_credentials():
    try:
        if getattr(settings, 'NODE_TYPE', 'base') == 'base':
            return True

        # Remote nodes may receive WiFi credentials only before provisioning.
        return not bool(
            getattr(settings, 'UNIT_PROVISIONED', False)
        )

    except Exception as e:
        record_exception(
            'settings_apply._can_apply_wifi_credentials',
            e,
            status='WARN'
        )

        return False


# ---------------------------------------------------------------------------
# VALUE NORMALIZATION
# ---------------------------------------------------------------------------

def _coerce_value(k, v):
    """
    Return the exact value that _apply_key() would put into settings.

    This is important because comparisons must happen AFTER coercion.

    Example:
        staged value: "true"
        current value: True

    These are semantically identical and must NOT trigger a reboot.
    """

    try:
        if k == 'DEVICE_SUSPENDED':
            return _to_bool(v)

        if k in ALLOWLIST:
            return ALLOWLIST[k](v)

        if k in SENSITIVE:
            return SENSITIVE[k](v)

    except Exception as e:
        record_exception(
            'settings_apply._coerce_value.%s' % k,
            e,
            status='WARN'
        )

    return v


def _values_equal(a, b):
    """
    Conservative comparison helper.

    MicroPython values can sometimes have slightly different types,
    so compare normalized representations where possible.
    """

    try:
        if a == b:
            return True

        # bool/int need special handling.
        if isinstance(a, bool) or isinstance(b, bool):
            return bool(a) == bool(b)

        # Numeric values.
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            try:
                return float(a) == float(b)
            except Exception:
                pass

        # Strings.
        if isinstance(a, str) or isinstance(b, str):
            try:
                return str(a) == str(b)
            except Exception:
                pass

    except Exception:
        pass

    return False


# ---------------------------------------------------------------------------
# APPLY ONE SETTING
# ---------------------------------------------------------------------------

def _apply_key(k, v):
    try:

        # DEVICE_SUSPENDED has special persistence behavior.
        if k == 'DEVICE_SUSPENDED':

            coerced = _to_bool(v)

            setattr(
                settings,
                k,
                coerced
            )

            try:
                persist_suspension_state(
                    getattr(settings, k)
                )
            except Exception as e:
                record_exception(
                    'settings_apply._apply_key.persist_suspension_state',
                    e,
                    status='WARN'
                )

            return True

        # Normal allowlisted settings.
        if k in ALLOWLIST:

            coerced = ALLOWLIST[k](v)

            setattr(
                settings,
                k,
                coerced
            )

            # NODE_TYPE persistence and role handling.
            if k == 'NODE_TYPE':

                try:

                    from utils import persist_node_type

                    persist_node_type(coerced)

                    if str(coerced).lower() == 'remote':

                        try:
                            from wifi import disable_wifi

                            disable_wifi()

                            settings.ENABLE_WIFI = False

                        except Exception as e:

                            record_exception(
                                'settings_apply._apply_key.disable_wifi',
                                e,
                                status='WARN'
                            )

                except Exception as e:

                    record_exception(
                        'settings_apply._apply_key.persist_node_type',
                        e,
                        status='WARN'
                    )

            # Persist WordPress API URL.
            if k == 'WORDPRESS_API_URL':

                try:

                    from utils import persist_wordpress_api_url

                    persist_wordpress_api_url(coerced)

                except Exception as e:

                    record_exception(
                        'settings_apply._apply_key.persist_wordpress_api_url',
                        e,
                        status='WARN'
                    )

            return True

        # Sensitive WiFi credentials.
        if k in SENSITIVE:

            if not _can_apply_wifi_credentials():
                return False

            coerced = SENSITIVE[k](v)

            setattr(
                settings,
                k,
                coerced
            )

            return True

    except Exception as e:

        record_exception(
            'settings_apply._apply_key',
            e
        )

        return False

    return False


# ---------------------------------------------------------------------------
# FILTER AND APPLY
# ---------------------------------------------------------------------------

def _filter_and_apply(incoming):
    applied = {}

    if not isinstance(incoming, dict):
        return applied

    for k, v in incoming.items():

        try:

            if _apply_key(k, v):

                try:
                    applied[k] = getattr(settings, k)
                except Exception:
                    applied[k] = v

        except Exception as e:

            record_exception(
                'settings_apply._filter_and_apply.%s' % k,
                e,
                status='WARN'
            )

    return applied


# ---------------------------------------------------------------------------
# BOOT-TIME APPLIED SETTINGS
# ---------------------------------------------------------------------------

def load_applied_settings_on_boot():

    path = getattr(
        settings,
        'REMOTE_SETTINGS_APPLIED_FILE',
        settings.LOG_DIR + '/remote_settings.applied.json'
    )

    try:

        data = read_json_safe(
            path,
            None
        )

        if isinstance(data, dict):

            applied = data.get('applied')

            if isinstance(applied, dict):

                _filter_and_apply(applied)

            else:

                # Backward compatibility with files that may contain
                # the settings directly.
                _filter_and_apply(data)

            try:

                load_persisted_custom_settings()

            except Exception as e:

                record_exception(
                    'settings_apply.load_applied_settings_on_boot.load_custom_settings',
                    e,
                    status='WARN'
                )

            # Remote nodes must not have WiFi enabled after provisioning.
            try:

                if str(
                    getattr(settings, 'NODE_TYPE', '')
                ).lower() == 'remote':

                    try:

                        from wifi import disable_wifi

                        disable_wifi()

                        settings.ENABLE_WIFI = False

                    except Exception as e:

                        record_exception(
                            'settings_apply.load_applied_settings_on_boot.disable_wifi',
                            e,
                            status='WARN'
                        )

            except Exception as e:

                record_exception(
                    'settings_apply.load_applied_settings_on_boot.remote_wifi_policy',
                    e,
                    status='WARN'
                )

        try:

            maybe_gc(
                "settings_apply_boot",
                min_interval_ms=2000,
                mem_free_below=55 * 1024
            )

        except Exception:
            pass

    except Exception as e:

        record_exception(
            'settings_apply.load_applied_settings_on_boot',
            e
        )


# ---------------------------------------------------------------------------
# APPLY STAGED SETTINGS
# ---------------------------------------------------------------------------

async def apply_staged_settings_once():

    staged_path = getattr(
        settings,
        'REMOTE_SETTINGS_STAGED_FILE',
        settings.LOG_DIR + '/remote_settings.staged.json'
    )

    applied_path = getattr(
        settings,
        'REMOTE_SETTINGS_APPLIED_FILE',
        settings.LOG_DIR + '/remote_settings.applied.json'
    )

    prev_path = getattr(
        settings,
        'REMOTE_SETTINGS_PREV_FILE',
        settings.LOG_DIR + '/remote_settings.prev.json'
    )

    try:

        # ---------------------------------------------------------------
        # Locate staged settings.
        # ---------------------------------------------------------------

        unit_staged = (
            settings.LOG_DIR
            + '/device_settings-'
            + str(getattr(settings, 'UNIT_ID', ''))
            + '.json'
        )

        staged = None

        try:

            staged = read_json(
                staged_path,
                None
            )

        except Exception:

            staged = None

        # Try unit-specific staged file.
        if not isinstance(staged, dict):

            try:

                staged_unit = read_json(
                    unit_staged,
                    None
                )

                if isinstance(staged_unit, dict):

                    try:

                        write_json_atomic(
                            staged_path,
                            staged_unit
                        )

                    except Exception:
                        pass

                    staged = staged_unit

            except Exception:

                staged = None

        # Nothing staged.
        if not isinstance(staged, dict):

            return False

        # ---------------------------------------------------------------
        # Load previous applied snapshot.
        # ---------------------------------------------------------------

        prev_applied_meta = read_json_safe(
            applied_path,
            None
        )

        prev_applied = {}

        if (
            isinstance(prev_applied_meta, dict)
            and isinstance(prev_applied_meta.get('applied'), dict)
        ):

            prev_applied = (
                prev_applied_meta.get('applied')
                or {}
            )

        # ---------------------------------------------------------------
        # Snapshot CURRENT runtime settings for rollback.
        # ---------------------------------------------------------------

        prev_snapshot = {}

        for k in ALLOWLIST.keys():

            try:

                if hasattr(settings, k):

                    prev_snapshot[k] = getattr(
                        settings,
                        k
                    )

            except Exception:
                pass

        # Include sensitive settings in rollback snapshot.
        for k in SENSITIVE.keys():

            try:

                if hasattr(settings, k):

                    prev_snapshot[k] = getattr(
                        settings,
                        k
                    )

            except Exception:
                pass

        try:

            write_json_atomic(
                prev_path,
                prev_snapshot
            )

        except Exception:
            pass

        # ---------------------------------------------------------------
        # FIRST: determine actual changes BEFORE modifying settings.
        # ---------------------------------------------------------------

        candidate = {}

        ignored_keys = []

        for k, v in staged.items():

            # Commands are metadata, not settings.
            if k == 'commands':
                continue

            if (
                k not in ALLOWLIST
                and k not in SENSITIVE
                and k != 'DEVICE_SUSPENDED'
            ):

                ignored_keys.append(k)

                continue

            # WiFi credential policy.
            if k in SENSITIVE and not _can_apply_wifi_credentials():

                ignored_keys.append(k)

                continue

            try:

                coerced = _coerce_value(
                    k,
                    v
                )

                candidate[k] = coerced

            except Exception:

                ignored_keys.append(k)

        changed_keys = []
        unchanged_keys = []
        added_keys = []

        for k, desired in candidate.items():

            current_exists = hasattr(
                settings,
                k
            )

            if not current_exists:

                added_keys.append(k)

                continue

            try:

                current = getattr(
                    settings,
                    k
                )

                if _values_equal(
                    current,
                    desired
                ):

                    unchanged_keys.append(k)

                else:

                    changed_keys.append(k)

            except Exception:

                changed_keys.append(k)

        # ---------------------------------------------------------------
        # Apply settings.
        # ---------------------------------------------------------------

        applied = _filter_and_apply(
            staged
        )

        # ---------------------------------------------------------------
        # Recalculate actual result from runtime values.
        # ---------------------------------------------------------------

        actual_changed_keys = []

        actual_unchanged_keys = []

        for k, desired in candidate.items():

            try:

                current_after = getattr(
                    settings,
                    k
                )

                if _values_equal(
                    current_after,
                    desired
                ):

                    if k in changed_keys:
                        actual_changed_keys.append(k)
                    else:
                        actual_unchanged_keys.append(k)

            except Exception:

                pass

        # Prefer the pre-apply actual diff because it tells us whether
        # a reboot was necessary.
        effective_changed_keys = list(
            dict.fromkeys(
                changed_keys
            )
        )

        # ---------------------------------------------------------------
        # Persist applied snapshot.
        # ---------------------------------------------------------------

        meta = {
            'applied': applied,
            'ts': None,
            'changed_keys': effective_changed_keys,
            'added_keys': list(
                dict.fromkeys(
                    added_keys
                )
            ),
            'unchanged_keys': list(
                dict.fromkeys(
                    unchanged_keys
                )
            ),
            'ignored_keys': list(
                dict.fromkeys(
                    ignored_keys
                )
            ),
        }

        try:

            import utime as _t

            meta['ts'] = int(
                _t.time()
            )

        except Exception:
            pass

        # Also compare against the prior persisted snapshot.
        persisted_changed_keys = []
        persisted_added_keys = []

        try:

            for k, v in applied.items():

                if k not in prev_applied:

                    persisted_added_keys.append(k)

                elif not _values_equal(
                    prev_applied.get(k),
                    v
                ):

                    persisted_changed_keys.append(k)

        except Exception:
            pass

        meta['persisted_changed_keys'] = (
            persisted_changed_keys
        )

        meta['persisted_added_keys'] = (
            persisted_added_keys
        )

        try:

            write_json_atomic(
                applied_path,
                meta
            )

        except Exception as e:

            record_exception(
                'settings_apply.write_applied_snapshot',
                e,
                status='WARN'
            )

        # ---------------------------------------------------------------
        # Consume local staged file.
        # ---------------------------------------------------------------

        try:

            os.remove(
                staged_path
            )

        except Exception:
            pass

        # Also consume unit-specific staged file.
        try:

            if unit_staged != staged_path:

                os.remove(
                    unit_staged
                )

        except Exception:
            pass

        try:

            from wprest import confirm_staged_settings_applied

        except Exception:

            confirm_staged_settings_applied = None

        if confirm_staged_settings_applied is not None:

            try:

                await confirm_staged_settings_applied(
                    changed_keys=list(effective_changed_keys),
                    applied_keys=list(applied.keys()),
                    status='applied',
                )

            except Exception as e:

                await debug_print(
                    'Settings server acknowledgement failed: %s'
                    % e,
                    'WARN'
                )

        try:

            maybe_gc(
                "settings_apply_once",
                min_interval_ms=3000,
                mem_free_below=55 * 1024
            )

        except Exception:
            pass

        # ---------------------------------------------------------------
        # CRITICAL FIX:
        #
        # Reboot ONLY if a critical value ACTUALLY CHANGED.
        #
        # DO NOT use:
        #
        #     if applied_keys & REBOOT_KEYS:
        #
        # because that causes an infinite reboot loop when the server
        # repeatedly returns the same configuration.
        # ---------------------------------------------------------------

        critical_changed = (
            set(effective_changed_keys)
            | set(persisted_changed_keys)
            | set(persisted_added_keys)
        ) & REBOOT_KEYS

        if critical_changed:

            await debug_print(
                'Critical settings changed: '
                + ','.join(
                    sorted(
                        list(
                            critical_changed
                        )
                    )
                )
                + '; performing soft reset',
                'PROVISION'
            )

            # -----------------------------------------------------------
            # IMPORTANT:
            #
            # The local staged file has already been consumed and the
            # applied snapshot persisted BEFORE reboot.
            # -----------------------------------------------------------

            try:

                import machine

                machine.soft_reset()

            except Exception:

                # Desktop/test environments may not provide machine.
                pass

            return True

        # ---------------------------------------------------------------
        # NO REBOOT REQUIRED.
        # ---------------------------------------------------------------

        if effective_changed_keys:

            await debug_print(
                'Settings changed without reboot-required keys: '
                + ','.join(
                    sorted(
                        list(
                            effective_changed_keys
                        )
                    )
                ),
                'PROVISION'
            )

        elif applied:

            await debug_print(
                'Settings already current; no reboot required',
                'PROVISION'
            )

        # ---------------------------------------------------------------
        # Confirm staged commands.
        # ---------------------------------------------------------------

        try:

            cmds = (
                staged.get('commands', [])
                if isinstance(staged, dict)
                else []
            )

            confirmed = 0

            for c in (cmds or []):

                try:

                    if not isinstance(c, dict):
                        continue

                    job_id = (
                        c.get('id')
                        or c.get('job_id')
                        or c.get('command_id')
                    )

                    payload = {
                        'job_id': job_id,
                        'ok': True,
                        'result': 'applied_via_staged_settings'
                    }

                    if job_id:

                        if _post_command_confirm(
                            payload
                        ):

                            confirmed += 1

                        else:

                            await debug_print(
                                'Failed to confirm staged command %s'
                                % job_id,
                                'WARN'
                            )

                except Exception as e:

                    await log_exception(
                        'settings_apply.apply_staged_settings_once.confirm_command',
                        e,
                        status='WARN'
                    )

            # Audit.
            try:

                _append_staged_audit(
                    getattr(
                        settings,
                        'UNIT_ID',
                        ''
                    ),
                    'apply',
                    {
                        'applied_keys': list(
                            applied.keys()
                        ),
                        'commands_confirmed': confirmed,
                        'added': meta.get(
                            'added_keys',
                            []
                        ),
                        'changed': meta.get(
                            'changed_keys',
                            []
                        ),
                        'unchanged': meta.get(
                            'unchanged_keys',
                            []
                        ),
                        'ignored': meta.get(
                            'ignored_keys',
                            []
                        ),
                    }
                )

            except Exception:
                pass

        except Exception as e:

            await log_exception(
                'settings_apply.apply_staged_settings_once.command_confirm_block',
                e,
                status='WARN'
            )

        # ---------------------------------------------------------------
        # Final log.
        # ---------------------------------------------------------------

        try:

            msg = (
                'Settings applied: '
                + (
                    'a='
                    + ','.join(
                        meta.get(
                            'added_keys',
                            []
                        )
                    )
                    if meta.get('added_keys')
                    else 'a=0'
                )
                + ' '
                + (
                    'c='
                    + ','.join(
                        meta.get(
                            'changed_keys',
                            []
                        )
                    )
                    if meta.get('changed_keys')
                    else 'c=0'
                )
                + ' '
                + (
                    'u='
                    + ','.join(
                        meta.get(
                            'unchanged_keys',
                            []
                        )
                    )
                    if meta.get('unchanged_keys')
                    else 'u=0'
                )
                + ' '
                + (
                    'i='
                    + ','.join(
                        meta.get(
                            'ignored_keys',
                            []
                        )
                    )
                    if meta.get('ignored_keys')
                    else 'i=0'
                )
            )

        except Exception:

            msg = 'Settings: staged settings applied'

        await debug_print(
            msg,
            'INFO'
        )

        return True

    except Exception as e:

        # ---------------------------------------------------------------
        # ROLLBACK
        # ---------------------------------------------------------------

        try:

            prev = read_json(
                prev_path,
                {}
            )

            if isinstance(prev, dict):

                for k, v in prev.items():

                    try:

                        setattr(
                            settings,
                            k,
                            v
                        )

                    except Exception as ie:

                        record_exception(
                            'settings_apply.rollback.%s' % k,
                            ie,
                            status='WARN'
                        )

        except Exception as re:

            record_exception(
                'settings_apply.rollback',
                re
            )

        await debug_print(
            'Settings: apply failed, rollback executed: %s'
            % e,
            'ERROR'
        )

        return False


# ---------------------------------------------------------------------------
# PERIODIC LOOP
# ---------------------------------------------------------------------------

async def settings_apply_loop(
    interval_s=60
):

    while True:

        try:

            await apply_staged_settings_once()

        except Exception as e:

            await log_exception(
                'settings_apply.settings_apply_loop',
                e
            )

        try:

            import uasyncio as _a

            await _a.sleep(
                int(interval_s)
            )

        except Exception:

            break
