# Firmware Version: v2.00j
# Utility to print remote node info
def print_remote_nodes():
    import settings
    remote_info = getattr(settings, 'REMOTE_NODE_INFO', {})
    for node_id, node_data in remote_info.items():
        print(f"[REMOTE NODE] {node_id}: {node_data}")

# --- All imports at the top ---
import ujson
import os
import uasyncio as asyncio
import select
from sampling import sampleEnviroment, findLowestTemp, findHighestTemp, findLowestBar, findHighestBar, findLowestHumid, findHighestHumid
try:
    import machine
    import sys
except ImportError:
    machine = None
    sys = None
try:
    from sx1262 import SX1262
except ImportError:
    SX1262 = None
try:
    import sdata
    import settings
except ImportError:
    sdata = None
    settings = None
try:
    import utime as time
except ImportError:
    import time
try:
    import urequests as requests
except ImportError:
    try:
        import requests
    except ImportError:
        requests = None
from utils import free_pins, checkLogDirectory, debug_print, TMON_AI, safe_run, led_status_flash, write_lora_log, persist_unit_id
from relay import toggle_relay
try:
    from encryption import chacha20_encrypt, derive_nonce
except Exception:
    chacha20_encrypt = None
    derive_nonce = None
from wprest import (
    register_with_wp,
    send_data_to_wp,
    send_settings_to_wp,
    fetch_settings_from_wp,
    send_file_to_wp,
    request_file_from_wp,
    heartbeat_ping,
    poll_ota_jobs,
    handle_ota_job
)

async def user_input_listener():
    """Non-blocking input for user commands via UART/serial."""
    if not sys or not hasattr(sys, 'stdin'):
        return
    while True:
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            cmd = sys.stdin.readline().strip()
            if cmd:
                await handle_user_command(cmd)
        await asyncio.sleep(0.1)

async def handle_user_command(cmd):
    """Parse and execute user commands for system/AI."""
    from utils import debug_print
    if cmd.lower() == 'reset_ai':
        TMON_AI.error_count = 0
        await debug_print('AI error count reset by user', 'user_input')
    elif cmd.lower().startswith('call '):
        # Example: call <function_name>
        fn = cmd[5:].strip()
        if hasattr(TMON_AI, fn):
            await debug_print(f'Calling AI function: {fn}', 'user_input')
            getattr(TMON_AI, fn)()
        else:
            await debug_print(f'No such AI function: {fn}', 'user_input')
    else:
        await debug_print(f'Unknown command: {cmd}', 'user_input')

# File to persist remote node info and remote sync schedule
import settings
REMOTE_NODE_INFO_FILE = settings.LOG_DIR + '/remote_node_info.json'
REMOTE_SYNC_SCHEDULE_FILE = settings.LOG_DIR + '/remote_sync_schedule.json'
GPS_STATE_FILE = settings.LOG_DIR + '/gps.json'

# Load REMOTE_NODE_INFO from file at startup
def load_remote_node_info():
    try:
        with open(REMOTE_NODE_INFO_FILE, 'r') as f:
            settings.REMOTE_NODE_INFO = ujson.load(f)
    except Exception:
        settings.REMOTE_NODE_INFO = {}

    # Load remote sync schedule (base only)
    try:
        with open(REMOTE_SYNC_SCHEDULE_FILE, 'r') as f:
            settings.REMOTE_SYNC_SCHEDULE = ujson.load(f)
    except Exception:
        settings.REMOTE_SYNC_SCHEDULE = {}

    # Load last known GPS state
    try:
        with open(GPS_STATE_FILE, 'r') as f:
            gps = ujson.load(f)
            try:
                import sdata as _s
                _s.gps_lat = gps.get('gps_lat')
                _s.gps_lng = gps.get('gps_lng')
                _s.gps_alt_m = gps.get('gps_alt_m')
                _s.gps_accuracy_m = gps.get('gps_accuracy_m')
                _s.gps_last_fix_ts = gps.get('gps_last_fix_ts')
            except Exception:
                pass
            # also project to settings if allowed
            try:
                if getattr(settings, 'GPS_OVERRIDE_ALLOWED', True):
                    if 'gps_lat' in gps: settings.GPS_LAT = gps.get('gps_lat')
                    if 'gps_lng' in gps: settings.GPS_LNG = gps.get('gps_lng')
                    if 'gps_alt_m' in gps: settings.GPS_ALT_M = gps.get('gps_alt_m')
                    if 'gps_accuracy_m' in gps: settings.GPS_ACCURACY_M = gps.get('gps_accuracy_m')
                    if 'gps_last_fix_ts' in gps: settings.GPS_LAST_FIX_TS = gps.get('gps_last_fix_ts')
            except Exception:
                pass
    except Exception:
        pass

# Ensure remote node info is loaded at startup (after settings import)
load_remote_node_info()

