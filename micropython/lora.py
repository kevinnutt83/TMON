# Firmware Version: v2.06.0
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
import random  # Added for jitter/backoff
import ubinascii as _ub  # NEW: base64 encode/decode for chunking
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
from utils import free_pins, checkLogDirectory, debug_print, TMON_AI, safe_run, led_status_flash, write_lora_log, persist_unit_id, record_field_data
from relay import toggle_relay
try:
    from encryption import chacha20_encrypt, derive_nonce
except Exception:
    chacha20_encrypt = None
    derive_nonce = None

# Guarded import of optional wprest helpers to avoid ImportError on devices that don't expose all names.
try:
    import wprest as _wp
    register_with_wp = getattr(_wp, 'register_with_wp', None)
    send_data_to_wp = getattr(_wp, 'send_data_to_wp', None)
    send_settings_to_wp = getattr(_wp, 'send_settings_to_wp', None)
    fetch_settings_from_wp = getattr(_wp, 'fetch_settings_from_wp', None)
    send_file_to_wp = getattr(_wp, 'send_file_to_wp', None)
    request_file_from_wp = getattr(_wp, 'request_file_from_wp', None)
    heartbeat_ping = getattr(_wp, 'heartbeat_ping', None)
    poll_ota_jobs = getattr(_wp, 'poll_ota_jobs', None)
    handle_ota_job = getattr(_wp, 'handle_ota_job', None)
    _auth_headers = getattr(_wp, '_auth_headers', None)
except Exception:
    register_with_wp = send_data_to_wp = send_settings_to_wp = fetch_settings_from_wp = None
    send_file_to_wp = request_file_from_wp = heartbeat_ping = poll_ota_jobs = handle_ota_job = _auth_headers = None

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

# Import all WordPress REST API functions from wprest.py (guarded - tolerate missing names)
try:
    import wprest as _wp
    register_with_wp = getattr(_wp, 'register_with_wp', None)
    send_data_to_wp = getattr(_wp, 'send_data_to_wp', None)
    send_settings_to_wp = getattr(_wp, 'send_settings_to_wp', None)
    fetch_settings_from_wp = getattr(_wp, 'fetch_settings_from_wp', None)
    send_file_to_wp = getattr(_wp, 'send_file_to_wp', None)
    request_file_from_wp = getattr(_wp, 'request_file_from_wp', None)
    heartbeat_ping = getattr(_wp, 'heartbeat_ping', None)
    poll_ota_jobs = getattr(_wp, 'poll_ota_jobs', None)
    handle_ota_job = getattr(_wp, 'handle_ota_job', None)
except Exception:
    register_with_wp = send_data_to_wp = send_settings_to_wp = fetch_settings_from_wp = None
    send_file_to_wp = request_file_from_wp = heartbeat_ping = poll_ota_jobs = handle_ota_job = None

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
        headers = {}
        try:
            headers = _auth_headers()
        except Exception:
            headers = {}
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/settings/{settings.UNIT_ID}', headers=headers)
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
        hdrs = {}
        try:
            hdrs = _auth_headers()
        except Exception:
            hdrs = {}
        resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/settings', headers=hdrs, json=data)
        await debug_print(f'Sent settings to WP: {resp.status_code}', 'HTTP')
    except Exception as e:
        await debug_print(f'Failed to send settings to WP: {e}', 'ERROR')

async def fetch_settings_from_wp():
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    try:
        hdrs = {}
        try:
            hdrs = _auth_headers()
        except Exception:
            hdrs = {}
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/settings/{settings.UNIT_ID}', headers=hdrs)
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
            hdrs = {}
            try:
                hdrs = _auth_headers()
            except Exception:
                hdrs = {}
            resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/file', headers=hdrs, files=files)
            await debug_print(f'Sent file to WP: {resp.status_code}', 'HTTP')
    except Exception as e:
        await debug_print(f'Failed to send file to WP: {e}', 'ERROR')

async def request_file_from_wp(filename):
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    try:
        hdrs = {}
        try:
            hdrs = _auth_headers()
        except Exception:
            hdrs = {}
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/file/{settings.UNIT_ID}/{filename}', headers=hdrs)
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

# In-memory reassembly buffers for incoming chunked messages (base-side)
_lora_incoming_chunks = {}  # unit_id -> {'total': int, 'parts': {seq: bytes}, 'ts': epoch}

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

# NEW: base-side tracking of connected remotes and pending commands
_connected_remotes = {}       # {unit_id: last_seen_epoch}
_pending_commands = {}        # {unit_id: "func(arg1,arg2,...)"}

# NEW: helper to parse and execute "func(arg1,arg2,...)" command strings
async def _execute_command_string(command):
    try:
        # Expect "func(arg1,arg2,...)" like previous version
        if '(' in command and command.endswith(')'):
            func_name, args_str = command.split('(', 1)
            func_name = func_name.strip()
            args_str = args_str.rstrip(')')
            args = [arg.strip() for arg in args_str.split(',')] if args_str else []
            if func_name in command_handlers:
                try:
                    await command_handlers[func_name](*args)
                    await debug_print(f"Executed command: {command}", "COMMAND")
                except Exception as e:
                    await debug_print(f"Command handler error for {func_name}: {e}", "ERROR")
            else:
                await debug_print(f"Unknown command: {func_name}", "ERROR")
        else:
            await debug_print(f"Invalid command format: {command}", "ERROR")
    except Exception as e:
        await debug_print(f"_execute_command_string failed: {e}", "ERROR")

import time as _time  # used for short sleeps during pin toggles

# Helpers: ensure pins / SPI are in a known state for reliable startup
def _safe_pin_out(pin_num, value=1):
    try:
        p = machine.Pin(pin_num, machine.Pin.OUT)
        p.value(value)
        return p
    except Exception:
        return None

