# Utility to print remote node info
def print_remote_nodes():
    import sdata
    remote_info = getattr(sdata, 'REMOTE_NODE_INFO', {})
    for node_id, node_data in remote_info.items():
        print(f"[REMOTE NODE] {node_id}: {node_data}")

# --- All imports at the top ---
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
    handle_ota_job = getattr(_wp, 'handle_ota_job', None)
    _auth_headers = getattr(_wp, '_auth_headers', None)
except Exception:
    register_with_wp = send_data_to_wp = send_settings_to_wp = fetch_settings_from_wp = None
    send_file_to_wp = request_file_from_wp = heartbeat_ping = poll_ota_jobs = handle_ota_job = _auth_headers = None


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
import settings
REMOTE_NODE_INFO_FILE = settings.LOG_DIR + '/remote_node_info.json'

# Load REMOTE_NODE_INFO from file at startup
def load_remote_node_info():
    try:
        with open(REMOTE_NODE_INFO_FILE, 'r') as f:
            settings.REMOTE_NODE_INFO = ujson.load(f)
    except Exception:
        settings.REMOTE_NODE_INFO = {}

# Ensure remote node info is loaded at startup (after settings import)
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
        await poll_ota_jobs()
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

# Start periodic sync in main event loop (add to your main.py or boot.py)
# asyncio.create_task(periodic_wp_sync())
# asyncio.create_task(check_suspend_remove())



# --- All imports at the very top ---
try:
    from sx1262 import SX1262
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
        print(f"[FATAL] Failed to log error: {e}")
    await asyncio.sleep(0)

command_handlers = {
    "toggle_relay": toggle_relay,
    # Add more handlers as needed, e.g., "other_func": other_func,
}

