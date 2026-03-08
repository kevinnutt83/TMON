# TMON v2.00.2 - LoRa (FULL BULLETPROOF GATEWAY + TRUE MULTI-REMOTE + ACK + SNR + CMD + OTA)

import ujson
import os
import uasyncio as asyncio
import select
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
    from sx1262 import SX1262
except ImportError:
    SX1262 = None
try:
    import sdata
    import settings
except ImportError:
    sdata = None
    settings = None

from utils import free_pins, debug_print, TMON_AI, stage_remote_field_data, stage_remote_files, record_field_data, get_machine_id
from relay import toggle_relay
from oled import display_message
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
    poll_device_commands = getattr(_wp, 'poll_device_commands', None)
except Exception:
    register_with_wp = send_data_to_wp = send_settings_to_wp = fetch_settings_from_wp = None
    send_file_to_wp = request_file_from_wp = heartbeat_ping = poll_ota_jobs = poll_device_commands = None

# Add for security
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

file_lock = asyncio.Lock()
pin_lock = asyncio.Lock()
lora = None
last_lora_error_ts = 0
proxy_last_ts = {}

tx_counter = 0
rx_counter = 0
remote_counters = {}

async def log_error(error_msg):
    global last_lora_error_ts
    ts = time.time()
    if ts - last_lora_error_ts < 5:
        return
    last_lora_error_ts = ts
    log_line = f"{ts}: {error_msg}\n"
    error_log_file = getattr(settings, 'ERROR_LOG_FILE', '/errors.log')
    try:
        async with file_lock:
            with open(error_log_file, 'a') as f:
                f.write(log_line)
    except Exception:
        await debug_print(f"[FATAL] Failed to log error: {error_msg}", "ERROR")
    await asyncio.sleep(0)

def simple_checksum(path):
    checksum = 0
    with open(path, 'rb') as f:
        chunk = f.read(128)
        while chunk:
            for b in chunk:
                checksum = (checksum + b) % 65536
            chunk = f.read(128)
    return checksum

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

async def hard_reset_lora():
    global lora
    if lora:
        try:
            lora.reset()
        except Exception:
            pass
    try:
        for pin_num in (getattr(settings, 'CLK_PIN', 0), getattr(settings, 'MOSI_PIN', 0), getattr(settings, 'MISO_PIN', 0),
                        getattr(settings, 'CS_PIN', 0), getattr(settings, 'IRQ_PIN', 0), getattr(settings, 'RST_PIN', 0),
                        getattr(settings, 'BUSY_PIN', 0), getattr(settings, 'I2C_A_SCL_PIN', 0), getattr(settings, 'I2C_A_SDA_PIN', 0)):
            p = machine.Pin(pin_num, machine.Pin.IN)
            p.value(0)
    except Exception:
        pass
    try:
        rst = machine.Pin(getattr(settings, 'RST_PIN', 0), machine.Pin.OUT)
        rst.value(0)
        await asyncio.sleep_ms(50)
        rst.value(1)
        await asyncio.sleep_ms(150)
    except Exception:
        pass
    gc.collect()

async def init_lora():
    global lora
    await debug_print('Init LoRa: Beginning LoRa Module Initialization', 'LORA')
    await display_message("LoRa Init...", 1)
    for attempt in range(10):
        try:
            await hard_reset_lora()
            await free_pins()
            await asyncio.sleep(0.5)
            lora = SX1262(
                getattr(settings, 'SPI_BUS', 0), getattr(settings, 'CLK_PIN', 0), getattr(settings, 'MOSI_PIN', 0), getattr(settings, 'MISO_PIN', 0),
                getattr(settings, 'CS_PIN', 0), getattr(settings, 'IRQ_PIN', 0), getattr(settings, 'RST_PIN', 0), getattr(settings, 'BUSY_PIN', 0)
            )
            status = lora.begin(
                freq=getattr(settings, 'FREQ', 915.0), bw=getattr(settings, 'BW', 125), sf=getattr(settings, 'SF', 9), cr=getattr(settings, 'CR', 5),
                syncWord=getattr(settings, 'SYNC_WORD', 0xF4), power=getattr(settings, 'POWER', 14),
                currentLimit=getattr(settings, 'CURRENT_LIMIT', 60.0), preambleLength=getattr(settings, 'PREAMBLE_LEN', 8),
                implicit=False, implicitLen=0xFF, crcOn=getattr(settings, 'CRC_ON', True),
                txIq=False, rxIq=False,
                tcxoVoltage=getattr(settings, 'TCXO_VOLTAGE', 1.7), useRegulatorLDO=getattr(settings, 'USE_LDO', False),
                blocking=False
            )
            await debug_print(f'begin() attempt {attempt+1}: status {status}', 'LORA')
            if status == 0:
                lora.setBlockingCallback(False)
                lora.recv(0, False, 0)
                await debug_print("LoRa initialized successfully", "LORA")
                await display_message("LoRa OK", 1.5)
                gc.collect()
                return True
            elif status == -2:
                await debug_print("Status -2 - extra reset cycle", "WARN")
                await asyncio.sleep(1.0)
        except Exception as e:
            await debug_print(f"init attempt {attempt+1} exception: {e}", "WARN")
        await asyncio.sleep(0.8)
    await debug_print("LoRa init FAILED after 10 attempts", "FATAL")
    await display_message("LoRa FAIL", 3)
    await free_pins()
    lora = None
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

