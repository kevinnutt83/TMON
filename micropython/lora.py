# TMON v2.01.6 - BULLETPROOF LoRa (FULLY REFACTORED + uasyncio COMPATIBLE + MULTI-NODE FIXES)
# CRITICAL FIXES APPLIED IN THIS UPDATE (v2.01.6):
# • FULL BURST COMPLETION DETECTION: processing/ACK now triggers ONLY after ALL types (TS + SETTINGS + SDATA) are assembled OR timeout
#   (fixes the exact issue: base was sending premature ACK after SETTINGS completed → remote stopped sending SDATA → transmission halted right before completion)
# • PERSISTENT REMOTE NODE INFO: now keeps next_expected / missed_syncs / COMPANY / MACHINE_ID across bursts (previous unconditional del lost scheduling)
# • TS metadata update uses .update() instead of overwriting the entire dict (prevents loss of persistent keys)
# • Cleanup now safely pops only temporary burst keys (types/data/chunks/last_rx)
# • All previous bulletproof fixes preserved (immediate assembly logging, multi-node UID filtering, short listen windows, etc.)

import ujson
import os
import uasyncio as asyncio
import random
import ubinascii as _ub
import gc
try:
    import utime as time
except ImportError:
    import time
try:
    import machine
    import sys
except ImportError:
    machine = None
    sys = None
try:
    import _thread
except Exception:
    _thread = None
try:
    import threading
except Exception:
    threading = None
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

from utils import free_pins, debug_print, TMON_AI, stage_remote_field_data, stage_remote_files, record_field_data, get_machine_id, persist_custom_settings
from relay import toggle_relay
from sampling import findLowestTemp, findHighestTemp, findLowestBar, findHighestBar, findLowestHumid, findHighestHumid
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
    send_ota_job_status = getattr(_wp, 'send_ota_job_status', None)
    poll_device_commands = getattr(_wp, 'poll_device_commands', None)
except Exception:
    register_with_wp = send_data_to_wp = send_settings_to_wp = fetch_settings_from_wp = None
    send_file_to_wp = request_file_from_wp = heartbeat_ping = poll_ota_jobs = poll_device_commands = None
    send_ota_job_status = None

import uhashlib
try:
    import hmac
except ImportError:
    def hmac_sha256(key, msg):
        BLOCK_SIZE = 64
        if len(key) > BLOCK_SIZE:
            key = uhashlib.sha256(key).digest()
        key += b'\x00' * (BLOCK_SIZE - len(key))
        opad = bytes((x ^ 0x5C) for x in key)
        ipad = bytes((x ^ 0x36) for x in key)
        inner = uhashlib.sha256(ipad + msg).digest()
        return uhashlib.sha256(opad + inner).digest()
else:
    def hmac_sha256(key, msg):
        return hmac.new(key, msg, uhashlib.sha256).digest()

from itertools import cycle
def xor_bytes(a, b):
    return bytes(x ^ y for x, y in zip(a, cycle(b)))


def crc16_ccitt(data, poly=0x1021, init=0xFFFF):
    crc = init
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _format_crc(crc):
    return f"{crc:04X}"


def _extract_lora_network_fields(msg_str):
    net = None
    password = None
    try:
        for part in str(msg_str).split(','):
            if part.startswith('NET:'):
                net = part[4:]
            elif part.startswith('PASS:'):
                password = part[5:]
    except Exception:
        pass
    return net, password


def _base_network_matches(msg_str, strict=False):
    expected_name = str(getattr(settings, 'LORA_NETWORK_NAME', '') or '').strip()
    expected_pass = str(getattr(settings, 'LORA_NETWORK_PASSWORD', '') or '').strip()
    if not expected_name and not expected_pass:
        return True
    net_name, net_pass = _extract_lora_network_fields(msg_str)
    # Some frame types (e.g., chunked TYPE frames) do not carry NET/PASS inline.
    # In non-strict mode we allow these frames and rely on LoRa HMAC/auth.
    if not strict and net_name is None and net_pass is None:
        return True
    if expected_name and net_name != expected_name:
        return False
    if expected_pass and net_pass != expected_pass:
        return False
    return True

# ===================== MICROPYTHON-COMPATIBLE QUEUE =====================
class SimpleQueue:
    def __init__(self, maxsize=10):
        self.maxsize = maxsize
        self._queue = []
        self._event = asyncio.Event()

    async def put(self, item):
        while len(self._queue) >= self.maxsize:
            await asyncio.sleep_ms(10)
        self._queue.append(item)
        self._event.set()

    async def get(self):
        while not self._queue:
            await self._event.wait()
            self._event.clear()
        return self._queue.pop(0)

    def task_done(self):
        pass

file_lock = asyncio.Lock()
pin_lock = asyncio.Lock()
lora = None
last_lora_error_ts = 0
proxy_last_ts = {}
last_rx_ts = 0
last_lora_activity_ts = 0
lora_rx_queue = SimpleQueue(maxsize=10)

tx_counter = 0
remote_counters = {}
_lora_ota_cache = {'version': None, 'files': None}
_remote_lora_ota_jobs = {}
_remote_ota_rx = {
    'chunks': {},
    'session': None,
    'version': None,
    'files': {},
    'received': {},
}


def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return int(default)


def _version_key(ver):
    try:
        s = str(ver or '').strip().lower()
        if s.startswith('v'):
            s = s[1:]
        nums = []
        token = ''
        for ch in s:
            if ch.isdigit():
                token += ch
            else:
                if token:
                    nums.append(int(token))
                    token = ''
        if token:
            nums.append(int(token))
        while len(nums) < 3:
            nums.append(0)
        return tuple(nums[:4])
    except Exception:
        return (0, 0, 0, 0)


def _is_newer_version(remote_ver, local_ver):
    try:
        return _version_key(str(local_ver or '')) > _version_key(str(remote_ver or ''))
    except Exception:
        return False


def _sha256_hex(data):
    try:
        h = uhashlib.sha256()
        h.update(data)
        return _ub.hexlify(h.digest()).decode().lower()
    except Exception:
        return ''


def _read_local_firmware_files():
    """Read local firmware files for LoRa OTA push and return metadata list."""
    base_ver = str(getattr(settings, 'FIRMWARE_VERSION', '') or '').strip()
    if _lora_ota_cache.get('version') == base_ver and isinstance(_lora_ota_cache.get('files'), list):
        return _lora_ota_cache.get('files')

    allow = getattr(settings, 'OTA_FILES_ALLOWLIST', []) or []
    files = []
    for rel in allow:
        name = str(rel or '').strip()
        if not name:
            continue
        raw = None
        candidates = [
            name,
            './' + name,
            '/workspaces/TMON/micropython/' + name,
        ]
        for fp in candidates:
            try:
                with open(fp, 'rb') as rf:
                    raw = rf.read()
                if raw is not None:
                    break
            except Exception:
                raw = None
        if raw is None:
            continue
        files.append({
            'name': name,
            'sha256': _sha256_hex(raw),
            'data_b64': _ub.b2a_base64(raw).rstrip(b'\n').decode(),
        })

    _lora_ota_cache['version'] = base_ver
    _lora_ota_cache['files'] = files
    return files


def _stage_remote_lora_ota_job(remote_uid, remote_ver):
    """Prepare a LoRa OTA push job when base firmware is newer than remote."""
    if str(getattr(settings, 'NODE_TYPE', 'base')).lower() != 'base':
        return None
    if not bool(getattr(settings, 'ENABLE_LORA_OTA', True)):
        return None
    base_ver = str(getattr(settings, 'FIRMWARE_VERSION', '') or '').strip()
    if not base_ver or not _is_newer_version(remote_ver, base_ver):
        return None

    files = _read_local_firmware_files()
    if not files:
        return None

    sess = f"{remote_uid}:{int(time.time())}"
    _remote_lora_ota_jobs[str(remote_uid)] = {
        'session': sess,
        'version': base_ver,
        'remote_version': str(remote_ver or ''),
        'files': files,
        'sent': False,
    }
    return sess


async def _send_lora_ota_job(remote_uid):
    """Send staged LoRa OTA package to a specific remote using chunked TYPE frames."""
    uid = str(remote_uid or '')
    job = _remote_lora_ota_jobs.get(uid)
    if not isinstance(job, dict) or job.get('sent'):
        return False

    files = job.get('files') or []
    if not files:
        return False

    session = str(job.get('session') or '')
    version = str(job.get('version') or '')
    retries = max(1, _safe_int(getattr(settings, 'LORA_OTA_MAX_RETRIES', 3), 3))
    chunk_len = max(96, _safe_int(getattr(settings, 'LORA_OTA_CHUNK_SIZE', 180), 180))

    meta = {
        'session': session,
        'version': version,
        'count': len(files),
        'files': [{'name': f.get('name'), 'sha256': f.get('sha256')} for f in files],
    }
    meta_b64 = _ub.b2a_base64(ujson.dumps(meta).encode()).rstrip(b'\n').decode()
    await _send_chunked('LORA_OTA_META', meta_b64, target_uid=uid, chunk_len=chunk_len)
    await asyncio.sleep(0.3)

    for f in files:
        payload = {
            'session': session,
            'version': version,
            'name': f.get('name'),
            'sha256': f.get('sha256'),
            'data_b64': f.get('data_b64'),
        }
        payload_b64 = _ub.b2a_base64(ujson.dumps(payload).encode()).rstrip(b'\n').decode()

        sent_ok = False
        for _ in range(retries):
            try:
                await _send_chunked('LORA_OTA_FILE', payload_b64, target_uid=uid, chunk_len=chunk_len)
                sent_ok = True
                break
            except Exception:
                await asyncio.sleep(0.5)
        if not sent_ok:
            await log_error(f'lora ota send failed file={f.get("name")} uid={uid}')
            return False
        await asyncio.sleep(0.25)

    apply_msg = {
        'session': session,
        'version': version,
        'count': len(files),
    }
    apply_b64 = _ub.b2a_base64(ujson.dumps(apply_msg).encode()).rstrip(b'\n').decode()
    await _send_chunked('LORA_OTA_APPLY', apply_b64, target_uid=uid, chunk_len=chunk_len)
    job['sent'] = True
    return True


def _reset_remote_ota_rx():
    _remote_ota_rx['chunks'] = {}
    _remote_ota_rx['session'] = None
    _remote_ota_rx['version'] = None
    _remote_ota_rx['files'] = {}
    _remote_ota_rx['received'] = {}


def _ensure_dir(path):
    try:
        d = path.rsplit('/', 1)[0]
        if d and d != path:
            try:
                os.stat(d)
            except Exception:
                os.mkdir(d)
    except Exception:
        pass


def _remote_ota_stage_root():
    return settings.LOG_DIR.rstrip('/') + '/lora_ota_stage'


def _remote_ota_stage_path(session, rel_name):
    safe = str(rel_name or '').replace('/', '__')
    return _remote_ota_stage_root() + '/' + str(session) + '__' + safe


