# Firmware Version: v2.06.0

# --- Single-threaded asyncio event loop ---
from platform_compat import asyncio, time, os, gc, machine, requests  # CHANGED

import sys  # CHANGED
import types  # CHANGED
import settings  # CHANGED
import sdata  # CHANGED

# NEW: CPython/Zero shims for MicroPython-only modules (fixes: "ModuleNotFoundError: machine")
def _install_micropython_shims_if_needed():
    try:
        mcu = str(getattr(settings, "MCU_TYPE", "")).lower()
    except Exception:
        mcu = ""
    try:
        is_micropython = (getattr(sys, "implementation", None) and sys.implementation.name == "micropython")
    except Exception:
        is_micropython = False
    is_zero_runtime = (mcu == "zero") or (not is_micropython)

    if not is_zero_runtime:
        return

    def _ensure_mod(name, mod):
        try:
            if name not in sys.modules:
                sys.modules[name] = mod
        except Exception:
            pass

    # ujson/ubinascii/uhashlib/uio/uselect/utime/uos/urequests/uasyncio shims
    try:
        import json as _json
        _ensure_mod("ujson", _json)
    except Exception:
        pass
    try:
        import binascii as _binascii
        _ensure_mod("ubinascii", _binascii)
    except Exception:
        pass
    try:
        import hashlib as _hashlib
        _ensure_mod("uhashlib", _hashlib)
    except Exception:
        pass
    try:
        import io as _io
        _ensure_mod("uio", _io)
    except Exception:
        pass
    try:
        import select as _select
        _ensure_mod("uselect", _select)
    except Exception:
        pass
    try:
        import time as _ptime
        _ensure_mod("utime", _ptime)
    except Exception:
        pass
    try:
        import os as _posix_os
        _ensure_mod("uos", _posix_os)
    except Exception:
        pass
    try:
        # platform_compat already selected the right requests; expose it as urequests for legacy imports
        if requests is not None:
            _ensure_mod("urequests", requests)
    except Exception:
        pass
    try:
        # platform_compat already selected asyncio implementation; expose it as uasyncio for legacy imports
        if asyncio is not None:
            _ensure_mod("uasyncio", asyncio)
    except Exception:
        pass

    # machine stub (or platform_compat.machine if it is a usable shim)
    if "machine" not in sys.modules:
        if machine is not None and hasattr(machine, "__dict__"):
            _ensure_mod("machine", machine)
        else:
            _m = types.ModuleType("machine")

            class Pin:
                IN = 0
                OUT = 1
                PULL_UP = 2
                PULL_DOWN = 3

                def __init__(self, pin, mode=None, pull=None):
                    self.pin = pin
                    self.mode = mode
                    self.pull = pull
                    self._val = 0

                def value(self, v=None):
                    if v is None:
                        return int(self._val)
                    self._val = 1 if v else 0
                    return int(self._val)

                def on(self):
                    self.value(1)

                def off(self):
                    self.value(0)

            class I2C:
                def __init__(self, *a, **kw):
                    raise RuntimeError("I2C not available on CPython/zero without a backend")

            class SPI:
                def __init__(self, *a, **kw):
                    raise RuntimeError("SPI not available on CPython/zero without a backend")

                def init(self, *a, **kw):
                    return None

                def deinit(self):
                    return None

            class UART:
                def __init__(self, *a, **kw):
                    raise RuntimeError("UART not available on CPython/zero without a backend")

            def soft_reset():
                raise SystemExit("soft_reset requested")

            _m.Pin = Pin
            _m.I2C = I2C
            _m.SPI = SPI
            _m.UART = UART
            _m.soft_reset = soft_reset
            _ensure_mod("machine", _m)

    # network stub
    if "network" not in sys.modules:
        _n = types.ModuleType("network")
        _n.STA_IF = 0

        class WLAN:
            def __init__(self, iface):
                self.iface = iface
                self._active = False
                self._connected = False

            def active(self, v=None):
                if v is None:
                    return bool(self._active)
                self._active = bool(v)
                if not self._active:
                    self._connected = False
                return bool(self._active)

            def isconnected(self):
                return bool(self._connected)

            def scan(self):
                return []

            def connect(self, *a, **kw):
                self._connected = False
                return None

            def ifconfig(self):
                return ("0.0.0.0", "0.0.0.0", "0.0.0.0", "0.0.0.0")

            def config(self, *a, **kw):
                if a and a[0] == "mac":
                    return b"\x00\x00\x00\x00\x00\x00"
                if a and a[0] == "rssi":
                    return -100
                return None

            def status(self, *a, **kw):
                if a and a[0] == "rssi":
                    return -100
                return 0

        _n.WLAN = WLAN
        _ensure_mod("network", _n)

