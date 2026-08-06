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


def crc16_ccitt(data, crc=0xFFFF):
    """CRC-16/CCITT-FALSE style (poly 0x1021)."""
    if isinstance(data, str):
        data = data.encode()
    for b in data:
        crc ^= (b << 8) & 0xFFFF
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def _format_crc(crc_val):
    """Always exactly 4 hex digits."""
    try:
        return '{:04X}'.format(int(crc_val) & 0xFFFF)
    except Exception:
        return '0000'


def _parse_crc_field(raw):
    """
    Extract CRC from a CRC: field value.
    - Accept only hex characters
    - Use the first 4 hex digits (tolerate trailing RF garbage)
    - Return (ok:bool, crc_int_or_None, normalized_hex)
    """
    if raw is None:
        return False, None, ''
    s = str(raw).strip()
    if s.upper().startswith('CRC:'):
        s = s[4:]
    hx = ''
    for ch in s:
        o = ord(ch)
        if (48 <= o <= 57) or (65 <= o <= 70) or (97 <= o <= 102):
            hx += ch
            if len(hx) >= 4:
                break
        else:
            break
    if len(hx) < 4:
        return False, None, hx.upper()
    hx4 = hx[:4].upper()
    try:
        return True, int(hx4, 16), hx4
    except Exception:
        return False, None, hx4


def verify_app_crc(body, crc_raw):
    """Return (ok: bool, detail: str) for envelope CRC validation."""
    ok, exp, hx4 = _parse_crc_field(crc_raw)
    if not ok:
        return False, 'Invalid CRC field: %s' % str(crc_raw)[:16]
    actual = crc16_ccitt(body if isinstance(body, bytes) else body.encode())
    if actual != exp:
        return False, 'CRC mismatch: expected %04X, got %s' % (actual, hx4)
    return True, 'CRC ok %s' % hx4


async def debug_crc_sample():
    sample = 'HELLO:unit-test'
    sec = await _secure_message(sample)
    await debug_print('SEC sample: %s' % sec, 'LORA')


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


def _is_lora_hub_node():
    """True when this node should run LoRa hub/base logic."""
    try:
        node_type = str(getattr(settings, 'NODE_TYPE', '') or '').lower()
        return bool(getattr(settings, 'ENABLE_LORA', True)) and node_type in ('base', 'wifi')
    except Exception:
        return False

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
_sec_log_last = {}
_sec_log_count = {}

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
_crc_selftest_done = False
_relay_dupe = []


def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return int(default)


def _relay_dupe_seen(pid):
    global _relay_dupe
    if not pid:
        return True
    if pid in _relay_dupe:
        return True
    _relay_dupe.append(pid)
    max_n = int(getattr(settings, 'LORA_RELAY_DUPE_CACHE', 32))
    while len(_relay_dupe) > max_n:
        _relay_dupe.pop(0)
    return False


async def maybe_relay_forward(clear, rssi=None):
    _ = rssi
    if not bool(getattr(settings, 'ENABLE_LORA_RELAY', False)):
        return False
    nt = str(getattr(settings, 'NODE_TYPE', '')).lower()
    if nt in ('base', 'wifi'):
        return False

    if bool(getattr(settings, 'LORA_RELAY_ONLY_WHEN_HUB_SILENT', True)):
        last = float(getattr(settings, '_last_hub_heard_ts', 0) or 0)
        if last and (time.time() - last) < float(getattr(settings, 'LORA_HUB_HEARD_S', 45)):
            return False

    if not str(clear).startswith('FWD:'):
        return False

    try:
        rest = str(clear)[4:]
        ttl_s, rest = rest.split(':', 1)
        origin, rest = rest.split(':', 1)
        seq_s, inner = rest.split(':', 1)
        ttl, seq = int(ttl_s), int(seq_s)
    except Exception:
        return False

    pid = '%s:%d' % (origin, seq)
    if _relay_dupe_seen(pid):
        return False
    if ttl <= 1:
        return False

    new_body = 'FWD:%d:%s:%d:%s' % (ttl - 1, origin, seq, inner)
    await asyncio.sleep_ms(int(getattr(settings, 'LORA_RELAY_FORWARD_DELAY_MS', 80)) + (seq & 0x3F))
    secured = await _secure_message(new_body, remote_uid=origin)
    ok = await _safe_send(secured.encode() if isinstance(secured, str) else secured)
    await debug_print('RELAY fwd origin=%s ttl=%d ok=%s' % (origin, ttl - 1, ok), 'RELAY')
    try:
        await ensure_lora_listening()
    except Exception:
        pass
    return ok


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
    if not _is_lora_hub_node():
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


async def _sec_log(msg, min_interval_s=10):
    """Avoid flooding logs with repeated CRC/HMAC failures."""
    now = time.time()
    key = str(msg)[:40]
    max_burst = 3
    last = _sec_log_last.get(key, 0)
    cnt = _sec_log_count.get(key, 0)
    if (now - last) < min_interval_s and cnt >= max_burst:
        return
    if (now - last) >= min_interval_s:
        cnt = 0
    _sec_log_last[key] = now
    _sec_log_count[key] = cnt + 1
    try:
        await debug_print(f"SEC: {msg}", "LORA")
    except Exception:
        pass
    try:
        await log_error(msg)
    except Exception:
        try:
            print('[LORA-SEC]', msg)
        except Exception:
            pass


async def _log_security_error(key, message, interval_s=5):
    # Compatibility wrapper used by existing code paths.
    _ = key
    await _sec_log(message, min_interval_s=interval_s)

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
                sf=getattr(settings, 'SF', 10), cr=getattr(settings, 'CR', 7),
                syncWord=getattr(settings, 'SYNC_WORD', 0xF4), power=getattr(settings, 'POWER', 17),
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
        pending_cmd = None
        try:
            pending_cmd = await _fetch_remote_pending_command(uid, remote_machine_id)
        except Exception as cmd_fetch_e:
            await log_error(f"Pending command fetch error for {uid}: {cmd_fetch_e}")

        ack_delay = calculate_next_delay(uid)
        ack_msg = f"ACK:{uid}:NEXT:{ack_delay}"
        if isinstance(pending_cmd, dict):
            encoded_cmd = _encode_ack_command(pending_cmd)
            if encoded_cmd:
                ack_msg += f":CMD:{encoded_cmd}"
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
            await _safe_send(ack_msg.encode(), remote_uid=uid)
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
                    await _safe_send(ack_msg.encode(), remote_uid=uid)
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


