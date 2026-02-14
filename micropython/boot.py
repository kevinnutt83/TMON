# Firmware Version: v2.00j
# This file is executed on every boot (including wake-boot from deepsleep)
# import esp
# esp.osdebug(None)
# import webrepl
# webrepl.start()

# CHANGED: import settings/platform first so MCU_TYPE is known before importing wifi/oled on Zero
import settings
from platform_compat import asyncio  # CHANGED

# NEW: install minimal MicroPython module shims early (boot runs before main.py on MicroPython)
def _install_zero_shims_if_needed():
    try:
        mcu = str(getattr(settings, "MCU_TYPE", "")).lower()
    except Exception:
        mcu = ""
    if mcu != "zero":
        return
    try:
        import sys, types
    except Exception:
        return

    def _ensure(name, mod):
        try:
            if name not in sys.modules and mod is not None:
                sys.modules[name] = mod
        except Exception:
            pass

    # Prefer platform_compat-provided shims when available
    try:
        from platform_compat import machine as _m, network as _n, requests as _r, asyncio as _a
    except Exception:
        _m = _n = _r = _a = None

    _ensure("machine", _m)
    _ensure("network", _n)
    if _r is not None:
        _ensure("urequests", _r)
    if _a is not None:
        _ensure("uasyncio", _a)

    # Also map common MicroPython stdlib module names used across the firmware
    try:
        import json as _json
        _ensure("ujson", _json)
    except Exception:
        pass
    try:
        import binascii as _binascii
        _ensure("ubinascii", _binascii)
    except Exception:
        pass
    try:
        import hashlib as _hashlib
        _ensure("uhashlib", _hashlib)
    except Exception:
        pass
    try:
        import os as _os
        _ensure("uos", _os)
    except Exception:
        pass

_install_zero_shims_if_needed()

# CHANGED: import these after shims
from utils import debug_print, flash_led
from oled import display_message

async def boot():
    fw_msg = f"Firmware: {settings.FIRMWARE_VERSION}"
    await display_message(fw_msg, 2)
    print(fw_msg)
    await display_message("Booting TMON Device", 3)
    # If remote node, try to load persisted next sync time
    try:
        if getattr(settings, 'NODE_TYPE', None) == 'remote':
            try:
                import ujson as _json  # CHANGED: MicroPython
            except Exception:
                import json as _json  # CHANGED: CPython (Zero)
            import os
            path = settings.LOG_DIR + '/remote_next_sync.json'
            try:
                os.stat(path)
                with open(path, 'r') as f:
                    obj = _json.load(f)
                    if 'next' in obj:
                        settings.nextLoraSync = int(obj['next'])
            except OSError:
                pass
    except Exception:
        pass
    # Only connect to WiFi when enabled. For remotes, allow connect if not yet provisioned and policy allows it.
    try:
        node_type = getattr(settings, 'NODE_TYPE', None)
        enabled = getattr(settings, 'ENABLE_WIFI', False)
        allow_remote_wifi_if_unprovisioned = bool(getattr(settings, 'WIFI_ALWAYS_ON_WHEN_UNPROVISIONED', True))
        should_connect = False
        if enabled:
            if node_type != 'remote':
                should_connect = True
                await debug_print("Non-remote Node Provisioning", "INFO")
            else:
                # remote: only if not provisioned and policy allows
                if not getattr(settings, 'UNIT_PROVISIONED', False) and allow_remote_wifi_if_unprovisioned:
                    should_connect = True
        if should_connect:
            # CHANGED: import wifi lazily (post-shim) so Zero can boot without MicroPython network stack
            from wifi import connectToWifiNetwork
            await connectToWifiNetwork()

            # NEW: Best-effort, early provisioning fetch when internet is available
            try:
                from wifi import check_internet_connection
                inet_ok = False
                try:
                    inet_ok = await check_internet_connection()
                except Exception:
                    inet_ok = False
                if inet_ok:
                    try:
                        # from main import first_boot_provision
                        # await first_boot_provision()
                        import provision
                        mid = getattr(settings, 'MACHINE_ID', None)
                        prov = provision.fetch_provisioning(unit_id=getattr(settings, 'UNIT_ID', None), machine_id=mid, base_url=getattr(settings, 'TMON_ADMIN_API_URL', None))
                        if isinstance(prov, dict) and prov:
                            try:
                                provision.apply_settings(prov)
                                await debug_print("Provisioning applied", "PROVISION")
                                if node_type != 'remote':
                                    from wifi import disable_wifi
                                    settings.ENABLE_WIFI = False
                                    await disable_wifi()
                                    await debug_print("Non-remote Node Provisioning", "PROVISION")
                            except Exception:
                                pass
                    except Exception:
                        # keep boot resilient on any errors
                        pass
            except Exception:
                pass
    except Exception:
        pass

asyncio.run(boot())