# Save REMOTE_NODE_INFO to file
def save_remote_node_info():
    try:
        with open(REMOTE_NODE_INFO_FILE, 'w') as f:
            ujson.dump(settings.REMOTE_NODE_INFO, f)
    except Exception:
        pass

def save_remote_sync_schedule():
    try:
        with open(REMOTE_SYNC_SCHEDULE_FILE, 'w') as f:
            ujson.dump(settings.REMOTE_SYNC_SCHEDULE, f)
    except Exception:
        pass

def save_gps_state(lat=None, lng=None, alt=None, acc=None, ts=None):
    try:
        # Update sdata mirror
        try:
            import sdata as _s
            _s.gps_lat = lat
            _s.gps_lng = lng
            _s.gps_alt_m = alt
            _s.gps_accuracy_m = acc
            _s.gps_last_fix_ts = ts
        except Exception:
            pass
        # Update settings if allowed
        try:
            if getattr(settings, 'GPS_OVERRIDE_ALLOWED', True):
                if lat is not None: settings.GPS_LAT = lat
                if lng is not None: settings.GPS_LNG = lng
                if alt is not None: settings.GPS_ALT_M = alt
                if acc is not None: settings.GPS_ACCURACY_M = acc
                if ts is not None: settings.GPS_LAST_FIX_TS = ts
        except Exception:
            pass
        with open(GPS_STATE_FILE, 'w') as f:
            ujson.dump({
                'gps_lat': lat,
                'gps_lng': lng,
                'gps_alt_m': alt,
                'gps_accuracy_m': acc,
                'gps_last_fix_ts': ts
            }, f)
    except Exception:
        pass

# Import all WordPress REST API functions from wprest.py
from wprest import (
    register_with_wp,
    send_data_to_wp,
    send_settings_to_wp,
    fetch_settings_from_wp,
    send_file_to_wp,
    request_file_from_wp,
    heartbeat_ping,
    poll_ota_jobs,
    handle_ota_job
)

# Periodic sync with WordPress (settings, data, OTA jobs)
async def periodic_wp_sync():
    if settings.NODE_TYPE != 'base':
        return  # Only base station handles WordPress communication
    while True:
        await register_with_wp()
        await send_settings_to_wp()
        await fetch_settings_from_wp()
        await send_data_to_wp()
        await poll_ota_jobs()
        await asyncio.sleep(300)  # Sync every 5 minutes

# Heartbeat loop
async def heartbeat_ping_loop():
    if settings.NODE_TYPE != 'base':
        return  # Only base station sends heartbeats to WordPress
    while True:
        await heartbeat_ping()
        await asyncio.sleep(60)

# Check for suspend/remove/remote access state (unchanged)
async def check_suspend_remove():
    if settings.NODE_TYPE != 'base':
        return  # Only base station checks suspend status from WordPress
    from wprest import WORDPRESS_API_URL
    if not WORDPRESS_API_URL:
        return
    try:
        import settings
        import urequests as requests
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/settings/{settings.UNIT_ID}')
        if resp.status_code == 200:
            settings_data = resp.json().get('settings', {})
            if settings_data.get('suspended'):
                from utils import debug_print
                await debug_print('Device is suspended by admin', 'WARN')
                while True:
                    await asyncio.sleep(60)
    except Exception:
        pass

# Start periodic sync in main event loop (add to your main.py or boot.py)
# asyncio.create_task(periodic_wp_sync())
# asyncio.create_task(check_suspend_remove())



# --- All imports at the very top ---
try:
    from sx1262 import SX1262
except ImportError:
    SX1262 = None
try:
    import uasyncio as asyncio
except ImportError:
    import asyncio
try:
    import sdata
    import settings
except ImportError:
    sdata = None
    settings = None
try:
    import machine
except ImportError:
    machine = None
try:
    import utime as time
except ImportError:
    import time
import os
try:
    import urequests as requests
except ImportError:
    try:
        import requests
    except ImportError:
        requests = None
from utils import free_pins, checkLogDirectory, debug_print, TMON_AI, safe_run
from relay import toggle_relay

# Restore: define WORDPRESS_API_URL safely for this module
try:
    WORDPRESS_API_URL = getattr(settings, 'WORDPRESS_API_URL', '')
except Exception:
    WORDPRESS_API_URL = ''

if not WORDPRESS_API_URL:
    try:
        from config_persist import read_text
        path = getattr(settings, 'WORDPRESS_API_URL_FILE', settings.LOG_DIR + '/wordpress_api_url.txt')
        val = (read_text(path, '') or '').strip()
        if val:
            settings.WORDPRESS_API_URL = val
            WORDPRESS_API_URL = val
    except Exception:
        pass

