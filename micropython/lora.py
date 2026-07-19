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
rx_counter = 0
remote_counters = {}

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
    error_log_file = getattr(settings, 'ERROR_LOG_FILE', '/logs/lora_errors.log')
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

REMOTE_NODE_INFO_FILE = getattr(settings, 'LOG_DIR', '/logs') + '/remote_node_info.json'

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
                'MACHINE_ID': remote_machine_id
            })
            save_remote_node_info()

        if None not in (uid, remote_runtime, remote_script_runtime, temp_c, temp_f, bar, humid):
            base_ts = time.time()
            log_line = f"{base_ts},{uid},{remote_ts},{remote_runtime},{remote_script_runtime},{temp_c},{temp_f},{bar},{humid}\n"
            log_file = getattr(settings, 'LOG_FILE', '/logs/lora.log')
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

    if 'SDATA' in st['types']:
        sdata_dict = st['data']['SDATA']
        stage_remote_field_data(uid, [sdata_dict])

    next_delay = calculate_next_delay(uid)
    now = time.time()
    if uid not in settings.REMOTE_NODE_INFO:
        settings.REMOTE_NODE_INFO[uid] = {}
    settings.REMOTE_NODE_INFO[uid]['next_expected'] = now + next_delay
    settings.REMOTE_NODE_INFO[uid]['missed_syncs'] = 0
    save_remote_node_info()

    # SEND ACK (optionally piggyback one pending command for this remote)
    try:
        pending_cmd = await _fetch_remote_pending_command(uid, remote_machine_id)
        ack_msg = f"ACK:{uid}:NEXT:{next_delay}"
        if isinstance(pending_cmd, dict):
            cmd_blob = _encode_ack_command(pending_cmd)
            if cmd_blob:
                ack_msg += f":CMD:{cmd_blob}"
        ack_msg = await _secure_message(ack_msg, remote_uid=uid)
        await _send_with_retry(ack_msg.encode())
        if isinstance(pending_cmd, dict):
            await debug_print(f"Sent ACK+CMD to {uid} (cmd_id={pending_cmd.get('id')})", "BASE_NODE")
        else:
            await debug_print(f"Sent ACK with next delay {next_delay}s to {uid}", "BASE_NODE")
        await display_message("ACK Sent", 0.5)
    except Exception as ack_e:
        await log_error(f"ACK send error to {uid}: {ack_e}")

    # Proxy HTTP calls AFTER ACK
    if 'TS' in st['types'] and remote_machine_id:
        await proxy_register_for_remote(uid, remote_machine_id)

    # Cleanup ONLY temporary burst tracking keys - KEEP persistent info (next_expected, missed_syncs, COMPANY, etc.)
    if uid in settings.REMOTE_NODE_INFO:
        for temp_key in ('types', 'data', 'chunks', 'last_rx'):
            settings.REMOTE_NODE_INFO[uid].pop(temp_key, None)
        save_remote_node_info()


async def process_remote_field_data(uid, st):
    try:
        payload = st.get('data', {}).get('FIELD_DATA')
        defaults = {}
        if isinstance(payload, dict) and 'data' in payload:
            records = payload.get('data')
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
                if 'unit_id' not in merged or not merged.get('unit_id'):
                    merged['unit_id'] = uid
                merged_records.append(merged)
            if merged_records:
                stage_remote_field_data(uid, merged_records)
                await debug_print(f"Staged {len(merged_records)} remote field records from {uid}", "BASE_NODE")
    except Exception as e:
        await log_error(f"Remote field data processor error for {uid}: {e}")
    finally:
        if 'FIELD_DATA' in st.get('types', set()):
            st['types'].discard('FIELD_DATA')
        if isinstance(st.get('data'), dict):
            st['data'].pop('FIELD_DATA', None)
        if isinstance(st.get('chunks'), dict):
            st['chunks'].pop('FIELD_DATA', None)


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
    while True:
        try:
            packet = await lora_rx_queue.get()
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
    global last_rx_ts
    msg_str = msg.rstrip(b'\x00').decode()

    # EARLY FILTER: ignore packets from wrong network
    if "NET:" in msg_str and "PASS:" in msg_str:
        if f"NET:{settings.LORA_NETWORK_NAME}" not in msg_str or f"PASS:{settings.LORA_NETWORK_PASSWORD}" not in msg_str:
            return

    msg_str = await _unsecure_message(msg_str)
    if not msg_str:
        return

    await debug_print(f"Base RX: {msg_str[:120]}...", "BASE_NODE")
    last_rx_ts = time.time()
    sdata.lora_SigStr = lora.getRSSI() if hasattr(lora, 'getRSSI') else -60
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

