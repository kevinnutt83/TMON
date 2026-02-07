# Firmware Version: v2.06.0

# --- Single-threaded asyncio event loop ---
from platform_compat import asyncio, time, os, gc, machine, requests  # CHANGED

import sys  # RESTORED
import types  # RESTORED
import settings  # RESTORED
import sdata  # RESTORED

from debug import info as dbg_info, warn as dbg_warn, error as dbg_error  # RESTORED
from sampling import sampleEnviroment  # RESTORED
from utils import (
    free_pins_lora,
    checkLogDirectory,
    debug_print,
    load_persisted_unit_name,
    load_persisted_unit_id,
    persist_unit_id,
    get_machine_id,
    periodic_provision_check,
)  # RESTORED

from ota import check_for_update, apply_pending_update  # RESTORED
from oled import update_display, display_message  # RESTORED
from settings_apply import load_applied_settings_on_boot, settings_apply_loop  # RESTORED

# Guarded optional engine controller
try:
    from engine_controller import engine_loop  # type: ignore
except Exception:
    engine_loop = None

# Guarded WiFi imports (Zero-safe)
try:
    from wifi import disable_wifi, connectToWifiNetwork, wifi_rssi_monitor  # type: ignore
except Exception:
    disable_wifi = None
    connectToWifiNetwork = None
    wifi_rssi_monitor = None

# Guard LoRa import for Zero/CPython (keeps booting even if LoRa stack not present)
try:
    _mcu = str(getattr(settings, "MCU_TYPE", "")).lower()
except Exception:
    _mcu = ""
try:
    _is_micropython = bool(getattr(sys, "implementation", None) and sys.implementation.name == "micropython")
except Exception:
    _is_micropython = False
IS_ZERO_RUNTIME = (_mcu == "zero") or (not _is_micropython)  # NEW

if (_mcu == "zero") or (not _is_micropython):
    try:
        from lora import connectLora, log_error, TMON_AI  # type: ignore
    except Exception:
        connectLora = None
        TMON_AI = None

        async def log_error(error_msg):
            try:
                await debug_print(f"lora unavailable on zero: {error_msg}", "WARN")
            except Exception:
                pass
else:
    from lora import connectLora, log_error, TMON_AI  # type: ignore

# --- Zero/CPython shims for MicroPython-only modules (keeps legacy imports satisfied) ---
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
            if name not in sys.modules and mod is not None:
                sys.modules[name] = mod
        except Exception:
            pass

    # stdlib aliases
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

    # expose platform_compat-selected libs under legacy names
    try:
        if requests is not None:
            _ensure_mod("urequests", requests)
    except Exception:
        pass
    try:
        if asyncio is not None:
            _ensure_mod("uasyncio", asyncio)
    except Exception:
        pass

    # machine stub (only if truly missing)
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

                def init(self, *a, **kw):
                    return None

            class ADC:
                def __init__(self, *a, **kw):
                    pass

                def read_u16(self):
                    return 0

            def soft_reset():
                raise SystemExit("soft_reset requested")

            def reset():
                raise SystemExit("reset requested")

            _m.Pin = Pin
            _m.ADC = ADC
            _m.soft_reset = soft_reset
            _m.reset = reset
            _ensure_mod("machine", _m)

    # network stub (keeps wifi.py import-safe)
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

# --- Boot-time initialization restored from earlier v2.06.0 ---
checkLogDirectory()

try:
    load_applied_settings_on_boot()
except Exception:
    pass

script_start_time = time.ticks_ms()

# Detect and persist MACHINE_ID on first boot if missing
try:
    if getattr(settings, "MACHINE_ID", None) is None:
        mid = get_machine_id()
        if mid:
            settings.MACHINE_ID = mid
            try:
                with open(getattr(settings, "MACHINE_ID_FILE", "/logs/machine_id.txt"), "w") as f:
                    f.write(mid)
            except Exception:
                pass
except Exception:
    pass