async def _send_final_ack(remote_uid, batch_id=None, reason='', remote_machine_id=None):
    """Send a final ACK to a remote and include optional batch marker."""
    try:
        next_delay = calculate_next_delay(remote_uid)
        ack_msg = f"ACK:{remote_uid}:NEXT:{next_delay}"
        if batch_id:
            ack_msg += f":BID:{batch_id}"

        # Opportunistically piggyback one queued command for this remote.
        try:
            if not remote_machine_id:
                node_meta = getattr(settings, 'REMOTE_NODE_INFO', {}).get(str(remote_uid), {})
                if isinstance(node_meta, dict):
                    remote_machine_id = node_meta.get('MACHINE_ID')
            pending_cmd = await _fetch_remote_pending_command(remote_uid, remote_machine_id)
            if isinstance(pending_cmd, dict):
                encoded_cmd = _encode_ack_command(pending_cmd)
                if encoded_cmd:
                    ack_msg += f":CMD:{encoded_cmd}"
        except Exception as cmd_e:
            await log_error(f"Final ACK command piggyback error for {remote_uid}: {cmd_e}")

        ack_msg = await _secure_message(ack_msg, remote_uid=remote_uid)
        await _safe_send(ack_msg.encode(), remote_uid=remote_uid)
        if reason:
            await debug_print(
                f"FINAL ACK sent to {remote_uid} (next={next_delay}s, reason={reason})",
                "BASE_NODE"
            )
        else:
            await debug_print(
                f"FINAL ACK sent to {remote_uid} (next={next_delay}s)",
                "BASE_NODE"
            )

        # Keep per-remote sync schedule current for watcher/missed-sync logic.
        try:
            now = time.time()
            if not hasattr(settings, 'REMOTE_NODE_INFO') or settings.REMOTE_NODE_INFO is None:
                settings.REMOTE_NODE_INFO = {}
            st = settings.REMOTE_NODE_INFO.setdefault(str(remote_uid), {})
            st['next_expected'] = now + int(next_delay)
            st['last_sync_ts'] = now
            st['missed_syncs'] = 0
            save_remote_node_info()
            await debug_print(
                f"Registered {remote_uid} next_sync in {next_delay}s",
                "BASE_NODE"
            )
        except Exception:
            pass

        return next_delay
    except Exception as e:
        await log_error(f"Final ACK error for {remote_uid}: {e}")
        return None


async def _maybe_force_ack_on_silence(remote_uid, st):
    try:
        silent_need = float(getattr(settings, 'LORA_SESSION_SILENCE_S', 5))
        last = float(st.get('last_chunk_ts') or 0)
        if last <= 0:
            return
        if (time.time() - last) < silent_need:
            return
        if not st.get('session_active'):
            return

        chunks = (st.get('chunks') or {}).get('FIELD_DATA') or {}
        if not chunks and not st.get('saw_end'):
            return

        next_delay = await _send_final_ack(remote_uid, batch_id=st.get('batch_id'), reason='silence')
        await debug_print(
            f"Silence ACK to {remote_uid} ok={bool(next_delay)}",
            "BASE_NODE"
        )
        st['session_active'] = False
        try:
            st.get('chunks', {}).pop('FIELD_DATA', None)
        except Exception:
            pass
        st.pop('chunk_first_ts', None)
        st.pop('last_chunk_ts', None)
        st.pop('chunk_total', None)
        st.pop('batch_id', None)
        st.pop('saw_end', None)
    except Exception as e:
        await log_error(f"Silence ACK handler error for {remote_uid}: {e}")

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
            handled_field_data = False

            if uid not in settings.REMOTE_NODE_INFO:
                settings.REMOTE_NODE_INFO[uid] = {'types': set(), 'last_rx': current_time, 'data': {}, 'chunks': {}}
            st = settings.REMOTE_NODE_INFO[uid]

            orig_type = packet_type[:-6] if packet_type.endswith('_CHUNK') else packet_type
            if packet_type == 'HELLO':
                remote_uid = str(parsed_data or uid or '').strip()
                try:
                    remote_uid = remote_uid.split(':', 1)[-1].strip().split('|')[0].strip()
                except Exception:
                    pass
                if not remote_uid:
                    remote_uid = str(uid or 'unknown').strip()

                await debug_print(f"HELLO from {remote_uid}", "BASE_NODE")

                if not hasattr(settings, 'REMOTE_NODE_INFO') or settings.REMOTE_NODE_INFO is None:
                    settings.REMOTE_NODE_INFO = {}
                if remote_uid not in settings.REMOTE_NODE_INFO:
                    settings.REMOTE_NODE_INFO[remote_uid] = {}
                st = settings.REMOTE_NODE_INFO[remote_uid]

                now = time.time()
                st['last_hello_ts'] = now
                st['last_rx'] = now
                st['session_active'] = True
                st['saw_end'] = False
                st['chunks'] = {'FIELD_DATA': {}}
                st['base_uid'] = str(getattr(settings, 'UNIT_ID', '') or '')
                st['chunk_first_ts'] = now
                st['last_chunk_ts'] = now
                st['missed_syncs'] = 0
                try:
                    if not hasattr(settings, 'LORA_PEER_COUNTERS') or settings.LORA_PEER_COUNTERS is None:
                        settings.LORA_PEER_COUNTERS = {}
                    settings.LORA_PEER_COUNTERS.setdefault(remote_uid, {'tx': 0, 'rx': 0})
                except Exception:
                    pass
                try:
                    save_remote_node_info()
                except Exception:
                    pass

                try:
                    chunk_sz = int(getattr(settings, 'LORA_CHUNK_SIZE', 100) or 100)
                    base_uid = str(getattr(settings, 'UNIT_ID', '') or '')
                    ready = f"READY:{remote_uid}:BASE:{base_uid}:CHUNKSZ:{chunk_sz}"
                    ready = await _secure_message(ready, remote_uid=remote_uid)
                    ok = await _safe_send(ready.encode(), remote_uid=remote_uid)
                    await debug_print(
                        f"READY sent to {remote_uid} ok={ok} chunk={chunk_sz}",
                        "BASE_NODE"
                    )
                    try:
                        from oled import display_message
                        await display_message("READY", 0.6)
                    except Exception:
                        pass
                    try:
                        await ensure_lora_listening()
                    except Exception:
                        pass
                except Exception as e:
                    await log_error(f"READY send FAILED for {remote_uid}: {e}")

                lora_rx_queue.task_done()
                await _maybe_force_ack_on_silence(remote_uid, st)
                gc.collect()
                continue

            if packet_type == 'END':
                end_info = parsed_data if isinstance(parsed_data, dict) else {}
                remote_uid = str(end_info.get('uid') or uid or '').strip()
                total = _safe_int(end_info.get('total'), 0)
                batch_id = end_info.get('batch_id')
                await debug_print(
                    f"END from {remote_uid} total={total}",
                    "BASE_NODE"
                )
                st['saw_end'] = True
                st['batch_id'] = batch_id
                next_delay = await _send_final_ack(remote_uid, batch_id=batch_id, reason='end')
                await debug_print(
                    f"FINAL ACK to {remote_uid} ok={bool(next_delay)} next={int(next_delay or 0)}",
                    "BASE_NODE"
                )
                try:
                    await ensure_lora_listening()
                except Exception:
                    pass

                if remote_uid in settings.REMOTE_NODE_INFO:
                    rst = settings.REMOTE_NODE_INFO[remote_uid]
                    rst.get('chunks', {}).pop('FIELD_DATA', None)
                    rst.pop('chunk_first_ts', None)
                    rst.pop('last_chunk_ts', None)
                    rst.pop('chunk_total', None)
                    rst.pop('batch_id', None)
                    rst.pop('session_active', None)
                    rst.pop('saw_end', None)

                lora_rx_queue.task_done()
                gc.collect()
                continue

            if packet_type.endswith('_CHUNK'):
                if 'chunks' not in st:
                    st['chunks'] = {}
                if orig_type not in st['chunks']:
                    st['chunks'][orig_type] = {}
                try:
                    cn, total = map(int, packet.get('chunk_info', '0/0').split('/'))

                    # New burst detection: remote restarted chunking from 0, clear stale partials.
                    if cn == 0 and st.get('chunks', {}).get(orig_type):
                        st['chunks'][orig_type] = {}
                        st['chunk_first_ts'] = time.time()
                        await debug_print(f"New burst detected for {uid} - cleared old chunks", "BASE_NODE")

                    if orig_type not in st.get('chunks', {}):
                        st.setdefault('chunks', {})[orig_type] = {}
                        st['chunk_first_ts'] = time.time()

                    if not st['chunks'][orig_type]:
                        st['chunk_first_ts'] = time.time()
                    st['last_chunk_ts'] = time.time()
                    st['chunk_total'] = total
                    bid = packet.get('batch_id')
                    if bid:
                        st['batch_id'] = bid
                    st['chunks'][orig_type][cn] = parsed_data
                    last_lora_activity_ts = time.time()
                    st['last_rx'] = current_time

                    have = len(st['chunks'][orig_type])
                    await debug_print(
                        f"Stored CHUNK {cn}/{total} for {orig_type} from {uid} (have {have}/{total})",
                        "BASE_NODE"
                    )

                    if have == total and all(k in st['chunks'][orig_type] for k in range(total)):
                        assembled_b64 = ''.join(st['chunks'][orig_type][j] for j in range(total))
                        json_data = _ub.a2b_base64(assembled_b64.encode()).decode()
                        parsed_dict = ujson.loads(json_data)
                        st['data'][orig_type] = parsed_dict
                        st['types'].add(orig_type)
                        del st['chunks'][orig_type]
                        st.pop('chunk_first_ts', None)
                        st.pop('chunk_total', None)
                        st.pop('last_chunk_ts', None)
                        await debug_print(f"FULLY ASSEMBLED {orig_type} ({total} chunks) for {uid}", "BASE_NODE")
                        if orig_type == 'FIELD_DATA':
                            await process_remote_field_data(uid, st)
                            handled_field_data = True
                except Exception as e:
                    await log_error(f"Chunk parse error for {uid}: {e}")

            else:
                st['types'].add(packet_type)
                st['data'][packet_type] = parsed_data
                st['last_rx'] = current_time

            # Only process FIELD_DATA after it is fully assembled (or non-chunk payload).
            if orig_type == 'FIELD_DATA' and ('FIELD_DATA' in st.get('types', set())) and not handled_field_data:
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
                if current_time - st.get('last_rx', 0) > 60:
                    del chunks_dict[t]
                    await debug_print(f"Discarded partial {t} chunks for {uid} (timeout)", "BASE_NODE")

            await _maybe_force_ack_on_silence(uid, st)
            lora_rx_queue.task_done()
            gc.collect()
        except Exception as e:
            await log_error(f"Background packet processor error: {e}")
            await asyncio.sleep(1)