# ===================== SECURE MESSAGING (unchanged) =====================
async def _secure_message(msg_str, remote_uid=None):
    global tx_counter
    if not getattr(settings, 'LORA_HMAC_ENABLED', False):
        return msg_str
    if settings.NODE_TYPE == 'remote':
        counter = tx_counter + 1
    else:
        if remote_uid is None:
            return msg_str
        if remote_uid not in remote_counters:
            remote_counters[remote_uid] = {'tx': 0, 'rx': 0}
        counter = remote_counters[remote_uid]['tx'] + 1
    counter_str = str(counter)
    counter_bytes = counter.to_bytes(4, 'big')

    crc_hex = _format_crc(crc16_ccitt(msg_str.encode())) if getattr(settings, 'LORA_CRC_ENABLED', True) else None

    if getattr(settings, 'LORA_ENCRYPT_ENABLED', False):
        msg_bytes = msg_str.encode()
        stream_key = getattr(settings, 'LORA_ENCRYPT_SECRET', b'').encode() + counter_bytes
        stream_hash = uhashlib.sha256(stream_key).digest()
        encrypted = xor_bytes(msg_bytes, stream_hash)
        enc_b64 = _ub.b2a_base64(encrypted).rstrip(b'\n').decode()
        to_hmac = encrypted + counter_bytes
        hmac_val = hmac_sha256(getattr(settings, 'LORA_HMAC_SECRET', b'').encode(), to_hmac)
        hmac_hex = _ub.hexlify(hmac_val).decode()[:getattr(settings, 'LORA_HMAC_TRUNCATE', 16)]
        secure_msg = f"ENC:{enc_b64},CNT:{counter},HMAC:{hmac_hex}"
    else:
        to_hmac = msg_str.encode() + counter_str.encode()
        hmac_val = hmac_sha256(getattr(settings, 'LORA_HMAC_SECRET', b'').encode(), to_hmac)
        hmac_hex = _ub.hexlify(hmac_val).decode()[:getattr(settings, 'LORA_HMAC_TRUNCATE', 16)]
        secure_msg = msg_str + f",CNT:{counter},HMAC:{hmac_hex}"

    if crc_hex is not None:
        secure_msg = secure_msg + f",CRC:{crc_hex}"

    if settings.NODE_TYPE == 'remote':
        tx_counter = counter
    else:
        remote_counters[remote_uid]['tx'] = counter
    return secure_msg

async def _unsecure_message(msg_str):
    global rx_counter
    if not getattr(settings, 'LORA_HMAC_ENABLED', False):
        return msg_str

    cnt = None
    hmac_hex = None
    crc_hex = None
    is_enc = False
    enc_b64 = None
    original_msg = msg_str

    if msg_str.startswith('ENC:'):
        is_enc = True
        parts = msg_str.split(',')
        for p in parts:
            if p.startswith('ENC:'):
                enc_b64 = p[4:]
            elif p.startswith('CNT:'):
                cnt = int(p[4:])
            elif p.startswith('HMAC:'):
                hmac_hex = p[5:]
            elif p.startswith('CRC:'):
                crc_hex = p[4:]
    else:
        if ',CNT:' not in msg_str or ',HMAC:' not in msg_str:
            await log_error("Invalid secure format (no CNT/HMAC)")
            return None
        try:
            parts = msg_str.split(',')
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
            original_msg = ','.join(message_parts)
        except Exception:
            return None

    if cnt is None or hmac_hex is None:
        await log_error("Missing CNT or HMAC in secure message")
        return None

    counter_bytes = cnt.to_bytes(4, 'big')
    if is_enc:
        encrypted = _ub.a2b_base64(enc_b64.encode())
        to_hmac = encrypted + counter_bytes
    else:
        to_hmac = original_msg.encode() + str(cnt).encode()

    hmac_val = hmac_sha256(getattr(settings, 'LORA_HMAC_SECRET', b'').encode(), to_hmac)
    hmac_hex_calc = _ub.hexlify(hmac_val).decode()[:getattr(settings, 'LORA_HMAC_TRUNCATE', 16)]
    if hmac_hex_calc != hmac_hex:
        await log_error("HMAC verification failed")
        return None

    if is_enc:
        stream_key = getattr(settings, 'LORA_ENCRYPT_SECRET', b'').encode() + counter_bytes
        stream_hash = uhashlib.sha256(stream_key).digest()
        decrypted = xor_bytes(encrypted, stream_hash)
        try:
            msg_str = decrypted.decode()
        except Exception:
            await log_error("Decryption decode failed")
            return None
    else:
        msg_str = original_msg

    if crc_hex:
        try:
            expected_crc = int(crc_hex, 16)
        except Exception:
            await log_error("Invalid CRC format")
            return None
        actual_crc = crc16_ccitt(msg_str.encode())
        if actual_crc != expected_crc:
            await log_error(f"CRC mismatch: expected {crc_hex}, got {_format_crc(actual_crc)}")
            return None

    if cnt <= rx_counter:
        await log_error(f"Replay attack detected (cnt {cnt} <= rx_counter {rx_counter})")
        return None
    rx_counter = cnt

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