def _remote_parse_type_message(msg_str):
    parts = str(msg_str).split(',')
    msg_type = None
    uid = None
    data_b64 = None
    chunk = None
    for p in parts:
        if p.startswith('TYPE:'):
            msg_type = p[5:]
        elif p.startswith('UID:'):
            uid = p[4:]
        elif p.startswith('DATA:'):
            data_b64 = p[5:]
        elif p.startswith('CHUNK:'):
            chunk = p[6:]
    return msg_type, uid, chunk, data_b64


def _remote_decode_json_b64(data_b64):
    raw = _ub.a2b_base64(str(data_b64).encode())
    return ujson.loads(raw.decode())


async def _remote_handle_lora_ota_payload(msg_type, payload):
    if not isinstance(payload, dict):
        return False

    if msg_type == 'LORA_OTA_META':
        session = str(payload.get('session') or '')
        files = payload.get('files') if isinstance(payload.get('files'), list) else []
        expected = {}
        for row in files:
            if not isinstance(row, dict):
                continue
            n = str(row.get('name') or '').strip()
            h = str(row.get('sha256') or '').strip().lower()
            if n and h:
                expected[n] = h
        _remote_ota_rx['session'] = session
        _remote_ota_rx['version'] = str(payload.get('version') or '')
        _remote_ota_rx['files'] = expected
        _remote_ota_rx['received'] = {}
        return True

    if msg_type == 'LORA_OTA_FILE':
        session = str(payload.get('session') or '')
        if not session or session != str(_remote_ota_rx.get('session') or ''):
            return False
        name = str(payload.get('name') or '').strip()
        expected_sha = str(payload.get('sha256') or '').strip().lower()
        blob_b64 = payload.get('data_b64')
        if not name or not expected_sha or not blob_b64:
            return False
        raw = _ub.a2b_base64(str(blob_b64).encode())
        got_sha = _sha256_hex(raw)
        if got_sha != expected_sha:
            await log_error(f'remote ota sha mismatch {name}')
            return False
        staged_path = _remote_ota_stage_path(session, name)
        _ensure_dir(staged_path)
        with open(staged_path, 'wb') as wf:
            wf.write(raw)
        _remote_ota_rx['received'][name] = {
            'sha256': expected_sha,
            'staged_path': staged_path,
        }
        return True

    if msg_type == 'LORA_OTA_APPLY':
        session = str(payload.get('session') or '')
        if not session or session != str(_remote_ota_rx.get('session') or ''):
            return False
        expected = _remote_ota_rx.get('files') if isinstance(_remote_ota_rx.get('files'), dict) else {}
        received = _remote_ota_rx.get('received') if isinstance(_remote_ota_rx.get('received'), dict) else {}
        for fname, fsha in expected.items():
            row = received.get(fname) if isinstance(received, dict) else None
            if not isinstance(row, dict) or str(row.get('sha256') or '').lower() != str(fsha or '').lower():
                await log_error(f'remote ota missing file {fname}')
                return False

        manifest_path = getattr(settings, 'LORA_OTA_STAGE_MANIFEST_FILE', settings.LOG_DIR.rstrip('/') + '/lora_ota_staged_manifest.json')
        manifest = {
            'session': session,
            'version': str(payload.get('version') or _remote_ota_rx.get('version') or ''),
            'files': [
                {
                    'name': n,
                    'sha256': row.get('sha256'),
                    'staged_path': row.get('staged_path'),
                }
                for n, row in received.items()
            ],
        }
        _ensure_dir(manifest_path)
        with open(manifest_path, 'w') as mf:
            mf.write(ujson.dumps(manifest))

        pending_file = getattr(settings, 'OTA_PENDING_FILE', settings.LOG_DIR.rstrip('/') + '/ota_pending.flag')
        _ensure_dir(pending_file)
        with open(pending_file, 'w') as pf:
            pf.write(str(manifest.get('version') or 'lora-ota'))

        await debug_print('Remote LoRa OTA staged; rebooting to apply.', 'OTA')
        await asyncio.sleep(0.4)
        try:
            machine.soft_reset()
        except Exception:
            try:
                machine.reset()
            except Exception:
                pass
        return True

    return False


async def _remote_handle_lora_ota_wire_message(msg_str):
    msg_type, uid, chunk_info, data_b64 = _remote_parse_type_message(msg_str)
    my_uid = str(getattr(settings, 'UNIT_ID', '') or '')
    if not msg_type or uid != my_uid:
        return False
    if not msg_type.startswith('LORA_OTA_'):
        return False

    base_type = msg_type[:-6] if msg_type.endswith('_CHUNK') else msg_type
    if msg_type.endswith('_CHUNK'):
        try:
            cn, total = map(int, str(chunk_info or '0/0').split('/'))
        except Exception:
            return False
        if base_type not in _remote_ota_rx['chunks']:
            _remote_ota_rx['chunks'][base_type] = {'total': total, 'parts': {}}
        _remote_ota_rx['chunks'][base_type]['parts'][cn] = data_b64
        slot = _remote_ota_rx['chunks'][base_type]
        if len(slot['parts']) < total:
            return True
        if not all(i in slot['parts'] for i in range(total)):
            return True
        assembled_b64 = ''.join(slot['parts'][i] for i in range(total))
        try:
            del _remote_ota_rx['chunks'][base_type]
        except Exception:
            pass
        payload = _remote_decode_json_b64(assembled_b64)
        return await _remote_handle_lora_ota_payload(base_type, payload)

    payload = _remote_decode_json_b64(data_b64)
    return await _remote_handle_lora_ota_payload(base_type, payload)

async def display_message(msg, duration=1.5):
    try:
        from oled import display_message as _dm
        await _dm(msg, duration)
    except Exception:
        pass

async def log_error(error_msg):
    global last_lora_error_ts
    ts = time.time()
    if ts - last_lora_error_ts < 5:
        return
    last_lora_error_ts = ts
    log_line = f"{ts}: {error_msg}\n"
    error_log_file = getattr(settings, 'ERROR_LOG_FILE', settings.LOG_DIR + '/lora_errors.log')
    try:
        async with file_lock:
            with open(error_log_file, 'a') as f:
                f.write(log_line)
    except Exception:
        await debug_print(f"[FATAL] Failed to log error: {error_msg}", "ERROR")

async def hard_reset_lora():
    global lora
    await debug_print("Hard LoRa reset + full pin isolation (v2.01.6)", "LORA")
    if lora:
        try:
            lora.reset()
        except Exception:
            pass

    pins_to_reset = [
        getattr(settings, 'CLK_PIN', 35), getattr(settings, 'MOSI_PIN', 36),
        getattr(settings, 'MISO_PIN', 37), getattr(settings, 'CS_PIN', 14),
        getattr(settings, 'IRQ_PIN', 4), getattr(settings, 'RST_PIN', 40),
        getattr(settings, 'BUSY_PIN', 13),
        getattr(settings, 'DEVICE_TEMP_SCL_PIN', 33), getattr(settings, 'DEVICE_TEMP_SDA_PIN', 34),
        getattr(settings, 'BME280_PROBE_SCL_PIN', 6), getattr(settings, 'BME280_PROBE_SDA_PIN', 5),
        getattr(settings, 'OLED_SCL_PIN', 38), getattr(settings, 'OLED_SDA_PIN', 39)
    ]
    for p_num in pins_to_reset:
        try:
            p = machine.Pin(p_num, machine.Pin.IN, machine.Pin.PULL_DOWN)
            p.value(0)
        except Exception:
            pass

    try:
        from machine import SPI
        spi_bus = getattr(settings, 'SPI_BUS', 1)
        spi = SPI(spi_bus)
        spi.deinit()
        await debug_print(f"SPI bus {spi_bus} deinit successful", "LORA")
    except Exception:
        pass

    try:
        rst = machine.Pin(getattr(settings, 'RST_PIN', 40), machine.Pin.OUT)
        for _ in range(5):
            rst.value(0)
            await asyncio.sleep_ms(50)
            rst.value(1)
            await asyncio.sleep_ms(100)
        await asyncio.sleep_ms(350)
    except Exception:
        pass

    lora = None
    gc.collect()
    await asyncio.sleep_ms(500)
    await debug_print("Hard reset sequence complete", "LORA")

async def ensure_lora_listening():
    global lora
    if lora is None or not hasattr(lora, 'recv'):
        return False
    try:
        lora.recv(0, False, 0)
        return True
    except Exception:
        lora = None
        return False

async def init_lora():
    global lora
    await debug_print("LoRa bulletproof init sequence (v2.01.6)", "LORA")
    await display_message("LoRa Init...", 1)
    for attempt in range(20):
        await hard_reset_lora()
        await free_pins()
        await asyncio.sleep(1.2)
        try:
            lora = SX1262(
                getattr(settings, 'SPI_BUS', 1), getattr(settings, 'CLK_PIN', 35),
                getattr(settings, 'MOSI_PIN', 36), getattr(settings, 'MISO_PIN', 37),
                getattr(settings, 'CS_PIN', 14), getattr(settings, 'IRQ_PIN', 4),
                getattr(settings, 'RST_PIN', 40), getattr(settings, 'BUSY_PIN', 13)
            )
            status = lora.begin(
                freq=getattr(settings, 'FREQ', 915.0), bw=getattr(settings, 'BW', 125.0),
                sf=getattr(settings, 'SF', 12), cr=getattr(settings, 'CR', 7),
                syncWord=getattr(settings, 'SYNC_WORD', 0xF4), power=getattr(settings, 'POWER', 14),
                currentLimit=getattr(settings, 'CURRENT_LIMIT', 140.0),
                preambleLength=getattr(settings, 'PREAMBLE_LEN', 12),
                implicit=False, implicitLen=0xFF, crcOn=getattr(settings, 'CRC_ON', True),
                txIq=False, rxIq=False,
                tcxoVoltage=getattr(settings, 'TCXO_VOLTAGE', 1.8),
                useRegulatorLDO=getattr(settings, 'USE_LDO', True),
                blocking=False
            )
            await debug_print(f'begin() attempt {attempt+1}: status {status}', 'LORA')
            if status == 0:
                lora.setBlockingCallback(False)
                await ensure_lora_listening()
                await debug_print("LoRa initialized successfully", "LORA")
                await display_message("LoRa OK", 1.5)
                sdata.lora_last_init_ts = time.time()
                return True
            elif status == -2:
                await debug_print("Status -2 detected - aggressive reset already performed", "WARN")
                await asyncio.sleep(2.5)
        except Exception as e:
            await debug_print(f"init attempt {attempt+1} exception: {e}", "WARN")
            lora = None
        await asyncio.sleep(1.5)

    await debug_print("LoRa init FAILED after 20 attempts - triggering MCU reset", "FATAL")
    await display_message("LoRa FAIL - REBOOT", 5)
    await free_pins()
    lora = None
    if machine and hasattr(machine, 'reset'):
        await asyncio.sleep(1)
        machine.reset()
    return False

command_handlers = {
    "toggle_relay": toggle_relay,
}

REMOTE_NODE_INFO_FILE = getattr(settings, 'REMOTE_NODE_INFO_FILE', settings.LOG_DIR + '/remote_node_info.json')

