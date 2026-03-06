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

REMOTE_NODE_INFO_FILE = settings.LORA_REMOTE_INFO_LOG

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

async def proxy_register_for_remote(remote_uid, remote_machine_id, remote_firmware, remote_node_type):
    if not register_with_wp:
        return
    now = time.time()
    if remote_uid in proxy_last_ts and now - proxy_last_ts[remote_uid] < 270:
        await debug_print(f"Proxy register throttled for {remote_uid}", "BASE_NODE")
        return

    success = False
    try:
        await debug_print(f"Proxy check-in/register for remote {remote_uid} (MACHINE_ID={remote_machine_id[:16]}...)", "BASE_NODE")
        for attempt in range(3):
            try:
                success = await register_with_wp(unit_id=remote_uid, machine_id=remote_machine_id, firmware_version=remote_firmware, node_type=remote_node_type)
                if success:
                    await display_message(f"Reg {remote_uid[:8]} OK", 0.8)
                    break
                await asyncio.sleep(1.5 * (attempt + 1))
            except Exception as e:
                await log_error(f"Proxy reg attempt {attempt+1} failed for {remote_uid}: {e}")
                await asyncio.sleep(2 ** attempt)
    finally:
        pass

    if success:
        proxy_last_ts[remote_uid] = time.time()
    else:
        await display_message(f"Reg {remote_uid[:8]} FAIL", 1.5)
    gc.collect()

async def proxy_send_settings_for_remote(remote_uid, remote_unit_name, remote_settings_dict):
    if not send_settings_to_wp:
        return False
    return await send_settings_to_wp(unit_id=remote_uid, unit_name=remote_unit_name, settings_dict=remote_settings_dict)

async def proxy_fetch_settings_from_remote(remote_uid, remote_machine_id):
    if not fetch_settings_from_wp:
        return {}
    original_unit_id = settings.UNIT_ID
    original_get = utils.get_machine_id
    utils.get_machine_id = lambda: remote_machine_id
    settings.UNIT_ID = remote_uid
    try:
        return await fetch_settings_from_wp()
    finally:
        settings.UNIT_ID = original_unit_id
        utils.get_machine_id = original_get

async def proxy_poll_commands_for_remote(remote_uid, remote_machine_id):
    if not poll_device_commands:
        return []
    original_unit_id = settings.UNIT_ID
    original_get = utils.get_machine_id
    utils.get_machine_id = lambda: remote_machine_id
    settings.UNIT_ID = remote_uid
    try:
        return await poll_device_commands()
    finally:
        settings.UNIT_ID = original_unit_id
        utils.get_machine_id = original_get

async def proxy_poll_ota_for_remote(remote_uid, remote_machine_id):
    if not poll_ota_jobs:
        return []
    original_unit_id = settings.UNIT_ID
    original_get = utils.get_machine_id
    utils.get_machine_id = lambda: remote_machine_id
    settings.UNIT_ID = remote_uid
    try:
        return await poll_ota_jobs()
    finally:
        settings.UNIT_ID = original_unit_id
        utils.get_machine_id = original_get

async def proxy_request_file_for_remote(remote_uid, remote_machine_id, file_name):
    if not request_file_from_wp:
        return None
    original_unit_id = settings.UNIT_ID
    original_get = utils.get_machine_id
    utils.get_machine_id = lambda: remote_machine_id
    settings.UNIT_ID = remote_uid
    try:
        return await request_file_from_wp(file_name)
    finally:
        settings.UNIT_ID = original_unit_id
        utils.get_machine_id = original_get

async def proxy_confirm_command_for_remote(remote_uid, remote_machine_id, command_id):
    if not _wp.confirm_device_command:
        return
    original_unit_id = settings.UNIT_ID
    original_get = utils.get_machine_id
    utils.get_machine_id = lambda: remote_machine_id
    settings.UNIT_ID = remote_uid
    try:
        await _wp.confirm_device_command(command_id)
    finally:
        settings.UNIT_ID = original_unit_id
        utils.get_machine_id = original_get

def load_lora_next_sync():
    try:
        with open(settings.LORA_NEXT_SYNC_FILE, 'r') as f:
            return int(f.read().strip())
    except Exception:
        return 0

def save_lora_next_sync(value):
    try:
        with open(settings.LORA_NEXT_SYNC_FILE, 'w') as f:
            f.write(str(value))
    except Exception:
        pass

async def send_with_retry(data, retries=3):
    for attempt in range(retries):
        try:
            lora.send(data)
            return True
        except Exception as e:
            await debug_print(f"Send attempt {attempt+1} failed: {e}", "LORA")
            await asyncio.sleep(1)
    return False

async def recv_with_timeout(timeout_s):
    start = time.time()
    while time.time() - start < timeout_s:
        if lora.available():
            data = lora.recv()
            if data:
                sdata.lora_SigStr = lora.packetRssi()
                sdata.lora_snr = lora.packetSnr()
                return data
        await asyncio.sleep(0.1)
    return None