def load_counters():
    global tx_counter, rx_counter, remote_counters
    if not getattr(settings, 'LORA_HMAC_ENABLED', False):
        return
    counter_file = getattr(settings, 'LORA_HMAC_COUNTER_FILE', '/lora_counters.json')
    try:
        with open(counter_file, 'r') as f:
            d = ujson.load(f)
        if settings.NODE_TYPE == 'remote':
            tx_counter = d.get('tx', random.randint(0, 100000))
            rx_counter = d.get('rx', 0)
        else:
            remote_counters = d.get('remotes', {})
            for u in remote_counters:
                remote_counters[u] = {'tx': remote_counters[u].get('tx', 0), 'rx': remote_counters[u].get('rx', 0)}
    except Exception:
        if settings.NODE_TYPE == 'remote':
            tx_counter = random.randint(0, 100000)
            rx_counter = 0
        else:
            remote_counters = {}

load_counters()

def save_counters():
    if not getattr(settings, 'LORA_HMAC_ENABLED', False):
        return
    counter_file = getattr(settings, 'LORA_HMAC_COUNTER_FILE', '/lora_counters.json')
    try:
        d = {}
        if settings.NODE_TYPE == 'remote':
            d['tx'] = tx_counter
            d['rx'] = rx_counter
        else:
            d['remotes'] = {}
            for u, c in remote_counters.items():
                d['remotes'][u] = {'tx': c['tx'], 'rx': c['rx']}
        with open(counter_file, 'w') as f:
            ujson.dump(d, f)
    except Exception:
        pass

async def proxy_register_for_remote(remote_uid, remote_machine_id):
    if not register_with_wp:
        return
    now = time.time()
    if remote_uid in proxy_last_ts and now - proxy_last_ts[remote_uid] < 270:
        await debug_print(f"Proxy register throttled for {remote_uid}", "BASE_NODE")
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

        await debug_print(f"Proxy check-in/register for remote {remote_uid} (MACHINE_ID={remote_machine_id[:16]}...)", "BASE_NODE")
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
                await log_error(f"Proxy reg attempt {attempt+1} failed for {remote_uid}: {e}")
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

