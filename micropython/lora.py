# Utility to print remote node info
def print_remote_nodes():
    import sdata
    remote_info = getattr(sdata, 'REMOTE_NODE_INFO', {})
    for node_id, node_data in remote_info.items():
        print(f"[REMOTE NODE] {node_id}: {node_data}")

# --- All imports at the top ---
import gc
import ujson
import os
import uasyncio as asyncio
import select
import random
import ubinascii as _ub
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
from utils import free_pins, checkLogDirectory, debug_print, TMON_AI, safe_run, led_status_flash, write_lora_log
from relay import toggle_relay
try:
    from encryption import chacha20_encrypt, derive_nonce
except Exception:
    chacha20_encrypt = None
    derive_nonce = None

def chacha20_decrypt(key, nonce, aad, ciphertext):
    return chacha20_encrypt(key, nonce, aad, ciphertext)

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

# File to persist remote node info
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

    try:
        with open(REMOTE_SYNC_SCHEDULE_FILE, 'r') as f:
            settings.REMOTE_SYNC_SCHEDULE = ujson.load(f)
    except Exception:
        settings.REMOTE_SYNC_SCHEDULE = {}

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
    gc.collect()

# Ensure remote node info is loaded at startup (after settings import)
load_remote_node_info()

# Save REMOTE_NODE_INFO to file
def save_remote_node_info():
    try:
        with open(REMOTE_NODE_INFO_FILE, 'w') as f:
            ujson.dump(settings.REMOTE_NODE_INFO, f)
    except Exception:
        pass
    gc.collect()

def save_remote_sync_schedule():
    try:
        with open(REMOTE_SYNC_SCHEDULE_FILE, 'w') as f:
            ujson.dump(settings.REMOTE_SYNC_SCHEDULE, f)
    except Exception:
        pass
    gc.collect()

def save_gps_state(lat=None, lng=None, alt=None, acc=None, ts=None):
    try:
        import sdata as _s
        _s.gps_lat = lat
        _s.gps_lng = lng
        _s.gps_alt_m = alt
        _s.gps_accuracy_m = acc
        _s.gps_last_fix_ts = ts
    except Exception:
        pass
    try:
        if getattr(settings, 'GPS_OVERRIDE_ALLOWED', True):
            if lat is not None: settings.GPS_LAT = lat
            if lng is not None: settings.GPS_LNG = lng
            if alt is not None: settings.GPS_ALT_M = alt
            if acc is not None: settings.GPS_ACCURACY_M = acc
            if ts is not None: settings.GPS_LAST_FIX_TS = ts
    except Exception:
        pass
    try:
        with open(GPS_STATE_FILE, 'w') as f:
            ujson.dump({'gps_lat': lat, 'gps_lng': lng, 'gps_alt_m': alt, 'gps_accuracy_m': acc, 'gps_last_fix_ts': ts}, f)
    except Exception:
        pass
    gc.collect()

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
        gc.collect()

# Heartbeat loop
async def heartbeat_ping_loop():
    if settings.NODE_TYPE != 'base':
        return  # Only base station sends heartbeats to WordPress
    while True:
        await heartbeat_ping()
        await asyncio.sleep(60)
        gc.collect()

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
    gc.collect()

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

WORDPRESS_API_URL = getattr(settings, 'WORDPRESS_API_URL', None)
WORDPRESS_API_KEY = getattr(settings, 'WORDPRESS_API_KEY', None)

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
    gc.collect()

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
    gc.collect()

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
    gc.collect()

async def send_file_to_wp(filepath):
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    try:
        with open(filepath, 'rb') as f:
            file_content = f.read()
            files = {'file': (os.path.basename(filepath), file_content)}
            hdrs = {}
            try:
                hdrs = _auth_headers()
            except Exception:
                hdrs = {}
            resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/file', headers=hdrs, files=files)
            await debug_print(f'Sent file to WP: {resp.status_code}', 'HTTP')
        del file_content
    except Exception as e:
        await debug_print(f'Failed to send file to WP: {e}', 'ERROR')
    gc.collect()

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
    gc.collect()

file_lock = asyncio.Lock()
pin_lock = asyncio.Lock()
lora = None