async def send_chunked(data_bytes, data_type, retries=3):
    size = len(data_bytes)
    chunk_size = 200
    chunks = [data_bytes[i:i+chunk_size] for i in range(0, size, chunk_size)]
    num_chunks = len(chunks)

    start_msg = f"START:{data_type},SIZE:{size},CHUNKS:{num_chunks}".encode()
    if not await send_with_retry(start_msg, retries):
        return False

    for i, chunk in enumerate(chunks):
        chunk_msg = f"CHUNK:{i+1},".encode() + chunk
        if not await send_with_retry(chunk_msg, retries):
            return False
        ack = await recv_with_timeout(5)
        if not ack or not ack.decode().startswith(f"ACK:{i+1}"):
            return False
        # Update progress
        percent = int(((i+1) / num_chunks) * 100)
        await display_message(f"TX {data_type}: {percent}%", 0.5)

    end_msg = f"END:{data_type}".encode()
    if not await send_with_retry(end_msg, retries):
        return False

    ack = await recv_with_timeout(5)
    if not ack or not ack.decode() == f"ACK:END":
        return False

    return True

async def recv_chunked(data_type, timeout_s=30):
    start = await recv_with_timeout(timeout_s)
    if not start or not start.decode().startswith(f"START:{data_type}"):
        return None

    parts = start.decode().split(',')
    size = int(parts[1].split(':')[1])
    num_chunks = int(parts[2].split(':')[1])

    received = b''
    for i in range(num_chunks):
        chunk = await recv_with_timeout(10)
        if not chunk or not chunk.decode().startswith(f"CHUNK:{i+1},"):
            return None
        received += chunk[chunk.find(b',')+1:]
        ack = f"ACK:{i+1}".encode()
        await send_with_retry(ack)
        # Update progress
        percent = int(((i+1) / num_chunks) * 100)
        await display_message(f"RX {data_type}: {percent}%", 0.5)

    end = await recv_with_timeout(5)
    if not end or not end.decode() == f"END:{data_type}":
        return None

    ack_end = b"ACK:END"
    await send_with_retry(ack_end)

    if len(received) != size:
        return None

    return received

