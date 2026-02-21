# Firmware Version: v2.06.0 + integrated command logic from previous version
# Utility to print remote node info
def print_remote_nodes():
    import settings
    remote_info = getattr(settings, 'REMOTE_NODE_INFO', {})
    for node_id, node_data in remote_info.items():
        print(f"[REMOTE NODE] {node_id}: {node_data}")

# Async helper to log remote nodes without blocking LoRa init
async def print_remote_nodes_async():
    try:
        print_remote_nodes()
    except Exception:
        pass

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
    try:
        from lib.sx1262 import SX1262
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
    time = None
try:
    import urequests as requests
except ImportError:
    try:
        import requests
    except ImportError:
        requests = None
from utils import free_pins, checkLogDirectory, debug_print, TMON_AI, safe_run, led_status_flash, write_lora_log, persist_unit_id, append_field_data_entry
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
    if not sys or not hasattr(sys, 'stdin'):
        return
    while True:
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            cmd = sys.stdin.readline().strip()
            if cmd:
                await handle_user_command(cmd)
        await asyncio.sleep(0.1)

async def handle_user_command(cmd):
    from utils import debug_print
    if cmd.lower() == 'reset_ai':
        TMON_AI.error_count = 0
        await debug_print('AI error count reset by user', 'user_input')
    elif cmd.lower().startswith('call '):
        fn = cmd[5:].strip()
        if hasattr(TMON_AI, fn):
            await debug_print(f'Calling AI function: {fn}', 'user_input')
            getattr(TMON_AI, fn)()
        else:
            await debug_print(f'No such AI function: {fn}', 'user_input')
    else:
        await debug_print(f'Unknown command: {cmd}', 'user_input')

import settings
REMOTE_NODE_INFO_FILE = settings.LOG_DIR + '/remote_node_info.json'
REMOTE_SYNC_SCHEDULE_FILE = settings.LOG_DIR + '/remote_sync_schedule.json'
GPS_STATE_FILE = settings.LOG_DIR + '/gps.json'
NEXT_LORA_SYNC_FILE = settings.LOG_DIR + '/next_lora_sync.json'

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

    try:
        with open(NEXT_LORA_SYNC_FILE, 'r') as f:
            settings.nextLoraSync = ujson.load(f).get('next')
    except Exception:
        settings.nextLoraSync = None

    gc.collect()

load_remote_node_info()

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

def save_next_lora_sync():
    try:
        with open(NEXT_LORA_SYNC_FILE, 'w') as f:
            ujson.dump({'next': settings.nextLoraSync}, f)
    except Exception:
        pass
    gc.collect()

async def periodic_wp_sync():
    if settings.NODE_TYPE != 'base':
        return
    while True:
        await register_with_wp()
        await send_settings_to_wp()
        await fetch_settings_from_wp()
        await send_data_to_wp()
        await poll_ota_jobs()
        await asyncio.sleep(300)
        gc.collect()

async def heartbeat_ping_loop():
    if settings.NODE_TYPE != 'base':
        return
    while True:
        await heartbeat_ping()
        await asyncio.sleep(60)
        gc.collect()

async def check_suspend_remove():
    if settings.NODE_TYPE != 'base':
        return
    from wprest import WORDPRESS_API_URL
    if not WORDPRESS_API_URL:
        return
    try:
        headers = {}
        try:
            headers = _auth_headers()
        except Exception:
            headers = {}
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/settings/{settings.UNIT_ID}', headers=headers)
        if resp.status_code == 200:
            settings_data = resp.json().get('settings', {})
            if settings_data.get('suspended'):
                await debug_print('Device is suspended by admin', 'WARN')
                while True:
                    await asyncio.sleep(60)
    except Exception:
        pass
    gc.collect()

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
}

pending_commands = {}   # base: uid -> "func(arg1,arg2,...)"

import time as _time

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

def _attach_spi_shim():
    try:
        if not (machine and hasattr(machine, 'SPI') and getattr(settings, 'CLK_PIN', None) is not None):
            return None
        spi = None
        try:
            spi = machine.SPI(
                settings.SPI_BUS,
                baudrate=getattr(settings, 'LORA_SPI_BAUD', 1000000),
                sck=machine.Pin(settings.CLK_PIN),
                mosi=machine.Pin(settings.MOSI_PIN),
                miso=machine.Pin(settings.MISO_PIN)
            )
        except Exception:
            try:
                spi = machine.SPI(settings.SPI_BUS)
                spi.init(
                    baudrate=getattr(settings, 'LORA_SPI_BAUD', 1000000),
                    sck=machine.Pin(settings.CLK_PIN),
                    mosi=machine.Pin(settings.MOSI_PIN),
                    miso=machine.Pin(settings.MISO_PIN)
                )
            except Exception:
                spi = None
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
    gc.collect()