# Load persisted UNIT_ID if available
try:
    stored_uid = load_persisted_unit_id()
    if stored_uid and str(stored_uid) != str(getattr(settings, "UNIT_ID", "")):
        settings.UNIT_ID = str(stored_uid)
except Exception:
    pass

# Load persisted UNIT_Name if available
try:
    stored_uname = load_persisted_unit_name()
    if stored_uname and str(stored_uname) != str(getattr(settings, "UNIT_Name", "")):
        settings.UNIT_Name = str(stored_uname)
except Exception:
    pass

# Load persisted WORDPRESS_API_URL before starting tasks
try:
    from utils import load_persisted_wordpress_api_url  # type: ignore
    load_persisted_wordpress_api_url()
except Exception:
    pass

# Load persisted NODE_TYPE before starting tasks
try:
    from utils import load_persisted_node_type  # type: ignore
    _nt = load_persisted_node_type()
    if _nt:
        settings.NODE_TYPE = _nt
except Exception:
    pass

_provision_warned = False
def is_provisioned():
    # RESTORED: earlier semantics (flag OR configured WORDPRESS_API_URL) with one-time warning
    global _provision_warned
    try:
        wp_url = str(getattr(settings, "WORDPRESS_API_URL", "")).strip()
        if wp_url:
            return True
        flag = getattr(settings, "PROVISIONED_FLAG_FILE", "/logs/provisioned.flag")
        try:
            os.stat(flag)
            return True
        except Exception:
            pass
    except Exception:
        pass
    if not _provision_warned:
        try:
            print("[WARN] Device not marked provisioned (no flag or WORDPRESS_API_URL).")
        except Exception:
            pass
        _provision_warned = True
    return False

def get_script_runtime():
    now = time.ticks_ms()
    return (now - script_start_time) // 1000

# --- Scheduler restored from earlier v2.06.0 ---
class TaskManager:
    def __init__(self):
        self.tasks = []

    def add_task(self, coro_func, name, interval):
        self.tasks.append({
            "coro_func": coro_func,
            "name": name,
            "interval": int(interval) if interval else 1,
            "last_run": 0,
            "task": None,
        })

    async def run(self):
        for t in self.tasks:
            try:
                t["task"] = asyncio.create_task(self._task_wrapper(t))
            except Exception:
                t["task"] = None
        # gather is not always available/desired on all uasyncio builds; keep simple
        while True:
            await asyncio.sleep(3600)

    async def _task_wrapper(self, t):
        while True:
            start = time.ticks_ms()
            try:
                await t["coro_func"]()
            except Exception as e:
                try:
                    await debug_print(f"Task {t['name']} error: {e}", "ERROR")
                except Exception:
                    pass
                try:
                    await log_error(f"Task {t['name']} error: {e}")
                except Exception:
                    pass
            t["last_run"] = time.ticks_ms()
            try:
                elapsed = (t["last_run"] - start) // 1000
            except Exception:
                elapsed = 0
            sleep_time = max(0, int(t["interval"]) - int(elapsed))
            await asyncio.sleep(sleep_time)

# --- Tasks restored from earlier v2.06.0 ---
async def lora_comm_task():
    """Periodic LoRa communication init/retry loop."""
    if connectLora is None:
        await asyncio.sleep(2)
        return
    from utils import led_status_flash  # type: ignore

    loop_start_time = time.ticks_ms()
    led_status_flash("INFO")

    if not hasattr(sdata, "loop_runtime"):
        sdata.loop_runtime = 0
    if not hasattr(sdata, "script_runtime"):
        sdata.script_runtime = 0

    try:
        sdata.loop_runtime = (time.ticks_ms() - loop_start_time) // 1000
        sdata.script_runtime = get_script_runtime()

        if getattr(settings, "DEVICE_SUSPENDED", False):
            await debug_print("Device suspended; skipping LoRa connect", "WARN")
        else:
            res = await connectLora()
            if res is False:
                led_status_flash("WARN")
                await debug_print("lora: init fail, retry", "WARN")
                for _ in range(10):
                    await asyncio.sleep(1)
    except Exception as e:
        led_status_flash("ERROR")
        msg = f"lora_task err: {e}"
        if "blocking" in msg:
            msg += " | .blocking attribute does not exist on SX1262."
        await debug_print(msg, "ERROR")
        try:
            await log_error(msg)
        except Exception:
            pass
        try:
            await free_pins_lora()
        except Exception:
            pass
        for _ in range(10):
            await asyncio.sleep(1)

    loop_runtime = (time.ticks_ms() - loop_start_time) // 1000
    led_status_flash("INFO")
    await debug_print(
        f"lora_comm_task loop runtime: {loop_runtime}s | script runtime: {get_script_runtime()}s",
        "TASK",
    )
    await asyncio.sleep(1)