_lora_incoming_chunks = {}

async def cleanup_incoming_chunks():
    while True:
        current_time = time.time()
        to_delete = []
        for uid, entry in _lora_incoming_chunks.items():
            if current_time - entry['ts'] > 3600:
                to_delete.append(uid)
        for uid in to_delete:
            del _lora_incoming_chunks[uid]
        gc.collect()
        await asyncio.sleep(600)

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
    gc.collect()

command_handlers = {
    "toggle_relay": toggle_relay,
    # Add more handlers as needed, e.g., "other_func": other_func,
}

pending_commands = {}  # {uid: "func(arg1,arg2,arg3)"}

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
        time.sleep_ms(low_ms)
        p.value(1)
        time.sleep_ms(post_high_ms)
    except Exception:
        try:
            time.sleep_ms(post_high_ms)
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

def _attach_spi_shim():
    try:
        if not (machine and hasattr(machine, 'SPI') and getattr(settings, 'CLK_PIN', None) is not None):
            return None
        spi = None
        # Try hardware SPI first
        try:
            spi = machine.SPI(
                settings.SPI_BUS,
                baudrate=getattr(settings, 'LORA_SPI_BAUD', 1000000),
                polarity=0,
                phase=0,
                sck=machine.Pin(settings.CLK_PIN),
                mosi=machine.Pin(settings.MOSI_PIN),
                miso=machine.Pin(settings.MISO_PIN)
            )
            print('[DEBUG] Hardware SPI initialized successfully')
        except ValueError as ve:
            print(f'[DEBUG] Hardware SPI failed: {ve}, attempting SoftSPI')
        except Exception as e:
            print(f'[DEBUG] Hardware SPI unexpected error: {e}')

        # Fall back to SoftSPI if hardware SPI fails
        if not spi:
            try:
                spi = machine.SoftSPI(
                    baudrate=getattr(settings, 'LORA_SPI_BAUD', 1000000),
                    polarity=0,
                    phase=0,
                    sck=machine.Pin(settings.CLK_PIN),
                    mosi=machine.Pin(settings.MOSI_PIN),
                    miso=machine.Pin(settings.MISO_PIN)
                )
                print('[DEBUG] SoftSPI initialized successfully')
            except Exception as e:
                print(f'[DEBUG] SoftSPI failed: {e}')
                return None

        if not spi:
            return None

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
                        return None
                    except Exception:
                        pass
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
    gc.collect()

