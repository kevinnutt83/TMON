# TMON v2.01.9 - BULLETPROOF LoRa (FULLY REFACTORED + uasyncio COMPATIBLE + MULTI-NODE FIXES)
# CRITICAL FIXES APPLIED IN THIS UPDATE (v2.01.9):
# • RAW FRAGMENT STORE: multi-chunk FIELD_DATA is stored as cleaned base64 only
# • ASSEMBLE-THEN-PARSE: JSON salvage runs only on the concatenated payload
# • NO PREFIX-AS-RECORD: a salvaged chunk-0 object cannot ACK assembled=True
# • SINGLE-FRAME BUDGET: ignore LORA_CHUNK_SIZE < 96 so compact telemetry fits one RX
# • COMPACT NUMBERS: remote payload rounds t/h/b/v to cut b64 under one frame
# PRIOR (v2.01.8):
# • STORE CHUNKS FROM ANY UID: hub lock queues HELLOs only; CHUNK/END from other remotes are kept
# • NO BEST-EFFORT FIELD DATA: remotes that miss READY do not TX chunks into another session
# • IDLE HUB RELEASE: if no CHUNK arrives within 8s of READY, release lock and serve queued HELLO
# • SINGLE-CHUNK BUDGET: default data budget 120 so compact telemetry fits one frame
# • NO MID-SESSION HARD RESET: TX (85,-706) retries without wiping the radio mid-burst
# • RX RE-ARM RETRY: startReceive is retried after every TX so READY is not missed
# PRIOR (v2.01.7):
# • MULTI-NODE SLOT SCHEDULE: ACK NEXT = interval + assigned_slot * slot_width (default 20s)
#   so four remotes do not retry on top of each other after a missed assemble.
# • HUB SESSION LOCK: only one remote session is live; extra HELLOs are queued until END/ACK.
# • REAL CHUNKING: remotes honor READY CHUNKSZ / LORA_CHUNK_SIZE instead of one 190-byte frame.
# • CAD DEFAULT ON: listen-before-talk; do not TX into a busy channel unless LORA_CAD_FORCE_TX.
# • RETRY ACK ON ASSEMBLE FAIL: still send ACK:NEXT so remotes leave the air instead of HELLO-flooding.
# • PARTIAL JSON SALVAGE: keep compact u/t/h/b/v/ts fields from clipped CHUNK payloads.
# • CLIPPED PREFIX RECOVERY: rebuild TYPE:FIELD_DATA_CHUNK from ,UID: / UID: fragments.
# • LONGER SESSION BUSY WINDOW: default 25s so CHUNK/END are not abandoned mid-air.
# • DISPATCH DOWNLINK: after READY, base sends staged SETTINGS via LoRa; ACK CMD prefers dispatch queue.
# PRIOR (v2.01.6):
# • FULL BURST COMPLETION DETECTION: processing/ACK now triggers ONLY after ALL types (TS + SETTINGS + SDATA) are assembled OR timeout
# • PERSISTENT REMOTE NODE INFO: keeps next_expected / missed_syncs / COMPANY / MACHINE_ID across bursts
# • TS metadata update uses .update() instead of overwriting the entire dict
# • Cleanup now safely pops only temporary burst keys (types/data/chunks/last_rx)
# • SESSION FIX: valid TYPE:FIELD_DATA_CHUNK frames are no longer treated as truncated.
# • ASSEMBLE FIX: _clean_b64 no longer joins header junk onto DATA; JSON salvage + clipped-prefix recovery.

import ujson
import os
import uasyncio as asyncio
import random
import ubinascii as _ub
import gc
try:
    import uctypes
except ImportError:
    uctypes = None
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

from utils import free_pins, debug_print, TMON_AI, stage_remote_field_data, stage_remote_files, record_field_data, get_machine_id, persist_custom_settings, build_field_data_record
from relay import toggle_relay
from sampling import findLowestTemp, findHighestTemp, findLowestBar, findHighestBar, findLowestHumid, findHighestHumid

_ALIGN = 32
_SCRATCH_RAW = bytearray(256 + _ALIGN + 64)


def _aligned_view(buf, size):
    if uctypes is None:
        return memoryview(buf)[:size]
    addr = uctypes.addressof(buf)
    offset = (_ALIGN - (addr % _ALIGN)) % _ALIGN
    return memoryview(buf)[offset:offset + size]


_TX = _aligned_view(_SCRATCH_RAW, 256)