async def connectLora():
    global lora
    if not getattr(settings, 'ENABLE_LORA', True):
        return False
    await debug_print(f"Enabling LoRa Module for TMON - {getattr(settings, 'FIRMWARE_VERSION', 'unknown')}...", "LORA")
    await display_message("LoRa Starting...", 1)

    async with pin_lock:
        if not await init_lora():
            return False

    # Deterministic boot stagger for remotes based on UID to prevent initial collisions
    if settings.NODE_TYPE == 'remote':
        uid = settings.UNIT_ID
        stagger_seed = 0
        for c in uid:
            stagger_seed = (stagger_seed * 31 + ord(c)) % 1000000
        initial_stagger = stagger_seed % 600  # 0-599s
        await debug_print(f"Remote deterministic boot stagger {initial_stagger}s based on UID", "REMOTE_NODE")
        await asyncio.sleep(initial_stagger)

    STATE_IDLE = 0
    STATE_WAIT_RESPONSE = 2
    STATE_RECEIVING = 3
    state = STATE_IDLE
    pending_commands = {}
    ota_send_pending = {}
    remote_states = {}
    failure_count = 0

    if settings.NODE_TYPE == 'remote':
        sync_rate = getattr(settings, 'LORA_SYNC_RATE', 300)
        response_timeout = 180  # Increased for better reliability
    else:
        sync_rate = 10
        response_timeout = 25
        burst_window = 15  # Reduced to send ACK sooner

    while True:
        try:
            current_time = time.time()
            if lora is None:
                if not await init_lora():
                    await asyncio.sleep(10)
                    continue

            # ===================== REMOTE NODE (bulletproof TX + RX arm) =====================
            if settings.NODE_TYPE == 'remote':
                if lora is None:
                    state = STATE_IDLE
                    continue
                if state == STATE_IDLE:
                    await debug_print("Remote: starting full check-in (TS + SETTINGS + SDATA)", "REMOTE_NODE")
                    await display_message("TX Data...", 0.8)
                    ts = time.time()

                    # TS packet
                    data_str = f"TS:{ts},UID:{settings.UNIT_ID},MACHINE_ID:{get_machine_id()},COMPANY:{getattr(settings,'COMPANY','')},SITE:{getattr(settings,'SITE','')},ZONE:{getattr(settings,'ZONE','')},CLUSTER:{getattr(settings,'CLUSTER','')},RUNTIME:{sdata.loop_runtime},SCRIPT_RUNTIME:{sdata.script_runtime},TEMP_C:{sdata.cur_temp_c},TEMP_F:{sdata.cur_temp_f},BAR:{sdata.cur_bar_pres},HUMID:{sdata.cur_humid}"
                    data_str = await _secure_message(data_str)
                    await _send_with_retry(data_str.encode())

                    # Small delay between packets to reduce collision risk
                    await asyncio.sleep(random.uniform(0.5, 1.5))

                    # SETTINGS packet
                    settings_dict = {k: getattr(settings, k) for k in dir(settings) if not k.startswith('__') and not callable(getattr(settings, k))}
                    settings_b64 = _ub.b2a_base64(ujson.dumps(settings_dict).encode()).rstrip(b'\n').decode()
                    data_str = f"TYPE:SETTINGS,UID:{settings.UNIT_ID},DATA:{settings_b64}"
                    data_str = await _secure_message(data_str)
                    await _send_with_retry(data_str.encode())

                    await asyncio.sleep(random.uniform(0.5, 1.5))

                    # SDATA packet - SAFE VERSION (never crashes the TX)
                    try:
                        sdata_dict = {k: v for k, v in getattr(sdata, '__dict__', {}).items() if not k.startswith('__') and not callable(v)}
                        sdata_b64 = _ub.b2a_base64(ujson.dumps(sdata_dict).encode()).rstrip(b'\n').decode()
                        await debug_print("Remote: full sdata snapshot sent", "REMOTE_NODE")
                    except Exception as sd_e:
                        await log_error(f"sdata snapshot failed (using minimal): {sd_e}")
                        sdata_dict = {
                            'loop_runtime': getattr(sdata, 'loop_runtime', 0),
                            'script_runtime': getattr(sdata, 'script_runtime', 0),
                            'cur_temp_c': getattr(sdata, 'cur_temp_c', 0),
                            'cur_temp_f': getattr(sdata, 'cur_temp_f', 0),
                            'cur_bar_pres': getattr(sdata, 'cur_bar_pres', 0),
                            'cur_humid': getattr(sdata, 'cur_humid', 0),
                            'lora_SigStr': getattr(sdata, 'lora_SigStr', 0),
                            'lora_snr': getattr(sdata, 'lora_snr', 0),
                        }
                        sdata_b64 = _ub.b2a_base64(ujson.dumps(sdata_dict).encode()).rstrip(b'\n').decode()

                    data_str = f"TYPE:SDATA,UID:{settings.UNIT_ID},DATA:{sdata_b64}"
                    data_str = await _secure_message(data_str)
                    await _send_with_retry(data_str.encode())

                    # CRITICAL: Arm RX right after last TX so we catch the ACK/CMD/OTA
                    if lora is not None:
                        lora.recv(0, False, 0)
                    await asyncio.sleep_ms(200)  # Increased delay for mode switch

                    await debug_print("Remote: TX burst complete - armed RX, waiting for base response", "REMOTE_NODE")
                    await display_message("Waiting ACK", 1)

                    state = STATE_WAIT_RESPONSE
                    start_wait = time.time()
                    received_response = False
                    next_delay = None

                elif state == STATE_WAIT_RESPONSE:
                    if lora is None:
                        continue
                    ev = lora._events()
                    if ev & lora.RX_DONE:
                        if lora is None:
                            continue
                        msg, err = lora.recv()
                        try:
                            rssi = lora.getRSSI()
                            snr = lora.getSNR() if hasattr(lora, 'getSNR') else 0
                            sdata.lora_SigStr = rssi
                            sdata.lora_snr = snr
                            await debug_print(f"Remote RX SigStr: {rssi} dBm, SNR: {snr} dB", "REMOTE_NODE")
                        except Exception:
                            pass
                        if err == 0 and msg:
                            msg_str = msg.rstrip(b'\x00').decode()
                            msg_str = await _unsecure_message(msg_str)
                            if msg_str is None:
                                await debug_print("Remote RX: invalid secure message", "WARN")
                                if lora is not None:
                                    lora.recv(0, False, 0)
                                continue
                            await debug_print(f"Remote RX: {msg_str[:100]}...", "REMOTE_NODE")
                            await display_message("RX OK", 0.8)

                            if msg_str.startswith('ACK:'):
                                await debug_print("✅ Remote successfully connected to base", "REMOTE_NODE")
                                received_response = True
                                parts = msg_str.split(':')
                                if len(parts) >= 4 and parts[2] == 'NEXT':
                                    try:
                                        next_delay = int(parts[3])
                                        await debug_print(f"Received next delay: {next_delay}s", "REMOTE_NODE")
                                    except ValueError:
                                        await log_error("Invalid next delay in ACK")
                            elif msg_str.startswith('CMD:'):
                                received_response = True
                                cmd_parts = msg_str.split(':', 2)
                                if len(cmd_parts) == 3 and (cmd_parts[1] == 'ALL' or cmd_parts[1] == settings.UNIT_ID):
                                    command = cmd_parts[2]
                                    if '(' in command and command.endswith(')'):
                                        func_name, args_str = command.split('(', 1)
                                        args = [a.strip() for a in args_str.rstrip(')').split(',')] if args_str else []
                                        if func_name in command_handlers:
                                            command_handlers[func_name](*args)
                            elif msg_str.startswith('OTA:'):
                                received_response = True
                                try:
                                    ota_json = msg_str[4:].strip()
                                    ota_info = ujson.loads(ota_json)
                                    handle_ota_chunk(ota_info)
                                    await debug_print(f"Remote OTA chunk {ota_info.get('chunk_num',0)}/{ota_info.get('total_chunks',0)}", "REMOTE_NODE")
                                    await display_message("OTA OK" if getattr(settings, 'last_chunk_ok', True) else "OTA ERR", 1)
                                except Exception as oe:
                                    await log_error(f"OTA handle error on remote: {oe}")
                        else:
                            if err != 0:
                                await debug_print(f"Remote RX error: {err}", "WARN")

                        if lora is not None:
                            lora.recv(0, False, 0)   # re-arm for more packets

                    # Timeout handling
                    if time.time() - start_wait > response_timeout:
                        if received_response:
                            await debug_print("Remote: check-in successful - scheduling next", "REMOTE_NODE")
                            await display_message("Success", 1)
                            failure_count = 0
                            if next_delay is None:
                                jitter = random.randint(-120, 120)
                                sleep_time = sync_rate + jitter
                            else:
                                sleep_time = next_delay
                        else:
                            await debug_print(f"Remote: no response after {response_timeout}s - retrying with backoff", "WARN")
                            await display_message("No Resp", 1.5)
                            failure_count += 1
                            backoff = min(600, 60 * (2 ** failure_count) + random.randint(-60, 60))
                            sleep_time = backoff
                        state = STATE_IDLE
                        await asyncio.sleep(max(10, sleep_time))  # ensure at least 10s
                        gc.collect()

            # ===================== BASE NODE =====================
            elif settings.NODE_TYPE == 'base':
                if lora is None:
                    continue
                if state == STATE_IDLE:
                    state = STATE_RECEIVING

                if state == STATE_RECEIVING:
                    if lora is None:
                        continue
                    ev = lora._events()
                    if ev & lora.RX_DONE:
                        if lora is None:
                            continue
                        msg, err = lora.recv()
                        try:
                            rssi = lora.getRSSI()
                            snr = lora.getSNR() if hasattr(lora, 'getSNR') else 0
                            sdata.lora_SigStr = rssi
                            sdata.lora_snr = snr
                            await debug_print(f"Base RX SigStr: {rssi} dBm, SNR: {snr} dB", "BASE_NODE")
                        except Exception:
                            pass
                        if err == 0 and msg:
                            msg_str = msg.rstrip(b'\x00').decode()
                            msg_str = await _unsecure_message(msg_str)
                            if msg_str is None:
                                await debug_print("Base RX: invalid secure message", "WARN")
                                if lora is not None:
                                    lora.recv(0, False, 0)
                                gc.collect()
                                continue
                            await debug_print(f"Base received from remote: {msg_str[:120]}...", "BASE_NODE")
                            await display_message("RX Remote", 1)

                            remote_uid = None
                            packet_type = 'UNKNOWN'
                            parsed_data = None

                            if msg_str.startswith('TS:'):
                                packet_type = 'TS'
                                parts = msg_str.split(',')
                                remote_ts = parts[0].split(':', 1)[1].strip()
                                remote_uid = remote_company = remote_site = remote_zone = remote_cluster = None
                                remote_runtime = remote_script_runtime = temp_c = temp_f = bar = humid = None
                                remote_machine_id = None
                                for part in parts[1:]:
                                    if ':' not in part:
                                        continue
                                    key, value = part.split(':', 1)
                                    value = value.strip()
                                    if key == 'UID': remote_uid = value
                                    elif key == 'MACHINE_ID': remote_machine_id = value
                                    elif key == 'COMPANY': remote_company = value
                                    elif key == 'SITE': remote_site = value
                                    elif key == 'ZONE': remote_zone = value
                                    elif key == 'CLUSTER': remote_cluster = value
                                    elif key == 'RUNTIME': remote_runtime = value
                                    elif key == 'SCRIPT_RUNTIME': remote_script_runtime = value
                                    elif key == 'TEMP_C': temp_c = value
                                    elif key == 'TEMP_F': temp_f = value
                                    elif key == 'BAR': bar = value
                                    elif key == 'HUMID': humid = value
                                parsed_data = {
                                    'remote_ts': remote_ts, 'remote_company': remote_company, 'remote_site': remote_site,
                                    'remote_zone': remote_zone, 'remote_cluster': remote_cluster, 'remote_runtime': remote_runtime,
                                    'remote_script_runtime': remote_script_runtime, 'temp_c': temp_c, 'temp_f': temp_f,
                                    'bar': bar, 'humid': humid, 'remote_machine_id': remote_machine_id
                                }

                            elif msg_str.startswith('TYPE:'):
                                parts = msg_str.split(',')
                                msg_type = None
                                remote_uid = None
                                data_b64 = None
                                for p in parts:
                                    if p.startswith('TYPE:'): msg_type = p[5:]
                                    elif p.startswith('UID:'): remote_uid = p[4:]
                                    elif p.startswith('DATA:'): data_b64 = p[5:]
                                if msg_type in ('SETTINGS', 'SDATA') and remote_uid and data_b64:
                                    packet_type = msg_type
                                    try:
                                        json_data = _ub.a2b_base64(data_b64.encode()).decode()
                                        parsed_dict = ujson.loads(json_data)
                                        parsed_data = parsed_dict
                                    except Exception as e:
                                        await log_error(f"Failed to parse {msg_type} for {remote_uid}: {e}")

                            if remote_uid and packet_type != 'UNKNOWN':
                                if remote_uid not in remote_states:
                                    remote_states[remote_uid] = {'types': set(), 'last_rx': current_time, 'data': {}}
                                remote_states[remote_uid]['types'].add(packet_type)
                                remote_states[remote_uid]['data'][packet_type] = parsed_data
                                remote_states[remote_uid]['last_rx'] = current_time

                        if lora is not None:
                            lora.recv(0, False, 0)
                        gc.collect()

                    # Process completed bursts
                    for uid in list(remote_states.keys()):
                        st = remote_states[uid]
                        if current_time - st['last_rx'] > burst_window:
                            await debug_print(f"Processing burst for {uid}: types {st['types']}", "BASE_NODE")

                            remote_machine_id = None

                            if 'TS' in st['types']:
                                data = st['data']['TS']
                                remote_ts = data['remote_ts']
                                remote_company = data['remote_company']
                                remote_site = data['remote_site']
                                remote_zone = data['remote_zone']
                                remote_cluster = data['remote_cluster']
                                remote_runtime = data['remote_runtime']
                                remote_script_runtime = data['remote_script_runtime']
                                temp_c = data['temp_c']
                                temp_f = data['temp_f']
                                bar = data['bar']
                                humid = data['humid']
                                remote_machine_id = data['remote_machine_id']

                                if uid and remote_company is not None:
                                    if not hasattr(settings, 'REMOTE_NODE_INFO'):
                                        settings.REMOTE_NODE_INFO = {}
                                    settings.REMOTE_NODE_INFO[uid] = {
                                        'COMPANY': remote_company, 'SITE': remote_site,
                                        'ZONE': remote_zone, 'CLUSTER': remote_cluster,
                                        'MACHINE_ID': remote_machine_id
                                    }
                                    save_remote_node_info()

                                if None in (uid, remote_runtime, remote_script_runtime, temp_c, temp_f, bar, humid):
                                    await log_error(f"Missing fields from {uid}")
                                else:
                                    base_ts = time.time()
                                    log_line = f"{base_ts},{uid},{remote_ts},{remote_runtime},{remote_script_runtime},{temp_c},{temp_f},{bar},{humid}\n"
                                    await debug_print(f"Received telemetry from {uid}", "BASE_NODE")
                                    log_file = getattr(settings, 'LOG_FILE', '/logs/data.log')
                                    async with file_lock:
                                        with open(log_file, 'a') as f:
                                            f.write(log_line)
                                    record_field_data()

                                    try:
                                        temp_f_val = float(temp_f)
                                        bar_val = float(bar)
                                        humid_val = float(humid)
                                    except ValueError:
                                        temp_f_val = bar_val = humid_val = 0.0

                                    await findLowestTemp(temp_f_val)
                                    await findHighestTemp(temp_f_val)
                                    await findLowestBar(bar_val)
                                    await findHighestBar(bar_val)
                                    await findLowestHumid(humid_val)
                                    await findHighestHumid(humid_val)

                                    if temp_f_val < 80:
                                        pending_commands[uid] = "toggle_relay(1,on,5)"

                                if uid and remote_machine_id:
                                    await proxy_register_for_remote(uid, remote_machine_id)

                            if 'SETTINGS' in st['types']:
                                settings_dict = st['data']['SETTINGS']
                                stage_remote_files(uid, {'settings.py': ujson.dumps(settings_dict).encode()})

                                remote_machine_id = settings.REMOTE_NODE_INFO.get(uid, {}).get('MACHINE_ID', None)
                                if remote_machine_id is None:
                                    await log_error(f"No MACHINE_ID for {uid} during settings proxy")
                                else:
                                    original_uid = settings.UNIT_ID
                                    original_get = None
                                    send_ok = False
                                    try:
                                        import utils as _u
                                        if hasattr(_u, 'get_machine_id'):
                                            original_get = _u.get_machine_id
                                            def temp_get():
                                                return str(remote_machine_id)
                                            _u.get_machine_id = temp_get
                                        settings.UNIT_ID = uid

                                        for att in range(3):
                                            try:
                                                if asyncio.iscoroutinefunction(send_settings_to_wp):
                                                    await send_settings_to_wp()
                                                else:
                                                    send_settings_to_wp()
                                                send_ok = True
                                                break
                                            except Exception as se:
                                                await log_error(f"Settings proxy attempt {att+1} fail for {uid}: {se}")
                                                await asyncio.sleep(1.5 * (att + 1))
                                    finally:
                                        settings.UNIT_ID = original_uid
                                        if original_get and hasattr(_u, 'get_machine_id'):
                                            _u.get_machine_id = original_get
                                    if send_ok:
                                        await debug_print(f"Proxied settings for {uid} to Unit Connector", "BASE_NODE")
                                        await display_message(f"Proxy {uid[:8]}", 1)
                                    gc.collect()

                            if 'SDATA' in st['types']:
                                sdata_dict = st['data']['SDATA']
                                stage_remote_field_data(uid, [sdata_dict])

                                remote_machine_id = settings.REMOTE_NODE_INFO.get(uid, {}).get('MACHINE_ID', None)
                                if remote_machine_id is None:
                                    await log_error(f"No MACHINE_ID for {uid} during sdata proxy")
                                else:
                                    original_uid = settings.UNIT_ID
                                    original_get = None
                                    send_ok = False
                                    try:
                                        import utils as _u
                                        if hasattr(_u, 'get_machine_id'):
                                            original_get = _u.get_machine_id
                                            def temp_get():
                                                return str(remote_machine_id)
                                            _u.get_machine_id = temp_get
                                        settings.UNIT_ID = uid

                                        for att in range(3):
                                            try:
                                                if asyncio.iscoroutinefunction(send_data_to_wp):
                                                    await send_data_to_wp()
                                                else:
                                                    send_data_to_wp()
                                                send_ok = True
                                                break
                                            except Exception as se:
                                                await log_error(f"SDATA proxy attempt {att+1} fail for {uid}: {se}")
                                                await asyncio.sleep(1.5 * (att + 1))
                                    finally:
                                        settings.UNIT_ID = original_uid
                                        if original_get and hasattr(_u, 'get_machine_id'):
                                            _u.get_machine_id = original_get
                                    if send_ok:
                                        await debug_print(f"Proxied sdata for {uid} to Unit Connector", "BASE_NODE")
                                        await display_message(f"Proxy {uid[:8]}", 1)
                                        ota_send_pending[uid] = True
                                    gc.collect()

                            # Calculate next delay and set expected
                            next_delay = calculate_next_delay(uid)
                            now = time.time()
                            settings.REMOTE_NODE_INFO[uid]['next_expected'] = now + next_delay
                            settings.REMOTE_NODE_INFO[uid]['missed_syncs'] = 0
                            save_remote_node_info()

                            # Send responses
                            try:
                                ack_msg = f"ACK:{uid}:NEXT:{next_delay}"
                                ack_msg = await _secure_message(ack_msg, remote_uid=uid)
                                await _send_with_retry(ack_msg.encode())
                                await debug_print(f"Sent ACK with next delay {next_delay}s to {uid}", "BASE_NODE")
                                await display_message("ACK Sent", 0.5)

                                if uid in pending_commands:
                                    cmd = pending_commands.pop(uid)
                                    cmd_msg = f"CMD:{uid}:{cmd}"
                                    cmd_msg = await _secure_message(cmd_msg, remote_uid=uid)
                                    await _send_with_retry(cmd_msg.encode())
                                    await debug_print(f"Sent CMD to {uid}: {cmd}", "BASE_NODE")
                                    await display_message("CMD Sent", 0.5)

                                ota_pending = ota_send_pending.pop(uid, False)
                                if ota_pending:
                                    chunk = get_next_ota_chunk(uid)
                                    if chunk:
                                        ota_str = f"OTA:{ujson.dumps(chunk)}"
                                        ota_str = await _secure_message(ota_str, remote_uid=uid)
                                        await _send_with_retry(ota_str.encode())
                                        await debug_print(f"Sent OTA chunk {chunk['chunk_num']}/{chunk['total_chunks']} to {uid}", "BASE_NODE")
                                        advance_ota_chunk(uid)
                                        await display_message(f"OTA→{uid[:6]}", 0.5)
                            except Exception as ack_e:
                                await log_error(f"ACK/CMD/OTA send error to {uid}: {ack_e}")

                            del remote_states[uid]
                            gc.collect()

                if int(current_time) % 30 == 0:
                    await _poll_and_relay_commands(pending_commands)

            await asyncio.sleep(0.05)
        except Exception as e:
            await log_error(f"LoRa gateway loop error: {e}")
            await display_message("LoRa Err", 2)
            lora = None  # Force re-initialization on next iteration
            if settings.NODE_TYPE == 'remote':
                state = STATE_IDLE   # force retry on remote
            await asyncio.sleep(2)
            gc.collect()

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

    # Update counter
    if settings.NODE_TYPE == 'remote':
        tx_counter = counter
    else:
        remote_counters[remote_uid]['tx'] = counter
    save_counters()
    return secure_msg

