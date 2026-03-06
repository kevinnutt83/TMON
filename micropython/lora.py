# TMON Version 2.00.5i - LoRa (FULL BULLETPROOF GATEWAY + TRUE MULTI-REMOTE + ACK + SNR + CMD + OTA)

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

file_lock = asyncio.Lock()
pin_lock = asyncio.Lock()
lora = None
last_lora_error_ts = 0
proxy_last_ts = {}

async def log_error(error_msg):
    global last_lora_error_ts
    ts = time.time()
    if ts - last_lora_error_ts < 5:
        return
    last_lora_error_ts = ts
    log_line = f"{ts}: {error_msg}\n"
    try:
        async with file_lock:
            with open(settings.ERROR_LOG_FILE, 'a') as f:
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
        for pin_num in (settings.CLK_PIN, settings.MOSI_PIN, settings.MISO_PIN,
                        settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN,
                        settings.BUSY_PIN, settings.I2C_A_SCL_PIN, settings.I2C_A_SDA_PIN):
            p = machine.Pin(pin_num, machine.Pin.IN)
            p.value(0)
    except Exception:
        pass
    try:
        rst = machine.Pin(settings.RST_PIN, machine.Pin.OUT)
        rst.value(0)
        await asyncio.sleep_ms(50)
        rst.value(1)
        await asyncio.sleep_ms(150)
    except Exception:
        pass
    gc.collect()

