# TMON Verion 2.00.1f - LoRa communication, WordPress integration, OTA updates, and remote node management

# Utility to print remote node info
async def print_remote_nodes():
    import sdata
    remote_info = getattr(sdata, 'REMOTE_NODE_INFO', {})
    if not remote_info:
        await debug_print("No remote nodes", "REMOTE_NODE")
        return
    for node_id, node_data in remote_info.items():
        await debug_print(f"[REMOTE NODE] {node_id}: {node_data}", "REMOTE_NODE")

import ujson
import os
import uasyncio as asyncio
import select
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
    import time
try:
    import urequests as requests
except ImportError:
    try:
        import requests
    except ImportError:
        requests = None
from utils import free_pins, checkLogDirectory, debug_print, TMON_AI, safe_run
from relay import toggle_relay
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
    _auth_headers = getattr(_wp, '_auth_headers', None)
except Exception:
    register_with_wp = send_data_to_wp = send_settings_to_wp = fetch_settings_from_wp = None
    send_file_to_wp = request_file_from_wp = heartbeat_ping = poll_ota_jobs = _auth_headers = None
import random
import ubinascii

async def user_input_listener():
    """Non-blocking input for user commands via UART/serial."""
    if not sys or not hasattr(sys, 'stdin'):
        return
    while True:
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            cmd = sys.stdin.readline().strip()
            if cmd:
                await handle_user_command(cmd)
        await asyncio.sleep(0.1)

async def handle_user_command(cmd):
    """Parse and execute user commands for system/AI."""
    from utils import debug_print
    if cmd.lower() == 'reset_ai':
        TMON_AI.error_count = 0
        await debug_print('AI error count reset by user', 'user_input')
    elif cmd.lower().startswith('call '):
        # Example: call <function_name>
        fn = cmd[5:].strip()
        if hasattr(TMON_AI, fn):
            await debug_print(f'Calling AI function: {fn}', 'user_input')
            getattr(TMON_AI, fn)()
        else:
            await debug_print(f'No such AI function: {fn}', 'user_input')
    else:
        await debug_print(f'Unknown command: {cmd}', 'user_input')

# File to persist remote node info
REMOTE_NODE_INFO_FILE = settings.LOG_DIR + '/remote_node_info.json'

# Load REMOTE_NODE_INFO from file at startup
def load_remote_node_info():
    try:
        with open(REMOTE_NODE_INFO_FILE, 'r') as f:
            settings.REMOTE_NODE_INFO = ujson.load(f)
    except Exception:
        settings.REMOTE_NODE_INFO = {}

load_remote_node_info()

# Save REMOTE_NODE_INFO to file
def save_remote_node_info():
    try:
        with open(REMOTE_NODE_INFO_FILE, 'w') as f:
            ujson.dump(settings.REMOTE_NODE_INFO, f)
    except Exception:
        pass

# Periodic sync with WordPress (settings, data, OTA jobs)
async def periodic_wp_sync():
    if settings.NODE_TYPE != 'base':
        return  # Only base station handles WordPress communication
    while True:
        await register_with_wp()
        await send_settings_to_wp()
        await fetch_settings_from_wp()
        await send_data_to_wp()
        jobs = await poll_ota_jobs()
        for job in jobs:
            await handle_ota_job(job)
        await asyncio.sleep(300)  # Sync every 5 minutes

# Heartbeat loop
async def heartbeat_ping_loop():
    if settings.NODE_TYPE != 'base':
        return  # Only base station sends heartbeats to WordPress
    while True:
        await heartbeat_ping()
        await asyncio.sleep(60)

# Check for suspend/remove/remote access state (unchanged)
async def check_suspend_remove():
    if settings.NODE_TYPE != 'base':
        return  # Only base station checks suspend status from WordPress
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
                from utils import debug_print
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

async def send_file_to_wp(filepath):
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
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
        await debug_print('No WordPress API URL set', 'ERROR')
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

file_lock = asyncio.Lock()
pin_lock = asyncio.Lock()
lora = None

# Asynchronous function to log errors
async def log_error(error_msg):
    ts = time.time()
    log_line = f"{ts}: {error_msg}\n"
    try:
        async with file_lock:
            with open(settings.ERROR_LOG_FILE, 'a') as f:
                f.write(log_line)
    except Exception as e:
        await debug_print(f"[FATAL] Failed to log error: {e}", "ERROR")
    await asyncio.sleep(0)

command_handlers = {
    "toggle_relay": toggle_relay,
    # Add more handlers as needed, e.g., "other_func": other_func,
}