async def check_incomplete_bursts():
    await debug_print("Incomplete-burst checker started (FORCE v3)", "BASE_NODE")
    while True:
        try:
            now = time.time()
            info = getattr(settings, 'REMOTE_NODE_INFO', {})
            for uid, st in list(info.items()):
                if not isinstance(st, dict):
                    continue
                field_chunks = (st.get('chunks') or {}).get('FIELD_DATA')
                if not isinstance(field_chunks, dict) or not field_chunks:
                    continue

                last_ts = float(st.get('last_chunk_ts') or 0)
                if last_ts == 0:
                    continue

                silent = now - last_ts

                silence_limit = float(getattr(settings, 'LORA_SESSION_SILENCE_S', 4) or 4)

                # Force ACK after short session silence.
                if silent >= silence_limit:
                    have = len(field_chunks)
                    total = int(st.get('chunk_total') or 0)
                    batch_id = st.get('batch_id')
                    await debug_print(
                        f"FORCING ACK {uid} after {silent:.0f}s silence "
                        f"(have {have}/{total})", "BASE_NODE"
                    )
                    await _send_final_ack(uid, batch_id=batch_id, reason='checker')

                    # Clear so we don't keep firing
                    st.get('chunks', {}).pop('FIELD_DATA', None)
                    st.pop('chunk_first_ts', None)
                    st.pop('last_chunk_ts', None)
                    st.pop('chunk_total', None)
                    st.pop('batch_id', None)
        except Exception as e:
            await log_error(f"check_incomplete_bursts: {e}")
        await asyncio.sleep(2)