async def handle_received_command(cmd_str):
    parts = cmd_str.split(',')
    if parts[0] == "toggle_relay":
        relay_num = int(parts[1])
        state = parts[2] == "on"
        toggle_relay(relay_num, state)
        return True
    return False

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

    busy = False
    if settings.NODE_TYPE == 'base':
        while True:
            if not busy:
                broadcast_msg = f"BROADCAST:{settings.LORA_NETWORK_NAME}".encode()
                await send_with_retry(broadcast_msg)
                await asyncio.sleep(5)

            data = await recv_with_timeout(1)
            if data:
                msg = data.decode()
                if msg.startswith("PING:"):
                    parts = msg[5:].split(',')
                    if len(parts) == 4:
                        unit_id, machine_id, name, password = parts
                        if name == settings.LORA_NETWORK_NAME and password == settings.LORA_NETWORK_PASSWORD:
                            busy = True
                            ack = b"ACK:OK"
                            await send_with_retry(ack)
                            # Record
                            settings.REMOTE_NODE_INFO[unit_id] = {'machine_id': machine_id, 'last_sync': time.time()}
                            save_remote_node_info()

                            # Receive data
                            settings_bytes = await recv_chunked("SETTINGS")
                            if not settings_bytes:
                                busy = False
                                continue
                            settings_dict = ujson.loads(settings_bytes)

                            sdata_bytes = await recv_chunked("SDATA")
                            if not sdata_bytes:
                                busy = False
                                continue
                            sdata_dict = ujson.loads(sdata_bytes)

                            # Update log
                            settings.REMOTE_NODE_INFO[unit_id]['unit_name'] = settings_dict.get('UNIT_Name', '')
                            settings.REMOTE_NODE_INFO[unit_id]['firmware_version'] = settings_dict.get('FIRMWARE_VERSION', '')
                            save_remote_node_info()

                            # Proxy to unit connector
                            await proxy_register_for_remote(unit_id, machine_id, settings_dict['FIRMWARE_VERSION'], 'remote')
                            await proxy_send_settings_for_remote(unit_id, settings_dict.get('UNIT_Name', ''), settings_dict)
                            stage_remote_field_data(unit_id, sdata_dict)  # Assumes this handles sdata as field data

                            # Fetch updates
                            new_settings = await proxy_fetch_settings_from_remote(unit_id, machine_id)
                            commands = await proxy_poll_commands_for_remote(unit_id, machine_id)
                            ota_jobs = await proxy_poll_ota_for_remote(unit_id, machine_id)

                            # Fetch manifest if ota
                            manifest = None
                            files = {}
                            if ota_jobs:
                                manifest = await proxy_request_file_for_remote(unit_id, machine_id, 'manifest.json')
                                for job in ota_jobs:
                                    f_name = job  # assume job is file name
                                    file_data = await proxy_request_file_for_remote(unit_id, machine_id, f_name)
                                    if file_data:
                                        files[f_name] = file_data

                            # Send back
                            if new_settings:
                                await send_chunked(ujson.dumps(new_settings).encode(), "SETTINGS")

                            for cmd in commands:
                                cmd_msg = f"CMD:{cmd}".encode()
                                await send_with_retry(cmd_msg)
                                ack_cmd = await recv_with_timeout(10)
                                if ack_cmd and ack_cmd.decode().startswith("CMD_OK:"):
                                    cmd_id = ack_cmd.decode()[7:]
                                    await proxy_confirm_command_for_remote(unit_id, machine_id, cmd_id)

                            if manifest:
                                await send_chunked(ujson.dumps(manifest).encode(), "MANIFEST")

                            for f_name, f_data in files.items():
                                await send_chunked(f_data, f"FILE:{f_name}")

                            # Close
                            next_sync = int(time.time() + settings.LORA_SYNC_RATE)
                            close_msg = f"CLOSE:{next_sync}".encode()
                            await send_with_retry(close_msg)
                            ack_close = await recv_with_timeout(5)
                            if ack_close and ack_close.decode() == "ACK:CLOSE":
                                settings.REMOTE_NODE_INFO[unit_id]['lora_next_sync'] = next_sync
                                save_remote_node_info()
                            busy = False

    elif settings.NODE_TYPE == 'remote':
        next_sync = load_lora_next_sync()
        if next_sync == 0:
            next_sync = time.time() + random.randint(0, settings.LORA_SYNC_RATE)
            save_lora_next_sync(next_sync)

        while True:
            if time.time() > next_sync:
                connected = False
                timeout = time.time() + 30
                while time.time() < timeout and not connected:
                    data = await recv_with_timeout(5)
                    if data and data.decode().startswith(f"BROADCAST:{settings.LORA_NETWORK_NAME}"):
                        ping_msg = f"PING:{settings.UNIT_ID},{get_machine_id()},{settings.LORA_NETWORK_NAME},{settings.LORA_NETWORK_PASSWORD}".encode()
                        await send_with_retry(ping_msg)
                        ack = await recv_with_timeout(10)
                        if ack and ack.decode() == "ACK:OK":
                            connected = True

                            # Send data
                            settings_dict = {k: getattr(settings, k) for k in dir(settings) if not k.startswith('__') and not callable(getattr(settings, k))}
                            await send_chunked(ujson.dumps(settings_dict).encode(), "SETTINGS")

                            sdata_dict = {k: getattr(sdata, k) for k in dir(sdata) if not k.startswith('__') and not callable(getattr(sdata, k))}
                            await send_chunked(ujson.dumps(sdata_dict).encode(), "SDATA")

                            # Receive updates
                            while True:
                                data = await recv_with_timeout(30)
                                if not data:
                                    break
                                msg = data.decode()
                                if msg.startswith("SETTINGS:"):
                                    settings_json_bytes = await recv_chunked("SETTINGS")
                                    if settings_json_bytes:
                                        with open(settings.REMOTE_SETTINGS_STAGED_FILE, 'wb') as f:
                                            f.write(settings_json_bytes)
                                        await send_with_retry(b"ACK:SETTINGS")

                                elif msg.startswith("CMD:"):
                                    if await handle_received_command(msg[4:]):
                                        cmd_id = ...  # parse id if needed
                                        await send_with_retry(f"CMD_OK:{cmd_id}".encode())

                                elif msg.startswith("MANIFEST:"):
                                    manifest_bytes = await recv_chunked("MANIFEST")
                                    if manifest_bytes:
                                        with open('/logs/ota_manifest.json', 'wb') as f:
                                            f.write(manifest_bytes)
                                        await send_with_retry(b"ACK:MANIFEST")

                                elif msg.startswith("FILE:"):
                                    f_name = msg.split(':')[1]
                                    file_bytes = await recv_chunked("FILE")
                                    if file_bytes:
                                        with open('/logs/' + f_name, 'wb') as f:
                                            f.write(file_bytes)
                                        await send_with_retry(f"ACK:FILE:{f_name}".encode())

                                elif msg.startswith("CLOSE:"):
                                    next_sync = int(msg[6:])
                                    save_lora_next_sync(next_sync)
                                    await send_with_retry(b"ACK:CLOSE")
                                    # Apply OTA if manifest present
                                    if os.stat('/logs/ota_manifest.json'):
                                        from ota import apply_from_local
                                        await apply_from_local()
                                    break

            await asyncio.sleep(1)