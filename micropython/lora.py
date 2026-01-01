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
    """Initialize SX1262 radio and put it into a known-good state."""
    global lora
    await debug_print('init_lora: start', 'LORA')
    try:
        # Operator reminder: antennas must be attached and matched
        try:
            print('[DEBUG] LoRa init: ensure matched 868MHz antennas are attached on all nodes')
        except Exception:
            pass

        if SX1262 is None or machine is None or settings is None:
            await debug_print('init_lora: SX1262/machine/settings not available', 'ERROR')
            return False

        # Hardware prep: CS high, BUSY/IRQ inputs, reset pulse
        try:
            _safe_pin_out(settings.CS_PIN, 1)
        except Exception:
            pass
        try:
            _safe_pin_input(settings.BUSY_PIN)
            _safe_pin_input(settings.IRQ_PIN)
        except Exception:
            pass
        try:
            _pulse_reset(settings.RST_PIN, low_ms=50, post_high_ms=120)
        except Exception:
            pass

        await debug_print('init_lora: creating SX1262', 'LORA')
        lora = SX1262(
            settings.SPI_BUS, settings.CLK_PIN, settings.MOSI_PIN, settings.MISO_PIN,
            settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN
        )

        # Quick SPI sanity check (helps catch wiring/pin mistakes early)
        try:
            if hasattr(lora, 'readRegister'):
                buf = bytearray(4)
                lora.readRegister(0x0320, buf, 4)
                print('[DEBUG] init_lora: SPI test OK, reg 0x0320 =', buf)
        except Exception as e:
            print('[DEBUG] init_lora: SPI test failed:', e)

        # Attach SPI shim if driver did not bind SPI
        try:
            if not getattr(lora, 'spi', None):
                shim = _attach_spi_shim()
                if shim:
                    lora.spi = shim
                    await debug_print('init_lora: attached SPI shim', 'LORA')
        except Exception:
            pass

        # Call begin() with full parameter set, then fall back to simpler form on TypeError
        status = -999
        try:
            status = lora.begin(
                freq=settings.FREQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
                syncWord=settings.SYNC_WORD, power=settings.POWER,
                currentLimit=settings.CURRENT_LIMIT, preambleLength=settings.PREAMBLE_LEN,
                implicit=False, implicitLen=0xFF, crcOn=settings.CRC_ON,
                txIq=False, rxIq=False,
                tcxoVoltage=settings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO
            )
        except TypeError as te:
            await debug_print('init_lora: begin() TypeError %s, retrying minimal args' % te, 'WARN')
            try:
                status = lora.begin(freq=settings.FREQ, power=settings.POWER)
            except Exception as e2:
                await debug_print('init_lora: begin(minimal) failed %s' % e2, 'ERROR')
                status = -999
        except Exception as e:
            await debug_print('init_lora: begin() exception %s' % e, 'ERROR')
            status = -999

        print('[DEBUG] init_lora: lora.begin() returned', status)

        if status != 0:
            # Map error code if driver exposes error table
            try:
                from _sx126x import ERROR as SXERR
                err_name = SXERR.get(status, 'UNKNOWN')
            except Exception:
                err_name = 'UNKNOWN'
            msg = 'LoRa initialization failed with status: %s (%s)' % (status, err_name)
            await debug_print(msg, 'ERROR')
            await log_error(msg)
            try:
                from oled import display_message
                await display_message('LoRa Error', 2)
            except Exception:
                pass
            # Put pins into safe input state
            try:
                _safe_pin_input(settings.CS_PIN)
                _safe_pin_input(settings.RST_PIN)
                _safe_pin_input(settings.IRQ_PIN)
                _safe_pin_input(settings.BUSY_PIN)
            except Exception:
                pass
            lora = None
            return False

        # Non-blocking mode (ignore if driver does not support it)
        try:
            rc = lora.setBlockingCallback(False)
        except Exception:
            rc = 0
        if rc != 0:
            try:
                from _sx126x import ERROR as SXERR
                err_name = SXERR.get(rc, 'UNKNOWN')
            except Exception:
                err_name = 'UNKNOWN'
            await debug_print('lora: setBlockingCallback fail %s (%s)' % (rc, err_name), 'ERROR')
            await log_error('LoRa setBlockingCallback failed: %s (%s)' % (rc, err_name))
            await free_pins()
            lora = None
            return False

        # Optional: verify packet type is LoRa
        try:
            from _sx126x import SX126X_PACKET_TYPE_LORA
            try:
                pkt_type = lora.getPacketType()
            except Exception:
                pkt_type = SX126X_PACKET_TYPE_LORA
            if pkt_type != SX126X_PACKET_TYPE_LORA:
                await debug_print('lora: packet type mismatch %s' % pkt_type, 'ERROR')
                await log_error('LoRa init verify failed: packet type=%s' % pkt_type)
                await free_pins()
                lora = None
                return False
        except Exception:
            pass

        # Enable IQ inversion for RX when supported (applies to base and remotes)
        try:
            if hasattr(lora, 'setRxIq'):
                lora.setRxIq(True)
                await debug_print('lora: setRxIq(True) applied', 'LORA')
            elif hasattr(lora, 'setIqInvert'):
                lora.setIqInvert(True)
                await debug_print('lora: setIqInvert(True) applied', 'LORA')
        except Exception:
            pass

        # Print RF parameters once when DEBUG_PRINT_PARAMS is enabled
        try:
            if getattr(settings, 'DEBUG_PRINT_PARAMS', False):
                try:
                    freq = lora.getFrequency() if hasattr(lora, 'getFrequency') else None
                    sf = lora.getSpreadingFactor() if hasattr(lora, 'getSpreadingFactor') else None
                    bw = lora.getBandwidth() if hasattr(lora, 'getBandwidth') else None
                    cr = lora.getCodingRate() if hasattr(lora, 'getCodingRate') else None
                    sw = lora.getSyncWord() if hasattr(lora, 'getSyncWord') else None
                    pre = lora.getPreambleLength() if hasattr(lora, 'getPreambleLength') else None
                    crc_on = lora.getCRC() if hasattr(lora, 'getCRC') else None
                except Exception:
                    freq = sf = bw = cr = sw = pre = crc_on = None
                try:
                    print(
                        '[DEBUG] LoRa params: FREQ=%s BW=%s SF=%s CR=%s SYNC=0x%X PREAMBLE=%s CRC_ON=%s'
                        % (freq, bw, sf, cr, (sw or 0), pre, crc_on)
                    )
                except Exception:
                    pass
        except Exception:
            pass

        await debug_print('lora: initialized', 'LORA')
        try:
            from oled import display_message
            await display_message('LoRa Ready', 2)
        except Exception:
            pass
        print_remote_nodes()

        # Put radio into initial mode based on role
        try:
            role = getattr(settings, 'NODE_TYPE', 'base')
            if role == 'base':
                lora.setOperatingMode(lora.MODE_RX)
            else:
                lora.setOperatingMode(lora.MODE_STDBY)
        except Exception:
            pass

        print('[DEBUG] init_lora: completed successfully')
        return True
    except Exception as e:
        msg = 'Exception in init_lora: %s' % e
        try:
            print(msg)
        except Exception:
            pass
        await debug_print(msg, 'ERROR')
        try:
            from oled import display_message
            await display_message('LoRa Error', 2)
        except Exception:
            pass
        await log_error(msg)
        try:
            _deinit_spi_if_any(lora)
        except Exception:
            pass
        await free_pins()
        lora = None
        return False

