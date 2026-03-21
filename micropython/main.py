# TMON v2.01.0 - Main entry (LoRa on Core 1, CLI + all tasks on Core 0)
# Dual-core architecture: LoRa runs on core 1 (never impeded). Full CLI listener added.
# All original logic preserved + streamlined error handling and GC calls.
# Heavy imports (lora, sampling, engine_controller, settings_apply) deferred
# to reduce C stack depth during module loading on ESP32-S3.

import uasyncio as asyncio
import settings
import sdata
import utime as time
import machine
from utils import (
    checkLogDirectory, debug_print, load_persisted_unit_name,
    load_persisted_unit_id, persist_unit_id, get_machine_id,
    periodic_provision_check, load_persisted_wordpress_api_url,
    load_persisted_node_type, handle_user_command
)
from ota import check_for_update, apply_pending_update
from wifi import connectToWifiNetwork, wifi_rssi_monitor
import uos as os
import gc

# Deferred heavy modules — loaded on first use to reduce import-time stack depth
_lora_mod = None
_sampling_mod = None
_settings_apply_mod = None
_engine_mod = None

def _get_lora():
    global _lora_mod
    if _lora_mod is None:
        import lora as _m
        _lora_mod = _m
    return _lora_mod

def _get_sampling():
    global _sampling_mod
    if _sampling_mod is None:
        import sampling as _m
        _sampling_mod = _m
    return _sampling_mod

def _get_settings_apply():
    global _settings_apply_mod
    if _settings_apply_mod is None:
        import settings_apply as _m
        _settings_apply_mod = _m
    return _settings_apply_mod

def _get_engine():
    global _engine_mod
    if _engine_mod is None:
        try:
            import engine_controller as _m
            _engine_mod = _m
        except Exception:
            _engine_mod = False
    return _engine_mod

try:
    import urequests as requests
except Exception:
    requests = None

# Lazy OLED import wrappers
async def _update_display(page=0):
    try:
        from oled import update_display
        await update_display(page)
    except Exception:
        pass

async def _display_message(msg, duration=1.5):
    try:
        from oled import display_message
        await display_message(msg, duration)
    except Exception:
        pass

checkLogDirectory()

# Apply any previously applied settings snapshot on boot
try:
    _get_settings_apply().load_applied_settings_on_boot()
except Exception:
    pass

# Pre-load lora module at module level (outside asyncio.run) so its deep
# import chain (sx1262 → sx126x → _sx126x, sampling → tmon, relay, wprest)
# runs with a fresh C stack. Dependencies (utils, settings, sdata) are already
# cached from earlier imports, keeping incremental depth ~3-4 levels.
_get_lora()
gc.collect()

script_start_time = time.ticks_ms()

# Detect and persist MACHINE_ID on first boot if missing
try:
    if settings.MACHINE_ID is None:
        mid = get_machine_id()
        if mid:
            settings.MACHINE_ID = mid
            try:
                with open(settings.MACHINE_ID_FILE, 'w') as f:
                    f.write(mid)
            except Exception:
                pass
except Exception:
    pass

# Load persisted UNIT_ID mapping if available
try:
    stored_uid = load_persisted_unit_id()
    if stored_uid and str(stored_uid) != str(settings.UNIT_ID):
        settings.UNIT_ID = str(stored_uid)
    print(f"[BOOT] Loaded persisted UNIT_ID: {settings.UNIT_ID}")
except Exception:
    pass

# Load persisted UNIT_Name mapping if available
try:
    stored_uname = load_persisted_unit_name()
    if stored_uname and str(stored_uname) != str(settings.UNIT_Name):
        settings.UNIT_Name = str(stored_uname)
    print(f"[BOOT] Loaded persisted UNIT_Name: {settings.UNIT_Name}")
except Exception:
    pass

# Load persisted WORDPRESS_API_URL before starting tasks
try:
    load_persisted_wordpress_api_url()
except Exception:
    pass

# Load persisted NODE_TYPE if available before starting tasks
try:
    _nt = load_persisted_node_type()
    if _nt:
        settings.NODE_TYPE = _nt
except Exception:
    pass

def get_script_runtime():
    now = time.ticks_ms()
    return (now - script_start_time) // 1000