async def sample_task():
    if not is_provisioned():
        await asyncio.sleep(1)
        return

    loop_start_time = time.ticks_ms()
    from utils import led_status_flash, update_sys_voltage, record_field_data  # type: ignore

    led_status_flash("INFO")

    if getattr(settings, "DEVICE_SUSPENDED", False):
        await debug_print("suspended: skip sample", "WARN")
    else:
        await sampleEnviroment()

    try:
        sdata.loop_runtime = (time.ticks_ms() - loop_start_time) // 1000
        sdata.script_runtime = get_script_runtime()
    except Exception:
        pass

    try:
        sdata.free_mem = gc.mem_free()
    except Exception:
        sdata.free_mem = 0

    try:
        led_status_flash("SUCCESS")
        # best-effort CPU temp (platform-dependent)
        try:
            sdata.cpu_temp = machine.ADC(4).read_u16() * 3.3 / 65535
        except Exception:
            sdata.cpu_temp = 0
    except Exception:
        try:
            led_status_flash("ERROR")
        except Exception:
            pass
        sdata.cpu_temp = 0

    try:
        sdata.sys_voltage = update_sys_voltage()
    except Exception:
        pass
    try:
        sdata.error_count = getattr(TMON_AI, "error_count", 0) if TMON_AI else 0
        sdata.last_error = getattr(TMON_AI, "last_error", "") if TMON_AI else ""
    except Exception:
        pass

    try:
        record_field_data()
    except Exception:
        pass

    await debug_print(
        f"sample: lr={getattr(sdata,'loop_runtime',0)}s sr={getattr(sdata,'script_runtime',0)}s mem={getattr(sdata,'free_mem',0)}",
        "INFO",
    )

    try:
        from utils import maybe_gc  # type: ignore
        maybe_gc("sample_task", min_interval_ms=5000, mem_free_below=35 * 1024)
    except Exception:
        pass

    led_status_flash("INFO")

async def periodic_field_data_task():
    try:
        from utils import send_field_data_log, maybe_gc  # type: ignore
    except Exception:
        send_field_data_log = None
        maybe_gc = None

    while True:
        if not is_provisioned():
            await asyncio.sleep(2)
            continue
        try:
            if getattr(settings, "DEVICE_SUSPENDED", False):
                await debug_print("suspended: skip sfd send", "WARN")
            else:
                if send_field_data_log:
                    await send_field_data_log()
        except Exception as e:
            await debug_print(f"sfd: task err {e}", "ERROR")

        try:
            if maybe_gc:
                maybe_gc("field_data_send", min_interval_ms=12000, mem_free_below=40 * 1024)
        except Exception:
            pass

        await asyncio.sleep(int(getattr(settings, "FIELD_DATA_SEND_INTERVAL", 30)))

