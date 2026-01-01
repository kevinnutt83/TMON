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
from utils import free_pins, checkLogDirectory, debug_print, TMON_AI, safe_run, led_status_flash, write_lora_log, persist_unit_id
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
    try:W: simple operator reminder — mismatched/absent antennas can prevent any RF
        # Defensive hardware prep: ensure CS high (inactive), RST pulsed, BUSY/IRQ as inputs
        try:t('[DEBUG] LoRa init: ensure matched 868MHz antennas are attached on all nodes')
            _safe_pin_out(settings.CS_PIN, 1)  # CS high
        except Exception:
            pass
        try:fensive hardware prep: ensure CS high (inactive), RST pulsed, BUSY/IRQ as inputs
            _safe_pin_input(settings.BUSY_PIN)
            _safe_pin_input(settings.IRQ_PIN)  # CS high
        except Exception:
            pass
        # Pulse reset to try to put chip into known state before instantiation
        try:_safe_pin_input(settings.BUSY_PIN)
            _pulse_reset(settings.RST_PIN, low_ms=50, post_high_ms=120)
        except Exception:
            pass
        # Pulse reset to try to put chip into known state before instantiation
        print('[DEBUG] init_lora: BEFORE SX1262 instantiation (pins prepped)')
        lora = SX1262(et(settings.RST_PIN, low_ms=50, post_high_ms=120)
            settings.SPI_BUS, settings.CLK_PIN, settings.MOSI_PIN, settings.MISO_PIN,
            settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN
        )
        print('[DEBUG] init_lora: SX1262 object created')tion (pins prepped)')
        # Ensure any leftover SPI is clean
        _deinit_spi_if_any(lora)ttings.CLK_PIN, settings.MOSI_PIN, settings.MISO_PIN,
        # Guarded begin: retry and attempt to attach a machine.SPI instance if the driver
        # throws an AttributeError referencing a missing 'write' (common when SPI wasn't bound).
        async def _attempt_begin(lo, attempts=3):reated')
            # Try proactively attaching a shim (helps drivers that expect spi already present)
            try:uick SPI sanity test before begin(); failure here often indicates wiring/pin issues.
                shim = _attach_spi_shim()
                if shim and not getattr(lo, 'spi', None):
                    lo.spi = shim)
                    await debug_print("lora: pre-attached machine.SPI shim before begin attempts", "LORA")us health.
            except Exception:ster(0x0320, buf, 4)
                passt('[DEBUG] init_lora: SPI test OK, reg 0x0320 =', buf)
            else:
            # Try several begin invocation patterns to handle differing driver signatures')
            for i in range(attempts):
                try:DEBUG] init_lora: SPI test failed:', e)
                    # Preferred / full signature first
                    status = lo.begin(lean
                        freq=settings.FREQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
                        syncWord=settings.SYNC_WORD, power=settings.POWER,e
                        currentLimit=settings.CURRENT_LIMIT, preambleLength=settings.PREAMBLE_LEN,
                        implicit=False, implicitLen=0xFF, crcOn=settings.CRC_ON, txIq=False, rxIq=False,
                        tcxoVoltage=settings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO
                    )= _attach_spi_shim()
                    return statusetattr(lo, 'spi', None):
                except AttributeError as ae:
                    # Missing attribute on underlying SPI/native binding: attach shim and retrys", "LORA")
                    try:tion:
                        msg = str(ae)
                    except Exception:
                        msg = ''invocation patterns to handle differing driver signatures
                    await debug_print(f"lora.begin AttributeError: {msg}", "ERROR")
                    try:
                        shim = _attach_spi_shim()first
                        if shim:begin(
                            lo.spi = shimQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
                            await debug_print("lora: attached machine.SPI shim and retrying begin", "LORA")
                        else:ntLimit=settings.CURRENT_LIMIT, preambleLength=settings.PREAMBLE_LEN,
                            await debug_print("lora: no usable machine.SPI instance available", "ERROR")
                    except Exception:ettings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO
                        pass
                    try:rn status
                        _time.sleep_ms(120):
                    except Exception:te on underlying SPI/native binding: attach shim and retry
                        pass
                    continue= str(ae)
                except TypeError as te:
                    # Some ports/drivers may raise TypeError (unexpected keyword arg). Try fallback signatures.
                    try:t debug_print(f"lora.begin AttributeError: {msg}", "ERROR")
                        msg = str(te)
                    except Exception:h_spi_shim()
                        msg = ''
                    await debug_print(f"lora.begin TypeError: {msg} (attempt {i+1})", "WARN")
                    # Try reduced signatures one-by-onetached machine.SPI shim and retrying begin", "LORA")
                    tried = False
                    try:    await debug_print("lora: no usable machine.SPI instance available", "ERROR")
                        # Minimal kwargs
                        status = lo.begin(freq=settings.FREQ, power=settings.POWER)
                        return status
                    except Exception:s(120)
                        tried = True:
                    try:pass
                        # Positional: freq, bw, sf
                        status = lo.begin(settings.FREQ, settings.BW, settings.SF)
                        return statusers may raise TypeError (unexpected keyword arg). Try fallback signatures.
                    except Exception:
                        pass= str(te)
                    # Try attaching a fresh SPI shim and re-instantiating driver with spi object if constructor allows
                    try:msg = ''
                        shim = _attach_spi_shim()n TypeError: {msg} (attempt {i+1})", "WARN")
                        if shim:d signatures one-by-one
                            try:e
                                # Some SX1262 wrappers accept a pre-constructed SPI instance as first argument
                                try:args
                                    lo2 = SX1262(shim, settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN)
                                except Exception:
                                    # Try keyword form
                                    lo2 = SX1262(spi=shim, cs=settings.CS_PIN, irq=settings.IRQ_PIN, rst=settings.RST_PIN, busy=settings.BUSY_PIN)
                                # swap and retry begin
                                lo = lo2eq, bw, sf
                                status = lo.begin(freq=settings.FREQ) settings.SF)
                                return status
                            except Exception as re:
                                await debug_print(f"lora: re-instantiation with SPI shim failed: {re}", "ERROR")
                    except Exception: fresh SPI shim and re-instantiating driver with spi object if constructor allows
                        pass
                    # Give a small settle time and try again outer loop
                    try:if shim:
                        _time.sleep_ms(120)
                    except Exception:e SX1262 wrappers accept a pre-constructed SPI instance as first argument
                        pass    try:
                    continue        lo2 = SX1262(shim, settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN)
                except Exception as e: Exception:
                    await debug_print(f"lora.begin exception: {e}", "ERROR")
                    return -999     lo2 = SX1262(spi=shim, cs=settings.CS_PIN, irq=settings.IRQ_PIN, rst=settings.RST_PIN, busy=settings.BUSY_PIN)
            return -999         # swap and retry begin
                                lo = lo2
        status = await _attempt_begin(lora, attempts=2)settings.FREQ)
        print(f'[DEBUG] init_lora: lora.begin() returned {status}')
        # If chip not found, attempt diagnostics, re-instantiation with shim, reset and a single retry.
        if status == -2:        await debug_print(f"lora: re-instantiation with SPI shim failed: {re}", "ERROR")
            await debug_print('lora: chip not found, performing diagnostics & retry', 'LORA')
            try:        pass
                # Diagnostics: device errors, status, and SPI presence/type
                try:try:
                    dev_err = lora.getDeviceErrors()
                    await debug_print(f"lora: device errors 0x{dev_err:04X}", "LORA")
                except Exception:
                    passinue
                try:pt Exception as e:
                    st = lora.getStatus()ora.begin exception: {e}", "ERROR")
                    await debug_print(f"lora: status {st}", "LORA")
                except Exception:
                    pass
                try:it _attempt_begin(lora, attempts=2)
                    spi_obj = getattr(lora, 'spi', None) {status}')
                    await debug_print(f"lora: spi present? {bool(spi_obj)} type={type(spi_obj)} has_write={hasattr(spi_obj, 'write') if spi_obj else False}", "LORA")
                except Exception:
                    passprint('lora: chip not found, performing diagnostics & retry', 'LORA')
            try:
                # Try to reinstantiate driver using a shim (some ports accept an SPI instance in constructor)
                try:
                    shim = _attach_spi_shim()rrors()
                    if shim:bug_print(f"lora: device errors 0x{dev_err:04X}", "LORA")
                        await debug_print("lora: attempting re-instantiation with SPI shim", "LORA")
                        newlo = None
                        try:
                            # positional variant (common)
                            newlo = SX1262(shim, settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN)
                        except Exception:
                            try:
                                # keyword variant (some wrappers)
                                newlo = SX1262(spi=shim, cs=settings.CS_PIN, irq=settings.IRQ_PIN, rst=settings.RST_PIN, busy=settings.BUSY_PIN)
                            except Exception: spi present? {bool(spi_obj)} type={type(spi_obj)} has_write={hasattr(spi_obj, 'write') if spi_obj else False}", "LORA")
                                newlo = None
                        if newlo:
                            lora = newlo
                            await debug_print("lora: re-instantiated SX1262 with shim, retrying begin", "LORA")
                except Exception:
                    pass = _attach_spi_shim()
                    if shim:
                # Pulse reset and wait, then try a single begin again (conservative)I shim", "LORA")
                try:    newlo = None
                    _pulse_reset(settings.RST_PIN, low_ms=80, post_high_ms=200)
                    _time.sleep_ms(140)l variant (common)
                    status = lora.begin(62(shim, settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN)
                        freq=settings.FREQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
                        syncWord=settings.SYNC_WORD, power=settings.POWER,
                        currentLimit=settings.CURRENT_LIMIT, preambleLength=settings.PREAMBLE_LEN,
                        implicit=False, implicitLen=0xFF, crcOn=settings.CRC_ON, txIq=False, rxIq=False,ettings.RST_PIN, busy=settings.BUSY_PIN)
                        tcxoVoltage=settings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO
                    )           newlo = None
                    await debug_print(f'lora: retry begin {status}', 'LORA')
                except Exception as re:o
                    await debug_print(f'LoRa retry exception: {re}', 'ERROR')ith shim, retrying begin", "LORA")
            except Exception as exc:
                await debug_print(f'LoRa chip-not-found diagnostics failed: {exc}', 'ERROR')
                await log_error(f'LoRa chip-not-found diagnostics failed: {exc}')
                lora = Noneet and wait, then try a single begin again (conservative)
                return False
        if status == 0:lse_reset(settings.RST_PIN, low_ms=80, post_high_ms=200)
            # Configure non-blocking operation and verify it succeeded
            rc = lora.setBlockingCallback(False)
            if rc != 0: freq=settings.FREQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
                try:    syncWord=settings.SYNC_WORD, power=settings.POWER,
                    from _sx126x import ERROR as SXERRLIMIT, preambleLength=settings.PREAMBLE_LEN,
                    err_name = SXERR.get(rc, 'UNKNOWN')F, crcOn=settings.CRC_ON, txIq=False, rxIq=False,
                except Exception:ge=settings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO
                    err_name = 'UNKNOWN'
                await debug_print(f"lora: setBlockingCallback fail {rc}", "ERROR")
                await log_error(f"LoRa setBlockingCallback failed: {rc} ({err_name})")
                await free_pins()rint(f'LoRa retry exception: {re}', 'ERROR')
                lora = Nonen as exc:
                return Falseprint(f'LoRa chip-not-found diagnostics failed: {exc}', 'ERROR')
            # Double-check radio packet type is LoRad diagnostics failed: {exc}')
            try:lora = None
                from _sx126x import SX126X_PACKET_TYPE_LORA
                pkt_type = lora.getPacketType()
                if pkt_type != SX126X_PACKET_TYPE_LORA: self-interference on all nodes when supported.
                    await debug_print("lora: init verify pkt_type mismatch", "ERROR")
                    await log_error(f"LoRa init verify failed: packet type={pkt_type}")
                    await free_pins())
                    lora = None_print("lora: setRxIq(True) applied", "LORA")
                    return Falsea, 'setIqInvert'):
            except Exception as ve:t(True)
                await debug_print(f"LoRa init verify exception: {ve}", "ERROR"))
                await log_error(f"LoRa init verify exception: {ve}")
                await free_pins()
                lora = None
                return Falserent LoRa RF parameters once after successful begin when debugging is enabled.
        if status == 0:
            await debug_print("lora: initialized", "LORA") False):
            try:    try:
                from oled import display_message() if hasattr(lora, 'getFrequency') else None
                await display_message("LoRa Ready", 2) if hasattr(lora, 'getSpreadingFactor') else None
            except Exception:lora.getBandwidth() if hasattr(lora, 'getBandwidth') else None
                pass    cr = lora.getCodingRate() if hasattr(lora, 'getCodingRate') else None
            print_remote_nodes()a.getSyncWord() if hasattr(lora, 'getSyncWord') else None
            # Ensure base starts in RX mode to listen for remotes(lora, 'getPreambleLength') else None
            try:        crc_on = lora.getCRC() if hasattr(lora, 'getCRC') else None
                if getattr(settings, 'NODE_TYPE', 'base') == 'base' and lora is not None:
                    lora.setOperatingMode(lora.MODE_RX)= crc_on = None
                elif getattr(settings, 'NODE_TYPE', 'base') == 'remote' and lora is not None:
                    lora.setOperatingMode(lora.MODE_STDBY){freq} BW={bw} SF={sf} CR={cr} SYNC=0x{(sw or 0):X} PREAMBLE={pre} CRC_ON={crc_on}")
            except Exception:ception:
                pass    pass
            print('[DEBUG] init_lora: completed successfully')
            return True
        if status != 0:
            # Map error code to readable namen and verify it succeeded
            try: lora.setBlockingCallback(False)
                from _sx126x import ERROR as SXERR
                err_name = SXERR.get(status, 'UNKNOWN')
            except Exception:26x import ERROR as SXERR
                err_name = 'UNKNOWN'.get(rc, 'UNKNOWN')
            error_msg = f"LoRa initialization failed with status: {status} ({err_name})"
            await debug_print(error_msg, "ERROR")
            try:await debug_print(f"lora: setBlockingCallback fail {rc}", "ERROR")
                from oled import display_messagengCallback failed: {rc} ({err_name})")
                await display_message("LoRa Error", 2)
            except Exception:
                passrn False
            await log_error(error_msg)t type is LoRa
            # On persistent failure, try to put pins into a safe input state so a soft reboot starts clean
            try:from _sx126x import SX126X_PACKET_TYPE_LORA
                _safe_pin_input(settings.CS_PIN)
                _safe_pin_input(settings.RST_PIN)_LORA:
                _safe_pin_input(settings.IRQ_PIN) verify pkt_type mismatch", "ERROR")
                _safe_pin_input(settings.BUSY_PIN)rify failed: packet type={pkt_type}")
            except Exception:e_pins()
                passlora = None
            lora = Noneurn False
            return Falsetion as ve:
        await debug_print("lora: initialized", "LORA")xception: {ve}", "ERROR")
        print_remote_nodes()ror(f"LoRa init verify exception: {ve}")
        # Ensure base starts in RX mode to listen for remotes
        try:    lora = None
            if getattr(settings, 'NODE_TYPE', 'base') == 'base' and lora is not None:
                lora.setOperatingMode(lora.MODE_RX)
        except Exception:rint("lora: initialized", "LORA")
            pass
        print('[DEBUG] init_lora: completed successfully')
        return Trueit display_message("LoRa Ready", 2)
    except Exception as e:on:
        error_msg = f"Exception in init_lora: {e}"
        print(error_msg)_nodes()
        await debug_print(error_msg, "ERROR")o listen for remotes
        try:try:
            from oled import display_messageYPE', 'base') == 'base' and lora is not None:
            await display_message("LoRa Error", 2)E_RX)
        except Exception:ttr(settings, 'NODE_TYPE', 'base') == 'remote' and lora is not None:
            pass    lora.setOperatingMode(lora.MODE_STDBY)
        await log_error(error_msg)
        # Ensure we deinit spi/pins when exceptional abort happens
        try:print('[DEBUG] init_lora: completed successfully')
            _deinit_spi_if_any(lora)
        except Exception:
            passp error code to readable name
        await free_pins()
        lora = Nonem _sx126x import ERROR as SXERR
        return Falsename = SXERR.get(status, 'UNKNOWN')
            except Exception:
