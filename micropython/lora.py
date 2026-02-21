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

    lora_init_failures = 0
    MAX_LORA_INIT_FAILS = 3
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
        send_interval = 300  # Default to 5 minutes
        timeout_ms = 15000
        last_activity = time.ticks_ms()
        idle_timeout = 60000
        connected = False

        # For base: Track connected remote nodes {uid: last_ts}
        connected_remotes = {}

        # For base: Pending commands {uid: "func(arg1,arg2,arg3)"}
        pending_commands = {}

        while True:
            current_time = time.ticks_ms()
            if state == STATE_IDLE and time.ticks_diff(current_time, last_activity) > idle_timeout:
                await debug_print("Idle timeout reached, freeing pins", "LORA")
                async with pin_lock:
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
                        'ts': ts,
                        'uid': settings.UNIT_ID,
                        'company': getattr(settings, 'COMPANY', ''),
                        'site': getattr(settings, 'SITE', ''),
                        'zone': getattr(settings, 'ZONE', ''),
                        'cluster': getattr(settings, 'CLUSTER', ''),
                        'runtime': sdata.loop_runtime,
                        'script_runtime': sdata.script_runtime,
                        'temp_c': sdata.cur_temp_c,
                        'temp_f': sdata.cur_temp_f,
                        'bar': sdata.cur_bar_pres,
                        'humid': sdata.cur_humid
                    }
                    if getattr(settings, 'LORA_HMAC_ENABLED', False):
                        ctr_file = getattr(settings, 'LORA_HMAC_COUNTER_FILE', settings.LOG_DIR + '/lora_ctr.json')
                        ctr = 0
                        try:
                            with open(ctr_file, 'r') as cf:
                                ctr_obj = ujson.load(cf)
                                ctr = int(ctr_obj.get('ctr', 0))
                        except Exception:
                            ctr = 0
                        ctr += 1
                        try:
                            with open(ctr_file, 'w') as cfw:
                                ujson.dump({'ctr': ctr}, cfw)
                        except Exception:
                            pass
                        payload['ctr'] = ctr
                        secret = getattr(settings, 'LORA_HMAC_SECRET', '').encode()
                        mac_src = b"|".join([
                            secret,
                            str(payload['uid']).encode(),
                            str(payload['ts']).encode(),
                            str(ctr).encode()
                        ])
                        h = uhashlib.sha256(mac_src)
                        payload['sig'] = ubinascii.hexlify(h.digest())[:32].decode()

                    data = ujson.dumps(payload).encode()
                    await debug_print(f"Sending data: {ujson.dumps(payload)}", "LORA")
                    max_payload = getattr(settings, 'LORA_MAX_PAYLOAD', 220)
                    if len(data) > max_payload:
                        # Chunk logic
                        raw_chunk_size = 80
                        parts = [data[i:i+raw_chunk_size] for i in range(0, len(data), raw_chunk_size)]
                        total = len(parts)
                        for seq, chunk in enumerate(parts, 1):
                            b64 = _ub.b2a_base64(chunk).decode().strip()
                            chunk_msg = {'chunked': 1, 'seq': seq, 'total': total, 'b64': b64}
                            chunk_data = ujson.dumps(chunk_msg).encode()
                            async with pin_lock:
                                if lora is None:
                                    if not await init_lora():
                                        continue
                                lora.send(chunk_data)
                            await asyncio.sleep(0.1)
                    else:
                        async with pin_lock:
                            if lora is None:
                                if not await init_lora():
                                    continue
                            lora.send(data)
                    state = STATE_WAIT_RESPONSE
                    start_wait = time.ticks_ms()
                    last_activity = time.ticks_ms()

                elif state == STATE_WAIT_RESPONSE:
                    await debug_print("Remote: Waiting for response...", "LORA")
                    async with pin_lock:
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
                            payload = ujson.loads(msg_str)
                            if payload.get('ack') == 'ok':
                                if not connected:
                                    await debug_print("Connected to base station", "LORA")
                                    connected = True
                                if 'next_in' in payload:
                                    rel = int(payload['next_in'])
                                    if rel < 60:
                                        rel = 60
                                    send_interval = rel
                                if 'cmd' in payload:
                                    command = payload['cmd']
                                    if '(' in command and command.endswith(')'):
                                        func_name, args_str = command.split('(', 1)
                                        args_str = args_str.rstrip(')')
                                        args = [arg.strip() for arg in args_str.split(',')] if args_str else []
                                        if func_name in command_handlers:
                                            await command_handlers[func_name](*args)
                                            await debug_print(f"Executed command: {command}", "COMMAND")
                                        else:
                                            await debug_print(f"Unknown command: {func_name}", "ERROR")
                                    else:
                                        await debug_print(f"Invalid command format: {command}", "ERROR")
                                if getattr(settings, 'GPS_ACCEPT_FROM_BASE', True):
                                    blat = payload.get('gps_lat')
                                    blng = payload.get('gps_lng')
                                    if blat is not None and blng is not None:
                                        balt = payload.get('gps_alt_m')
                                        bacc = payload.get('gps_accuracy_m')
                                        bts = payload.get('gps_last_fix_ts')
                                        save_gps_state(blat, blng, balt, bacc, bts)
                                        await debug_print('lora: GPS adopted', 'LORA')
                            else:
                                await debug_print(f"Unknown response: {msg_str}", "WARN")
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
                        send_interval = 300 + random.randint(-30, 30)
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
                            payload = ujson.loads(msg_str)
                            if payload.get('chunked'):
                                uid = payload.get('uid', 'unknown')
                                seq = payload.get('seq', 1)
                                total = payload.get('total', 1)
                                b64 = payload.get('b64', '')
                                if b64:
                                    raw_chunk = _ub.a2b_base64(b64)
                                    entry = _lora_incoming_chunks.get(uid, {'total': total, 'parts': {}, 'ts': time.time()})
                                    entry['total'] = total
                                    entry['parts'][seq] = raw_chunk
                                    entry['ts'] = time.time()
                                    _lora_incoming_chunks[uid] = entry
                                    if len(entry['parts']) == total:
                                        assembled = b''.join(entry['parts'][i] for i in range(1, total + 1))
                                        payload = ujson.loads(assembled.decode())
                                        del _lora_incoming_chunks[uid]
                                    else:
                                        continue

                            if getattr(settings, 'LORA_HMAC_ENABLED', False) and 'sig' in payload:
                                secret = getattr(settings, 'LORA_HMAC_SECRET', '').encode()
                                ctr = payload.get('ctr', 0)
                                mac_src = b"|".join([
                                    secret,
                                    str(payload.get('uid', '')).encode(),
                                    str(payload.get('ts', '')).encode(),
                                    str(ctr).encode()
                                ])
                                h = uhashlib.sha256(mac_src)
                                expected = ubinascii.hexlify(h.digest())[:32].decode()
                                if expected != payload['sig']:
                                    await debug_print("lora: invalid signature", "ERROR")
                                    continue
                                if getattr(settings, 'LORA_HMAC_REPLAY_PROTECT', False):
                                    ctrs = _load_remote_counters()
                                    uid = payload.get('uid', '')
                                    last = ctrs.get(uid, 0)
                                    if ctr <= last:
                                        await debug_print("lora: replay detected", "ERROR")
                                        continue
                                    ctrs[uid] = ctr
                                    _save_remote_counters(ctrs)
                                del payload['sig']
                                del payload['ctr']

                            remote_ts = payload.get('ts')
                            remote_uid = payload.get('uid')
                            remote_company = payload.get('company', '')
                            remote_site = payload.get('site', '')
                            remote_zone = payload.get('zone', '')
                            remote_cluster = payload.get('cluster', '')
                            remote_runtime = payload.get('runtime')
                            remote_script_runtime = payload.get('script_runtime')
                            temp_c = payload.get('temp_c')
                            temp_f = payload.get('temp_f')
                            bar = payload.get('bar')
                            humid = payload.get('humid')

                            if remote_uid and remote_company is not None:
                                settings.REMOTE_NODE_INFO[remote_uid] = {
                                    'company': remote_company,
                                    'site': remote_site,
                                    'zone': remote_zone,
                                    'cluster': remote_cluster
                                }
                                save_remote_node_info()

                            if any(v is None for v in [remote_uid, remote_runtime, remote_script_runtime, temp_c, temp_f, bar, humid]):
                                error_msg = f"Missing fields in message"
                                await debug_print(error_msg, "ERROR")
                                await log_error(error_msg)
                            else:
                                base_ts = time.time()
                                log_line = f"{base_ts},{remote_uid},{remote_ts},{remote_runtime},{remote_script_runtime},{temp_c},{temp_f},{bar},{humid}\n"
                                temp_f_val = float(temp_f) if temp_f else 0.0
                                bar_val = float(bar) if bar else 0.0
                                humid_val = float(humid) if humid else 0.0
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
                                from utils import record_field_data
                                record_field_data()
                                connected_remotes[remote_uid] = base_ts
                                if temp_f_val < 80:
                                    pending_commands[remote_uid] = "toggle_relay(1,on,5)"
                                ack = {'ack': 'ok'}
                                next_in = getattr(settings, 'LORA_CHECK_IN_MINUTES', 5) * 60 + random.randint(-30, 30)
                                if next_in < 60: next_in = 60
                                ack['next_in'] = next_in
                                if getattr(settings, 'GPS_BROADCAST_TO_REMOTES', False):
                                    ack['gps_lat'] = getattr(settings, 'GPS_LAT', None)
                                    ack['gps_lng'] = getattr(settings, 'GPS_LNG', None)
                                    ack['gps_alt_m'] = getattr(settings, 'GPS_ALT_M', None)
                                    ack['gps_accuracy_m'] = getattr(settings, 'GPS_ACCURACY_M', None)
                                settings.REMOTE_SYNC_SCHEDULE[remote_uid] = {'next_expected': time.time() + next_in}
                                save_remote_sync_schedule()
                                if remote_uid in pending_commands:
                                    command = pending_commands.pop(remote_uid)
                                    ack['cmd'] = command
                                    await debug_print(f"Sending command to {remote_uid}: {command}", "COMMAND")
                                ack_data = ujson.dumps(ack).encode()
                                async with pin_lock:
                                    if lora is None:
                                        if not await init_lora():
                                            continue
                                    lora.send(ack_data)
                                    await debug_print(f"Sent ACK/CMD to {remote_uid}", "LORA")
                                if not connected:
                                    await debug_print("Base: New connection established", "LORA")
                                    connected = True
                                state = STATE_IDLE
                        except Exception as e:
                            error_msg = f"Invalid message: {str(e)}"
                            await debug_print(error_msg, "ERROR")
                            await log_error(error_msg)
                    elif err == -81:
                        await debug_print("Receive timeout - retrying...", "LORA")
                        state = STATE_IDLE
                        await asyncio.sleep(0)
                    else:
                        error_msg = f"Receive error: {err}"
                        await debug_print(error_msg, "ERROR")
                        await log_error(error_msg)
                        state = STATE_IDLE
                else:
                    state = STATE_IDLE
                    await asyncio.sleep(1)

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
    while True:
        await asyncio.sleep(60)  # Keep main_loop alive; adjust as needed

async def ai_health_monitor():
    while True:
        if TMON_AI.error_count > 3:
            await TMON_AI.recover_system()
        if TMON_AI.last_error:
            suggestion = await TMON_AI.suggest_action(TMON_AI.last_error[1])
            await log_error(f'AI suggestion: {suggestion}', 'ai_health_monitor')
        await asyncio.sleep(60)

async def ai_dashboard_display():
    from oled import display_message
    while True:
        msg = f"AI ERR: {TMON_AI.error_count}\n"
        if TMON_AI.last_error:
            msg += f"LAST: {TMON_AI.last_error[0][:20]}"
        await display_message(msg, 2)
        await asyncio.sleep(60)

async def ai_input_listener():
    from machine import Pin
    reset_btn = Pin(settings.AI_RESET_BTN_PIN, Pin.IN, Pin.PULL_UP)
    while True:
        if not reset_btn.value():
            TMON_AI.error_count = 0
            await log_error('AI error count reset by user', 'ai_input_listener')
            await asyncio.sleep(1)
        await asyncio.sleep(0.1)