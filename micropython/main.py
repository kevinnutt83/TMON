# Firmware Version: v2.06.0

# --- Single-threaded asyncio event loop ---
import uasyncio as asyncio
import settings
from debug import info as dbg_info, warn as dbg_warn, error as dbg_error
import sdata
import utime as time
from sampling import sampleEnviroment
from utils import free_pins_lora, checkLogDirectory, debug_print, load_persisted_unit_name, periodic_field_data_send, load_persisted_unit_id, persist_unit_id, get_machine_id, periodic_provision_check
from lora import connectLora, log_error, TMON_AI, check_missed_syncs
from ota import check_for_update, apply_pending_update
from oled import update_display, display_message
from settings_apply import load_applied_settings_on_boot, settings_apply_loop
try:
    from engine_controller import engine_loop
except Exception:
    engine_loop = None
import ujson as json
import uos as os
try:
    import urequests as requests
except Exception:
    requests = None
from wifi import disable_wifi, connectToWifiNetwork, wifi_rssi_monitor
# duplicate import removed

checkLogDirectory()

# Apply any previously applied settings snapshot on boot
try:
    load_applied_settings_on_boot()
except Exception:
    pass

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

# NEW: load persisted WORDPRESS_API_URL before starting tasks
try:
    from utils import load_persisted_wordpress_api_url
    load_persisted_wordpress_api_url()
except Exception:
    pass

# NEW: simple provisioned check (flag existence or configured hub URL)
_provision_warned = False
def is_provisioned():
    global _provision_warned
    try:
        flag = getattr(settings, 'PROVISIONED_FLAG_FILE', '/logs/provisioned.flag')
        wp_url = str(getattr(settings, 'WORDPRESS_API_URL', '')).strip()
        # If a hub URL is configured, allow tasks to proceed even if the flag is missing
        if wp_url:
            return True
        try:
            os.stat(flag)
            return True
        except Exception:
            pass
    except Exception:
        pass
    if not _provision_warned:
        # One-time warning so we know tasks are gated
        try:
            print('[WARN] Device not marked provisioned (no flag or WORDPRESS_API_URL).')
        except Exception:
            pass
        _provision_warned = True
    return False

# Load persisted NODE_TYPE if available before starting tasks
try:
    from utils import load_persisted_node_type
    _nt = load_persisted_node_type()
    if _nt:
        settings.NODE_TYPE = _nt
except Exception:
    pass

def get_script_runtime():
    now = time.ticks_ms()
    return (now - script_start_time) // 1000

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
                await log_error(f"Task {t['name']} error: {e}")
            t['last_run'] = time.ticks_ms()
            elapsed = (t['last_run'] - start) // 1000
            sleep_time = max(0, t['interval'] - elapsed)
            await asyncio.sleep(sleep_time)

async def lora_comm_task():
    """Periodic LoRa communication init/retry loop."""
    global sdata
    from utils import led_status_flash
    while True:
        loop_start_time = time.ticks_ms()
        led_status_flash('INFO')
        result = None
        error_msg = None
        # Defensive init
        if not hasattr(sdata, 'loop_runtime'):
            sdata.loop_runtime = 0
        if not hasattr(sdata, 'script_runtime'):
            sdata.script_runtime = 0
        try:
            sdata.loop_runtime = (time.ticks_ms() - loop_start_time) // 1000
            sdata.script_runtime = get_script_runtime()
            if getattr(settings, 'DEVICE_SUSPENDED', False):
                await debug_print("Device suspended; skipping LoRa connect", "WARN")
                result = None
            else:
                result = await connectLora()
            if result is False:
                led_status_flash('WARN')
                await debug_print("lora: init fail, retry", "WARN")
                for _ in range(10):
                    await asyncio.sleep(1)
        except Exception as e:
            led_status_flash('ERROR')
            error_msg = f"lora_task err: {e}"
            if "blocking" in error_msg:
                error_msg += " | .blocking attribute does not exist on SX1262."
            await debug_print(error_msg, "ERROR")
            await log_error(error_msg)
            await free_pins_lora()
            for _ in range(10):
                await asyncio.sleep(1)
        loop_runtime = (time.ticks_ms() - loop_start_time) // 1000
        led_status_flash('INFO')
        await debug_print(f"lora_comm_task loop runtime: {loop_runtime}s | script runtime: {get_script_runtime()}s", "TASK")
        await asyncio.sleep(1)

import gc
import machine

async def sample_task():
    if not is_provisioned():
        await asyncio.sleep(1)
        return
    loop_start_time = time.ticks_ms()
    from utils import led_status_flash
    led_status_flash('INFO')
    # Skip sampling if suspended
    if getattr(settings, 'DEVICE_SUSPENDED', False):
        await debug_print("suspended: skip sample", "WARN")
    else:
        await sampleEnviroment()
    sdata.loop_runtime = (time.ticks_ms() - loop_start_time) // 1000
    sdata.script_runtime = get_script_runtime()
    sdata.free_mem = gc.mem_free()
    try:
        led_status_flash('SUCCESS')  # Always flash LED for success
        sdata.cpu_temp = machine.ADC(4).read_u16() * 3.3 / 65535
    except Exception:
        led_status_flash('ERROR')  # Always flash LED for error
        sdata.cpu_temp = 0
    from utils import update_sys_voltage, record_field_data
    sdata.sys_voltage = update_sys_voltage()
    sdata.error_count = getattr(TMON_AI, 'error_count', 0)
    sdata.last_error = getattr(TMON_AI, 'last_error', '')
    # Shortened debug print; consider making it conditional on settings.DEBUG
    record_field_data()
    await debug_print(f"sample: lr={sdata.loop_runtime}s sr={sdata.script_runtime}s mem={sdata.free_mem}", "INFO")
    # NEW: GC after sampling + record persistence
    try:
        from utils import maybe_gc
        maybe_gc("sample_task", min_interval_ms=5000, mem_free_below=35 * 1024)
    except Exception:
        pass
    led_status_flash('INFO')  # Always flash LED for info