async def _unsecure_message(msg_str):
    global rx_counter
    if not getattr(settings, 'LORA_HMAC_ENABLED', False):
        return msg_str
    parts = msg_str.split(',')
    cnt_str = None
    hmac_received = None
    enc_b64 = None
    base_idx = len(msg_str)
    for i in range(len(parts)-1, -1, -1):
        p = parts[i]
        if p.startswith('HMAC:'):
            hmac_received = p[5:]
            base_idx = msg_str.rfind(',HMAC:')
            msg_str = msg_str[:base_idx]
            break
        if p.startswith('CNT:'):
            cnt_str = p[4:]
        if p.startswith('ENC:'):
            enc_b64 = p[4:]
    if hmac_received is None and getattr(settings, 'LORA_HMAC_REJECT_UNSIGNED', True):
        return None
    if cnt_str is None:
        return None
    try:
        cnt = int(cnt_str)
    except:
        return None
    counter_bytes = cnt.to_bytes(4, 'big')
    if enc_b64:
        encrypted = _ub.a2b_base64(enc_b64.encode())
        to_hmac = encrypted + counter_bytes
    else:
        to_hmac = msg_str.encode() + cnt_str.encode()
    computed_hex = _ub.hexlify(hmac_sha256(getattr(settings, 'LORA_HMAC_SECRET', b'').encode(), to_hmac)).decode()[:getattr(settings, 'LORA_HMAC_TRUNCATE', 16)]
    if not computed_hex == hmac_received:
        return None
    # Replay check
    if getattr(settings, 'LORA_HMAC_REPLAY_PROTECT', True):
        if settings.NODE_TYPE == 'remote':
            last_rx = rx_counter
        else:
            # Extract UID
            uid = None
            for part in msg_str.split(','):
                if part.startswith('UID:'):
                    uid = part[4:]
                    break
            if uid is None:
                return None
            if uid not in remote_counters:
                remote_counters[uid] = {'tx': 0, 'rx': 0}
            last_rx = remote_counters[uid]['rx']
        if cnt <= last_rx:
            return None
    # Decrypt
    if enc_b64:
        stream_key = getattr(settings, 'LORA_ENCRYPT_SECRET', b'').encode() + counter_bytes
        stream_hash = uhashlib.sha256(stream_key).digest()
        encrypted = _ub.a2b_base64(enc_b64.encode())
        msg_bytes = xor_bytes(encrypted, stream_hash)
        try:
            msg_str = msg_bytes.decode()
        except:
            return None
    # Update rx counter
    if settings.NODE_TYPE == 'remote':
        rx_counter = cnt
    else:
        remote_counters[uid]['rx'] = cnt
    save_counters()
    return msg_str