async def handle_simple_session_hub(clear):
    """
    SIMPLE SESSION ONLY:
      HELLO -> READY
      END   -> ACK
      FIELD_DATA_CHUNK -> optional assemble; no SETTINGS/SDATA dependency
    """
    if not clear:
        return False
    clear = str(clear).strip()

    if clear.startswith('FWD:'):
        await debug_print('Simple mode: ignore FWD frame', 'BASE_NODE')
        return True

    if clear.startswith('HELLO:'):
        try:
            remote_uid = clear.split(':', 1)[1].strip().split('|')[0].strip()
        except Exception:
            remote_uid = 'unknown'
        await debug_print('HELLO from %s' % remote_uid, 'BASE_NODE')

        if not hasattr(settings, 'REMOTE_NODE_INFO') or settings.REMOTE_NODE_INFO is None:
            settings.REMOTE_NODE_INFO = {}
        st = settings.REMOTE_NODE_INFO.setdefault(remote_uid, {})
        st['session_active'] = True
        st['chunks'] = []
        st['chunk_total'] = None
        try:
            import utime as _t
            st['last_hello_ts'] = _t.time()
        except Exception:
            pass

        chunk_sz = int(getattr(settings, 'LORA_CHUNK_SIZE', 80))
        base_uid = str(getattr(settings, 'UNIT_ID', '') or '')
        ready = 'READY:%s:BASE:%s:CHUNKSZ:%d' % (remote_uid, base_uid, chunk_sz)
        try:
            secured = await _secure_message(ready, remote_uid=remote_uid)
            data = secured.encode() if isinstance(secured, str) else secured
            ok = await _safe_send(data, remote_uid=remote_uid)
        except Exception as e:
            ok = False
            await debug_print('READY send error: %s' % e, 'ERROR')
        await debug_print('READY sent to %s ok=%s' % (remote_uid, ok), 'BASE_NODE')
        try:
            await ensure_lora_listening()
        except Exception:
            pass
        return True

    if 'FIELD_DATA_CHUNK' in clear or clear.startswith('TYPE:FIELD_DATA_CHUNK'):
        uid = ''
        idx = -1
        total = 0
        try:
            for part in clear.replace(',', ' ').split():
                if part.startswith('UID:'):
                    uid = part[4:].strip()
                if part.startswith('CHUNK:'):
                    frac = part[6:].strip()
                    a, b = frac.split('/')
                    idx, total = int(a), int(b)
        except Exception:
            pass
        if uid:
            st = getattr(settings, 'REMOTE_NODE_INFO', {}).setdefault(uid, {})
            st['session_active'] = True
            st['chunk_total'] = total
            ch = st.setdefault('chunks', [])
            if idx >= 0:
                while len(ch) <= idx:
                    ch.append(None)
                ch[idx] = clear
            await debug_print('Chunk %s %s/%s' % (uid, idx, total), 'BASE_NODE')
        return True

    if clear.startswith('END:'):
        parts = clear.split(':')
        remote_uid = parts[1].strip() if len(parts) > 1 else 'unknown'
        total = 0
        try:
            if len(parts) > 2:
                total = int(parts[2])
        except Exception:
            total = 0
        await debug_print('END from %s total=%s' % (remote_uid, total), 'BASE_NODE')

        try:
            st = getattr(settings, 'REMOTE_NODE_INFO', {}).get(remote_uid, {})
            if st.get('chunks') and callable(globals().get('process_remote_field_data')):
                await process_remote_field_data(remote_uid, st)
        except Exception as e:
            await debug_print('field process skip: %s' % e, 'WARN')

        next_delay = int(getattr(settings, 'REMOTE_SYNC_INTERVAL_S', 300) or 300)
        try:
            if callable(globals().get('calculate_next_delay')):
                next_delay = int(calculate_next_delay(remote_uid))
        except Exception:
            pass
        next_delay = max(30, next_delay)

        ack = 'ACK:%s:NEXT:%d' % (remote_uid, next_delay)
        try:
            secured = await _secure_message(ack, remote_uid=remote_uid)
            data = secured.encode() if isinstance(secured, str) else secured
            ok = await _safe_send(data, remote_uid=remote_uid)
        except Exception as e:
            ok = False
            await debug_print('ACK send error: %s' % e, 'ERROR')
        await debug_print('FINAL ACK to %s ok=%s next=%d' % (remote_uid, ok, next_delay), 'BASE_NODE')

        st = getattr(settings, 'REMOTE_NODE_INFO', {}).get(remote_uid, {})
        st['session_active'] = False
        st['chunks'] = []
        try:
            await ensure_lora_listening()
        except Exception:
            pass
        return True

    return False

async def handle_incoming_packet(msg):
    global last_rx_ts, last_lora_activity_ts
    msg_str = msg.rstrip(b'\x00').decode()

    uid_hint = None
    if _is_lora_hub_node():
        try:
            parts = msg_str.split(',')
            for p in parts:
                if p.startswith('UID:'):
                    uid_hint = p[4:].strip()
                    break
                if p.startswith('U:'):
                    uid_hint = p[2:].strip()
                    break
            if uid_hint is None and msg_str.startswith('HELLO:'):
                uid_hint = msg_str.split('|', 1)[0].split(':', 1)[1].strip()
            if uid_hint is None and msg_str.startswith('END:'):
                uid_hint = msg_str.split('|', 1)[0].split(':', 2)[1].strip()
        except Exception:
            uid_hint = None

    msg_str = await _unsecure_message(msg_str, remote_uid=uid_hint)
    if not msg_str:
        await debug_print("Dropped inbound packet: secure decode failed", "WARN")
        return

    if bool(getattr(settings, 'LORA_SIMPLE_SESSION_ONLY', True)):
        if str(getattr(settings, 'NODE_TYPE', '')).lower() in ('base', 'wifi'):
            handled = await handle_simple_session_hub(msg_str)
            if handled:
                return

    # Optional relay forwarding / unwrapping: FWD:ttl:origin:seq:inner
    if str(msg_str).startswith('FWD:'):
        node_type = str(getattr(settings, 'NODE_TYPE', '')).lower()
        if node_type in ('base', 'wifi'):
            try:
                parts = str(msg_str).split(':', 4)
                if len(parts) == 5:
                    settings._last_hub_heard_ts = time.time()
                    msg_str = parts[4]
                    uid_hint = parts[2]
            except Exception:
                pass
        elif bool(getattr(settings, 'ENABLE_LORA_RELAY', False)):
            await maybe_relay_forward(msg_str, rssi=(lora.getRSSI() if lora and hasattr(lora, 'getRSSI') else None))
            return

    # Validate network membership after decryption so secure envelopes can be checked.
    if _is_lora_hub_node():
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

    elif msg_str.startswith('HELLO:'):
        packet_type = 'HELLO'
        try:
            remote_uid = msg_str.split(':', 1)[1].strip()
        except Exception:
            remote_uid = None
        parsed_data = remote_uid

    elif msg_str.startswith('END:'):
        packet_type = 'END'
        try:
            parts = msg_str.split(':')
            remote_uid = parts[1].strip() if len(parts) > 1 else None
            declared_total = _safe_int(parts[2], 0) if len(parts) > 2 else 0
            batch_id = None
            if len(parts) >= 5 and parts[3] == 'BID':
                batch_id = parts[4]
            parsed_data = {'uid': remote_uid, 'total': declared_total, 'batch_id': batch_id}
        except Exception:
            remote_uid = None
            parsed_data = None

    elif msg_str.startswith('TYPE:'):
        parts = msg_str.split(',')
        msg_type = None
        remote_uid = None
        data_b64 = None
        chunk_str = None
        batch_id = None
        for p in parts:
            if p.startswith('TYPE:'):
                msg_type = p[5:]
            elif p.startswith('UID:'):
                remote_uid = p[4:]
            elif p.startswith('DATA:'):
                data_b64 = p[5:]
            elif p.startswith('CHUNK:'):
                chunk_str = p[6:]
            elif p.startswith('BID:'):
                batch_id = p[4:]
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
            'chunk_info': chunk_str if packet_type.endswith('_CHUNK') else None,
            'batch_id': batch_id if packet_type.endswith('_CHUNK') else None,
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
                settings.LORA_PEER_COUNTERS = remote_counters
    except Exception:
        pass


def _save_counters():
    """Persist counters to disk."""
    try:
        path = getattr(settings, 'LORA_COUNTERS_FILE', '/logs/lora_counters.json')
        peer_map = getattr(settings, 'LORA_PEER_COUNTERS', None)
        if isinstance(peer_map, dict):
            for uid, vals in peer_map.items():
                if isinstance(vals, dict):
                    remote_counters[uid] = {
                        'tx': int(vals.get('tx', 0)),
                        'rx': int(vals.get('rx', 0))
                    }
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