if not WORDPRESS_API_URL:
    try:
        import wprest as _w
        WORDPRESS_API_URL = getattr(_w, 'WORDPRESS_API_URL', '') or ''
    except Exception:
        pass

def refresh_wp_url():
    """Refresh local WORDPRESS_API_URL from settings/wprest/file."""
    global WORDPRESS_API_URL
    try:
        url = getattr(settings, 'WORDPRESS_API_URL', '') or ''
        if not url:
            try:
                import wprest as _w
                url = getattr(_w, 'WORDPRESS_API_URL', '') or ''
            except Exception:
                url = ''
        if not url:
            try:
                from config_persist import read_text
                path = getattr(settings, 'WORDPRESS_API_URL_FILE', settings.LOG_DIR + '/wordpress_api_url.txt')
                url = (read_text(path, '') or '').strip()
            except Exception:
                pass
        if url:
            WORDPRESS_API_URL = url
    except Exception:
        pass

async def send_settings_to_wp():
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    data = {
        'unit_id': settings.UNIT_ID,
        'unit_name': settings.UNIT_Name,
        'company': getattr(settings, 'COMPANY', ''),
        'site': getattr(settings, 'SITE', ''),
        'zone': getattr(settings, 'ZONE', ''),
        'cluster': getattr(settings, 'CLUSTER', ''),
        'settings': {k: getattr(settings, k) for k in dir(settings) if not k.startswith('__') and not callable(getattr(settings, k))}
    }
    try:
        resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/settings', headers={'Authorization': f'Bearer {WORDPRESS_API_KEY}'}, json=data)
        await debug_print(f'Sent settings to WP: {resp.status_code}', 'HTTP')
    except Exception as e:
        await debug_print(f'Failed to send settings to WP: {e}', 'ERROR')

async def fetch_settings_from_wp():
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    try:
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/settings/{settings.UNIT_ID}', headers={'Authorization': f'Bearer {WORDPRESS_API_KEY}'})
        if resp.status_code == 200:
            new_settings = resp.json().get('settings', {})
            # Also update company, site, zone, cluster if present
            for k in ['COMPANY', 'SITE', 'ZONE', 'CLUSTER']:
                if k in new_settings:
                    setattr(settings, k, new_settings[k])
            for k, v in new_settings.items():
                if hasattr(settings, k):
                    setattr(settings, k, v)
            await debug_print('Settings updated from WP', 'HTTP')
        else:
            await debug_print(f'Failed to fetch settings: {resp.status_code}', 'ERROR')
    except Exception as e:
        await debug_print(f'Failed to fetch settings from WP: {e}', 'ERROR')

async def send_file_to_wp(filepath):
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    try:
        with open(filepath, 'rb') as f:
            files = {'file': (os.path.basename(filepath), f.read())}
            resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/file', headers={'Authorization': f'Bearer {WORDPRESS_API_KEY}'}, files=files)
            await debug_print(f'Sent file to WP: {resp.status_code}', 'HTTP')
    except Exception as e:
        await debug_print(f'Failed to send file to WP: {e}', 'ERROR')

async def request_file_from_wp(filename):
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    try:
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/file/{settings.UNIT_ID}/{filename}', headers={'Authorization': f'Bearer {WORDPRESS_API_KEY}'})
        if resp.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(resp.content)
            await debug_print(f'Received file from WP: {filename}', 'HTTP')
        else:
            await debug_print(f'Failed to fetch file: {resp.status_code}', 'ERROR')
    except Exception as e:
        await debug_print(f'Failed to fetch file from WP: {e}', 'ERROR')

file_lock = asyncio.Lock()
pin_lock = asyncio.Lock()
lora = None

# Asynchronous function to log errors
async def log_error(error_msg):
    ts = time.time()
    log_line = f"{ts}: {error_msg}\n"
    try:
        async with file_lock:
            with open(settings.ERROR_LOG_FILE, 'a') as f:
                f.write(log_line)
    except Exception as e:
        print(f"[FATAL] Failed to log error: {e}")
    await asyncio.sleep(0)

command_handlers = {
    "toggle_relay": toggle_relay,
    # Add more handlers as needed, e.g., "other_func": other_func,
}