async def init_lora():
    global lora
    print('[DEBUG] init_lora: starting SX1262 init')
    try:
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

        print('[DEBUG] init_lora: BEFORE SX1262 instantiation (pins prepped)')
        spi = _attach_spi_shim()
        if not spi:
            print('[ERROR] Failed to attach SPI shim')
            return False

        try:
            lora = SX1262(spi, settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN)
        except Exception:
            lora = SX1262(spi=spi, cs=settings.CS_PIN, irq=settings.IRQ_PIN, rst=settings.RST_PIN, busy=settings.BUSY_PIN)
        print('[DEBUG] init_lora: SX1262 object created')
        _deinit_spi_if_any(lora)

        async def _attempt_begin(lo, attempts=3):
            try:
                if not getattr(lo, 'spi', None):
                    lo.spi = spi
                    await debug_print("lora: attached SPI shim before begin attempts", "LORA")
            except Exception:
                pass
            for i in range(attempts):
                try:
                    status = lo.begin(
                        freq=settings.FREQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
                        syncWord=settings.SYNC_WORD, power=settings.POWER,
                        currentLimit=settings.CURRENT_LIMIT, preambleLength=settings.PREAMBLE_LEN,
                        implicit=False, implicitLen=0xFF, crcOn=settings.CRC_ON, txIq=False, rxIq=False,
                        tcxoVoltage=settings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO
                    )
                    return status
                except AttributeError as ae:
                    await debug_print(f"lora.begin AttributeError: {ae}", "ERROR")
                    try:
                        if spi:
                            lo.spi = spi
                            await debug_print("lora: attached SPI shim and retrying begin", "LORA")
                    except Exception:
                        pass
                    time.sleep_ms(120)
                    continue
                except TypeError as te:
                    await debug_print(f"lora.begin TypeError: {te} (attempt {i+1})", "WARN")
                    try:
                        status = lo.begin(freq=settings.FREQ, power=settings.POWER)
                        return status
                    except Exception:
                        pass
                    try:
                        status = lo.begin(settings.FREQ, settings.BW, settings.SF)
                        return status
                    except Exception:
                        pass
                    try:
                        if spi:
                            try:
                                lo2 = SX1262(spi, settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN)
                            except Exception:
                                lo2 = SX1262(spi=spi, cs=settings.CS_PIN, irq=settings.IRQ_PIN, rst=settings.RST_PIN, busy=settings.BUSY_PIN)
                            lo = lo2
                            status = lo.begin(freq=settings.FREQ)
                            return status
                    except Exception:
                        pass
                    time.sleep_ms(120)
                    continue
                except Exception as e:
                    await debug_print(f"lora.begin exception: {e}", "ERROR")
                    return -999
            return -999

        status = await _attempt_begin(lora, attempts=2)
        print(f'[DEBUG] init_lora: lora.begin() returned {status}')

        if status == -2:
            await debug_print('lora: chip not found, performing diagnostics & retry', 'LORA')
            try:
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
                    await debug_print(f"lora: spi present? {bool(spi_obj)}", "LORA")
                except Exception:
                    pass
                try:
                    spi = _attach_spi_shim()
                    if spi:
                        newlo = SX1262(spi, settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN)
                        lora = newlo
                        await debug_print("lora: re-instantiated with shim, retrying begin", "LORA")
                except Exception:
                    pass
                try:
                    _pulse_reset(settings.RST_PIN, low_ms=80, post_high_ms=200)
                    time.sleep_ms(140)
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
                await debug_print(f'LoRa diagnostics failed: {exc}', 'ERROR')
                await log_error(f'LoRa diagnostics failed: {exc}')
                lora = None
                return False

        if status != 0:
            error_msg = f"LoRa initialization failed with status: {status}"
            await debug_print(error_msg, "ERROR")
            await log_error(error_msg)
            await free_pins()
            lora = None
            return False

        rc = lora.setBlockingCallback(False)
        if rc != 0:
            await debug_print(f"lora: setBlockingCallback fail {rc}", "ERROR")
            await free_pins()
            lora = None
            return False

        try:
            pkt_type = lora.getPacketType()
            if pkt_type != 1:
                await debug_print("lora: init verify pkt_type mismatch", "ERROR")
                await free_pins()
                lora = None
                return False
        except Exception as ve:
            await debug_print(f"LoRa init verify exception: {ve}", "ERROR")
            await free_pins()
            lora = None
            return False

        await debug_print("LoRa initialized successfully", "LORA")
        try:
            from oled import display_message
            await display_message("LoRa Ready", 2)
        except Exception:
            pass
        print_remote_nodes()
        try:
            if settings.NODE_TYPE == 'base' and lora is not None:
                lora.setOperatingMode(lora.MODE_RX)
                led_status_flash('LORA_RX')
            elif settings.NODE_TYPE == 'remote' and lora is not None:
                lora.setOperatingMode(lora.MODE_STDBY)
                led_status_flash('LORA_TX')
        except Exception:
            pass
        print('[DEBUG] init_lora: completed successfully')
        gc.collect()
        return True
    except Exception as e:
        error_msg = f"Exception in init_lora: {e}"
        print(error_msg)
        await debug_print(error_msg, "ERROR")
        await log_error(error_msg)
        _deinit_spi_if_any(lora)
        await free_pins()
        lora = None
        gc.collect()
        return False

_last_send_ms = 0
_last_activity_ms = 0
_init_failures = 0
_MAX_INIT_FAILS = 3
_last_tx_exception_ms = 0
_TX_EXCEPTION_COOLDOWN_MS = 2500

def _load_remote_counters():
    path = getattr(settings, 'LORA_REMOTE_COUNTERS_FILE', settings.LOG_DIR + '/remote_ctr.json')
    try:
        with open(path, 'r') as f:
            return ujson.load(f)
    except Exception:
        return {}

