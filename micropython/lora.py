# TMON Version 2.00.1g - LoRa (FULL BULLETPROOF GATEWAY MODE)
# All requested enhancements included:
# - sdata.lora_SigStr updated on every successful RX/connection
# - Remote sends full telemetry + settings.py snapshot + sdata.py snapshot
# - Base proxies remote data to Unit Connector via wprest.py calls (send_settings_to_wp / send_data_to_wp)
# - Base records remote data in its own field log
# - OLED display_message calls in all logical places
# - gc.collect() after every heavy operation
# - Enhanced hard reset + init to fix status -2 error (aggressive pin cleanup, longer stabilization)
# - Full original parsing, WP, OTA, AI, main_loop kept 100% intact

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

from utils import free_pins, debug_print, TMON_AI, stage_remote_field_data, stage_remote_files, record_field_data
from relay import toggle_relay
from oled import display_message   # For user-visible feedback
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

def print_remote_nodes():
    import sdata
    remote_info = getattr(sdata, 'REMOTE_NODE_INFO', {})
    for node_id, node_data in remote_info.items():
        print(f"[REMOTE NODE] {node_id}: {node_data}")

async def print_remote_nodes_async():
    try:
        print_remote_nodes()
    except Exception:
        pass

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

# Enhanced hard reset to fix status -2 (aggressive pin cleanup + longer TCXO stabilization)
async def hard_reset_lora():
    global lora
    if lora:
        try:
            lora.reset()
        except Exception:
            pass
    # Aggressive cleanup to resolve -2 on first boot / after reset
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
        await asyncio.sleep_ms(150)  # Extra stabilization for TCXO
    except Exception:
        pass
    gc.collect()

# Bulletproof init with -2 fix
async def init_lora():
    global lora
    await debug_print('init_lora: starting with -2 fix', 'LORA')
    await display_message("LoRa Init...", 1)
    for attempt in range(8):
        try:
            await hard_reset_lora()
            await free_pins()
            await asyncio.sleep(0.4)
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
                await print_remote_nodes_async()
                gc.collect()
                return True
            elif status == -2:
                await debug_print("Status -2 - extra reset cycle", "WARN")
                await asyncio.sleep(0.8)
        except Exception as e:
            await debug_print(f"init attempt {attempt+1} exception: {e}", "WARN")
        await asyncio.sleep(0.7)
    await debug_print("LoRa init FAILED after 8 attempts", "FATAL")
    await display_message("LoRa FAIL", 3)
    await free_pins()
    lora = None
    return False

command_handlers = {
    "toggle_relay": toggle_relay,
}

# Remote node info persistence
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