async def _send_with_retry(data, retries=5):
    global lora
    if lora is None:
        return
    max_cad_attempts = 5
    cad_symbols = getattr(settings, 'CAD_SYMBOLS', 3)
    cad_backoff_s = getattr(settings, 'LORA_CAD_BACKOFF_S', 3.0)
    for att in range(retries):
        # CAD check if supported
        if hasattr(lora, 'cad'):
            channel_busy = False
            for cad_att in range(max_cad_attempts):
                if lora.cad(cad_symbols):
                    backoff = random.uniform(0.5, cad_backoff_s)
                    await asyncio.sleep(backoff)
                    channel_busy = True
                else:
                    channel_busy = False
                    break
            if channel_busy:
                await log_error("Channel busy after CAD attempts")
                await asyncio.sleep(1)
                continue
        if lora is None:
            await log_error("LoRa is None after CAD")
            return
        try:
            if lora is None:
                raise RuntimeError("LoRa None before send")
            lora.send(data)
            if not await _wait_tx_done():
                raise RuntimeError("TX done wait failed")
            if lora is not None:
                lora.recv(0, False, 0)  # re-arm RX after TX
            save_counters()  # after successful send
            return
        except Exception as e:
            await log_error(f"TX attempt {att+1} failed: {e}")
            if "NoneType" in str(e):
                lora = None
                await hard_reset_lora()
                await log_error("Force reinit LoRa due to NoneType error")
                return  # Stop retries on critical error
            await asyncio.sleep(1 * (2 ** att))
    await debug_print("TX failed after retries", "WARN")