# Simple provisioned check
_provision_warned = False
def is_provisioned():
    global _provision_warned
    try:
        flag = getattr(settings, 'PROVISIONED_FLAG_FILE', '/logs/provisioned.flag')
        wp_url = str(getattr(settings, 'WORDPRESS_API_URL', '')).strip()
        if wp_url:
            return True
        os.stat(flag)
        return True
    except Exception:
        if not _provision_warned:
            print('[WARN] Device not marked provisioned (no flag or WORDPRESS_API_URL).')
            _provision_warned = True
        return False

class TaskManager:
    def __init__(self):
        self.tasks = []
    def add_task(self, coro_func, name, interval):
        self.tasks.append({
            'coro_func': coro_func,
            'name': name,
            'interval': interval,
            'last_run': 0,
            'task': None
        })
    async def run(self):
        for t in self.tasks:
            t['task'] = asyncio.create_task(self._task_wrapper(t))
        await asyncio.gather(*(t['task'] for t in self.tasks if t['task'] is not None))
    async def _task_wrapper(self, t):
        while True:
            start = time.ticks_ms()
            try:
                await t['coro_func']()
            except Exception as e:
                await debug_print(f"Task {t['name']} error: {e}", "ERROR")
                try:
                    await _get_lora().log_error(f"Task {t['name']} error: {e}")
                except Exception:
                    pass
            t['last_run'] = time.ticks_ms()
            elapsed = (t['last_run'] - start) // 1000
            sleep_time = max(0, t['interval'] - elapsed)
            await asyncio.sleep(sleep_time)

# First-boot provisioning check-in
async def first_boot_provision():
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
    if not hub or not requests:
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
                    f.write('ok')
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
                    from utils import persist_unit_name
                    persist_unit_name(unit_name)
                    settings.UNIT_Name = unit_name
                    await debug_print('first_boot_provision: UNIT_Name persisted', 'PROVISION')
            except Exception:
                pass
            try:
                new_uid = resp_json.get('unit_id')
                if new_uid and str(new_uid).strip():
                    if str(new_uid).strip() != str(settings.UNIT_ID):
                        settings.UNIT_ID = str(new_uid).strip()
                        persist_unit_id(settings.UNIT_ID)
                        await debug_print('first_boot_provision: UNIT_ID persisted', 'PROVISION')
            except Exception:
                pass
            await _display_message("Provisioned", 2)
            try:
                site_val = (resp_json.get('site_url') or resp_json.get('wordpress_api_url') or '').strip()
                role_val = (resp_json.get('role') or '').strip()
                if site_val:
                    from utils import persist_wordpress_api_url
                    persist_wordpress_api_url(site_val)
                if role_val:
                    settings.NODE_TYPE = role_val
            except Exception:
                pass
            try:
                machine.soft_reset()
            except Exception:
                pass
        else:
            await _display_message("Provision Failed", 2)
    except Exception as e:
        await debug_print(f'first_boot_provision err {e}', 'ERROR')

# Sample task
async def sample_task():
    if not is_provisioned():
        await asyncio.sleep(1)
        return
    loop_start_time = time.ticks_ms()
    from utils import led_status_flash
    led_status_flash('INFO')
    if getattr(settings, 'DEVICE_SUSPENDED', False):
        await debug_print("suspended: skip sample", "WARN")
    else:
        await _get_sampling().sampleEnviroment()
    sdata.loop_runtime = (time.ticks_ms() - loop_start_time) // 1000
    sdata.script_runtime = get_script_runtime()
    sdata.free_mem = gc.mem_free()
    try:
        led_status_flash('SUCCESS')
        sdata.cpu_temp = machine.ADC(4).read_u16() * 3.3 / 65535
    except Exception:
        led_status_flash('ERROR')
        sdata.cpu_temp = 0
    from utils import update_sys_voltage, record_field_data
    sdata.sys_voltage = update_sys_voltage()
    _tmon_ai = getattr(_get_lora(), 'TMON_AI', None)
    sdata.error_count = getattr(_tmon_ai, 'error_count', 0) if _tmon_ai else 0
    sdata.last_error = getattr(_tmon_ai, 'last_error', '') if _tmon_ai else ''
    record_field_data()
    await debug_print(f"sample: lr={sdata.loop_runtime}s sr={sdata.script_runtime}s mem={sdata.free_mem}", "INFO")
    try:
        from utils import maybe_gc
        maybe_gc("sample_task", min_interval_ms=5000, mem_free_below=35 * 1024)
    except Exception:
        pass
    led_status_flash('INFO')