def _save_remote_counters(ctrs):
    path = getattr(settings, 'LORA_REMOTE_COUNTERS_FILE', settings.LOG_DIR + '/remote_ctr.json')
    try:
        with open(path, 'w') as f:
            ujson.dump(ctrs, f)
    except Exception:
        pass
    gc.collect()

def _get_hashlib():
    try:
        import uhashlib as _uh
        import ubinascii as _ub
        return _uh, _ub
    except Exception:
        import hashlib as _uh
        import binascii as _ub
        return _uh, _ub

def compute_sha256_from_bytes(data):
    _uh, _ub = _get_hashlib()
    h = _uh.sha256()
    try:
        h.update(data)
    except Exception:
        pass
    try:
        digest = h.digest()
        hexsum = _ub.hexlify(digest).decode().lower()
    except Exception:
        try:
            hexsum = h.hexdigest().lower()
        except Exception:
            hexsum = ''
    return hexsum
    gc.collect()

async def connectLora():
    global lora, _last_send_ms, _last_activity_ms, _init_failures, _last_tx_exception_ms

    lora_init_failures = _init_failures
    MAX_LORA_INIT_FAILS = _MAX_INIT_FAILS
    if settings.ENABLE_LORA:
        await debug_print("Attempting LoRa initialization...", "LORA")
        async with pin_lock:
            print('[DEBUG] connectLora: calling init_lora')
            while lora_init_failures < MAX_LORA_INIT_FAILS:
                if await init_lora():
                    print('[DEBUG] connectLora: init_lora succeeded')
                    break
                else:
                    lora_init_failures += 1
                    print(f'[DEBUG] connectLora: init_lora failed ({lora_init_failures}/{MAX_LORA_INIT_FAILS})')
                    await asyncio.sleep(10)
            if lora_init_failures >= MAX_LORA_INIT_FAILS:
                print('[FATAL] LoRa initialization failed too many times. Halting further attempts.')
                await debug_print('LoRa initialization failed too many times. Halting.', 'FATAL')
                return False

        STATE_IDLE = 0
        STATE_SENDING = 1
        STATE_WAIT_RESPONSE = 2
        STATE_RECEIVING = 3

        state = STATE_IDLE
        send_interval = 10
        timeout_ms = 15000
        last_activity = time.ticks_ms()
        idle_timeout = 60000
        connected = False

        # For base: Track connected remote nodes {uid: last_ts}
        connected_remotes = {}

        # For base: Pending commands {uid: "func(arg1,arg2,arg3)"}
        # Populate this dict externally or based on criteria
        pending_commands = {}

        while True:
            current_time = time.ticks_ms()
            if state == STATE_IDLE and time.ticks_diff(current_time, last_activity) > idle_timeout:
                await debug_print("Idle timeout reached, freeing pins", "LORA")
                async with pin_lock:
                    global lora
                    if lora is not None:
                        _deinit_spi_if_any(lora)
                        lora = None
                await free_pins()
                await asyncio.sleep(60)
                last_activity = time.ticks_ms()

            if settings.NODE_TYPE == 'remote':
                if state == STATE_IDLE:
                    await debug_print("Remote: Idle state - attempting to send/connect", "LORA")
                    ts = time.time()
                    payload = {
                        "TS": ts,
                        "UID": settings.UNIT_ID,
                        "COMPANY": getattr(settings, 'COMPANY', ''),
                        "SITE": getattr(settings, 'SITE', ''),
                        "ZONE": getattr(settings, 'ZONE', ''),
                        "CLUSTER": getattr(settings, 'CLUSTER', ''),
                        "RUNTIME": sdata.loop_runtime,
                        "SCRIPT_RUNTIME": sdata.script_runtime,
                        "TEMP_C": sdata.cur_temp_c,
                        "TEMP_F": sdata.cur_temp_f,
                        "BAR": sdata.cur_bar_pres,
                        "HUMID": sdata.cur_humid
                    }
                    data_str = ujson.dumps(payload)
                    data = data_str.encode()
                    await debug_print(f"Sending data: {data_str}", "LORA")

                    # Integrate chunking from second script
                    max_payload = int(getattr(settings, 'LORA_MAX_PAYLOAD', 220) or 220)
                    raw_chunk_size = 80
                    if len(data) <= max_payload:
                        async with pin_lock:
                            global lora
                            if lora is None:
                                if not await init_lora():
                                    continue
                            lora.send(data)
                    else:
                        parts = [data[i:i+raw_chunk_size] for i in range(0, len(data), raw_chunk_size)]
                        total = len(parts)
                        for idx, chunk in enumerate(parts, start=1):
                            b64 = _ub.b2a_base64(chunk).decode().strip()
                            chunk_msg = {'chunked': 1, 'seq': idx, 'total': total, 'b64': b64}
                            chunk_data = ujson.dumps(chunk_msg).encode('utf-8')
                            async with pin_lock:
                                global lora
                                if lora is None:
                                    if not await init_lora():
                                        continue
                                lora.send(chunk_data)
                            await asyncio.sleep(0.1)

                    state = STATE_WAIT_RESPONSE
                    start_wait = time.ticks_ms()
                    last_activity = time.ticks_ms()

                elif state == STATE_WAIT_RESPONSE:
                    await debug_print("Remote: Waiting for response...", "LORA")
                    async with pin_lock:
                        global lora
                        if lora is None:
                            if not await init_lora():
                                continue
                        msg, err = lora.recv(len=0, timeout_en=True, timeout_ms=timeout_ms)
                        try:
                            rssi = lora.getRSSI()
                            sdata.lora_SigStr = rssi
                            await debug_print(f"LoRa Signal Strength (RSSI): {rssi}", "LORA")
                        except Exception as e:
                            await debug_print(f"Failed to get RSSI: {e}", "ERROR")
                    if err == 0 and msg:
                        msg = msg.rstrip(b'\x00')
                        try:
                            msg_str = msg.decode()
                            await debug_print(f"Raw response: {msg_str}", "DEBUG")
                            try:
                                obj = ujson.loads(msg_str)
                            except Exception:
                                obj = {}
                            if obj.get('ACK'):
                                ack_ts = obj.get('ACK')
                                await debug_print(f"Received ACK with base TS: {ack_ts}", "LORA")
                                if not connected:
                                    await debug_print("Connected to base station", "LORA")
                                    connected = True
                            cmd = obj.get('CMD')
                            if cmd:
                                if '(' in cmd and cmd.endswith(')'):
                                    func_name, args_str = cmd.split('(', 1)
                                    args_str = args_str.rstrip(')')
                                    args = [arg.strip() for arg in args_str.split(',')] if args_str else []
                                    if func_name in command_handlers:
                                        await command_handlers[func_name](*args)
                                        await debug_print(f"Executed command: {cmd}", "COMMAND")
                                    else:
                                        await debug_print(f"Unknown command: {func_name}", "ERROR")
                                else:
                                    await debug_print(f"Invalid command format: {cmd}", "ERROR")
                            # Add GPS from second
                            if getattr(settings, 'GPS_ACCEPT_FROM_BASE', True):
                                blat = obj.get('gps_lat')
                                blng = obj.get('gps_lng')
                                if blat is not None and blng is not None:
                                    balt = obj.get('gps_alt_m')
                                    bacc = obj.get('gps_accuracy_m')
                                    bts = obj.get('gps_last_fix_ts')
                                    save_gps_state(blat, blng, balt, bacc, bts)
                                    await debug_print('lora: GPS adopted', 'LORA')
                            state = STATE_IDLE
                            last_activity = time.ticks_ms()
                            await debug_print("Remote: Connection active - sleeping for interval", "LORA")
                            await asyncio.sleep(send_interval)
                        except Exception as e:
                            error_msg = f"Invalid response: {str(e)}"
                            await debug_print(error_msg, "ERROR")
                            await log_error(error_msg)
                            if connected:
                                await debug_print("Disconnected from base station", "WARN")
                                connected = False
                            state = STATE_IDLE
                            await asyncio.sleep(send_interval)
                    else:
                        await debug_print(f"Timeout or error: {err}", "WARN")
                        if connected:
                            await debug_print("Disconnected from base station", "WARN")
                            connected = False
                        state = STATE_IDLE
                        await debug_print("Remote: No connection - retrying in interval", "LORA")
                        await asyncio.sleep(send_interval)

                else:
                    await asyncio.sleep(1)

            elif settings.NODE_TYPE == 'base':
                if state == STATE_IDLE:
                    if connected:
                        await debug_print("Base: Already connected - continuing to listen", "LORA")
                    else:
                        await debug_print("Base: Idle state - starting receive for connections", "LORA")
                    state = STATE_RECEIVING

                elif state == STATE_RECEIVING:
                    await debug_print("Base: Listening for remote nodes...", "LORA")
                    global lora
                    if lora is None:
                        if not await init_lora():
                            await asyncio.sleep(1)
                            continue
                    msg, err = lora.recv(len=0, timeout_en=False)
                    try:
                        rssi = lora.getRSSI()
                        sdata.lora_SigStr = rssi
                        await debug_print(f"LoRa Signal Strength (RSSI): {rssi}", "LORA")
                    except Exception as e:
                        await debug_print(f"Failed to get RSSI: {e}", "ERROR")
                    last_activity = time.ticks_ms()
                    if err == 0 and msg:
                        msg = msg.rstrip(b'\x00')
                        try:
                            msg_str = msg.decode()
                            try:
                                payload = ujson.loads(msg_str)
                            except Exception:
                                payload = {}
                            if payload.get('chunked'):
                                # Handle chunked from second
                                uid = str(payload.get('UID') or 'unknown')
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
                                await debug_print(f"lora: chunk {seq}/{total} for {uid}, parts: {len(entry['parts'])}", 'LORA')
                                if len(entry['parts']) == entry['total']:
                                    assembled = b''.join(entry['parts'][i] for i in range(1, entry['total'] + 1))
                                    try:
                                        payload = ujson.loads(assembled.decode('utf-8', 'ignore'))
                                    except Exception:
                                        payload = {}
                                    await debug_print(f"lora: assembled for {uid}", 'LORA')
                                    del _lora_incoming_chunks[uid]
                                else:
                                    continue

                            remote_ts = payload.get('TS')
                            remote_uid = payload.get('UID')
                            remote_company = payload.get('COMPANY')
                            remote_site = payload.get('SITE')
                            remote_zone = payload.get('ZONE')
                            remote_cluster = payload.get('CLUSTER')
                            remote_runtime = payload.get('RUNTIME')
                            remote_script_runtime = payload.get('SCRIPT_RUNTIME')
                            temp_c = payload.get('TEMP_C')
                            temp_f = payload.get('TEMP_F')
                            bar = payload.get('BAR')
                            humid = payload.get('HUMID')

                            if remote_uid and remote_company is not None:
                                if not hasattr(settings, 'REMOTE_NODE_INFO'):
                                    settings.REMOTE_NODE_INFO = {}
                                settings.REMOTE_NODE_INFO[remote_uid] = {
                                    'COMPANY': remote_company,
                                    'SITE': remote_site,
                                    'ZONE': remote_zone,
                                    'CLUSTER': remote_cluster
                                }
                                save_remote_node_info()
                            if any(v is None for v in [remote_uid, remote_runtime, remote_script_runtime, temp_c, temp_f, bar, humid]):
                                error_msg = f"Missing fields in message: UID={remote_uid}, RUNTIME={remote_runtime}, SCRIPT_RUNTIME={remote_script_runtime}, TEMP_C={temp_c}, TEMP_F={temp_f}, BAR={bar}, HUMID={humid}"
                                await debug_print(error_msg, "ERROR")
                                await log_error(error_msg)
                            else:
                                base_ts = time.time()
                                log_line = f"{base_ts},{remote_uid},{remote_ts},{remote_runtime},{remote_script_runtime},{temp_c},{temp_f},{bar},{humid}\n"
                                try:
                                    temp_f_val = float(temp_f)
                                except ValueError as ve:
                                    error_msg = f"Invalid number syntax for TEMP_F: {repr(temp_f)} | {ve}"
                                    await debug_print(error_msg, "ERROR")
                                    await log_error(error_msg)
                                    temp_f_val = 0.0
                                try:
                                    bar_val = float(bar)
                                except ValueError as ve:
                                    error_msg = f"Invalid number syntax for BAR: {repr(bar)} | {ve}"
                                    await debug_print(error_msg, "ERROR")
                                    await log_error(error_msg)
                                    bar_val = 0.0
                                try:
                                    humid_val = float(humid)
                                except ValueError as ve:
                                    error_msg = f"Invalid number syntax for HUMID: {repr(humid)} | {ve}"
                                    await debug_print(error_msg, "ERROR")
                                    await log_error(error_msg)
                                    humid_val = 0.0
                                await findLowestTemp(temp_f_val)
                                await findLowestBar(bar_val)
                                await findLowestHumid(humid_val)
                                await findHighestTemp(temp_f_val)
                                await findHighestBar(bar_val)
                                await findHighestHumid(humid_val)
                                await debug_print(f"Received: {log_line.strip()}", "LORA")
                                async with file_lock:
                                    with open(settings.LOG_FILE, 'a') as f:
                                        f.write(log_line)
                                # Record all sdata/settings to field_data.log
                                from utils import record_field_data
                                record_field_data()
                                # Update connected remotes
                                connected_remotes[remote_uid] = base_ts
                                # Check criteria and queue command (example from second)
                                if temp_f_val < 80:  # Replace with actual criteria
                                    pending_commands[remote_uid] = "toggle_relay(1,on,5)"
                                # Send ACK or CMD
                                ack_data = f"ACK:{base_ts}"
                                if remote_uid in pending_commands:
                                    command = pending_commands.pop(remote_uid)
                                    ack_data = f"CMD:{remote_uid}:{command}"
                                    await debug_print(f"Sending command to {remote_uid}: {command}", "COMMAND")
                                async with pin_lock:
                                    global lora
                                    if lora is None:
                                        if not await init_lora():
                                            continue
                                    lora.send(ack_data.encode())
                                    await debug_print(f"Sent ACK/CMD to {remote_uid}", "LORA")
                                if not connected:
                                    await debug_print("Base: New connection established", "LORA")
                                    connected = True
                                state = STATE_IDLE
                        except Exception as e:
                            error_msg = f"Invalid message: {str(e)}"
                            await debug_print(error_msg, "ERROR")
                            await log_error(error_msg)
                    elif err == -81:  # Replace with actual timeout err code from library
                        await debug_print("Receive timeout - retrying...", "LORA")
                        state = STATE_IDLE
                        await asyncio.sleep(0)  # Yield to event loop
                    else:
                        error_msg = f"Receive error: {err}"
                        await debug_print(error_msg, "ERROR")
                        await log_error(error_msg)
                        state = STATE_IDLE
                else:
                    state = STATE_IDLE
                    await asyncio.sleep(1)
            gc.collect()

# --- AI and main loop integration ---
async def safe_loop(coro, context):
    while True:
        try:
            await coro()
        except Exception as e:
            await log_error(f"{context} crashed: {str(e)}")
            await asyncio.sleep(10)  # Retry after delay

async def main_loop():
    asyncio.create_task(safe_loop(periodic_wp_sync, 'periodic_wp_sync'))
    asyncio.create_task(safe_loop(heartbeat_ping_loop, 'heartbeat_ping_loop'))
    asyncio.create_task(safe_loop(cleanup_incoming_chunks, 'cleanup_incoming_chunks'))
    # Add similar for any other infinite coros, e.g., ai_health_monitor()
    while True:
        await asyncio.sleep(60)  # Keep main_loop alive; adjust as needed

# Example: AI-driven system health check
async def ai_health_monitor():
    while True:
        # Check error count and escalate if needed
        if TMON_AI.error_count > 3:
            await TMON_AI.recover_system()
        # Example: check for specific error patterns
        if TMON_AI.last_error:
            suggestion = await TMON_AI.suggest_action(TMON_AI.last_error[1])
            await log_error(f'AI suggestion: {suggestion}', 'ai_health_monitor')
        await asyncio.sleep(60)

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