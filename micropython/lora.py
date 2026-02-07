# Firmware Version: v2.06.0

# CHANGED: fix NameError / empty try-block; import settings safely
def print_remote_nodes():
    try:
        import settings as _settings  # type: ignore
    except Exception:
        _settings = None
    remote_info = getattr(_settings, "REMOTE_NODE_INFO", {}) if _settings else {}
    for node_id, node_data in remote_info.items():
        print(f"[REMOTE NODE] {node_id}: {node_data}")

# Async helper to log remote nodes without blocking LoRa init
async def print_remote_nodes_async():
    try:
        print_remote_nodes()
    except Exception:
        pass

# --- All imports at the top ---
from platform_compat import (
    asyncio, time, os, gc, requests, machine, network, IS_ZERO, IS_MICROPYTHON
)  # CHANGED

# CHANGED: stdlib/micropython compatibility imports (parse-safe on both runtimes)
try:
    import sys  # type: ignore
except Exception:
    sys = None  # type: ignore
try:
    import io  # type: ignore
except Exception:
    io = None  # type: ignore
try:
    import random  # type: ignore
except Exception:
    random = None  # type: ignore
try:
    import select  # type: ignore
except Exception:
    select = None  # type: ignore

# CHANGED: ujson / ubinascii / uhashlib compatibility
try:
    import ujson as ujson  # type: ignore
except Exception:
    try:
        import json as ujson  # type: ignore
    except Exception:
        ujson = None  # type: ignore

try:
    import ubinascii as ubinascii  # type: ignore
except Exception:
    try:
        import binascii as ubinascii  # type: ignore
    except Exception:
        ubinascii = None  # type: ignore

try:
    import uhashlib as uhashlib  # type: ignore
except Exception:
    try:
        import hashlib as uhashlib  # type: ignore
    except Exception:
        uhashlib = None  # type: ignore

# CHANGED: Base64 helpers for CPython fallback
try:
    import base64 as _py_b64  # type: ignore
except Exception:
    _py_b64 = None  # type: ignore

# Sleep-ms helper used by existing code (_pulse_reset/_attempt_begin)
try:
    import utime as _time  # type: ignore
except Exception:
    try:
        import time as _time  # type: ignore
    except Exception:
        _time = None  # type: ignore

# MicroPython-only SX1262 driver
try:
    from sx1262 import SX1262
except Exception:
    try:
        from lib.sx1262 import SX1262
    except Exception:
        SX1262 = None

# CHANGED: import settings/sdata explicitly and safely
try:
    import settings  # type: ignore
except Exception:
    settings = None  # type: ignore
try:
    import sdata  # type: ignore
except Exception:
    sdata = None  # type: ignore

from utils import (
    free_pins, checkLogDirectory, debug_print, TMON_AI, safe_run, led_status_flash,
    write_lora_log, persist_unit_id, append_field_data_entry,
    stage_remote_field_data, stage_remote_files,  # CHANGED: used later in base RX path
)

from relay import toggle_relay

try:
    from encryption import chacha20_encrypt, derive_nonce
except Exception:
    chacha20_encrypt = None
    derive_nonce = None

def chacha20_decrypt(key, nonce, aad, ciphertext):
    return chacha20_encrypt(key, nonce, aad, ciphertext)

# Guarded import of optional wprest helpers to avoid ImportError
try:
    import wprest as _wp  # CHANGED
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

# File paths (safe even if settings failed to import)
_LOG_DIR = (getattr(settings, 'LOG_DIR', '/logs') if settings else '/logs')
REMOTE_NODE_INFO_FILE = _LOG_DIR + '/remote_node_info.json'
REMOTE_SYNC_SCHEDULE_FILE = _LOG_DIR + '/remote_sync_schedule.json'
GPS_STATE_FILE = _LOG_DIR + '/gps.json'

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
                _s = sdata
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
        # Update sdata mirror
        try:
            _s = sdata
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
    try:
        from lib.sx1262 import SX1262  # fallback to lib path
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

# In-memory reassembly buffers for incoming chunked messages (base-side)
_lora_incoming_chunks = {}  # unit_id -> {'total': int, 'parts': {seq: bytes}, 'ts': epoch}

# Cleanup stale chunks periodically
async def cleanup_incoming_chunks():
    while True:
        current_time = time.time()
        to_delete = []
        for uid, entry in _lora_incoming_chunks.items():
            if current_time - entry['ts'] > 3600:  # 1 hour timeout
                to_delete.append(uid)
        for uid in to_delete:
            del _lora_incoming_chunks[uid]
        gc.collect()
        await asyncio.sleep(600)  # Check every 10 minutes

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
    gc.collect()

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
                await debug_print(f"lora: setBlockingCallback fail {rc}", "ERROR")
                await log_error(f"LoRa setBlockingCallback failed: {rc}")
                await free_pins()
                lora = None
                return False
            # Double-check radio packet type is LoRa
            try:
                pkt_type = lora.getPacketType()
                if pkt_type != 1:  # assuming 1 is LORA mode, since import removed
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
            await print_remote_nodes_async()
            # Ensure base starts in RX mode to listen for remotes
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
        if status != 0:
            error_msg = f"LoRa initialization failed with status: {status}"
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
        # Ensure we deinit spi/pins when exceptional abort happens
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