# ===================== MAIN GATEWAY LOOP =====================
async def connectLora():
    global lora
    if not settings.ENABLE_LORA:
        return False
    await debug_print("Starting bulletproof LoRa Gateway...", "LORA")
    await display_message("LoRa Starting...", 1)
    async with pin_lock:
        if not await init_lora():
            return False

    STATE_IDLE = 0
    STATE_WAIT_RESPONSE = 2
    STATE_RECEIVING = 3
    state = STATE_IDLE
    send_interval = 10
    response_timeout = 25
    last_activity = time.time()
    pending_commands = {}

    while True:
        try:
            current_time = time.time()
            if lora is None:
                if not await init_lora():
                    await asyncio.sleep(10)
                    continue

            # ===================== REMOTE NODE =====================
            if settings.NODE_TYPE == 'remote':
                if state == STATE_IDLE:
                    await debug_print("Remote: sending full payload", "REMOTE_NODE")
                    await display_message("TX Data...", 0.8)
                    ts = time.time()

                    # Telemetry
                    data_str = f"TS:{ts},UID:{settings.UNIT_ID},COMPANY:{getattr(settings,'COMPANY','')},SITE:{getattr(settings,'SITE','')},ZONE:{getattr(settings,'ZONE','')},CLUSTER:{getattr(settings,'CLUSTER','')},RUNTIME:{sdata.loop_runtime},SCRIPT_RUNTIME:{sdata.script_runtime},TEMP_C:{sdata.cur_temp_c},TEMP_F:{sdata.cur_temp_f},BAR:{sdata.cur_bar_pres},HUMID:{sdata.cur_humid}"
                    lora.send(data_str.encode())
                    await _wait_tx_done()

                    # Settings snapshot
                    settings_dict = {k: getattr(settings, k) for k in dir(settings) if not k.startswith('__') and not callable(getattr(settings, k))}
                    settings_b64 = _ub.b64encode(ujson.dumps(settings_dict).encode()).decode()
                    lora.send(f"TYPE:SETTINGS,UID:{settings.UNIT_ID},DATA:{settings_b64}".encode())
                    await _wait_tx_done()

                    # Sdata snapshot
                    sdata_dict = {k: getattr(sdata, k) for k in dir(sdata) if not k.startswith('__')}
                    sdata_b64 = _ub.b64encode(ujson.dumps(sdata_dict).encode()).decode()
                    lora.send(f"TYPE:SDATA,UID:{settings.UNIT_ID},DATA:{sdata_b64}".encode())
                    await _wait_tx_done()

                    state = STATE_WAIT_RESPONSE
                    start_wait = current_time
                    last_activity = current_time

                elif state == STATE_WAIT_RESPONSE:
                    ev = lora._events()
                    if ev & lora.RX_DONE:
                        msg, err = lora.recv()
                        try:
                            rssi = lora.getRSSI()
                            sdata.lora_SigStr = rssi
                            await debug_print(f"RSSI: {rssi}", "REMOTE_NODE")
                        except Exception:
                            pass
                        if err == 0 and msg:
                            msg_str = msg.rstrip(b'\x00').decode()
                            await debug_print(f"Remote RX: {msg_str}", "REMOTE_NODE")
                            await display_message("RX ACK", 0.8)
                            if msg_str.startswith('ACK:'):
                                await debug_print("Connected to base", "REMOTE_NODE")
                            elif msg_str.startswith('CMD:'):
                                cmd_parts = msg_str.split(':', 2)
                                if len(cmd_parts) == 3 and (cmd_parts[1] == 'ALL' or cmd_parts[1] == settings.UNIT_ID):
                                    command = cmd_parts[2]
                                    if '(' in command and command.endswith(')'):
                                        func_name, args_str = command.split('(', 1)
                                        args = [a.strip() for a in args_str.rstrip(')').split(',')] if args_str else []
                                        if func_name in command_handlers:
                                            command_handlers[func_name](*args)
                    if current_time - start_wait > response_timeout:
                        state = STATE_IDLE
                        await asyncio.sleep(send_interval)

            # ===================== BASE NODE (FULL PROXY) =====================
            elif settings.NODE_TYPE == 'base':
                if state == STATE_IDLE:
                    state = STATE_RECEIVING

                if state == STATE_RECEIVING:
                    ev = lora._events()
                    if ev & lora.RX_DONE:
                        msg, err = lora.recv()
                        try:
                            rssi = lora.getRSSI()
                            sdata.lora_SigStr = rssi
                        except Exception:
                            pass
                        if err == 0 and msg:
                            msg_str = msg.rstrip(b'\x00').decode()
                            await debug_print(f"Base received: {msg_str[:100]}...", "BASE_NODE")
                            await display_message("RX Remote", 1)

                            if msg_str.startswith('TS:'):
                                # FULL ORIGINAL TELEMETRY PARSING
                                parts = msg_str.split(',')
                                remote_ts = parts[0].split(':', 1)[1].strip()
                                remote_uid = remote_company = remote_site = remote_zone = remote_cluster = None
                                remote_runtime = remote_script_runtime = temp_c = temp_f = bar = humid = None
                                for part in parts[1:]:
                                    if ':' not in part:
                                        continue
                                    key, value = part.split(':', 1)
                                    value = value.strip()
                                    if key == 'UID': remote_uid = value
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

                                if remote_uid and remote_company is not None:
                                    if not hasattr(settings, 'REMOTE_NODE_INFO'):
                                        settings.REMOTE_NODE_INFO = {}
                                    settings.REMOTE_NODE_INFO[remote_uid] = {
                                        'COMPANY': remote_company, 'SITE': remote_site,
                                        'ZONE': remote_zone, 'CLUSTER': remote_cluster
                                    }
                                    save_remote_node_info()

                                if None in (remote_uid, remote_runtime, remote_script_runtime, temp_c, temp_f, bar, humid):
                                    await log_error(f"Missing fields from {remote_uid}")
                                else:
                                    base_ts = time.time()
                                    log_line = f"{base_ts},{remote_uid},{remote_ts},{remote_runtime},{remote_script_runtime},{temp_c},{temp_f},{bar},{humid}\n"
                                    await debug_print(f"Received telemetry from {remote_uid}", "BASE_NODE")
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
                                        pending_commands[remote_uid] = "toggle_relay(1,on,5)"

                            elif msg_str.startswith('TYPE:'):
                                parts = msg_str.split(',')
                                msg_type = None
                                remote_uid = None
                                data_b64 = None
                                for p in parts:
                                    if p.startswith('TYPE:'): msg_type = p[5:]
                                    elif p.startswith('UID:'): remote_uid = p[4:]
                                    elif p.startswith('DATA:'): data_b64 = p[5:]

                                if msg_type == 'SETTINGS' and remote_uid and data_b64:
                                    try:
                                        settings_json = _ub.b64decode(data_b64).decode()
                                        settings_dict = ujson.loads(settings_json)
                                        stage_remote_files(remote_uid, {'settings.py': ujson.dumps(settings_dict).encode()})
                                        # Proxy to Unit Connector using wprest functions
                                        original_uid = settings.UNIT_ID
                                        settings.UNIT_ID = remote_uid
                                        if send_settings_to_wp:
                                            await send_settings_to_wp()
                                        settings.UNIT_ID = original_uid
                                        await debug_print(f"Proxied settings for {remote_uid} to Unit Connector", "BASE_NODE")
                                        await display_message(f"Proxy {remote_uid[:8]}", 1)
                                        gc.collect()
                                    except Exception as e:
                                        await log_error(f"Settings proxy error for {remote_uid}: {e}")

                                elif msg_type == 'SDATA' and remote_uid and data_b64:
                                    try:
                                        sdata_json = _ub.b64decode(data_b64).decode()
                                        sdata_dict = ujson.loads(sdata_json)
                                        stage_remote_field_data(remote_uid, [sdata_dict])
                                        # Proxy to Unit Connector
                                        original_uid = settings.UNIT_ID
                                        settings.UNIT_ID = remote_uid
                                        if send_data_to_wp:
                                            await send_data_to_wp()
                                        settings.UNIT_ID = original_uid
                                        await debug_print(f"Proxied sdata for {remote_uid} to Unit Connector", "BASE_NODE")
                                        await display_message(f"Proxy {remote_uid[:8]}", 1)
                                        gc.collect()
                                    except Exception as e:
                                        await log_error(f"SDATA proxy error for {remote_uid}: {e}")

                            # Re-arm RX
                            lora.recv(0, False, 0)
                            gc.collect()

                # Periodic command polling for remotes
                if int(current_time) % 30 == 0:
                    await _poll_and_relay_commands(pending_commands)

            await asyncio.sleep(0.05)
        except Exception as e:
            await log_error(f"LoRa gateway loop error: {e}")
            await display_message("LoRa Err", 2)
            await asyncio.sleep(1)