async def _wait_tx_done(timeout=30):  # Increased timeout
    global lora
    if lora is None:
        return False
    tx_start = time.time()
    while time.time() - tx_start < timeout:
        try:
            if lora is None:
                return False
            if lora._events() & lora.TX_DONE:
                return True
        except AttributeError as ae:
            if 'NoneType' in str(ae):
                lora = None
                await hard_reset_lora()
                await log_error("Force reinit LoRa due to NoneType in _events")
                return False
        await asyncio.sleep(0.01)
    await log_error("TX timeout")
    return False

async def _poll_and_relay_commands(pending_commands):
    if not poll_device_commands:
        return
    for remote_uid in list(getattr(settings, 'REMOTE_NODE_INFO', {}).keys()):
        remote_machine_id = settings.REMOTE_NODE_INFO.get(remote_uid, {}).get('MACHINE_ID', None)
        if remote_machine_id is None:
            await log_error(f"No MACHINE_ID for {remote_uid} during command poll")
            continue
        try:
            original = settings.UNIT_ID
            original_get = None
            try:
                import utils as _u
                if hasattr(_u, 'get_machine_id'):
                    original_get = _u.get_machine_id
                    def temp_get():
                        return str(remote_machine_id)
                    _u.get_machine_id = temp_get
                settings.UNIT_ID = remote_uid
                cmds = await poll_device_commands() if asyncio.iscoroutinefunction(poll_device_commands) else poll_device_commands()
            finally:
                settings.UNIT_ID = original
                if original_get and hasattr(_u, 'get_machine_id'):
                    _u.get_machine_id = original_get
            for cmd in cmds:
                pending_commands[remote_uid] = cmd
                await debug_print(f"Queued CMD for {remote_uid}: {cmd}", "BASE_NODE")
        except Exception:
            pass
    gc.collect()