_install_micropython_shims_if_needed()

# CHANGED: keep legacy "import machine"/"import network" satisfied (now covered by shims too)
try:
    if str(getattr(settings, "MCU_TYPE", "")).lower() == "zero":
        if "machine" not in sys.modules:
            if machine is not None and hasattr(machine, "__dict__"):
                sys.modules["machine"] = machine
            else:
                _m = types.ModuleType("machine")
                sys.modules["machine"] = _m
        if "network" not in sys.modules:
            _n = types.ModuleType("network")
            sys.modules["network"] = _n
except Exception:
    pass

script_start_time = time.ticks_ms()  # CHANGED

from debug import info as dbg_info, warn as dbg_warn, error as dbg_error
from sampling import sampleEnviroment
from utils import (
    free_pins_lora, checkLogDirectory, debug_print, load_persisted_unit_name,
    periodic_field_data_send, load_persisted_unit_id, persist_unit_id,
    get_machine_id, periodic_provision_check
)

# CHANGED: guard LoRa import on Zero/CPython so firmware can boot without LoRa driver stack
try:
    _mcu = str(getattr(settings, "MCU_TYPE", "")).lower()
except Exception:
    _mcu = ""
try:
    _is_micropython = (getattr(sys, "implementation", None) and sys.implementation.name == "micropython")
except Exception:
    _is_micropython = False

if (_mcu == "zero") or (not _is_micropython):
    try:
        from lora import connectLora, log_error, TMON_AI
    except Exception:
        connectLora = None
        TMON_AI = None
        async def log_error(error_msg):
            try:
                await debug_print(f"lora unavailable on zero: {error_msg}", "WARN")
            except Exception:
                pass
else:
    from lora import connectLora, log_error, TMON_AI

from ota import check_for_update, apply_pending_update
from oled import update_display, display_message
from settings_apply import load_applied_settings_on_boot, settings_apply_loop

# NEW: engine controller import must be guarded (not present / not usable on Zero)
try:
    from engine_controller import engine_loop  # type: ignore
except Exception:
    engine_loop = None

try:
    from wifi import connectToWifiNetwork, wifi_rssi_monitor  # CHANGED
except Exception:
    connectToWifiNetwork = None
    wifi_rssi_monitor = None

def get_script_runtime():
    now = time.ticks_ms()
    return (now - script_start_time) // 1000

# NEW: provisioned helper used by UC checkin task (was referenced but not defined)
def is_provisioned():
    try:
        if bool(getattr(settings, 'UNIT_PROVISIONED', False)):
            return True
        flag = getattr(settings, 'PROVISIONED_FLAG_FILE', '/logs/provisioned.flag')
        try:
            os.stat(flag)
            # also require basic identity/url presence to avoid false positives
            return bool(str(getattr(settings, 'UNIT_ID', '')).strip()) and bool(str(getattr(settings, 'WORDPRESS_API_URL', '')).strip())
        except Exception:
            return False
    except Exception:
        return False

# NEW: minimal TaskManager fallback (fixes NameError; preserves "interval task" behavior)
try:
    TaskManager  # type: ignore[name-defined]
except Exception:
    class TaskManager:
        def __init__(self):
            self._tasks = []

        def add_task(self, coro_fn, name, interval_s):
            # coro_fn: async callable; interval_s: seconds
            self._tasks.append((str(name or 'task'), coro_fn, int(interval_s) if interval_s else 1))

        async def _runner(self, name, coro_fn, interval_s):
            while True:
                try:
                    await coro_fn()
                except Exception as e:
                    try:
                        await debug_print(f"TaskManager[{name}] error: {e}", "ERROR")
                    except Exception:
                        pass
                try:
                    await asyncio.sleep(interval_s)
                except Exception:
                    # keep loop alive even if asyncio is partially stubbed
                    pass

        async def run(self):
            # schedule all runners and then idle forever
            try:
                for (name, fn, interval_s) in self._tasks:
                    try:
                        asyncio.create_task(self._runner(name, fn, interval_s))
                    except Exception:
                        pass
                while True:
                    await asyncio.sleep(3600)
            except Exception:
                # last-resort idle loop
                while True:
                    try:
                        await asyncio.sleep(3600)
                    except Exception:
                        pass