# Add cooldown guard for repeated TX exceptions (ms)
_last_tx_exception_ms = 0
_TX_EXCEPTION_COOLDOWN_MS = 2500  # avoid tight re-init loops on persistent TX failures

# Remote counters for HMAC replay protection (base only)
def _load_remote_counters():
    path = getattr(settings, 'LORA_REMOTE_REMOTE_COUNTERS_FILE', settings.LOG_DIR + '/remote_ctr.json')
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

# Copy from firmware_updater for remote OTA verify
def _get_hashlib():
    try:
        return uhashlib, _ub
    except Exception:
        return uhashlib, _ub

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

async def connectLora():
    """Non-blocking LoRa routine called frequently from lora_comm_task.
    - Initializes radio once (with retry cap)
    - Remote: sends payload at interval, waits for TX_DONE briefly, then returns
    - Base: polls for RX_DONE and processes any message
    - Idle timeout: deinit after prolonged inactivity to save power
    Returns True if LoRa is initialized and usable, else False.
    """
    global lora, _last_send_ms, _last_activity_ms, _init_failures, _last_tx_exception_ms

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
    max_payload = int(getattr(settings, 'LORA_MAX_PAYLOAD', 220) or 220)  # Reduced to 220 for safety
    raw_chunk_size = 80  # Reduced to avoid CRC errors
    transient_codes = [86, 87, 89]
    shrink_codes = [-4]
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
        if _init_failures >= _MAX_INIT_FAILS:
            # Stop hammering if it keeps failing
            return False
        await debug_print("LoRa: initializing...", "LORA")
        async with pin_lock:
            ok = await init_lora()
        if not ok:
            _init_failures += 1
            return False
        _init_failures = 0
        _last_activity_ms = now

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
                    await debug_print(f"lora: RX len={len(msg_bytes if msg_bytes else b'')} err={err}", "LORA")
                    if err != 0:
                        await debug_print(f"lora: RX err={err} discarded", "LORA")
                except Exception as rexc:
                    await debug_print(f"lora: _readData exception: {rexc}", "ERROR")
                    msg_bytes = None; err = -1
                if err == 0 and msg_bytes:
                    # Capture RSSI/SNR on successful RX (update sdata for OLED)
                    try:
                        sdata.lora_SigStr = lora.getRSSI()
                        sdata.lora_snr = lora.getSNR()
                        sdata.lora_last_rx_ts = time.time()
                    except Exception:
                        pass
                    try:
                        # Normalize to text for JSON parsing (bytes -> str)
                        if isinstance(msg_bytes, (bytes, bytearray)):
                            txt = msg_bytes.decode('utf-8', 'ignore')
                        else:
                            txt = str(msg_bytes)
                        await debug_print(f"lora: RX txt={txt}", "LORA")
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
                                await debug_print(f"lora: chunk {seq}/{total} for {uid}, parts: {len(entry['parts'])}", 'LORA')
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
                                        await debug_print(f"lora: assembled for {uid}", 'LORA')
                                    finally:
                                        try:
                                            del _lora_incoming_chunks[uid]
                                        except Exception:
                                            pass
                                else:
                                    # waiting for more parts; skip persistence until complete
                                    # Was `continue` here (invalid outside loop) — return to caller instead.
                                    gc.collect()
                                    return True
                            except Exception as e:
                                await debug_print(f"lora: chunk handling error: {e}", "ERROR")
                                # Was `continue` here (invalid outside loop) — exit handler cleanly.
                                gc.collect()
                                return True

                        # Decrypt if encrypted
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
                                return True  # discard

                        # Verify HMAC if enabled
                        if settings.LORA_HMAC_ENABLED:
                            if 'sig' not in payload:
                                if settings.LORA_HMAC_REJECT_UNSIGNED:
                                    await debug_print("lora: unsigned payload rejected", "WARN")
                                    return True
                            else:
                                try:
                                    secret = getattr(settings, 'LORA_HMAC_SECRET', '').encode()
                                    ctr = payload.get('ctr', 0)
                                    mac_src = b"|".join([
                                        secret,
                                        str(payload.get('unit_id', '')).encode(),
                                        str(payload.get('ts', '')).encode(),
                                        str(ctr).encode()
                                    ])
                                    import uhashlib
                                    h = uhashlib.sha256(mac_src)
                                    import ubinascii
                                    expected = ubinascii.hexlify(h.digest())[:32].decode()
                                    if expected != payload['sig']:
                                        await debug_print("lora: invalid signature", "ERROR")
                                        return True
                                    # Replay protect
                                    if settings.LORA_HMAC_REPLAY_PROTECT:
                                        ctrs = _load_remote_counters()
                                        uid = str(payload.get('unit_id', ''))
                                        last = ctrs.get(uid, 0)
                                        if ctr <= last:
                                            await debug_print("lora: replay detected", "ERROR")
                                            return True
                                        ctrs[uid] = ctr
                                        _save_remote_counters(ctrs)
                                    # Clean up
                                    del payload['sig']
                                    del payload['ctr']
                                except Exception as ve:
                                    await debug_print(f"lora: hmac verify failed: {ve}", "ERROR")
                                    return True

                        uid = payload.get('unit_id', '')
                        # existing processing logic: persist record etc.
                        if 'data' in payload and isinstance(payload['data'], list):
                            stage_remote_field_data(uid, payload['data'])
                        elif 'files' in payload and isinstance(payload['files'], dict):
                            stage_remote_files(uid, payload['files'])
                        else:
                            # Single record fallback
                            record = {'timestamp': int(time.time()),
                                      'remote_timestamp': payload.get('ts'),
                                      'cur_temp_f': payload.get('t_f'),
                                      'cur_temp_c': payload.get('t_c'),
                                      'cur_humid': payload.get('hum'),
                                      'cur_bar_pres': payload.get('bar'),
                                      'sys_voltage': payload.get('v'),
                                      'free_mem': payload.get('fm'),
                                      'remote_unit_id': uid,
                                      'node_type': 'remote',
                                      'source': 'remote'
                                      }
                            # Persist to field data log so base later uploads remote telemetry via WPREST
                            try:
                                append_field_data_entry(record)
                                await debug_print("persisted remote data to field log", 'LORA')
                            except Exception as e:
                                await debug_print(f"lora: failed to persist remote line: {e}", "ERROR")
                            write_lora_log(f"Base received remote payload: {str(record)[:160]}", 'INFO')
                        # update in-memory remote info and write file
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
                                # If remote sent staged settings, persist to per-unit staged file for later apply/inspection
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
                        # Check for OTA jobs for this remote
                        ack = {'ack': 'ok'}
                        try:
                            jobs = await poll_ota_jobs()
                            ota_sent = False
                            for job in jobs:
                                if job.get('target') == uid and job.get('type') == 'firmware_update':
                                    from firmware_updater import download_and_apply_firmware
                                    dl = download_and_apply_firmware(job.get('url'), job.get('version'), expected_sha=job.get('sha'), manifest_url=job.get('manifest_url'))
                                    if dl['ok']:
                                        ota_sent = True
                                        ack['ota_pending'] = True
                                        ack['ota_filename'] = os.path.basename(dl['path'])
                                        ack['ota_sha'] = dl['sha256']
                                        # Send file after ACK
                                        await send_ota_file_to_remote(uid, dl['path'], dl['sha256'])
                                        break
                        except Exception:
                            pass
                        # Best-effort: ACK back to remote with next sync and optional GPS
                        try:
                            # schedule next_in seconds (base chooses cadence)
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
                                    sdata.lora_last_tx_ts = time.time()
                                except Exception:
                                    # try a more direct sequence if the driver has explicit tx API
                                    try:
                                        lora.setOperatingMode(lora.MODE_TX)
                                        lora.send(ujson.dumps(ack).encode('utf-8'))
                                        lora.setOperatingMode(lora.MODE_RX)
                                        sdata.lora_last_tx_ts = time.time()
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        except Exception:
                            pass
                    except Exception as e:
                        await debug_print(f"lora: processing RX failed: {e}", "ERROR")
            gc.collect()
        except Exception as e:
            await debug_print(f"lora: base RX loop exception: {e}", "ERROR")
            gc.collect()

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

                # Disable encryption to avoid chunking for debugging
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

                # NEW: only chunk if data actually exceeds safe payload size
                max_payload = int(getattr(settings, 'LORA_MAX_PAYLOAD', 220) or 220)  # Reduced for safety

                # Quick single-frame send when payload fits — avoids tiny chunk floods for modest payloads
                if len(data) <= max_payload:
                    # Ensure radio present
                    if lora is None:
                        await debug_print("lora: reinit before single-frame send", "LORA")
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
                        # Wait for ACK
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
                                    msg2 = None; err2 = -1
                                if err2 == 0 and msg2:
                                    try:
                                        obj2 = None
                                        txt2 = msg2.decode('utf-8', 'ignore') if isinstance(msg2, (bytes, bytearray)) else str(msg2)
                                        try:
                                            obj2 = ujson.loads(txt2)
                                        except Exception:
                                            obj2 = None
                                        if isinstance(obj2, dict) and obj2.get('ack') == 'ok':
                                            ack_received = True
                                            # Capture signal info
                                            try:
                                                if hasattr(lora, 'getRSSI'):
                                                    sdata.lora_SigStr = lora.getRSSI()
                                                    sdata.lora_last_rx_ts = time.time()
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
                                            # Adopt GPS
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
                                            await debug_print(f"lora: next {getattr(settings, 'nextLoraSync', '')}", 'LORA')
                                            write_lora_log(f"Remote stored next sync epoch: {getattr(settings, 'nextLoraSync', '')}", 'INFO')
                                            led_status_flash('SUCCESS')
                                            # Check for ota_pending
                                            if obj2.get('ota_pending'):
                                                ota_filename = obj2.get('ota_filename')
                                                ota_sha = obj2.get('ota_sha')
                                                ota_chunks = {}
                                                ota_ts = time.time()
                                                while time.time() - ota_ts < 3600:
                                                    ev2 = lora._events()
                                                    if RX_DONE_FLAG and (ev2 & RX_DONE_FLAG):
                                                        msg2, err2 = lora._readData(0)
                                                        if err2 == 0 and msg2:
                                                            txt2 = msg2.decode('utf-8', 'ignore')
                                                            chunk_payload = ujson.loads(txt2)
                                                            if chunk_payload.get('ota_file'):
                                                                seq = chunk_payload.get('seq')
                                                                total = chunk_payload.get('total')
                                                                b64 = chunk_payload.get('b64')
                                                                raw_chunk = _ub.a2b_base64(b64)
                                                                ota_chunks[seq] = raw_chunk
                                                                if len(ota_chunks) == total:
                                                                    assembled = b''.join(ota_chunks[i] for i in range(1, total+1))
                                                                    computed_sha = compute_sha256_from_bytes(assembled)
                                                                    if computed_sha == ota_sha:
                                                                        path = '/ota/backup/' + ota_filename
                                                                        with open(path, 'wb') as f:
                                                                            f.write(assembled)
                                                                        # Set pending flag
                                                                        with open(settings.OTA_PENDING_FILE, 'w') as f:
                                                                            f.write('pending')
                                                                        machine.reset()
                                                                        break
                                                    break
                                                except Exception:
                                                    pass
                                            break
                                    except Exception:
                                        pass
                                await asyncio.sleep(0.01)
                            if not ack_received:
                                fallback = 300 + random.randint(-30, 30)
                                if fallback < 60: fallback = 60
                                settings.nextLoraSync = int(time.time() + fallback)
                                write_lora_log(f"Remote no ACK, fallback next sync in {fallback} sec", 'INFO')
                            gc.collect()
                            return True

                    # If we reached here, single-frame failed after retries: treat as re-init trigger
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

                # Tunables
                min_raw = int(getattr(settings, 'LORA_CHUNK_MIN_RAW_BYTES', 12))
                max_parts_allowed = int(getattr(settings, 'LORA_CHUNK_MAX_PARTS', 8))
                # Build a minimal template to estimate JSON overhead accurately
                try:
                    tmpl = {'unit_id': getattr(settings, 'UNIT_ID', ''), 'chunked': 1, 'seq': 999, 'total': 999, 'b64': ''}
                    overhead = len(ujson.dumps(tmpl).encode('utf-8')) + 20  # safety margin
                    avail_b64 = max_payload - overhead
                    raw_chunk_size = max(min_raw, int((avail_b64 * 3) // 4)) if avail_b64 > 0 else min_raw
                except Exception:
                    # Fallback conservative size
                    raw_chunk_size = max(min_raw, int(getattr(settings, 'LORA_CHUNK_RAW_BYTES', 80)))

                # Helper to compact payload to minimal telemetry shapes
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

                # Adaptive send with shrink attempts and per-chunk retries
                max_shrinks = 4
                shrink_attempt = 0
                sent_ok = False
                max_shrink_retries = int(getattr(settings, 'LORA_CHUNK_MAX_RETRIES', 3))
                jitter_base = 0.02

                # If payload already larger than a reasonable size, attempt compaction up-front
                while shrink_attempt < max_shrinks and not sent_ok:
                    parts = [data[i:i+raw_chunk_size] for i in range(0, len(data), raw_chunk_size)]
                    total = len(parts)

                    # If message would create too many parts, try compressing payload to a minimal form
                    if total > max_parts_allowed:
                        await debug_print(f"lora: large split {total} parts > max {max_parts_allowed}, attempting compact payload", "LORA")
                        # try minimal telemetry
                        compacted = _compact_payload_to_minimal(payload)
                        if len(compacted) < len(data):
                            data = compacted
                            parts = [data[i:i+raw_chunk_size] for i in range(0, len(data), raw_chunk_size)]
                            total = len(parts)
                        # still too many parts? try ultra-compact (unit_id + ts)
                        if total > max_parts_allowed:
                            tiny = ujson.dumps({'unit_id': getattr(settings, 'UNIT_ID', ''), 'ts': payload.get('ts')}).encode('utf-8')
                            data = tiny
                            parts = [data[i:i+raw_chunk_size] for i in range(0, len(data), raw_chunk_size)]
                            total = len(parts)
                        # if still too many parts, abort
                        if total > max_parts_allowed:
                            await debug_print(f"lora: aborting chunk send, required parts {total} exceeds limit {max_parts_allowed}", "ERROR")
                            write_lora_log(f"Remote chunk send aborted: {total} parts exceeds max {max_parts_allowed}", 'ERROR')
                            gc.collect()
                            return False

                        # NEW: After compaction, if the payload now fits a single frame, try that first
                        if len(data) <= max_payload:
                            await debug_print("lora: compaction produced single-frame payload; attempting single-frame send", "LORA")
                            # Ensure radio present
                            if lora is None:
                                await debug_print("lora: reinit before single-frame send (post-compact)", "LORA")
                                async with pin_lock:
                                    ok_init = await init_lora()
                                if not ok_init:
                                    await debug_print("lora: post-compact re-init failed, aborting", "ERROR")
                                    return False
                            try:
                                resp = lora.send(data)
                            except Exception as send_exc:
                                await debug_print(f"lora: single-frame send() (post-compact) raised: {send_exc}", 'ERROR')
                                resp = -999
                            # normalize
                            st_code = None
                            try:
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
                            except Exception:
                                st_code = -999
                            if st_code == 0:
                                await debug_print("lora: single-frame send (post-compact) succeeded", "LORA")
                                _last_send_ms = time.ticks_ms()
                                _last_activity_ms = _last_send_ms
                                # Wait for TX_DONE and ACK
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
                                # Wait for ACK
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
                                            msg2 = None; err2 = -1
                                        if err2 == 0 and msg2:
                                            try:
                                                obj2 = None
                                                txt2 = msg2.decode('utf-8', 'ignore') if isinstance(msg2, (bytes, bytearray)) else str(msg2)
                                                try:
                                                    obj2 = ujson.loads(txt2)
                                                except Exception:
                                                    obj2 = None
                                                if isinstance(obj2, dict) and obj2.get('ack') == 'ok':
                                                    ack_received = True
                                                    # Capture signal info for display
                                                    try:
                                                        if hasattr(lora, 'getRSSI'):
                                                            sdata.lora_SigStr = lora.getRSSI()
                                                            sdata.lora_last_rx_ts = time.time()
                                                        if hasattr(lora, 'getSNR'):
                                                            sdata.lora_snr = lora.getSNR()
                                                            sdata.last_message = ujson.dumps(obj2)[:32]
                                                    except Exception:
                                                        pass
                                                    # Adopt next sync if provided
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
                                                    await debug_print(f"lora: next {getattr(settings, 'nextLoraSync', '')}", 'LORA')
                                                    write_lora_log(f"Remote stored next sync epoch: {getattr(settings, 'nextLoraSync', '')}", 'INFO')
                                                    led_status_flash('SUCCESS')
                                                    # Check for ota_pending
                                                    if obj2.get('ota_pending'):
                                                        ota_filename = obj2.get('ota_filename')
                                                        ota_sha = obj2.get('ota_sha')
                                                        ota_chunks = {}
                                                        ota_ts = time.time()
                                                        while time.time() - ota_ts < 3600:
                                                            ev2 = lora._events()
                                                            if RX_DONE_FLAG and (ev2 & RX_DONE_FLAG):
                                                                msg2, err2 = lora._readData(0)
                                                                if err2 == 0 and msg2:
                                                                    txt2 = msg2.decode('utf-8', 'ignore')
                                                                    chunk_payload = ujson.loads(txt2)
                                                                    if chunk_payload.get('ota_file'):
                                                                        seq = chunk_payload.get('seq')
                                                                        total = chunk_payload.get('total')
                                                                        b64 = chunk_payload.get('b64')
                                                                        raw_chunk = _ub.a2b_base64(b64)
                                                                        ota_chunks[seq] = raw_chunk
                                                                        if len(ota_chunks) == total:
                                                                            assembled = b''.join(ota_chunks[i] for i in range(1, total+1))
                                                                            computed_sha = compute_sha256_from_bytes(assembled)
                                                                            if computed_sha == ota_sha:
                                                                                path = '/ota/backup/' + ota_filename
                                                                                with open(path, 'wb') as f:
                                                                                    f.write(assembled)
                                                                                # Set pending flag
                                                                                with open(settings.OTA_PENDING_FILE, 'w') as f:
                                                                                    f.write('pending')
                                                                                machine.reset()
                                                                                break
                                                    break
                                                except Exception:
                                                    pass
                                            await asyncio.sleep(0.01)
                                        if not ack_received:
                                            fallback = 300 + random.randint(-30, 30)
                                            if fallback < 60: fallback = 60
                                            settings.nextLoraSync = int(time.time() + fallback)
                                            write_lora_log(f"Remote no ACK, fallback next sync in {fallback} sec", 'INFO')
                                    gc.collect()
                                    return True
                            else:
                                await debug_print(f"lora: single-frame (post-compact) failed: {st_code}", "WARN")
                                # If it's a negative hardware-like code, attempt guarded re-init and fall through to chunk flow
                                if st_code < 0:
                                    await debug_print("lora: negative code on single-frame post-compact; reinit attempt", "LORA")
                                    async with pin_lock:
                                        ok_init = await init_lora()
                                    if not ok_init:
                                        await debug_print("lora: post-compact re-init failed, aborting", "ERROR")
                                        return False
                                    # re-check radio and continue into chunk attempts after short backoff
                                    await asyncio.sleep(0.08)

                    for idx, chunk in enumerate(parts, start=1):
                        await debug_print(f"lora: sending chunk {idx}/{total}", "LORA")
                        attempt = 0
                        chunk_sent = False
                        while attempt < max_shrink_retries and not chunk_sent:
                            try:
                                # Ensure radio is present — re-init on demand
                                if lora is None:
                                    await debug_print("lora: SPI/radio missing before chunk send, attempting re-init", "LORA")
                                    async with pin_lock:
                                        ok = await init_lora()
                                    if not ok or lora is None:
                                        await debug_print("lora: re-init failed, aborting chunk send", "ERROR")
                                        part_failure = True
                                        break

                                # Ensure radio not busy and set TX mode
                                try:
                                    busy_start = time.ticks_ms()
                                    # wait up to 800ms for not-busy
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

                                # Normalize status
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

                                # Log the raw response for diagnostics when non-zero
                                if st_code != 0:
                                    await debug_print(f"lora: raw send resp={resp} normalized_code={st_code} (part {idx}/{total})", "LORA")

                                if st_code == 0:
                                    # Wait for TX_DONE after successful send
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
                                    # small spacing between chunks
                                    await asyncio.sleep(jitter_base + random.random() * jitter_base)
                                    break

                                # NEW: negative/stub codes likely indicate radio/hardware issue — attempt guarded re-init once
                                if st_code is not None and st_code < 0:
                                    await debug_print(f"lora: negative chunk send code {st_code} — attempting guarded re-init", "LORA")
                                    async with pin_lock:
                                        ok = await init_lora()
                                    if ok and lora is not None:
                                        await debug_print("lora: re-init succeeded, retrying chunk send", "LORA")
                                        # do not advance shrink/shrink_attempt here; retry chunk attempts
                                        attempt += 1
                                        await asyncio.sleep(0.06)
                                        continue
                                    else:
                                        await debug_print("lora: re-init after negative code failed, aborting", "ERROR")
                                        part_failure = True
                                        break

                                # Decide action: shrink only on explicit shrink codes; otherwise treat some codes as transient retry
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

                                # Unknown non-zero codes: treat as transient but log prominently and retry once
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
                    # If part_failure -> shrink raw_chunk and retry (bounded)
                    if part_failure:
                        shrink_attempt += 1
                        new_raw = max(min_raw, raw_chunk_size // 2)
                        if new_raw == raw_chunk_size:
                            # cannot shrink more — try single-frame as last resort if fits
                            if len(data) <= max_payload:
                                await debug_print("lora: cannot shrink but data fits single-frame; attempting single-frame send (last-resort)", "LORA")
                                # try single-frame send with guarded re-init
                                if lora is None:
                                    async with pin_lock:
                                        ok = await init_lora()
                                    if not ok:
                                        await debug_print("lora: re-init failed for last-resort single-frame send", "ERROR")
                                        break
                                try:
                                    resp = lora.send(data)
                                except Exception as se:
                                    await debug_print(f"lora: last-resort single-frame send error: {se}", "ERROR")
                                    resp = -999
                                # Normalize and evaluate
                                try:
                                    if isinstance(resp, (tuple, list)) and len(resp) >= 2 and isinstance(resp[1], int):
                                        st_last = resp[1]
                                    elif isinstance(resp, int):
                                        st_last = resp
                                    else:
                                        try:
                                            st_last = int(resp[0]) if isinstance(resp, (tuple, list)) else int(resp)
                                        except Exception:
                                            st_last = -999
                                except Exception:
                                    st_last = -999
                                if st_last == 0:
                                    await debug_print("lora: last-resort single-frame succeeded", "LORA")
                                    _last_send_ms = time.ticks_ms()
                                    _last_activity_ms = _last_send_ms
                                    # Wait for TX_DONE and ACK
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
                                    # Wait for ACK
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
                                                msg2 = None; err2 = -1
                                            if err2 == 0 and msg2:
                                                try:
                                                    obj2 = None
                                                    txt2 = msg2.decode('utf-8', 'ignore') if isinstance(msg2, (bytes, bytearray)) else str(msg2)
                                                    try:
                                                        obj2 = ujson.loads(txt2)
                                                    except Exception:
                                                        obj2 = None
                                                    if isinstance(obj2, dict) and obj2.get('ack') == 'ok':
                                                        ack_received = True
                                                        # Capture signal info for display
                                                        try:
                                                            if hasattr(lora, 'getRSSI'):
                                                                sdata.lora_SigStr = lora.getRSSI()
                                                                sdata.lora_last_rx_ts = time.time()
                                                            if hasattr(lora, 'getSNR'):
                                                                sdata.lora_snr = lora.getSNR()
                                                                sdata.last_message = ujson.dumps(obj2)[:32]
                                                        except Exception:
                                                            pass
                                                        # Adopt next sync if provided
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
                                                        await debug_print(f"lora: next {getattr(settings, 'nextLoraSync', '')}", 'LORA')
                                                        write_lora_log(f"Remote stored next sync epoch: {getattr(settings, 'nextLoraSync', '')}", 'INFO')
                                                        led_status_flash('SUCCESS')
                                                        # Check for ota_pending
                                                        if obj2.get('ota_pending'):
                                                            ota_filename = obj2.get('ota_filename')
                                                            ota_sha = obj2.get('ota_sha')
                                                            ota_chunks = {}
                                                            ota_ts = time.time()
                                                            while time.time() - ota_ts < 3600:
                                                                ev2 = lora._events()
                                                                if RX_DONE_FLAG and (ev2 & RX_DONE_FLAG):
                                                                    msg2, err2 = lora._readData(0)
                                                                    if err2 == 0 and msg2:
                                                                        txt2 = msg2.decode('utf-8', 'ignore')
                                                                        chunk_payload = ujson.loads(txt2)
                                                                        if chunk_payload.get('ota_file'):
                                                                            seq = chunk_payload.get('seq')
                                                                            total = chunk_payload.get('total')
                                                                            b64 = chunk_payload.get('b64')
                                                                            raw_chunk = _ub.a2b_base64(b64)
                                                                            ota_chunks[seq] = raw_chunk
                                                                            if len(ota_chunks) == total:
                                                                                assembled = b''.join(ota_chunks[i] for i in range(1, total+1))
                                                                                computed_sha = compute_sha256_from_bytes(assembled)
                                                                                if computed_sha == ota_sha:
                                                                                    path = '/ota/backup/' + ota_filename
                                                                                    with open(path, 'wb') as f:
                                                                                        f.write(assembled)
                                                                                    # Set pending flag
                                                                                    with open(settings.OTA_PENDING_FILE, 'w') as f:
                                                                                        f.write('pending')
                                                                                    machine.reset()
                                                                                    break
                                                    break
                                                except Exception:
                                                    pass
                                            await asyncio.sleep(0.01)
                                        if not ack_received:
                                            fallback = 300 + random.randint(-30, 30)
                                            if fallback < 60: fallback = 60
                                            settings.nextLoraSync = int(time.time() + fallback)
                                            write_lora_log(f"Remote no ACK, fallback next sync in {fallback} sec", 'INFO')
                                    gc.collect()
                                    return True
                            # If we reached here, chunked send failed after retries: treat as re-init trigger
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

                # After sending all chunks, switch to RX and wait for ACK
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
                            msg2 = None; err2 = -1
                        if err2 == 0 and msg2:
                            try:
                                obj2 = None
                                txt2 = msg2.decode('utf-8', 'ignore') if isinstance(msg2, (bytes, bytearray)) else str(msg2)
                                try:
                                    obj2 = ujson.loads(txt2)
                                except Exception:
                                    obj2 = None
                                if isinstance(obj2, dict) and obj2.get('ack') == 'ok':
                                    ack_received = True
                                    # Capture signal info for display
                                    try:
                                        if hasattr(lora, 'getRSSI'):
                                            sdata.lora_SigStr = lora.getRSSI()
                                            sdata.lora_last_rx_ts = time.time()
                                        if hasattr(lora, 'getSNR'):
                                            sdata.lora_snr = lora.getSNR()
                                            sdata.last_message = ujson.dumps(obj2)[:32]
                                    except Exception:
                                        pass
                                    # Adopt next sync if provided
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
                                    await debug_print(f"lora: next {getattr(settings, 'nextLoraSync', '')}", 'LORA')
                                    write_lora_log(f"Remote stored next sync epoch: {getattr(settings, 'nextLoraSync', '')}", 'INFO')
                                    led_status_flash('SUCCESS')
                                    # Check for ota_pending
                                    if obj2.get('ota_pending'):
                                        ota_filename = obj2.get('ota_filename')
                                        ota_sha = obj2.get('ota_sha')
                                        ota_chunks = {}
                                        ota_ts = time.time()
                                        while time.time() - ota_ts < 3600:
                                            ev2 = lora._events()
                                            if RX_DONE_FLAG and (ev2 & RX_DONE_FLAG):
                                                msg2, err2 = lora._readData(0)
                                                if err2 == 0 and msg2:
                                                    txt2 = msg2.decode('utf-8', 'ignore')
                                                    chunk_payload = ujson.loads(txt2)
                                                    if chunk_payload.get('ota_file'):
                                                        seq = chunk_payload.get('seq')
                                                        total = chunk_payload.get('total')
                                                        b64 = chunk_payload.get('b64')
                                                        raw_chunk = _ub.a2b_base64(b64)
                                                        ota_chunks[seq] = raw_chunk
                                                        if len(ota_chunks) == total:
                                                            assembled = b''.join(ota_chunks[i] for i in range(1, total+1))
                                                            computed_sha = compute_sha256_from_bytes(assembled)
                                                            if computed_sha == ota_sha:
                                                                path = '/ota/backup/' + ota_filename
                                                                with open(path, 'wb') as f:
                                                                    f.write(assembled)
                                                                # Set pending flag
                                                                with open(settings.OTA_PENDING_FILE, 'w') as f:
                                                                    f.write('pending')
                                                                machine.reset()
                                                                break
                                                    break
                                                except Exception:
                                                    pass
                                            await asyncio.sleep(0.01)
                                        if not ack_received:
                                            fallback = 300 + random.randint(-30, 30)
                                            if fallback < 60: fallback = 60
                                            settings.nextLoraSync = int(time.time() + fallback)
                                            write_lora_log(f"Remote no ACK, fallback next sync in {fallback} sec", 'INFO')
                                    gc.collect()
                                    return True
                            # If we reached here, chunked send failed after retries: treat as re-init trigger
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

                # After sending all chunks, done for this cycle
                _last_send_ms = time.ticks_ms()
                _last_activity_ms = _last_send_ms
                gc.collect()
                return True

            except Exception as e:
                # Unified exception handling for remote TX
                # Special-case UnboundLocalError / "local variable referenced before assignment"
                try:
                    is_ule = isinstance(e, UnboundLocalError) or ('local variable referenced before assignment' in str(e).lower())
                except Exception:
                    is_ule = False
                if is_ule:
                    await debug_print("Remote TX encountered UnboundLocalError; aborting send and scheduling radio re-init", "ERROR")
                    await log_error(f"Remote TX UnboundLocalError: {e}")
                    # Force cooldown and clean hardware to avoid tight repeat attempts
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
                    # Return False to let the caller perform an orderly retry/reinit
                    return False

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
                    ls = {k: (str(v)[:160] if v is not None else None) for k, v in locals().items() if k in ('lora','state','resp','msg2','tx_start')}
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
                gc.collect()
                return False
    gc.collect()
    return True

# OTA file sending from base to remote
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
                # Send chunk via LoRa
                lora.send(ujson.dumps(chunk_msg).encode('utf-8'))
                # Wait for TX_DONE
                tx_start = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), tx_start) < 10000:
                    ev = lora._events()
                    if TX_DONE_FLAG and (ev & TX_DONE_FLAG):
                        break
                    await asyncio.sleep(0.01)
                await asyncio.sleep(0.1)  # small delay between chunks
                seq += 1
                chunk = f.read(raw_chunk_size)
        return True
    except Exception as e:
        await debug_print(f"Failed to send OTA file: {e}", "ERROR")
        return False
    gc.collect()

# NEW: remote send helpers for field data batch and state files
async def send_remote_field_data_batch(payload):
    """Send field data batch to base over LoRa, with chunking if needed."""
    try:
        data = ujson.dumps(payload).encode('utf-8')
        return await send_lora_payload(data, confirm=True)
    except Exception as e:
        await debug_print(f"send_remote_field_data_batch error: {e}", "ERROR")
        return False
    gc.collect()

async def send_remote_state_files(files):
    """Send state files to base over LoRa, with chunking if needed."""
    try:
        # Convert bytes to str if needed (py files are text)
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
    """Send data_bytes over LoRa, chunk if large, wait for confirm ACK if requested."""
    try:
        if lora is None:
            return False
        max_payload = int(getattr(settings, 'LORA_MAX_PAYLOAD', 220))
        raw_chunk_size = 80
        if len(data_bytes) <= max_payload:
            # Single frame
            lora.setOperatingMode(lora.MODE_TX)
            resp = lora.send(data_bytes)
            st_code = 0 if resp == 0 else -1  # Simplified
            if st_code != 0:
                return False
            # Wait TX_DONE
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
            # Chunked
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
                # Wait TX_DONE
                tx_start = time.ticks_ms()
                while time.ticks_diff(time.ticks_ms(), tx_start) < 10000:
                    ev = lora._events()
                    if TX_DONE_FLAG and (ev & TX_DONE_FLAG):
                        break
                    await asyncio.sleep(0.01)
                await asyncio.sleep(0.1)  # Delay between chunks
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