async def _secure_message(msg_str, remote_uid=None):
    """
    Envelope: msg|CNT:n|HMAC:hex|CRC:XXXX
    CRC covers the original msg_str only (not the envelope).
    """
    try:
        if isinstance(msg_str, bytes):
            msg_str = msg_str.decode()
        msg_str = str(msg_str)

        # Simple-mode / diagnostics path: when HMAC is disabled, keep payload plain
        # and optionally append only CRC.
        if not bool(getattr(settings, 'LORA_HMAC_ENABLED', True)):
            if bool(getattr(settings, 'LORA_CRC_ENABLED', False) or getattr(settings, 'CRC_ON', False)):
                c = crc16_ccitt(msg_str.encode() if not isinstance(msg_str, bytes) else msg_str)
                return '%s|CRC:%s' % (msg_str, _format_crc(c))
            return msg_str

        uid = remote_uid or getattr(settings, 'UNIT_ID', 'local')
        if not hasattr(settings, 'LORA_PEER_COUNTERS') or settings.LORA_PEER_COUNTERS is None:
            settings.LORA_PEER_COUNTERS = {}
        peer = settings.LORA_PEER_COUNTERS.setdefault(str(uid), {'tx': 0, 'rx': 0})
        peer['tx'] = int(peer.get('tx', 0)) + 1
        counter = int(peer['tx'])
        remote_counters[str(uid)] = {'tx': int(peer['tx']), 'rx': int(peer.get('rx', 0))}

        parts = [msg_str, 'CNT:%d' % counter]

        if getattr(settings, 'LORA_HMAC_ENABLED', True):
            secret = str(getattr(settings, 'LORA_HMAC_SECRET', '') or '')
            trunc = int(getattr(settings, 'LORA_HMAC_TRUNCATE', 16))
            material = ('%s|%d' % (msg_str, counter)).encode()
            try:
                digest = hmac_sha256(secret.encode(), material)
                if isinstance(digest, bytes):
                    hx = ''.join('{:02x}'.format(b) for b in digest)
                else:
                    hx = str(digest)
                parts.append('HMAC:%s' % hx[:trunc])
            except Exception as e:
                await _sec_log('HMAC build failed: %s' % e)

        if getattr(settings, 'LORA_CRC_ENABLED', True) or getattr(settings, 'CRC_ON', True):
            c = crc16_ccitt(msg_str.encode() if not isinstance(msg_str, bytes) else msg_str)
            parts.append('CRC:' + _format_crc(c))

        if counter % 5 == 0:
            _save_counters()
        return '|'.join(parts)
    except Exception as e:
        await _sec_log('secure_message error: %s' % e)
        return str(msg_str)


async def crc_selftest():
    sample = 'HELLO:unit-test'
    c = crc16_ccitt(sample.encode())
    wire = _format_crc(c)
    ok, detail = verify_app_crc(sample, wire)
    await debug_print('CRC selftest %s %s (wire=CRC:%s)' % (ok, detail, wire), 'LORA')


async def _unsecure_message(msg_str, remote_uid=None):
    """
    Parse pipe envelope. Return cleartext msg or None on hard failure.
    """
    try:
        if isinstance(msg_str, bytes):
            msg_str = msg_str.rstrip(b'\x00').decode()
        raw = str(msg_str).strip()
        if not raw:
            return None

        if '|' not in raw:
            if raw.startswith('HELLO:') or raw.startswith('READY:') or raw.startswith('ACK:') or raw.startswith('END:') or raw.startswith('FWD:') or raw.startswith('TYPE:'):
                return raw
            if getattr(settings, 'LORA_HMAC_REJECT_UNSIGNED', True) and getattr(settings, 'LORA_HMAC_ENABLED', True):
                await _sec_log('Invalid secure format (no CNT/HMAC)')
                return None
            return raw

        parts = raw.split('|')
        body = parts[0]
        cnt = None
        hmac_hex = None
        crc_raw = None

        for p in parts[1:]:
            pu = p.strip()
            if pu.upper().startswith('CRC:'):
                crc_raw = pu[4:]
            elif pu.upper().startswith('CNT:'):
                try:
                    cnt = int(pu[4:].strip())
                except Exception:
                    cnt = None
            elif pu.upper().startswith('HMAC:'):
                hmac_hex = pu[5:].strip()

        hmac_enabled = bool(getattr(settings, 'LORA_HMAC_ENABLED', True))

        if hmac_enabled and hmac_hex is None:
            if getattr(settings, 'LORA_HMAC_REJECT_UNSIGNED', True):
                await _sec_log('Invalid secure format (no CNT/HMAC)')
                return None
            return body

        # When HMAC is disabled, accept plain body and (optionally) validate CRC.
        if not hmac_enabled:
            if crc_raw is not None and (bool(getattr(settings, 'LORA_CRC_ENABLED', False)) or bool(getattr(settings, 'CRC_ON', False))):
                ok_crc, detail = verify_app_crc(body, crc_raw)
                if not ok_crc:
                    if getattr(settings, 'LORA_SESSION_SOFT_CRC', True):
                        b = body.strip()
                        if b.startswith('HELLO:') or b.startswith('READY:') or b.startswith('ACK:') or b.startswith('END:') or b.startswith('FWD:'):
                            await _sec_log('CRC soft-accept session frame: %s' % b[:32])
                            return body
                    await _sec_log(detail)
                    return None
            return body

        if (getattr(settings, 'LORA_CRC_ENABLED', True) or getattr(settings, 'CRC_ON', True)) and crc_raw is not None:
            ok_crc, detail = verify_app_crc(body, crc_raw)
            if not ok_crc:
                if getattr(settings, 'LORA_SESSION_SOFT_CRC', True):
                    b = body.strip()
                    if b.startswith('HELLO:') or b.startswith('READY:') or b.startswith('ACK:') or b.startswith('END:') or b.startswith('FWD:'):
                        await _sec_log('CRC soft-accept session frame: %s' % b[:32])
                        return body
                await _sec_log(detail)
                return None

        if hmac_enabled and hmac_hex is not None:
            secret = str(getattr(settings, 'LORA_HMAC_SECRET', '') or '')
            trunc = int(getattr(settings, 'LORA_HMAC_TRUNCATE', 16))
            if cnt is None:
                await _sec_log('Invalid secure format (no CNT/HMAC)')
                return None
            material = ('%s|%d' % (body, cnt)).encode()
            try:
                digest = hmac_sha256(secret.encode(), material)
                if isinstance(digest, bytes):
                    calc = ''.join('{:02x}'.format(b) for b in digest)[:trunc]
                else:
                    calc = str(digest)[:trunc]
                if calc.lower() != str(hmac_hex)[:trunc].lower():
                    await _sec_log('HMAC verification failed')
                    return None
            except Exception as e:
                await _sec_log('HMAC verify error: %s' % e)
                return None

        if hmac_enabled and cnt is not None and getattr(settings, 'LORA_HMAC_REPLAY_PROTECT', True):
            uid = str(remote_uid or 'unknown')
            if not hasattr(settings, 'LORA_PEER_COUNTERS') or settings.LORA_PEER_COUNTERS is None:
                settings.LORA_PEER_COUNTERS = {}
            peer = settings.LORA_PEER_COUNTERS.setdefault(uid, {'tx': 0, 'rx': 0})
            last_rx = int(peer.get('rx', 0))
            window = int(getattr(settings, 'LORA_REPLAY_WINDOW', 8))

            if body.startswith('HELLO:') or body.startswith('FWD:'):
                peer['rx'] = cnt
            elif cnt + window <= last_rx:
                await _sec_log('Replay attack detected (cnt %d <= last_rx %d)' % (cnt, last_rx))
                return None
            elif cnt > last_rx:
                peer['rx'] = cnt

            remote_counters[uid] = {'tx': int(peer.get('tx', 0)), 'rx': int(peer.get('rx', 0))}
            if cnt % 5 == 0:
                _save_counters()

        return body
    except Exception as e:
        await _sec_log('unsecure_message error: %s' % e)
        return None