# NEW: LoRa comm wrapper expected by startup() (was referenced but not defined)
async def lora_comm_task():
    try:
        if connectLora:
            r = connectLora()
            if hasattr(r, "__await__"):
                await r
    except Exception as e:
        try:
            await debug_print(f"lora_comm_task error: {e}", "ERROR")
        except Exception:
            pass

async def periodic_field_data_task():
    # Preserve current behavior: send log using the existing uploader (utils.send_field_data_log via periodic_field_data_send loop elsewhere)
    try:
        from utils import send_field_data_log
    except Exception:
        send_field_data_log = None
    try:
        if send_field_data_log:
            await send_field_data_log()
    except Exception as e:
        try:
            await debug_print(f"periodic_field_data_task error: {e}", "ERROR")
        except Exception:
            pass

async def periodic_command_poll_task():
    # Preserve current behavior: poll commands through wprest helper when present
    try:
        from wprest import poll_device_commands
    except Exception:
        poll_device_commands = None
    try:
        if poll_device_commands:
            await poll_device_commands()
    except Exception as e:
        try:
            await debug_print(f"periodic_command_poll_task error: {e}", "ERROR")
        except Exception:
            pass

async def first_boot_provision():
    # Check for provisioning flag; if absent, try WiFi check-in to TMON Admin hub
    try:
        flag = settings.PROVISIONED_FLAG_FILE
    except Exception:
        flag = '/logs/provisioned.flag'
    already = False
    try:
        if os.stat(flag):
            already = True
    except Exception:
        already = False
    if already:
        return
    hub = getattr(settings, 'TMON_ADMIN_API_URL', '')
    if not hub or not requests or not connectToWifiNetwork:
        return
    try:
        await connectToWifiNetwork()
        mid = get_machine_id()
        body = {
            'unit_id': settings.UNIT_ID,
            'machine_id': mid,
            'firmware_version': getattr(settings, 'FIRMWARE_VERSION', ''),
            'node_type': getattr(settings, 'NODE_TYPE', ''),
        }
        url = hub.rstrip('/') + '/wp-json/tmon-admin/v1/device/check-in'
        try:
            resp = requests.post(url, json=body, timeout=10)
        except TypeError:
            resp = requests.post(url, json=body)
        ok = (resp is not None and getattr(resp, 'status_code', 0) == 200)
        if ok:
            try:
                with open(flag, 'w') as f:
                    f.write('1')  # CHANGED: was empty (syntax break)
            except Exception:
                pass
            try:
                settings.UNIT_PROVISIONED = True
            except Exception:
                pass
            try:
                resp_json = resp.json()
            except Exception:
                resp_json = {}
            try:
                unit_name = (resp_json.get('unit_name') or '').strip()
                if unit_name:
                    try:
                        setattr(settings, "UNIT_Name", unit_name)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                new_uid = resp_json.get('unit_id')
                if new_uid and str(new_uid).strip():
                    try:
                        settings.UNIT_ID = str(new_uid).strip()
                        persist_unit_id(settings.UNIT_ID)
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                await display_message("Provisioned", 2)
            except Exception:
                pass
            try:
                site_val = (resp_json.get('site_url') or resp_json.get('wordpress_api_url') or '').strip()
                role_val = (resp_json.get('role') or '').strip()
                unit_name = (resp_json.get('unit_name') or '').strip()
                plan_val = (resp_json.get('plan') or '').strip()
                fw_ver = (resp_json.get('firmware') or '').strip()
                staged = bool(resp_json.get('staged_exists'))
                provisioned = bool(resp_json.get('provisioned'))
                if site_val:
                    try:
                        settings.WORDPRESS_API_URL = site_val
                    except Exception:
                        pass
                if role_val:
                    try:
                        settings.NODE_TYPE = role_val
                    except Exception:
                        pass
                if unit_name:
                    try:
                        settings.UNIT_Name = unit_name
                    except Exception:
                        pass
                if plan_val:
                    try:
                        settings.PLAN = plan_val
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                if str(getattr(settings, "NODE_TYPE", "")).lower() == "remote" and bool(getattr(settings, "WIFI_DISABLE_AFTER_PROVISION", False)):
                    try:
                        settings.ENABLE_WIFI = False
                    except Exception:
                        pass
            except Exception:
                pass
        try:
            if resp:
                resp.close()
        except Exception:
            pass
    except Exception as e:
        await debug_print('Provisioning check-in failed: %s' % e, 'ERROR')