def _safe_pin_input(pin_num):
    try:
        p = machine.Pin(pin_num, machine.Pin.IN)
        return p
    except Exception:
        return None

def _pulse_reset(pin_num, low_ms=50, post_high_ms=120):
    try:
        p = _safe_pin_out(pin_num, 0)
        _time.sleep_ms(low_ms)
        p.value(1)
        _time.sleep_ms(post_high_ms)
    except Exception:
        try:
            _time.sleep_ms(post_high_ms)
        except Exception:
            pass

def _deinit_spi_if_any(lora_obj):
    try:
        if lora_obj and hasattr(lora_obj, 'spi') and lora_obj.spi:
            try:
                lora_obj.spi.deinit()
            except Exception:
                pass
            try:
                lora_obj.spi = None
            except Exception:
                pass
    except Exception:
        pass

# NEW helper: attempt to create machine.SPI and return a tolerant shim instance or None.
def _attach_spi_shim():
    """Try various machine.SPI construction patterns and return a compact shim object or None."""
    try:
        if not (machine and hasattr(machine, 'SPI') and getattr(settings, 'CLK_PIN', None) is not None):
            return None
        spi = None
        # Try constructor with kwargs (common on many ports)
        try:
            spi = machine.SPI(
                settings.SPI_BUS,
                baudrate=getattr(settings, 'LORA_SPI_BAUD', 1000000),
                sck=machine.Pin(settings.CLK_PIN),
                mosi=machine.Pin(settings.MOSI_PIN),
                miso=machine.Pin(settings.MISO_PIN)
            )
        except Exception:
            # Fallback: construct then .init()
            try:
                spi = machine.SPI(settings.SPI_BUS)
                try:
                    spi.init(
                        baudrate=getattr(settings, 'LORA_SPI_BAUD', 1000000),
                        sck=machine.Pin(settings.CLK_PIN),
                        mosi=machine.Pin(settings.MOSI_PIN),
                        miso=machine.Pin(settings.MISO_PIN)
                    )
                except Exception:
                    # keep spi instance even if init signature differs
                    pass
            except Exception:
                spi = None
        if not spi:
            return None
        # Compact shim with tolerant methods and attribute passthrough
        class _SPIShim:
            def __init__(self, spi_obj):
                self._spi = spi_obj
            def __getattr__(self, name):
                return getattr(self._spi, name)
            def __call__(self, *a, **kw):
                try:
                    return self._spi(*a, **kw)
                except Exception:
                    return self._spi
            def init(self, *a, **kw):
                try:
                    return self._spi.init(*a, **kw)
                except Exception:
                    return None
            def write(self, buf, *a, **kw):
                try:
                    return self._spi.write(buf, *a, **kw)
                except Exception:
                    try:
                        if hasattr(self._spi, 'write_readinto'):
                            dummy = bytearray(len(buf))
                            return self._spi.write_readinto(buf, dummy)
                    except Exception:
                        pass
                    return None
            def read(self, nbytes, *a, **kw):
                try:
                    if hasattr(self._spi, 'read'):
                        return self._spi.read(nbytes, *a, **kw)
                except Exception:
                    pass
                try:
                    buf = bytearray(nbytes)
                    if hasattr(self._spi, 'readinto'):
                        self._spi.readinto(buf)
                        return bytes(buf)
                    if hasattr(self._spi, 'write_readinto'):
                        out = bytes([0]*nbytes)
                        self._spi.write_readinto(out, buf)
                        return bytes(buf)
                except Exception:
                    pass
                return bytes([0]*nbytes)
            def readinto(self, buf, *a, **kw):
                try:
                    return self._spi.readinto(buf, *a, **kw)
                except Exception:
                    return None
            def write_readinto(self, out, into, *a, **kw):
                try:
                    return self._spi.write_readinto(out, into, *a, **kw)
                except Exception:
                    return None
            def deinit(self, *a, **kw):
                try:
                    if hasattr(self._spi, 'deinit'):
                        return self._spi.deinit(*a, **kw)
                except Exception:
                    pass
                return None
        return _SPIShim(spi)
    except Exception:
        return None