def load_remote_node_info():
    try:
        with open(REMOTE_NODE_INFO_FILE, 'r') as f:
            settings.REMOTE_NODE_INFO = ujson.load(f)
    except Exception:
        settings.REMOTE_NODE_INFO = {}

load_remote_node_info()

def save_remote_node_info():
    try:
        with open(REMOTE_NODE_INFO_FILE, 'w') as f:
            ujson.dump(settings.REMOTE_NODE_INFO, f)
    except Exception:
        pass

async def proxy_register_for_remote(remote_uid, remote_machine_id):
    if not register_with_wp:
        return
    now = time.time()
    if remote_uid in proxy_last_ts and now - proxy_last_ts[remote_uid] < 270:
        return
    original_unit_id = getattr(settings, 'UNIT_ID', '')
    original_get = None
    success = False
    try:
        import utils as _u
        if hasattr(_u, 'get_machine_id'):
            original_get = _u.get_machine_id
            def temp_get():
                return str(remote_machine_id)
            _u.get_machine_id = temp_get
        settings.UNIT_ID = remote_uid
        await debug_print(f"Proxy register for remote {remote_uid}", "BASE_NODE")
        for attempt in range(3):
            try:
                if asyncio.iscoroutinefunction(register_with_wp):
                    success = await register_with_wp()
                else:
                    success = register_with_wp()
                if success:
                    await display_message(f"Reg {remote_uid[:8]} OK", 0.8)
                    break
                await asyncio.sleep(1.5 * (attempt + 1))
            except Exception as e:
                await log_error(f"Proxy reg attempt {attempt+1} failed: {e}")
                await asyncio.sleep(2 ** attempt)
    finally:
        settings.UNIT_ID = original_unit_id
        if original_get and hasattr(_u, 'get_machine_id'):
            _u.get_machine_id = original_get
    if success:
        proxy_last_ts[remote_uid] = time.time()
    else:
        await display_message(f"Reg {remote_uid[:8]} FAIL", 1.5)
    gc.collect()

# ===================== BACKGROUND PROCESSOR =====================
async def process_remote_burst(uid, st):
    """Called immediately after FULL burst (TS+SETTINGS+SDATA) OR after idle timeout"""
    await debug_print(f"Processing complete burst for {uid} (background)", "BASE_NODE")
    remote_machine_id = None
    remote_fw_version = None
    ota_session_id = None

    ack_delay = None
    ack_msg = None

    if 'TS' in st['types']:
        data = st['data']['TS']
        remote_ts = data.get('remote_ts')
        remote_company = data.get('remote_company')
        remote_site = data.get('remote_site')
        remote_zone = data.get('remote_zone')
        remote_cluster = data.get('remote_cluster')
        remote_runtime = data.get('remote_runtime')
        remote_script_runtime = data.get('remote_script_runtime')
        temp_c = data.get('temp_c')
        temp_f = data.get('temp_f')
        bar = data.get('bar')
        humid = data.get('humid')
        remote_machine_id = data.get('remote_machine_id')

        if uid and remote_company is not None:
            if uid not in settings.REMOTE_NODE_INFO:
                settings.REMOTE_NODE_INFO[uid] = {}
            settings.REMOTE_NODE_INFO[uid].update({
                'COMPANY': remote_company, 'SITE': remote_site,
                'ZONE': remote_zone, 'CLUSTER': remote_cluster,
                'MACHINE_ID': remote_machine_id,
                'last_temp_f': temp_f,
            })
            save_remote_node_info()

    if uid:
        ack_delay = calculate_next_delay(uid)
        ack_msg = f"ACK:{uid}:NEXT:{ack_delay}"
        try:
            ota_session_hint = _remote_lora_ota_jobs.get(uid)
            if isinstance(ota_session_hint, dict) and ota_session_hint.get('session'):
                ack_msg += f":OTA:{ota_session_hint.get('session')}:VER:{getattr(settings, 'FIRMWARE_VERSION', '')}"
        except Exception:
            pass

        now = time.time()
        if uid not in settings.REMOTE_NODE_INFO:
            settings.REMOTE_NODE_INFO[uid] = {}
        settings.REMOTE_NODE_INFO[uid]['next_expected'] = now + ack_delay
        settings.REMOTE_NODE_INFO[uid]['missed_syncs'] = 0
        save_remote_node_info()

        try:
            ack_msg = await _secure_message(ack_msg, remote_uid=uid)
            await _send_with_retry(ack_msg.encode())
            await debug_print(f"Sent ACK with next delay {ack_delay}s to {uid}", "BASE_NODE")
            try:
                from oled import display_message
                await display_message("ACK Sent", 0.5)
            except Exception:
                pass
        except Exception as ack_e:
            await log_error(f"ACK send error to {uid}: {ack_e}")

    if None not in (uid, remote_runtime, remote_script_runtime, temp_c, temp_f, bar, humid):
            base_ts = time.time()
            log_line = f"{base_ts},{uid},{remote_ts},{remote_runtime},{remote_script_runtime},{temp_c},{temp_f},{bar},{humid}\n"
            log_file = getattr(settings, 'LOG_FILE', settings.LOG_DIR + '/lora.log')
            async with file_lock:
                with open(log_file, 'a') as f:
                    f.write(log_line)
            record_field_data()

            try:
                temp_f_val = float(temp_f)
                bar_val = float(bar)
                humid_val = float(humid)
            except Exception:
                temp_f_val = bar_val = humid_val = 0.0

            await findLowestTemp(temp_f_val)
            await findHighestTemp(temp_f_val)
            await findLowestBar(bar_val)
            await findHighestBar(bar_val)
            await findLowestHumid(humid_val)
            await findHighestHumid(humid_val)

    if 'SETTINGS' in st['types']:
        settings_dict = st['data']['SETTINGS']
        stage_remote_files(uid, {'settings.py': ujson.dumps(settings_dict).encode()})
        try:
            remote_fw_version = str(settings_dict.get('FIRMWARE_VERSION') or '').strip()
        except Exception:
            remote_fw_version = None

    try:
        ota_session_id = _stage_remote_lora_ota_job(uid, remote_fw_version)
        if ota_session_id:
            await debug_print(
                f"LoRa OTA staged for {uid}: {remote_fw_version} -> {getattr(settings, 'FIRMWARE_VERSION', '')}",
                "OTA"
            )
    except Exception as ota_stage_e:
        await log_error(f"LoRa OTA stage error for {uid}: {ota_stage_e}")

    if 'SDATA' in st['types']:
        sdata_dict = st['data']['SDATA']
        stage_remote_field_data(uid, [sdata_dict])

    # SEND ACK (optionally piggyback one pending command for this remote)
    try:
        pending_cmd = await _fetch_remote_pending_command(uid, remote_machine_id)
        if isinstance(pending_cmd, dict):
            cmd_blob = _encode_ack_command(pending_cmd)
            if cmd_blob:
                ack_msg += f":CMD:{cmd_blob}"
        ack_msg = await _secure_message(ack_msg, remote_uid=uid)
        await _send_with_retry(ack_msg.encode())
        if isinstance(pending_cmd, dict):
            await debug_print(f"Sent ACK+CMD to {uid} (cmd_id={pending_cmd.get('id')})", "BASE_NODE")
        elif ota_session_id:
            await debug_print(f"Sent ACK+OTA hint to {uid}", "BASE_NODE")
    except Exception as ack_e:
        await log_error(f"ACK send error to {uid}: {ack_e}")

    if ota_session_id:
        try:
            await _send_lora_ota_job(uid)
        except Exception as ota_send_e:
            await log_error(f"LoRa OTA send error to {uid}: {ota_send_e}")

    # Proxy HTTP calls AFTER ACK
    if 'TS' in st['types'] and remote_machine_id:
        await proxy_register_for_remote(uid, remote_machine_id)

    # Cleanup ONLY temporary burst tracking keys - KEEP persistent info (next_expected, missed_syncs, COMPANY, etc.)
    if uid in settings.REMOTE_NODE_INFO:
        for temp_key in ('types', 'data', 'chunks', 'last_rx'):
            settings.REMOTE_NODE_INFO[uid].pop(temp_key, None)
        save_remote_node_info()


async def process_remote_field_data(uid, st):
    """
    Process a fully assembled FIELD_DATA payload from a remote node,
    stage the records, and send an ACK with the next sync delay.
    """
    try:
        payload = st.get('data', {}).get('FIELD_DATA')

        defaults = {}
        batch_id = None
        if isinstance(payload, dict) and 'data' in payload:
            records = payload.get('data')
            batch_id = payload.get('batch_id')
            defaults = {
                'unit_id': payload.get('unit_id') or uid,
                'machine_id': payload.get('machine_id'),
                'firmware_version': payload.get('firmware_version'),
                'NODE_TYPE': payload.get('NODE_TYPE') or payload.get('node_type') or 'remote',
            }
        elif isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            records = [payload]
        else:
            records = None

        if isinstance(records, list) and records:
            merged_records = []
            for record in records:
                if not isinstance(record, dict):
                    continue
                merged = dict(defaults)
                merged.update(record)
                if not merged.get('unit_id'):
                    merged['unit_id'] = uid
                merged['node_type'] = merged.get('node_type') or merged.get('NODE_TYPE') or 'remote'
                merged['ingested_via'] = 'lora_base'
                merged['remote_unit_id'] = uid
                merged_records.append(merged)

            if merged_records:
                next_delay = calculate_next_delay(uid)
                now = time.time()
                if uid not in settings.REMOTE_NODE_INFO:
                    settings.REMOTE_NODE_INFO[uid] = {}
                settings.REMOTE_NODE_INFO[uid]['next_expected'] = now + next_delay
                settings.REMOTE_NODE_INFO[uid]['missed_syncs'] = 0
                try:
                    save_remote_node_info()
                except Exception:
                    pass

                # Send ACK immediately so the remote can decide whether to sleep.
                try:
                    ack_msg = f"ACK:{uid}:NEXT:{next_delay}"
                    if batch_id:
                        ack_msg += f":BID:{batch_id}"
                    ack_msg = await _secure_message(ack_msg, remote_uid=uid)
                    await _send_with_retry(ack_msg.encode())
                    if batch_id:
                        await debug_print(
                            f"Sent FIELD_DATA ACK to {uid} next={next_delay}s bid={batch_id}",
                            "BASE_NODE"
                        )
                    else:
                        await debug_print(
                            f"Sent FIELD_DATA ACK with next delay {next_delay}s to {uid}",
                            "BASE_NODE"
                        )
                    try:
                        from oled import display_message
                        await display_message("ACK Sent", 0.8)
                    except Exception:
                        pass
                except Exception as ack_e:
                    await log_error(f"FIELD_DATA ACK send error to {uid}: {ack_e}")

                # Stage after ACK so the radio window is not blocked by local IO.
                try:
                    stage_remote_field_data(uid, merged_records)
                    await debug_print(f"Staged {len(merged_records)} remote field records from {uid}", "BASE_NODE")
                except Exception as stage_e:
                    await log_error(f"stage_remote_field_data error for {uid}: {stage_e}")

    except Exception as e:
        await log_error(f"Remote field data processor error for {uid}: {e}")

    finally:
        # Clean up state for this burst
        try:
            if 'FIELD_DATA' in st.get('types', set()):
                st['types'].discard('FIELD_DATA')
            if isinstance(st.get('data'), dict):
                st['data'].pop('FIELD_DATA', None)
            if isinstance(st.get('chunks'), dict):
                st['chunks'].pop('FIELD_DATA', None)
        except Exception:
            pass