async def ota_boot_check():
    """One-time early OTA version check to ensure latest firmware before starting tasks."""
    try:
        await check_for_update()
    except Exception:
        pass

async def periodic_uc_checkin_task():
    """Periodic Unit Connector check-in for provisioned devices."""
    try:
        from wprest import register_with_wp, send_settings_to_wp, send_data_to_wp, poll_ota_jobs, fetch_staged_settings, poll_device_commands
    except Exception:
        register_with_wp = send_settings_to_wp = send_data_to_wp = poll_ota_jobs = fetch_staged_settings = poll_device_commands = None
    interval = int(getattr(settings, 'UC_CHECKIN_INTERVAL_S', 300))
    while True:
        try:
            if not is_provisioned():
                await asyncio.sleep(2)  # CHANGED: was empty (syntax break)
                continue
            wp = getattr(settings, 'WORDPRESS_API_URL', '')
            if wp and not getattr(settings, 'DEVICE_SUSPENDED', False):
                # Keep existing behavior: the real work lives in wprest helpers if present.
                if register_with_wp:
                    await register_with_wp()
                if fetch_staged_settings:
                    await fetch_staged_settings()
                if poll_ota_jobs:
                    await poll_ota_jobs()
                if poll_device_commands:
                    await poll_device_commands()
        except Exception as e:
            await debug_print(f"uc: checkin err {e}", "ERROR")
        # NEW: GC after UC check-in loop (multiple HTTP calls + JSON)
        try:
            from utils import maybe_gc
            maybe_gc("uc_checkin", min_interval_ms=15000, mem_free_below=45 * 1024)
        except Exception:
            pass
        await asyncio.sleep(interval)