async def init_lora():
    global lora
    print('[DEBUG] init_lora start')
    try:
        # Defensive hardware prep: ensure CS high (inactive), RST pulsed, BUSY/IRQ as inputs
        try:
            _safe_pin_out(settings.CS_PIN, 1)  # CS high
        except Exception:
            pass
        try:
            _safe_pin_input(settings.BUSY_PIN)
            _safe_pin_input(settings.IRQ_PIN)
        except Exception:
            pass
        # Pulse reset to try to put chip into known state before instantiation
        try:
            _pulse_reset(settings.RST_PIN, low_ms=50, post_high_ms=120)
        except Exception:
            pass

        print('[DEBUG] init_lora: BEFORE SX1262 instantiation (pins prepped)')
        lora = SX1262(
            settings.SPI_BUS, settings.CLK_PIN, settings.MOSI_PIN, settings.MISO_PIN,
            settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN
        )
        print('[DEBUG] init_lora: SX1262 object created')
        # Ensure any leftover SPI is clean
        _deinit_spi_if_any(lora)
        # Guarded begin: retry and attempt to attach a machine.SPI instance if the driver
        # throws an AttributeError referencing a missing 'write' (common when SPI wasn't bound).
        async def _attempt_begin(lo, attempts=3):
            # Try proactively attaching a shim (helps drivers that expect spi already present)
            try:
                shim = _attach_spi_shim()
                if shim and not getattr(lo, 'spi', None):
                    lo.spi = shim
                    await debug_print("lora: pre-attached machine.SPI shim before begin attempts", "LORA")
            except Exception:
                pass

            # Try several begin invocation patterns to handle differing driver signatures
            for i in range(attempts):
                try:
                    # Preferred / full signature first
                    status = lo.begin(
                        freq=settings.FREQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
                        syncWord=settings.SYNC_WORD, power=settings.POWER,
                        currentLimit=settings.CURRENT_LIMIT, preambleLength=settings.PREAMBLE_LEN,
                        implicit=False, implicitLen=0xFF, crcOn=settings.CRC_ON, txIq=False, rxIq=False,
                        tcxoVoltage=settings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO
                    )
                    return status
                except AttributeError as ae:
                    # Missing attribute on underlying SPI/native binding: attach shim and retry
                    try:
                        msg = str(ae)
                    except Exception:
                        msg = ''
                    await debug_print(f"lora.begin AttributeError: {msg}", "ERROR")
                    try:
                        shim = _attach_spi_shim()
                        if shim:
                            lo.spi = shim
                            await debug_print("lora: attached machine.SPI shim and retrying begin", "LORA")
                        else:
                            await debug_print("lora: no usable machine.SPI instance available", "ERROR")
                    except Exception:
                        pass
                    try:
                        _time.sleep_ms(120)
                    except Exception:
                        pass
                    continue
                except TypeError as te:
                    # Some ports/drivers may raise TypeError (unexpected keyword arg). Try fallback signatures.
                    try:
                        msg = str(te)
                    except Exception:
                        msg = ''
                    await debug_print(f"lora.begin TypeError: {msg} (attempt {i+1})", "WARN")
                    # Try reduced signatures one-by-one
                    tried = False
                    try:
                        # Minimal kwargs
                        status = lo.begin(freq=settings.FREQ, power=settings.POWER)
                        return status
                    except Exception:
                        tried = True
                    try:
                        # Positional: freq, bw, sf
                        status = lo.begin(settings.FREQ, settings.BW, settings.SF)
                        return status
                    except Exception:
                        pass
                    # Try attaching a fresh SPI shim and re-instantiating driver with spi object if constructor allows
                    try:
                        shim = _attach_spi_shim()
                        if shim:
                            try:
                                # Some SX1262 wrappers accept a pre-constructed SPI instance as first argument
                                try:
                                    lo2 = SX1262(shim, settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN)
                                except Exception:
                                    # Try keyword form
                                    lo2 = SX1262(spi=shim, cs=settings.CS_PIN, irq=settings.IRQ_PIN, rst=settings.RST_PIN, busy=settings.BUSY_PIN)
                                # swap and retry begin
                                lo = lo2
                                status = lo.begin(freq=settings.FREQ)
                                return status
                            except Exception as re:
                                await debug_print(f"lora: re-instantiation with SPI shim failed: {re}", "ERROR")
                    except Exception:
                        pass
                    # Give a small settle time and try again outer loop
                    try:
                        _time.sleep_ms(120)
                    except Exception:
                        pass
                    continue
                except Exception as e:
                    await debug_print(f"lora.begin exception: {e}", "ERROR")
                    return -999
            return -999

        status = await _attempt_begin(lora, attempts=2)
        print(f'[DEBUG] init_lora: lora.begin() returned {status}')
        # If chip not found, attempt diagnostics, re-instantiation with shim, reset and a single retry.
        if status == -2:
            await debug_print('lora: chip not found, performing diagnostics & retry', 'LORA')
            try:
                # Diagnostics: device errors, status, and SPI presence/type
                try:
                    dev_err = lora.getDeviceErrors()
                    await debug_print(f"lora: device errors 0x{dev_err:04X}", "LORA")
                except Exception:
                    pass
                try:
                    st = lora.getStatus()
                    await debug_print(f"lora: status {st}", "LORA")
                except Exception:
                    pass
                try:
                    spi_obj = getattr(lora, 'spi', None)
                    await debug_print(f"lora: spi present? {bool(spi_obj)} type={type(spi_obj)} has_write={hasattr(spi_obj, 'write') if spi_obj else False}", "LORA")
                except Exception:
                    pass

                # Try to reinstantiate driver using a shim (some ports accept an SPI instance in constructor)
                try:
                    shim = _attach_spi_shim()
                    if shim:
                        await debug_print("lora: attempting re-instantiation with SPI shim", "LORA")
                        newlo = None
                        try:
                            # positional variant (common)
                            newlo = SX1262(shim, settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN)
                        except Exception:
                            try:
                                # keyword variant (some wrappers)
                                newlo = SX1262(spi=shim, cs=settings.CS_PIN, irq=settings.IRQ_PIN, rst=settings.RST_PIN, busy=settings.BUSY_PIN)
                            except Exception:
                                newlo = None
                        if newlo:
                            lora = newlo
                            await debug_print("lora: re-instantiated SX1262 with shim, retrying begin", "LORA")
                except Exception:
                    pass

                # Pulse reset and wait, then try a single begin again (conservative)
                try:
                    _pulse_reset(settings.RST_PIN, low_ms=80, post_high_ms=200)
                    _time.sleep_ms(140)
                    status = lora.begin(
                        freq=settings.FREQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
                        syncWord=settings.SYNC_WORD, power=settings.POWER,
                        currentLimit=settings.CURRENT_LIMIT, preambleLength=settings.PREAMBLE_LEN,
                        implicit=False, implicitLen=0xFF, crcOn=settings.CRC_ON, txIq=False, rxIq=False,
                        tcxoVoltage=settings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO
                    )
                    await debug_print(f'lora: retry begin {status}', 'LORA')
                except Exception as re:
                    await debug_print(f'LoRa retry exception: {re}', 'ERROR')
            except Exception as exc:
                await debug_print(f'LoRa chip-not-found diagnostics failed: {exc}', 'ERROR')
                await log_error(f'LoRa chip-not-found diagnostics failed: {exc}')
                lora = None
                return False
        if status == 0:
            # Configure non-blocking operation and verify it succeeded
            rc = lora.setBlockingCallback(False)
            if rc != 0:
                try:
                    from _sx126x import ERROR as SXERR
                    err_name = SXERR.get(rc, 'UNKNOWN')
                except Exception:
                    err_name = 'UNKNOWN'
                await debug_print(f"lora: setBlockingCallback fail {rc}", "ERROR")
                await log_error(f"LoRa setBlockingCallback failed: {rc} ({err_name})")
                await free_pins()
                lora = None
                return False
            # Double-check radio packet type is LoRa
            try:
                from _sx126x import SX126X_PACKET_TYPE_LORA
                pkt_type = lora.getPacketType()
                if pkt_type != SX126X_PACKET_TYPE_LORA:
                    await debug_print("lora: init verify pkt_type mismatch", "ERROR")
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
        if status == 0:
            await debug_print("lora: initialized", "LORA")
            try:
                from oled import display_message
                await display_message("LoRa Ready", 2)
            except Exception:
                pass
            print_remote_nodes()
            # Ensure base starts in RX mode to listen for remotes
            try:
                if getattr(settings, 'NODE_TYPE', 'base') == 'base' and lora is not None:
                    lora.setOperatingMode(lora.MODE_RX)
                    await debug_print("init_lora: base set MODE_RX after begin", "LORA")
                elif getattr(settings, 'NODE_TYPE', 'base') == 'remote' and lora is not None:
                    lora.setOperatingMode(lora.MODE_STDBY)
                    await debug_print("init_lora: remote set MODE_STDBY after begin", "LORA")
            except Exception as e_mode:
                await debug_print(f"init_lora: failed to set initial operating mode: {e_mode}", "ERROR")
            print('[DEBUG] init_lora: completed successfully')
            return True
        if status != 0:
            # Map error code to readable name
            try:
                from _sx126x import ERROR as SXERR
                err_name = SXERR.get(status, 'UNKNOWN')
            except Exception:
                err_name = 'UNKNOWN'
            error_msg = f"LoRa initialization failed with status: {status} ({err_name})"
            await debug_print(error_msg, "ERROR")
            try:
                from oled import display_message
                await display_message("LoRa Error", 2)
            except Exception:
                pass
            await log_error(error_msg)
            # On persistent failure, try to put pins into a safe input state so a soft reboot starts clean
            try:
                _safe_pin_input(settings.CS_PIN)
                _safe_pin_input(settings.RST_PIN)
                _safe_pin_input(settings.IRQ_PIN)
                _safe_pin_input(settings.BUSY_PIN)
            except Exception:
                pass
            lora = None
            return False
        await debug_print("lora: initialized", "LORA")
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
        try:
            from oled import display_message
            await display_message("LoRa Error", 2)
        except Exception:
            pass
        await log_error(error_msg)
        # Ensure we deinit spi/pins when exceptional abort happens
        try:
            _deinit_spi_if_any(lora)
        except Exception:
            pass
        await free_pins()
        lora = None
        return False