def calculate_next_delay(node_id):
    sync_rate = getattr(settings, 'LORA_SYNC_RATE', 300)
    sync_window = getattr(settings, 'LORA_NEXT_SYNC', 600)
    stagger_seed = 0
    for c in node_id:
        stagger_seed = (stagger_seed * 31 + ord(c)) % sync_window
    jitter = random.randint(-30, 30)  # small jitter to avoid exact collisions
    delay = sync_rate + stagger_seed + jitter
    return max(60, delay)

# ===================== ORIGINAL FUNCTIONS (100% unchanged) =====================
async def periodic_wp_sync():
    if settings.NODE_TYPE != 'base':
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
    while True:
        await heartbeat_ping()
        await asyncio.sleep(60)

async def check_suspend_remove():
    if settings.NODE_TYPE != 'base':
        return
    from wprest import WORDPRESS_API_URL
    if not WORDPRESS_API_URL:
        return
    try:
        import settings
        import urequests as requests
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/settings/{settings.UNIT_ID}')
        if resp.status_code == 200:
            settings_data = resp.json().get('settings', {})
            if settings_data.get('suspended'):
                await debug_print('Device is suspended by admin', 'WARN')
                while True:
                    await asyncio.sleep(60)
    except Exception:
        pass

WORDPRESS_API_URL = getattr(settings, 'WORDPRESS_API_URL', None)
WORDPRESS_API_KEY = getattr(settings, 'WORDPRESS_API_KEY', None)