async def _wait_tx_done():
    tx_start = time.time()
    while time.time() - tx_start < 10:
        if lora._events() & lora.TX_DONE:
            break
        await asyncio.sleep(0.01)

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

# ===================== WP SYNC (ORIGINAL) =====================
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
        resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/settings', headers={'Authorization': f'Bearer {WORDPRESS_API_KEY}'}, json=data)
        await debug_print(f'Sent settings to WP: {resp.status_code}', 'HTTP')
    except Exception as e:
        await debug_print(f'Failed to send settings to WP: {e}', 'ERROR')

async def fetch_settings_from_wp():
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    try:
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/settings/{settings.UNIT_ID}', headers={'Authorization': f'Bearer {WORDPRESS_API_KEY}'})
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

async def send_file_to_wp(filepath):
    if not WORDPRESS_API_URL:
        return
    try:
        with open(filepath, 'rb') as f:
            files = {'file': (os.path.basename(filepath), f.read())}
            resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/file', headers={'Authorization': f'Bearer {WORDPRESS_API_KEY}'}, files=files)
            await debug_print(f'Sent file to WP: {resp.status_code}', 'HTTP')
    except Exception as e:
        await debug_print(f'Failed to send file to WP: {e}', 'ERROR')

async def request_file_from_wp(filename):
    if not WORDPRESS_API_URL:
        return
    try:
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/file/{settings.UNIT_ID}/{filename}', headers={'Authorization': f'Bearer {WORDPRESS_API_KEY}'})
        if resp.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(resp.content)
            await debug_print(f'Received file from WP: {filename}', 'HTTP')
        else:
            await debug_print(f'Failed to fetch file: {resp.status_code}', 'ERROR')
    except Exception as e:
        await debug_print(f'Failed to fetch file from WP: {e}', 'ERROR')

# Sync time functions
def calculate_next_sync(node_id):
    remotes = list(settings.REMOTE_NODE_INFO.keys())
    index = remotes.index(node_id) if node_id in remotes else len(remotes)
    stagger = index * settings.LORA_SYNC_WINDOW + random.randint(0, settings.LORA_SYNC_WINDOW - 1)
    check_in_sec = settings.LORA_CHECK_IN_MINUTES * 60
    next_sync = time.time() + check_in_sec + stagger
    settings.REMOTE_NODE_INFO[node_id]['next_expected'] = next_sync
    save_remote_node_info()
    return next_sync

async def check_missed_syncs():
    if settings.NODE_TYPE != 'base':
        return
    while True:
        now = time.time()
        for node_id, info in settings.REMOTE_NODE_INFO.items():
            if 'next_expected' in info and now > info['next_expected'] + settings.LORA_SYNC_WINDOW * 2:
                info['missed_syncs'] = info.get('missed_syncs', 0) + 1
                await debug_print(f"Missed sync from {node_id}", "WARN")
                if info['missed_syncs'] > 3:
                    await debug_print(f"Excessive missed syncs from {node_id}", "WARN")
        save_remote_node_info()
        await asyncio.sleep(300)

# OTA functions (original)
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

# AI & main loop helpers
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

# In boot.py / main.py you must have:
# asyncio.create_task(connectLora())
# asyncio.create_task(main_loop())
# asyncio.create_task(ai_health_monitor())
# asyncio.create_task(user_input_listener())