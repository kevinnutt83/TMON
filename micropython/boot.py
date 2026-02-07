# Firmware Version: v2.00j
# This file is executed on every boot (including wake-boot from deepsleep)
# import esp
# esp.osdebug(None)
# import webrepl
# webrepl.start()

import settings

# For MCU_TYPE="zero" (Raspberry Pi Zero / CPython), ensure a `machine` module exists
# before importing modules that import `machine` at import-time (e.g., oled.py).
try:
    import machine  # MicroPython
except Exception:
    machine = None

if (machine is None) and (str(getattr(settings, "MCU_TYPE", "")).lower() == "zero"):
    try:
        import sys as _sys, types as _types, uuid as _uuid
        _m = _types.SimpleNamespace()

        def _unique_id():
            try:
                with open("/etc/machine-id", "r") as f:
                    mid = (f.read() or "").strip()
                    if mid:
                        return mid.encode("utf-8")[:12]
            except Exception:
                pass
            try:
                node = _uuid.getnode()
                return int(node).to_bytes(6, "big", signed=False)
            except Exception:
                return b"\x00" * 6

        class Pin:
            IN = 0; OUT = 1; PULL_UP = 2; PULL_DOWN = 3
            def __init__(self, pin, mode=OUT, pull=None):
                self.pin = pin; self.mode = mode; self.pull = pull; self._val = 0
            def value(self, v=None):
                if v is None:
                    return self._val
                self._val = 1 if v else 0
                return self._val

        class ADC:
            def __init__(self, *_a, **_kw): pass
            def read_u16(self): return 0

        def soft_reset(): raise SystemExit("soft_reset requested")
        def reset(): raise SystemExit("reset requested")

        _m.Pin = Pin; _m.ADC = ADC; _m.unique_id = _unique_id
        _m.soft_reset = soft_reset; _m.reset = reset
        _sys.modules["machine"] = _m
    except Exception:
        pass

from wifi import connectToWifiNetwork
from utils import flash_led
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio
from oled import display_message

async def boot():
    fw_msg = f"Firmware: {settings.FIRMWARE_VERSION}"
    await display_message(fw_msg, 2)
    print(fw_msg)
    await display_message("Booting TMON Device", 3)
    # If remote node, try to load persisted next sync time
    try:
        if getattr(settings, 'NODE_TYPE', None) == 'remote':
            import ujson, os
            path = settings.LOG_DIR + '/remote_next_sync.json'
            try:
                os.stat(path)
                with open(path, 'r') as f:
                    obj = ujson.load(f)
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
            else:
                # remote: only if not provisioned and policy allows
                if not getattr(settings, 'UNIT_PROVISIONED', False) and allow_remote_wifi_if_unprovisioned:
                    should_connect = True
        if should_connect:
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
                        from main import first_boot_provision
                        await first_boot_provision()
                        import provision
                        mid = getattr(settings, 'MACHINE_ID', None)
                        prov = provision.fetch_provisioning(unit_id=getattr(settings, 'UNIT_ID', None), machine_id=mid, base_url=getattr(settings, 'TMON_ADMIN_API_URL', None))
                        if isinstance(prov, dict) and prov:
                            try:
                                provision.apply_settings(prov)
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