async def init_lora():
    global lora
    print('[DEBUG] init_lora: starting SX1262 init')
    try:
        print('[DEBUG] init_lora: BEFORE SX1262 instantiation')
        lora = SX1262(
            settings.SPI_BUS, settings.CLK_PIN, settings.MOSI_PIN, settings.MISO_PIN,
            settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN
        )
        print('[DEBUG] init_lora: SX1262 object created')
        status = lora.begin(
            freq=settings.FREQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
            syncWord=settings.SYNC_WORD, power=settings.POWER,
            currentLimit=settings.CURRENT_LIMIT, preambleLength=settings.PREAMBLE_LEN,
            implicit=False, implicitLen=0xFF, crcOn=settings.CRC_ON, txIq=False, rxIq=False,
            tcxoVoltage=settings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO
        )
        print(f'[DEBUG] init_lora: lora.begin() returned {status}')
        if status == 0:
            # Configure non-blocking operation and verify it succeeded
            rc = lora.setBlockingCallback(False)
            if rc != 0:
                try:
                    from _sx126x import ERROR as SXERR
                    err_name = SXERR.get(rc, 'UNKNOWN')
                except Exception:
                    err_name = 'UNKNOWN'
                await debug_print(f"LoRa setBlockingCallback failed: {rc} ({err_name})", "ERROR")
                await log_error(f"LoRa setBlockingCallback failed: {rc} ({err_name})")
                await free_pins()
                lora = None
                return False
            # Double-check radio packet type is LoRa
            try:
                from _sx126x import SX126X_PACKET_TYPE_LORA
                pkt_type = lora.getPacketType()
                if pkt_type != SX126X_PACKET_TYPE_LORA:
                    await debug_print(f"LoRa init verify failed: packet type={pkt_type} (expected LoRa)", "ERROR")
                    await log_error(f"LoRa init verify failed: packet type={pkt_type}")
                    await free_pins()
                    lora = None
                    return False
            except Exception as ve:
                await debug_print(f"LoRa init verify exception: {ve}", "ERROR")
                await log_error(f"LoRa init verify exception: {ve}")
                await free_pins()
                lora = None
                return False
        if status != 0:
            # Map error code to readable name
            try:
                from _sx126x import ERROR as SXERR
                err_name = SXERR.get(status, 'UNKNOWN')
            except Exception:
                err_name = 'UNKNOWN'
            error_msg = f"LoRa initialization failed with status: {status} ({err_name})"
            await debug_print(error_msg, "ERROR")
            await log_error(error_msg)
            await free_pins()
            lora = None
            return False
        await debug_print("LoRa initialized successfully", "LORA")
        print_remote_nodes()
        # Ensure base starts in RX mode to listen for remotes
        try:
            if getattr(settings, 'NODE_TYPE', 'base') == 'base' and lora is not None:
                lora.setOperatingMode(lora.MODE_RX)
        except Exception:
            pass
        print('[DEBUG] init_lora: completed successfully')
        return True
    except Exception as e:
        error_msg = f"Exception in init_lora: {e}"
        print(error_msg)
        await debug_print(error_msg, "ERROR")
        await log_error(error_msg)
        await free_pins()
        lora = None
        return False

_last_send_ms = 0
_last_activity_ms = 0
_init_failures = 0
_MAX_INIT_FAILS = 3