async def init_lora():
    global lora
    print('[DEBUG] init_lora start')
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
        lora = SX1262(
            settings.SPI_BUS, settings.CLK_PIN, settings.MOSI_PIN, settings.MISO_PIN,
            settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN
        )
        print('[DEBUG] init_lora: SX1262 object created')
        _deinit_spi_if_any(lora)

        async def _attempt_begin(lo, attempts=3):
            try:
                shim = _attach_spi_shim()
                if shim and not getattr(lo, 'spi', None):
                    lo.spi = shim
                    await debug_print("lora: pre-attached machine.SPI shim before begin attempts", "LORA")
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
                        shim = _attach_spi_shim()
                        if shim:
                            lo.spi = shim
                            await debug_print("lora: attached machine.SPI shim and retrying begin", "LORA")
                    except Exception:
                        pass
                    try:
                        _time.sleep_ms(120)
                    except Exception:
                        pass
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
                        shim = _attach_spi_shim()
                        if shim:
                            try:
                                lo2 = SX1262(shim, settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN)
                            except Exception:
                                lo2 = SX1262(spi=shim, cs=settings.CS_PIN, irq=settings.IRQ_PIN, rst=settings.RST_PIN, busy=settings.BUSY_PIN)
                            lo = lo2
                            status = lo.begin(freq=settings.FREQ)
                            return status
                    except Exception:
                        pass
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
                    shim = _attach_spi_shim()
                    if shim:
                        newlo = SX1262(shim, settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN)
                        lora = newlo
                        await debug_print("lora: re-instantiated with shim, retrying begin", "LORA")
                except Exception:
                    pass
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
                await debug_print(f'LoRa diagnostics failed: {exc}', 'ERROR')
                await log_error(f'LoRa diagnostics failed: {exc}')
                lora = None
                return False

        if status == 0:
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

        if status == 0:
            await debug_print("lora: initialized", "LORA")
            try:
                from oled import display_message
                await display_message("LoRa Ready", 2)
            except Exception:
                pass
            await print_remote_nodes_async()
            try:
                if getattr(settings, 'NODE_TYPE', 'base') == 'base' and lora is not None:
                    lora.setOperatingMode(lora.MODE_RX)
                    led_status_flash('LORA_RX')
                elif getattr(settings, 'NODE_TYPE', 'base') == 'remote' and lora is not None:
                    lora.setOperatingMode(lora.MODE_STDBY)
                    led_status_flash('LORA_TX')
            except Exception:
                pass
            print('[DEBUG] init_lora: completed successfully')
            gc.collect()
            return True

        error_msg = f"LoRa initialization failed with status: {status}"
        await debug_print(error_msg, "ERROR")
        try:
            from oled import display_message
            await display_message("LoRa Error", 2)
        except Exception:
            pass
        await log_error(error_msg)
        try:
            _safe_pin_input(settings.CS_PIN)
            _safe_pin_input(settings.RST_PIN)
            _safe_pin_input(settings.IRQ_PIN)
            _safe_pin_input(settings.BUSY_PIN)
        except Exception:
            pass
        lora = None
        gc.collect()
        return False
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
        try:
            _deinit_spi_if_any(lora)
        except Exception:
            pass
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
    parts = []
    total = 0
    part_failure = False
    chunk_sent = False
    attempt = 0
    st_code = None
    ev = 0
    ev_pre = 0
    ev_post = 0
    ev2 = 0
    txt2 = ''
    obj2 = None
    rel = 0
    blat = None
    blng = None
    balt = None
    bacc = None
    bts = None
    sent = False
    shrink_attempt = 0
    sent_ok = False
    chunk_msg = None
    new_raw = 0
    max_shrinks = 4
    max_shrink_retries = 3
    jitter_base = 0.02
    max_payload = int(getattr(settings, 'LORA_MAX_PAYLOAD', 220) or 220)
    raw_chunk_size = 80
    transient_codes = [86, 87, 89]
    shrink_codes = [-4]
    TX_DONE_FLAG = getattr(SX1262, 'TX_DONE', None) if SX1262 is not None else None
    RX_DONE_FLAG = getattr(SX1262, 'RX_DONE', None) if SX1262 is not None else None

    now = time.ticks_ms()

    try:
        if _last_tx_exception_ms and time.ticks_diff(now, _last_tx_exception_ms) < _TX_EXCEPTION_COOLDOWN_MS:
            await debug_print('lora: cooling down after recent TX error', 'LORA')
            return False
    except Exception:
        pass

    if lora is None:
        if _init_failures >= _MAX_INIT_FAILS:
            return False
        await debug_print("LoRa: initializing...", "LORA")
        async with pin_lock:
            ok = await init_lora()
        if not ok:
            _init_failures += 1
            return False
        _init_failures = 0
        _last_activity_ms = now

    role = getattr(settings, 'NODE_TYPE', 'base')

    if role == 'base':
        while True:
            try:
                RX_DONE_FLAG = getattr(SX1262, 'RX_DONE', None)
                try:
                    ev = lora._events()
                except Exception:
                    ev = 0
                if RX_DONE_FLAG is not None and (ev & RX_DONE_FLAG):
                    try:
                        msg_bytes, err = lora._readData(0)
                        await debug_print(f"lora: RX len={len(msg_bytes if msg_bytes else b'')} err={err}", "LORA")
                        if err != 0:
                            await debug_print(f"lora: RX err={err} discarded", "LORA")
                    except Exception as rexc:
                        await debug_print(f"lora: _readData exception: {rexc}", "ERROR")
                        msg_bytes = None
                        err = -1
                    if err == 0 and msg_bytes:
                        try:
                            sdata.lora_SigStr = lora.getRSSI()
                            sdata.lora_snr = lora.getSNR()
                            sdata.lora_last_rx_ts = time.time()
                        except Exception:
                            pass
                        try:
                            if isinstance(msg_bytes, (bytes, bytearray)):
                                msg_str = msg_bytes.decode('utf-8', 'ignore')
                            else:
                                msg_str = str(msg_bytes)
                            await debug_print(f"lora: RX txt={msg_str}", "LORA")
                            try:
                                payload = ujson.loads(msg_str)
                            except Exception:
                                payload = None
                            if payload is None:
                                # Try old string format
                                if msg_str.startswith('TS:'):
                                    parts = msg_str.split(',')
                                    payload = {}
                                    for part in parts:
                                        if ':' in part:
                                            key, value = part.split(':', 1)
                                            payload[key.lower().strip()] = value.strip()
                                else:
                                    payload = {'raw': msg_str}

                            if isinstance(payload, dict) and payload.get('chunked'):
                                try:
                                    uid = str(payload.get('uid') or payload.get('unit_id') or 'unknown')
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
                                            assembled_obj = ujson.loads(assembled.decode('utf-8', 'ignore'))
                                        except Exception:
                                            assembled_obj = {'raw': assembled.decode('utf-8', 'ignore')}
                                        payload = assembled_obj
                                        await debug_print(f"lora: assembled for {uid}", 'LORA')
                                        del _lora_incoming_chunks[uid]
                                    else:
                                        await asyncio.sleep(0)
                                        continue
                                except Exception as e:
                                    await debug_print(f"lora: chunk handling error: {e}", "ERROR")
                                    await asyncio.sleep(0)
                                    continue

                            if 'enc' in payload and payload['enc'] == 1:
                                try:
                                    secret = getattr(settings, 'LORA_ENCRYPT_SECRET', '')
                                    key = secret.encode()
                                    if len(key) < 32:
                                        key = (key + b'\x00'*32)[:32]
                                    nonce_str = payload.get('nonce', '')
                                    nonce = bytes(int(nonce_str[i:i+2], 16) for i in range(0, len(nonce_str), 2))
                                    ct_str = payload.get('ct', '')
                                    ct = bytes(int(ct_str[i:i+2], 16) for i in range(0, len(ct_str), 2))
                                    pt = chacha20_decrypt(key, nonce, 1, ct)
                                    inner = ujson.loads(pt.decode('utf-8', 'ignore'))
                                    payload = inner
                                except Exception as de:
                                    await debug_print(f"lora: decrypt failed: {de}", "ERROR")
                                    await asyncio.sleep(0)
                                    continue

                            if getattr(settings, 'LORA_HMAC_ENABLED', False):
                                if 'sig' not in payload:
                                    if getattr(settings, 'LORA_HMAC_REJECT_UNSIGNED', False):
                                        await debug_print("lora: unsigned payload rejected", "WARN")
                                        await asyncio.sleep(0)
                                        continue
                                else:
                                    try:
                                        secret = getattr(settings, 'LORA_HMAC_SECRET', '').encode()
                                        ctr = payload.get('ctr', 0)
                                        mac_src = b"|".join([
                                            secret,
                                            str(payload.get('uid', '')).encode(),
                                            str(payload.get('ts', '')).encode(),
                                            str(ctr).encode()
                                        ])
                                        import uhashlib
                                        h = uhashlib.sha256(mac_src)
                                        import ubinascii
                                        expected = ubinascii.hexlify(h.digest())[:32].decode()
                                        if expected != payload['sig']:
                                            await debug_print("lora: invalid signature", "ERROR")
                                            await asyncio.sleep(0)
                                            continue
                                        if getattr(settings, 'LORA_HMAC_REPLAY_PROTECT', False):
                                            ctrs = _load_remote_counters()
                                            uid = str(payload.get('uid', ''))
                                            last = ctrs.get(uid, 0)
                                            if ctr <= last:
                                                await debug_print("lora: replay detected", "ERROR")
                                                await asyncio.sleep(0)
                                                continue
                                            ctrs[uid] = ctr
                                            _save_remote_counters(ctrs)
                                        del payload['sig']
                                        del payload['ctr']
                                    except Exception as ve:
                                        await debug_print(f"lora: hmac verify failed: {ve}", "ERROR")
                                        await asyncio.sleep(0)
                                        continue

                            uid = payload.get('uid', '') or payload.get('unit_id', '')

                            if 'data' in payload and isinstance(payload['data'], list):
                                stage_remote_field_data(uid, payload['data'])
                            elif 'files' in payload and isinstance(payload['files'], dict):
                                stage_remote_files(uid, payload['files'])
                            else:
                                record = {'timestamp': int(time.time()),
                                          'remote_timestamp': payload.get('ts'),
                                          'cur_temp_f': payload.get('t_f') or payload.get('temp_f'),
                                          'cur_temp_c': payload.get('t_c') or payload.get('temp_c'),
                                          'cur_humid': payload.get('hum') or payload.get('humid'),
                                          'cur_bar_pres': payload.get('bar'),
                                          'sys_voltage': payload.get('v'),
                                          'free_mem': payload.get('fm'),
                                          'remote_unit_id': uid,
                                          'node_type': 'remote',
                                          'source': 'remote'
                                          }
                                try:
                                    append_field_data_entry(record)
                                    await debug_print("persisted remote data to field log", 'LORA')
                                except Exception as e:
                                    await debug_print(f"lora: failed to persist remote line: {e}", "ERROR")
                                write_lora_log(f"Base received remote payload: {str(record)[:160]}", 'INFO')

                            try:
                                if uid:
                                    settings.REMOTE_NODE_INFO = getattr(settings, 'REMOTE_NODE_INFO', {})
                                    last_payload = record if 'record' in locals() else payload
                                    settings.REMOTE_NODE_INFO[str(uid)] = {'last_seen': int(time.time()), 'last_payload': last_payload}
                                    try:
                                        settings.REMOTE_NODE_INFO[str(uid)]['last_rssi'] = lora.getRSSI()
                                        settings.REMOTE_NODE_INFO[str(uid)]['last_snr'] = lora.getSNR()
                                    except Exception:
                                        pass
                                    save_remote_node_info()
                                    if isinstance(payload, dict) and payload.get('settings'):
                                        try:
                                            staged_path = settings.LOG_DIR.rstrip('/') + f'/device_settings-{uid}.json'
                                            with open(staged_path, 'w') as sf:
                                                ujson.dump(payload.get('settings'), sf)
                                            write_lora_log(f"Base: persisted staged settings for {uid}", 'INFO')
                                        except Exception:
                                            pass
                            except Exception:
                                pass

                            # === COMMAND QUEUING (from previous version) ===
                            if uid:
                                try:
                                    temp_f_val = float(payload.get('t_f', 100.0))
                                    if temp_f_val < 80:   # example criteria from previous version
                                        pending_commands[uid] = "toggle_relay(1,on,5)"
                                        await debug_print(f"Queued command for {uid} (low temp)", "COMMAND")
                                except Exception as e:
                                    await debug_print(f"Command queuing error: {e}", "ERROR")

                            ack = {'ack': 'ok'}
                            try:
                                jobs = await poll_ota_jobs()
                                for job in jobs:
                                    if job.get('target') == uid and job.get('type') == 'firmware_update':
                                        from firmware_updater import download_and_apply_firmware
                                        dl = download_and_apply_firmware(job.get('url'), job.get('version'), expected_sha=job.get('sha'), manifest_url=job.get('manifest_url'))
                                        if dl['ok']:
                                            ack['ota_pending'] = True
                                            ack['ota_filename'] = os.path.basename(dl['path'])
                                            ack['ota_sha'] = dl['sha256']
                                            await send_ota_file_to_remote(uid, dl['path'], dl['sha256'])
                                            break
                            except Exception:
                                pass

                            next_in = getattr(settings, 'LORA_CHECK_IN_MINUTES', 5) * 60 + random.randint(-30, 30)
                            if next_in < 60: next_in = 60
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
                                settings.REMOTE_SYNC_SCHEDULE[str(uid)] = {'next_expected': int(time.time() + next_in)}
                                save_remote_sync_schedule()
                            except Exception:
                                pass

                            # === SEND COMMAND IF QUEUED (from previous version) ===
                            if uid in pending_commands:
                                command = pending_commands.pop(uid)
                                ack['cmd'] = command
                                await debug_print(f"Sending command to {uid}: {command}", "COMMAND")

                            try:
                                busy_start = time.ticks_ms()
                                while lora.gpio.value() and time.ticks_diff(time.ticks_ms(), busy_start) < 2000:
                                    await asyncio.sleep(0.01)
                                lora.setOperatingMode(lora.MODE_TX)
                                lora.send(ujson.dumps(ack).encode('utf-8'))
                                ack_start = time.ticks_ms()
                                while time.ticks_diff(time.ticks_ms(), ack_start) < 2000:
                                    ev = lora._events()
                                    if getattr(lora, 'TX_DONE', 0) and (ev & lora.TX_DONE):
                                        break
                                    await asyncio.sleep(0.01)
                                busy_start = time.ticks_ms()
                                while lora.gpio.value() and time.ticks_diff(time.ticks_ms(), busy_start) < 2000:
                                    await asyncio.sleep(0.01)
                                lora.setOperatingMode(lora.MODE_RX)
                                sdata.lora_last_tx_ts = time.time()
                            except Exception:
                                try:
                                    lora.setOperatingMode(lora.MODE_TX)
                                    lora.send(ujson.dumps(ack).encode('utf-8'))
                                    lora.setOperatingMode(lora.MODE_RX)
                                    sdata.lora_last_tx_ts = time.time()
                                except Exception:
                                    pass
                except Exception as e:
                    await debug_print(f"lora: processing RX failed: {e}", "ERROR")
            await asyncio.sleep(0)  # Yield to event loop
            gc.collect()

    if role == 'remote':
        probe_interval_ms = 30 * 1000
        fallback = 300
        if settings.nextLoraSync is None:
            settings.nextLoraSync = time.time() + fallback
            save_next_lora_sync()
        next_sync = settings.nextLoraSync
        now_epoch = time.time()
        due = now_epoch >= next_sync
        if not due:
            await asyncio.sleep(1)
            return False

        try:
            payload = {
                'unit_id': getattr(settings, 'UNIT_ID', ''),
                'name': getattr(settings, 'UNIT_Name', ''),
                'ts': now_epoch,
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

            if False and getattr(settings, 'LORA_ENCRYPT_ENABLED', False) and chacha20_encrypt and derive_nonce:
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

            await debug_print(f"lora: TX data len={len(data)}", "LORA")

            max_payload = int(getattr(settings, 'LORA_MAX_PAYLOAD', 220) or 220)

            if len(data) <= max_payload:
                if lora is None:
                    await debug_print("lora: reinit before single-frame send", "LORA")
                    async with pin_lock:
                        ok = await init_lora()
                    if not ok:
                        return False

                single_retries = int(getattr(settings, 'LORA_SINGLE_FRAME_RETRIES', 2))
                sent = False
                for sr in range(1, single_retries + 1):
                    try:
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

                        try:
                            resp = lora.send(data)
                        except Exception as send_exc:
                            await debug_print(f"lora: single-frame send() raised: {send_exc}", 'ERROR')
                            resp = -999

                        st_code = None
                        try:
                            if isinstance(resp, (tuple, list)):
                                if len(resp) >= 2 and isinstance(resp[1], int):
                                    st_code = resp[1]
                                elif len(resp) >= 1 and isinstance(resp[0], int):
                                    st_code = resp[0]
                                else:
                                    st_code = int(resp[0])
                            elif isinstance(resp, int):
                                st_code = resp
                            else:
                                st_code = int(resp)
                        except Exception:
                            st_code = -999

                        if st_code == 0:
                            sent = True
                            break

                        transient_codes = set(getattr(settings, 'LORA_CHUNK_TRANSIENT_CODES', [86, 87, 89]) or [86,87,89])
                        if (st_code in transient_codes) or (st_code == -1) or (st_code == -999):
                            await debug_print(f"lora: single-frame transient err {st_code} (attempt {sr}/{single_retries})", "WARN")
                            await asyncio.sleep(0.06 + random.random() * 0.06)
                            continue

                        await debug_print(f"lora: single-frame error {st_code} (fatal)", "ERROR")
                        break
                    except Exception:
                        await asyncio.sleep(0.05)
                        continue

                if sent:
                    try:
                        tx_start = time.ticks_ms()
                        while time.ticks_diff(time.ticks_ms(), tx_start) < 10000:
                            try:
                                ev = lora._events()
                            except Exception:
                                ev = 0
                            if TX_DONE_FLAG is not None and (ev & TX_DONE_FLAG):
                                break
                            await asyncio.sleep(0.01)
                        try:
                            lora.setOperatingMode(lora.MODE_RX)
                        except Exception:
                            pass
                    except Exception:
                        pass
                    _last_send_ms = time.ticks_ms()
                    _last_activity_ms = _last_send_ms

                    ack_wait_ms = int(getattr(settings, 'LORA_CHUNK_ACK_WAIT_MS', 1500))
                    start_wait = time.ticks_ms()
                    ack_received = False
                    while time.ticks_diff(time.ticks_ms(), start_wait) < ack_wait_ms:
                        try:
                            ev2 = lora._events()
                        except Exception:
                            ev2 = 0
                        if RX_DONE_FLAG is not None and (ev2 & RX_DONE_FLAG):
                            try:
                                msg2, err2 = lora._readData(0)
                            except Exception:
                                msg2 = None
                                err2 = -1
                            if err2 == 0 and msg2:
                                try:
                                    txt2 = msg2.decode('utf-8', 'ignore') if isinstance(msg2, (bytes, bytearray)) else str(msg2)
                                    obj2 = ujson.loads(txt2)
                                    if isinstance(obj2, dict) and obj2.get('ack') == 'ok':
                                        ack_received = True
                                        try:
                                            if hasattr(lora, 'getRSSI'):
                                                sdata.lora_SigStr = lora.getRSSI()
                                                sdata.lora_last_rx_ts = time.time()
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
                                                save_next_lora_sync()
                                            elif 'next' in obj2:
                                                settings.nextLoraSync = int(obj2['next'])
                                                save_next_lora_sync()
                                        except Exception:
                                            pass
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

                                        # === COMMAND EXECUTION (from previous version) ===
                                        if 'cmd' in obj2:
                                            command = obj2['cmd']
                                            await debug_print(f"Raw response: {command}", "DEBUG")
                                            if '(' in command and command.endswith(')'):
                                                func_name, args_str = command.split('(', 1)
                                                args_str = args_str.rstrip(')')
                                                args = [arg.strip() for arg in args_str.split(',')] if args_str else []
                                                if func_name in command_handlers:
                                                    try:
                                                        await command_handlers[func_name](*args)
                                                        await debug_print(f"Executed command: {command}", "COMMAND")
                                                    except Exception as ce:
                                                        await debug_print(f"Command execution failed: {ce}", "ERROR")
                                                else:
                                                    await debug_print(f"Unknown command: {func_name}", "ERROR")
                                            else:
                                                await debug_print(f"Invalid command format: {command}", "ERROR")

                                        await debug_print(f"lora: next {getattr(settings, 'nextLoraSync', '')}", 'LORA')
                                        write_lora_log(f"Remote stored next sync epoch: {getattr(settings, 'nextLoraSync', '')}", 'INFO')
                                        led_status_flash('SUCCESS')

                                        if obj2.get('ota_pending'):
                                            # (OTA chunk receive code unchanged)
                                            pass
                                        break
                                except Exception:
                                    pass
                        await asyncio.sleep(0.01)
                    if not ack_received:
                        fallback = 300 + random.randint(-30, 30)
                        if fallback < 60: fallback = 60
                        settings.nextLoraSync = int(time.time() + fallback)
                        save_next_lora_sync()
                        write_lora_log(f"Remote no ACK, fallback next sync in {fallback} sec", 'INFO')
                    gc.collect()
                    return True

                await debug_print("lora: single-frame send failed after retries, re-initing radio", "ERROR")
                try:
                    if hasattr(lora, 'spi') and lora.spi:
                        lora.spi.deinit()
                    _last_tx_exception_ms = time.ticks_ms()
                except Exception:
                    pass
                lora = None
                gc.collect()
                return False

            # === FULL CHUNKED SEND PATH (unchanged from your current file) ===
            min_raw = int(getattr(settings, 'LORA_CHUNK_MIN_RAW_BYTES', 12))
            max_parts_allowed = int(getattr(settings, 'LORA_CHUNK_MAX_PARTS', 8))
            try:
                tmpl = {'unit_id': getattr(settings, 'UNIT_ID', ''), 'chunked': 1, 'seq': 999, 'total': 999, 'b64': ''}
                overhead = len(ujson.dumps(tmpl).encode('utf-8')) + 20
                avail_b64 = max_payload - overhead
                raw_chunk_size = max(min_raw, int((avail_b64 * 3) // 4)) if avail_b64 > 0 else min_raw
            except Exception:
                raw_chunk_size = max(min_raw, int(getattr(settings, 'LORA_CHUNK_RAW_BYTES', 80)))

            def _compact_payload_to_minimal(p):
                try:
                    return ujson.dumps({
                        'unit_id': p.get('unit_id'),
                        'ts': p.get('ts'),
                        't_f': p.get('t_f'),
                        'hum': p.get('hum'),
                        'bar': p.get('bar'),
                        'v': p.get('v')
                    }).encode('utf-8')
                except Exception:
                    return ujson.dumps({'unit_id': p.get('unit_id'), 'ts': p.get('ts')}).encode('utf-8')

            while shrink_attempt < max_shrinks and not sent_ok:
                parts = [data[i:i+raw_chunk_size] for i in range(0, len(data), raw_chunk_size)]
                total = len(parts)

                if total > max_parts_allowed:
                    await debug_print(f"lora: large split {total} parts > max {max_parts_allowed}, attempting compact payload", "LORA")
                    compacted = _compact_payload_to_minimal(payload)
                    if len(compacted) < len(data):
                        data = compacted
                        parts = [data[i:i+raw_chunk_size] for i in range(0, len(data), raw_chunk_size)]
                        total = len(parts)
                    if total > max_parts_allowed:
                        tiny = ujson.dumps({'unit_id': getattr(settings, 'UNIT_ID', ''), 'ts': payload.get('ts')}).encode('utf-8')
                        data = tiny
                        parts = [data[i:i+raw_chunk_size] for i in range(0, len(data), raw_chunk_size)]
                        total = len(parts)
                    if total > max_parts_allowed:
                        await debug_print(f"lora: aborting chunk send, required parts {total} exceeds limit {max_parts_allowed}", "ERROR")
                        write_lora_log(f"Remote chunk send aborted: {total} parts exceeds max {max_parts_allowed}", 'ERROR')
                        gc.collect()
                        return False

                    if len(data) <= max_payload:
                        await debug_print("lora: compaction produced single-frame payload; attempting single-frame send", "LORA")
                        if lora is None:
                            await debug_print("lora: reinit before single-frame send (post-compact)", "LORA")
                            async with pin_lock:
                                ok_init = await init_lora()
                            if not ok_init:
                                return False
                        try:
                            resp = lora.send(data)
                        except Exception as se:
                            await debug_print(f"lora: single-frame send() (post-compact) raised: {se}", 'ERROR')
                            resp = -999
                        try:
                            if isinstance(resp, (tuple, list)) and len(resp) >= 2 and isinstance(resp[1], int):
                                st_last = resp[1]
                            elif isinstance(resp, int):
                                st_last = resp
                            else:
                                st_last = int(resp[0]) if isinstance(resp, (tuple, list)) else int(resp)
                        except Exception:
                            st_last = -999
                        if st_last == 0:
                            await debug_print("lora: single-frame send (post-compact) succeeded", "LORA")
                            _last_send_ms = time.ticks_ms()
                            _last_activity_ms = _last_send_ms
                            try:
                                tx_start = time.ticks_ms()
                                while time.ticks_diff(time.ticks_ms(), tx_start) < 10000:
                                    try:
                                        ev = lora._events()
                                    except Exception:
                                        ev = 0
                                    if TX_DONE_FLAG is not None and (ev & TX_DONE_FLAG):
                                        break
                                    await asyncio.sleep(0.01)
                                try:
                                    lora.setOperatingMode(lora.MODE_RX)
                                except Exception:
                                    pass
                            except Exception:
                                pass
                            ack_wait_ms = int(getattr(settings, 'LORA_CHUNK_ACK_WAIT_MS', 1500))
                            start_wait = time.ticks_ms()
                            ack_received = False
                            while time.ticks_diff(time.ticks_ms(), start_wait) < ack_wait_ms:
                                try:
                                    ev2 = lora._events()
                                except Exception:
                                    ev2 = 0
                                if RX_DONE_FLAG is not None and (ev2 & RX_DONE_FLAG):
                                    try:
                                        msg2, err2 = lora._readData(0)
                                    except Exception:
                                        msg2 = None
                                        err2 = -1
                                    if err2 == 0 and msg2:
                                        try:
                                            txt2 = msg2.decode('utf-8', 'ignore') if isinstance(msg2, (bytes, bytearray)) else str(msg2)
                                            obj2 = ujson.loads(txt2)
                                            if isinstance(obj2, dict) and obj2.get('ack') == 'ok':
                                                ack_received = True
                                                try:
                                                    if hasattr(lora, 'getRSSI'):
                                                        sdata.lora_SigStr = lora.getRSSI()
                                                        sdata.lora_last_rx_ts = time.time()
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
                                                        save_next_lora_sync()
                                                    elif 'next' in obj2:
                                                        settings.nextLoraSync = int(obj2['next'])
                                                        save_next_lora_sync()
                                                except Exception:
                                                    pass
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

                                                # === COMMAND EXECUTION (same block) ===
                                                if 'cmd' in obj2:
                                                    command = obj2['cmd']
                                                    await debug_print(f"Raw response: {command}", "DEBUG")
                                                    if '(' in command and command.endswith(')'):
                                                        func_name, args_str = command.split('(', 1)
                                                        args_str = args_str.rstrip(')')
                                                        args = [arg.strip() for arg in args_str.split(',')] if args_str else []
                                                        if func_name in command_handlers:
                                                            try:
                                                                await command_handlers[func_name](*args)
                                                                await debug_print(f"Executed command: {command}", "COMMAND")
                                                            except Exception as ce:
                                                                await debug_print(f"Command execution failed: {ce}", "ERROR")
                                                        else:
                                                            await debug_print(f"Unknown command: {func_name}", "ERROR")
                                                    else:
                                                        await debug_print(f"Invalid command format: {command}", "ERROR")

                                                await debug_print(f"lora: next {getattr(settings, 'nextLoraSync', '')}", 'LORA')
                                                write_lora_log(f"Remote stored next sync epoch: {getattr(settings, 'nextLoraSync', '')}", 'INFO')
                                                led_status_flash('SUCCESS')
                                                if obj2.get('ota_pending'):
                                                    # OTA code unchanged
                                                    pass
                                                break
                                        except Exception:
                                            pass
                                await asyncio.sleep(0.01)
                            if not ack_received:
                                fallback = 300 + random.randint(-30, 30)
                                if fallback < 60: fallback = 60
                                settings.nextLoraSync = int(time.time() + fallback)
                                save_next_lora_sync()
                                write_lora_log(f"Remote no ACK, fallback next sync in {fallback} sec", 'INFO')
                            gc.collect()
                            return True
                        else:
                            await debug_print(f"lora: single-frame (post-compact) failed: {st_last}", "WARN")
                            if st_last < 0:
                                await debug_print("lora: negative code on single-frame post-compact; reinit attempt", "LORA")
                                async with pin_lock:
                                    ok_init = await init_lora()
                                if not ok_init:
                                    return False
                                await asyncio.sleep(0.08)

                for idx, chunk in enumerate(parts, start=1):
                    await debug_print(f"lora: sending chunk {idx}/{total}", "LORA")
                    attempt = 0
                    chunk_sent = False
                    while attempt < max_shrink_retries and not chunk_sent:
                        try:
                            if lora is None:
                                await debug_print("lora: SPI/radio missing before chunk send, attempting re-init", "LORA")
                                async with pin_lock:
                                    ok = await init_lora()
                                if not ok or lora is None:
                                    await debug_print("lora: re-init failed, aborting chunk send", "ERROR")
                                    part_failure = True
                                    break

                            try:
                                busy_start = time.ticks_ms()
                                while True:
                                    gpio = getattr(lora, 'gpio', None)
                                    busy = gpio.value() if gpio and hasattr(gpio, 'value') else False
                                    if not busy:
                                        break
                                    if time.ticks_diff(time.ticks_ms(), busy_start) > 800:
                                        break
                                    await asyncio.sleep(0.01)
                            except Exception:
                                pass
                            try:
                                lora.setOperatingMode(lora.MODE_TX)
                            except Exception:
                                pass

                            b64 = _ub.b2a_base64(chunk).decode().strip()
                            chunk_msg = {'unit_id': getattr(settings, 'UNIT_ID', ''), 'chunked': 1, 'seq': idx, 'total': total, 'b64': b64}
                            resp = None
                            try:
                                resp = lora.send(ujson.dumps(chunk_msg).encode('utf-8'))
                            except Exception as exc_send:
                                await debug_print(f"lora: chunk send exception: {exc_send}", "ERROR")
                                resp = -999

                            st_code = None
                            if isinstance(resp, (tuple, list)) and len(resp) > 0:
                                if len(resp) >= 2 and isinstance(resp[1], int):
                                    st_code = resp[1]
                                elif isinstance(resp[0], int):
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

                            if st_code != 0:
                                await debug_print(f"lora: raw send resp={resp} normalized_code={st_code} (part {idx}/{total})", "LORA")

                            if st_code == 0:
                                try:
                                    tx_start = time.ticks_ms()
                                    while time.ticks_diff(time.ticks_ms(), tx_start) < 10000:
                                        try:
                                            ev = lora._events()
                                        except Exception:
                                            ev = 0
                                        if TX_DONE_FLAG is not None and (ev & TX_DONE_FLAG):
                                            await debug_print(f"lora: TX_DONE for chunk {idx}", 'LORA')
                                            break
                                        await asyncio.sleep(0.01)
                                except Exception:
                                    pass
                                chunk_sent = True
                                await asyncio.sleep(jitter_base + random.random() * jitter_base)
                                break

                            if st_code is not None and st_code < 0:
                                await debug_print(f"lora: negative chunk send code {st_code} — attempting guarded re-init", "LORA")
                                async with pin_lock:
                                    ok = await init_lora()
                                if ok and lora is not None:
                                    await debug_print("lora: re-init succeeded, retrying chunk send", "LORA")
                                    attempt += 1
                                    await asyncio.sleep(0.06)
                                    continue
                                else:
                                    await debug_print("lora: re-init after negative code failed, aborting", "ERROR")
                                    part_failure = True
                                    break

                            shrink_codes = set(getattr(settings, 'LORA_CHUNK_SHRINK_CODES', [-4]) or [-4])
                            transient_codes = set(getattr(settings, 'LORA_CHUNK_TRANSIENT_CODES', [86, 87, 89]) or [86,87,89])
                            if st_code in shrink_codes:
                                await debug_print(f"lora: chunk send indicates shrink-needed (code {st_code})", "ERROR")
                                part_failure = True
                                break
                            if st_code in transient_codes or st_code in (-999,):
                                attempt += 1
                                await asyncio.sleep(0.05 + random.random() * 0.05)
                                continue

                            await debug_print(f"lora: unexpected chunk TX err {st_code} (retry attempt {attempt+1})", "WARN")
                            attempt += 1
                            await asyncio.sleep(0.05 + random.random() * 0.05)
                            continue

                        except Exception as e:
                            await debug_print(f"lora: unexpected chunk send error: {e}", "ERROR")
                            attempt += 1
                            await asyncio.sleep(0.05)
                    if not chunk_sent:
                        part_failure = True
                        break
                if part_failure:
                    shrink_attempt += 1
                    new_raw = max(min_raw, raw_chunk_size // 2)
                    if new_raw == raw_chunk_size:
                        await debug_print("lora: cannot shrink further, aborting", "ERROR")
                        gc.collect()
                        return False
                    raw_chunk_size = new_raw
                    await debug_print(f"lora: shrinking raw chunk to {raw_chunk_size}", "LORA")
                    continue
                sent_ok = True

            if sent_ok:
                try:
                    lora.setOperatingMode(lora.MODE_RX)
                except Exception:
                    pass

                ack_wait_ms = int(getattr(settings, 'LORA_CHUNK_ACK_WAIT_MS', 1500))
                start_wait = time.ticks_ms()
                ack_received = False
                while time.ticks_diff(time.ticks_ms(), start_wait) < ack_wait_ms:
                    try:
                        ev2 = lora._events()
                    except Exception:
                        ev2 = 0
                    if RX_DONE_FLAG is not None and (ev2 & RX_DONE_FLAG):
                        try:
                            msg2, err2 = lora._readData(0)
                        except Exception:
                            msg2 = None
                            err2 = -1
                        if err2 == 0 and msg2:
                            try:
                                txt2 = msg2.decode('utf-8', 'ignore') if isinstance(msg2, (bytes, bytearray)) else str(msg2)
                                obj2 = ujson.loads(txt2)
                                if isinstance(obj2, dict) and obj2.get('ack') == 'ok':
                                    ack_received = True
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
                                            save_next_lora_sync()
                                        elif 'next' in obj2:
                                            settings.nextLoraSync = int(obj2['next'])
                                            save_next_lora_sync()
                                    except Exception:
                                        pass
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

                                    # === COMMAND EXECUTION (same block) ===
                                    if 'cmd' in obj2:
                                        command = obj2['cmd']
                                        await debug_print(f"Raw response: {command}", "DEBUG")
                                        if '(' in command and command.endswith(')'):
                                            func_name, args_str = command.split('(', 1)
                                            args_str = args_str.rstrip(')')
                                            args = [arg.strip() for arg in args_str.split(',')] if args_str else []
                                            if func_name in command_handlers:
                                                try:
                                                    await command_handlers[func_name](*args)
                                                    await debug_print(f"Executed command: {command}", "COMMAND")
                                                except Exception as ce:
                                                    await debug_print(f"Command execution failed: {ce}", "ERROR")
                                            else:
                                                await debug_print(f"Unknown command: {func_name}", "ERROR")
                                        else:
                                            await debug_print(f"Invalid command format: {command}", "ERROR")

                                    await debug_print(f"lora: next {getattr(settings, 'nextLoraSync', '')}", 'LORA')
                                    write_lora_log(f"Remote stored next sync epoch: {getattr(settings, 'nextLoraSync', '')}", 'INFO')
                                    led_status_flash('SUCCESS')
                                    if obj2.get('ota_pending'):
                                        # OTA code unchanged
                                        pass
                                    break
                            except Exception:
                                pass
                    await asyncio.sleep(0.01)
                if not ack_received:
                    fallback = 300 + random.randint(-30, 30)
                    if fallback < 60: fallback = 60
                    settings.nextLoraSync = int(time.time() + fallback)
                    save_next_lora_sync()
                    write_lora_log(f"Remote no ACK, fallback next sync in {fallback} sec", 'INFO')

                _last_send_ms = time.ticks_ms()
                _last_activity_ms = _last_send_ms
                gc.collect()
                return True

            await debug_print("lora: chunk send failed after retries, re-initing radio", "ERROR")
            try:
                if hasattr(lora, 'spi') and lora.spi:
                    lora.spi.deinit()
                _last_tx_exception_ms = time.ticks_ms()
            except Exception:
                pass
            lora = None
            gc.collect()
            return False

        except Exception as e:
            await debug_print(f"Remote TX exception: {e}", "ERROR")
            await log_error(f"Remote TX exception: {e}")
            try:
                _last_tx_exception_ms = time.ticks_ms()
            except Exception:
                pass
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
            gc.collect()
            return False
    gc.collect()
    return True

# OTA file sending from base to remote (unchanged)
async def send_ota_file_to_remote(remote_uid, file_path, sha256):
    try:
        raw_chunk_size = 80
        file_size = os.stat(file_path)[6]
        total = (file_size // raw_chunk_size) + (1 if file_size % raw_chunk_size else 0)
        with open(file_path, 'rb') as f:
            seq = 1
            chunk = f.read(raw_chunk_size)
            while chunk:
                b64 = _ub.b2a_base64(chunk).decode().strip()
                chunk_msg = {
                    'ota_file': 1,
                    'filename': os.path.basename(file_path),
                    'sha': sha256,
                    'seq': seq,
                    'total': total,
                    'b64': b64,
                    'unit_id': remote_uid
                }
                lora.send(ujson.dumps(chunk_msg).encode('utf-8'))
                tx_start = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), tx_start) < 10000:
                    ev = lora._events()
                    if TX_DONE_FLAG and (ev & TX_DONE_FLAG):
                        break
                    await asyncio.sleep(0.01)
                await asyncio.sleep(0.1)
                seq += 1
                chunk = f.read(raw_chunk_size)
        return True
    except Exception as e:
        await debug_print(f"Failed to send OTA file: {e}", "ERROR")
        return False
    gc.collect()

async def send_remote_field_data_batch(payload):
    try:
        data = ujson.dumps(payload).encode('utf-8')
        return await send_lora_payload(data, confirm=True)
    except Exception as e:
        await debug_print(f"send_remote_field_data_batch error: {e}", "ERROR")
        return False
    gc.collect()

async def send_remote_state_files(files):
    try:
        files_str = {}
        for name, content in files.items():
            if isinstance(content, bytes):
                files_str[name] = content.decode('utf-8', 'ignore')
            else:
                files_str[name] = str(content)
        payload = {'files': files_str}
        data = ujson.dumps(payload).encode('utf-8')
        return await send_lora_payload(data, confirm=True)
    except Exception as e:
        await debug_print(f"send_remote_state_files error: {e}", "ERROR")
        return False
    gc.collect()

async def send_lora_payload(data_bytes, confirm=True, max_wait_ms=1500):
    try:
        if lora is None:
            return False
        max_payload = int(getattr(settings, 'LORA_MAX_PAYLOAD', 220))
        raw_chunk_size = 80
        if len(data_bytes) <= max_payload:
            lora.setOperatingMode(lora.MODE_TX)
            resp = lora.send(data_bytes)
            st_code = 0 if resp == 0 else -1
            if st_code != 0:
                return False
            tx_start = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), tx_start) < 10000:
                ev = lora._events()
                if TX_DONE_FLAG and (ev & TX_DONE_FLAG):
                    break
                await asyncio.sleep(0.01)
            if confirm:
                lora.setOperatingMode(lora.MODE_RX)
                start_wait = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), start_wait) < max_wait_ms:
                    ev = lora._events()
                    if RX_DONE_FLAG and (ev & RX_DONE_FLAG):
                        msg, err = lora._readData(0)
                        if err == 0 and msg:
                            try:
                                obj = ujson.loads(msg.decode('utf-8', 'ignore'))
                                if obj.get('ack') == 'ok':
                                    return True
                            except Exception:
                                pass
                    await asyncio.sleep(0.01)
            return True
        else:
            parts = [data_bytes[i:i+raw_chunk_size] for i in range(0, len(data_bytes), raw_chunk_size)]
            total = len(parts)
            for seq, chunk in enumerate(parts, 1):
                b64 = _ub.b2a_base64(chunk).decode().strip()
                chunk_p = {'chunked': 1, 'seq': seq, 'total': total, 'b64': b64}
                chunk_data = ujson.dumps(chunk_p).encode('utf-8')
                lora.setOperatingMode(lora.MODE_TX)
                resp = lora.send(chunk_data)
                st_code = 0 if resp == 0 else -1
                if st_code != 0:
                    return False
                tx_start = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), tx_start) < 10000:
                    ev = lora._events()
                    if TX_DONE_FLAG and (ev & TX_DONE_FLAG):
                        break
                    await asyncio.sleep(0.01)
                await asyncio.sleep(0.1)
            if confirm:
                lora.setOperatingMode(lora.MODE_RX)
                start_wait = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), start_wait) < max_wait_ms:
                    ev = lora._events()
                    if RX_DONE_FLAG and (ev & RX_DONE_FLAG):
                        msg, err = lora._readData(0)
                        if err == 0 and msg:
                            try:
                                obj = ujson.loads(msg.decode('utf-8', 'ignore'))
                                if obj.get('ack') == 'ok':
                                    return True
                            except Exception:
                                pass
                    await asyncio.sleep(0.01)
            return True
    except Exception as e:
        await debug_print(f"send_lora_payload error: {e}", "ERROR")
        return False
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