async def init_lora():
    global lora
    await debug_print('init_lora: starting with -2 fix', 'LORA')
    await display_message("LoRa Init...", 1)
    for attempt in range(5):
        try:
            await hard_reset_lora()
            await free_pins()
            await asyncio.sleep(0.5)
            lora = SX1262(
                settings.SPI_BUS, settings.CLK_PIN, settings.MOSI_PIN, settings.MISO_PIN,
                settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN
            )
            status = lora.begin(
                freq=settings.FREQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
                syncWord=settings.SYNC_WORD, power=settings.POWER,
                currentLimit=settings.CURRENT_LIMIT, preambleLength=settings.PREAMBLE_LEN,
                implicit=False, implicitLen=0xFF, crcOn=settings.CRC_ON,
                txIq=False, rxIq=False,
                tcxoVoltage=settings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO,
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
    await debug_print("LoRa init FAILED after 5 attempts", "FATAL")
    await display_message("LoRa FAIL", 3)
    await free_pins()
    lora = None
    return False

command_handlers = {
    "toggle_relay": toggle_relay,
}

REMOTE_NODE_INFO_FILE = settings.LOG_DIR + '/remote_node_info.json'

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
    if not settings.ENABLE_LORA:
        return False
    await debug_print("Starting bulletproof LoRa Gateway v2.00.5i...", "LORA")
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
                if state == STATE_IDLE:
                    await debug_print("Remote: starting full check-in (TS + SETTINGS + SDATA)", "REMOTE_NODE")
                    await display_message("TX Data...", 0.8)
                    ts = time.time()

                    # TS packet
                    data_str = f"TS:{ts},UID:{settings.UNIT_ID},MACHINE_ID:{get_machine_id()},COMPANY:{getattr(settings,'COMPANY','')},SITE:{getattr(settings,'SITE','')},ZONE:{getattr(settings,'ZONE','')},CLUSTER:{getattr(settings,'CLUSTER','')},RUNTIME:{sdata.loop_runtime},SCRIPT_RUNTIME:{sdata.script_runtime},TEMP_C:{sdata.cur_temp_c},TEMP_F:{sdata.cur_temp_f},BAR:{sdata.cur_bar_pres},HUMID:{sdata.cur_humid}"
                    await _send_with_retry(data_str.encode())

                    # Small delay between packets to reduce collision risk
                    await asyncio.sleep(random.uniform(0.5, 1.5))

                    # SETTINGS packet
                    settings_dict = {k: getattr(settings, k) for k in dir(settings) if not k.startswith('__') and not callable(getattr(settings, k))}
                    settings_b64 = _ub.b64encode(ujson.dumps(settings_dict).encode()).decode()
                    await _send_with_retry(f"TYPE:SETTINGS,UID:{settings.UNIT_ID},DATA:{settings_b64}".encode())

                    await asyncio.sleep(random.uniform(0.5, 1.5))

                    # SDATA packet - SAFE VERSION (never crashes the TX)
                    try:
                        sdata_dict = {k: v for k, v in getattr(sdata, '__dict__', {}).items() if not k.startswith('__') and not callable(v)}
                        sdata_b64 = _ub.b64encode(ujson.dumps(sdata_dict).encode()).decode()
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
                        sdata_b64 = _ub.b64encode(ujson.dumps(sdata_dict).encode()).decode()

                    await _send_with_retry(f"TYPE:SDATA,UID:{settings.UNIT_ID},DATA:{sdata_b64}".encode())

                    # CRITICAL: Arm RX right after last TX so we catch the ACK/CMD/OTA
                    lora.recv(0, False, 0)
                    await asyncio.sleep_ms(200)  # Increased delay for mode switch

                    await debug_print("Remote: TX burst complete - armed RX, waiting for base response", "REMOTE_NODE")
                    await display_message("Waiting ACK", 1)

                    state = STATE_WAIT_RESPONSE
                    start_wait = time.time()
                    received_response = False
                    next_delay = None

                elif state == STATE_WAIT_RESPONSE:
                    ev = lora._events()
                    if ev & lora.RX_DONE:
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

                        lora.recv(0, False, 0)   # re-arm for more packets

                    # Timeout handling
                    if time.time() - start_wait > response_timeout:
                        if received_response:
                            await debug_print("Remote: check-in successful - scheduling next", "REMOTE_NODE")
                            await display_message("Success", 1)
                            failure_count = 0
                            if next_delay is not None:
                                sleep_time = next_delay
                            else:
                                jitter = random.randint(-120, 120)
                                sleep_time = sync_rate + jitter
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
                if state == STATE_IDLE:
                    state = STATE_RECEIVING

                if state == STATE_RECEIVING:
                    ev = lora._events()
                    if ev & lora.RX_DONE:
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
                                        json_data = _ub.b64decode(data_b64).decode()
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
                                    async with file_lock:
                                        with open(settings.LOG_FILE, 'a') as f:
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

                                original_uid = settings.UNIT_ID
                                settings.UNIT_ID = uid
                                send_ok = False
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
                                settings.UNIT_ID = original_uid
                                if send_ok:
                                    await debug_print(f"Proxied settings for {uid} to Unit Connector", "BASE_NODE")
                                    await display_message(f"Proxy {uid[:8]}", 1)
                                gc.collect()

                            if 'SDATA' in st['types']:
                                sdata_dict = st['data']['SDATA']
                                stage_remote_field_data(uid, [sdata_dict])

                                original_uid = settings.UNIT_ID
                                settings.UNIT_ID = uid
                                send_ok = False
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
                                settings.UNIT_ID = original_uid
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
                                await _send_with_retry(ack_msg.encode())
                                await debug_print(f"Sent ACK with next delay {next_delay}s to {uid}", "BASE_NODE")
                                await display_message("ACK Sent", 0.5)

                                if uid in pending_commands:
                                    cmd = pending_commands.pop(uid)
                                    cmd_msg = f"CMD:{uid}:{cmd}"
                                    await _send_with_retry(cmd_msg.encode())
                                    await debug_print(f"Sent CMD to {uid}: {cmd}", "BASE_NODE")
                                    await display_message("CMD Sent", 0.5)

                                ota_pending = ota_send_pending.pop(uid, False)
                                if ota_pending:
                                    chunk = get_next_ota_chunk(uid)
                                    if chunk:
                                        ota_str = f"OTA:{ujson.dumps(chunk)}"
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
            if settings.NODE_TYPE == 'remote':
                state = STATE_IDLE   # force retry on remote
            await asyncio.sleep(2)
            gc.collect()

async def _send_with_retry(data, retries=3):
    for att in range(retries):
        try:
            lora.send(data)
            await _wait_tx_done()
            lora.recv(0, False, 0)  # re-arm RX after TX
            return
        except Exception as e:
            await log_error(f"TX attempt {att+1} failed: {e}")
            await asyncio.sleep(1)
    await debug_print("TX failed after retries", "WARN")

async def _wait_tx_done(timeout=10):
    tx_start = time.time()
    while time.time() - tx_start < timeout:
        if lora._events() & lora.TX_DONE:
            return True
        await asyncio.sleep(0.01)
    await log_error("TX timeout")
    return False

async def _poll_and_relay_commands(pending_commands):
    if not poll_device_commands:
        return
    for remote_uid in list(getattr(settings, 'REMOTE_NODE_INFO', {}).keys()):
        try:
            original = settings.UNIT_ID
            settings.UNIT_ID = remote_uid
            cmds = await poll_device_commands() if asyncio.iscoroutinefunction(poll_device_commands) else poll_device_commands()
            settings.UNIT_ID = original
            for cmd in cmds:
                pending_commands[remote_uid] = cmd
                await debug_print(f"Queued CMD for {remote_uid}: {cmd}", "BASE_NODE")
        except Exception:
            pass
    gc.collect()

def calculate_next_delay(node_id):
    sync_window = getattr(settings, 'LORA_NEXT_SYNC', 600)  # Restored configurable with increased default
    sync_rate = getattr(settings, 'LORA_SYNC_RATE', 300)
    nodes = sorted(settings.REMOTE_NODE_INFO.keys())
    num_nodes = len(nodes)
    if num_nodes == 0:
        return sync_rate
    try:
        slot_index = nodes.index(node_id)
    except ValueError:
        slot_index = random.randint(0, num_nodes - 1)
    slot_size = sync_window // num_nodes if num_nodes > 0 else sync_window
    stagger = slot_index * slot_size
    jitter = random.randint(-slot_size // 2, slot_size // 2) if slot_size > 0 else 0
    stagger += jitter
    stagger = max(0, min(stagger, sync_window - 1))
    delay = sync_rate + stagger
    return delay

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
        total_chunks = (file_size // settings.LORA_CHUNK_SIZE) + 1
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
    chunk_num = ota['current_chunk']
    with open(ota['file'], 'rb') as f:
        f.seek(chunk_num * settings.LORA_CHUNK_SIZE)
        data = f.read(settings.LORA_CHUNK_SIZE)
    if not data:
        return None
    chunk_checksum = sum(data) % 65536
    return {
        'file': ota['file'],
        'chunk_num': chunk_num,
        'data': _ub.b64encode(data).decode(),
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
    data = _ub.b64decode(ota_info['data'])
    if sum(data) % 65536 != ota_info['chunk_checksum']:
        settings.last_chunk_ok = False
        return
    mode = 'wb' if ota_info['chunk_num'] == 0 else 'ab'
    with open(settings.OTA_TEMP_FILE, mode) as f:
        f.write(data)
    settings.ota_in_progress = True
    settings.last_chunk_ok = True
    if ota_info['chunk_num'] + 1 == ota_info['total_chunks']:
        if simple_checksum(settings.OTA_TEMP_FILE) == ota_info['file_checksum']:
            os.rename(settings.OTA_TEMP_FILE, ota_info['file'])
            machine.reset()
        else:
            os.remove(settings.OTA_TEMP_FILE)
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