async def _send_with_retry(data, retries=6):
    global lora
    if lora is None or not hasattr(lora, 'send'):
        return
    max_size = int(getattr(settings, 'LORA_MAX_PACKET_SIZE', 240))
    if len(data) > max_size:
        await log_error(f"Payload too large: {len(data)} (max {max_size})")
        return
    base_delay = getattr(settings, 'LORA_RETRY_BASE_DELAY_S', 2)
    max_backoff = getattr(settings, 'LORA_MAX_BACKOFF_S', 90)
    for att in range(retries):
        try:
            await ensure_lora_listening()
            if bool(getattr(settings, 'LORA_ENABLE_CAD', False)) and hasattr(lora, 'cad'):
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


async def _safe_send(data: bytes, remote_uid=None):
    """
    Enforce maximum packet size before transmitting.
    Returns True on success, False on failure.
    """
    max_size = int(getattr(settings, 'LORA_MAX_PACKET_SIZE', 240))

    if len(data) > max_size:
        await log_error(f"Payload too large: {len(data)} (max {max_size})")
        return False

    try:
        await _send_with_retry(data)
        return True
    except Exception as e:
        await log_error(f"_safe_send error: {e}")
        return False

async def _wait_tx_done(timeout=5):
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
    await debug_print("TX timeout - forcing radio recovery", "WARN")
    await log_error("TX timeout")
    lora = None
    await hard_reset_lora()
    try:
        await init_lora()
    except Exception as e:
        await log_error(f"TX timeout recovery init failed: {e}")
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
    max_size = int(getattr(settings, 'LORA_MAX_PACKET_SIZE', 240))
    max_b64_chunk_len = _safe_int(chunk_len, 0)
    if max_b64_chunk_len <= 0:
        configured = _safe_int(getattr(settings, 'LORA_CHUNK_SIZE', 160), 160)
        max_b64_chunk_len = max(48, configured)

    target = str(target_uid or getattr(settings, 'UNIT_ID', ''))
    b64_len = len(full_b64)

    for split_try in range(5):
        if b64_len <= max_b64_chunk_len:
            num_chunks = 1
        else:
            num_chunks = (b64_len + max_b64_chunk_len - 1) // max_b64_chunk_len

        oversized = False
        for i in range(num_chunks):
            chunk_start = i * max_b64_chunk_len
            chunk_end = min(b64_len, chunk_start + max_b64_chunk_len)
            chunk_b64 = full_b64[chunk_start:chunk_end]

            if num_chunks == 1:
                data_str = f"TYPE:{msg_type},UID:{target},DATA:{chunk_b64}"
            else:
                data_str = f"TYPE:{msg_type}_CHUNK,UID:{target},CHUNK:{i}/{num_chunks},DATA:{chunk_b64}"

            if _is_lora_hub_node():
                secured = await _secure_message(data_str, remote_uid=target)
            else:
                secured = await _secure_message(data_str)

            secured_bytes = secured.encode()
            if len(secured_bytes) > max_size:
                await log_error(
                    f"Secured chunk too large: {len(secured_bytes)} (max {max_size}); shrinking chunk size"
                )
                max_b64_chunk_len = max(48, int(max_b64_chunk_len * 0.8))
                oversized = True
                break

            await _safe_send(secured_bytes)
            if num_chunks > 1:
                await asyncio.sleep(random.uniform(0.08, 0.25))

        if not oversized:
            if num_chunks > 1:
                await asyncio.sleep(0.5)
            return

    await log_error(f"Unable to fit chunked payload under max packet size for {msg_type}")


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


async def send_hello_and_wait_ready(use_fwd=False):
    """Simple mode remote greeting: direct HELLO -> wait for READY."""
    if str(getattr(settings, 'NODE_TYPE', 'base')).lower() != 'remote':
        return None

    uid = str(getattr(settings, 'UNIT_ID', '') or '')
    if not uid:
        return None
    try:
        secret = str(getattr(settings, 'LORA_HMAC_SECRET', '') or '')
        if secret:
            fp = _ub.hexlify(uhashlib.sha256(secret.encode()).digest()).decode()[:10]
            await debug_print(f"LoRa HMAC secret fingerprint: {fp}", "LORA")
        else:
            await debug_print("LoRa HMAC secret is empty", "WARN")
    except Exception:
        pass
    await debug_print("=== SIMPLE SESSION START ===", "REMOTE_NODE")
    hello = 'HELLO:%s' % uid

    sent_any = False
    retries = int(getattr(settings, 'LORA_HELLO_RETRIES', 3))
    for attempt in range(retries):
        try:
            secured = await _secure_message(hello)
            ok = await _safe_send(secured.encode())
            sent_any = bool(ok)
            await ensure_lora_listening()
            await debug_print('HELLO sent attempt %d ok=%s' % (attempt + 1, ok), 'REMOTE_NODE')
            if ok:
                break
        except Exception as e:
            await debug_print(f"HELLO TX error: {e}", "WARN")
        await asyncio.sleep_ms(400)

    if not sent_any:
        await debug_print("HELLO failed all attempts", "ERROR")
        return None

    timeout = _safe_int(getattr(settings, 'LORA_HELLO_TIMEOUT_S', 15), 15)
    timeout = max(2, timeout)
    await debug_print("Waiting for READY...", "REMOTE_NODE")
    end_ts = time.time() + timeout
    while time.time() < end_ts:
        try:
            if lora is None:
                await asyncio.sleep_ms(100)
                continue

            try:
                lora.recv(0, False, 0)
            except Exception:
                pass

            msg, err = lora.recv(0) if hasattr(lora, 'recv') else (None, -1)
            if err == 0 and msg:
                raw = msg.rstrip(b'\x00').decode()
                clear = await _unsecure_message(raw)
                if not clear:
                    continue
                if clear.startswith("READY:") and uid in clear:
                    await debug_print(f"READY received: {clear}", "REMOTE_NODE")

                    parts = str(clear).split(':')
                    base_uid = None
                    chunk_sz = _safe_int(getattr(settings, 'LORA_CHUNK_SIZE', 80), 80)
                    try:
                        if 'BASE' in parts:
                            base_uid = parts[parts.index('BASE') + 1]
                        if 'CHUNKSZ' in parts:
                            chunk_sz = int(parts[parts.index('CHUNKSZ') + 1])
                    except Exception:
                        pass
                    try:
                        settings.PAIRED_BASE_UID = base_uid
                        settings.LORA_CHUNK_SIZE = chunk_sz
                        with open(settings.LOG_DIR.rstrip('/') + '/paired_base.txt', 'w') as f:
                            f.write(str(base_uid or ''))
                    except Exception:
                        pass
                    await debug_print(
                        f"Paired with base {base_uid}, chunk_size={chunk_sz}",
                        "REMOTE_NODE"
                    )
                    await debug_print("=== SIMPLE SESSION READY ===", "REMOTE_NODE")
                    return clear
        except Exception:
            pass
        await asyncio.sleep_ms(80)

    await debug_print("No READY - session failed", "WARN")
    return None