async def init_lora():
    global lora
    await debug_print('init_lora: starting SX1262 init', 'LORA')
    try:
        await debug_print('init_lora: BEFORE SX1262 instantiation', 'LORA')
        lora = SX1262(
            settings.SPI_BUS, settings.CLK_PIN, settings.MOSI_PIN, settings.MISO_PIN,
            settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN
        )
        await debug_print('init_lora: SX1262 object created', 'LORA')
        status = lora.begin(
            freq=settings.FREQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
            syncWord=settings.SYNC_WORD, power=settings.POWER,
            currentLimit=settings.CURRENT_LIMIT, preambleLength=settings.PREAMBLE_LEN,
            implicit=False, implicitLen=0xFF, crcOn=settings.CRC_ON, txIq=False, rxIq=False,
            tcxoVoltage=settings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO
        )
        await debug_print(f'init_lora: lora.begin() returned {status}', 'LORA')
        if status != 0:
            error_msg = f"LoRa initialization failed with status: {status}"
            await debug_print(error_msg, "ERROR")
            await log_error(error_msg)
            await free_pins()
            lora = None
            return False
        await debug_print("LoRa initialized successfully", "LORA")
        await print_remote_nodes()
        await debug_print('init_lora: completed successfully', 'LORA')
        return True
    except Exception as e:
        error_msg = f"Exception in init_lora: {e}"
        await debug_print(error_msg, "ERROR")
        await log_error(error_msg)
        await free_pins()
        lora = None
        return False

