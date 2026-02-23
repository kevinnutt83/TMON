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
    from sx1262 import SX1262, ERR_RX_TIMEOUT, ERR_UNKNOWN, ERR_CRC_MISMATCH  # Added library constants for error handling
except ImportError:
    SX1262 = None
    ERR_RX_TIMEOUT = -1  # Fallback assumptions
    ERR_UNKNOWN = -2
    ERR_CRC_MISMATCH = -3
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
import random  # Added for random backoff
import gc  # Added for memory optimization

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

async def connectLora():
    global lora
    lora_init_failures = 0
    MAX_LORA_INIT_FAILS = 3
    consecutive_failures = 0  # Added for failure tracking
    MAX_CONSECUTIVE_FAILS = 5  # Threshold for reset
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
        pending_commands = {}

        # Command handlers (added for completeness; adjust as needed)
        command_handlers = {
            'toggle_relay': toggle_relay,
            # Add other handlers if needed
        }

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
                                consecutive_failures += 1
                                if consecutive_failures > MAX_CONSECUTIVE_FAILS:
                                    await debug_print("Too many failures, resetting module", "ERROR")
                                    machine.reset()
                                continue
                        # Added CAD check with backoff
                        cad_result = lora.scanChannel()
                        if cad_result == CHANNEL_FREE:
                            lora.send(data)
                            consecutive_failures = 0  # Reset on success
                        else:
                            await debug_print(f"CAD: channel busy or error ({cad_result}), backoff", "LORA")
                            await asyncio.sleep(random.uniform(0.5, 2.0))
                            continue
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
                    # Enhanced error handling
                    if err != 0:
                        consecutive_failures += 1
                        if err == ERR_RX_TIMEOUT:
                            await debug_print("Receive timeout", "WARN")
                        elif err == ERR_CRC_MISMATCH:
                            await debug_print("CRC mismatch", "ERROR")
                        elif err == ERR_UNKNOWN:
                            await debug_print("Unknown receive error", "ERROR")
                        else:
                            await debug_print(f"Receive error: {err}", "ERROR")
                        if consecutive_failures > MAX_CONSECUTIVE_FAILS:
                            await debug_print("Too many failures, resetting module", "ERROR")
                            machine.reset()
                        if connected:
                            await debug_print("Disconnected from base station", "WARN")
                            connected = False
                        state = STATE_IDLE
                        await asyncio.sleep(send_interval)
                        continue
                    if msg:
                        consecutive_failures = 0  # Reset on success
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
                        await debug_print("No message received despite no error", "WARN")
                        state = STATE_IDLE
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
                    # Enhanced error handling
                    if err != 0:
                        consecutive_failures += 1
                        if err == ERR_RX_TIMEOUT:
                            await debug_print("Receive timeout", "WARN")
                        elif err == ERR_CRC_MISMATCH:
                            await debug_print("CRC mismatch", "ERROR")
                        elif err == ERR_UNKNOWN:
                            await debug_print("Unknown receive error", "ERROR")
                        else:
                            await debug_print(f"Receive error: {err}", "ERROR")
                        if consecutive_failures > MAX_CONSECUTIVE_FAILS:
                            await debug_print("Too many failures, resetting module", "ERROR")
                            machine.reset()
                        state = STATE_IDLE
                        await asyncio.sleep(0)
                        continue
                    if msg:
                        consecutive_failures = 0  # Reset on success
                        msg = msg.rstrip(b'\x00')
                        try:
                            msg_str = msg.decode()
                            if msg_str.startswith('TS:'):
                                parts = msg_str.split(',')
                                remote_ts = remote_uid = remote_runtime = remote_script_runtime = temp_c = temp_f = bar = humid = None
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
                                        # Added CAD check with backoff for base send
                                        cad_result = lora.scanChannel()
                                        if cad_result == CHANNEL_FREE:
                                            lora.send(ack_data)
                                            await debug_print(f"Sent ACK/CMD to {remote_uid}", "LORA")
                                        else:
                                            await debug_print(f"CAD: channel busy or error ({cad_result}), backoff", "LORA")
                                            await asyncio.sleep(random.uniform(0.5, 2.0))
                                            # Re-queue the command for next attempt
                                            if 'command' in locals():
                                                pending_commands[remote_uid] = command
                                            continue
                                    if not connected:
                                        await debug_print("Base: New connection established", "LORA")
                                        connected = True
                                    state = STATE_IDLE
                        except Exception as e:
                            error_msg = f"Invalid message: {str(e)}"
                            await debug_print(error_msg, "ERROR")
                            await log_error(error_msg)
                    else:
                        await debug_print("No message received despite no error", "WARN")
                    gc.collect()  # Added GC after receive/process

                else:
                    state = STATE_IDLE
                    await asyncio.sleep(1)

            gc.collect()  # Added GC after each loop iteration for memory stability

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