def _fill_tx(value):
    if isinstance(value, str):
        value = value.encode()
    length = len(value)
    if length > 200:
        raise ValueError('tx %d' % length)
    _TX[:length] = value
    return memoryview(_TX)[:length]
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
lora_rx_pending = False
_last_rx_digest = None
_last_rx_ticks = 0
_sec_log_last = {}
_sec_log_count = {}
_pending_hellos = []
_hub_active_uid = None
_hub_ready_ticks = 0
_in_session_tx = False

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
_remote_settings_rx = {
    'chunks': {},
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
        await _arm_rx_retry()
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
    files = None
    base_ver = ''
    if not _is_lora_hub_node():
        return None
    if not bool(getattr(settings, 'ENABLE_LORA_OTA', False)):
        return None
    base_ver = str(getattr(settings, 'FIRMWARE_VERSION', '') or '').strip()
    remote_ver = str(remote_ver or '').strip()
    if not remote_ver or remote_ver == base_ver or not _is_newer_version(remote_ver, base_ver):
        return None
    if any(isinstance(info, dict) and info.get('session_active')
           for info in (getattr(settings, 'REMOTE_NODE_INFO', {}) or {}).values()):
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
    chunk_len = min(120, max(48, _safe_int(getattr(settings, 'LORA_OTA_CHUNK_SIZE', 120), 120)))

    meta = {
        'session': session,
        'version': version,
        'count': len(files),
        'files': [{'name': f.get('name'), 'sha256': f.get('sha256')} for f in files],
    }
    meta_b64 = _ub.b2a_base64(ujson.dumps(meta).encode()).rstrip(b'\n').decode()
    if not await _send_chunked('LORA_OTA_META', meta_b64, target_uid=uid, chunk_len=chunk_len):
        return False
    await asyncio.sleep(0.5)

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
                sent_ok = await _send_chunked('LORA_OTA_FILE', payload_b64, target_uid=uid, chunk_len=chunk_len)
                if sent_ok:
                    break
            except Exception:
                await asyncio.sleep(0.5)
        if not sent_ok:
            await log_error(f'lora ota send failed file={f.get("name")} uid={uid}')
            return False
        await asyncio.sleep(0.5)

    apply_msg = {
        'session': session,
        'version': version,
        'count': len(files),
    }
    apply_b64 = _ub.b2a_base64(ujson.dumps(apply_msg).encode()).rstrip(b'\n').decode()
    if not await _send_chunked('LORA_OTA_APPLY', apply_b64, target_uid=uid, chunk_len=chunk_len):
        return False
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
    text = str(msg_str)
    head, separator, data_b64 = text.partition(',DATA:')
    parts = head.split(',')
    msg_type = None
    uid = None
    chunk = None
    for p in parts:
        if p.startswith('TYPE:'):
            msg_type = p[5:]
        elif p.startswith('UID:'):
            uid = p[4:]
        elif p.startswith('CHUNK:'):
            chunk = p[6:]
    return msg_type, uid, chunk, data_b64 if separator else None


def _remote_decode_json_b64(data_b64):
    raw = _ub.a2b_base64(str(data_b64).encode())
    return ujson.loads(raw.decode())

async def _apply_inbound_settings_dict(payload):
    if not isinstance(payload, dict) or not payload:
        return False
    try:
        from dispatch import apply_inbound_settings_payload
        return await apply_inbound_settings_payload(payload)
    except Exception:
        try:
            persist_custom_settings(payload)
            await debug_print('Remote SETTINGS applied via persist keys=%s' % ','.join(list(payload.keys())[:8]), 'REMOTE_NODE')
            return True
        except Exception as e:
            await debug_print('Remote SETTINGS apply failed: %s' % e, 'ERROR')
            return False


async def _remote_handle_settings_wire_message(msg_str):
    msg_type, uid, chunk_info, data_b64 = _remote_parse_type_message(msg_str)
    my_uid = str(getattr(settings, 'UNIT_ID', '') or '')
    if not msg_type or uid != my_uid:
        return False
    if msg_type not in ('SETTINGS', 'SETTINGS_CHUNK'):
        return False
    base_type = 'SETTINGS'
    if msg_type.endswith('_CHUNK'):
        try:
            cn, total = map(int, str(chunk_info or '0/0').split('/'))
        except Exception:
            return False
        if base_type not in _remote_settings_rx['chunks']:
            _remote_settings_rx['chunks'][base_type] = {'total': total, 'parts': {}}
        _remote_settings_rx['chunks'][base_type]['parts'][cn] = data_b64
        slot = _remote_settings_rx['chunks'][base_type]
        if len(slot['parts']) < total:
            return True
        if not all(i in slot['parts'] for i in range(total)):
            return True
        assembled_b64 = ''.join(slot['parts'][i] for i in range(total))
        try:
            del _remote_settings_rx['chunks'][base_type]
        except Exception:
            pass
        payload = _remote_decode_json_b64(assembled_b64)
        return await _apply_inbound_settings_dict(payload)
    payload = _remote_decode_json_b64(data_b64)
    return await _apply_inbound_settings_dict(payload)


async def _remote_listen_settings_window(timeout_s=3.5):
    """After READY, listen briefly for base SETTINGS downlink before field-data TX."""
    try:
        timeout_s = float(timeout_s)
    except Exception:
        timeout_s = 3.5
    deadline = time.ticks_ms() + int(timeout_s * 1000)
    await _arm_rx_retry()
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        try:
            if not _lora_rx_ready():
                await asyncio.sleep_ms(50)
                continue
            msg = await _read_lora_packet()
            if not msg:
                continue
            try:
                raw = msg.rstrip(b'\x00').decode()
            except Exception:
                continue
            clear = await _unsecure_message(raw)
            if not clear:
                continue
            if clear.startswith('TYPE:SETTINGS') or 'TYPE:SETTINGS' in clear[:24]:
                handled = await _remote_handle_settings_wire_message(clear)
                await debug_print('Remote SETTINGS frame handled=%s' % handled, 'REMOTE_NODE')
        except Exception as e:
            await debug_print('settings listen error: %s' % e, 'WARN')
        await asyncio.sleep_ms(20)
    await _arm_rx_retry()


async def _pending_command_for_remote(remote_uid, remote_machine_id=None):
    """Prefer dispatch cache, then UC poll."""
    try:
        from dispatch import next_ack_command
        pending = next_ack_command(remote_uid)
        if isinstance(pending, dict):
            return pending
    except Exception:
        pass
    return await _fetch_remote_pending_command(remote_uid, remote_machine_id)


async def _mark_pending_command_sent(remote_uid, pending_cmd):
    try:
        from dispatch import mark_ack_command_sent
        await mark_ack_command_sent(remote_uid, pending_cmd, delivered=True)
    except Exception:
        pass


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
    _ = key
    await _sec_log(message, min_interval_s=interval_s)

async def hard_reset_lora():
    global lora, lora_rx_pending
    await debug_print("Hard LoRa reset + full pin isolation (v2.01.8)", "LORA")
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
    lora_rx_pending = False
    gc.collect()
    await asyncio.sleep_ms(500)
    await debug_print("Hard reset sequence complete", "LORA")

IRQ_RX_DONE = 0x0002
IRQ_TX_DONE = 0x0001
IRQ_PREAMBLE = 0x0004
IRQ_HEADER_VALID = 0x0010
IRQ_CRC_ERR = 0x0040
IRQ_HEADER_ERR = 0x0020
IRQ_TIMEOUT = 0x0200
IRQ_RX_CLEAR = IRQ_PREAMBLE | IRQ_HEADER_VALID | IRQ_HEADER_ERR | IRQ_CRC_ERR | IRQ_RX_DONE
IRQ_RX = IRQ_RX_DONE | IRQ_CRC_ERR | IRQ_HEADER_ERR | IRQ_TIMEOUT
IRQ_ALL = 0x03FF


def arm_rx():
    """Set continuous receive mode and restore the RX IRQ mask after TX."""
    if lora is None:
        return False
    try:
        irq = lora.getIrqStatus() if hasattr(lora, 'getIrqStatus') else 0
        if (irq & IRQ_RX_DONE) or bool(globals().get('lora_rx_pending', False)):
            return True
        try:
            state = lora.startReceive(0xFFFFFF)
        except TypeError:
            state = lora.startReceive()
        if state not in (0, None, True):
            return False
        if hasattr(lora, 'setDioIrqParams'):
            lora.setDioIrqParams(IRQ_ALL, IRQ_RX, 0, 0)
        return True
    except Exception:
        return False


def _chip_status():
    if lora is None or not hasattr(lora, 'getStatus'):
        return 0
    try:
        status = lora.getStatus()
        if isinstance(status, (bytes, bytearray)):
            status = status[0]
        return int(status) & 0xFF
    except Exception:
        return 0


async def ensure_lora_listening():
    global lora
    if lora is None:
        return False
    try:
        if hasattr(lora, 'startReceive'):
            if not arm_rx():
                await debug_print('ensure_lora_listening startReceive failed', 'WARN')
                return False
            return True
        if hasattr(lora, 'setOperatingMode'):
            mode = getattr(lora, 'MODE_RX', getattr(lora, 'RX', 1))
            lora.setOperatingMode(mode)
            return True
        await debug_print('ensure_lora_listening: no RX arming API', 'ERROR')
        return False
    except Exception as e:
        await debug_print('ensure_lora_listening error: %s' % e, 'ERROR')
        try:
            await log_error('ensure_lora_listening: %s' % e)
        except Exception:
            pass
        return False


async def _arm_rx_retry(tries=5):
    for i in range(max(1, int(tries))):
        if arm_rx():
            return True
        await asyncio.sleep_ms(40 + (i * 30))
    return await ensure_lora_listening()


def _lora_irq_callback(events=0):
    global lora_rx_pending, last_lora_activity_ts
    last_lora_activity_ts = time.time()
    try:
        rx_done = getattr(lora, 'RX_DONE', 0)
        if events is None or (events & rx_done):
            lora_rx_pending = True
    except Exception:
        lora_rx_pending = True


def _lora_rx_ready():
    if lora is None:
        return False
    if bool(globals().get('lora_rx_pending', False)):
        return True
    try:
        if hasattr(lora, 'getIrqStatus'):
            rx_done = int(getattr(lora, 'RX_DONE', IRQ_RX_DONE) or IRQ_RX_DONE)
            if int(lora.getIrqStatus() or 0) & rx_done:
                return True
    except Exception as e:
        try:
            asyncio.create_task(debug_print('LoRa RX event check error: %s' % e, 'WARN'))
        except Exception:
            pass
    return False


async def _record_lora_session_failure(reason):
    await debug_print(reason, 'ERROR')
    try:
        await log_error(reason)
    except Exception:
        pass
    try:
        if sdata is not None:
            sdata.error_count = int(getattr(sdata, 'error_count', 0) or 0) + 1
    except Exception:
        pass
    try:
        label = 'No READY' if 'READY' in reason else ('No HELLO' if 'HELLO' in reason else 'No ACK')
        await display_message('LoRa ' + label, 2)
    except Exception:
        pass


def _usable_unit_id():
    uid = str(getattr(settings, 'UNIT_ID', '') or '').strip()
    if not uid or uid.lower() in ('none', 'null', 'unknown', 'n/a'):
        if str(getattr(settings, 'NODE_TYPE', '')).lower() == 'remote':
            machine_id = str(get_machine_id() or '').strip()
            if machine_id:
                return '%s%s' % (getattr(settings, 'REMOTE_FALLBACK_UID_PREFIX', 'RM-'), machine_id[-8:])
        return ''
    return uid


_psram_pin_warning_shown = False


def warn_psram_pins():
    global _psram_pin_warning_shown
    if _psram_pin_warning_shown:
        return
    reserved = set(getattr(settings, 'PSRAM_RESERVED_PINS', (33, 34, 35, 36, 37)))
    names = ('CLK_PIN', 'MOSI_PIN', 'MISO_PIN', 'CS_PIN')
    conflicts = []
    for name in names:
        value = getattr(settings, name, None)
        if value in reserved:
            conflicts.append('%s=%s' % (name, value))
    if conflicts:
        message = 'LoRa pins share S3R2 PSRAM IOs: ' + ','.join(conflicts)
        print(message)
        _psram_pin_warning_shown = True
        if getattr(settings, 'PSRAM_PIN_POLICY', 'warn') == 'abort':
            print('PSRAM_PIN_POLICY=abort ignored on this board')

async def init_lora():
    global lora, lora_rx_pending
    warn_psram_pins()
    await debug_print("LoRa bulletproof init sequence (v2.01.9)", "LORA")
    await debug_print(
        'lora rf freq=%s sf=%s bw=%s sync=0x%02X pwr=%s' % (
            getattr(settings, 'FREQ', 915.0), getattr(settings, 'SF', 10),
            getattr(settings, 'BW', 125.0), getattr(settings, 'SYNC_WORD', 0xF4),
            getattr(settings, 'POWER', 17)),
        'LORA'
    )
    await debug_print(
        'lora pins cs=%s rst=%s busy=%s irq=%s clk=%s' % (
            getattr(settings, 'CS_PIN', 14), getattr(settings, 'RST_PIN', 40),
            getattr(settings, 'BUSY_PIN', 13), getattr(settings, 'IRQ_PIN', 4),
            getattr(settings, 'CLK_PIN', 35)),
        'LORA'
    )
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
                lora_rx_pending = False
                try:
                    if hasattr(lora, 'setDio2AsRfSwitch'):
                        lora.setDio2AsRfSwitch(True)
                except Exception as e:
                    await debug_print('DIO2 RF switch setup failed: %r' % (e,), 'WARN')
                try:
                    lora.setBlockingCallback(False, callback=_lora_irq_callback)
                except TypeError:
                    lora.setBlockingCallback(False, _lora_irq_callback)
                if not arm_rx():
                    await debug_print('RX arm failed after begin()', 'WARN')
                await debug_print("LoRa initialized successfully", "LORA")
                await display_message("LoRa OK", 1.5)
                sdata.lora_last_init_ts = time.time()
                sdata.lora_last_rx_ticks = time.ticks_ms()
                sdata.lora_rx_pause_until = time.time() + 3
                return True
            elif status == -2:
                await debug_print("Status -2 detected - aggressive reset already performed", "WARN")
                await asyncio.sleep(2.5)
        except Exception as e:
            await debug_print(f"init attempt {attempt+1} exception: {e}", "WARN")
            lora = None
        await asyncio.sleep(1.5)

    await debug_print("LoRa init FAILED after 20 attempts; connectLora will retry", "ERROR")
    await display_message("LoRa FAIL - RETRY", 2)
    await free_pins()
    lora = None
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
    remote_ts = remote_company = remote_site = remote_zone = remote_cluster = None
    remote_runtime = remote_script_runtime = temp_c = temp_f = bar = humid = None

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
            pending_cmd = await _pending_command_for_remote(uid, remote_machine_id)
        except Exception as cmd_fetch_e:
            await log_error(f"Pending command fetch error for {uid}: {cmd_fetch_e}")

        ack_delay = calculate_next_delay(uid)
        ack_msg = f"ACK:{uid}:NEXT:{ack_delay}"
        if isinstance(pending_cmd, dict):
            encoded_cmd = _encode_ack_command(pending_cmd)
            if encoded_cmd:
                ack_msg += f":CMD:{encoded_cmd}"
                await _mark_pending_command_sent(uid, pending_cmd)
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
            try:
                await _arm_rx_retry()
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

    if 'TS' in st['types'] and remote_machine_id:
        await proxy_register_for_remote(uid, remote_machine_id)

    if uid in settings.REMOTE_NODE_INFO:
        for temp_key in ('types', 'data', 'chunks', 'last_rx'):
            settings.REMOTE_NODE_INFO[uid].pop(temp_key, None)
        save_remote_node_info()


def _canonicalize_remote_record(uid, payload, rssi=None):
    return build_field_data_record(
        uid, node_type='remote', payload=payload,
        lora_rssi=rssi if rssi is not None else getattr(sdata, 'lora_SigStr', None),
    )


async def process_remote_field_data(uid, st, send_ack=True):
    """
    Process a fully assembled FIELD_DATA payload from a remote node,
    stage the records, and optionally send an ACK with the next sync delay.
    """
    try:
        if not isinstance(st, dict):
            st = {}
        payload = st.get('data', {}).get('FIELD_DATA')
        if payload is None:
            payload = _assemble_simple_session_field_data(st)

        defaults = {}
        batch_id = None
        if isinstance(payload, dict) and 'data' in payload:
            records = payload.get('data')
            batch_id = payload.get('batch_id') or st.get('batch_id')
            defaults = {
                'unit_id': payload.get('unit_id') or uid,
                'machine_id': payload.get('machine_id'),
                'firmware_version': payload.get('firmware_version') or payload.get('fw'),
                'NODE_TYPE': payload.get('NODE_TYPE') or payload.get('node_type') or 'remote',
            }
        elif isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            records = [payload]
            batch_id = payload.get('batch_id') or st.get('batch_id')
        else:
            records = None

        if isinstance(records, list) and records:
            merged_records = []
            for record in records:
                if not isinstance(record, dict):
                    continue
                merged = dict(defaults)
                merged.update(record)
                merged_records.append(_canonicalize_remote_record(uid, merged))

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

                if send_ack:
                    try:
                        ack_msg = f"ACK:{uid}:NEXT:{next_delay}"
                        if batch_id:
                            ack_msg += f":BID:{batch_id}"
                        pending_cmd = await _pending_command_for_remote(uid, settings.REMOTE_NODE_INFO[uid].get('MACHINE_ID'))
                        if isinstance(pending_cmd, dict):
                            encoded_cmd = _encode_ack_command(pending_cmd)
                            if encoded_cmd:
                                ack_msg += f":CMD:{encoded_cmd}"
                                await _mark_pending_command_sent(uid, pending_cmd)
                        ack_msg = await _secure_message(ack_msg, remote_uid=uid)
                        ack_ok = await _safe_send(ack_msg.encode(), remote_uid=uid)
                        if not ack_ok:
                            await log_error('ACK TX failed for %s' % uid)
                        await debug_print(
                            f"Sent FIELD_DATA ACK to {uid} next={next_delay}s bid={batch_id}",
                            "BASE_NODE"
                        )
                        try:
                            from oled import display_message
                            await display_message("ACK Sent", 0.8)
                        except Exception:
                            pass
                        try:
                            await _arm_rx_retry()
                        except Exception:
                            pass
                    except Exception as ack_e:
                        await log_error(f"FIELD_DATA ACK send error to {uid}: {ack_e}")

                try:
                    stage_remote_field_data(uid, merged_records)
                    await debug_print(f"Staged {len(merged_records)} remote field records from {uid}", "BASE_NODE")
                    await debug_print(
                        'Staged remote %s keys=%s' % (uid, ','.join(merged_records[0].keys())),
                        'BASE_NODE'
                    )
                except Exception as stage_e:
                    await log_error(f"stage_remote_field_data error for {uid}: {stage_e}")

    except Exception as e:
        await log_error(f"Remote field data processor error for {uid}: {e}")

    finally:
        try:
            if 'FIELD_DATA' in st.get('types', set()):
                st['types'].discard('FIELD_DATA')
            if isinstance(st.get('data'), dict):
                st['data'].pop('FIELD_DATA', None)
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


async def _send_final_ack(remote_uid, batch_id=None, reason='', remote_machine_id=None, retry=False):
    """Send a final ACK to a remote and include optional batch marker."""
    try:
        st = getattr(settings, 'REMOTE_NODE_INFO', {}).get(str(remote_uid), {})
        if isinstance(st, dict) and st.get('ack_sent') and not retry:
            return None
        next_delay = calculate_next_delay(remote_uid, retry=retry)
        ack_msg = f"ACK:{remote_uid}:NEXT:{next_delay}"
        if batch_id:
            ack_msg += f":BID:{batch_id}"

        try:
            if not remote_machine_id:
                node_meta = getattr(settings, 'REMOTE_NODE_INFO', {}).get(str(remote_uid), {})
                if isinstance(node_meta, dict):
                    remote_machine_id = node_meta.get('MACHINE_ID')
            pending_cmd = await _pending_command_for_remote(remote_uid, remote_machine_id)
            if isinstance(pending_cmd, dict):
                encoded_cmd = _encode_ack_command(pending_cmd)
                if encoded_cmd:
                    ack_msg += f":CMD:{encoded_cmd}"
                    await _mark_pending_command_sent(remote_uid, pending_cmd)
        except Exception as cmd_e:
            await log_error(f"Final ACK command piggyback error for {remote_uid}: {cmd_e}")

        ack_msg = await _secure_message(ack_msg, remote_uid=remote_uid)
        await _safe_send(ack_msg.encode(), remote_uid=remote_uid)
        try:
            await _arm_rx_retry()
        except Exception:
            pass
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

        try:
            now = time.time()
            if not hasattr(settings, 'REMOTE_NODE_INFO') or settings.REMOTE_NODE_INFO is None:
                settings.REMOTE_NODE_INFO = {}
            st = settings.REMOTE_NODE_INFO.setdefault(str(remote_uid), {})
            st['next_expected'] = now + int(next_delay)
            st['last_sync_ts'] = now
            if not retry:
                st['missed_syncs'] = 0
            st['ack_sent'] = True
            st['ack_sent_ticks'] = time.ticks_ms()
            st['session_active'] = False
            st['chunks'] = []
            st['last_chunk_ticks'] = 0
            save_remote_node_info()
            await debug_print(
                f"Registered {remote_uid} next_sync in {next_delay}s slot={st.get('slot')}",
                "BASE_NODE"
            )
        except Exception:
            pass

        live = _hub_live_uid()
        if (not live) or live == remote_uid:
            await _release_hub_session(remote_uid)
        return next_delay
    except Exception as e:
        await log_error(f"Final ACK error for {remote_uid}: {e}")
        return None


async def _maybe_force_ack_on_silence(remote_uid, st):
    try:
        if st.get('ack_sent'):
            return
        silent_need_ms = int(float(getattr(settings, 'LORA_SESSION_SILENCE_S', 5)) * 1000)
        last = int(st.get('last_chunk_ticks') or 0)
        if last <= 0 or time.ticks_diff(time.ticks_ms(), last) < silent_need_ms:
            return
        if not st.get('session_active'):
            return

        chunks = (st.get('chunks') or {}).get('FIELD_DATA') or {}
        have_simple = len([item for item in _simple_session_chunk_slots(st) if item])
        if not chunks and not have_simple and not st.get('saw_end'):
            return

        assembled = _assemble_simple_session_field_data(st)
        if assembled is None:
            await debug_print('Silence ACK retry-schedule for partial session %s' % remote_uid, 'WARN')
            await _send_final_ack(remote_uid, batch_id=st.get('batch_id'), reason='silence-retry', retry=True)
            st['session_active'] = False
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
        st.pop('last_chunk_ticks', None)
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
                st['ack_sent'] = False
                st['staged_ok'] = False
                st['chunks'] = {'FIELD_DATA': {}}
                st['chunk_total'] = 0
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
                    chunk_sz = int(_lora_data_budget())
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
                        from dispatch import after_remote_ready
                        await after_remote_ready(remote_uid)
                    except Exception as disp_e:
                        await debug_print('dispatch after READY failed: %s' % disp_e, 'WARN')
                    try:
                        await _arm_rx_retry()
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
                assembled = _assemble_simple_session_field_data(st)
                next_delay = await _send_final_ack(
                    remote_uid,
                    batch_id=batch_id,
                    reason='end' if assembled else 'end-retry',
                    retry=assembled is None,
                )
                await debug_print(
                    f"FINAL ACK to {remote_uid} ok={bool(next_delay)} next={int(next_delay or 0)} assembled={bool(assembled)}",
                    "BASE_NODE"
                )
                try:
                    await _arm_rx_retry()
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

            if orig_type == 'FIELD_DATA' and ('FIELD_DATA' in st.get('types', set())) and not handled_field_data:
                await process_remote_field_data(uid, st)
            elif orig_type == 'CMD_RESULT':
                await process_remote_command_result(uid, st)
            elif orig_type == 'STATE_FILES':
                await process_remote_state_files(uid, st)
            else:
                full_burst = all(t in st['types'] for t in ('TS', 'SETTINGS', 'SDATA'))
                if full_burst or (current_time - st['last_rx'] > 12):
                    await process_remote_burst(uid, st)

            chunks_dict = st.get('chunks', {})
            if isinstance(chunks_dict, dict):
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
            
def _session_field_chunks(st):
    """Return indexed FIELD_DATA chunks from burst or simple-session state."""
    chunks = st.get('chunks') if isinstance(st, dict) else None
    if isinstance(chunks, list):
        return {index: value for index, value in enumerate(chunks) if value}
    if isinstance(chunks, dict):
        field_chunks = chunks.get('FIELD_DATA', chunks)
        if isinstance(field_chunks, list):
            return {index: value for index, value in enumerate(field_chunks) if value}
        if isinstance(field_chunks, dict):
            return field_chunks
    return {}


async def check_incomplete_bursts():
    await debug_print("Incomplete-burst checker started (FORCE v3)", "BASE_NODE")
    while True:
        try:
            now_ticks = time.ticks_ms()
            info = getattr(settings, 'REMOTE_NODE_INFO', {})
            for uid, st in list(info.items()):
                if not isinstance(st, dict):
                    continue
                if st.get('ack_sent'):
                    continue
                if int(st.get('assemble_fail_count') or 0) >= 3:
                    st['simple_chunks'] = []
                    st['session_active'] = False
                    st['chunk_total'] = 0
                    st['assemble_fail_count'] = 0
                    if sdata is not None:
                        sdata.lora_session_busy = False
                    await _release_hub_session(uid)
                    continue
                field_chunks = _session_field_chunks(st)
                if not field_chunks:
                    field_chunks = {index: value for index, value in enumerate(st.get('simple_chunks', [])) if value}
                if not field_chunks:
                    continue

                last_ticks = int(st.get('last_chunk_ticks') or 0)
                if last_ticks == 0:
                    continue

                silent_ms = time.ticks_diff(now_ticks, last_ticks)

                silence_limit_ms = int(float(getattr(settings, 'LORA_SESSION_SILENCE_S', 4) or 4) * 1000)

                if silent_ms >= silence_limit_ms:
                    have = len(field_chunks)
                    total = int(st.get('chunk_total') or 0)
                    batch_id = st.get('batch_id')
                    assembled = _assemble_simple_session_field_data(st)
                    if assembled is None:
                        missing = [index for index in range(total) if index not in field_chunks]
                        last_log_time = st.get('last_incomplete_log_ticks')
                        now = time.ticks_ms()
                        if last_log_time is None or time.ticks_diff(now, last_log_time) >= 60000:
                            await debug_print(
                                f"Simple session partial {uid} have={have}/{total} missing={missing}", "WARN"
                            )
                            st['last_incomplete_log_ticks'] = now
                        await _send_final_ack(uid, batch_id=batch_id, reason='checker-retry', retry=True)
                        st['session_active'] = False
                        continue
                    if not st.get('staged_ok') and callable(globals().get('process_remote_field_data')):
                        await process_remote_field_data(uid, st, send_ack=False)
                        st['staged_ok'] = True
                        st['last_good_payload_ts'] = time.time()
                    await _send_final_ack(uid, batch_id=batch_id, reason='checker')
                    st['session_active'] = False
        except Exception as e:
            await log_error(f"check_incomplete_bursts: {e}")
        await asyncio.sleep(5)


_B64_KEEP = frozenset('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=')


def _clean_b64(value):
    """Keep only the first contiguous base64 run. Do not join across junk."""
    if not value:
        return ''
    text = str(value)
    for marker in ('\x00', '|HMAC:', '|CRC:', '|CNT:', 'HELLO:', 'END:', 'READY:', 'ACK:'):
        text = text.split(marker, 1)[0]
    if 'TYPE:' in text and not text.lstrip().startswith(('e', 'E', 'T', 't', 'A', 'a', 'I', 'i', 'W', 'w', '{')):
        text = text.split('TYPE:', 1)[0]
    out = []
    started = False
    for ch in text:
        if ch in _B64_KEEP:
            started = True
            out.append(ch)
        elif ch in ' \t\r\n':
            continue
        elif started:
            break
    cleaned = ''.join(out).rstrip('=')
    if not cleaned:
        return ''
    return cleaned + ('=' * ((-len(cleaned)) % 4))


def _b64_to_text(cleaned):
    if not cleaned or len(cleaned) < 4:
        return ''
    raw = None
    try:
        raw = bytes(_ub.a2b_base64(cleaned))
    except Exception:
        for n in (1, 2, 3, 4):
            trial = cleaned[:-n] if n < len(cleaned) else ''
            trial = trial.rstrip('=') + ('=' * ((-len(trial.rstrip('='))) % 4))
            if len(trial) < 4:
                continue
            try:
                raw = bytes(_ub.a2b_base64(trial))
                break
            except Exception:
                raw = None
    if not raw:
        return ''
    try:
        return raw.decode('utf-8').strip().rstrip('\x00')
    except Exception:
        try:
            return raw.decode('latin-1').strip().rstrip('\x00')
        except Exception:
            return ''


def _scan_json_string(text, key):
    token = '"%s":"' % key
    i = text.find(token)
    if i < 0:
        return None
    i += len(token)
    j = text.find('"', i)
    if j < 0:
        return text[i:i + 24]
    return text[i:j]


def _scan_json_number(text, key):
    token = '"%s":' % key
    i = text.find(token)
    if i < 0:
        return None
    i += len(token)
    while i < len(text) and text[i] in ' \t':
        i += 1
    j = i
    if j < len(text) and text[j] == '-':
        j += 1
    saw_digit = False
    while j < len(text) and (text[j].isdigit() or text[j] == '.'):
        if text[j].isdigit():
            saw_digit = True
        j += 1
    if not saw_digit:
        return None
    try:
        val = text[i:j]
        return float(val) if '.' in val else int(val)
    except Exception:
        return None


def _extract_short_fields(text, uid=None):
    """Pull compact telemetry keys from clipped JSON."""
    if not text:
        return None
    obj = {}
    u_val = _scan_json_string(text, 'u')
    if u_val:
        obj['u'] = u_val
    elif uid:
        obj['u'] = uid
    for key in ('t', 'h', 'b', 'v', 'ts'):
        num = _scan_json_number(text, key)
        if num is not None:
            obj[key] = num
    fw = _scan_json_string(text, 'fw')
    if fw:
        obj['fw'] = fw
    if 't' in obj or 'v' in obj or 'ts' in obj:
        return obj
    return None


def _salvage_json_object(text):
    if not text:
        return None
    if '{' in text:
        text = text[text.index('{'):]
    if '}' in text:
        try:
            obj = ujson.loads(text[:text.rindex('}') + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            text = text[:text.rindex('}')]
    junk = text.find('TYPEFIELD')
    if junk < 0:
        junk = text.find('TYPE:')
    if junk > 0:
        text = text[:junk]
    cut = text.rstrip()
    for _ in range(12):
        try:
            obj = ujson.loads(cut + '}')
            if isinstance(obj, dict) and obj:
                return obj
        except Exception:
            pass
        if cut.endswith(','):
            cut = cut[:-1]
            continue
        comma = cut.rfind(',')
        if comma > 0:
            cut = cut[:comma]
            continue
        break
    return _extract_short_fields(text)


def _compact_num(value, digits=2):
    """Shrink telemetry floats so compact JSON fits one LoRa frame."""
    if value is None or value == '':
        return None
    try:
        number = float(value)
    except Exception:
        return value
    if number != number:
        return None
    rounded = round(number, digits)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def _split_b64_parts(full_b64, budget):
    """Split base64 on 4-char boundaries. Never cut inside a quartet."""
    text = str(full_b64 or '')
    budget = max(48, int(budget or 120))
    budget = budget - (budget % 4)
    if budget < 48:
        budget = 48
    if len(text) <= budget:
        return [text]
    parts = []
    index = 0
    while index < len(text):
        parts.append(text[index:index + budget])
        index += budget
    return parts


def _decode_assembled_field_json(encoded, uid=None):
    """Parse concatenated base64 once. Do not accept a prefix object plus leftover tail."""
    text = _b64_to_text(encoded)
    if not text:
        return None
    try:
        obj = ujson.loads(text)
        if isinstance(obj, dict) and obj:
            if uid and not obj.get('u'):
                obj['u'] = uid
            return obj
    except Exception:
        pass
    if '{' in text and '}' in text:
        start = text.index('{')
        end = text.rindex('}') + 1
        head = text[start:end]
        tail = text[end:].strip().strip('\x00')
        if tail:
            return None
        try:
            obj = ujson.loads(head)
            if isinstance(obj, dict) and obj:
                if uid and not obj.get('u'):
                    obj['u'] = uid
                return obj
        except Exception:
            pass
    obj = _extract_short_fields(text, uid=uid)
    if isinstance(obj, dict) and (('ts' in obj and 'b' in obj) or ('t' in obj and 'v' in obj and 'ts' in obj)):
        return obj
    return None


def _normalize_chunk_payload(data_b64, uid=None):
    """Complete-payload helper only. Never use this on a multi-chunk fragment."""
    cleaned = _clean_b64(data_b64)
    return _decode_assembled_field_json(cleaned, uid=uid)


def _valid_unit_uid(uid):
    value = str(uid or '')
    if not value.startswith('unit-') or len(value) < 10 or len(value) > 24:
        return False
    return all(('a' <= char <= 'z') or ('0' <= char <= '9') for char in value[5:])


def _chunk_data_ok(data, uid=None):
    """A fragment is OK if it is clean base64. JSON is checked after concat."""
    _ = uid
    cleaned = _clean_b64(data)
    return bool(cleaned) and len(cleaned) >= 4


_SHORT_OK = ('HELLO:', 'END:', 'ACK:', 'READY:', 'BEACON:')
_TRUNC_HEADS = (
    'YPE:FIELD',
    'E:FIELD_DATA',
    'HEHELLO',
    'HELLO:uHELLO',
    'JTEND:',
    'DAEND:',
    '0/1,DA',
)


def _is_truncated_rx(raw):
    if not raw:
        return True
    if isinstance(raw, (bytes, bytearray)):
        text = raw.decode('utf-8', 'ignore')
    else:
        text = str(raw)
    text = text.strip('\x00').strip()
    if not text:
        return True
    if text.startswith(_SHORT_OK):
        return False
    if text.startswith((',UID:', 'UID:')):
        return False
    if text.startswith(('TYPE:', 'DATA_CHUNK,', 'IELD_DATA_CHUNK,', 'YPE:FIELD_DATA_CHUNK,')):
        if ('DATA:' not in text) and (len(raw) <= 24):
            return True
        return False
    if 'FIELD_DATA_CHUNK' in text and ',DATA:' in text:
        return False
    for bad in _TRUNC_HEADS:
        if bad in text[:24]:
            return True
    return False


def _simple_session_parse_chunk(clear):
    """Return uid, index, total, base64 data, and optional batch id from a chunk."""
    uid = ''
    idx = -1
    total = 0
    data_b64 = None
    batch_id = None
    try:
        _msg_type, parsed_uid, chunk, parsed_b64 = _remote_parse_type_message(clear)
        if parsed_uid:
            uid = str(parsed_uid).strip()
        if parsed_b64:
            data_b64 = str(parsed_b64).strip()
        if chunk and '/' in str(chunk):
            first, last = str(chunk).split('/', 1)
            idx, total = int(first), int(last)
    except Exception:
        pass
    try:
        for part in str(clear).replace(',', ' ').split():
            if part.startswith('UID:') and not uid:
                uid = part[4:].strip()
            elif part.startswith('CHUNK:') and idx < 0:
                first, last = part[6:].strip().split('/', 1)
                idx, total = int(first), int(last)
            elif part.startswith('BID:') and batch_id is None:
                batch_id = part[4:].strip()
            elif part.startswith('DATA:') and data_b64 is None:
                data_b64 = part[5:].strip()
    except Exception:
        pass
    return uid, idx, total, data_b64, batch_id


def _simple_session_chunk_slots(st):
    """Normalize simple-session chunks to indexed base64 slots."""
    slots = st.get('simple_chunks')
    if not isinstance(slots, list):
        slots = []
        st['simple_chunks'] = slots
    return slots


def _assemble_simple_session_field_data(st):
    """Decode complete simple-session base64 data into FIELD_DATA."""
    if not isinstance(st, dict):
        return None
    slots = _simple_session_chunk_slots(st)
    try:
        total = int(st.get('chunk_total') or 0)
    except Exception:
        total = 0
    if total <= 0:
        total = sum(1 for item in slots if item)
    if total <= 0:
        return None
    parts = []
    for index in range(total):
        item = slots[index] if index < len(slots) else None
        if not item:
            return None
        cleaned = _clean_b64(item)
        if not cleaned:
            return None
        parts.append(cleaned)
    encoded = ''.join(parts)
    uid = None
    try:
        for key, value in (getattr(settings, 'REMOTE_NODE_INFO', {}) or {}).items():
            if value is st:
                uid = key
                break
    except Exception:
        uid = None
    payload = _decode_assembled_field_json(encoded, uid=uid)
    if not isinstance(payload, dict):
        st['assemble_fail_count'] = int(st.get('assemble_fail_count') or 0) + 1
        if st['assemble_fail_count'] <= 2:
            try:
                asyncio.create_task(debug_print(
                    'Simple session assemble error: len=%d head=%r' % (len(encoded), encoded[:24]),
                    'WARN'
                ))
            except Exception:
                pass
        return None
    st['assemble_fail_count'] = 0
    if not isinstance(st.get('data'), dict):
        st['data'] = {}
    st['data']['FIELD_DATA'] = payload
    if not isinstance(st.get('types'), set):
        st['types'] = set(st.get('types') or [])
    st['types'].add('FIELD_DATA')
    return payload

async def handle_simple_session_hub(clear):
    """Handle simple remote sessions using HELLO/READY/CHUNK/END/ACK."""
    global last_lora_activity_ts
    try:
        last_lora_activity_ts = time.time()
        if not hasattr(settings, 'REMOTE_NODE_INFO') or settings.REMOTE_NODE_INFO is None:
            settings.REMOTE_NODE_INFO = {}

        if clear.startswith('HELLO:'):
            remote_uid = str(clear.split(':', 1)[1].strip().split('|')[0].strip())
            if not remote_uid:
                return
            await debug_print(f"HELLO from {remote_uid}", "BASE_NODE")
            if not await _claim_hub_session(remote_uid):
                return
            st = settings.REMOTE_NODE_INFO.setdefault(remote_uid, {})
            now = time.time()
            now_ticks = time.ticks_ms()
            st['last_hello_ts'] = now
            st['last_rx'] = now
            st['session_active'] = True
            st['ack_sent'] = False
            st['saw_end'] = False
            st['simple_chunks'] = []
            st['chunk_total'] = 0
            st['chunk_first_ts'] = now
            st['last_chunk_ts'] = now
            st['last_chunk_ticks'] = now_ticks
            st['missed_syncs'] = 0
            try:
                save_remote_node_info()
            except Exception:
                pass
            chunk_sz = int(_lora_data_budget())
            ready = f"READY:{remote_uid}:BASE:{getattr(settings, 'UNIT_ID', '')}:CHUNKSZ:{chunk_sz}"
            ready = await _secure_message(ready, remote_uid=remote_uid)
            ok = await _safe_send(ready.encode(), remote_uid=remote_uid)
            await debug_print(f"READY sent to {remote_uid} ok={ok} chunk={chunk_sz}", "BASE_NODE")
            try:
                from oled import display_message
                await display_message("READY", 0.6)
            except Exception:
                pass
            try:
                from dispatch import after_remote_ready
                await after_remote_ready(remote_uid)
            except Exception as disp_e:
                await debug_print('dispatch after READY failed: %s' % disp_e, 'WARN')
            await _arm_rx_retry()
            return

        if 'TYPE:FIELD_DATA_CHUNK' in clear or 'FIELD_DATA_CHUNK' in clear[:40]:
            uid, idx, total, data_b64, batch_id = _simple_session_parse_chunk(clear)
            if not uid or idx < 0 or total <= 0:
                await debug_print('Dropped malformed CHUNK frame', 'WARN')
                return
            if not await _claim_hub_session(uid, allow_steal=False):
                if sdata is not None:
                    sdata.lora_session_busy = True
            st = settings.REMOTE_NODE_INFO.setdefault(uid, {})
            if batch_id:
                st['batch_id'] = batch_id
            slots = _simple_session_chunk_slots(st)
            while len(slots) < total:
                slots.append('')
            raw_keep = _clean_b64(data_b64)
            if not raw_keep:
                await debug_print('Dropped empty CHUNK data idx=%d uid=%s' % (idx, uid), 'WARN')
                return
            if total <= 1:
                decoded = _decode_assembled_field_json(raw_keep, uid=uid)
                if isinstance(decoded, dict):
                    try:
                        raw_keep = _ub.b2a_base64(ujson.dumps(decoded).encode()).decode().strip()
                    except Exception:
                        pass
            slots[idx] = raw_keep
            st['simple_chunks'] = slots
            st['chunk_total'] = total
            st['session_active'] = True
            st['last_chunk_ts'] = time.time()
            st['last_chunk_ticks'] = time.ticks_ms()
            st['last_rx'] = time.time()
            have = sum(1 for item in slots if item)
            await debug_print(
                f"CHUNK stored idx={idx}/{total} uid={uid} have={have}/{total}",
                "BASE_NODE"
            )
            if have == total and all(slots[i] for i in range(total)):
                payload = _assemble_simple_session_field_data(st)
                if payload is not None:
                    st['staged_ok'] = False
                    await process_remote_field_data(uid, st, send_ack=False)
                    st['staged_ok'] = True
                    st['last_good_payload_ts'] = time.time()
            return

        if clear.startswith('END:'):
            parts = [p for p in clear.split(':') if p]
            uid = parts[1] if len(parts) > 1 else ''
            total = _safe_int(parts[2], 0) if len(parts) > 2 else 0
            if not uid:
                return
            st = settings.REMOTE_NODE_INFO.setdefault(uid, {})
            st['saw_end'] = True
            if total > 0:
                st['chunk_total'] = total
            assembled = _assemble_simple_session_field_data(st)
            if assembled is not None and not st.get('staged_ok'):
                await process_remote_field_data(uid, st, send_ack=False)
                st['staged_ok'] = True
                st['last_good_payload_ts'] = time.time()
            next_delay = await _send_final_ack(
                uid,
                batch_id=st.get('batch_id'),
                reason='end' if assembled else 'end-retry',
                retry=assembled is None,
            )
            await debug_print(
                f"FINAL ACK to {uid} ok={bool(next_delay)} next={int(next_delay or 0)} assembled={bool(assembled)}",
                "BASE_NODE"
            )
            st['session_active'] = False
            st['simple_chunks'] = []
            await _arm_rx_retry()
    except Exception as e:
        await log_error(f"Simple session handler error: {e}")


def _looks_collided(text):
    if not text:
        return False
    if text.count('HELLO:') > 1:
        return True
    if 'HELLO:' in text and ('TYPE:' in text or 'END:' in text or 'ACK:' in text):
        return True
    if text.startswith('HELLO:') and ('TYPE:' in text or 'unit-' in text[16:]):
        return True
    return False


def _recover_clipped_chunk(raw):
    """Rebuild TYPE:FIELD_DATA_CHUNK from a frame whose prefix was clipped."""
    if not raw:
        return None
    if isinstance(raw, (bytes, bytearray)):
        text = raw.decode('utf-8', 'ignore')
    else:
        text = str(raw)
    text = text.strip('\x00')
    if not text:
        return None
    if text.startswith('TYPE:FIELD_DATA_CHUNK'):
        return text
    if text.startswith((',UID:', 'UID:')):
        body = text[1:] if text.startswith(',') else text
        return 'TYPE:FIELD_DATA_CHUNK,' + body
    if 'FIELD_DATA_CHUNK' in text and ',DATA:' in text:
        start = text.find('TYPE:')
        if start < 0:
            start = text.find('FIELD_DATA_CHUNK')
        if start >= 0:
            return text[start:] if text[start:].startswith('TYPE:') else 'TYPE:' + text[start:]
    return None


async def handle_incoming_packet(raw):
    recovered = _recover_clipped_chunk(raw)
    if recovered:
        raw = recovered.encode() if isinstance(recovered, str) else recovered
    if _is_truncated_rx(raw):
        await debug_print('Dropped truncated RX (%d): %r' % (len(raw or b''), raw[:24] if raw else b''), 'WARN')
        return
    await debug_print('RAW RX (%d): %r' % (len(raw), raw[:80]), 'LORA_RX')
    try:
        try:
            raw_str = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
        except Exception:
            raw_str = str(raw)
        if _looks_collided(raw_str):
            await debug_print('Dropped collided RX: %r' % raw_str[:48], 'WARN')
            return
        if raw_str.startswith('TYPE:') or raw_str.startswith('DATA_CHUNK,') or raw_str.startswith('IELD_DATA_CHUNK,'):
            raw_str = await _unsecure_message(raw_str) or raw_str
            if raw_str.startswith('DATA_CHUNK,'):
                raw_str = 'TYPE:FIELD_' + raw_str
            elif raw_str.startswith('IELD_DATA_CHUNK,'):
                raw_str = 'TYPE:F' + raw_str
            if raw_str.startswith('TYPE:FIELD_DATA_CHUNK') or raw_str.startswith('TYPE:SETTINGS') or raw_str.startswith('TYPE:LORA_OTA_'):
                if _is_lora_hub_node() and raw_str.startswith('TYPE:FIELD_DATA_CHUNK'):
                    await handle_simple_session_hub(raw_str)
                    return
                if settings.NODE_TYPE == 'remote':
                    if raw_str.startswith('TYPE:SETTINGS'):
                        await _remote_handle_settings_wire_message(raw_str)
                        return
                    if raw_str.startswith('TYPE:LORA_OTA_'):
                        await _remote_handle_lora_ota_wire_message(raw_str)
                        return
        raw_str = await _unsecure_message(raw_str)
        if not raw_str:
            return
        if raw_str.startswith('FWD:'):
            try:
                _ttl, rest = raw_str[4:].split(':', 1)
                _origin, rest = rest.split(':', 1)
                _seq, inner = rest.split(':', 1)
                raw_str = inner
            except Exception:
                pass
        if _is_lora_hub_node() and (
            raw_str.startswith('HELLO:') or
            raw_str.startswith('END:') or
            raw_str.startswith('TYPE:FIELD_DATA_CHUNK')
        ):
            await handle_simple_session_hub(raw_str)
            return
        if raw_str.startswith('BEACON:') and settings.NODE_TYPE == 'remote':
            try:
                settings._last_hub_heard_ts = time.time()
            except Exception:
                pass
            return
        if raw_str.startswith('HELLO:') and settings.NODE_TYPE == 'remote':
            return
        if raw_str.startswith('READY:') and settings.NODE_TYPE == 'remote':
            if raw_str.split(':', 2)[1] == _usable_unit_id():
                settings.lora_ready_event.set()
            return
        if raw_str.startswith('ACK:') and settings.NODE_TYPE == 'remote':
            parts = raw_str.split(':')
            if len(parts) >= 4 and parts[1] == _usable_unit_id() and parts[2] == 'NEXT':
                try:
                    settings.lora_ack_delay = int(parts[3])
                    settings.lora_ack_event.set()
                except Exception:
                    pass
            return
        if raw_str.startswith('CMD:') and settings.NODE_TYPE == 'remote':
            return
        if _is_lora_hub_node():
            parts = raw_str.split(',', 3)
            if len(parts) >= 3 and parts[0].startswith('TYPE:') and parts[1].startswith('UID:'):
                packet_type = parts[0][5:]
                uid = parts[1][4:]
                extra = parts[2]
                payload = parts[3] if len(parts) > 3 else ''
                chunk_info = extra[6:] if extra.startswith('CHUNK:') else '0/1'
                data_b64 = payload[5:] if payload.startswith('DATA:') else payload
                try:
                    parsed = ujson.loads(_ub.a2b_base64(data_b64.encode()).decode()) if data_b64 else extra
                except Exception:
                    parsed = extra
                await lora_rx_queue.put({
                    'uid': uid,
                    'type': packet_type,
                    'chunk_info': chunk_info,
                    'data': parsed,
                    'batch_id': None,
                })
    except Exception as e:
        await log_error('Incoming packet handler error: %s' % e)


def _lora_data_budget():
    """Prefer a single-frame compact telemetry payload. Ignore tiny CHUNKSZ values."""
    max_pkt = _safe_int(getattr(settings, 'LORA_MAX_PACKET_SIZE', 200), 200)
    overhead = _safe_int(getattr(settings, 'LORA_CHUNK_OVERHEAD', 70), 70)
    wanted = _safe_int(getattr(settings, 'LORA_DATA_BUDGET', 0), 0)
    if wanted <= 0:
        wanted = _safe_int(getattr(settings, 'LORA_CHUNK_SIZE', 120), 120)
    if wanted < 96:
        wanted = 120
    return max(96, min(wanted, max_pkt - overhead, 140))


def _minimal_remote_payload():
    """Compact telemetry so typical field data fits one LoRa frame."""
    uid = _usable_unit_id()
    payload = {
        'u': uid,
        'fw': str(getattr(settings, 'FIRMWARE_VERSION', '') or '')[:12],
    }
    try:
        payload['t'] = _compact_num(getattr(sdata, 'last_temp_f', None), 2)
        payload['h'] = _compact_num(getattr(sdata, 'last_humid', None), 2)
        payload['b'] = _compact_num(getattr(sdata, 'last_bar', None), 2)
        payload['v'] = _compact_num(getattr(sdata, 'last_batt_v', None), 3)
    except Exception:
        pass
    payload['ts'] = int(time.time())
    return {key: value for key, value in payload.items() if value not in (None, '')}


async def send_field_data_controlled():
    """Remote simple-session sender: HELLO -> READY -> CHUNK(s) -> END."""
    global state, retry_count
    uid = _usable_unit_id()
    if not uid:
        await debug_print('FIELD_DATA skipped: no UNIT_ID', 'WARN')
        return False
    payload = _minimal_remote_payload()
    try:
        encoded = _ub.b2a_base64(ujson.dumps(payload).encode()).decode().strip()
    except Exception as e:
        await debug_print('FIELD_DATA encode failed: %s' % e, 'ERROR')
        return False
    hello = await _secure_message('HELLO:%s' % uid)
    if not await _safe_send(hello.encode()):
        await _record_lora_session_failure('HELLO TX failed')
        return False
    await _arm_rx_retry()
    ready_event = getattr(settings, 'lora_ready_event', None)
    if ready_event is None:
        settings.lora_ready_event = asyncio.Event()
        ready_event = settings.lora_ready_event
    ready_event.clear()
    try:
        await asyncio.wait_for(ready_event.wait(), float(getattr(settings, 'LORA_READY_TIMEOUT_S', 8)))
    except Exception:
        await _record_lora_session_failure('No READY from hub')
        return False
    await _remote_listen_settings_window(float(getattr(settings, 'LORA_SETTINGS_LISTEN_S', 2.5)))
    budget = _lora_data_budget()
    parts = _split_b64_parts(encoded, budget)
    total = len(parts)
    for idx, part in enumerate(parts):
        frame = 'TYPE:FIELD_DATA_CHUNK,UID:%s,CHUNK:%d/%d,DATA:%s' % (uid, idx, total, part)
        secured = await _secure_message(frame)
        if not await _safe_send(secured.encode()):
            await debug_print('CHUNK TX failed idx=%d/%d' % (idx, total), 'WARN')
            return False
        await _arm_rx_retry()
        if idx + 1 < total:
            await asyncio.sleep_ms(int(getattr(settings, 'LORA_INTERCHUNK_MS', 180)))
    end = await _secure_message('END:%s:%d' % (uid, total))
    if not await _safe_send(end.encode()):
        await debug_print('END TX failed', 'WARN')
    await _arm_rx_retry()
    ack_event = getattr(settings, 'lora_ack_event', None)
    if ack_event is None:
        settings.lora_ack_event = asyncio.Event()
        ack_event = settings.lora_ack_event
    ack_event.clear()
    try:
        await asyncio.wait_for(ack_event.wait(), float(getattr(settings, 'LORA_ACK_TIMEOUT_S', 10)))
        retry_count = 0
        state = STATE_IDLE
        return True
    except Exception:
        await _record_lora_session_failure('No ACK from hub')
        return False


def calculate_next_delay(uid, retry=False):
    interval = _safe_int(getattr(settings, 'LORA_REMOTE_INTERVAL_S', 180), 180)
    slot_width = _safe_int(getattr(settings, 'LORA_SLOT_WIDTH_S', 20), 20)
    info = (getattr(settings, 'REMOTE_NODE_INFO', {}) or {}).get(uid, {})
    slot = _safe_int((info or {}).get('slot'), 0)
    if slot <= 0:
        known = sorted((getattr(settings, 'REMOTE_NODE_INFO', {}) or {}).keys())
        try:
            slot = known.index(uid) + 1
        except Exception:
            slot = (abs(hash(uid)) % 8) + 1
        try:
            settings.REMOTE_NODE_INFO.setdefault(uid, {})['slot'] = slot
        except Exception:
            pass
    delay = interval + (slot * slot_width)
    if retry:
        delay = slot_width + (slot * 3)
    return max(15, delay)


def _encode_ack_command(pending_cmd):
    try:
        return _ub.b2a_base64(ujson.dumps(pending_cmd).encode()).decode().strip()
    except Exception:
        return ''


async def _fetch_remote_pending_command(remote_uid, remote_machine_id=None):
    _ = remote_machine_id
    try:
        from dispatch import next_ack_command
        return next_ack_command(remote_uid)
    except Exception:
        return None


async def process_remote_command_result(uid, st):
    try:
        payload = st.get('data', {}).get('CMD_RESULT')
        await debug_print('CMD_RESULT from %s: %r' % (uid, payload), 'BASE_NODE')
    except Exception as e:
        await log_error('CMD_RESULT processor error for %s: %s' % (uid, e))


async def _secure_message(body, remote_uid=None):
    text = body if isinstance(body, str) else body.decode()
    crc = _format_crc(crc16_ccitt(text))
    return '%s|CRC:%s' % (text, crc)


async def _unsecure_message(raw):
    text = raw if isinstance(raw, str) else raw.decode()
    if '|CRC:' not in text:
        return text
    body, crc_raw = text.rsplit('|CRC:', 1)
    ok, detail = verify_app_crc(body, crc_raw)
    if not ok:
        await _sec_log(detail)
        return None
    return body


def _hub_live_uid():
    global _hub_active_uid
    return _hub_active_uid


async def _claim_hub_session(uid, allow_steal=False):
    global _hub_active_uid, _hub_ready_ticks, _pending_hellos
    now_ticks = time.ticks_ms()
    live = _hub_active_uid
    if live and live != uid:
        idle_ms = int(float(getattr(settings, 'LORA_HUB_IDLE_RELEASE_S', 8)) * 1000)
        if allow_steal or time.ticks_diff(now_ticks, _hub_ready_ticks) >= idle_ms:
            await debug_print('Idle hub release uid=%s (no CHUNK after READY)' % live, 'BASE_NODE')
            await _release_hub_session(live)
        else:
            if uid and uid not in _pending_hellos:
                _pending_hellos.append(uid)
            await debug_print('Queued HELLO from %s; hub busy uid=%s' % (uid, live), 'BASE_NODE')
            if sdata is not None:
                sdata.lora_session_busy = True
            return False
    _hub_active_uid = uid
    _hub_ready_ticks = now_ticks
    if sdata is not None:
        sdata.lora_session_busy = True
    return True


async def _release_hub_session(uid=None):
    global _hub_active_uid, _pending_hellos
    live = _hub_active_uid
    if uid and live and uid != live:
        return
    _hub_active_uid = None
    if sdata is not None:
        sdata.lora_session_busy = False
    if _pending_hellos:
        nxt = _pending_hellos.pop(0)
        await debug_print('Releasing queued HELLO for %s' % nxt, 'BASE_NODE')
        await handle_simple_session_hub('HELLO:%s' % nxt)


async def _safe_send(payload, remote_uid=None):
    global lora, last_lora_activity_ts, _in_session_tx
    _ = remote_uid
    if lora is None:
        return False
    try:
        if bool(getattr(settings, 'LORA_CAD_ON', True)) and hasattr(lora, 'scanChannel'):
            try:
                busy = lora.scanChannel()
                if busy and not bool(getattr(settings, 'LORA_CAD_FORCE_TX', False)):
                    await asyncio.sleep_ms(int(getattr(settings, 'LORA_CAD_BACKOFF_MS', 40)))
            except Exception:
                pass
        data = _fill_tx(payload)
        _in_session_tx = True
        status = lora.send(data)
        last_lora_activity_ts = time.time()
        ok = status in (0, None, True)
        if not ok:
            await debug_print('TX status=%s' % status, 'WARN')
        return bool(ok)
    except Exception as e:
        await debug_print('TX error: %s' % e, 'ERROR')
        return False
    finally:
        _in_session_tx = False
        await _arm_rx_retry()


async def _read_lora_packet():
    global lora_rx_pending, _last_rx_digest, _last_rx_ticks
    lora_rx_pending = False
    if lora is None:
        return None
    try:
        raw = None
        if hasattr(lora, 'read'):
            raw = lora.read()
        elif hasattr(lora, 'recv'):
            raw = lora.recv()
        if not raw:
            return None
        if isinstance(raw, tuple):
            raw = raw[0]
        if not raw:
            return None
        digest = None
        try:
            digest = bytes(raw[:24])
        except Exception:
            digest = None
        now_ticks = time.ticks_ms()
        if digest and digest == _last_rx_digest and time.ticks_diff(now_ticks, _last_rx_ticks) < 400:
            return None
        _last_rx_digest = digest
        _last_rx_ticks = now_ticks
        return raw
    except Exception as e:
        await debug_print('RX read error: %s' % e, 'WARN')
        return None


async def _send_chunked(msg_type, data_b64, target_uid=None, chunk_len=120):
    uid = target_uid or _usable_unit_id()
    parts = _split_b64_parts(data_b64, chunk_len)
    total = len(parts)
    for idx, part in enumerate(parts):
        frame = 'TYPE:%s_CHUNK,UID:%s,CHUNK:%d/%d,DATA:%s' % (msg_type, uid, idx, total, part)
        secured = await _secure_message(frame, remote_uid=target_uid)
        if not await _safe_send(secured.encode(), remote_uid=target_uid):
            return False
        await asyncio.sleep_ms(int(getattr(settings, 'LORA_INTERCHUNK_MS', 180)))
    return True


STATE_IDLE = 0
STATE_HELLO = 1
STATE_DATA = 2
state = STATE_IDLE
retry_count = 0


async def connectLora():
    global lora, last_lora_activity_ts, last_rx_ts, state, retry_count
    last_beacon_ticks = time.ticks_ms()
    processor_started = False
    checker_started = False
    while True:
        try:
            if lora is None:
                ok = await init_lora()
                if not ok:
                    await asyncio.sleep(3)
                    continue
            if _is_lora_hub_node() and not processor_started:
                asyncio.create_task(base_packet_processor())
                processor_started = True
            if _is_lora_hub_node() and not checker_started:
                asyncio.create_task(check_incomplete_bursts())
                checker_started = True

            now_ticks = time.ticks_ms()
            current_time = time.time()
            irq = 0
            try:
                irq = int(lora.getIrqStatus() or 0) if hasattr(lora, 'getIrqStatus') else 0
            except Exception:
                irq = 0
            try:
                status = _chip_status()
                mode = (status >> 4) & 7
                await debug_print('irq=0x%04X status=0x%02X mode=%s' % (irq, status, mode), 'LORA')
            except Exception:
                pass
            if irq & (IRQ_CRC_ERR | IRQ_HEADER_ERR):
                await debug_print('RX CRC/header err irq=0x%04X' % irq, 'WARN')
                try:
                    if hasattr(lora, 'clearIrqStatus'):
                        lora.clearIrqStatus(IRQ_RX_CLEAR)
                except Exception:
                    pass
                await _arm_rx_retry()

            sessions_active = False
            try:
                sessions_active = any(
                    isinstance(info, dict) and info.get('session_active')
                    for info in (getattr(settings, 'REMOTE_NODE_INFO', {}) or {}).values()
                )
            except Exception:
                sessions_active = False
            if sdata is not None and getattr(sdata, 'lora_session_busy', False):
                sessions_active = True
            if _hub_active_uid:
                sessions_active = True
            if (sdata is not None and getattr(sdata, 'lora_session_busy', False)
                    and time.ticks_diff(now_ticks, _hub_ready_ticks) > 25000):
                await debug_print('LoRa session busy watchdog cleared', 'WARN')
                if sdata is not None:
                    sdata.lora_session_busy = False

            if settings.NODE_TYPE == 'remote':
                interval = _safe_int(getattr(settings, 'LORA_REMOTE_INTERVAL_S', 180), 180)
                last_send = float(getattr(sdata, 'lora_last_field_tx_ts', 0) or 0)
                if state == STATE_IDLE and (current_time - last_send) >= interval:
                    sent = await send_field_data_controlled()
                    if sdata is not None:
                        sdata.lora_last_field_tx_ts = current_time
                    await debug_print('sfd: cycle lines=2 sent=%s skipped=%s' % (1 if sent else 0, 'ok' if sent else 'empty'), 'FIELD_DATA')

            if (_is_lora_hub_node() and
                    not (bool(getattr(settings, 'LORA_BASE_BEACON_PAUSE_DURING_SESSION', True)) and sessions_active) and
                    time.ticks_diff(now_ticks, last_beacon_ticks) >=
                    int(getattr(settings, 'LORA_BASE_BEACON_INTERVAL_S', 30)) * 1000):
                last_beacon_ticks = now_ticks
                beacon = 'BEACON:%s' % _usable_unit_id()
                beacon_secured = await _secure_message(beacon)
                beacon_ok = await _safe_send(beacon_secured.encode())
                await debug_print('BEACON sent ok=%s' % beacon_ok, 'LORA')
                await _arm_rx_retry()

            rx_done = getattr(lora, 'RX_DONE', 0)
            packet_ready = bool(irq & rx_done) or bool(lora_rx_pending)
            if not packet_ready:
                await asyncio.sleep_ms(20)
                continue
            last_lora_activity_ts = current_time
            msg = await _read_lora_packet()
            if msg:
                await handle_incoming_packet(msg)
                if ((_chip_status() >> 4) & 7) != 5:
                    await _arm_rx_retry()
            await asyncio.sleep_ms(5)

        except Exception as e:
            await log_error(f"Main LoRa loop error: {e!r}")
            await display_message("LoRa Err", 2)
            lora = None
            if settings.NODE_TYPE == 'remote':
                state = STATE_IDLE
                retry_count = 0
            await asyncio.sleep(3)
            gc.collect()
            
# ===================== MAIN.PY EXPORTS (v2.01.9) =====================

try:
    TMON_AI
except NameError:
    try:
        from utils import TMON_AI
    except Exception:
        class _TMONAIShim:
            error_count = 0
            last_error = ''
        TMON_AI = _TMONAIShim()


async def handle_ota_job(job):
    """Apply one UC/WP OTA job if helpers exist. Safe no-op otherwise."""
    if not job:
        return False
    try:
        if callable(send_ota_job_status):
            job_id = None
            if isinstance(job, dict):
                job_id = job.get('id') or job.get('job_id')
            if job_id:
                try:
                    await send_ota_job_status(job_id, 'received')
                except TypeError:
                    send_ota_job_status(job_id, 'received')
        await debug_print('OTA job seen: %r' % (job if not isinstance(job, dict) else list(job.keys()),), 'OTA')
        return True
    except Exception as e:
        await debug_print('handle_ota_job error: %s' % e, 'WARN')
        return False


async def check_missed_syncs():
    """One pass. Warn when a registered remote misses next_expected / heartbeat."""
    if not _is_lora_hub_node():
        return
    info_map = getattr(settings, 'REMOTE_NODE_INFO', None)
    if not isinstance(info_map, dict) or not info_map:
        return
    now = time.time()
    threshold = _safe_int(getattr(settings, 'LORA_MISSED_SYNC_THRESHOLD', 3), 3)
    heartbeat_timeout = _safe_int(getattr(settings, 'LORA_HEARTBEAT_INTERVAL_S', 120), 120) * 2
    next_sync_window = _safe_int(getattr(settings, 'LORA_NEXT_SYNC', 100), 100)
    changed = False
    for node_id, info in list(info_map.items()):
        if not isinstance(info, dict):
            continue
        if info.get('session_active'):
            continue
        next_expected = info.get('next_expected')
        last_seen = info.get('last_heartbeat_ts') or info.get('last_rx') or info.get('last_good_payload_ts') or 0
        try:
            missed = int(info.get('missed_syncs') or 0)
        except Exception:
            missed = 0
        should_increment = False
        if next_expected:
            try:
                if now > (float(next_expected) + next_sync_window):
                    should_increment = True
            except Exception:
                pass
        elif last_seen:
            try:
                if now > (float(last_seen) + heartbeat_timeout):
                    should_increment = True
            except Exception:
                pass
        if should_increment:
            missed += 1
            info['missed_syncs'] = missed
            changed = True
            if missed >= threshold:
                await debug_print('Excessive missed syncs/heartbeats from %s' % node_id, 'WARN')
        elif missed:
            info['missed_syncs'] = 0
            changed = True
    if changed:
        try:
            save_remote_node_info()
        except Exception:
            pass


async def periodic_wp_sync():
    """One pass. Base/wifi WordPress register + settings + data + OTA poll."""
    if not _is_lora_hub_node():
        return
    if getattr(sdata, 'lora_session_busy', False):
        return
    async def _call(fn):
        if not fn:
            return None
        try:
            result = fn()
            if hasattr(result, 'send') or hasattr(result, '__await__'):
                return await result
            return result
        except Exception as e:
            await debug_print('periodic_wp_sync helper error: %s' % e, 'WARN')
            return None
    if not any((register_with_wp, send_settings_to_wp, fetch_settings_from_wp, send_data_to_wp, poll_ota_jobs)):
        return
    await _call(register_with_wp)
    await _call(send_settings_to_wp)
    await _call(fetch_settings_from_wp)
    await _call(send_data_to_wp)
    jobs = await _call(poll_ota_jobs)
    if isinstance(jobs, dict):
        jobs = jobs.get('jobs') or jobs.get('data') or []
    if isinstance(jobs, list):
        for job in jobs:
            try:
                await handle_ota_job(job)
            except Exception as e:
                await debug_print('OTA job handle error: %s' % e, 'WARN')


async def expected_sync_watcher():
    """Optional hub helper: log remotes that are due soon."""
    if not _is_lora_hub_node():
        return
    info_map = getattr(settings, 'REMOTE_NODE_INFO', None)
    if not isinstance(info_map, dict):
        return
    now = time.time()
    for node_id, info in info_map.items():
        if not isinstance(info, dict):
            continue
        nxt = info.get('next_expected')
        if not nxt:
            continue
        try:
            delta = float(nxt) - now
        except Exception:
            continue
        if 0 <= delta <= 15:
            await debug_print('Expecting %s around now' % node_id, 'BASE_NODE')


async def heartbeat_ping_loop():
    """One pass remote heartbeat if enabled."""
    if str(getattr(settings, 'NODE_TYPE', '')).lower() != 'remote':
        return
    if not bool(getattr(settings, 'LORA_REMOTE_HEARTBEAT', False)):
        return
    try:
        await _send_lora_heartbeat()
    except NameError:
        uid = _usable_unit_id()
        if not uid:
            return
        msg = await _secure_message('HEARTBEAT:%s' % uid)
        await _safe_send(msg.encode())
        await _arm_rx_retry()
    except Exception as e:
        await debug_print('heartbeat error: %s' % e, 'WARN')