async def send_settings_to_wp():
    pass
async def fetch_settings_from_wp():
    pass
async def send_file_to_wp(filepath):
    pass
async def request_file_from_wp(filename):
    pass

async def check_missed_syncs():
    if settings.NODE_TYPE != 'base':
        return
    while True:
        now = time.time()
        for node_id, info in settings.REMOTE_NODE_INFO.items():
            if 'next_expected' in info and now > info['next_expected'] + getattr(settings, 'LORA_NEXT_SYNC', 100) * 2:
                info['missed_syncs'] = info.get('missed_syncs', 0) + 1
                await debug_print(f"Missed sync from {node_id}", "WARN")
                if info['missed_syncs'] > 3:
                    await debug_print(f"Excessive missed syncs from {node_id}", "WARN")
        save_remote_node_info()
        await asyncio.sleep(300)

async def handle_ota_job(job):
    if settings.NODE_TYPE != 'base':
        return
    if 'targets' in job and job['type'] == 'firmware':
        filename = job['file']
        await request_file_from_wp(filename)
        file_size = os.stat(filename)[6]
        total_chunks = (file_size // getattr(settings, 'LORA_CHUNK_SIZE', 200)) + 1
        file_checksum = simple_checksum(filename)
        targets = job['targets'] if job['targets'] != 'all' else settings.REMOTE_NODE_INFO.keys()
        for node_id in targets:
            if node_id in settings.REMOTE_NODE_INFO:
                settings.REMOTE_NODE_INFO[node_id]['ota'] = {
                    'file': filename,
                    'total_chunks': total_chunks,
                    'current_chunk': 0,
                    'file_checksum': file_checksum
                }
        save_remote_node_info()

def get_next_ota_chunk(node_id):
    if 'ota' not in settings.REMOTE_NODE_INFO.get(node_id, {}):
        return None
    ota = settings.REMOTE_NODE_INFO[node_id]['ota']
    chunk_size = getattr(settings, 'LORA_CHUNK_SIZE', 200)
    with open(ota['file'], 'rb') as f:
        f.seek(ota['current_chunk'] * chunk_size)
        data = f.read(chunk_size)
    if not data:
        return None
    chunk_checksum = sum(data) % 65536
    return {
        'file': ota['file'],
        'chunk_num': ota['current_chunk'],
        'data': _ub.b2a_base64(data).rstrip(b'\n').decode(),
        'chunk_checksum': chunk_checksum,
        'total_chunks': ota['total_chunks'],
        'file_checksum': ota['file_checksum']
    }

def advance_ota_chunk(node_id):
    if 'ota' in settings.REMOTE_NODE_INFO.get(node_id, {}):
        ota = settings.REMOTE_NODE_INFO[node_id]['ota']
        ota['current_chunk'] += 1
        if ota['current_chunk'] >= ota['total_chunks']:
            del settings.REMOTE_NODE_INFO[node_id]['ota']
        save_remote_node_info()

def handle_ota_chunk(ota_info):
    data = _ub.a2b_base64(ota_info['data'].encode())
    if sum(data) % 65536 != ota_info['chunk_checksum']:
        settings.last_chunk_ok = False
        return
    mode = 'wb' if ota_info['chunk_num'] == 0 else 'ab'
    ota_temp_file = getattr(settings, 'OTA_TEMP_FILE', '/ota_temp')
    with open(ota_temp_file, mode) as f:
        f.write(data)
    settings.ota_in_progress = True
    settings.last_chunk_ok = True
    if ota_info['chunk_num'] + 1 == ota_info['total_chunks']:
        if simple_checksum(ota_temp_file) == ota_info['file_checksum']:
            os.rename(ota_temp_file, ota_info['file'])
            machine.reset()
        else:
            os.remove(ota_temp_file)
            settings.ota_in_progress = False

async def safe_loop(coro, context):
    while True:
        try:
            await coro()
        except Exception as e:
            await log_error(f"{context} crashed: {str(e)}")
            await asyncio.sleep(10)

async def main_loop():
    asyncio.create_task(safe_loop(periodic_wp_sync, 'periodic_wp_sync'))
    asyncio.create_task(safe_loop(heartbeat_ping_loop, 'heartbeat_ping_loop'))
    asyncio.create_task(safe_loop(check_suspend_remove, 'check_suspend_remove'))
    asyncio.create_task(safe_loop(check_missed_syncs, 'missed_syncs'))
    while True:
        await asyncio.sleep(60)

async def ai_health_monitor():
    while True:
        if TMON_AI.error_count > 3:
            await TMON_AI.recover_system()
        await asyncio.sleep(60)