_last_send_ms = 0
_last_activity_ms = 0
_init_failures = 0
_MAX_INIT_FAILS = 3

# Add cooldown guard for repeated TX exceptions (ms)
_last_tx_exception_ms = 0
_TX_EXCEPTION_COOLDOWN_MS = 2500  # avoid tight re-init loops on persistent TX failures

async def connectLora():
    """Non-blocking LoRa routine called frequently from lora_comm_task.
    - Initializes radio once (with retry cap)
    - Remote: sends payload at interval, waits for TX_DONE briefly, then returns
    - Base: polls for RX_DONE and processes any message
    - Idle timeout: deinit after prolonged inactivity to save power
    Returns True if LoRa is initialized and usable, else False.
    """
    global lora, _last_send_ms, _last_activity_ms, _init_failures, _last_tx_exception_ms
    global _connected_remotes, _pending_commands

    # Respect ENABLE_LORA flag like previous version
    if not getattr(settings, 'ENABLE_LORA', True):
        try:
            await debug_print("connectLora: ENABLE_LORA is False, skipping LoRa work", "LORA")
        except Exception:
            pass
        return False

    # --- INITIALIZE SHARED LOCALS TO AVOID UnboundLocalError ---
    # Defensive defaults for locals that may be referenced in exception handlers
    state = -999
    resp = None
    st = None
    st2 = None
    dev_err = None
    busy_val = None
    msg2 = None
    err2 = None
    tb = ''
    tx_start = 0
    # Extra locals that may otherwise be referenced before assignment in complex flows
    parts = []
    total = 0
    part_failure = False
    chunk_sent = False
    attempt = 0
    st_code = None
    # TX/RX flags: evaluate early and reuse (safe even if SX1262 missing)
    TX_DONE_FLAG = getattr(SX1262, 'TX_DONE', None) if SX1262 is not None else None
    RX_DONE_FLAG = getattr(SX1262, 'RX_DONE', None) if SX1262 is not None else None

    now = time.ticks_ms()
    role = getattr(settings, 'NODE_TYPE', 'base')
    try:
        await debug_print(
            f"connectLora: entry role={role} lora_is_none={lora is None} "
            f"last_send_ms={_last_send_ms} last_activity_ms={_last_activity_ms}",
            "LORA",
        )
    except Exception:
        pass

    # Avoid hammering radio when recent TX exception occurred
    try:
        if _last_tx_exception_ms and time.ticks_diff(now, _last_tx_exception_ms) < _TX_EXCEPTION_COOLDOWN_MS:
            # small backoff window — don't attempt sends/initialization right away
            await debug_print('lora: cooling down after recent TX error', 'LORA')
            return False
    except Exception:
        pass

    # Ensure initialized
    if lora is None:
        if _init_failures >= _MAX_INIT_FAILS:
            # Stop hammering if it keeps failing
            try:
                await debug_print("connectLora: max init failures reached, not reinitializing", "ERROR")
            except Exception:
                pass
            return False
        await debug_print("LoRa: initializing...", "LORA")
        async with pin_lock:
            ok = await init_lora()
        if not ok:
            _init_failures += 1
            try:
                await debug_print(f"connectLora: init_lora failed (count={_init_failures})", "ERROR")
            except Exception:
                pass
            return False
        _init_failures = 0
        _last_activity_ms = now
        try:
            await debug_print("connectLora: init_lora succeeded", "LORA")
        except Exception:
            pass

    # Choose behavior by role
    # (role already computed above)
    # --- Base: listen for remote messages and persist them ---
    if role == 'base':
        try:
            # Poll events briefly for incoming RX frames
            RX_DONE_FLAG = getattr(SX1262, 'RX_DONE', None)
            try:
                ev = lora._events()
            except Exception:
                ev = 0
            try:
                await debug_print(
                    f"lora base: _events=0x{ev:X} RX_DONE_FLAG={RX_DONE_FLAG}",
                    "LORA",
                )
            except Exception:
                pass
            if RX_DONE_FLAG is not None and (ev & RX_DONE_FLAG):
                try:
                    msg_bytes, err = lora._readData(0)
                    try:
                        await debug_print(
                            f"lora base: _readData err={err} len={len(msg_bytes) if msg_bytes else 0}",
                            "LORA",
                        )
                    except Exception:
                        pass
                except Exception as rexc:
                    await debug_print(f"lora: _readData exception: {rexc}", "ERROR")
                    msg_bytes = None; err = -1
                if err == 0 and msg_bytes:
                    try:
                        # Normalize to text for JSON parsing (bytes -> str)
                        if isinstance(msg_bytes, (bytes, bytearray)):
                            txt = msg_bytes.decode('utf-8', 'ignore')
                        else:
                            txt = str(msg_bytes)
                        try:
                            payload = ujson.loads(txt)
                        except Exception:
                            # not json; store raw
                            payload = {'raw': txt}
                        # Handle chunked messages
                        if isinstance(payload, dict) and payload.get('chunked'):
                            try:
                                uid = str(payload.get('unit_id') or 'unknown')
                                seq = int(payload.get('seq', 1))
                                total = int(payload.get('total', 1))
                                b64 = payload.get('b64', '') or ''
                                if not b64:
                                    raise ValueError('empty_chunk')
                                raw_chunk = _ub.a2b_base64(b64)
                                entry = _lora_incoming_chunks.get(uid, {'total': total, 'parts': {}, 'ts': int(time.time())})
                                entry['total'] = total
                                entry['parts'][seq] = raw_chunk
                                entry['ts'] = int(time.time())
                                _lora_incoming_chunks[uid] = entry
                                # If complete, reassemble and process as a single payload
                                if len(entry['parts']) == entry['total']:
                                    try:
                                        assembled = b''.join(entry['parts'][i] for i in range(1, entry['total'] + 1))
                                        try:
                                            assembled_obj = ujson.loads(assembled.decode('utf-8', 'ignore'))
                                        except Exception:
                                            assembled_obj = {'raw': assembled.decode('utf-8', 'ignore')}
                                        # Replace payload with assembled and continue processing using existing branch
                                        payload = assembled_obj
                                    finally:
                                        try:
                                            del _lora_incoming_chunks[uid]
                                        except Exception:
                                            pass
                                else:
                                    # waiting for more parts; skip persistence until complete
                                    # Was `continue` here (invalid outside loop) — return to caller instead.
                                    return True
                            except Exception as e:
                                await debug_print(f"lora: chunk handling error: {e}", "ERROR")
                                # Was `continue` here (invalid outside loop) — exit handler cleanly.
                                return True

                        # existing processing logic: persist record etc.
                        record = {'received_at': int(time.time()), 'source': 'remote', 'from_radio': True}
                        if isinstance(payload, dict):
                            record.update(payload)
                        else:
                            record['data'] = payload

                        # NEW: derive unit_id early for later tracking / commands
                        uid = record.get('unit_id') or record.get('unit') or record.get('name')
                        if uid is not None:
                            uid = str(uid)

                        # Persist to field data log so base later uploads remote telemetry via WPREST
                        try:
                            checkLogDirectory()
                            fd_path = getattr(settings, 'FIELD_DATA_LOG', settings.LOG_DIR + '/field_data.log')
                            with open(fd_path, 'a') as f:
                                f.write(ujson.dumps(record) + '\n')
                        except Exception as e:
                            await debug_print(f"lora: failed to persist remote line: {e}", "ERROR")

                        # Also record full system snapshot like previous version
                        try:
                            record_field_data()
                        except Exception:
                            pass

                        # NEW: update connected remotes and run min/max stats + queue commands (old logic integrated)
                        try:
                            now_ts = int(time.time())
                            if uid:
                                _connected_remotes[uid] = now_ts
                            # Use numeric telemetry if present
                            temp_f_val = None
                            bar_val = None
                            humid_val = None
                            try:
                                if 't_f' in record:
                                    temp_f_val = float(record.get('t_f'))
                                elif 'TEMP_F' in record:
                                    temp_f_val = float(record.get('TEMP_F'))
                            except Exception as ve:
                                await debug_print(f"Invalid TEMP_F value in record: {ve}", "ERROR")
                                temp_f_val = None
                            try:
                                if 'bar' in record:
                                    bar_val = float(record.get('bar'))
                                elif 'BAR' in record:
                                    bar_val = float(record.get('BAR'))
                            except Exception as ve:
                                await debug_print(f"Invalid BAR value in record: {ve}", "ERROR")
                                bar_val = None
                            try:
                                if 'hum' in record:
                                    humid_val = float(record.get('hum'))
                                elif 'HUMID' in record:
                                    humid_val = float(record.get('HUMID'))
                            except Exception as ve:
                                await debug_print(f"Invalid HUMID value in record: {ve}", "ERROR")
                                humid_val = None

                            # Mirror old min/max tracking if we have values
                            try:
                                if temp_f_val is not None:
                                    await findLowestTemp(temp_f_val)
                                    await findHighestTemp(temp_f_val)
                                if bar_val is not None:
                                    await findLowestBar(bar_val)
                                    await findHighestBar(bar_val)
                                if humid_val is not None:
                                    await findLowestHumid(humid_val)
                                    await findHighestHumid(humid_val)
                            except Exception as e_stats:
                                await debug_print(f"LORA stats update failed: {e_stats}", "ERROR")

                            # Example criteria: queue relay command like previous version
                            try:
                                if uid and (temp_f_val is not None):
                                    # NOTE: keep same example condition as previous version (customize as needed)
                                    if temp_f_val < 80:
                                        _pending_commands[uid] = "toggle_relay(1,on,5)"
                            except Exception:
                                pass
                        except Exception:
                            pass

                        # update in-memory remote info and write file
                        try:
                            if uid:
                                # Preserve COMPANY/SITE/ZONE/CLUSTER metadata like previous version
                                info = getattr(settings, 'REMOTE_NODE_INFO', {})
                                node = info.get(str(uid), {})
                                # Meta fields may appear uppercase or lowercase in record
                                for src_keys, dst in (
                                    (('COMPANY', 'company'), 'COMPANY'),
                                    (('SITE', 'site'), 'SITE'),
                                    (('ZONE', 'zone'), 'ZONE'),
                                    (('CLUSTER', 'cluster'), 'CLUSTER'),
                                ):
                                    val = None
                                    for sk in src_keys:
                                        if sk in record:
                                            val = record.get(sk)
                                            break
                                    if val is not None:
                                        node[dst] = val
                                node['last_seen'] = int(time.time())
                                node['last_payload'] = record
                                info[str(uid)] = node
                                settings.REMOTE_NODE_INFO = info
                                save_remote_node_info()

                                # If remote sent staged settings, persist to per-unit staged file for later apply/inspection
                                if isinstance(payload, dict) and payload.get('settings'):
                                    try:
                                        staged_path = settings.LOG_DIR.rstrip('/') + f'/device_settings-{uid}.json'
                                        with open(staged_path, 'w') as sf:
                                            ujson.dump(payload.get('settings'), sf)
                                        write_lora_log(f"Base: persisted staged settings for {uid}", 'INFO')
                                    except Exception:
                                        pass
                                # Best-effort: ACK back to remote with next sync, optional GPS, and optional CMD
                                try:
                                    ack = {'ack': 'ok'}
                                    # schedule next_in seconds (base chooses cadence)
                                    next_in = getattr(settings, 'LORA_CHECK_IN_MINUTES', 5) * 60
                                    ack['next_in'] = next_in

                                    # NEW: embed pending command (if any) into ACK JSON
                                    try:
                                        cmd = _pending_commands.pop(uid, None)
                                    except Exception:
                                        cmd = None
                                    if cmd:
                                        ack['cmd'] = cmd
                                        ack['cmd_target'] = uid

                                    if getattr(settings, 'GPS_BROADCAST_TO_REMOTES', False):
                                        try:
                                            ack['gps_lat'] = getattr(settings, 'GPS_LAT', None)
                                            ack['gps_lng'] = getattr(settings, 'GPS_LNG', None)
                                            ack['gps_alt_m'] = getattr(settings, 'GPS_ALT_M', None)
                                            ack['gps_accuracy_m'] = getattr(settings, 'GPS_ACCURACY_M', None)
                                            ack['gps_last_fix_ts'] = getattr(settings, 'GPS_LAST_FIX_TS', None)
                                        except Exception:
                                            pass
                                    try:
                                        # send ack (best-effort). Radio may need reconfig, so guard heavily.
                                        try:
                                            await debug_print(
                                                f"lora base: sending ACK to {uid}: {ack}",
                                                "LORA",
                                            )
                                        except Exception:
                                            pass
                                        try:
                                            # Wait for not busy before mode change
                                            busy_start = time.ticks_ms()
                                            while lora.gpio.value() and time.ticks_diff(time.ticks.ms(), busy_start) < 2000:
                                                await asyncio.sleep(0.01)
                                            lora.setOperatingMode(lora.MODE_TX)
                                            try:
                                                await debug_print("lora base: MODE_TX set for ACK", "LORA")
                                            except Exception:
                                                pass
                                            lora.send(ujson.dumps(ack).encode('utf-8'))
                                            # Wait briefly for TX_DONE then restore RX mode
                                            ack_start = time.ticks_ms()
                                            while time.ticks_diff(time.ticks.ms(), ack_start) < 2000:
                                                ev_ack = 0
                                                try:
                                                    ev_ack = lora._events()
                                                except Exception:
                                                    ev_ack = 0
                                                if getattr(lora, 'TX_DONE', 0) and (ev_ack & lora.TX_DONE):
                                                    try:
                                                        await debug_print(
                                                            f"lora base: ACK TX_DONE events=0x{ev_ack:X}",
                                                            "LORA",
                                                        )
                                                    except Exception:
                                                        pass
                                                    break
                                                await asyncio.sleep(0.01)
                                            # Wait for not busy after TX_DONE
                                            busy_start = time.ticks_ms()
                                            while lora.gpio.value() and time.ticks_diff(time.ticks.ms(), busy_start) < 2000:
                                                await asyncio.sleep(0.01)
                                            lora.setOperatingMode(lora.MODE_RX)
                                            try:
                                                await debug_print("lora base: MODE_RX restored after ACK", "LORA")
                                            except Exception:
                                                pass
                                        except Exception:
                                            # try a more direct sequence if the driver has explicit tx API
                                            try:
                                                lora.setOperatingMode(lora.MODE_TX)
                                                lora.send(ujson.dumps(ack).encode('utf-8'))
                                                lora.setOperatingMode(lora.MODE_RX)
                                                try:
                                                    await debug_print(
                                                        "lora base: fallback ACK send sequence used",
                                                        "LORA",
                                                    )
                                                except Exception:
                                                    pass
                                            except Exception as ack_exc:
                                                try:
                                                    await debug_print(
                                                        f"lora base: ACK send failed: {ack_exc}",
                                                        "ERROR",
                                                    )
                                                except Exception:
                                                    pass
                                    except Exception:
                                        pass
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        write_lora_log(f"Base received remote payload: {str(record)[:160]}", 'INFO')
                    except Exception as e:
                        await debug_print(f"lora: processing RX failed: {e}", "ERROR")
        except Exception as e:
            await debug_print(f"lora: base RX loop exception: {e}", "ERROR")

    # --- Remote TX flow (unchanged but hardened) ---
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
            try:
                await debug_print(
                    f"lora remote: now_epoch={now_epoch} nextLoraSync={next_sync} "
                    f"last_send_ms={_last_send_ms} due={due}",
                    "LORA",
                )
            except Exception:
                pass
        except Exception:
            due = (_last_send_ms == 0) or (time.ticks_diff(now, _last_send_ms) >= probe_interval_ms)

        if not due:
            # Light heartbeat so we know remote is evaluating but not sending yet
            try:
                if random.random() < 0.1:
                    await debug_print("lora remote: not due to send this cycle", "LORA")
            except Exception:
                pass

        if due:
            try:
                await debug_print("lora remote: TX cycle starting (building payload)", "LORA")
            except Exception:
                pass
            try:
                # Build compact payload
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

                # Integrate previous-version metadata and runtime fields so base can
                # mirror connection logic and relay command criteria.
                try:
                    payload.update({
                        'COMPANY': getattr(settings, 'COMPANY', ''),
                        'SITE': getattr(settings, 'SITE', ''),
                        'ZONE': getattr(settings, 'ZONE', ''),
                        'CLUSTER': getattr(settings, 'CLUSTER', ''),
                        'RUNTIME': getattr(sdata, 'loop_runtime', 0),
                        'SCRIPT_RUNTIME': getattr(sdata, 'script_runtime', 0),
                        # Uppercase aliases matching older parsing logic
                        'TEMP_C': getattr(sdata, 'cur_temp_c', 0),
                        'TEMP_F': getattr(sdata, 'cur_temp_f', 0),
                        'BAR': getattr(sdata, 'cur_bar_pres', 0),
                        'HUMID': getattr(sdata, 'cur_humid', 0),
                    })
                except Exception:
                    pass

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

                # NEW: only chunk if data actually exceeds safe payload size
                max_payload = int(getattr(settings, 'LORA_MAX_PAYLOAD', 255) or 255)

                # Quick single-frame send when payload fits — avoids tiny chunk floods for modest payloads
                if len(data) <= max_payload:
                    # Ensure radio present
                    if lora is None:
                        await debug_print ("lora: reinit before single-frame send", "LORA")
                        async with pin_lock:
                            ok = await init_lora()
                        if not ok:
                            await debug_print("lora: single-frame send aborted, radio unavailable", "ERROR")
                            return False

                    # NEW: ensure TX mode and wait for not-busy; perform bounded retry loop on transient codes
                    single_retries = int(getattr(settings, 'LORA_SINGLE_FRAME_RETRIES', 2))
                    sent = False
                    for sr in range(1, single_retries + 1):
                        try:
                            # wait for not-busy (short)
                            try:
                                busy_start = time.ticks_ms()
                                while True:
                                    gpio = getattr(lora, 'gpio', None)
                                    busy = gpio.value() if gpio and hasattr(gpio, 'value') else False
                                    if not busy:
                                        break
                                    if time.ticks_diff(time.ticks_ms(), busy_start) > 400:
                                        break
                                    await asyncio.sleep(0.01)
                            except Exception:
                                pass
                            try:
                                lora.setOperatingMode(lora.MODE_TX)
                                await asyncio.sleep(0.02)
                            except Exception:
                                pass

                            # diagnostic snapshot before send
                            try:
                                ev_pre = lora._events()
                            except Exception:
                                ev_pre = None
                            try:
                                gpio_pre = getattr(lora, 'gpio', None).value() if getattr(lora, 'gpio', None) and hasattr(lora.gpio, 'value') else None
                            except Exception:
                                gpio_pre = None
                            await debug_print(f"lora: single-frame pre-send events={ev_pre} gpio={gpio_pre}", "LORA")

                            # send
                            try:
                                resp = lora.send(data)
                            except Exception as send_exc:
                                await debug_print(f"lora: single-frame send() raised: {send_exc}", 'ERROR')
                                resp = -999

                            # normalize status
                            st_code = None
                            try:
                                if isinstance(resp, (tuple, list)):
                                    if len(resp) >= 2 and isinstance(resp[1], int):
                                        st_code = resp[1]
                                    elif len(resp) >= 1 and isinstance(resp[0], int):
                                        st_code = resp[0]
                                    else:
                                        try:
                                            st_code = int(resp[0])
                                        except Exception:
                                            st_code = -999
                                elif isinstance(resp, int):
                                    st_code = resp
                                else:
                                    try:
                                        st_code = int(resp)
                                    except Exception:
                                        st_code = -999
                            except Exception:
                                st_code = -999

                            # diagnostic after send
                            try:
                                ev_post = lora._events()
                            except Exception:
                                ev_post = None
                            await debug_print(f"lora: single-frame resp={resp} code={st_code} events_post={ev_post}", "LORA")

                            if st_code == 0:
                                sent = True
                                break

                            # On transient negative or known transient codes, retry locally first
                            transient_codes = set(getattr(settings, 'LORA_CHUNK_TRANSIENT_CODES', [86, 87, 89]) or [86,87,89])
                            if (st_code in transient_codes) or (st_code == -1) or (st_code == -999):
                                await debug_print(f"lora: single-frame transient err {st_code} (attempt {sr}/{single_retries})", "WARN")
                                await asyncio.sleep(0.06 + random.random() * 0.06)
                                # loop to retry
                                continue

                            # otherwise treat as severe and break to re-init handling below
                            await debug_print(f"lora: single-frame error {st_code} (fatal)", "ERROR")
                            break
                        except Exception:
                            await asyncio.sleep(0.05)
                            continue

                    if sent:
                        # wait for TX_DONE and optional ACK same as chunk flow
                        try:
                            tx_start = time.ticks_ms()
                            await debug_print("lora remote: waiting for TX_DONE", "LORA")
                        except Exception:
                            tx_start = time.ticks_ms()
                        while time.ticks_diff(time.ticks.ms(), tx_start) < 10000:
                            try:
                                ev = lora._events()
                            except Exception:
                                ev = 0
                            if TX_DONE_FLAG is not None and (ev & TX_DONE_FLAG):
                                try:
                                    await debug_print(f"lora remote: TX_DONE events=0x{ev:X}", "LORA")
                                except Exception:
                                    pass
                                break
                            await asyncio.sleep(0.01)
                        try:
                            lora.setOperatingMode(lora.MODE_RX)
                            await debug_print("lora remote: MODE_RX set after TX", "LORA")
                        except Exception:
                            pass
                        _last_send_ms = time.ticks_ms()
                        _last_activity_ms = _last_send_ms
                        # Wait for ACK
                        ack_wait_ms = int(getattr(settings, 'LORA_CHUNK_ACK_WAIT_MS', 1500))
                        start_wait = time.ticks_ms()
                        try:
                            await debug_print(f"lora remote: waiting for ACK up to {ack_wait_ms} ms", "LORA")
                        except Exception:
                            pass
                        while time.ticks_diff(time.ticks.ms(), start_wait) < ack_wait_ms:
                            try:
                                ev2 = lora._events()
                            except Exception:
                                ev2 = 0
                            if RX_DONE_FLAG is not None and (ev2 & RX_DONE_FLAG):
                                try:
                                    await debug_print(
                                        f"lora remote: RX_DONE for ACK events=0x{ev2:X}",
                                        "LORA",
                                    )
                                except Exception:
                                    pass
                                try:
                                    msg2, err2 = lora._readData(0)
                                except Exception:
                                    msg2 = None; err2 = -1
                                if err2 == 0 and msg2:
                                    try:
                                        obj2 = None
                                        txt2 = msg2.decode('utf-8', 'ignore') if isinstance(msg2, (bytes, bytearray)) else str(msg2)
                                        try:
                                            obj2 = ujson.loads(txt2)
                                        except Exception:
                                            obj2 = None
                                        try:
                                            await debug_print(
                                                f"lora remote: ACK payload raw='{txt2[:80]}' parsed={bool(obj2)}",
                                                "LORA",
                                            )
                                        except Exception:
                                            pass
                                        if isinstance(obj2, dict) and obj2.get('ack') == 'ok':
                                            # Capture signal info
                                            try:
                                                if hasattr(lora, 'getRSSI'):
                                                    sdata.lora_SigStr = lora.getRSSI()
                                                if hasattr(lora, 'getSNR'):
                                                    sdata.lora_snr = lora.getSNR()
                                                    sdata.last_message = ujson.dumps(obj2)[:32]
                                            except Exception:
                                                pass
                                            # Adopt next sync
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
                                            # Adopt GPS from base if provided and allowed
                                            try:
                                                if getattr(settings, 'GPS_ACCEPT_FROM_BASE', True):
                                                    blat = obj2.get('gps_lat')
                                                    blng = obj2.get('gps_lng')
                                                    if (blat is not None) and (blng is not None):
                                                        balt = obj2.get('gps_alt_m')
                                                        bacc = obj2.get('gps_accuracy_m')
                                                        bts = obj2.get('gps_last_fix_ts')
                                                        save_gps_state(blat, blng, balt, bacc, bts)
                                                        await debug_print('lora: GPS adopted', 'LORA')
                                            except Exception:
                                                pass

                                            # NEW: handle optional relay command from ACK JSON
                                            try:
                                                cmd_str = obj2.get('cmd')
                                                if cmd_str:
                                                    target = obj2.get('cmd_target', 'ALL')
                                                    if target == 'ALL' or str(target) == str(getattr(settings, 'UNIT_ID', '')):
                                                        await _execute_command_string(cmd_str)
                                            except Exception:
                                                pass

                                            await debug_print(f"lora: next {getattr(settings, 'nextLoraSync', '')}", 'LORA')
                                            write_lora_log(
                                                f"Remote stored next sync epoch: {getattr(settings, 'nextLoraSync', '')}",
                                                'INFO'
                                            )
                                            led_status_flash('SUCCESS')
                                            break
                                    except Exception:
                                        pass
                            await asyncio.sleep(0.01)
                        return True
            except Exception as e:
                await debug_print(f'lora: remote TX exception: {e}', 'ERROR')
                try:
                    _last_tx_exception_ms = time.ticks_ms()
                except Exception:
                    pass
                # on remote failure, keep radio but record failure
                return False

    # --- Idle-time deinit for power saving ---
    try:
        idle_ms = int(getattr(settings, 'LORA_IDLE_TIMEOUT_MS', 300000))  # default 5 minutes
        if lora is not None and _last_activity_ms and time.ticks_diff(now, _last_activity_ms) > idle_ms:
            await debug_print('lora: idle timeout reached, deinit radio', 'LORA')
            try:
                _deinit_spi_if_any(lora)
            except Exception:
                pass
            try:
                await free_pins()
            except Exception:
                pass
            lora = None
            return False
    except Exception:
        pass

    # If we reach here, just report whether LoRa is currently usable
    return lora is not None