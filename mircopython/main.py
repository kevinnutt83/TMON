# Firmware Version: v.2.00i



# --- Single-threaded asyncio event loop ---
import uasyncio as asyncio
import settings
from debug import info as dbg_info, warn as dbg_warn, error as dbg_error
import sdata
import utime as time
from sampling import sampleEnviroment
from utils import free_pins, checkLogDirectory, debug_print, periodic_field_data_send, load_persisted_unit_id, persist_unit_id, get_machine_id
from lora import connectLora, log_error, TMON_AI
from ota import check_for_update
from oled import update_display
import ujson as json
import uos as os
try:
    import urequests as requests
except Exception:
    requests = None
from wifi import disable_wifi, connectToWifiNetwork, wifi_rssi_monitor
from utils import get_machine_id

checkLogDirectory()

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
                await debug_print("LoRa init failed, retrying...", "WARN")
                for _ in range(10):
                    await asyncio.sleep(1)
        except Exception as e:
            led_status_flash('ERROR')
            error_msg = f"Unexpected error in lora_comm_task: {e}"
            if "blocking" in error_msg:
                error_msg += " | .blocking attribute does not exist on SX1262."
            await debug_print(error_msg, "ERROR")
            await log_error(error_msg)
            await free_pins()
            for _ in range(10):
                await asyncio.sleep(1)
        loop_runtime = (time.ticks_ms() - loop_start_time) // 1000
        led_status_flash('INFO')
        await debug_print(f"lora_comm_task loop runtime: {loop_runtime}s | script runtime: {get_script_runtime()}s", "TASK")
        await asyncio.sleep(1)

import gc
import machine

async def sample_task():
    loop_start_time = time.ticks_ms()
    from utils import led_status_flash
    led_status_flash('INFO')  # Always flash LED for info
    # Skip sampling if suspended
    if getattr(settings, 'DEVICE_SUSPENDED', False):
        await debug_print("Device suspended; skipping sampling", "WARN")
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
    if getattr(settings, 'DEBUG', False):
        print(f"[DEBUG] sample_task: loop_runtime={sdata.loop_runtime}, script_runtime={sdata.script_runtime}, free_mem={sdata.free_mem}")
    record_field_data()
    await debug_print(f"sample_task: loop_runtime: {sdata.loop_runtime}s | script_runtime: {sdata.script_runtime}s | free_mem: {sdata.free_mem}", "INFO")
    led_status_flash('INFO')  # Always flash LED for info

async def periodic_field_data_task():
    from utils import send_field_data_log
    while True:
        # Run send sequentially to avoid overlapping uploads (reduces memory pressure)
        try:
            if getattr(settings, 'DEVICE_SUSPENDED', False):
                await debug_print("Device suspended; skip field data send", "WARN")
            else:
                await send_field_data_log()
        except Exception as e:
            await debug_print(f"field_data_task error: {e}", "ERROR")
        await asyncio.sleep(settings.FIELD_DATA_SEND_INTERVAL)

async def periodic_command_poll_task():
    try:
        from wprest import poll_device_commands
    except Exception:
        poll_device_commands = None
    while True:
        if poll_device_commands and not getattr(settings, 'DEVICE_SUSPENDED', False):
            try:
                await poll_device_commands()
            except Exception as e:
                await debug_print(f"Command poll error: {e}", "ERROR")
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
        body = {'unit_id': settings.UNIT_ID, 'machine_id': mid}
        url = hub.rstrip('/') + '/wp-json/tmon-admin/v1/device/check-in'
        resp = requests.post(url, json=body)
        ok = (resp is not None and getattr(resp, 'status_code', 0) == 200)
        if ok:
            # Persist flag
            try:
                with open(flag, 'w') as f:
                    f.write('ok')
            except Exception:
                pass
            # If UNIT_ID returned in body, persist
            try:
                resp_json = resp.json()
                new_uid = resp_json.get('unit_id') if isinstance(resp_json, dict) else None
                if new_uid and str(new_uid) != str(settings.UNIT_ID):
                    settings.UNIT_ID = str(new_uid)
                    persist_unit_id(settings.UNIT_ID)
            except Exception:
                pass
            # If remote node, disable WiFi after provisioning
            if getattr(settings, 'NODE_TYPE', 'base') == 'remote' and getattr(settings, 'WIFI_DISABLE_AFTER_PROVISION', True):
                disable_wifi()
    except Exception as e:
        await debug_print('Provisioning check-in failed: %s' % e, 'ERROR')


async def startup():
    tm = TaskManager()
    # Run first-boot provisioning before normal tasks
    try:
        await first_boot_provision()
    except Exception as e:
        await debug_print('first_boot_provision error: %s' % e, 'ERROR')
    tm.add_task(lora_comm_task, 'lora', 1)
    tm.add_task(sample_task, 'sample', 60)
    if getattr(settings, 'NODE_TYPE', 'base') == 'base':
        tm.add_task(periodic_field_data_task, 'field_data', settings.FIELD_DATA_SEND_INTERVAL)
        tm.add_task(periodic_command_poll_task, 'cmd_poll', 10)
    # Background periodic tasks (standalone loops)
    try:
        import uasyncio as _a
        _a.create_task(wifi_rssi_monitor())
    except Exception:
        pass
    # OLED background update with optional page rotation
    async def _oled_loop():
        page = 0
        try:
            upd = int(getattr(settings, 'OLED_UPDATE_INTERVAL_S', 10))
            rotate_s = int(getattr(settings, 'OLED_PAGE_ROTATE_INTERVAL_S', 30))
            scroll = bool(getattr(settings, 'OLED_SCROLL_ENABLED', False))
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
        import uasyncio as _a3
        _a3.create_task(_oled_loop())
    except Exception:
        pass
    async def ota_version_task():
        while True:
            try:
                await check_for_update()
            except Exception:
                pass
            await asyncio.sleep(getattr(settings, 'OTA_CHECK_INTERVAL_S', 1800))
    try:
        import uasyncio as _a2
        _a2.create_task(ota_version_task())
    except Exception:
        pass
    await tm.run()

def run_asyncio_thread():
    import uasyncio as asyncio
    asyncio.run(startup())


# Run the asyncio event loop in the main thread
import uasyncio as asyncio
asyncio.run(startup())

# If blocking tasks are added later, start them in a separate thread here