async def send_field_data_controlled(payload):
    """Remote controlled simple session: HELLO -> READY -> chunks -> END -> FINAL ACK."""
    if str(getattr(settings, 'NODE_TYPE', 'base')).lower() != 'remote':
        return None

    uid = str(getattr(settings, 'UNIT_ID', '') or '')

    if payload is None:
        ts_now = time.time()
        if bool(getattr(settings, 'LORA_MINIMAL_TELEMETRY', True)):
            payload = {
                'unit_id': uid,
                'ts': ts_now,
                'fw': getattr(settings, 'FIRMWARE_VERSION', ''),
                'volt': getattr(sdata, 'sys_voltage', None),
                'temp_f': getattr(sdata, 'cur_temp_f', None),
                'humid': getattr(sdata, 'cur_humid', None),
            }
        else:
            payload = {
                'unit_id': uid,
                'node_type': 'remote',
                'ts': ts_now,
                'fw': getattr(settings, 'FIRMWARE_VERSION', ''),
                'v': getattr(sdata, 'sys_voltage', None),
                't': (getattr(sdata, 'cur_temp_f', None) or getattr(sdata, 'cur_device_temp_f', None)),
                'h': getattr(sdata, 'cur_humid', None),
                'rssi': getattr(sdata, 'lora_SigStr', None),
            }

    ready_msg = await send_hello_and_wait_ready(use_fwd=False)
    if not ready_msg:
        await debug_print("No READY - aborting session", "WARN")
        await debug_print("=== SIMPLE SESSION FAILED ===", "REMOTE_NODE")
        return None

    chunk_size = _safe_int(getattr(settings, 'LORA_CHUNK_SIZE', 100), 100)
    try:
        parts = str(ready_msg).split(':')
        if parts and parts[0] == 'READY' and uid in parts:
            if 'CHUNKSZ' in parts:
                chunk_size = max(48, int(parts[parts.index('CHUNKSZ') + 1]))
    except Exception:
        pass

    try:
        raw_json = ujson.dumps(payload)
        full_b64 = _ub.b2a_base64(raw_json.encode()).rstrip(b'\n').decode()
    except Exception as e:
        await debug_print(f"Payload encode failed: {e}", "ERROR")
        await debug_print("=== SIMPLE SESSION FAILED ===", "REMOTE_NODE")
        return None

    total = (len(full_b64) + chunk_size - 1) // chunk_size if full_b64 else 1
    await debug_print(f"Payload {len(raw_json)} bytes -> {total} chunk(s)", "REMOTE_NODE")

    batch_id = None
    try:
        if isinstance(payload, dict):
            batch_id = payload.get('batch_id')
    except Exception:
        batch_id = None

    for i in range(total):
        start = i * chunk_size
        part = full_b64[start:start + chunk_size]
        if batch_id:
            chunk_msg = f"TYPE:FIELD_DATA_CHUNK,UID:{uid},CHUNK:{i}/{total},BID:{batch_id},DATA:{part}"
        else:
            chunk_msg = f"TYPE:FIELD_DATA_CHUNK,UID:{uid},CHUNK:{i}/{total},DATA:{part}"
        try:
            secured = await _secure_message(chunk_msg)
            ok = await _safe_send(secured.encode())
            await debug_print(f"Chunk {i}/{total} sent (ok={ok})", "REMOTE_NODE")
            if not ok:
                await debug_print(f"Chunk {i} TX failed", "ERROR")
                await debug_print("=== SIMPLE SESSION FAILED ===", "REMOTE_NODE")
                return None
        except Exception as e:
            await debug_print(f"Chunk {i} send exception: {e}", "ERROR")
            await debug_print("=== SIMPLE SESSION FAILED ===", "REMOTE_NODE")
            return None
        await asyncio.sleep_ms(300)

    if batch_id:
        end_msg = f"END:{uid}:{total}:BID:{batch_id}"
    else:
        end_msg = f"END:{uid}:{total}"

    try:
        secured = await _secure_message(end_msg)
        ok = await _safe_send(secured.encode())
        await debug_print(f"END sent (total={total}, ok={ok})", "REMOTE_NODE")
    except Exception as e:
        await debug_print(f"END send failed: {e}", "ERROR")
        await debug_print("=== SIMPLE SESSION FAILED ===", "REMOTE_NODE")
        return None

    await debug_print("Waiting for final ACK...", "REMOTE_NODE")
    ack_timeout = _safe_int(getattr(settings, 'REMOTE_ACK_WAIT_S', 45), 45)
    ack_timeout = max(10, ack_timeout)
    end_ts = time.time() + ack_timeout

    while time.time() < end_ts:
        try:
            if lora is None:
                break
            try:
                msg, err = lora.recv(0)
            except TypeError:
                msg, err = lora.recv()
            if err == 0 and msg:
                raw = msg.rstrip(b'\x00').decode()
                clear = await _unsecure_message(raw)
                if clear and clear.startswith('ACK:'):
                    parts = clear.split(':')
                    if len(parts) >= 4 and parts[1] == uid and parts[2] == 'NEXT':
                        ack_bid = None
                        ack_cmd = None
                        if len(parts) >= 6:
                            i = 4
                            while i + 1 < len(parts):
                                if parts[i] == 'BID':
                                    ack_bid = parts[i + 1]
                                elif parts[i] == 'CMD':
                                    ack_cmd = _decode_ack_command(parts[i + 1])
                                    break
                                i += 2
                        if batch_id and ack_bid and str(ack_bid) != str(batch_id):
                            await debug_print(
                                f"Final ACK BID mismatch (expected {batch_id}, got {ack_bid})",
                                "WARN"
                            )
                            await asyncio.sleep_ms(80)
                            continue
                        if isinstance(ack_cmd, dict):
                            await debug_print("Remote: received command via FINAL ACK", "REMOTE_NODE")
                            await _apply_remote_command_from_ack(ack_cmd)
                        try:
                            delay = max(10, int(parts[3]))
                        except Exception:
                            delay = None
                        await debug_print(f"FINAL ACK received: {clear}", "REMOTE_NODE")
                        await debug_print("=== SIMPLE SESSION SUCCESS ===", "REMOTE_NODE")
                        return delay
        except Exception:
            pass
        await asyncio.sleep_ms(100)

    await debug_print("Final ACK timeout", "WARN")
    await debug_print("=== SIMPLE SESSION FAILED ===", "REMOTE_NODE")
    return None