# --- All globals at the very top ---
_last_send_ms = 0
_last_activity_ms = 0
_init_failures = 0
_MAX_INIT_FAILS = 3

# Periodic task to manage LoRa connection and data flow
async def connectLora():
    """Non-blocking LoRa routine called frequently from lora_comm_task.
    - Initializes radio once (with retry cap)
    - Remote: sends payload at interval, waits for TX_DONE briefly, then returns
    - Base: polls for RX_DONE and processes any message
    - Idle timeout: deinit after prolonged inactivity to save power
    Returns True if LoRa is initialized and usable, else False.
    """
    global lora, _last_send_ms, _last_activity_ms, _init_failures, _last_tx_exception_ms, _last_rssi_log_ms

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
        await debug_print('lora: initializing...', 'LORA')
        async with pin_lock:
            ok = await init_lora()
        if not ok:
            _init_failures += 1
            return False
        _init_failures = 0
        _last_activity_ms = now
        return True

    # Choose behavior by role
    role = getattr(settings, 'NODE_TYPE', 'base')
    # --- Base: listen for remote messages and persist them ---
    if role == 'base':
        try:
            # Poll events briefly for incoming RX frames
            RX_DONE_FLAG = getattr(SX1262, 'RX_DONE', None)
            try:
                ev = lora._events()
            except Exception:
                ev = 0
            if RX_DONE_FLAG is not None and (ev & RX_DONE_FLAG):
                try:
                    msg_bytes, err = lora._readData(0)
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
                                        # cleanup: remove entry if successfully assembled
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
                        # Persist to field data log so base later uploads remote telemetry via WPREST
                        try:
                            checkLogDirectory()
                            fd_path = getattr(settings, 'FIELD_DATA_LOG', settings.LOG_DIR + '/field_data.log')
                            with open(fd_path, 'a') as f:
                                f.write(ujson.dumps(record) + '\n')
                        except Exception as e:
                            await debug_print(f"lora: failed to persist remote line: {e}", "ERROR")
                        # update in-memory remote info and write file
                        try:
                            uid = record.get('unit_id') or record.get('unit') or record.get('name')
                            if uid:
                                settings.REMOTE_NODE_INFO = getattr(settings, 'REMOTE_NODE_INFO', {})
                                settings.REMOTE_NODE_INFO[str(uid)] = {'last_seen': int(time.time()), 'last_payload': record}
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
                                # Best-effort: ACK back to remote with next sync and optional GPS
                                try:
                                    ack = {'ack': 'ok'}
                                    # schedule next_in seconds (base chooses cadence)
                                    next_in = getattr(settings, 'LORA_CHECK_IN_MINUTES', 5) * 60
                                    ack['next_in'] = next_in
                                    if getattr(settings, 'GPS_BROADCAST_TO_REMOTES', False):
                                        try:
                                            ack['gps_lat'] = getattr(settings, 'GPS_LAT', None)
                                            ack['gps_lng'] = getattr(settings, 'GPS_LNG', None)
                                            ack['gps_alt_m'] = getattr(settings, 'GPS_ALT_M', None)
                                            ack['gps_accuracy_m'] = getattr(settings, 'GPS_ACCURACY_M', None)
                                        except Exception:
                                            pass
                                    try:
                                        # send ack (best-effort). Radio may need reconfig, so guard heavily.
                                        try:
                                            # Wait for not busy before mode change
                                            busy_start = time.ticks_ms()
                                            while lora.gpio.value() and time.ticks_diff(time.ticks_ms(), busy_start) < 2000:
                                                await asyncio.sleep(0.01)
                                            lora.setOperatingMode(lora.MODE_TX)
                                            lora.send(ujson.dumps(ack).encode('utf-8'))
                                            # Wait briefly for TX_DONE then restore RX mode
                                            ack_start = time.ticks_ms()
                                            while time.ticks_diff(time.ticks_ms(), ack_start) < 2000:
                                                ev = lora._events()
                                                if getattr(lora, 'TX_DONE', 0) and (ev & lora.TX_DONE):
                                                    break
                                                await asyncio.sleep(0.01)
                                            # Wait for not busy after TX_DONE
                                            busy_start = time.ticks_ms()
                                            while lora.gpio.value() and time.ticks_diff(time.ticks_ms(), busy_start) < 2000:
                                                await asyncio.sleep(0.01)
                                            lora.setOperatingMode(lora.MODE_RX)
                                        except Exception:
                                            # try a more direct sequence if the driver has explicit tx API
                                            try:
                                                lora.setOperatingMode(lora.MODE_TX)
                                                lora.send(ujson.dumps(ack).encode('utf-8'))
                                                lora.setOperatingMode(lora.MODE_RX)
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    except Exception as e:
                        await debug_print(f"lora: processing RX failed: {e}", "ERROR")
        except Exception as e:
            await debug_print(f"lora: base RX loop exception: {e}", "ERROR")
            _init_failures += 1
            lora = None
            return False
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
        except Exception:
            due = (_last_send_ms == 0) or (time.ticks_diff(now, _last_send_ms) >= probe_interval_ms)

        if due:
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
                try:
                 