async def periodic_field_data_task():
    from utils import send_field_data_log
    while True:
        if not is_provisioned():
            await asyncio.sleep(2)
            continue
        # Run send sequentially to avoid overlapping uploads (reduces memory pressure)
        try:
            if getattr(settings, 'DEVICE_SUSPENDED', False):
                await debug_print("suspended: skip sfd send", "WARN")
            else:
                await send_field_data_log()
        except Exception as e:
            await debug_print(f"sfd: task err {e}", "ERROR")
        # NEW: GC after HTTP/upload attempts
        try:
            from utils import maybe_gc
            maybe_gc("field_data_send", min_interval_ms=12000, mem_free_below=40 * 1024)
        except Exception:
            pass
        await asyncio.sleep(settings.FIELD_DATA_SEND_INTERVAL)

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
            # NEW: GC after command poll (JSON + handlers)
            try:
                from utils import maybe_gc
                maybe_gc("cmd_poll", min_interval_ms=12000, mem_free_below=40 * 1024)
            except Exception:
                pass
        await asyncio.sleep(10)


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
    # Require admin URL configured
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
        # Add a small timeout to avoid hanging on boot
        try:
            resp = requests.post(url, json=body, timeout=10)
        except TypeError:
            # Some urequests versions don't support timeout kwarg
            resp = requests.post(url, json=body)
        ok = (resp is not None and getattr(resp, 'status_code', 0) == 200)
        if ok:
            # Persist flag
            try:
                with open(flag, 'w') as f:
                    f.write('ok')
            except Exception:
                pass
            # Mark device as provisioned in-memory so other tasks (esp. remotes) stop HTTP usage
            try:
                settings.UNIT_PROVISIONED = True
            except Exception:
                pass
            # Restore: do not overwrite UNIT_ID with blank values
            try:
                resp_json = resp.json()
            except Exception:
                resp_json = {}
            # Persist unit name when returned during check-in
            try:
                unit_name = (resp_json.get('unit_name') or '').strip()
                if unit_name:
                    try:
                        from utils import persist_unit_name
                        persist_unit_name(unit_name)
                        settings.UNIT_Name = unit_name
                        await debug_print('first_boot_provision: UNIT_Name persisted', 'PROVISION')
                    except Exception:
                        pass
            except Exception:
                pass
            # Restore: do not overwrite UNIT_ID with blank values
            try:
                new_uid = resp_json.get('unit_id')
                if new_uid and str(new_uid).strip():
                    if str(new_uid).strip() != str(settings.UNIT_ID):
                        settings.UNIT_ID = str(new_uid).strip()
                        persist_unit_id(settings.UNIT_ID)
                        await debug_print('first_boot_provision: UNIT_ID persisted', 'PROVISION')
            except Exception:
                pass
            # User-friendly OLED notice
            try:
                await display_message("Provisioned", 2)
            except Exception:
                pass
            # Restore: persist provisioning metadata (site_url to WORDPRESS_API_URL) and soft reset once
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
                        from utils import persist_wordpress_api_url
                        persist_wordpress_api_url(site_val)
                    except Exception:
                        pass
                if role_val:
                    try:
                        settings.NODE_TYPE = role_val
                    except Exception:
                        pass
            except Exception:
                pass
            # Soft reset once after successful provision to apply any changes
            try:
                machine.soft_reset()
            except Exception:
                pass
        else:
            # User-friendly notice for failure
            try:
                await display_message("Provision Failed", 2)
            except Exception:
                pass
    except Exception as e:
        await debug_print(f'first_boot_provision err {e}', 'ERROR')

tm = TaskManager()
tm.add_task(first_boot_provision, 'first_boot_provision', 0)  # Run once
tm.add_task(sample_task, 'sample', 30)
tm.add_task(lora_comm_task, 'lora_comm', 1)
tm.add_task(periodic_field_data_task, 'field_data', settings.FIELD_DATA_SEND_INTERVAL)
tm.add_task(periodic_command_poll_task, 'command_poll', 10)
tm.add_task(check_for_update, 'ota_check', 3600)  # Example interval
tm.add_task(apply_pending_update, 'ota_apply', settings.OTA_APPLY_INTERVAL_S)
tm.add_task(update_display, 'display', settings.OLED_UPDATE_INTERVAL_S)
tm.add_task(settings_apply_loop, 'settings_apply', 60)
if engine_loop:
    tm.add_task(engine_loop, 'engine', settings.ENGINE_POLL_INTERVAL_S)
tm.add_task(wifi_rssi_monitor, 'wifi_rssi', settings.WIFI_SIGNAL_SAMPLE_INTERVAL_S)
tm.add_task(periodic_provision_check, 'provision_check', settings.PROVISION_CHECK_INTERVAL_S)
tm.add_task(check_missed_syncs, 'missed_syncs', 60)
asyncio.run(tm.run())