async def _fetch_remote_pending_command(remote_unit_id, remote_machine_id=None):
    """Base helper: fetch one queued command for a remote unit from UC/WP."""
    try:
        if not _is_lora_hub_node():
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
        if not _is_lora_hub_node() or not isinstance(payload, dict):
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
        await _safe_send(msg_str.encode())
        await debug_print("LoRa heartbeat sent", "LORA")
    except Exception as e:
        await log_error(f"Heartbeat send error: {e}")

# ===================== PERIODIC TASKS (unchanged) =====================
async def periodic_wp_sync():
    if not _is_lora_hub_node():
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
    if not _is_lora_hub_node():
        return
    if not heartbeat_ping:
        await debug_print("heartbeat_ping_loop unavailable: heartbeat_ping helper missing", "LORA")
        return
    while True:
        await heartbeat_ping()
        await asyncio.sleep(60)


async def expected_sync_watcher():
    """Log remotes that are near their expected sync time and keep RX in listen mode."""
    if not _is_lora_hub_node():
        return
    while True:
        try:
            now = time.time()
            for uid, st in list(getattr(settings, 'REMOTE_NODE_INFO', {}).items()):
                if not isinstance(st, dict):
                    continue
                next_exp = st.get('next_expected', 0)
                if next_exp and abs(now - next_exp) < 15:
                    await debug_print(f"Expecting {uid} around now", "BASE_NODE")
                    await ensure_lora_listening()
        except Exception:
            pass
        await asyncio.sleep(10)

async def check_missed_syncs():
    if not _is_lora_hub_node():
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
    global lora, last_rx_ts, last_lora_activity_ts, _crc_selftest_done
    if not getattr(settings, 'ENABLE_LORA', True):
        return False

    await debug_print(f"Enabling LoRa - {getattr(settings, 'FIRMWARE_VERSION', 'unknown')}", "LORA")
    try:
        secret = str(getattr(settings, 'LORA_HMAC_SECRET', '') or '')
        if secret:
            fp = _ub.hexlify(uhashlib.sha256(secret.encode()).digest()).decode()[:10]
            await debug_print(f"LoRa HMAC secret fingerprint: {fp}", "LORA")
        else:
            await debug_print("LoRa HMAC secret is empty", "WARN")
    except Exception:
        pass
    await display_message("LoRa Starting...", 1)

    async with pin_lock:
        if not await init_lora():
            return False
    last_lora_activity_ts = time.time()
    if not _crc_selftest_done:
        try:
            await crc_selftest()
        except Exception as e:
            await log_error(f"crc_selftest failed: {e}")
        _crc_selftest_done = True

    if _is_lora_hub_node():
        asyncio.create_task(base_packet_processor())
        await debug_print("Base background processor started", "BASE_NODE")
        asyncio.create_task(check_incomplete_bursts())
        await debug_print("Base incomplete-burst checker started", "BASE_NODE")
        if heartbeat_ping:
            asyncio.create_task(heartbeat_ping_loop())
            await debug_print("Base heartbeat ping loop started", "BASE_NODE")
        asyncio.create_task(expected_sync_watcher())
        await debug_print("Base expected-sync watcher started", "BASE_NODE")

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
            watch_timeout_s = int(getattr(settings, 'LORA_WATCHDOG_TIMEOUT_S', 86400))
            hard_reset_on_idle = bool(getattr(settings, 'LORA_WATCHDOG_HARD_RESET_ON_IDLE', False))
            is_base_or_wifi = str(getattr(settings, 'NODE_TYPE', '')).lower() in ('base', 'wifi')

            if hard_reset_on_idle:
                if not is_base_or_wifi:
                    remote_watchdog_s = int(getattr(settings, 'LORA_REMOTE_WATCHDOG_S', 600))
                    if bool(getattr(settings, 'REMOTE_USE_CONTROLLED_SESSION_ONLY', True)):
                        remote_watchdog_s = 10**9
                    if current_time - last_lora_activity_ts > remote_watchdog_s:
                        await debug_print("LoRa health watchdog (remote) - re-init", "WARN")
                        await init_lora()
                        last_lora_activity_ts = current_time
                else:
                    if current_time - last_lora_activity_ts > watch_timeout_s:
                        await debug_print("LoRa health watchdog (base) - long idle re-init", "WARN")
                        await init_lora()
                        last_lora_activity_ts = current_time

            if lora is None or not hasattr(lora, '_events'):
                if not await init_lora():
                    await asyncio.sleep(8)
                    continue

            if _is_lora_hub_node() or str(getattr(settings, 'NODE_TYPE', '')).lower() == 'remote':
                await ensure_lora_listening()

            if current_time - last_rx_ts > 70:
                sdata.lora_SigStr = -120
                sdata.LORA_CONNECTED = False

            if settings.NODE_TYPE == 'remote':
                if bool(getattr(settings, 'LORA_SIMPLE_SESSION_ONLY', True)):
                    await debug_print('Remote: simple session only mode (HELLO/READY/END/ACK)', 'REMOTE_NODE')
                    _next = await send_field_data_controlled(None)
                    if isinstance(_next, int) and _next > 0:
                        await debug_print(f"Remote simple mode ACK next={_next}s", "REMOTE_NODE")
                        await asyncio.sleep(max(5, _next))
                    else:
                        await debug_print("Remote simple mode: no ACK, retrying", "WARN")
                        await asyncio.sleep(max(5, int(getattr(settings, 'REMOTE_FAILED_SYNC_RETRY_S', 60))))
                    continue

                heartbeat_interval = getattr(settings, 'LORA_HEARTBEAT_INTERVAL_S', 120)
                if current_time - last_heartbeat_ts >= heartbeat_interval:
                    await _send_lora_heartbeat()
                    last_heartbeat_ts = current_time

                if state == STATE_IDLE:
                    awaiting_ota_session = None
                    ota_wait_deadline = 0
                    await debug_print("Remote: starting full check-in (periodic)", "REMOTE_NODE")
                    ready_msg = await send_hello_and_wait_ready(use_fwd=False)
                    if not ready_msg and bool(getattr(settings, 'LORA_DIRECT_THEN_RELAY', True)):
                        await debug_print('Direct HELLO failed - trying FWD relay path', 'REMOTE_NODE')
                        ready_msg = await send_hello_and_wait_ready(use_fwd=True)
                    if bool(getattr(settings, 'LORA_SESSION_ENABLED', True)) and not ready_msg:
                        await debug_print("Remote: READY not received, deferring burst TX", "WARN")
                        await asyncio.sleep(2)
                        continue
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
                    await _safe_send(data_str.encode())
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
                            configured_retry = _safe_int(getattr(settings, 'REMOTE_FAILED_SYNC_RETRY_S', 0), 0)
                            if configured_retry > 0:
                                sleep_time = configured_retry + random.uniform(0, max(2, configured_retry * 0.1))
                            else:
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
                        # TEMP DIAGNOSTIC - log every raw packet the radio sees
                        try:
                            raw_preview = msg.rstrip(b'\x00')[:80]
                            await debug_print(f"RAW RX ({len(msg)} bytes): {raw_preview!r}", "LORA_RX")
                        except Exception as e:
                            await debug_print(f"RAW RX log error: {e}", "LORA_RX")
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