async def _send_chunked(msg_type, full_b64):
    max_b64_chunk_len = 100 if getattr(settings, 'LORA_ENCRYPT_ENABLED', False) else 160
    b64_len = len(full_b64)
    if b64_len <= max_b64_chunk_len:
        data_str = f"TYPE:{msg_type},UID:{settings.UNIT_ID},DATA:{full_b64}"
        data_str = await _secure_message(data_str)
        await _send_with_retry(data_str.encode())
    else:
        num_chunks = (b64_len + max_b64_chunk_len - 1) // max_b64_chunk_len
        for i in range(num_chunks):
            chunk_start = i * max_b64_chunk_len
            chunk_end = chunk_start + max_b64_chunk_len
            chunk_b64 = full_b64[chunk_start:chunk_end]
            data_str = f"TYPE:{msg_type}_CHUNK,UID:{settings.UNIT_ID},CHUNK:{i}/{num_chunks},DATA:{chunk_b64}"
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
        result_file = getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + f'/ota_job_{job_id or "temp"}.result.json'

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
                        pending_file = getattr(settings, 'OTA_PENDING_FILE', None) or (getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/ota_pending.flag')
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
    else:
        sync_rate = 10
        response_timeout = 30

    last_heartbeat_ts = 0
    while True:
        try:
            current_time = time.time()

            if current_time - last_lora_activity_ts > 90:
                await debug_print("LoRa health watchdog - re-init", "WARN")
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
                    await debug_print("Remote: starting full check-in (periodic)", "REMOTE_NODE")
                    await display_message("TX Data...", 0.8)
                    ts = time.time()
                    data_str = f"T:{ts},U:{settings.UNIT_ID},M:{get_machine_id()},NET:{getattr(settings,'LORA_NETWORK_NAME','tmon')},PASS:{getattr(settings,'LORA_NETWORK_PASSWORD','12345')},C:{getattr(settings,'COMPANY','')},S:{getattr(settings,'SITE','')},Z:{getattr(settings,'ZONE','')},K:{getattr(settings,'CLUSTER','')},R:{sdata.loop_runtime},SR:{sdata.script_runtime},TC:{sdata.cur_temp_c},TF:{sdata.cur_temp_f},B:{sdata.cur_bar_pres},H:{sdata.cur_humid}"
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
                                    if len(parts) >= 6:
                                        i = 4
                                        while i + 1 < len(parts):
                                            if parts[i] == 'CMD':
                                                ack_cmd = _decode_ack_command(parts[i + 1])
                                                break
                                            i += 2
                                    if isinstance(ack_cmd, dict):
                                        await debug_print("Remote: received command via ACK", "REMOTE_NODE")
                                        await _apply_remote_command_from_ack(ack_cmd)
                                    last_rx_ts = time.time()
                                    sdata.lora_SigStr = lora.getRSSI() if hasattr(lora, 'getRSSI') else -60
                                    sdata.LORA_CONNECTED = True
                                    await ensure_lora_listening()
                                    await asyncio.sleep(0.5)
                                    state = STATE_IDLE
                                    sleep_time = next_delay or (sync_rate + random.randint(-30, 30))
                                    await asyncio.sleep(max(10, sleep_time))
                                    continue
                                else:
                                    await debug_print("Ignored ACK for different UID", "REMOTE_NODE")
                        await ensure_lora_listening()

                    if time.time() - start_wait > response_timeout:
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