async def process_remote_state_files(uid, st):
    try:
        payload = st.get('data', {}).get('STATE_FILES')
        if isinstance(payload, dict):
            file_map = payload.get('files') if isinstance(payload.get('files'), dict) else payload
            files = {}
            for name, content in (file_map or {}).items():
                if isinstance(content, str):
                    try:
                        files[str(name)] = _ub.a2b_base64(content.encode())
                    except Exception:
                        pass
                elif isinstance(content, bytes):
                    files[str(name)] = content
            if files:
                stage_remote_files(uid, files)
                await debug_print(f"Staged {len(files)} remote state files from {uid}", "BASE_NODE")
    except Exception as e:
        await log_error(f"Remote state file processor error for {uid}: {e}")
    finally:
        if 'STATE_FILES' in st.get('types', set()):
            st['types'].discard('STATE_FILES')
        if isinstance(st.get('data'), dict):
            st['data'].pop('STATE_FILES', None)
        if isinstance(st.get('chunks'), dict):
            st['chunks'].pop('STATE_FILES', None)

async def base_packet_processor():
    global last_lora_activity_ts
    while True:
        try:
            packet = await lora_rx_queue.get()
            last_lora_activity_ts = time.time()
            uid = packet.get('uid')
            packet_type = packet.get('type')
            parsed_data = packet.get('data')
            current_time = time.time()

            if uid not in settings.REMOTE_NODE_INFO:
                settings.REMOTE_NODE_INFO[uid] = {'types': set(), 'last_rx': current_time, 'data': {}, 'chunks': {}}
            st = settings.REMOTE_NODE_INFO[uid]

            orig_type = packet_type[:-6] if packet_type.endswith('_CHUNK') else packet_type
            if packet_type.endswith('_CHUNK'):
                if 'chunks' not in st:
                    st['chunks'] = {}
                if orig_type not in st['chunks']:
                    st['chunks'][orig_type] = {}
                try:
                    cn, total = map(int, packet.get('chunk_info', '0/0').split('/'))
                    st['chunks'][orig_type][cn] = parsed_data
                    st['last_rx'] = current_time

                    await debug_print(f"Stored CHUNK {cn}/{total} for {orig_type} from {uid} (have {len(st['chunks'][orig_type])}/{total})", "BASE_NODE")

                    if len(st['chunks'][orig_type]) == total and all(k in st['chunks'][orig_type] for k in range(total)):
                        assembled_b64 = ''.join(st['chunks'][orig_type][j] for j in range(total))
                        json_data = _ub.a2b_base64(assembled_b64.encode()).decode()
                        parsed_dict = ujson.loads(json_data)
                        st['data'][orig_type] = parsed_dict
                        st['types'].add(orig_type)
                        del st['chunks'][orig_type]
                        await debug_print(f"✅ FULLY ASSEMBLED {orig_type} ({total} chunks) for {uid}", "BASE_NODE")
                except Exception as e:
                    await log_error(f"Chunk parse error for {uid}: {e}")

            else:
                st['types'].add(packet_type)
                st['data'][packet_type] = parsed_data
                st['last_rx'] = current_time

            if orig_type == 'FIELD_DATA':
                await process_remote_field_data(uid, st)
            elif orig_type == 'CMD_RESULT':
                await process_remote_command_result(uid, st)
            elif orig_type == 'STATE_FILES':
                await process_remote_state_files(uid, st)
            else:
                # FULL BURST PROCESSING: only after ALL three expected types are present (or silence timeout)
                full_burst = all(t in st['types'] for t in ('TS', 'SETTINGS', 'SDATA'))
                if full_burst or (current_time - st['last_rx'] > 12):
                    await process_remote_burst(uid, st)

            # Cleanup old partial bursts (prevent memory leak) - safe even if keys were popped in process_remote_burst
            chunks_dict = st.get('chunks', {})
            for t in list(chunks_dict):
                if current_time - st.get('last_rx', 0) > 30:
                    del chunks_dict[t]
                    await debug_print(f"Discarded partial {t} chunks for {uid} (timeout)", "BASE_NODE")

            lora_rx_queue.task_done()
            gc.collect()
        except Exception as e:
            await log_error(f"Background packet processor error: {e}")
            await asyncio.sleep(1)

async def handle_incoming_packet(msg):
    global last_rx_ts, last_lora_activity_ts
    msg_str = msg.rstrip(b'\x00').decode()

    uid_hint = None
    if str(getattr(settings, 'NODE_TYPE', 'base')).lower() == 'base':
        try:
            parts = msg_str.split(',')
            for p in parts:
                if p.startswith('UID:'):
                    uid_hint = p[4:].strip()
                    break
                if p.startswith('U:'):
                    uid_hint = p[2:].strip()
                    break
        except Exception:
            uid_hint = None

    msg_str = await _unsecure_message(msg_str, remote_uid=uid_hint)
    if not msg_str:
        return

    # Validate network membership after decryption so secure envelopes can be checked.
    if str(getattr(settings, 'NODE_TYPE', 'base')).lower() == 'base':
        strict_net_check = msg_str.startswith('T:')
        if not _base_network_matches(msg_str, strict=strict_net_check):
            await debug_print('LoRa packet rejected due to network mismatch', 'WARN')
            return

    await debug_print(f"Base RX: {msg_str[:120]}...", "BASE_NODE")
    last_rx_ts = time.time()
    last_lora_activity_ts = last_rx_ts
    sdata.lora_SigStr = lora.getRSSI() if hasattr(lora, 'getRSSI') else -60
    sdata.lora_snr = lora.getSNR() if hasattr(lora, 'getSNR') else 0
    sdata.LORA_CONNECTED = True

    # Lightweight parse → queue (unchanged)
    remote_uid = None
    packet_type = 'UNKNOWN'
    parsed_data = None
    chunk_str = None

    if msg_str.startswith('T:'):
        packet_type = 'TS'
        parsed_data = {}
        parts = msg_str.split(',')
        for part in parts:
            if ':' not in part:
                continue
            key, value = part.split(':', 1)
            value = value.strip()
            if key == 'U':
                remote_uid = value
            elif key == 'T':
                parsed_data['remote_ts'] = value
            elif key == 'M':
                parsed_data['remote_machine_id'] = value
            elif key == 'C':
                parsed_data['remote_company'] = value
            elif key == 'S':
                parsed_data['remote_site'] = value
            elif key == 'Z':
                parsed_data['remote_zone'] = value
            elif key == 'K':
                parsed_data['remote_cluster'] = value
            elif key == 'R':
                parsed_data['remote_runtime'] = value
            elif key == 'SR':
                parsed_data['remote_script_runtime'] = value
            elif key == 'TC':
                parsed_data['temp_c'] = value
            elif key == 'TF':
                parsed_data['temp_f'] = value
            elif key == 'B':
                parsed_data['bar'] = value
            elif key == 'H':
                parsed_data['humid'] = value
            elif key == 'DTC':
                parsed_data['device_temp_c'] = value
            elif key == 'DTF':
                parsed_data['device_temp_f'] = value
            elif key == 'DB':
                parsed_data['device_bar'] = value
            elif key == 'DH':
                parsed_data['device_humid'] = value

    elif msg_str.startswith('TYPE:'):
        parts = msg_str.split(',')
        msg_type = None
        remote_uid = None
        data_b64 = None
        chunk_str = None
        for p in parts:
            if p.startswith('TYPE:'):
                msg_type = p[5:]
            elif p.startswith('UID:'):
                remote_uid = p[4:]
            elif p.startswith('DATA:'):
                data_b64 = p[5:]
            elif p.startswith('CHUNK:'):
                chunk_str = p[6:]
        if msg_type and remote_uid:
            packet_type = msg_type
            if msg_type.endswith('_CHUNK'):
                parsed_data = data_b64
            else:
                try:
                    json_data = _ub.a2b_base64(data_b64.encode()).decode()
                    parsed_data = ujson.loads(json_data)
                except Exception:
                    return

    if packet_type == 'HEARTBEAT' and remote_uid:
        try:
            info = getattr(settings, 'REMOTE_NODE_INFO', {}) or {}
            node = info.get(remote_uid, {})
            if isinstance(parsed_data, dict):
                now = time.time()
                node['last_heartbeat_ts'] = now
                node['rssi'] = parsed_data.get('rssi')
                node['snr'] = parsed_data.get('snr')
                node['missed_syncs'] = 0
                heartbeat_window = getattr(settings, 'LORA_HEARTBEAT_INTERVAL_S', 120) * 2
                node['next_expected'] = now + heartbeat_window
                info[remote_uid] = node
                settings.REMOTE_NODE_INFO = info
                save_remote_node_info()
                await debug_print(f"Heartbeat received from {remote_uid}", "BASE_NODE")
        except Exception as e:
            await log_error(f"Heartbeat parse error: {e}")
        return

    if remote_uid and packet_type != 'UNKNOWN':
        packet = {
            'uid': remote_uid,
            'type': packet_type,
            'data': parsed_data,
            'chunk_info': chunk_str if packet_type.endswith('_CHUNK') else None
        }
        await lora_rx_queue.put(packet)

# ---------------------------------------------------------------------------
# LoRa Security - HMAC + per-remote counters + replay window
# ---------------------------------------------------------------------------

def _load_counters():
    """Load persisted counters from disk."""
    global tx_counter, remote_counters
    try:
        path = getattr(settings, 'LORA_COUNTERS_FILE', '/logs/lora_counters.json')
        with open(path, 'r') as f:
            data = ujson.load(f)
        if isinstance(data, dict):
            tx_counter = int(data.get('tx_counter', 0))
            rc = data.get('remote_counters', {})
            if isinstance(rc, dict):
                remote_counters = {}
                for uid, vals in rc.items():
                    if isinstance(vals, dict):
                        remote_counters[uid] = {
                            'tx': int(vals.get('tx', 0)),
                            'rx': int(vals.get('rx', 0))
                        }
    except Exception:
        pass


def _save_counters():
    """Persist counters to disk."""
    try:
        path = getattr(settings, 'LORA_COUNTERS_FILE', '/logs/lora_counters.json')
        data = {
            'tx_counter': tx_counter,
            'remote_counters': remote_counters
        }
        with open(path, 'w') as f:
            ujson.dump(data, f)
    except Exception:
        pass


_load_counters()


def hmac_sha256(key, msg):
    BLOCK_SIZE = 64
    if isinstance(key, str):
        key = key.encode()
    if isinstance(msg, str):
        msg = msg.encode()
    if len(key) > BLOCK_SIZE:
        key = uhashlib.sha256(key).digest()
    key = key + b'\x00' * (BLOCK_SIZE - len(key))
    opad = bytes((x ^ 0x5C) for x in key)
    ipad = bytes((x ^ 0x36) for x in key)
    inner = uhashlib.sha256(ipad + msg).digest()
    return uhashlib.sha256(opad + inner).digest()