async def init_lora():
    global lora
    print('[DEBUG] init_lora: starting SX1262 init')
    try:
        print('[DEBUG] init_lora: BEFORE SX1262 instantiation')
        lora = SX1262(
            settings.SPI_BUS, settings.CLK_PIN, settings.MOSI_PIN, settings.MISO_PIN,
            settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN
        )
        print('[DEBUG] init_lora: SX1262 object created')
        status = lora.begin(
            freq=settings.FREQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
            syncWord=settings.SYNC_WORD, power=settings.POWER,
            currentLimit=settings.CURRENT_LIMIT, preambleLength=settings.PREAMBLE_LEN,
            implicit=False, implicitLen=0xFF, crcOn=settings.CRC_ON, txIq=False, rxIq=False,
            tcxoVoltage=settings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO
        )
        print(f'[DEBUG] init_lora: lora.begin() returned {status}')
        if status != 0:
            error_msg = f"LoRa initialization failed with status: {status}"
            await debug_print(error_msg, "ERROR")
            await log_error(error_msg)
            await free_pins()
            lora = None
            return False
        await debug_print("LoRa initialized successfully", "LORA")
        print_remote_nodes()
        print('[DEBUG] init_lora: completed successfully')
        return True
    except Exception as e:
        error_msg = f"Exception in init_lora: {e}"
        print(error_msg)
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
        send_interval = 10
        timeout_ms = 15000
        last_activity = time.ticks_ms()
        idle_timeout = 60000
        connected = False

        # For base: Track connected remote nodes {uid: last_ts}
        connected_remotes = {}

        # For base: Pending commands {uid: "func(arg1,arg2,arg3)"}
        # Populate this dict externally or based on criteria
        pending_commands = {}

        while True:
            current_time = time.ticks_ms()
            if state == STATE_IDLE and time.ticks_diff(current_time, last_activity) > idle_timeout:
                await debug_print("Idle timeout reached, freeing pins", "LORA")
                async with pin_lock:
                    global lora
                    if lora is not None:
                        lora.spi.deinit()
                        lora = None
                await free_pins()
                await asyncio.sleep(60)
                last_activity = time.ticks_ms()

            if settings.NODE_TYPE == 'remote':
                if state == STATE_IDLE:
                    await debug_print("Remote: Idle state - attempting to send/connect", "LORA")
                    ts = time.time()
                    # Split string construction to reduce stack usage
                    data_str = "TS:{}".format(ts)
                    data_str += ",UID:{}".format(settings.UNIT_ID)
                    data_str += ",COMPANY:{}".format(getattr(settings, 'COMPANY', ''))
                    data_str += ",SITE:{}".format(getattr(settings, 'SITE', ''))
                    data_str += ",ZONE:{}".format(getattr(settings, 'ZONE', ''))
                    data_str += ",CLUSTER:{}".format(getattr(settings, 'CLUSTER', ''))
                    data_str += ",RUNTIME:{}".format(sdata.loop_runtime)
                    data_str += ",SCRIPT_RUNTIME:{}".format(sdata.script_runtime)
                    data_str += ",TEMP_C:{}".format(sdata.cur_temp_c)
                    data_str += ",TEMP_F:{}".format(sdata.cur_temp_f)
                    data_str += ",BAR:{}".format(sdata.cur_bar_pres)
                    data_str += ",HUMID:{}".format(sdata.cur_humid)
                    data = data_str.encode()
                    await debug_print(f"Sending data: {data_str}", "LORA")
                    async with pin_lock:
                        global lora
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
                        global lora
                        if lora is None:
                            if not await init_lora():
                                continue
                        msg, err = lora.recv(len=0, timeout_en=True, timeout_ms=timeout_ms)
                        # Get RSSI after receive
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
                            await debug_print(f"Raw response: {msg_str}", "DEBUG")
                            if msg_str.startswith('ACK:'):
                                ack_ts = msg_str[4:]
                                await debug_print(f"Received ACK with base TS: {ack_ts}", "LORA")
                                if not connected:
                                    await debug_print("Connected to base station", "LORA")
                                    connected = True
                            elif msg_str.startswith('CMD:'):
                                # Parse CMD:target:function(arg1,arg2,arg3)
                                cmd_parts = msg_str.split(':', 2)
                                if len(cmd_parts) == 3:
                                    target = cmd_parts[1]
                                    command = cmd_parts[2]
                                    if target == 'ALL' or target == settings.UNIT_ID:
                                        # Parse function and args
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
                    global lora
                    if lora is None:
                        if not await init_lora():
                            await asyncio.sleep(1)
                            continue
                    msg, err = lora.recv(len=0, timeout_en=False)
                    # Get RSSI after receive
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
                            if msg_str.startswith('TS:'):
                                parts = msg_str.split(',')
                                remote_ts = parts[0].split(':', 1)[1].strip()
                                remote_uid = remote_runtime = remote_script_runtime = temp_c = temp_f = bar = humid = None
                                remote_company = remote_site = remote_zone = remote_cluster = None
                                for part in parts[1:]:
                                    if ':' not in part:
                                        await debug_print(f"Invalid part in message: {part}", "ERROR")
                                        continue
                                    key, value = part.split(':', 1)
                                    value = value.strip()
                                    if key == 'UID':
                                        remote_uid = value
                                    elif key == 'COMPANY':
                                        remote_company = value
                                    elif key == 'SITE':
                                        remote_site = value
                                    elif key == 'ZONE':
                                        remote_zone = value
                                    elif key == 'CLUSTER':
                                        remote_cluster = value
                                    elif key == 'RUNTIME':
                                        remote_runtime = value
                                    elif key == 'SCRIPT_RUNTIME':
                                        remote_script_runtime = value
                                    elif key == 'TEMP_C':
                                        temp_c = value
                                    elif key == 'TEMP_F':
                                        temp_f = value
                                    elif key == 'BAR':
                                        bar = value
                                    elif key == 'HUMID':
                                        humid = value
                                # Store company/site/zone/cluster for remote node
                                if remote_uid and remote_company is not None:
                                    if not hasattr(settings, 'REMOTE_NODE_INFO'):
                                        settings.REMOTE_NODE_INFO = {}
                                    settings.REMOTE_NODE_INFO[remote_uid] = {
                                        'COMPANY': remote_company,
                                        'SITE': remote_site,
                                        'ZONE': remote_zone,
                                        'CLUSTER': remote_cluster
                                    }
                                    save_remote_node_info()
                                # Check for missing fields
                                if any(v is None for v in [remote_uid, remote_runtime, remote_script_runtime, temp_c, temp_f, bar, humid]):
                                    error_msg = f"Missing fields in message: UID={remote_uid}, RUNTIME={remote_runtime}, SCRIPT_RUNTIME={remote_script_runtime}, TEMP_C={temp_c}, TEMP_F={temp_f}, BAR={bar}, HUMID={humid}"
                                    await debug_print(error_msg, "ERROR")
                                    await log_error(error_msg)
                                else:
                                    base_ts = time.time()
                                    log_line = f"{base_ts},{remote_uid},{remote_ts},{remote_runtime},{remote_script_runtime},{temp_c},{temp_f},{bar},{humid}\n"
                                    # Individual conversions with fallback
                                    try:
                                        temp_f_val = float(temp_f)
                                    except ValueError as ve:
                                        error_msg = f"Invalid number syntax for TEMP_F: {repr(temp_f)} | {ve}"
                                        await debug_print(error_msg, "ERROR")
                                        await log_error(error_msg)
                                        temp_f_val = 0.0
                                    try:
                                        bar_val = float(bar)
                                    except ValueError as ve:
                                        error_msg = f"Invalid number syntax for BAR: {repr(bar)} | {ve}"
                                        await debug_print(error_msg, "ERROR")
                                        await log_error(error_msg)
                                        bar_val = 0.0
                                    try:
                                        humid_val = float(humid)
                                    except ValueError as ve:
                                        error_msg = f"Invalid number syntax for HUMID: {repr(humid)} | {ve}"
                                        await debug_print(error_msg, "ERROR")
                                        await log_error(error_msg)
                                        humid_val = 0.0
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
                                    # Record all sdata/settings to field_data.log
                                    from utils import record_field_data
                                    record_field_data()
                                    # Update connected remotes
                                    connected_remotes[remote_uid] = base_ts
                                    # Check criteria and queue command (example)
                                    if temp_f_val < 80:  # Replace with actual criteria
                                        pending_commands[remote_uid] = "toggle_relay(1,on,5)"
                                    # Send ACK or CMD
                                    if remote_uid in pending_commands:
                                        command = pending_commands.pop(remote_uid)
                                        ack_data = f"CMD:{remote_uid}:{command}".encode()
                                        await debug_print(f"Sending command to {remote_uid}: {command}", "COMMAND")
                                    else:
                                        ack_data = f"ACK:{base_ts}".encode()
                                    async with pin_lock:
                                        global lora
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
                    elif err == -81:  # Replace with actual timeout err code from library
                        await debug_print("Receive timeout - retrying...", "LORA")
                        state = STATE_IDLE
                        await asyncio.sleep(0)  # Yield to event loop
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
    # Example: listen for a button press to reset error count
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