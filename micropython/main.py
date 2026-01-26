# Firmware Version: v2.06.0



# --- Single-threaded asyncio event loop ---
import uasyncio as asyncio
import settings
from debug import info as dbg_info, warn as dbg_warn, error as dbg_error
import sdata
import utime as time
from sampling import sampleEnviroment
from utils import free_pins_lora, checkLogDirectory, debug_print, load_persisted_unit_name, periodic_field_data_send, load_persisted_unit_id, persist_unit_id, get_machine_id, periodic_provision_check
from lora import connectLora, log_error, TMON_AI
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
            # Restore: persist provisioning metadata (site_url → WORDPRESS_API_URL) and soft reset once
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
                    try:
                        persist_node_type(role_val)
                    except Exception:
                        pass
                    # if role is remote, proactively disable wifi and persist
                    try:
                        if str(role_val).lower() == 'remote':
                            try:
                                from utils import persist_node_type
                                persist_node_type(role_val)
                            except Exception:
                                pass
                            try:
                                from utils import persist_unit_name
                                # ensure unit name persisted earlier
                            except Exception:
                                pass
                            try:
                                disable_wifi()
                            except Exception:
                                pass
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
                if fw_ver:
                    try:
                        settings.FIRMWARE_VERSION = fw_ver
                    except Exception:
                        pass
                # mark provisioned flag
                if (provisioned or staged) and site_val:
                    try:
                        with open(flag, 'w') as f:
                            f.write('ok')
                    except Exception:
                        pass
                    # Mark device as provisioned in-memory
                    try:
                        settings.UNIT_PROVISIONED = True
                    except Exception:
                        pass
                    # NEW: confirm applied provisioning to Admin (best-effort)
                    try:
                        token = getattr(settings, 'TMON_ADMIN_CONFIRM_TOKEN', '')
                        confirm_url = hub.rstrip('/') + '/wp-json/tmon-admin/v1/device/confirm-applied'
                        payload = {
                            'unit_id': settings.UNIT_ID,
                            'machine_id': mid,
                            'wordpress_api_url': site_val,
                            'role': settings.NODE_TYPE,
                            'unit_name': getattr(settings, 'UNIT_Name', ''),
                            'plan': getattr(settings, 'PLAN', ''),
                            'firmware_version': getattr(settings, 'FIRMWARE_VERSION', '')
                        }
                        headers = {}
                        if token:
                            headers['X-TMON-CONFIRM'] = token
                        try:
                            respc = requests.post(confirm_url, json=payload, headers=headers, timeout=8)
                        except TypeError:
                            respc = requests.post(confirm_url, json=payload, headers=headers)
                        try:
                            respc.close()
                        except Exception:
                            pass
                    except Exception:
                        pass
                    # Guard: only soft reset once (complete missing logic)
                    guard_file = getattr(settings, 'PROVISION_REBOOT_GUARD_FILE', settings.LOG_DIR + '/provision_reboot.flag')
                    try:
                        import uos as _os
                        listed = _os.listdir(settings.LOG_DIR) if hasattr(_os, 'listdir') else []
                        guard_name = guard_file.split('/')[-1]
                        already_guarded = (guard_name in listed)
                        if not already_guarded:
                            try:
                                with open(guard_file, 'w') as gf:
                                    gf.write('1')
                            except Exception:
                                pass
                            await debug_print('first_boot_provision: provisioning applied; soft resetting', 'PROVISION')
                            try:
                                import machine as _m
                                _m.soft_reset()
                            except Exception:
                                pass
                    except Exception:
                        pass
            except Exception:
                # Ensure inner provisioning metadata block doesn't break boot flow
                pass
            # If remote node, disable WiFi after provisioning
            try:
                if getattr(settings, 'NODE_TYPE', 'base') == 'remote' and getattr(settings, 'WIFI_DISABLE_AFTER_PROVISION', True):
                    disable_wifi()
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
                await asyncio.sleep(2)
                continue
            wp = getattr(settings, 'WORDPRESS_API_URL', '')
            # Only run check-ins and related operations on nodes that have WP configured
            if wp and not getattr(settings, 'DEVICE_SUSPENDED', False):
                if register_with_wp:
                    await register_with_wp()
                if send_settings_to_wp:
                    await send_settings_to_wp()
                if send_data_to_wp:
                    await send_data_to_wp()
                if poll_ota_jobs:
                    await poll_ota_jobs()
                # NEW: fetch staged settings and pending commands (useful for wifi & base nodes)
                if fetch_staged_settings:
                    res = await fetch_staged_settings()
                    # If commands returned, attempt to process them immediately (use same handlers as poll)
                    if res and isinstance(res, dict) and res.get('commands'):
                        cmds = res.get('commands')
                        for c in cmds:
                            try:
                                # simple handler reuse: insert as immediate commands via poll_device_commands logic if available
                                if poll_device_commands:
                                    # poll handler will retrieve via its own endpoint; skip heavy immediate execution here
                                    pass
                            except Exception:
                                pass
                # Also ensure regular command poll runs for wifi/base nodes here (avoid extra loop for remotes)
                node_role = str(getattr(settings, 'NODE_TYPE', 'base')).lower()
                if node_role in ('base', 'wifi') and poll_device_commands:
                    try:
                        await poll_device_commands()
                    except Exception as e:
                        await debug_print(f"Command poll error (checkin): {e}", "ERROR")
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
        import uasyncio as _a
        _a.create_task(wifi_rssi_monitor())
    except Exception:
        pass

    # Start provisioning loop
    try:
        import uasyncio as _a5
        await debug_print('startup: schedule prov-check', 'INFO')
        _a5.create_task(periodic_provision_check())
    except Exception as e:
        await debug_print(f'startup: prov-check schedule fail: {e}', 'ERROR')

    # Staged settings apply loop
    try:
        import uasyncio as _a0
        _a0.create_task(settings_apply_loop(int(getattr(settings, 'PROVISION_CHECK_INTERVAL_S', 60))))
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

    # Periodic OTA version/apply tasks
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

    async def ota_apply_task():
        while True:
            try:
                await apply_pending_update()
            except Exception:
                pass
            await asyncio.sleep(getattr(settings, 'OTA_APPLY_INTERVAL_S', 600))
    try:
        import uasyncio as _a4
        _a4.create_task(ota_apply_task())
    except Exception:
        pass

    # Unit Connector periodic check-in loop
    try:
        import uasyncio as _auc
        _auc.create_task(periodic_uc_checkin_task())
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
import uasyncio as asyncio
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
                update_sys_voltage()
            except Exception:
                pass

            await asyncio.sleep(10)

            # CHANGED: runGC every 300s at end of loop
            try:
                now_ms = time.ticks_ms()
                if time.ticks_diff(now_ms, _last_gc_ms) >= _gc_interval_ms:
                    await runGC()
                    _last_gc_ms = now_ms
            except Exception:
                pass

        except Exception:
            await asyncio.sleep(5)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception:
        # Older uasyncio compatibility
        loop = asyncio.get_event_loop()
        loop.create_task(main())
        loop.run_forever()