def _format_crc(crc_val):
    try:
        return '{:04X}'.format(crc_val & 0xFFFF)
    except Exception:
        return '0000'


async def _secure_message(msg_str, remote_uid=None):
    """Add CNT/HMAC metadata using a pipe-separated envelope."""
    global tx_counter

    if not getattr(settings, 'LORA_HMAC_ENABLED', False):
        return msg_str

    if str(getattr(settings, 'NODE_TYPE', '')).lower() == 'remote':
        counter = tx_counter + 1
        tx_counter = counter
    else:
        if remote_uid is None:
            counter = tx_counter + 1
            tx_counter = counter
        else:
            if remote_uid not in remote_counters:
                remote_counters[remote_uid] = {'tx': 0, 'rx': 0}
            counter = remote_counters[remote_uid]['tx'] + 1
            remote_counters[remote_uid]['tx'] = counter

    counter_str = str(counter)
    counter_bytes = counter.to_bytes(4, 'big')

    secret = getattr(settings, 'LORA_HMAC_SECRET', '') or ''
    if isinstance(secret, str):
        secret = secret.encode()

    crc_hex = None
    if getattr(settings, 'LORA_CRC_ENABLED', True):
        try:
            crc_hex = _format_crc(crc16_ccitt(msg_str.encode()))
        except Exception:
            crc_hex = None

    if getattr(settings, 'LORA_ENCRYPT_ENABLED', False):
        msg_bytes = msg_str.encode()
        stream_key = secret + counter_bytes
        stream_hash = uhashlib.sha256(stream_key).digest()
        encrypted = bytes(a ^ b for a, b in zip(msg_bytes, (stream_hash * ((len(msg_bytes) // 32) + 1))[:len(msg_bytes)]))
        enc_b64 = _ub.b2a_base64(encrypted).rstrip(b'\n').decode()
        to_hmac = encrypted + counter_bytes
        hmac_val = hmac_sha256(secret, to_hmac)
        hmac_hex = _ub.hexlify(hmac_val).decode()[:getattr(settings, 'LORA_HMAC_TRUNCATE', 16)]
        secure_msg = f"ENC:{enc_b64}|CNT:{counter}|HMAC:{hmac_hex}"
    else:
        to_hmac = msg_str.encode() + counter_str.encode()
        hmac_val = hmac_sha256(secret, to_hmac)
        hmac_hex = _ub.hexlify(hmac_val).decode()[:getattr(settings, 'LORA_HMAC_TRUNCATE', 16)]
        secure_msg = msg_str + f"|CNT:{counter}|HMAC:{hmac_hex}"

    if crc_hex is not None:
        secure_msg += f"|CRC:{crc_hex}"

    if counter % 5 == 0:
        _save_counters()

    return secure_msg


async def _unsecure_message(msg_str, remote_uid=None):
    """Verify HMAC/CRC and replay window for pipe-separated secure envelopes."""
    if not getattr(settings, 'LORA_HMAC_ENABLED', False):
        return msg_str

    if not msg_str:
        return None

    cnt = None
    hmac_hex = None
    crc_hex = None
    is_enc = False
    enc_b64 = None
    original_msg = msg_str

    if '|CNT:' in msg_str or '|HMAC:' in msg_str:
        meta_sep = '|'
    elif ',CNT:' in msg_str or ',HMAC:' in msg_str:
        meta_sep = ','
    else:
        # Default for new format when metadata is incomplete/corrupt.
        meta_sep = '|'

    if msg_str.startswith('ENC:'):
        is_enc = True
        parts = msg_str.split(meta_sep)
        for p in parts:
            if p.startswith('ENC:'):
                enc_b64 = p[4:]
            elif p.startswith('CNT:'):
                try:
                    cnt = int(p[4:])
                except Exception:
                    cnt = None
            elif p.startswith('HMAC:'):
                hmac_hex = p[5:]
            elif p.startswith('CRC:'):
                crc_hex = p[4:]
    else:
        cnt_marker = f'{meta_sep}CNT:'
        hmac_marker = f'{meta_sep}HMAC:'
        if cnt_marker not in msg_str or hmac_marker not in msg_str:
            if getattr(settings, 'LORA_HMAC_REJECT_UNSIGNED', True):
                await log_error('Invalid secure format (no CNT/HMAC)')
                return None
            return msg_str

        try:
            parts = msg_str.split(meta_sep)
            message_parts = []
            for p in parts:
                if p.startswith('CNT:'):
                    try:
                        cnt = int(p[4:])
                    except Exception:
                        cnt = None
                elif p.startswith('HMAC:'):
                    hmac_hex = p[5:]
                elif p.startswith('CRC:'):
                    crc_hex = p[4:]
                else:
                    message_parts.append(p)
            original_msg = meta_sep.join(message_parts)
        except Exception:
            return None

    if cnt is None or hmac_hex is None:
        await log_error('Missing CNT or HMAC in secure message')
        return None

    secret = getattr(settings, 'LORA_HMAC_SECRET', '') or ''
    if isinstance(secret, str):
        secret = secret.encode()

    counter_bytes = cnt.to_bytes(4, 'big')

    if is_enc:
        try:
            encrypted = _ub.a2b_base64(enc_b64.encode())
        except Exception:
            await log_error('Base64 decode failed')
            return None
        to_hmac = encrypted + counter_bytes
    else:
        to_hmac = original_msg.encode() + str(cnt).encode()

    hmac_val = hmac_sha256(secret, to_hmac)
    hmac_hex_calc = _ub.hexlify(hmac_val).decode()[:getattr(settings, 'LORA_HMAC_TRUNCATE', 16)]
    if hmac_hex_calc != hmac_hex:
        await log_error('HMAC verification failed')
        return None

    if is_enc:
        stream_key = secret + counter_bytes
        stream_hash = uhashlib.sha256(stream_key).digest()
        decrypted = bytes(a ^ b for a, b in zip(encrypted, (stream_hash * ((len(encrypted) // 32) + 1))[:len(encrypted)]))
        try:
            msg_str = decrypted.decode()
        except Exception:
            await log_error('Decryption decode failed')
            return None
    else:
        msg_str = original_msg

    if crc_hex:
        try:
            expected_crc = int(crc_hex, 16)
            actual_crc = crc16_ccitt(msg_str.encode())
            if actual_crc != expected_crc:
                await log_error(f"CRC mismatch: expected {crc_hex}, got {_format_crc(actual_crc)}")
                return None
        except Exception:
            pass

    if not getattr(settings, 'LORA_HMAC_REPLAY_PROTECT', True):
        return msg_str

    window = max(1, int(getattr(settings, 'LORA_REPLAY_WINDOW', 8)))

    if str(getattr(settings, 'NODE_TYPE', '')).lower() == 'remote':
        last_rx = getattr(settings, '_last_rx_counter', 0)
        if cnt <= last_rx - window:
            await log_error(f"Replay attack detected (cnt {cnt} <= last_rx {last_rx})")
            return None
        settings._last_rx_counter = max(last_rx, cnt)
    else:
        if remote_uid is None:
            try:
                if 'UID:' in msg_str:
                    remote_uid = msg_str.split('UID:')[1].split(',')[0].strip()
                elif ',U:' in msg_str:
                    remote_uid = msg_str.split(',U:')[1].split(',')[0].strip()
                elif msg_str.startswith('U:'):
                    remote_uid = msg_str.split('U:')[1].split(',')[0].strip()
                elif 'unit-' in msg_str:
                    for part in msg_str.split(','):
                        if part.startswith('unit-') or 'UID' in part:
                            remote_uid = part.split(':')[-1].strip()
                            break
            except Exception:
                remote_uid = 'unknown'

        if remote_uid not in remote_counters:
            remote_counters[remote_uid] = {'tx': 0, 'rx': 0}

        last_rx = remote_counters[remote_uid]['rx']

        if cnt <= last_rx - window:
            await log_error(f"Replay attack detected (cnt {cnt} <= rx_counter {last_rx}) uid={remote_uid}")
            return None

        if cnt > last_rx:
            remote_counters[remote_uid]['rx'] = cnt
            if cnt % 5 == 0:
                _save_counters()

    return msg_str

async def _send_with_retry(data, retries=6):
    global lora
    if lora is None or not hasattr(lora, 'send'):
        return
    if len(data) > 255:
        await log_error(f"Payload too large: {len(data)}")
        return
    base_delay = getattr(settings, 'LORA_RETRY_BASE_DELAY_S', 2)
    max_backoff = getattr(settings, 'LORA_MAX_BACKOFF_S', 90)
    for att in range(retries):
        try:
            await ensure_lora_listening()
            if hasattr(lora, 'cad'):
                for cad_try in range(3):
                    if not lora.cad(getattr(settings, 'CAD_SYMBOLS', 3)):
                        break
                    await asyncio.sleep(random.uniform(0.3, 1.0))
                else:
                    await debug_print("CAD still busy after 3 tries - sending anyway", "LORA")

            lora.send(data)
            if await _wait_tx_done():
                await ensure_lora_listening()
                return
        except Exception as e:
            await log_error(f"TX attempt {att+1} failed: {e}")
            if lora is None:
                await hard_reset_lora()
                await init_lora()
                return
            delay = min(max_backoff, base_delay * (2 ** att))
            delay += random.uniform(0, base_delay)
            await asyncio.sleep(delay)
    await debug_print("TX failed after retries", "WARN")
    try:
        await hard_reset_lora()
        await init_lora()
    except Exception as e:
        await log_error(f"TX recovery failed: {e}")

async def _wait_tx_done(timeout=30):
    global lora
    if lora is None:
        return False
    tx_start = time.time()
    while time.time() - tx_start < timeout:
        try:
            if lora._events() & lora.TX_DONE:
                return True
        except Exception:
            pass
        await asyncio.sleep(0.01)
    await log_error("TX timeout")
    lora = None
    await hard_reset_lora()
    return False

def calculate_next_delay(node_id):
    sync_rate = getattr(settings, 'LORA_SYNC_RATE', 300)
    sync_window = getattr(settings, 'LORA_NEXT_SYNC', 600)
    stagger_seed = 0
    for c in node_id:
        stagger_seed = (stagger_seed * 31 + ord(c)) % sync_window
    jitter = random.randint(-30, 30)
    delay = sync_rate + stagger_seed + jitter
    return max(60, delay)

async def _send_chunked(msg_type, full_b64, target_uid=None, chunk_len=None):
    max_b64_chunk_len = _safe_int(chunk_len, 0)
    if max_b64_chunk_len <= 0:
        configured = _safe_int(getattr(settings, 'LORA_CHUNK_SIZE', 0), 0)
        if configured > 0:
            max_b64_chunk_len = configured
        else:
            max_b64_chunk_len = 100 if getattr(settings, 'LORA_ENCRYPT_ENABLED', False) else 160
    target = str(target_uid or getattr(settings, 'UNIT_ID', ''))
    b64_len = len(full_b64)
    if b64_len <= max_b64_chunk_len:
        data_str = f"TYPE:{msg_type},UID:{target},DATA:{full_b64}"
        if str(getattr(settings, 'NODE_TYPE', 'base')).lower() == 'base':
            data_str = await _secure_message(data_str, remote_uid=target)
        else:
            data_str = await _secure_message(data_str)
        await _send_with_retry(data_str.encode())
    else:
        num_chunks = (b64_len + max_b64_chunk_len - 1) // max_b64_chunk_len
        for i in range(num_chunks):
            chunk_start = i * max_b64_chunk_len
            chunk_end = chunk_start + max_b64_chunk_len
            chunk_b64 = full_b64[chunk_start:chunk_end]
            data_str = f"TYPE:{msg_type}_CHUNK,UID:{target},CHUNK:{i}/{num_chunks},DATA:{chunk_b64}"
            if str(getattr(settings, 'NODE_TYPE', 'base')).lower() == 'base':
                data_str = await _secure_message(data_str, remote_uid=target)
            else:
                data_str = await _secure_message(data_str)
            await _send_with_retry(data_str.encode())
            await asyncio.sleep(random.uniform(0.08, 0.25))
        await asyncio.sleep(0.5)  # final pause so base can finish processing last chunk


async def send_remote_field_data_batch(payload):
    try:
        if not isinstance(payload, dict):
            return False
        payload_b64 = _ub.b2a_base64(ujson.dumps(payload).encode()).rstrip(b'\n').decode()
        await _send_chunked('FIELD_DATA', payload_b64)
        return True
    except Exception as e:
        await log_error(f'send_remote_field_data_batch failed: {e}')
        return False


async def send_remote_state_files(files):
    try:
        if not isinstance(files, dict):
            return False
        encoded_files = {}
        for name, content in files.items():
            if isinstance(content, str):
                content = content.encode()
            if isinstance(content, bytes):
                try:
                    encoded_files[str(name)] = _ub.b2a_base64(content).rstrip(b'\n').decode()
                except Exception:
                    pass
        if not encoded_files:
            return False
        payload = {'files': encoded_files}
        payload_b64 = _ub.b2a_base64(ujson.dumps(payload).encode()).rstrip(b'\n').decode()
        await _send_chunked('STATE_FILES', payload_b64)
        return True
    except Exception as e:
        await log_error(f'send_remote_state_files failed: {e}')
        return False


async def wait_for_next_sync_ack(timeout_s=None, expected_batch_id=None):
    """
    Remote helper: wait for ACK:<uid>:NEXT:<seconds> from base.
    When expected_batch_id is provided, only ACKs with matching BID are accepted.
    Returns the next delay in seconds, or None on timeout / failure.
    """
    if str(getattr(settings, 'NODE_TYPE', 'base')).lower() != 'remote':
        return None

    if timeout_s is None:
        timeout_s = getattr(settings, 'REMOTE_ACK_WAIT_S', 90)
    try:
        timeout_s = max(15, int(timeout_s))
    except Exception:
        timeout_s = 90

    end_ts = time.time() + timeout_s
    my_uid = str(getattr(settings, 'UNIT_ID', ''))

    await debug_print(f"Waiting for ACK (timeout {timeout_s}s) ...", "REMOTE_NODE")

    while time.time() < end_ts:
        try:
            if lora is None:
                await asyncio.sleep_ms(100)
                continue

            # Try to receive a packet
            try:
                # Prefer non-blocking style receive if available
                if hasattr(lora, 'recv'):
                    msg, err = lora.recv(0)
                else:
                    msg, err = None, -1
            except TypeError:
                # Some drivers don't accept the timeout argument
                try:
                    msg, err = lora.recv()
                except Exception:
                    msg, err = None, -1
            except Exception:
                msg, err = None, -1

            if err == 0 and msg:
                try:
                    msg_str = msg.rstrip(b'\x00').decode()
                    msg_str = await _unsecure_message(msg_str)
                except Exception:
                    msg_str = None

                if msg_str and msg_str.startswith('ACK:'):
                    parts = msg_str.split(':')
                    # Expected format: ACK:<uid>:NEXT:<seconds>
                    if len(parts) >= 4 and parts[1] == my_uid and parts[2] == 'NEXT':
                        ack_bid = None
                        if len(parts) >= 6:
                            i = 4
                            while i + 1 < len(parts):
                                if parts[i] == 'BID':
                                    ack_bid = parts[i + 1]
                                    break
                                i += 2

                        if expected_batch_id is not None and str(ack_bid or '') != str(expected_batch_id):
                            await debug_print(
                                f"ACK BID mismatch; expected {expected_batch_id}, got {ack_bid}",
                                "WARN"
                            )
                            await asyncio.sleep_ms(20)
                            continue

                        try:
                            delay = max(10, int(parts[3]))
                            await debug_print(f"ACK received – next sync in {delay}s", "REMOTE_NODE")
                            return delay
                        except Exception:
                            pass
        except Exception:
            pass

        await asyncio.sleep_ms(80)

    await debug_print("ACK wait timed out", "REMOTE_NODE")
    return None

async def _fetch_remote_pending_command(remote_unit_id, remote_machine_id=None):
    """Base helper: fetch one queued command for a remote unit from UC/WP."""
    try:
        if settings.NODE_TYPE != 'base':
            return None
        wp_url = ''
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        req_mod = None
        if '_wp' in globals() and _wp is not None:
            try:
                wp_url = str(getattr(_wp, '_current_wp_url', lambda: '')() or '').strip()
            except Exception:
                wp_url = ''
            try:
                headers = getattr(_wp, '_auth_headers', lambda *_: headers)()
            except Exception:
                pass
            req_mod = getattr(_wp, 'requests', None)
        if not req_mod:
            try:
                import urequests as req_mod
            except Exception:
                req_mod = None
        if not wp_url or not req_mod:
            return None

        body = {
            'unit_id': str(remote_unit_id),
            'device_id': str(remote_unit_id),
            'machine_id': str(remote_machine_id or ''),
            'limit': 1,
        }
        resp = None
        try:
            try:
                resp = req_mod.post(wp_url.rstrip('/') + '/wp-json/tmon/v1/device/commands', json=body, headers=headers, timeout=8)
            except TypeError:
                resp = req_mod.post(wp_url.rstrip('/') + '/wp-json/tmon/v1/device/commands', json=body, headers=headers)
            status = int(getattr(resp, 'status_code', 0) or 0)
            if status not in (200, 201):
                return None
            parsed = None
            try:
                parsed = resp.json()
            except Exception:
                parsed = None
            commands = []
            if isinstance(parsed, dict) and isinstance(parsed.get('commands'), list):
                commands = parsed.get('commands')
            elif isinstance(parsed, list):
                commands = parsed
            if not commands:
                return None
            cmd = commands[0] if isinstance(commands[0], dict) else None
            if not cmd:
                return None
            ctype = str(cmd.get('type') or cmd.get('command') or '').strip().lower()
            payload = cmd.get('payload') if isinstance(cmd.get('payload'), dict) else (
                cmd.get('params') if isinstance(cmd.get('params'), dict) else (
                    cmd.get('data') if isinstance(cmd.get('data'), dict) else {}
                )
            )
            if ctype not in ('set_var', 'set_setting', 'settings_update', 'settings_change', 'relay_ctrl', 'toggle_relay'):
                return None
            return {
                'id': cmd.get('id'),
                'type': ctype,
                'payload': payload if isinstance(payload, dict) else {},
            }
        finally:
            try:
                if resp:
                    resp.close()
            except Exception:
                pass
    except Exception:
        return None


def _encode_ack_command(cmd_obj):
    try:
        if not isinstance(cmd_obj, dict):
            return ''
        raw = ujson.dumps(cmd_obj).encode()
        return _ub.b2a_base64(raw).rstrip(b'\n').decode()
    except Exception:
        return ''


def _decode_ack_command(encoded):
    try:
        if not encoded:
            return None
        raw = _ub.a2b_base64(str(encoded).encode()).decode()
        obj = ujson.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


async def _send_remote_command_result(result_payload):
    try:
        payload_b64 = _ub.b2a_base64(ujson.dumps(result_payload).encode()).rstrip(b'\n').decode()
        await _send_chunked('CMD_RESULT', payload_b64)
    except Exception as e:
        await log_error(f'send_remote_command_result failed: {e}')


async def _apply_remote_command_from_ack(cmd_obj):
    """Remote helper: apply command received via ACK and emit command result."""
    if not isinstance(cmd_obj, dict):
        return
    cmd_id = cmd_obj.get('id') or cmd_obj.get('job_id')
    ctype = str(cmd_obj.get('type') or cmd_obj.get('command') or '').strip().lower()
    payload = cmd_obj.get('payload') if isinstance(cmd_obj.get('payload'), dict) else (
        cmd_obj.get('params') if isinstance(cmd_obj.get('params'), dict) else (
            cmd_obj.get('data') if isinstance(cmd_obj.get('data'), dict) else {}
        )
    )
    ok = False
    result = {'type': ctype}
    try:
        if ctype in ('set_var', 'set_setting'):
            key = str(payload.get('key') or '').strip()
            if key:
                persist_custom_settings({key: payload.get('value')})
                ok = True
                result['staged'] = True
                result['key'] = key
        elif ctype in ('settings_update', 'settings_change') and isinstance(payload, dict):
            updates = {}
            for k, v in payload.items():
                sk = str(k or '').strip()
                if sk:
                    updates[sk] = v
            if updates:
                persist_custom_settings(updates)
                ok = True
                result['staged_count'] = len(updates)
        elif ctype in ('relay_ctrl', 'toggle_relay'):
            relay_num = payload.get('relay_num', payload.get('relay', '1'))
            state = payload.get('state', 'off')
            runtime = payload.get('runtime', payload.get('duration_s', 0))
            await toggle_relay(str(relay_num), str(state), str(runtime))
            ok = True
            result['executed'] = True
        elif ctype in ('suspend', 'resume', 'set_suspend'):
            try:
                from utils import persist_suspension_state
                if ctype == 'resume':
                    new_state = False
                elif ctype == 'suspend':
                    new_state = True
                else:
                    new_state = bool(payload.get('enabled', payload.get('suspended', True)))
                settings.DEVICE_SUSPENDED = bool(new_state)
                persist_suspension_state(settings.DEVICE_SUSPENDED)
                ok = True
                result['device_suspended'] = bool(settings.DEVICE_SUSPENDED)
            except Exception as se:
                ok = False
                result['reason'] = 'suspend_command_error'
                result['error'] = str(se)
        else:
            result['reason'] = 'unsupported_command_type'
    except Exception as e:
        ok = False
        result['reason'] = 'command_exec_error'
        result['error'] = str(e)

    if cmd_id is not None:
        await _send_remote_command_result({
            'id': cmd_id,
            'job_id': cmd_id,
            'unit_id': getattr(settings, 'UNIT_ID', ''),
            'machine_id': get_machine_id(),
            'ok': bool(ok),
            'status': 'done' if ok else 'failed',
            'result': result,
        })


async def _proxy_remote_command_result(remote_uid, payload):
    """Base helper: proxy remote command execution result to UC/WP."""
    try:
        if settings.NODE_TYPE != 'base' or not isinstance(payload, dict):
            return
        wp_url = ''
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        req_mod = None
        if '_wp' in globals() and _wp is not None:
            try:
                wp_url = str(getattr(_wp, '_current_wp_url', lambda: '')() or '').strip()
            except Exception:
                wp_url = ''
            try:
                headers = getattr(_wp, '_auth_headers', lambda *_: headers)()
            except Exception:
                pass
            req_mod = getattr(_wp, 'requests', None)
        if not req_mod:
            try:
                import urequests as req_mod
            except Exception:
                req_mod = None
        if not wp_url or not req_mod:
            return

        body = {
            'id': payload.get('id') or payload.get('job_id'),
            'job_id': payload.get('job_id') or payload.get('id'),
            'unit_id': payload.get('unit_id') or remote_uid,
            'machine_id': payload.get('machine_id') or '',
            'ok': bool(payload.get('ok')),
            'status': payload.get('status') or ('done' if bool(payload.get('ok')) else 'failed'),
            'result': payload.get('result') if isinstance(payload.get('result'), (dict, list, str, int, float, bool)) else {},
        }
        if not body['id']:
            return

        endpoints = [
            '/wp-json/tmon/v1/device/command-result',
            '/wp-json/tmon/v1/device/command-complete',
            '/wp-json/tmon/v1/device/ack',
        ]
        for ep in endpoints:
            resp = None
            try:
                try:
                    resp = req_mod.post(wp_url.rstrip('/') + ep, json=body, headers=headers, timeout=8)
                except TypeError:
                    resp = req_mod.post(wp_url.rstrip('/') + ep, json=body, headers=headers)
                status = int(getattr(resp, 'status_code', 0) or 0)
                if status in (200, 201, 202):
                    return
            except Exception:
                pass
            finally:
                try:
                    if resp:
                        resp.close()
                except Exception:
                    pass
    except Exception:
        return


async def process_remote_command_result(uid, st):
    try:
        payload = st.get('data', {}).get('CMD_RESULT')
        if isinstance(payload, dict):
            await _proxy_remote_command_result(uid, payload)
    except Exception as e:
        await log_error(f"Remote command result processor error for {uid}: {e}")
    finally:
        if 'CMD_RESULT' in st.get('types', set()):
            st['types'].discard('CMD_RESULT')
        if isinstance(st.get('data'), dict):
            st['data'].pop('CMD_RESULT', None)
        if isinstance(st.get('chunks'), dict):
            st['chunks'].pop('CMD_RESULT', None)


async def _send_lora_heartbeat():
    if settings.NODE_TYPE != 'remote':
        return
    try:
        rssi = lora.getRSSI() if lora is not None and hasattr(lora, 'getRSSI') else None
        snr = lora.getSNR() if lora is not None and hasattr(lora, 'getSNR') else None
        payload = {
            'rssi': rssi,
            'snr': snr,
            'missed_syncs': 0,
        }
        payload_b64 = _ub.b2a_base64(ujson.dumps(payload).encode()).rstrip(b'\n').decode()
        msg_str = f"TYPE:HEARTBEAT,UID:{settings.UNIT_ID},DATA:{payload_b64}"
        msg_str = await _secure_message(msg_str)
        await _send_with_retry(msg_str.encode())
        await debug_print("LoRa heartbeat sent", "LORA")
    except Exception as e:
        await log_error(f"Heartbeat send error: {e}")

# ===================== PERIODIC TASKS (unchanged) =====================
async def periodic_wp_sync():
    if settings.NODE_TYPE != 'base':
        return
    if not all((register_with_wp, send_settings_to_wp, fetch_settings_from_wp, send_data_to_wp, poll_ota_jobs)):
        await debug_print("periodic_wp_sync unavailable: WP helpers missing", "LORA")
        return
    while True:
        await register_with_wp()
        await send_settings_to_wp()
        await fetch_settings_from_wp()
        await send_data_to_wp()
        jobs = await poll_ota_jobs()
        for job in jobs:
            await handle_ota_job(job)
        await asyncio.sleep(300)

async def heartbeat_ping_loop():
    if settings.NODE_TYPE != 'base':
        return
    if not heartbeat_ping:
        await debug_print("heartbeat_ping_loop unavailable: heartbeat_ping helper missing", "LORA")
        return
    while True:
        await heartbeat_ping()
        await asyncio.sleep(60)

async def check_missed_syncs():
    if settings.NODE_TYPE != 'base':
        return
    while True:
        now = time.time()
        threshold = getattr(settings, 'LORA_MISSED_SYNC_THRESHOLD', 3)
        heartbeat_timeout = getattr(settings, 'LORA_HEARTBEAT_INTERVAL_S', 120) * 2
        next_sync_window = getattr(settings, 'LORA_NEXT_SYNC', 100) * 2
        for node_id, info in getattr(settings, 'REMOTE_NODE_INFO', {}).items():
            next_expected = info.get('next_expected')
            last_seen = info.get('last_heartbeat_ts') or info.get('last_rx') or 0
            missed = info.get('missed_syncs', 0)
            should_increment = False
            if next_expected and now > next_expected + next_sync_window:
                should_increment = True
            elif last_seen and now > last_seen + heartbeat_timeout:
                should_increment = True

            if should_increment:
                info['missed_syncs'] = missed + 1
                if info['missed_syncs'] > threshold:
                    await debug_print(f"Excessive missed syncs/heartbeats from {node_id}", "WARN")
            elif missed > 0:
                info['missed_syncs'] = 0
        save_remote_node_info()
        await asyncio.sleep(300)

async def handle_ota_job(job):
    try:
        if not job or not isinstance(job, dict):
            await debug_print("handle_ota_job: invalid job payload", 'OTA')
            return
        job_id = job.get('id') or job.get('job_id') or ''
        url = job.get('url') or job.get('download_url') or job.get('file')
        expected_sha = job.get('sha256') or job.get('expected_sha')
        manifest_url = job.get('manifest_url') or job.get('manifest')
        version_hint = job.get('version') or job.get('ver')

        if not url:
            await debug_print(f'handle_ota_job: no url in job {job_id}', 'OTA')
            return

        await debug_print(f'OTA job received id={job_id} url={url[:80]}', 'OTA')
        job_start_ts = time.time()
        try:
            if send_ota_job_status:
                await send_ota_job_status(job_id, 'started', {'url': url, 'started_at': job_start_ts})
        except Exception:
            pass

        try:
            import firmware_updater as fw
        except Exception:
            await debug_print('handle_ota_job: firmware_updater missing', 'ERROR')
            return

        # Start a background worker to perform the blocking download
        result_file = settings.LOG_DIR.rstrip('/') + f'/ota_job_{job_id or "temp"}.result.json'

        def _ota_worker():
            try:
                res = fw.download_and_apply_firmware(url, version_hint=version_hint, expected_sha=expected_sha, manifest_url=manifest_url)
            except Exception as e:
                res = {'ok': False, 'error': str(e)}
            res['worker_end_ts'] = time.time()
            try:
                import ujson as _uj
            except Exception:
                import json as _uj
            try:
                with open(result_file, 'w') as rf:
                    rf.write(_uj.dumps(res))
            except Exception:
                pass

        # Try to offload to a thread if available, else run in-process (blocking fallback)
        try:
            if _thread:
                try:
                    _thread.start_new_thread(_ota_worker, ())
                except Exception:
                    # fallback to CPython threading module
                    if threading:
                        try:
                            t = threading.Thread(target=_ota_worker, daemon=True)
                            t.start()
                        except Exception:
                            _ota_worker()
                    else:
                        _ota_worker()
            else:
                # No _thread; try CPython threading module
                if threading:
                    try:
                        t = threading.Thread(target=_ota_worker, daemon=True)
                        t.start()
                    except Exception:
                        _ota_worker()
                else:
                    # No threading available; perform blocking call but still report status
                    _ota_worker()
        except Exception as e:
            await debug_print(f'OTA worker start failed: {e}', 'ERROR')
            return

        # Poll for result (non-blocking) with timeout
        timeout = int(getattr(settings, 'OTA_JOB_TIMEOUT_S', 1800))
        poll_interval = 2
        waited = 0
        while waited < timeout:
            try:
                if os.path.exists(result_file):
                    try:
                        with open(result_file, 'r') as rf:
                            try:
                                j = __import__('ujson').loads(rf.read())
                            except Exception:
                                import json as _json
                                j = _json.loads(rf.read())
                    except Exception:
                        j = None
                    try:
                        os.remove(result_file)
                    except Exception:
                        pass
                    if isinstance(j, dict) and j.get('ok'):
                        pending_file = getattr(settings, 'OTA_PENDING_FILE', None) or (settings.LOG_DIR.rstrip('/') + '/ota_pending.flag')
                        job_end_ts = time.time()
                        duration = job_end_ts - job_start_ts
                        try:
                            with open(pending_file, 'w') as pf:
                                pf.write(str(version_hint or j.get('sha256') or job_id or 'downloaded'))
                        except Exception:
                            pass
                        await debug_print(f'OTA job {job_id} downloaded OK -> {j.get("path")} (duration: {duration:.1f}s)', 'OTA')
                        try:
                            await display_message('OTA Downloaded', 3)
                        except Exception:
                            pass
                        try:
                            if send_ota_job_status:
                                await send_ota_job_status(job_id, 'downloaded', {'path': j.get('path'), 'sha256': j.get('sha256'), 'started_at': job_start_ts, 'completed_at': job_end_ts, 'duration_s': duration})
                        except Exception:
                            pass
                        return
                    else:
                        err = j.get('error') if isinstance(j, dict) else 'unknown'
                        job_end_ts = time.time()
                        duration = job_end_ts - job_start_ts
                        await debug_print(f'OTA job {job_id} failed: {err}', 'ERROR')
                        try:
                            if send_ota_job_status:
                                await send_ota_job_status(job_id, 'failed', {'error': err, 'started_at': job_start_ts, 'completed_at': job_end_ts, 'duration_s': duration})
                        except Exception:
                            pass
                        return
            except Exception:
                pass
            await asyncio.sleep(poll_interval)
            waited += poll_interval

        # timeout
        job_end_ts = time.time()
        duration = job_end_ts - job_start_ts
        await debug_print(f'OTA job {job_id} timed out after {timeout}s', 'ERROR')
        try:
            if send_ota_job_status:
                await send_ota_job_status(job_id, 'failed', {'error': 'timeout', 'started_at': job_start_ts, 'completed_at': job_end_ts, 'duration_s': duration})
        except Exception:
            pass
    except Exception as e:
        await debug_print(f'handle_ota_job top-level exc: {e}', 'ERROR')

# ===================== MAIN LOOP =====================
async def connectLora():
    global lora, last_rx_ts, last_lora_activity_ts
    if not getattr(settings, 'ENABLE_LORA', True):
        return False

    await debug_print(f"Enabling LoRa - {getattr(settings, 'FIRMWARE_VERSION', 'unknown')}", "LORA")
    await display_message("LoRa Starting...", 1)

    async with pin_lock:
        if not await init_lora():
            return False
    last_lora_activity_ts = time.time()

    if settings.NODE_TYPE == 'base':
        asyncio.create_task(base_packet_processor())
        await debug_print("Base background processor started", "BASE_NODE")
        if heartbeat_ping:
            asyncio.create_task(heartbeat_ping_loop())
            await debug_print("Base heartbeat ping loop started", "BASE_NODE")

    if settings.NODE_TYPE == 'remote':
        uid = settings.UNIT_ID
        stagger_seed = 0
        for c in uid:
            stagger_seed = (stagger_seed * 31 + ord(c)) % 1000000
        initial_stagger = stagger_seed % 35
        await debug_print(f"Remote Check-In Stagger {initial_stagger}s", "REMOTE_NODE")
        await asyncio.sleep(initial_stagger)

    STATE_IDLE = 0
    STATE_WAIT_RESPONSE = 2
    state = STATE_IDLE
    failure_count = 0
    retry_count = 0
    max_retries_per_cycle = int(getattr(settings, 'LORA_MAX_RETRIES', 3))

    if settings.NODE_TYPE == 'remote':
        sync_rate = getattr(settings, 'LORA_SYNC_RATE', 300)
        response_timeout = 20   # shortened to reduce crosstalk window
        ota_wait_deadline = 0
        awaiting_ota_session = None
    else:
        sync_rate = 10
        response_timeout = 30

    last_heartbeat_ts = 0
    while True:
        try:
            current_time = time.time()

            # ---------- Safer LoRa health watchdog ----------
            # Only re-init if there has been NO activity for a long time.
            # Never use the old aggressive watchdog on base/wifi.
            watch_timeout_s = int(getattr(settings, 'LORA_WATCHDOG_TIMEOUT_S', 300))
            is_base_or_wifi = str(getattr(settings, 'NODE_TYPE', '')).lower() in ('base', 'wifi')

            if not is_base_or_wifi:
                # Remotes can keep a shorter watchdog.
                if current_time - last_lora_activity_ts > 120:
                    await debug_print("LoRa health watchdog (remote) - re-init", "WARN")
                    await init_lora()
                    last_lora_activity_ts = current_time
            else:
                # Base/wifi only after a long quiet period.
                if current_time - last_lora_activity_ts > watch_timeout_s:
                    await debug_print("LoRa health watchdog (base) - long idle re-init", "WARN")
                    await init_lora()
                    last_lora_activity_ts = current_time

            if lora is None or not hasattr(lora, '_events'):
                if not await init_lora():
                    await asyncio.sleep(8)
                    continue

            if settings.NODE_TYPE == 'base':
                await ensure_lora_listening()

            if current_time - last_rx_ts > 70:
                sdata.lora_SigStr = -120
                sdata.LORA_CONNECTED = False

            if settings.NODE_TYPE == 'remote':
                heartbeat_interval = getattr(settings, 'LORA_HEARTBEAT_INTERVAL_S', 120)
                if current_time - last_heartbeat_ts >= heartbeat_interval:
                    await _send_lora_heartbeat()
                    last_heartbeat_ts = current_time

                if state == STATE_IDLE:
                    awaiting_ota_session = None
                    ota_wait_deadline = 0
                    await debug_print("Remote: starting full check-in (periodic)", "REMOTE_NODE")
                    await display_message("TX Data...", 0.8)
                    ts = time.time()
                    data_str = (
                        f"T:{ts},U:{settings.UNIT_ID},M:{get_machine_id()},"
                        f"NET:{getattr(settings,'LORA_NETWORK_NAME','tmon')},PASS:{getattr(settings,'LORA_NETWORK_PASSWORD','12345')},"
                        f"C:{getattr(settings,'COMPANY','')},S:{getattr(settings,'SITE','')},Z:{getattr(settings,'ZONE','')},K:{getattr(settings,'CLUSTER','')},"
                        f"R:{sdata.loop_runtime},SR:{sdata.script_runtime},"
                        f"TC:{getattr(sdata,'cur_temp_c',None)},TF:{getattr(sdata,'cur_temp_f',None)},"
                        f"B:{getattr(sdata,'cur_bar_pres',None)},H:{getattr(sdata,'cur_humid',None)},"
                        f"DTC:{getattr(sdata,'cur_device_temp_c',None)},DTF:{getattr(sdata,'cur_device_temp_f',None)},"
                        f"DB:{getattr(sdata,'cur_device_bar_pres',None)},DH:{getattr(sdata,'cur_device_humid',None)}"
                    )
                    data_str = await _secure_message(data_str)
                    await _send_with_retry(data_str.encode())
                    await ensure_lora_listening()
                    await asyncio.sleep(random.uniform(1.0, 2.0))

                    settings_dict = {k: getattr(settings, k) for k in dir(settings) if not k.startswith('__') and not callable(getattr(settings, k))}
                    settings_b64 = _ub.b2a_base64(ujson.dumps(settings_dict).encode()).rstrip(b'\n').decode()
                    await _send_chunked("SETTINGS", settings_b64)
                    await ensure_lora_listening()

                    sdata_dict = {k: v for k, v in getattr(sdata, '__dict__', {}).items() if not k.startswith('__') and not callable(v)}
                    sdata_b64 = _ub.b2a_base64(ujson.dumps(sdata_dict).encode()).rstrip(b'\n').decode()
                    await _send_chunked("SDATA", sdata_b64)
                    await ensure_lora_listening()

                    state = STATE_WAIT_RESPONSE
                    start_wait = time.time()
                    retry_count = 0

                elif state == STATE_WAIT_RESPONSE:
                    if lora and hasattr(lora, '_events') and (lora._events() & lora.RX_DONE):
                        last_lora_activity_ts = time.time()
                        msg, err = lora.recv()
                        if err == 0 and msg:
                            msg_str = msg.rstrip(b'\x00').decode()
                            msg_str = await _unsecure_message(msg_str)
                            if msg_str and msg_str.startswith('ACK:'):
                                parts = msg_str.split(':')
                                # STRICT UID CHECK - prevents accepting ACK meant for another remote
                                if len(parts) >= 4 and parts[1] == settings.UNIT_ID and parts[2] == 'NEXT':
                                    await debug_print("Remote: ACK received for this node", "REMOTE_NODE")
                                    next_delay = int(parts[3])
                                    ack_cmd = None
                                    ack_ota_session = None
                                    ack_ota_ver = None
                                    if len(parts) >= 6:
                                        i = 4
                                        while i + 1 < len(parts):
                                            if parts[i] == 'CMD':
                                                ack_cmd = _decode_ack_command(parts[i + 1])
                                            elif parts[i] == 'OTA':
                                                ack_ota_session = parts[i + 1]
                                            elif parts[i] == 'VER':
                                                ack_ota_ver = parts[i + 1]
                                            i += 2
                                    if isinstance(ack_cmd, dict):
                                        await debug_print("Remote: received command via ACK", "REMOTE_NODE")
                                        await _apply_remote_command_from_ack(ack_cmd)
                                    last_rx_ts = time.time()
                                    sdata.lora_SigStr = lora.getRSSI() if hasattr(lora, 'getRSSI') else -60
                                    sdata.lora_snr = lora.getSNR() if hasattr(lora, 'getSNR') else 0
                                    sdata.LORA_CONNECTED = True
                                    if ack_ota_session:
                                        _reset_remote_ota_rx()
                                        awaiting_ota_session = ack_ota_session
                                        ota_wait_deadline = time.time() + max(30, int(getattr(settings, 'REMOTE_ACK_WAIT_S', 8)) + 120)
                                        await debug_print(
                                            f"Remote: OTA window opened session={ack_ota_session} ver={ack_ota_ver}",
                                            "OTA"
                                        )
                                        await ensure_lora_listening()
                                        await asyncio.sleep(0.1)
                                        continue
                                    await ensure_lora_listening()
                                    await asyncio.sleep(0.5)
                                    state = STATE_IDLE
                                    sleep_time = next_delay or (sync_rate + random.randint(-30, 30))
                                    await asyncio.sleep(max(10, sleep_time))
                                    continue
                                else:
                                    await debug_print("Ignored ACK for different UID", "REMOTE_NODE")
                            elif msg_str and msg_str.startswith('TYPE:') and awaiting_ota_session:
                                handled = False
                                try:
                                    handled = await _remote_handle_lora_ota_wire_message(msg_str)
                                except Exception as ota_rx_e:
                                    await log_error(f"remote ota rx error: {ota_rx_e}")
                                    handled = False
                                if handled:
                                    last_rx_ts = time.time()
                                    await ensure_lora_listening()
                                    await asyncio.sleep(0.05)
                                    continue
                        await ensure_lora_listening()

                    if awaiting_ota_session and ota_wait_deadline and time.time() > ota_wait_deadline:
                        await debug_print("Remote: OTA window timeout; continuing normal schedule", "WARN")
                        awaiting_ota_session = None
                        ota_wait_deadline = 0
                        state = STATE_IDLE
                        await asyncio.sleep(2)
                        continue

                    if (not awaiting_ota_session) and (time.time() - start_wait > response_timeout):
                        retry_count += 1
                        await debug_print(f"Remote: no ACK (retry {retry_count}/{max_retries_per_cycle})", "WARN")
                        if retry_count < max_retries_per_cycle:
                            state = STATE_IDLE
                            backoff_base = getattr(settings, 'LORA_RETRY_BASE_DELAY_S', 2)
                            max_backoff = getattr(settings, 'LORA_MAX_BACKOFF_S', 90)
                            delay = min(max_backoff, backoff_base * (2 ** (retry_count - 1)))
                            delay += random.uniform(0, backoff_base)
                            await asyncio.sleep(delay)
                            continue
                        else:
                            failure_count += 1
                            backoff_base = getattr(settings, 'LORA_RETRY_BASE_DELAY_S', 2)
                            max_backoff = getattr(settings, 'LORA_MAX_BACKOFF_S', 90)
                            sleep_time = min(max_backoff, backoff_base * (2 ** failure_count))
                            sleep_time += random.uniform(0, backoff_base)
                            state = STATE_IDLE
                            await asyncio.sleep(max(10, sleep_time))
                            retry_count = 0
                            continue

            else:  # BASE NODE
                if lora and hasattr(lora, '_events') and (lora._events() & lora.RX_DONE):
                    last_lora_activity_ts = current_time
                    msg, err = lora.recv()
                    if err == 0 and msg:
                        await handle_incoming_packet(msg)
                    await ensure_lora_listening()

            await asyncio.sleep_ms(25)

        except Exception as e:
            await log_error(f"Main LoRa loop error: {e}")
            await display_message("LoRa Err", 2)
            lora = None
            if settings.NODE_TYPE == 'remote':
                state = STATE_IDLE
                retry_count = 0
            await asyncio.sleep(3)
            gc.collect()