# Periodic field data task
async def periodic_field_data_task():
    from utils import send_field_data_log
    while True:
        if not is_provisioned():
            await asyncio.sleep(2)
            continue
        try:
            if getattr(settings, 'DEVICE_SUSPENDED', False):
                await debug_print("suspended: skip sfd send", "WARN")
            else:
                await send_field_data_log()
        except Exception as e:
            await debug_print(f"sfd: task err {e}", "ERROR")
        try:
            from utils import maybe_gc
            maybe_gc("field_data_send", min_interval_ms=12000, mem_free_below=40 * 1024)
        except Exception:
            pass
        await asyncio.sleep(settings.FIELD_DATA_SEND_INTERVAL)

# Periodic command poll task
async def periodic_command_poll_task():
    try:
        from wprest import poll_device_commands
    except Exception:
        poll_device_commands = None
    while True:
        if not is_provisioned():
            await asyncio.sleep(2)
            continue
        if poll_device_commands and not getattr(settings, 'DEVICE_SUSPENDED', False):
            try:
                await poll_device_commands()
            except Exception as e:
                await debug_print(f"Command poll error: {e}", "ERROR")
            try:
                from utils import maybe_gc
                maybe_gc("cmd_poll", min_interval_ms=12000, mem_free_below=40 * 1024)
            except Exception:
                pass
        await asyncio.sleep(10)

# ========================== TASK SETUP ==========================
# settings_apply_loop and engine_loop wrapped for deferred import
async def _settings_apply_loop_wrapper():
    await _get_settings_apply().settings_apply_loop()

async def _engine_loop_wrapper():
    mod = _get_engine()
    if mod and mod is not False:
        await mod.engine_loop()

async def _check_missed_syncs_wrapper():
    await _get_lora().check_missed_syncs()

tm = TaskManager()
tm.add_task(first_boot_provision, 'first_boot_provision', 0)
if settings.SAMPLE_TEMP or settings.SAMPLE_HUMIDITY or settings.SAMPLE_PRESSURE or settings.SAMPLE_GAS:
    tm.add_task(sample_task, 'sample', 30)
tm.add_task(periodic_field_data_task, 'field_data', settings.FIELD_DATA_SEND_INTERVAL)
tm.add_task(periodic_command_poll_task, 'command_poll', 10)
tm.add_task(check_for_update, 'ota_check', 3600)
tm.add_task(apply_pending_update, 'ota_apply', settings.OTA_APPLY_INTERVAL_S)
if settings.ENABLE_OLED:
    tm.add_task(_update_display, 'display', settings.OLED_UPDATE_INTERVAL_S)
tm.add_task(_settings_apply_loop_wrapper, 'settings_apply', 60)
if getattr(settings, 'ENABLE_ENGINE_CONTROLLER', False):
    tm.add_task(_engine_loop_wrapper, 'engine', settings.ENGINE_POLL_INTERVAL_S)
tm.add_task(wifi_rssi_monitor, 'wifi_rssi', settings.WIFI_SIGNAL_SAMPLE_INTERVAL_S)
tm.add_task(periodic_provision_check, 'provision_check', settings.PROVISION_CHECK_INTERVAL_S)
tm.add_task(_check_missed_syncs_wrapper, 'missed_syncs', 60)

# Non-blocking CLI listener
async def cli_listener():
    import sys, select
    while True:
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            cmd = sys.stdin.readline().strip()
            if cmd:
                await handle_user_command(cmd)
        await asyncio.sleep_ms(200)

tm.add_task(cli_listener, 'cli', 0)

# LoRa runs as an asyncio task on the same event loop.
# MicroPython's uasyncio uses module-level globals (_task_queue, _io_queue)
# shared across all threads. Calling asyncio.run() on Core 1 replaces these
# globals, corrupting Core 0's active event loop and causing a NULL dereference
# (EXCVADDR: 0x0000000c). Running LoRa as a cooperative asyncio task avoids
# this entirely — connectLora() already yields at every await point.
async def _lora_task():
    try:
        await _lora_mod.connectLora()
    except Exception as e:
        await debug_print(f"LoRa task fatal: {e}", "ERROR")

async def main():
    lora_t = asyncio.create_task(_lora_task())
    await asyncio.sleep(0.1)
    await debug_print("LoRa started as async task", "LORA")
    await tm.run()

asyncio.run(main())