async def connectLora():
    global lora
    lora_init_failures = 0
    MAX_LORA_INIT_FAILS = 3
    if settings.ENABLE_LORA:
        await debug_print("Attempting LoRa initialization...", "LORA")
        async with pin_lock:
            await debug_print('connectLora: calling init_lora', 'LORA')
            while lora_init_failures < MAX_LORA_INIT_FAILS:
                if await init_lora():
                    await debug_print('connectLora: init_lora succeeded', 'LORA')
                    break
                else:
                    lora_init_failures += 1
                    await debug_print(f'connectLora: init_lora failed ({lora_init_failures}/{MAX_LORA_INIT_FAILS})', 'LORA')
                    await asyncio.sleep(10)
            if lora_init_failures >= MAX_LORA_INIT_FAILS:
                await debug_print('LoRa initialization failed too many times. Halting.', 'FATAL')
                return False

        STATE_IDLE = 0
        STATE_SENDING = 1
        STATE_WAIT_RESPONSE = 2
        STATE_RECEIVING = 3

        state = STATE_IDLE
        send_interval = settings.nextLoraSync
        response_timeout = 10
        last_activity = time.time()
        idle_timeout = 60
        connected = False

        # For base: Track connected remote nodes {uid: last_ts}
        connected_remotes = {}

        # For base: Pending commands {uid: "func(arg1,arg2,arg3)"}
        # Populate this dict externally or based on criteria
        pending_commands = {}

        while True:
            try:
                current_time = time.time()
                if state == STATE_IDLE and (current_time - last_activity) > idle_timeout:
                    await debug_print("Idle timeout reached, freeing pins", "LORA")
                    async with pin_lock:
                        if lora is not None:
                            try:
                                lora.reset()
                            except Exception:
                                pass
                            lora = None
                    await free_pins()
                    await asyncio.sleep(60)
                    last_activity = current_time

                if lora is None:
                    if not await init_lora():
                        await asyncio.sleep(10)
                        continue

                if settings.NODE_TYPE == 'remote':
                    if state == STATE_IDLE:
                        await debug_print("Remote: Idle state - attempting to send/connect", "REMOTE_NODE")
                        await sampleEnviroment()
                        payload_dict = sdata.__dict__.copy()
                        payload_dict['node_id'] = settings.UNIT_ID
                        payload_dict['timestamp'] = time.time()
                        payload_dict['firmware_version'] = settings.FIRMWARE_VERSION
                        if hasattr(settings, 'ota_in_progress') and settings.ota_in_progress:
                            payload_dict['ota_ack'] = settings.last_chunk_ok
                        payload = ujson.dumps(payload_dict)
                        lora.send(payload)
                        lora.startReceive()
                        state = STATE_WAIT_RESPONSE
                        start_wait = time.time()
                        last_activity = time.time()
                        await debug_print("Remote: Sent data, waiting response", "REMOTE_NODE")

                    elif state == STATE_WAIT_RESPONSE:
                        if lora.irq():
                            received = lora.recv()
                            if received:
                                try:
                                    response = ujson.loads(received)
                                    if 'ack' in response:
                                        await debug_print("Received ACK", "REMOTE_NODE")
                                        connected = True
                                        for cmd in response.get('commands', []):
                                            if isinstance(cmd, str) and '(' in cmd and cmd.endswith(')'):
                                                func_name, args_str = cmd.split('(', 1)
                                                args_str = args_str.rstrip(')')
                                                args = [arg.strip() for arg in args_str.split(',')] if args_str else []
                                                if func_name in command_handlers:
                                                    command_handlers[func_name](*args)
                                                    await debug_print(f"Executed command: {cmd}", "REMOTE_NODE")
                                                else:
                                                    await debug_print(f"Unknown command: {func_name}", "ERROR")
                                        if 'next_sync' in response:
                                            settings.nextLoraSync = response['next_sync']
                                        if 'file_update' in response:
                                            handle_ota_chunk(response['file_update'])
                                    state = STATE_IDLE
                                    last_activity = time.time()
                                    await debug_print("Remote: Processed response, closing connection", "REMOTE_NODE")
                                    connected = False
                                except Exception as e:
                                    await debug_print(f"Response parse error: {e}", "ERROR")
                        if time.time() - start_wait > response_timeout:
                            await debug_print("Response timeout", "WARN")
                            state = STATE_IDLE
                            settings.nextLoraSync = time.time() + (settings.LORA_CHECK_IN_MINUTES * 60)
                            connected = False
                    await asyncio.sleep(0.1)

                elif settings.NODE_TYPE == 'base':
                    if state == STATE_IDLE:
                        lora.startReceive()
                        state = STATE_RECEIVING
                        await debug_print("Base: Listening for remote nodes", "BASE_NODE")

                    if state == STATE_RECEIVING:
                        if lora.irq():
                            received = lora.recv()
                            if received:
                                try:
                                    data = ujson.loads(received)
                                    node_id = data['node_id']
                                    connected_remotes[node_id] = time.time()
                                    connected = True
                                    settings.REMOTE_NODE_INFO[node_id] = {
                                        'last_seen': time.time(),
                                        'data': data,
                                        'firmware_version': data['firmware_version'],
                                        'last_ack_ts': time.time()
                                    }
                                    save_remote_node_info()
                                    with open(settings.FIELD_DATA_LOG, 'a') as f:
                                        f.write(ujson.dumps(data) + '\n')
                                    response = {
                                        'ack': True,
                                        'commands': []  # From pending_commands
                                    }
                                    if node_id in pending_commands:
                                        response['commands'] = [pending_commands.pop(node_id)]
                                    response['next_sync'] = calculate_next_sync(node_id)
                                    if 'ota' in settings.REMOTE_NODE_INFO.get(node_id, {}):
                                        ota_info = get_next_ota_chunk(node_id)
                                        if ota_info:
                                            response['file_update'] = ota_info
                                    if 'ota_ack' in data:
                                        if data['ota_ack']:
                                            advance_ota_chunk(node_id)
                                    response_payload = ujson.dumps(response)
                                    lora.send(response_payload)
                                    await debug_print("Base: Sent response, closing connection", "BASE_NODE")
                                    connected = False
                                    lora.startReceive()
                                    state = STATE_IDLE
                                except Exception as e:
                                    await debug_print(f"Receive parse error: {e}", "ERROR")
                        await asyncio.sleep(0.1)
            except Exception as e:
                await debug_print(f"LoRa loop error: {e}", "ERROR")
                await asyncio.sleep(1)

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
    now = time.time()
    for node_id, info in settings.REMOTE_NODE_INFO.items():
        if 'next_expected' in info and now > info['next_expected'] + settings.LORA_SYNC_WINDOW * 2:
            info['missed_syncs'] = info.get('missed_syncs', 0) + 1
            await debug_print(f"Missed sync from {node_id}", "WARN")
            if info['missed_syncs'] > 3:
                pass  # Alert or remove
    save_remote_node_info()

# OTA functions
async def handle_ota_job(job):
    if 'targets' in job and job['type'] == 'firmware' and settings.NODE_TYPE == 'base':
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

def simple_checksum(path):
    checksum = 0
    with open(path, 'rb') as f:
        while chunk := f.read(128):
            for b in chunk:
                checksum = (checksum + b) % 65536
    return checksum

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
        'data': ubinascii.b64encode(data).decode(),
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
    data = ubinascii.b64decode(ota_info['data'])
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