_last_send_ms = 0rr_name = 'UNKNOWN'
_last_activity_ms = 0 = f"LoRa initialization failed with status: {status} ({err_name})"
_init_failures = 0debug_print(error_msg, "ERROR")
_MAX_INIT_FAILS = 3
                from oled import display_message
# Add cooldown guard for repeated TX exceptions (ms)2)
_last_tx_exception_ms = 0ion:
_TX_EXCEPTION_COOLDOWN_MS = 2500  # avoid tight re-init loops on persistent TX failures
_last_rssi_log_ms = 0            await log_error(error_msg)
ent failure, try to put pins into a safe input state so a soft reboot starts clean
async def connectLora():
    """Non-blocking LoRa routine called frequently from lora_comm_task.IN)
    - Initializes radio once (with retry cap)
    - Remote: sends payload at interval, waits for TX_DONE briefly, then returns
    - Base: polls for RX_DONE and processes any message
    - Idle timeout: deinit after prolonged inactivity to save power
    Returns True if LoRa is initialized and usable, else False.         pass
    """
    global lora, _last_send_ms, _last_activity_ms, _init_failures, _last_tx_exception_ms, _last_rssi_log_ms            return False

    # --- INITIALIZE SHARED LOCALS TO AVOID UnboundLocalError ---
    # Defensive defaults for locals that may be referenced in exception handlers base starts in RX mode to listen for remotes
    state = -999
    resp = Nonef getattr(settings, 'NODE_TYPE', 'base') == 'base' and lora is not None:
    st = None  lora.setOperatingMode(lora.MODE_RX)
    st2 = Noneeption:
    dev_err = None
    busy_val = None[DEBUG] init_lora: completed successfully')
    msg2 = NoneTrue
    err2 = NoneException as e:
    tb = ''g = f"Exception in init_lora: {e}"
    tx_start = 0
    # Extra locals that may otherwise be referenced before assignment in complex flowsdebug_print(error_msg, "ERROR")
    parts = []
    total = 0port display_message
    part_failure = Falselay_message("LoRa Error", 2)
    chunk_sent = FalseException:
    attempt = 0
    st_code = None
    # TX/RX flags: evaluate early and reuse (safe even if SX1262 missing)
    TX_DONE_FLAG = getattr(SX1262, 'TX_DONE', None) if SX1262 is not None else None
    RX_DONE_FLAG = getattr(SX1262, 'RX_DONE', None) if SX1262 is not None else None            _deinit_spi_if_any(lora)

    now = time.ticks_ms()            pass

    # Avoid hammering radio when recent TX exception occurredlora = None
    try:
        if _last_tx_exception_ms and time.ticks_diff(now, _last_tx_exception_ms) < _TX_EXCEPTION_COOLDOWN_MS:
            # small backoff window — don't attempt sends/initialization right away
            await debug_print('lora: cooling down after recent TX error', 'LORA')
            return False
    except Exception:ILS = 3
        pass
 repeated TX exceptions (ms)
    # Ensure initializeds = 0
    if lora is None:ht re-init loops on persistent TX failures
        if _init_failures >= _MAX_INIT_FAILS:or low-noise periodic diagnostics)
            # Stop hammering if it keeps failing
            return False
        await debug_print("LoRa: initializing...", "LORA")
        async with pin_lock:alled frequently from lora_comm_task.
            ok = await init_lora()radio once (with retry cap)
        if not ok:interval, waits for TX_DONE briefly, then returns
            _init_failures += 1_DONE and processes any message
            return False after prolonged inactivity to save power
        _init_failures = 0tialized and usable, else False.
        _last_activity_ms = now    """
s, _last_activity_ms, _init_failures, _last_tx_exception_ms
    # Choose behavior by role
    role = getattr(settings, 'NODE_TYPE', 'base')    # --- INITIALIZE SHARED LOCALS TO AVOID UnboundLocalError ---
xception handlers
    # --- Base: listen for remote messages and persist them ---
    if role == 'base':one
        try:
            # Poll events briefly for incoming RX frames
            RX_DONE_FLAG = getattr(SX1262, 'RX_DONE', None)ne
            try:
                ev = lora._events()
            except Exception:
                ev = 0
            if RX_DONE_FLAG is not None and (ev & RX_DONE_FLAG):
                try:fore assignment in complex flows
                    msg_bytes, err = lora._readData(0)
                except Exception as rexc:
                    await debug_print(f"lora: _readData exception: {rexc}", "ERROR")
                    msg_bytes = None; err = -1
                if err == 0 and msg_bytes:
                    try:
                        # Normalize to text for JSON parsing (bytes -> str)ing)
                        if isinstance(msg_bytes, (bytes, bytearray)):None else None
                            txt = msg_bytes.decode('utf-8', 'ignore')1262, 'RX_DONE', None) if SX1262 is not None else None
                        else:
                            txt = str(msg_bytes)
                        try:
                            payload = ujson.loads(txt)X exception occurred
                        except Exception:
                            # not json; store rawff(now, _last_tx_exception_ms) < _TX_EXCEPTION_COOLDOWN_MS:
                            payload = {'raw': txt}t sends/initialization right away
                        # Handle chunked messages)
                        if isinstance(payload, dict) and payload.get('chunked'):
                            try:
                                uid = str(payload.get('unit_id') or 'unknown')
                                seq = int(payload.get('seq', 1))
                                total = int(payload.get('total', 1))
                                b64 = payload.get('b64', '') or ''
                                if not b64:
                                    raise ValueError('empty_chunk')
                                raw_chunk = _ub.a2b_base64(b64)
                                entry = _lora_incoming_chunks.get(uid, {'total': total, 'parts': {}, 'ts': int(time.time())})RA")
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
                                    finally:ng RX frames
                                        try:
                                            del _lora_incoming_chunks[uid]
                                        except Exception:
                                            pass
                                else:
                                    # waiting for more parts; skip persistence until complete
                                    # Was `continue` here (invalid outside loop) — return to caller instead.
                                    return Truea(0)
                            except Exception as e:
                                await debug_print(f"lora: chunk handling error: {e}", "ERROR")
                                # Was `continue` here (invalid outside loop) — exit handler cleanly. -1
                                return True                if err == 0 and msg_bytes:

                        # existing processing logic: persist record etc.
                        record = {'received_at': int(time.time()), 'source': 'remote', 'from_radio': True}es, bytearray)):
                        if isinstance(payload, dict):('utf-8', 'ignore')
                            record.update(payload)
                        else:
                            record['data'] = payload
                        # Persist to field data log so base later uploads remote telemetry via WPRESTpayload = ujson.loads(txt)
                        try:
                            checkLogDirectory()
                            fd_path = getattr(settings, 'FIELD_DATA_LOG', settings.LOG_DIR + '/field_data.log')
                            with open(fd_path, 'a') as f:
                                f.write(ujson.dumps(record) + '\n') dict) and payload.get('chunked'):
                        except Exception as e:
                            await debug_print(f"lora: failed to persist remote line: {e}", "ERROR")unknown')
                        # update in-memory remote info and write file    seq = int(payload.get('seq', 1))
                        try:
                            uid = record.get('unit_id') or record.get('unit') or record.get('name') = payload.get('b64', '') or ''
                            if uid:
                                settings.REMOTE_NODE_INFO = getattr(settings, 'REMOTE_NODE_INFO', {})
                                settings.REMOTE_NODE_INFO[str(uid)] = {'last_seen': int(time.time()), 'last_payload': record}e64(b64)
                                save_remote_node_info())
                                # If remote sent staged settings, persist to per-unit staged file for later apply/inspection
                                if isinstance(payload, dict) and payload.get('settings'):arts'][seq] = raw_chunk
                                    try:
                                        staged_path = settings.LOG_DIR.rstrip('/') + f'/device_settings-{uid}.json'
                                        with open(staged_path, 'w') as sf:ayload
                                            ujson.dump(payload.get('settings'), sf)
                                        write_lora_log(f"Base: persisted staged settings for {uid}", 'INFO')
                                    except Exception:mbled = b''.join(entry['parts'][i] for i in range(1, entry['total'] + 1))
                                        pass
                                # Best-effort: ACK back to remote with next sync and optional GPS        assembled_obj = ujson.loads(assembled.decode('utf-8', 'ignore'))
                                try:n:
                                    ack = {'ack': 'ok'}'utf-8', 'ignore')}
                                    # schedule next_in seconds (base chooses cadence) using existing branch
                                    next_in = getattr(settings, 'LORA_CHECK_IN_MINUTES', 5) * 60obj
                                    ack['next_in'] = next_in
                                    if getattr(settings, 'GPS_BROADCAST_TO_REMOTES', False):
                                        try:
                                            ack['gps_lat'] = getattr(settings, 'GPS_LAT', None)
                                            ack['gps_lng'] = getattr(settings, 'GPS_LNG', None)
                                            ack['gps_alt_m'] = getattr(settings, 'GPS_ALT_M', None)
                                            ack['gps_accuracy_m'] = getattr(settings, 'GPS_ACCURACY_M', None)rts; skip persistence until complete
                                        except Exception:nue` here (invalid outside loop) — return to caller instead.
                                            passrn True
                                    try:
                                        # send ack (best-effort). Radio may need reconfig, so guard heavily.print(f"lora: chunk handling error: {e}", "ERROR")
                                        try:t handler cleanly.
                                            # Wait for not busy before mode change
                                            busy_start = time.ticks_ms()
                                            while lora.gpio.value() and time.ticks_diff(time.ticks_ms(), busy_start) < 2000:
                                                await asyncio.sleep(0.01)emote', 'from_radio': True}
                                            lora.setOperatingMode(lora.MODE_TX)
                                            lora.send(ujson.dumps(ack).encode('utf-8'))
                                            # Wait briefly for TX_DONE then restore RX mode
                                            ack_start = time.ticks_ms()
                                            while time.ticks_diff(time.ticks_ms(), ack_start) < 2000:ploads remote telemetry via WPREST
                                                ev = lora._events()
                                                if getattr(lora, 'TX_DONE', 0) and (ev & lora.TX_DONE):
                                                    break settings.LOG_DIR + '/field_data.log')
                                                await asyncio.sleep(0.01)
                                            # Wait for not busy after TX_DONE
                                            busy_start = time.ticks_ms()
                                            while lora.gpio.value() and time.ticks_diff(time.ticks_ms(), busy_start) < 2000:emote line: {e}", "ERROR")
                                                await asyncio.sleep(0.01)
                                            lora.setOperatingMode(lora.MODE_RX)
                                        except Exception:
                                            # try a more direct sequence if the driver has explicit tx API
                                            try:TE_NODE_INFO', {})
                                                lora.setOperatingMode(lora.MODE_TX)e.time()), 'last_payload': record}
                                                lora.send(ujson.dumps(ack).encode('utf-8'))
                                                lora.setOperatingMode(lora.MODE_RX)ngs, persist to per-unit staged file for later apply/inspection
                                            except Exception:d, dict) and payload.get('settings'):
                                                pass
                                    except Exception:ed_path = settings.LOG_DIR.rstrip('/') + f'/device_settings-{uid}.json'
                                        pass(staged_path, 'w') as sf:
                                except Exception:    ujson.dump(payload.get('settings'), sf)
                                    passrite_lora_log(f"Base: persisted staged settings for {uid}", 'INFO')
                        except Exception:    except Exception:
                            pass
                        write_lora_log(f"Base received remote payload: {str(record)[:160]}", 'INFO')ort: ACK back to remote with next sync and optional GPS
                    except Exception as e:
                        await debug_print(f"lora: processing RX failed: {e}", "ERROR")      ack = {'ack': 'ok'}
        except Exception as e: cadence)
            await debug_print(f"lora: base RX loop exception: {e}", "ERROR")                                    next_in = getattr(settings, 'LORA_CHECK_IN_MINUTES', 5) * 60
    # --- Remote TX flow (unchanged but hardened) ---next_in
    if role == 'remote':            if getattr(settings, 'GPS_BROADCAST_TO_REMOTES', False):
        # Determine if it's time to TX. Before first contact, fall back to short probing interval.
        probe_interval_ms = 30 * 1000       ack['gps_lat'] = getattr(settings, 'GPS_LAT', None)
        next_sync = getattr(settings, 'nextLoraSync', 300) = getattr(settings, 'GPS_LNG', None)
        # If next_sync appears to be an absolute epoch (far in the future vs boot ticks), schedule against wall time
        due = False                         ack['gps_accuracy_m'] = getattr(settings, 'GPS_ACCURACY_M', None)
        try:                            except Exception:
            # Assume utime.time() returns epoch seconds; consider due if now_epoch >= next_sync
            now_epoch = time.time() try:
            if isinstance(next_sync, int) or isinstance(next_sync, float):y need reconfig, so guard heavily.
                if next_sync > 100000:  # treat as absolute epoch
                    due = now_epoch >= next_syncit for not busy before mode change
                else:                       busy_start = time.ticks_ms()
                    # Not yet provisioned; probe periodicallyalue() and time.ticks_diff(time.ticks_ms(), busy_start) < 2000:
                    due = (_last_send_ms == 0) or (time.ticks_diff(now, _last_send_ms) >= probe_interval_ms)
            else:                           lora.setOperatingMode(lora.MODE_TX)
                due = (_last_send_ms == 0) or (time.ticks_diff(now, _last_send_ms) >= probe_interval_ms)
        except Exception:                   # Wait briefly for TX_DONE then restore RX mode
            due = (_last_send_ms == 0) or (time.ticks_diff(now, _last_send_ms) >= probe_interval_ms)
                                            while time.ticks_diff(time.ticks_ms(), ack_start) < 2000:
        if due:                                 ev = lora._events()
            # NEW: optional CAD/busy-channel check before any TX; skip when DISABLE_CAD_FOR_TESTING is True.                                if getattr(lora, 'TX_DONE', 0) and (ev & lora.TX_DONE):
            try:             break
                if not getattr(settings, 'DISABLE_CAD_FOR_TESTING', False):                     await asyncio.sleep(0.01)
                    if hasattr(lora, 'cad'):after TX_DONE
                        busy = Falseicks_ms()
                        try:              while lora.gpio.value() and time.ticks_diff(time.ticks_ms(), busy_start) < 2000:
                            # some drivers accept no args, others (symb) countio.sleep(0.01)
                            busy = lora.cad()ngMode(lora.MODE_RX)
                        except TypeError:
                            try:ct sequence if the driver has explicit tx API
                                busy = lora.cad(getattr(settings, 'CAD_SYMBOLS', 8))
                            except Exception:OperatingMode(lora.MODE_TX)
                                busy = False.encode('utf-8'))
                        if busy:.MODE_RX)
                            await debug_print("lora: CAD detected busy; backing off", "LORA")                           except Exception:
                            try:                            pass
                                print("CAD detected busy; backing off")
                            except Exception:
                                pass
                            back = getattr(settings, 'LORA_CAD_BACKOFF_S', 2)     pass
                            back_max = getattr(settings, 'LORA_CAD_BACKOFF_MAX_S', 60)pt Exception:
                            if back_max > 0:
                                back = min(back, back_max)yload: {str(record)[:160]}", 'INFO')
                            await asyncio.sleep(back)
                            return False(f"lora: processing RX failed: {e}", "ERROR")
                else:
                    try:lora: base RX loop exception: {e}", "ERROR")
                        print("CAD disabled for testing")
                    except Exception:
                        pass
            except Exception:efore first contact, fall back to short probing interval.
                pass 1000
oraSync', 300)
            try:vs boot ticks), schedule against wall time
                # Build compact payload
                payload = {
                    'unit_id': getattr(settings, 'UNIT_ID', ''),seconds; consider due if now_epoch >= next_sync
                    'name': getattr(settings, 'UNIT_Name', ''),
                    'ts': now,_sync, float):
                    't_f': getattr(sdata, 'cur_temp_f', 0),epoch
                    't_c': getattr(sdata, 'cur_temp_c', 0),epoch >= next_sync
                    'hum': getattr(sdata, 'cur_humid', 0),
                    'bar': getattr(sdata, 'cur_bar_pres', 0),
                    'v': getattr(sdata, 'sys_voltage', 0),send_ms == 0) or (time.ticks_diff(now, _last_send_ms) >= probe_interval_ms)
                    'fm': getattr(sdata, 'free_mem', 0),
                    'net': getattr(settings, 'LORA_NETWORK_NAME', 'tmon'),                due = (_last_send_ms == 0) or (time.ticks_diff(now, _last_send_ms) >= probe_interval_ms)
                    'key': getattr(settings, 'LORA_NETWORK_PASSWORD', ''),
                }_send_ms == 0) or (time.ticks_diff(now, _last_send_ms) >= probe_interval_ms)
                try:
                    if getattr(settings, 'LORA_HMAC_ENABLED', False):
                        import uhashlib, ubinascii, ujson
                        ctr_file = getattr(settings, 'LORA_HMAC_COUNTER_FILE', '/logs/lora_ctr.json')
                        ctr = 0
                        try:
                            with open(ctr_file, 'r') as cf:
                                ctr_obj = ujson.loads(cf.read())
                                ctr = int(ctr_obj.get('ctr', 0))
                        except Exception:ata, 'cur_temp_c', 0),
                            ctr = 0
                        ctr += 1bar': getattr(sdata, 'cur_bar_pres', 0),
                        try:
                            with open(ctr_file, 'w') as cfw:                    'fm': getattr(sdata, 'free_mem', 0),
                                cfw.write(ujson.dumps({'ctr': ctr}))
                        except Exception:
                            pass                }
                        payload['ctr'] = ctr
                        secret = getattr(settings, 'LORA_HMAC_SECRET', '')RA_HMAC_ENABLED', False):
                        if secret:binascii, ujson
                            mac_src = b"|".join([etattr(settings, 'LORA_HMAC_COUNTER_FILE', '/logs/lora_ctr.json')
                                secret.encode(),
                                str(payload['unit_id']).encode(),
                                str(payload['ts']).encode(),') as cf:
                                str(payload['ctr']).encode()r_obj = ujson.loads(cf.read())
                            ])
                            h = uhashlib.sha256(mac_src):
                            payload['sig'] = ubinascii.hexlify(h.digest())[:32].decode()                            ctr = 0
                except Exception:
                    pass
 open(ctr_file, 'w') as cfw:
                if getattr(settings, 'LORA_ENCRYPT_ENABLED', False) and chacha20_encrypt and derive_nonce:': ctr}))
                    try:pt Exception:
                        secret = getattr(settings, 'LORA_ENCRYPT_SECRET', '')
                        key = secret.encode()'ctr'] = ctr
                        if len(key) < 32:C_SECRET', '')
                            key = (key + b'\x00'*32)[:32]
                        nonce = derive_nonce(int(time.time()), int(payload.get('ctr', 0)))
                        pt = ujson.dumps(payload).encode('utf-8')
                        ct = chacha20_encrypt(key, nonce, 1, pt)t_id']).encode(),
                        env = {'enc': 1, 'nonce': ''.join('{:02x}'.format(b) for b in nonce), 'ct': ''.join('{:02x}'.format(b) for b in ct), 'net': payload.get('net'), 'key': payload.get('key')}ts']).encode(),
                        data = ujson.dumps(env).encode('utf-8')
                    except Exception:
                        data = ujson.dumps(payload).encode('utf-8')
                else:ubinascii.hexlify(h.digest())[:32].decode()
                    data = ujson.dumps(payload).encode('utf-8')

                # NEW: only chunk if data actually exceeds safe payload size
                max_payload = int(getattr(settings, 'LORA_MAX_PAYLOAD', 255) or 255)D', False) and chacha20_encrypt and derive_nonce:

                # Quick single-frame send when payload fits — avoids tiny chunk floods for modest payloadsattr(settings, 'LORA_ENCRYPT_SECRET', '')
                if len(data) <= max_payload:                        key = secret.encode()
                    # Ensure radio present
                    if lora is None:= (key + b'\x00'*32)[:32]
                        await debug_print("lora: reinit before single-frame send", "LORA")ime()), int(payload.get('ctr', 0)))
                        async with pin_lock:oad).encode('utf-8')
                            ok = await init_lora()(key, nonce, 1, pt)
                        if not ok:enc': 1, 'nonce': ''.join('{:02x}'.format(b) for b in nonce), 'ct': ''.join('{:02x}'.format(b) for b in ct), 'net': payload.get('net'), 'key': payload.get('key')}
                            await debug_print("lora: single-frame send aborted, radio unavailable", "ERROR")
                            return False
oad).encode('utf-8')
                    # NEW: ensure TX mode and wait for not-busy; perform bounded retry loop on transient codes
                    single_retries = int(getattr(settings, 'LORA_SINGLE_FRAME_RETRIES', 2))                    data = ujson.dumps(payload).encode('utf-8')
                    sent = False
                    for sr in range(1, single_retries + 1):k if data actually exceeds safe payload size
                        try:ORA_MAX_PAYLOAD', 255) or 255)
                            # wait for not-busy (short)
                            try:
                                busy_start = time.ticks_ms():
                                while True:                    # Ensure radio present
                                    gpio = getattr(lora, 'gpio', None)
                                    busy = gpio.value() if gpio and hasattr(gpio, 'value') else False"lora: reinit before single-frame send", "LORA")
                                    if not busy:th pin_lock:
                                        break
                                    if time.ticks_diff(time.ticks_ms(), busy_start) > 400:
                                        breakle-frame send aborted, radio unavailable", "ERROR")
                                    await asyncio.sleep(0.01)
                            except Exception:
                                pass and wait for not-busy; perform bounded retry loop on transient codes
                            try:attr(settings, 'LORA_SINGLE_FRAME_RETRIES', 2))
                                lora.setOperatingMode(lora.MODE_TX)
                                await asyncio.sleep(0.02)):
                            except Exception:
                                pass

                            # diagnostic snapshot before sendstart = time.ticks_ms()
                            try:ue:
                                ev_pre = lora._events()pio', None)
                            except Exception:() if gpio and hasattr(gpio, 'value') else False
                                ev_pre = None
                            try:
                                gpio_pre = getattr(lora, 'gpio', None).value() if getattr(lora, 'gpio', None) and hasattr(lora.gpio, 'value') else Nonecks_diff(time.ticks_ms(), busy_start) > 400:
                            except Exception:                                        break
                                gpio_pre = Noneleep(0.01)
                            await debug_print(f"lora: single-frame pre-send events={ev_pre} gpio={gpio_pre}", "LORA")pt Exception:

                            # send
                            try:ingMode(lora.MODE_TX)
                                resp = lora.send(data)
                            except Exception as send_exc:                            except Exception:
                                await debug_print(f"lora: single-frame send() raised: {send_exc}", 'ERROR')
                                resp = -999
tic snapshot before send
                            # normalize status                            try:
                            st_code = None
                            try:
                                if isinstance(resp, (tuple, list)):
                                    if len(resp) >= 2 and isinstance(resp[1], int):
                                        st_code = resp[1]getattr(lora, 'gpio', None) and hasattr(lora.gpio, 'value') else None
                                    elif len(resp) >= 1 and isinstance(resp[0], int):
                                        st_code = resp[0] = None
                                    else:                            await debug_print(f"lora: single-frame pre-send events={ev_pre} gpio={gpio_pre}", "LORA")
                                        try:
                                            st_code = int(resp[0])
                                        except Exception:
                                            st_code = -999ra.send(data)
                                elif isinstance(resp, int):exc:
                                    st_code = respt debug_print(f"lora: single-frame send() raised: {send_exc}", 'ERROR')
                                else:                                resp = -999
                                    try:
                                        st_code = int(resp)
                                    except Exception:st_code = None
                                        st_code = -999
                            except Exception:
                                st_code = -999if len(resp) >= 2 and isinstance(resp[1], int):
1]
                            # diagnostic after send) >= 1 and isinstance(resp[0], int):
                            try:_code = resp[0]
                                ev_post = lora._events()
                            except Exception:ry:
                                ev_post = None(resp[0])
                            await debug_print(f"lora: single-frame resp={resp} code={st_code} events_post={ev_post}", "LORA")        except Exception:

                            if st_code == 0:ce(resp, int):
                                sent = Truest_code = resp
                                break
    try:
                            # On transient negative or known transient codes, retry locally firstesp)
                            transient_codes = set(getattr(settings, 'LORA_CHUNK_TRANSIENT_CODES', [86, 87, 89]) or [86,87,89])
                            if (st_code in transient_codes) or (st_code == -1) or (st_code == -999):  st_code = -999
                                await debug_print(f"lora: single-frame transient err {st_code} (attempt {sr}/{single_retries})", "WARN")
                                await asyncio.sleep(0.06 + random.random() * 0.06)
                                # loop to retry
                                continueagnostic after send

                            # otherwise treat as severe and break to re-init handling belowa._events()
                            await debug_print(f"lora: single-frame error {st_code} (fatal)", "ERROR")ption:
                            break
                        except Exception:bug_print(f"lora: single-frame resp={resp} code={st_code} events_post={ev_post}", "LORA")
                            await asyncio.sleep(0.05)
                            continue

                    if sent:
                        # wait for TX_DONE and optional ACK same as chunk flow
                        try: or known transient codes, retry locally first
                            tx_start = time.ticks_ms()
                            while time.ticks_diff(time.ticks_ms(), tx_start) < 10000:ransient_codes) or (st_code == -1) or (st_code == -999):
                                try:me transient err {st_code} (attempt {sr}/{single_retries})", "WARN")
                                    ev = lora._events()+ random.random() * 0.06)
                                except Exception:
                                    ev = 0
                                if TX_DONE_FLAG is not None and (ev & TX_DONE_FLAG):
                                    break severe and break to re-init handling below
                                await asyncio.sleep(0.01)_code} (fatal)", "ERROR")
                            try:
                                lora.setOperatingMode(lora.MODE_RX)
                            except Exception:
                                pass
                        except Exception:
                            pass
                        _last_send_ms = time.ticks_ms() flow
                        _last_activity_ms = _last_send_ms
                        # NEW: explicit debug before starting ACK wait to make remote behavior obvious
                        await debug_print("lora: sent packet; awaiting ACK (up to ~30s)", "LORA") 10000:
                        # Wait for ACK
                        ack_wait_ms = int(getattr(settings, 'LORA_CHUNK_ACK_WAIT_MS', 1500))
                        start_wait = time.ticks_ms()
                        while time.ticks_diff(time.ticks_ms(), start_wait) < ack_wait_ms:
                            try:
                                ev2 = lora._events()
                            except Exception:
                                ev2 = 0
                            if RX_DONE_FLAG is not None and (ev2 & RX_DONE_FLAG):e(lora.MODE_RX)
                                try:
                                    msg2, err2 = lora._readData(0)
                                except Exception:
                                    msg2 = None; err2 = -1
                                if err2 == 0 and msg2:
                                    try:
                                        obj2 = None
                                        txt2 = msg2.decode('utf-8', 'ignore') if isinstance(msg2, (bytes, bytearray)) else str(msg2)0))
                                        try:
                                            obj2 = ujson.loads(txt2)
                                        except Exception:
                                            obj2 = None
                                        if isinstance(obj2, dict) and obj2.get('ack') == 'ok':
                                            # Capture signal info for display
                                            try:
                                                if hasattr(lora, 'getRSSI'):
                                                    sdata.lora_SigStr = lora.getRSSI()lora._readData(0)
                                                if hasattr(lora, 'getSNR'):
                                                    sdata.lora_snr = lora.getSNR()one; err2 = -1
                                                sdata.last_message = ujson.dumps(obj2)[:32]:
                                            except Exception: try:
                                                pass                                        obj2 = None
                                            # Adopt next sync if providedtes, bytearray)) else str(msg2)
                                            try:
                                                if 'next_in' in obj2:                    obj2 = ujson.loads(txt2)
                                                    rel = int(obj2['next_in'])
                                                    if rel < 1:bj2 = None
                                                        rel = 1   if isinstance(obj2, dict) and obj2.get('ack') == 'ok':
                                                    if rel > 24 * 3600:                # Capture signal info for display
                                                        rel = 24 * 3600                    try:
                                                    settings.nextLoraSync = int(time.time() + rel), 'getRSSI'):
                                                elif 'next' in obj2:               sdata.lora_SigStr = lora.getRSSI()
                                                    settings.nextLoraSync = int(obj2['next'])                    if hasattr(lora, 'getSNR'):
                                            except Exception:                     sdata.lora_snr = lora.getSNR()
                                                pass                sdata.last_message = ujson.dumps(obj2)[:32]
                                            # Adopt GPS from base if provided and allowed                                            except Exception:
                                            try:
                                                if getattr(settings, 'GPS_ACCEPT_FROM_BASE', True):# Adopt next sync if provided
                                                    blat = obj2.get('gps_lat')
                                                    blng = obj2.get('gps_lng')
                                                    if (blat is not None) and (blng is not None):
                                                        balt = obj2.get('gps_alt_m')                    if rel < 1:
                                                        bacc = obj2.get('gps_accuracy_m')                                                        rel = 1
                                                        bts = obj2.get('gps_last_fix_ts')                          if rel > 24 * 3600:
                                                        save_gps_state(blat, blng, balt, bacc, bts)
                                                        await debug_print('lora: GPS adopted', 'LORA')time() + rel)
                                            except Exception:
                                                pass                                settings.nextLoraSync = int(obj2['next'])
                                            await debug_print(f"lora: next {getattr(settings, 'nextLoraSync', '')}", 'LORA')
                                            write_lora_log(f"Remote stored next sync epoch: {getattr(settings, 'nextLoraSync', '')}", 'INFO')
                                            led_status_flash('SUCCESS')S from base if provided and allowed
                                            break
                                    except Exception:               if getattr(settings, 'GPS_ACCEPT_FROM_BASE', True):
                                        pass    blat = obj2.get('gps_lat')
                            await asyncio.sleep(0.01)
                        return True                                                    if (blat is not None) and (blng is not None):
('gps_alt_m')
                    # If we reached here, single-frame failed after retries: treat as re-init trigger     bacc = obj2.get('gps_accuracy_m')
                    await debug_print("lora: single-frame send failed after retries, re-initing radio", "ERROR")                                bts = obj2.get('gps_last_fix_ts')
                    try:            save_gps_state(blat, blng, balt, bacc, bts)
                        if hasattr(lora, 'spi') and lora.spi:await debug_print('lora: GPS adopted', 'LORA')
                            lora.spi.deinit()cept Exception:
                    except Exception:pass
                        passt debug_print(f"lora: next {getattr(settings, 'nextLoraSync', '')}", 'LORA')
                    try:e_lora_log(f"Remote stored next sync epoch: {getattr(settings, 'nextLoraSync', '')}", 'INFO')
                        _last_tx_exception_ms = time.ticks_ms() led_status_flash('SUCCESS')
                    except Exception:  break
                        passxcept Exception:
                    lora = None
                    return False                            await asyncio.sleep(0.01)

                # ...existing chunking path (building parts / adaptive shrink)...
                # After sending all chunks, switch to RX and wait for ACKd here, single-frame failed after retries: treat as re-init trigger
                try:_print("lora: single-frame send failed after retries, re-initing radio", "ERROR")
                    lora.setOperatingMode(lora.MODE_RX)
                except Exception:(lora, 'spi') and lora.spi:
                    pass                            lora.spi.deinit()

                # NEW: explicit debug before ACK wait for chunked sends as well
                await debug_print("lora: sent chunked packet; awaiting ACK (up to ~30s)", "LORA")
                ack_wait_ms = int(getattr(settings, 'LORA_CHUNK_ACK_WAIT_MS', 1500))tion_ms = time.ticks_ms()
                start_wait = time.ticks_ms()                    except Exception:
                while time.ticks_diff(time.ticks_ms(), start_wait) < ack_wait_ms:
                    try:
                        ev2 = lora._events()
                    except Exception:
                        ev2 = 0payload
                    if RX_DONE_FLAG is not None and (ev2 & RX_DONE_FLAG):
                        try:ove on success, so if we reach here single-frame send must have failed but
                            msg2, err2 = lora._readData(0)
                        except Exception:ingle-frame send attempted and failed for small payload; aborting chunk fallback", "ERROR")
                            msg2 = None; err2 = -1
                        if err2 == 0 and msg2:
                            try:
                                obj2 = Noneettings, 'LORA_CHUNK_MIN_RAW_BYTES', 12))
                                txt2 = msg2.decode('utf-8', 'ignore') if isinstance(msg2, (bytes, bytearray)) else str(msg2)
                                try:estimate JSON overhead accurately
                                    obj2 = ujson.loads(txt2)
                                except Exception:gs, 'UNIT_ID', ''), 'chunked': 1, 'seq': 1, 'total': 1, 'b64': ''}
                                    obj2 = None
                                if isinstance(obj2, dict) and obj2.get('ack') == 'ok':
                                    # Capture signal info for display(min_raw, int((avail_b64 * 3) // 4)) if avail_b64 > 0 else min_raw
                                    try:                except Exception:
                                        if hasattr(lora, 'getRSSI'):
                                            sdata.lora_SigStr = lora.getRSSI()t(getattr(settings, 'LORA_CHUNK_RAW_BYTES', 50)))
                                        if hasattr(lora, 'getSNR'):
                                            sdata.lora_snr = lora.getSNR()imal telemetry shapes
                                        sdata.last_message = ujson.dumps(obj2)[:32]mal(p):
                                    except Exception:
                                        pass
                                    # Adopt next sync if provided
                                    try:
                                        if 'next_in' in obj2:
                                            rel = int(obj2['next_in'])
                                            if rel < 1:': p.get('bar'),
                                                rel = 1
                                            if rel > 24 * 3600:
                                                rel = 24 * 3600
                                            settings.nextLoraSync = int(time.time() + rel){'unit_id': p.get('unit_id'), 'ts': p.get('ts')}).encode('utf-8')
                                        elif 'next' in obj2:
                                            settings.nextLoraSync = int(obj2['next'])k attempts and per-chunk retries
                                    except Exception:
                                        pass
                                    # Adopt GPS from base if provided and allowed
                                    try:, 'LORA_CHUNK_MAX_RETRIES', 3))
                                        if getattr(settings, 'GPS_ACCEPT_FROM_BASE', True):
                                            blat = obj2.get('gps_lat')
                                            blng = obj2.get('gps_lng')er than a reasonable size, attempt compaction up-front
                                            if (blat is not None) and (blng is not None):hrinks and not sent_ok:
                                                balt = obj2.get('gps_alt_m')ge(0, len(data), raw_chunk_size)]
                                                bacc = obj2.get('gps_accuracy_m')
                                                bts = obj2.get('gps_last_fix_ts')
                                                save_gps_state(blat, blng, balt, bacc, bts) too many parts, try compressing payload to a minimal form
                                                await debug_print('lora: GPS adopted', 'LORA')ed:
                                    except Exception:lora: large split {total} parts > max {max_parts_allowed}, attempting compact payload", "LORA")
                                        pass
                                    await debug_print(f"lora: next {getattr(settings, 'nextLoraSync', '')}", 'LORA')ayload)
                                    write_lora_log(f"Remote stored next sync epoch: {getattr(settings, 'nextLoraSync', '')}", 'INFO')
                                    led_status_flash('SUCCESS')
                                    break[data[i:i+raw_chunk_size] for i in range(0, len(data), raw_chunk_size)]
                        except Exception:
                            pass
                    await asyncio.sleep(0.01)_allowed:
ttr(settings, 'UNIT_ID', ''), 'ts': payload.get('ts')}).encode('utf-8')
                # After sending all chunks, done for this cycle
                _last_send_ms = time.ticks_ms()chunk_size] for i in range(0, len(data), raw_chunk_size)]
                _last_activity_ms = _last_send_ms
                return True, abort
            except Exception as e:
                # ...existing unified exception handling for remote TX...print(f"lora: aborting chunk send, required parts {total} exceeds limit {max_parts_allowed}", "ERROR")
                return Falsetal} parts exceeds max {max_parts_allowed}", 'ERROR')
    # End of connectLora
    return True
                # Fallback: original generic exception handler (keeps existing behavior)
                try:
                    import sys
                    try:
                        import uio as io
                    except Exception:
                        import io
                    buf = io.StringIO()
                    try:
                        sys.print_exception(e, buf)
                        tb = buf.getvalue()
                    except Exception:
                        tb = str(e)
                except Exception:
                    tb = str(e)
                try:
                    msg = str(e)
                except Exception:
                    msg = repr(e)
                if 'local variable referenced before assignment' in msg.lower() or 'unboundlocalerror' in msg.lower():
                    await debug_print(f"Remote TX local-variable error detected: {msg}", "ERROR")
                else:
                    await debug_print(f"Remote TX exception: {msg}", "ERROR")
                await log_error(f"Remote TX exception: {msg} | trace: {tb}")

                # Best-effort locals snapshot (trimmed) for diagnostics
                try:
                    ls = {k: (str(v)[:160] if v is not None else None) for k, v in globals().items() if k in ('lora','state','resp','msg2','tx_start')}
                    write_lora_log(f"Remote TX exception locals snapshot: {ls}", 'DEBUG')
                except Exception:
                    pass

                try:
                    _init_failures = min(_init_failures + 1, _MAX_INIT_FAILS)
                except Exception:
                    pass
                try:
                    _last_tx_exception_ms = time.ticks_ms()
                except Exception:
                    pass

                # Cleanup hardware & state
                try:
                    if lora and hasattr(lora, 'spi') and lora.spi:
                        lora.spi.deinit()
                except Exception:
                    pass
                try:
                    await free_pins()
                except Exception:
                    pass
                lora = None
                return False
    # End of connectLora
    return True