async def periodic_command_poll_task():
    try:
        from wprest import poll_device_commands  # type: ignore
    except Exception:
        poll_device_commands = None
    try:
        from utils import maybe_gc  # type: ignore
    except Exception:
        maybe_gc = None

    while True:
        if not is_provisioned():
            await asyncio.sleep(2)
            continue
        if poll_device_commands and not getattr(settings, "DEVICE_SUSPENDED", False):
            try:
                await poll_device_commands()
            except Exception as e:
                await debug_print(f"Command poll error: {e}", "ERROR")
            try:
                if maybe_gc:
                    maybe_gc("cmd_poll", min_interval_ms=12000, mem_free_below=40 * 1024)
            except Exception:
                pass
        await asyncio.sleep(10)

# --- Keep existing provisioning/OTA/UC logic, but ensure parsing remains valid ---
# ...existing code...
# NOTE: your existing first_boot_provision(), ota_boot_check(), periodic_uc_checkin_task()
# can remain below; restore them if they were previously blanked out during edits.

async def ota_boot_check():
    try:
        await check_for_update()
    except Exception:
        pass

async def startup():
    tm = TaskManager()

    # Run first-boot provisioning before normal tasks (only if present and usable)
    try:
        if "first_boot_provision" in globals() and callable(globals().get("first_boot_provision")):
            await globals()["first_boot_provision"]()
    except Exception as e:
        try:
            await debug_print(f"first_boot_provision error: {e}", "ERROR")
        except Exception:
            pass

    try:
        await ota_boot_check()
    except Exception:
        pass

    lora_interval = int(getattr(settings, "LORA_LOOP_INTERVAL_S", 1))
    node_role = str(getattr(settings, "NODE_TYPE", "base")).lower()

    if node_role != "wifi":
        tm.add_task(lora_comm_task, "lora", lora_interval)

    tm.add_task(sample_task, "sample", 60)

    wp_url = str(getattr(settings, "WORDPRESS_API_URL", "")).strip()
    if node_role in ("base", "wifi"):
        if wp_url:
            tm.add_task(periodic_field_data_task, "field_data", int(getattr(settings, "FIELD_DATA_SEND_INTERVAL", 30)))
        tm.add_task(periodic_command_poll_task, "cmd_poll", 10)

    # Background monitors / loops
    try:
        if wifi_rssi_monitor:
            asyncio.create_task(wifi_rssi_monitor())
    except Exception:
        pass

    # Start provisioning loop
    try:
        asyncio.create_task(periodic_provision_check())
    except Exception:
        pass

    # Staged settings apply loop
    try:
        asyncio.create_task(settings_apply_loop(int(getattr(settings, "PROVISION_CHECK_INTERVAL_S", 60))))
    except Exception:
        pass

    # OLED background update
    async def _oled_loop():
        page = 0
        if not bool(getattr(settings, "ENABLE_OLED", True)):
            return
        try:
            upd = int(getattr(settings, "OLED_UPDATE_INTERVAL_S", 10))
            rotate_s = int(getattr(settings, "OLED_PAGE_ROTATE_INTERVAL_S", 30))
            scroll = bool(getattr(settings, "OLED_SCROLL_ENABLED", False))
        except Exception:
            upd, rotate_s, scroll = 10, 30, False
        last_rotate = time.time()
        while True:
            try:
                await update_display(page)
            except Exception:
                pass
            if scroll and (time.time() - last_rotate) >= rotate_s:
                page = 1 - page
                last_rotate = time.time()
            await asyncio.sleep(upd)

    try:
        asyncio.create_task(_oled_loop())
    except Exception:
        pass

    # Periodic OTA tasks
    async def ota_version_task():
        while True:
            try:
                await check_for_update()
            except Exception:
                pass
            await asyncio.sleep(int(getattr(settings, "OTA_CHECK_INTERVAL_S", 1800)))

    async def ota_apply_task():
        while True:
            try:
                await apply_pending_update()
            except Exception:
                pass
            await asyncio.sleep(int(getattr(settings, "OTA_APPLY_INTERVAL_S", 600)))

    try:
        asyncio.create_task(ota_version_task())
    except Exception:
        pass
    try:
        asyncio.create_task(ota_apply_task())
    except Exception:
        pass

    # UC periodic check-in loop (if present)
    try:
        if "periodic_uc_checkin_task" in globals() and callable(globals().get("periodic_uc_checkin_task")):
            asyncio.create_task(globals()["periodic_uc_checkin_task"]())
    except Exception:
        pass

    # Engine loop
    try:
        if (
            engine_loop
            and not bool(getattr(settings, "ENGINE_FORCE_DISABLED", False))
            and bool(getattr(settings, "ENABLE_RS485", False))
            and bool(getattr(settings, "ENABLE_ENGINE_CONTROLLER", False))
        ):
            asyncio.create_task(engine_loop())
            await debug_print("startup: engine_loop started", "INFO")
        else:
            await debug_print("startup: engine_loop disabled", "INFO")
    except Exception as e:
        try:
            await debug_print(f"startup: engine start fail: {e}", "ERROR")
        except Exception:
            pass

    # NEW: Zero/CPython does not execute boot.py; ensure it still attempts check-in + provisioning.
    async def _zero_http_bootstrap_loop():
        # Keep best-effort and do not change MicroPython flows.
        if not IS_ZERO_RUNTIME:
            return
        try:
            from wprest import register_with_wp  # type: ignore
        except Exception:
            register_with_wp = None
        try:
            import provision  # type: ignore
        except Exception:
            provision = None

        interval = int(getattr(settings, "PROVISION_CHECK_INTERVAL_S", 30) or 30)
        while True:
            try:
                if getattr(settings, "DEVICE_SUSPENDED", False):
                    await asyncio.sleep(interval)
                    continue

                # Check-in to Admin (helps UNIT_ID assignment / registration visibility)
                if register_with_wp:
                    try:
                        await register_with_wp()
                    except Exception as e:
                        try:
                            await debug_print(f"zero_bootstrap: register err {e}", "WARN")
                        except Exception:
                            pass

                # Provisioning pull/apply (Admin → device) if not provisioned
                try:
                    is_prov = bool(getattr(settings, "UNIT_PROVISIONED", False)) or bool(str(getattr(settings, "WORDPRESS_API_URL", "")).strip())
                except Exception:
                    is_prov = False
                if (not is_prov) and provision:
                    try:
                        doc = provision.fetch_provisioning(
                            unit_id=getattr(settings, "UNIT_ID", None),
                            machine_id=getattr(settings, "MACHINE_ID", None),
                            base_url=getattr(settings, "TMON_ADMIN_API_URL", None),
                        )
                        if isinstance(doc, dict) and doc:
                            try:
                                provision.apply_settings(doc)
                            except Exception as e:
                                await debug_print(f"zero_bootstrap: apply_settings err {e}", "ERROR")
                    except Exception as e:
                        try:
                            await debug_print(f"zero_bootstrap: fetch_provisioning err {e}", "WARN")
                        except Exception:
                            pass
            except Exception:
                pass
            await asyncio.sleep(interval)

    try:
        asyncio.create_task(_zero_http_bootstrap_loop())  # NEW
    except Exception:
        pass

    await tm.run()

# Main runner (restored semantics)
from utils import start_background_tasks, runGC, update_sys_voltage  # type: ignore

async def main():
    try:
        start_background_tasks()
    except Exception:
        pass

    asyncio.create_task(startup())

    try:
        if bool(getattr(settings, "ENABLE_OLED", True)):
            await display_message("TMON Starting", 1.2)
    except Exception:
        pass

    _last_gc_ms = time.ticks_ms()
    _gc_interval_ms = 300 * 1000

    while True:
        try:
            try:
                update_sys_voltage()
            except Exception:
                pass

            await asyncio.sleep(10)

            try:
                now_ms = time.ticks_ms()
                if time.ticks_diff(now_ms, _last_gc_ms) >= _gc_interval_ms:
                    await runGC()
                    _last_gc_ms = now_ms
            except Exception:
                pass
        except Exception:
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
        except Exception:
            raise