async def connectLora():
    """Non-blocking LoRa routine called frequently from lora_comm_task.
    - Initializes radio once (with retry cap)
    - Remote: sends payload at interval, waits for TX_DONE briefly, then returns
    - Base: polls for RX_DONE and processes any message
    - Idle timeout: deinit after prolonged inactivity to save power
    Returns True if LoRa is initialized and usable, else False.
    """
    global lora, _last_send_ms, _last_activity_ms, _init_failures

    if not getattr(settings, 'ENABLE_LORA', True):
        return False

    now = time.ticks_ms()

    # Ensure initialized
    if lora is None:
        if _init_failures >= _MAX_INIT_FAILS:
            # Stop hammering if it keeps failing
            return False
        await debug_print("LoRa: initializing...", "LORA")
        async with pin_lock:
            ok = await init_lora()
        if not ok:
            _init_failures += 1
            # Small backoff handled by caller; return quickly
            return False
        _init_failures = 0
        _last_activity_ms = now

    # Choose behavior by role
    role = getattr(settings, 'NODE_TYPE', 'base')

    # Remote: send data on base-managed schedule after first contact
    if role == 'remote':
        # Determine if it's time to TX. Before first contact, fall back to short probing interval.
        probe_interval_ms = 30 * 1000
        next_sync = getattr(settings, 'nextLoraSync', 300)
        # If next_sync appears to be an absolute epoch (far in the future vs boot ticks), schedule against wall time
        due = False
        try:
            # Assume utime.time() returns epoch seconds; consider due if now_epoch >= next_sync
            now_epoch = time.time()
            if isinstance(next_sync, int) or isinstance(next_sync, float):
                if next_sync > 100000:  # treat as absolute epoch
                    due = now_epoch >= next_sync
                else:
                    # Not yet provisioned; probe periodically
                    due = (_last_send_ms == 0) or (time.ticks_diff(now, _last_send_ms) >= probe_interval_ms)
            else:
                due = (_last_send_ms == 0) or (time.ticks_diff(now, _last_send_ms) >= probe_interval_ms)
        except Exception:
            due = (_last_send_ms == 0) or (time.ticks_diff(now, _last_send_ms) >= probe_interval_ms)

        if due:
            try:
                # Build compact payload
                # Load & increment local HMAC counter if enabled
                payload = {
                    'unit_id': getattr(settings, 'UNIT_ID', ''),
                    'name': getattr(settings, 'UNIT_Name', ''),
                    'ts': now,
                    't_f': getattr(sdata, 'cur_temp_f', 0),
                    't_c': getattr(sdata, 'cur_temp_c', 0),
                    'hum': getattr(sdata, 'cur_humid', 0),
                    'bar': getattr(sdata, 'cur_bar_pres', 0),
                    'v': getattr(sdata, 'sys_voltage', 0),
                    'fm': getattr(sdata, 'free_mem', 0),
                    'net': getattr(settings, 'LORA_NETWORK_NAME', 'tmon'),
                    'key': getattr(settings, 'LORA_NETWORK_PASSWORD', ''),
                }
                try:
                    if getattr(settings, 'LORA_HMAC_ENABLED', False):
                        import uhashlib, ubinascii, ujson
                        ctr_file = getattr(settings, 'LORA_HMAC_COUNTER_FILE', '/logs/lora_ctr.json')
                        ctr = 0
                        try:
                            with open(ctr_file, 'r') as cf:
                                ctr_obj = ujson.loads(cf.read())
                                ctr = int(ctr_obj.get('ctr', 0))
                        except Exception:
                            ctr = 0
                        ctr += 1
                        try:
                            with open(ctr_file, 'w') as cfw:
                                cfw.write(ujson.dumps({'ctr': ctr}))
                        except Exception:
                            pass
                        payload['ctr'] = ctr
                        secret = getattr(settings, 'LORA_HMAC_SECRET', '')
                        if secret:
                            mac_src = b"|".join([
                                secret.encode(),
                                str(payload['unit_id']).encode(),
                                str(payload['ts']).encode(),
                                str(payload['ctr']).encode()
                            ])
                            h = uhashlib.sha256(mac_src)
                            payload['sig'] = ubinascii.hexlify(h.digest())[:32].decode()
                except Exception:
                    pass
                # Optional encryption: wrap payload into {enc, nonce, ct}
                if getattr(settings, 'LORA_ENCRYPT_ENABLED', False) and chacha20_encrypt and derive_nonce:
                    try:
                        secret = getattr(settings, 'LORA_ENCRYPT_SECRET', '')
                        key = secret.encode()
                        if len(key) < 32:
                            key = (key + b'\x00'*32)[:32]
                        nonce = derive_nonce(int(time.time()), int(payload.get('ctr', 0)))
                        pt = ujson.dumps(payload).encode('utf-8')
                        ct = chacha20_encrypt(key, nonce, 1, pt)
                        env = {'enc': 1, 'nonce': ''.join('{:02x}'.format(b) for b in nonce), 'ct': ''.join('{:02x}'.format(b) for b in ct), 'net': payload.get('net'), 'key': payload.get('key')}
                        data = ujson.dumps(env).encode('utf-8')
                    except Exception:
                        data = ujson.dumps(payload).encode('utf-8')
                else:
                    data = ujson.dumps(payload).encode('utf-8')

                # Transmit in non-blocking mode; poll for TX_DONE
                # If radio was deinitialized in a prior loop, re-init
                if lora is None:
                    await debug_print('Remote: lora handle is None before send, reinitializing', 'WARN')
                    async with pin_lock:
                        ok = await init_lora()
                    if not ok:
                        raise Exception('LoRa unavailable for TX')
                _, state = lora.send(data)
                if state != 0:
                    # Map error code to name (if available)
                    try:
                        from _sx126x import ERROR as SXERR
                        err_name = SXERR.get(state, 'UNKNOWN')
                    except Exception:
                        err_name = 'UNKNOWN'
                    await debug_print(f"LoRa TX error: {state} ({err_name})", 'ERROR')
                    await log_error(f"LoRa TX error: {state} ({err_name})")
                    led_status_flash('ERROR')
                    # Try to read device error flags for more detail
                    try:
                        dev_err = lora.getDeviceErrors()
                        await debug_print(f"LoRa device errors: 0x{dev_err:04X}", 'ERROR')
                        await log_error(f"LoRa device errors: 0x{dev_err:04X}")
                    except Exception:
                        pass
                    # Capture radio status and BUSY pin state for diagnostics
                    try:
                        st = None
                        try:
                            st = lora.getStatus()
                        except Exception:
                            st = None
                        busy_val = None
                        try:
                            if machine and hasattr(machine, 'Pin'):
                                busy_val = machine.Pin(settings.BUSY_PIN, machine.Pin.IN).value()
                        except Exception:
                            busy_val = None
                        await debug_print(f"LoRa status={st} busy={busy_val}", 'ERROR')
                        await log_error(f"LoRa status={st} busy={busy_val}")
                    except Exception:
                        pass
                    # If unknown (-1), chip not found (-2), or SPI timeout (-705), force re-init next loop
                    if state in (-1, -2, -705):
                        await debug_print("LoRa: forcing re-initialize due to TX error", 'WARN')
                        try:
                            lora.clearDeviceErrors()
                        except Exception:
                            pass
                        try:
                            if hasattr(lora, 'spi') and lora.spi:
                                lora.spi.deinit()
                        except Exception:
                            pass
                        lora = None
                else:
                    # Flash LED for TX success
                    led_status_flash('LORA_TX')
                    tx_start = time.ticks_ms()
                    while time.ticks_diff(time.ticks_ms(), tx_start) < 5000:
                        if lora is None:
                            break
                        ev = lora._events()
                        if ev & SX1262.TX_DONE:
                            await debug_print("Remote: TX_DONE", 'LORA')
                            write_lora_log("Remote TX_DONE", 'INFO')
                            break
                        await asyncio.sleep(0.01)
                    # Return to RX to be ready for any ack
                    try:
                        lora.setOperatingMode(lora.MODE_RX)
                    except Exception:
                        pass
                    # Briefly listen for ACK that may include next absolute or relative sync time
                    ack_wait_ms = 1500
                    start_wait = time.ticks_ms()
                    while time.ticks_diff(time.ticks_ms(), start_wait) < ack_wait_ms:
                        if lora is None:
                            break
                        ev2 = lora._events()
                        if ev2 & SX1262.RX_DONE:
                            msg2, err2 = lora._readData(0)
                            if err2 == 0 and msg2:
                                try:
                                    obj2 = ujson.loads(msg2)
                                    if obj2.get('ack') == 'ok':
                                        # Capture signal info for display
                                        try:
                                            if hasattr(lora, 'getRSSI'):
                                                sdata.lora_SigStr = lora.getRSSI()
                                            if hasattr(lora, 'getSNR'):
                                                sdata.lora_snr = lora.getSNR()
                                            sdata.last_message = ujson.dumps(obj2)[:32]
                                        except Exception:
                                            pass
                                        try:
                                            if 'next_in' in obj2:
                                                rel = int(obj2['next_in'])
                                                if rel < 1:
                                                    rel = 1
                                                if rel > 24 * 3600:
                                                    rel = 24 * 3600
                                                settings.nextLoraSync = int(time.time() + rel)
                                            elif 'next' in obj2:
                                                settings.nextLoraSync = int(obj2['next'])
                                        except Exception:
                                            pass
                                        try:
                                            with open(settings.LOG_DIR + '/remote_next_sync.json', 'w') as fns:
                                                ujson.dump({'next': settings.nextLoraSync}, fns)
                                        except Exception:
                                            pass
                                        # Adopt GPS from base if provided
                                        try:
                                            if getattr(settings, 'GPS_ACCEPT_FROM_BASE', True):
                                                blat = obj2.get('gps_lat')
                                                blng = obj2.get('gps_lng')
                                                if (blat is not None) and (blng is not None):
                                                    balt = obj2.get('gps_alt_m')
                                                    bacc = obj2.get('gps_accuracy_m')
                                                    bts = obj2.get('gps_last_fix_ts')
                                                    save_gps_state(blat, blng, balt, bacc, bts)
                                                    await debug_print('Remote adopted GPS from base', 'LORA')
                                        except Exception:
                                            pass
                                        await debug_print(f"Remote stored next sync epoch: {settings.nextLoraSync}", 'LORA')
                                        write_lora_log(f"Remote stored next sync epoch: {settings.nextLoraSync}", 'INFO')
                                        led_status_flash('SUCCESS')
                                        break
                                except Exception:
                                    pass
                        await asyncio.sleep(0.01)
                _last_send_ms = time.ticks_ms()
                _last_activity_ms = _last_send_ms
            except Exception as e:
                await debug_print(f"Remote TX exception: {e}", 'ERROR')
                await log_error(f"Remote TX exception: {e}")

    # Base: check for received packets
    else:  # 'base'
        try:
            # Ensure we're in RX mode to receive packets
            try:
                if lora is not None:
                    lora.setOperatingMode(lora.MODE_RX)
            except Exception:
                pass
            ev = lora._events()
            if ev & SX1262.RX_DONE:
                msg, err = lora._readData(0)
                if err == 0 and msg:
                    _last_activity_ms = time.ticks_ms()
                    await debug_print("Base: RX packet", 'LORA')
                    led_status_flash('LORA_RX')
                    write_lora_log("Base RX packet", 'INFO')
                    try:
                        obj = ujson.loads(msg)
                        # If encrypted envelope, attempt decrypt
                        if isinstance(obj, dict) and obj.get('enc') and getattr(settings, 'LORA_ENCRYPT_ENABLED', False) and chacha20_encrypt and derive_nonce:
                            try:
                                secret = getattr(settings, 'LORA_ENCRYPT_SECRET', '')
                                key = secret.encode(); key = (key + b'\x00'*32)[:32]
                                hex_nonce = obj.get('nonce','')
                                nonce = bytes(int(hex_nonce[i:i+2],16) for i in range(0, len(hex_nonce),2)) if hex_nonce else b'\x00'*12
                                hex_ct = obj.get('ct','')
                                ct = bytes(int(hex_ct[i:i+2],16) for i in range(0, len(hex_ct),2)) if hex_ct else b''
                                pt = chacha20_encrypt(key, nonce, 1, ct)
                                obj = ujson.loads(pt)
                            except Exception:
                                pass
                        # Basic network credential enforcement
                        try:
                            net_ok = (obj.get('net') == getattr(settings, 'LORA_NETWORK_NAME', 'tmon'))
                            key_ok = (obj.get('key') == getattr(settings, 'LORA_NETWORK_PASSWORD', ''))
                        except Exception:
                            net_ok = False
                            key_ok = False
                        # Strict HMAC validation & replay protection
                        if getattr(settings, 'LORA_HMAC_ENABLED', False):
                            try:
                                import uhashlib, ubinascii, ujson
                                secret = getattr(settings, 'LORA_HMAC_SECRET', '')
                                sig = obj.get('sig')
                                ctr = obj.get('ctr')
                                if not secret or sig is None or ctr is None:
                                    if getattr(settings, 'LORA_HMAC_REJECT_UNSIGNED', True):
                                        net_ok = False; key_ok = False
                                else:
                                    mac_src = b"|".join([
                                        secret.encode(),
                                        str(obj.get('unit_id','')).encode(),
                                        str(obj.get('ts','')).encode(),
                                        str(ctr).encode()
                                    ])
                                    h = uhashlib.sha256(mac_src)
                                    expect = ubinascii.hexlify(h.digest())[:32].decode()
                                    if expect != sig:
                                        net_ok = False; key_ok = False
                                        await debug_print('Base: LoRa HMAC signature mismatch', 'WARN')
                                    elif getattr(settings, 'LORA_HMAC_REPLAY_PROTECT', True):
                                        # Load remote counters table
                                        rctr_file = getattr(settings, 'LORA_REMOTE_COUNTERS_FILE', '/logs/remote_ctr.json')
                                        table = {}
                                        try:
                                            with open(rctr_file, 'r') as rf:
                                                table = ujson.loads(rf.read()) or {}
                                        except Exception:
                                            table = {}
                                        last_ctr = int(table.get(obj.get('unit_id',''), -1))
                                        if int(ctr) <= last_ctr:
                                            net_ok = False; key_ok = False
                                            await debug_print('Base: LoRa HMAC replay detected', 'WARN')
                                        else:
                                            table[obj.get('unit_id','')] = int(ctr)
                                            try:
                                                with open(rctr_file, 'w') as rfw:
                                                    rfw.write(ujson.dumps(table))
                                            except Exception:
                                                pass
                            except Exception:
                                pass
                        if not (net_ok and key_ok):
                            # Optionally send an auth error ack
                            try:
                                nack = {'err': 'auth'}
                                if lora is not None:
                                    _, stn = lora.send(ujson.dumps(nack).encode('utf-8'))
                                    write_lora_log(f"Base NACK auth (rc={stn})", 'WARN')
                            except Exception:
                                pass
                            await debug_print('Base: rejected packet (LoRa network credentials mismatch)', 'WARN')
                            led_status_flash('WARN')
                            return True
                        # Capture RSSI/SNR and last message for UI
                        try:
                            if hasattr(lora, 'getRSSI'):
                                sdata.lora_SigStr = lora.getRSSI()
                            if hasattr(lora, 'getSNR'):
                                sdata.lora_snr = lora.getSNR()
                            sdata.last_message = ujson.dumps(obj)[:32]
                        except Exception:
                            pass
                        uid = str(obj.get('unit_id', 'unknown'))
                        # Track latest remote payload
                        if not hasattr(settings, 'REMOTE_NODE_INFO') or not isinstance(getattr(settings, 'REMOTE_NODE_INFO'), dict):
                            settings.REMOTE_NODE_INFO = {}
                        settings.REMOTE_NODE_INFO[uid] = obj
                        save_remote_node_info()

                        # Compute and send ACK with next absolute sync time for this remote
                        if not hasattr(settings, 'REMOTE_SYNC_SCHEDULE') or not isinstance(getattr(settings, 'REMOTE_SYNC_SCHEDULE'), dict):
                            settings.REMOTE_SYNC_SCHEDULE = {}

                        now_epoch = time.time()
                        base_interval = getattr(settings, 'nextLoraSync', 300)
                        min_gap = getattr(settings, 'LORA_SYNC_WINDOW', 2)

                        # Determine next slot that doesn't overlap existing scheduled slots
                        # Use relative seconds by default; support absolute epoch if configured
                        default_interval = base_interval if isinstance(base_interval, (int, float)) else 300
                        if default_interval <= 100000:
                            candidate = int(now_epoch + max(1, int(default_interval)))
                        else:
                            candidate = int(default_interval)
                        def overlaps(ts):
                            for other_uid, other_ts in settings.REMOTE_SYNC_SCHEDULE.items():
                                try:
                                    if abs(int(other_ts) - int(ts)) < min_gap:
                                        return True
                                except Exception:
                                    continue
                            return False

                        # Limit attempts to avoid infinite loop
                        attempts = 0
                        while overlaps(candidate) and attempts < 50:
                            candidate += min_gap
                            attempts += 1

                        settings.REMOTE_SYNC_SCHEDULE[uid] = candidate
                        save_remote_sync_schedule()

                        # Include absolute and relative schedule in ACK for robustness
                        next_in = max(1, int(candidate - now_epoch))
                        ack = {'ack': 'ok', 'next': candidate, 'next_in': next_in, 'net': getattr(settings, 'LORA_NETWORK_NAME', 'tmon')}
                        try:
                            if lora is None:
                                raise Exception('LoRa unavailable for ACK TX')
                            _, st2 = lora.send(ujson.dumps(ack).encode('utf-8'))
                            await debug_print(f"Base ACK sent to {uid} with next={candidate} next_in={next_in} rc={st2}", 'LORA')
                            write_lora_log(f"Base ACK to {uid} next={candidate} next_in={next_in} rc={st2}", 'INFO')
                            if st2 == 0:
                                led_status_flash('SUCCESS')
                                # Wait briefly for TX_DONE then return to RX mode
                                tx_start = time.ticks_ms()
                                while time.ticks_diff(time.ticks_ms(), tx_start) < 1000:
                                    if lora is None:
                                        break
                                    ev3 = lora._events()
                                    if ev3 & SX1262.TX_DONE:
                                        await debug_print("Base: ACK TX_DONE", 'LORA')
                                        break
                                    await asyncio.sleep(0.01)
                        except Exception as se:
                            await debug_print(f"Base ACK send error: {se}", 'ERROR')
                            await log_error(f"Base ACK send error: {se}")
                            led_status_flash('ERROR')
                        finally:
                            # Always try to return to RX to continue listening for other remotes
                            try:
                                if lora is not None:
                                    lora.setOperatingMode(lora.MODE_RX)
                            except Exception:
                                pass
                    except Exception as pe:
                        await debug_print(f"RX parse error: {pe}", 'ERROR')
                        await log_error(f"RX parse error: {pe}")
                        led_status_flash('ERROR')
        except Exception as e:
            await debug_print(f"Base RX exception: {e}", 'ERROR')
            await log_error(f"Base RX exception: {e}")

    # Idle timeout: deinit if no activity for a while
    idle_timeout_ms = 10 * 60 * 1000  # 10 minutes
    if lora is not None and _last_activity_ms and time.ticks_diff(now, _last_activity_ms) > idle_timeout_ms:
        await debug_print("LoRa idle timeout, deinitializing", 'LORA')
        async with pin_lock:
            try:
                if hasattr(lora, 'spi') and lora.spi:
                    lora.spi.deinit()
            except Exception:
                pass
            lora = None
        await free_pins()

    return lora is not None

async def ai_dashboard_display():
    """Display AI health and error stats on OLED or console."""
    from oled import display_message
    while True:
        msg = f"AI ERR: {TMON_AI.error_count}\n"
        if TMON_AI.last_error:
            msg += f"LAST: {TMON_AI.last_error[0][:20]}"
        await display_message(msg, 2)
        await asyncio.sleep(60)

async def ai_input_listener():
    """Listen for user/system input to interact with AI (e.g., via UART, button, or network)."""
    # Example: listen for a button press to reset error count
    from machine import Pin
    reset_btn = Pin(settings.AI_RESET_BTN_PIN, Pin.IN, Pin.PULL_UP)
    while True:
        if not reset_btn.value():  # Button pressed
            TMON_AI.error_count = 0
            await log_error('AI error count reset by user', 'ai_input_listener')
            await asyncio.sleep(1)  # Debounce
        await asyncio.sleep(0.1)

# In boot.py or main.py, launch these as background tasks:
# asyncio.create_task(main_loop())
# asyncio.create_task(ai_health_monitor())
# asyncio.create_task(ai_dashboard_display())
# asyncio.create_task(ai_input_listener())
# asyncio.create_task(user_input_listener())