async def startup():
    tm = TaskManager()
    # Run first-boot provisioning before normal tasks
    try:
        await first_boot_provision()
    except Exception as e:
        await debug_print('first_boot_provision error: %s' % e, 'ERROR')

    # One-time OTA version check early
    try:
        await ota_boot_check()
    except Exception:
        pass

    # Dedicated LoRa and sampling loops
    lora_interval = int(getattr(settings, 'LORA_LOOP_INTERVAL_S', 1))
    node_role = str(getattr(settings, 'NODE_TYPE', 'base')).lower()
    if node_role != 'wifi':
        tm.add_task(lora_comm_task, 'lora', lora_interval)
    tm.add_task(sample_task, 'sample', 60)

    wp_url = str(getattr(settings, 'WORDPRESS_API_URL', '')).strip()
    if node_role in ('base', 'wifi'):
        if wp_url:
            tm.add_task(periodic_field_data_task, 'field_data', settings.FIELD_DATA_SEND_INTERVAL)
        tm.add_task(periodic_command_poll_task, 'cmd_poll', 10)

    # Background periodic tasks (standalone loops)
    try:
        if wifi_rssi_monitor:
            asyncio.create_task(wifi_rssi_monitor())  # CHANGED
    except Exception:
        pass

    # Start provisioning loop
    try:
        await debug_print('startup: schedule prov-check', 'INFO')  # CHANGED
        asyncio.create_task(periodic_provision_check())  # CHANGED
    except Exception as e:
        await debug_print(f'startup: prov-check schedule fail: {e}', 'ERROR')

    # Staged settings apply loop
    try:
        asyncio.create_task(settings_apply_loop(int(getattr(settings, 'PROVISION_CHECK_INTERVAL_S', 60))))  # CHANGED
    except Exception:
        pass

    # OLED background update with optional page rotation, gated by ENABLE_OLED
    async def _oled_loop():
        page = 0
        if not bool(getattr(settings, 'ENABLE_OLED', True)):
            return
        try:
            upd = int(getattr(settings, 'OLED_UPDATE_INTERVAL_S', 10))
            rotate_s = int(getattr(settings, 'OLED_PAGE_ROTATE_INTERVAL_S', 30))
            scroll = bool(getattr(settings, 'OLED_SCROLL_ENABLED', False))
        except Exception:
            upd, rotate_s, scroll = 10, 30, False  # CHANGED: was invalid assignment
        last_rotate = time.time()
        while True:
            try:
                await update_display(page)
            except Exception:
                pass
            if scroll and (time.time() - last_rotate) >= rotate_s:
                page = (page + 1) % 2
                last_rotate = time.time()
            await asyncio.sleep(upd)
    try:
        asyncio.create_task(_oled_loop())  # CHANGED
    except Exception:
        pass

    # Periodic OTA version/apply tasks
    async def ota_version_task():
        while True:
            try:
                await check_for_update()  # CHANGED
            except Exception:
                pass
            await asyncio.sleep(getattr(settings, 'OTA_CHECK_INTERVAL_S', 1800))
    try:
        asyncio.create_task(ota_version_task())  # CHANGED
    except Exception:
        pass

    async def ota_apply_task():
        while True:
            try:
                await apply_pending_update()  # CHANGED
            except Exception:
                pass
            await asyncio.sleep(getattr(settings, 'OTA_APPLY_INTERVAL_S', 600))
    try:
        asyncio.create_task(ota_apply_task())  # CHANGED
    except Exception:
        pass

    # Unit Connector periodic check-in loop
    try:
        asyncio.create_task(periodic_uc_checkin_task())  # CHANGED
    except Exception:
        pass

    # RS485 engine polling loop
    try:
        if (
            engine_loop
            and not bool(getattr(settings, 'ENGINE_FORCE_DISABLED', False))
            and bool(getattr(settings, 'USE_RS485', False))
            and bool(getattr(settings, 'ENABLE_ENGINE_CONTROLLER', False))
        ):
            import uasyncio as _ae
            _ae.create_task(engine_loop())
            await debug_print('startup: engine_loop started', 'INFO')
        else:
            await debug_print('startup: engine_loop disabled', 'INFO')
    except Exception as e:
        await debug_print(f'startup: engine start fail: {e}', 'ERROR')

    await tm.run()

# If blocking tasks are added later, start them in a separate thread here
try:
    # CHANGED: do not re-import uasyncio here; platform_compat already selected the correct asyncio
    from utils import start_background_tasks, update_sys_voltage, runGC  # CHANGED: use runGC alias
    from oled import display_message

    async def main():
        # Start background tasks (provisioning, field-data uploader, etc.)
        try:
            start_background_tasks()
        except Exception:
            pass

        asyncio.create_task(startup())

        # Optional: present a short startup message on OLED if enabled
        try:
            if bool(getattr(settings, 'ENABLE_OLED', True)):
                await display_message("TMON Starting", 1.2)
        except Exception:
            pass

        # Idle loop to update system metrics and keep loop alive
        _last_gc_ms = time.ticks_ms()
        _gc_interval_ms = 300 * 1000  # 300 seconds

        while True:
            try:
                try:
                    sdata.script_runtime = get_script_runtime()  # CHANGED: was empty block
                except Exception:
                    pass

                await asyncio.sleep(10)

                try:
                    # CHANGED: runGC is async in utils.py
                    await runGC()
                except Exception:
                    pass

            except Exception:
                await asyncio.sleep(5)

    if __name__ == '__main__':
        # CHANGED: make runner block structurally unambiguous for CPython parsing
        try:
            asyncio.run(main())
        except Exception as _run_exc:
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(main())
                loop.run_forever()
            except Exception as _loop_exc:
                try:
                    print("main.py event loop bootstrap failed:", _run_exc, _loop_exc)
                except Exception:
                    pass
                raise

except Exception as _boot_exc:
    # NEW: close the outer try to avoid SyntaxError on CPython, and keep boot resilient.
    try:
        # Best-effort minimal diagnostics without assuming debug_print is available
        print("main.py bootstrap failed:", _boot_exc)
    except Exception:
        pass