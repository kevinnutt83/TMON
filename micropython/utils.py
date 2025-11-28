# Firmware Version: v2.00j
import ujson
import uasyncio as asyncio
import os
import settings
from config_persist import write_text, read_text, set_flag, is_flag_set, write_json, read_json

# Persistent backlog file for unsent field data
FIELD_DATA_BACKLOG = settings.LOG_DIR + '/field_data_backlog.log'
UNIT_ID_FILE = settings.UNIT_ID_FILE if hasattr(settings, 'UNIT_ID_FILE') else (settings.LOG_DIR + '/unit_id.txt')
SUSPENDED_FLAG = getattr(settings, 'DEVICE_SUSPENDED_FILE', settings.LOG_DIR + '/suspended.flag')

def append_to_backlog(payload):
    checkLogDirectory()
    try:
        with open(FIELD_DATA_BACKLOG, 'a') as f:
            f.write(ujson.dumps(payload) + '\n')
    except Exception as e:
        print(f"Error appending to backlog: {e}")

def read_backlog():
    checkLogDirectory()
    try:
        try:
            os.stat(FIELD_DATA_BACKLOG)
        except OSError:
            return []
        with open(FIELD_DATA_BACKLOG, 'r') as f:
            lines = f.readlines()
        return [ujson.loads(line) for line in lines if line.strip()]
    except Exception as e:
        print(f"Error reading backlog: {e}")
        return []

def clear_backlog():
    checkLogDirectory()
    try:
        try:
            os.stat(FIELD_DATA_BACKLOG)
            with open(FIELD_DATA_BACKLOG, 'w') as f:
                f.write('')
        except OSError:
            pass
    except Exception as e:
        print(f"Error clearing backlog: {e}")
def persist_unit_id(unit_id):
    try:
        checkLogDirectory()
        write_text(UNIT_ID_FILE, str(unit_id).strip())
    except Exception as e:
        print(f"Error persisting UNIT_ID: {e}")

def load_persisted_unit_id():
    try:
        checkLogDirectory()
        val = read_text(UNIT_ID_FILE, None)
        if not val:
            return None
        val = val.strip()
        return val if val else None
    except Exception:
        return None

def persist_suspension_state(enabled: bool):
    try:
        set_flag(SUSPENDED_FLAG, enabled)
    except Exception:
        pass

def load_suspension_state():
    try:
        return is_flag_set(SUSPENDED_FLAG)
    except Exception:
        return False
# --- Field Data Log Management ---


def rotate_field_data_log():
    """Rotate field_data.log to data_history.log and clear field_data.log."""
    checkLogDirectory()
    try:
        try:
            os.stat(settings.FIELD_DATA_LOG)
            # Append to history log
            with open(settings.FIELD_DATA_LOG, 'r') as src, open(settings.DATA_HISTORY_LOG, 'a') as dst:
                for line in src:
                    dst.write(line)
            # Clear field_data.log
            with open(settings.FIELD_DATA_LOG, 'w') as f:
                f.write('')
        except OSError:
            pass
    except Exception as e:
        print(f"Error rotating field data log: {e}")

def delete_field_data_log():
    checkLogDirectory()
    try:
        try:
            os.stat(settings.FIELD_DATA_LOG)
            os.remove(settings.FIELD_DATA_LOG)
        except OSError:
            pass
    except Exception as e:
        print(f"Error deleting field data log: {e}")

def delete_data_history_log():
    checkLogDirectory()
    try:
        try:
            os.stat(settings.DATA_HISTORY_LOG)
            os.remove(settings.DATA_HISTORY_LOG)
        except OSError:
            pass
    except Exception as e:
        print(f"Error deleting data history log: {e}")

_send_field_data_lock = asyncio.Lock()

async def send_field_data_log():
    """Send field_data.log to WordPress and rotate on confirmation."""
    if getattr(settings, 'NODE_TYPE', 'base') != 'base':
        return
    from wprest import WORDPRESS_API_URL, get_jwt_token
    await debug_print('send_field_data_log: Starting field data delivery process', 'DEBUG')
    if not WORDPRESS_API_URL:
        await debug_print('send_field_data_log: No WORDPRESS_API_URL set', 'ERROR')
        return
    checkLogDirectory()
    # Ensure field_data.log exists before reading
    try:
        try:
            os.stat(settings.FIELD_DATA_LOG)
        except OSError:
            with open(settings.FIELD_DATA_LOG, 'w') as f:
                f.write('')
            await debug_print('send_field_data_log: FIELD_DATA_LOG did not exist, created empty file', 'DEBUG')
    except Exception as e:
        await debug_print(f'send_field_data_log: Exception checking/creating FIELD_DATA_LOG: {e}', 'ERROR')
        return
    max_retries = 5
    try:
        if _send_field_data_lock.locked():
            await debug_print('send_field_data_log: another send in progress, skipping this cycle', 'DEBUG')
            return
        async with _send_field_data_lock:
            await debug_print('send_field_data_log: Reading field_data.log', 'DEBUG')
            payloads = []
            total_lines = 0
            batch = []
            batch_size = 10
            with open(settings.FIELD_DATA_LOG, 'rb') as f:
                for raw_line in f:
                    if not raw_line:
                        continue
                    try:
                        line = raw_line.decode('utf-8', 'ignore')
                    except Exception:
                        try:
                            line = raw_line.decode()
                        except Exception:
                            line = ''
                    if line and line.strip():
                        try:
                            batch.append(ujson.loads(line))
                            total_lines += 1
                            if len(batch) >= batch_size:
                                payloads.append({'unit_id': settings.UNIT_ID, 'data': batch})
                                batch = []
                        except Exception as pe:
                            await debug_print(f'send_field_data_log: JSON parse error on a line: {pe}', 'ERROR')
            if batch:
                payloads.append({'unit_id': settings.UNIT_ID, 'data': batch})
            await debug_print(f'send_field_data_log: Read {total_lines} lines and built {len(payloads)} batched payloads', 'DEBUG')
            backlog = read_backlog()
            await debug_print(f'send_field_data_log: Read {len(backlog)} backlog payloads', 'DEBUG')
            payloads = backlog + payloads
            backlog_count = len(backlog)
            if not payloads:
                await debug_print('send_field_data_log: No payloads to send', 'DEBUG')
                return
            import urequests as requests
            def _sanitize_json(obj, depth=0):
                if depth > 6:
                    return str(obj)
                t = type(obj)
                if obj is None or t in (int, float, bool):
                    return obj
                if t is str:
                    try:
                        _ = obj.encode('utf-8', 'ignore')
                        return _.decode('utf-8', 'ignore')
                    except Exception:
                        try:
                            return ''.join(ch if 32 <= ord(ch) < 127 else ' ' for ch in obj)
                        except Exception:
                            return '<str>'
                if t is bytes:
                    try:
                        return obj.decode('utf-8', 'ignore')
                    except Exception:
                        try:
                            import ubinascii as _ub
                        except Exception:
                            import binascii as _ub
                        try:
                            return _ub.hexlify(obj).decode('ascii')
                        except Exception:
                            return '<bytes>'
                if t is dict:
                    out = {}
                    for k, v in obj.items():
                        try:
                            key = k if isinstance(k, str) else str(k)
                            out[key] = _sanitize_json(v, depth + 1)
                        except Exception:
                            pass
                    return out
                if t in (list, tuple):
                    return [_sanitize_json(x, depth + 1) for x in obj]
                try:
                    return obj if t in (int, float, bool) else str(obj)
                except Exception:
                    return '<obj>'
            sent_indices = []
            for idx, payload in enumerate(payloads):
                delay = 2
                try:
                    payload['machine_id'] = get_machine_id()
                except Exception:
                    pass
                # Enrich envelope with firmware and node role for auditing/normalization
                try:
                    payload['firmware_version'] = getattr(settings, 'FIRMWARE_VERSION', '')
                except Exception:
                    pass
                try:
                    payload['node_type'] = getattr(settings, 'NODE_TYPE', '')
                except Exception:
                    pass
                delivered = False
                await debug_print(f'send_field_data_log: Sending payload {idx+1}/{len(payloads)}', 'DEBUG')
                for attempt in range(1, max_retries + 1):
                    try:
                        import gc as _gc
                        _gc.collect()
                    except Exception:
                        pass
                    try:
                        token = get_jwt_token()
                        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json; charset=utf-8'}
                        # Optional field data HMAC signing
                        try:
                            if getattr(settings, 'FIELD_DATA_HMAC_ENABLED', False):
                                import uhashlib as _uh, ubinascii as _ub
                                secret = getattr(settings, 'FIELD_DATA_HMAC_SECRET', '')
                                if secret:
                                    # Build canonical minimal string
                                    core = []
                                    for k in getattr(settings, 'FIELD_DATA_HMAC_INCLUDE_KEYS', ['unit_id']):
                                        core.append(str(payload.get(k, '')))
                                    # Also include count and first/last timestamps if present for stability
                                    try:
                                        arr = payload.get('data', [])
                                        if isinstance(arr, list) and arr:
                                            first_ts = arr[0].get('timestamp') if isinstance(arr[0], dict) else ''
                                            last_ts = arr[-1].get('timestamp') if isinstance(arr[-1], dict) else ''
                                        else:
                                            first_ts = last_ts = ''
                                    except Exception:
                                        first_ts = last_ts = ''
                                    canon = '|'.join(core + [str(len(payload.get('data', []) or [])), str(first_ts), str(last_ts)])
                                    h = _uh.sha256(secret.encode() + canon.encode())
                                    sig = _ub.hexlify(h.digest()).decode()[:int(getattr(settings,'FIELD_DATA_HMAC_TRUNCATE',32))]
                                    payload['sig'] = sig
                                    payload['sig_v'] = 1
                        except Exception:
                            pass
                        await debug_print(f'send_field_data_log: Attempt {attempt} POST to {WORDPRESS_API_URL}/wp-json/tmon/v1/device/field-data', 'DEBUG')
                        safe_payload = _sanitize_json(payload)
                        try:
                            encoded = ujson.dumps(safe_payload)
                        except Exception:
                            minimal = {'unit_id': settings.UNIT_ID, 'data': []}
                            if isinstance(payload, dict) and 'data' in payload:
                                minimal['data'] = _sanitize_json(payload['data'])
                            encoded = ujson.dumps(minimal)
                        try:
                            log_snippet = encoded[:200]
                            log_snippet = ''.join(ch if 32 <= ord(ch) <= 126 else ' ' for ch in log_snippet)
                        except Exception:
                            log_snippet = '<payload>'
                        await debug_print(f'send_field_data_log: Payload: {log_snippet}', 'DEBUG')
                        resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/field-data', headers=headers, data=encoded, timeout=10)
                        try:
                            await debug_print(f'send_field_data_log: Response status: {resp.status_code}', 'DEBUG')
                            resp_bytes = b''
                            try:
                                resp_bytes = resp.content if hasattr(resp, 'content') else b''
                            except Exception:
                                resp_bytes = b''
                            resp_json = {}
                            if resp_bytes:
                                try:
                                    resp_text_local = resp_bytes.decode('utf-8', 'ignore')
                                    try:
                                        resp_json = ujson.loads(resp_text_local)
                                    except Exception as e:
                                        await debug_print(f'send_field_data_log: Failed to parse response JSON: {e}', 'ERROR')
                                    safe_text = ''.join(ch if 32 <= ord(ch) <= 126 else ' ' for ch in resp_text_local)
                                    await debug_print(f'send_field_data_log: Response text: {safe_text[:200]}', 'DEBUG')
                                except Exception:
                                    pass
                            ok_resp = (resp.status_code == 200) and ((resp_json.get('status') == 'ok') or (resp_bytes == b'OK'))
                            if ok_resp:
                                # Persist UNIT_ID mapping if provided
                                try:
                                    new_uid = resp_json.get('unit_id') if isinstance(resp_json, dict) else None
                                    if new_uid and str(new_uid) != str(settings.UNIT_ID):
                                        settings.UNIT_ID = str(new_uid)
                                        try:
                                            persist_unit_id(settings.UNIT_ID)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                                delivered = True
                                await debug_print(f'send_field_data_log: Payload {idx+1} delivered successfully', 'DEBUG')
                                break
                            else:
                                err_txt = ''
                                try:
                                    err_txt = resp_bytes.decode('utf-8','ignore')[:120]
                                    err_txt = ''.join(ch if 32 <= ord(ch) <= 126 else ' ' for ch in err_txt)
                                except Exception:
                                    pass
                                await log_error(f'Field data log delivery failed (attempt {attempt}): {resp.status_code} {err_txt}', 'field_data')
                        finally:
                            try:
                                resp.close()
                            except Exception:
                                pass
                    except Exception as e:
                        try:
                            emsg = f"{type(e).__name__}: {str(e)}"
                            emsg = ''.join(ch if ord(ch) >= 32 else ' ' for ch in emsg)
                        except Exception:
                            emsg = f"{type(e).__name__}"
                        await debug_print(f'send_field_data_log: Exception during delivery attempt {attempt}: {emsg}', 'ERROR')
                        await log_error(f'Field data log delivery exception (attempt {attempt}): {emsg}', 'field_data')
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)
                if delivered:
                    sent_indices.append(idx)
                else:
                    await debug_print(f'send_field_data_log: Payload {idx+1} failed after {max_retries} attempts', 'ERROR')
                    await log_error('Field data log delivery failed after max retries, will try again later.', 'field_data')
            if total_lines:
                current_indices = range(backlog_count, len(payloads))
                delivered_current_all = all(i in sent_indices for i in current_indices) if len(payloads) > backlog_count else False
                if delivered_current_all:
                    await debug_print('send_field_data_log: Rotating field_data.log after successful delivery of current payloads', 'DEBUG')
                    rotate_field_data_log()
            unsent = [payloads[i] for i in range(len(payloads)) if i not in sent_indices]
            if unsent:
                await debug_print(f'send_field_data_log: Writing {len(unsent)} unsent payloads back to backlog', 'DEBUG')
                clear_backlog()
                for p in unsent:
                    append_to_backlog(p)
            else:
                await debug_print('send_field_data_log: All payloads delivered, clearing backlog', 'DEBUG')
                clear_backlog()
    except Exception as e:
        try:
            import sys
            try:
                import uio as io
            except Exception:
                import io
            buf = io.StringIO()
            try:
                sys.print_exception(e, buf)
                tb_str = buf.getvalue()
            except Exception:
                tb_str = ''
        except Exception:
            tb_str = ''
        etype = type(e).__name__
        try:
            emsg = f"{etype}: {str(e)}"
            emsg = ''.join(ch if 32 <= ord(ch) <= 126 else ' ' for ch in emsg)
        except Exception:
            emsg = etype
        try:
            tb_str = ''.join(ch if 32 <= ord(ch) <= 126 or ch in '\n\r\t' else ' ' for ch in tb_str)
        except Exception:
            pass
        await debug_print(f'send_field_data_log: Exception in send_field_data_log: {emsg}\n{tb_str}', 'ERROR')
        await log_error(f'Failed to send field data log: {emsg}\n{tb_str}', 'field_data')
    finally:
        # nothing to do; lock released by context manager
        pass

async def periodic_field_data_send():
    while True:
        await send_field_data_log()
        await asyncio.sleep(settings.FIELD_DATA_SEND_INTERVAL)
# Record all sdata and settings variables to field_data.log with timestamp
def get_unix_time():
    try:
        # MicroPython often uses epoch 2000-01-01. Detect and offset to Unix epoch if needed.
        epoch_year = time.gmtime(0)[0] if hasattr(time, 'gmtime') else 1970
        t = int(time.time())
        if epoch_year >= 2000:
            return t + 946684800  # seconds from 1970->2000
        return t
    except Exception:
        return int(time.time())

def record_field_data():
    """Append a minimal telemetry record for the base node.
    Prior approach dumped all settings/sdata which was too heavy for flash and bandwidth.
    """
    import sdata, settings, ujson, os, utime as time
    entry = {'timestamp': int(get_unix_time())}
    try:
        ts = time.localtime()
        entry['ts_iso'] = f"{ts[0]:04}-{ts[1]:02}-{ts[2]:02} {ts[3]:02}:{ts[4]:02}:{ts[5]:02}"
    except Exception:
        pass
    # Curated sdata fields
    def _copy(dst, src, key, alias=None):
        try:
            val = getattr(src, key)
            dst[alias or key] = val
        except Exception:
            pass
    _copy(entry, sdata, 'cur_temp_f')
    _copy(entry, sdata, 'cur_temp_c')
    _copy(entry, sdata, 'cur_humid')
    _copy(entry, sdata, 'cur_bar_pres')
    _copy(entry, sdata, 'sys_voltage')
    _copy(entry, sdata, 'wifi_rssi')
    _copy(entry, sdata, 'lora_SigStr')
    _copy(entry, sdata, 'free_mem')
    _copy(entry, sdata, 'script_runtime')
    _copy(entry, sdata, 'loop_runtime')
    _copy(entry, sdata, 'cpu_temp')
    _copy(entry, sdata, 'error_count')
    _copy(entry, sdata, 'last_error')
    # Relay runtime counters (only include if non-zero to reduce payload size)
    for i in range(1,9):
        try:
            val = getattr(sdata, f'relay{i}_runtime_s')
            if val:
                entry[f'relay{i}_runtime_s'] = val
            on_state = getattr(sdata, f'relay{i}_on')
            if on_state:
                entry[f'relay{i}_on'] = 1
        except Exception:
            pass
    # GPS mirrors if present
    _copy(entry, sdata, 'gps_lat')
    _copy(entry, sdata, 'gps_lng')
    _copy(entry, sdata, 'gps_alt_m')
    _copy(entry, sdata, 'gps_accuracy_m')
    _copy(entry, sdata, 'gps_last_fix_ts')
    # Minimal identity
    entry['unit_id'] = getattr(settings, 'UNIT_ID', '')
    entry['firmware_version'] = getattr(settings, 'FIRMWARE_VERSION', '')
    entry['NODE_TYPE'] = getattr(settings, 'NODE_TYPE', '')
    # Only persist on base node to avoid filling flash on remotes
    if getattr(settings, 'NODE_TYPE', 'base') != 'base':
        return
    checkLogDirectory()
    try:
        with open(settings.FIELD_DATA_LOG, 'a') as f:
            f.write(ujson.dumps(entry) + '\n')
        import gc
        gc.collect()
    except Exception as e:
        print(f"Error recording field data: {e}")
import utime as time
import settings
import machine
from machine import Pin, SPI, PWM, ADC, soft_reset
import os
import sys
import uasyncio as asyncio
import gc
from oled import display_message
import ujson

# Measure system voltage and update sdata.sys_voltage
def update_sys_voltage():
    import sdata
    try:
        adc = ADC(Pin(settings.SYS_VOLTAGE_PIN))  # Define SYS_VOLTAGE_PIN in settings.py
        raw = adc.read_u16()  # 0-65535
        # Convert raw ADC to voltage (assume 3.3V ref, scale as needed)
        # If voltage divider is used, adjust scale accordingly
        voltage = (raw / 65535) * settings.SYS_VOLTAGE_MAX  # e.g., 5.0 if scaled to 5V
        sdata.sys_voltage = voltage
        return voltage
    except Exception as e:
        sdata.sys_voltage = 0
        return 0

#Create Log File Directories
def checkLogDirectory():
    # Create log directory and file if not present (only for base)
    try:
        dirs = os.listdir('/')
        if settings.LOG_DIR[1:] not in dirs:  # Strip '/' for check
            os.mkdir(settings.LOG_DIR)
    except OSError:
        print("Error creating log directory")

# Asynchronous function to free pins (set to input mode to avoid conflicts)
async def free_pins():
    machine.Pin(settings.CLK_PIN, machine.Pin.IN)
    machine.Pin(settings.MOSI_PIN, machine.Pin.IN)
    machine.Pin(settings.MISO_PIN, machine.Pin.IN)
    machine.Pin(settings.CS_PIN, machine.Pin.IN)
    machine.Pin(settings.IRQ_PIN, machine.Pin.IN)
    machine.Pin(settings.RST_PIN, machine.Pin.IN)
    machine.Pin(settings.BUSY_PIN, machine.Pin.IN)
    machine.Pin(settings.I2C_A_SCL_PIN, machine.Pin.IN)
    machine.Pin(settings.I2C_A_SDA_PIN, machine.Pin.IN)
    await asyncio.sleep(0)  # Yield control

# Asynchronous garbage collection
async def runGC():
    gc.enable()
    try:
        unreachable_objects = gc.collect()  # Perform garbage collection
        print(f"Unreachable objects collected: {unreachable_objects}")
        used_memory = gc.mem_alloc()
        total_memory = used_memory + gc.mem_free()
        avail_memory = total_memory - used_memory
        print(f"Memory used (RAM): {used_memory} bytes / Total available: {total_memory} bytes | Bytes Remaining - {avail_memory} bytes")
    except MemoryError:
        print("MemoryError: Failed to allocate memory during garbage collection")
        gc.collect()
        print("Garbage collection completed after MemoryError")
    await asyncio.sleep(0)  # Yield control

# Asynchronous debug print
async def debug_print(message, status):
    # Feature-based debug control
    debug_flags = {
        'TEMP': settings.DEBUG_TEMP,
        'BAR': settings.DEBUG_BAR,
        'HUMID': settings.DEBUG_HUMID,
        'LORA': settings.DEBUG_LORA,
    }
    # Always print if global DEBUG is True
    should_print = settings.DEBUG
    # Print if feature-specific debug is enabled
    for key, enabled in debug_flags.items():
        if key in status and enabled:
            should_print = True
    if should_print:
        # Sanitize for print/display to avoid UnicodeError
        try:
            safe_msg = message
            if isinstance(safe_msg, bytes):
                safe_msg = safe_msg.decode('utf-8', 'ignore')
            safe_msg = ''.join(ch if 32 <= ord(ch) <= 126 else ' ' for ch in safe_msg)
        except Exception:
            safe_msg = '<unprintable>'
        current_time = time.localtime()
        timestamp = f"{current_time[0]:04}-{current_time[1]:02}-{current_time[2]:02} {current_time[3]:02}:{current_time[4]:02}:{current_time[5]:02}"
        print(f"[{timestamp}] [{status}] {safe_msg}")
        try:
            await display_message(safe_msg, 1.5)
        except Exception:
            pass
    await asyncio.sleep(0)  # Yield control

def led_status_flash(status):
    """General-purpose LED flash based on status, to be called in main loops or event handlers."""
    import uasyncio as asyncio
    from utils import flash_led
    color_map = {
        'INFO': 'green',
        'SUCCESS': 'green',
        'OK': 'green',
        'WARN': 'orange',
        'WARNING': 'orange',
        'ERROR': 'red',
        'WIFI': 'blue',
        # LoRa specific
        'LORA_RX': 'purple',
        'LORA_TX': 'teal',
        # Sampling specific
        'SAMPLE_TEMP': 'magenta',
        'SAMPLE_HUMID': 'cyan',
        'SAMPLE_BAR': 'blue',
    }
    color = color_map.get(status, 'white')
    # Schedule LED flash asynchronously
    asyncio.create_task(flash_led(1, 0.2, color, 'short'))

# Expanded color to duty cycle mapping
color_to_duty = {
    'white': (255, 255, 255),
    'red': (255, 0, 0),
    'blue': (0, 0, 255),
    'green': (0, 255, 0),
    'yellow': (255, 255, 0),
    'cyan': (0, 255, 255),
    'magenta': (255, 0, 255),
    'orange': (255, 128, 0),
    'purple': (128, 0, 255),
    'pink': (255, 128, 128),
    'lime': (128, 255, 0),
    'teal': (0, 128, 128),
    'lavender': (128, 0, 128),
    'brown': (128, 64, 0),
    'beige': (255, 192, 128),
    'maroon': (128, 0, 0),
    'olive': (128, 128, 0),
    'navy': (0, 0, 128),
    'grey': (128, 128, 128),
    'black': (0, 0, 0)
}

# Commented out examples of using flash_led:
# await flash_led(3, 0.5, 'red', 'short')      # Flash red LED 3 times, short interval
# await flash_led(5, 1, 'green', 'mix')        # Flash green LED 5 times, mixed pattern
# await flash_led(1, 2, 'blue', 'on')          # Turn blue LED on
# await flash_led(1, 2, 'blue', 'off')         # Turn blue LED off
# await flash_led(2, 1, 'yellow', 'clear')     # Clear (turn off) yellow LED

# Lock for synchronizing LED operations
led_lock = asyncio.Lock()

def set_color(rgb_led, color):
    try:
        rgb_led[0] = color
        rgb_led.write()
    except Exception as e:
        debug_print(f"LED operation failed: {e}","ERROR LED")

async def flash_led(num_flashes, interval, lightColor, pattern):
    from neopixel import NeoPixel
    from machine import Pin

    duty_cycle = color_to_duty.get(lightColor.lower())
    if duty_cycle is None:
        print(f"Invalid color: {lightColor}")
        return

    rgb_led_pin = Pin(settings.LED_PIN, Pin.OUT)
    rgb_led = NeoPixel(rgb_led_pin, 1)
    await asyncio.sleep(0.1)  # Ensure the LED is properly initialized

    async with led_lock:
        try:
            if pattern == "on":
                set_color(rgb_led, duty_cycle)
                await asyncio.sleep(0.1)
                return
            elif pattern == "off" or pattern == "clear":
                set_color(rgb_led, (0, 0, 0))
                await asyncio.sleep(0.1)
                return

            if pattern == "mix":
                for i in range(num_flashes):
                    set_color(rgb_led, duty_cycle)
                    await asyncio.sleep(interval if i % 2 == 0 else interval * 3)
                    set_color(rgb_led, (0, 0, 0))
                    await asyncio.sleep(interval)
            else:
                flash_interval = interval if pattern == "short" else interval * 3
                for i in range(num_flashes):
                    set_color(rgb_led, duty_cycle)
                    await asyncio.sleep(flash_interval)
                    set_color(rgb_led, (0, 0, 0))
                    await asyncio.sleep(interval)

            set_color(rgb_led, (0, 0, 0))
            await asyncio.sleep(0.1)
        except OSError as e:
            print(f"LED operation failed: {e}")
        finally:
            rgb_led_pin.init(Pin.IN)  # Release the pin


ERROR_LOG_FILE = getattr(settings, 'ERROR_LOG_FILE', '/logs/lora_errors.log')

async def log_error(error_msg, context=None):
    """Log error to persistent storage and optionally print to console."""
    try:
        ts = time.localtime()
        timestamp = f"{ts[0]:04}-{ts[1]:02}-{ts[2]:02} {ts[3]:02}:{ts[4]:02}:{ts[5]:02}"
        entry = {'timestamp': timestamp, 'error': error_msg, 'context': context}
        # Append to error log file
        try:
            os.stat(settings.LOG_DIR)
        except OSError:
            os.mkdir(settings.LOG_DIR)
        with open(ERROR_LOG_FILE, 'a') as f:
            f.write(ujson.dumps(entry) + '\n')
        if settings.DEBUG:
            print(f"[ERROR] {timestamp}: {error_msg} | {context}")
    except Exception as e:
        print(f"[FATAL] Failed to log error: {e}")
    await asyncio.sleep(0)

def write_lora_log(message, level='INFO'):
    """Append a structured entry to lora.log with timestamp and level."""
    try:
        ts = time.localtime()
        timestamp = f"{ts[0]:04}-{ts[1]:02}-{ts[2]:02} {ts[3]:02}:{ts[4]:02}:{ts[5]:02}"
        entry = {'timestamp': timestamp, 'level': level, 'message': message}
        try:
            os.stat(settings.LOG_DIR)
        except OSError:
            os.mkdir(settings.LOG_DIR)
        with open(settings.LOG_FILE, 'a') as f:
            f.write(ujson.dumps(entry) + '\n')
    except Exception as e:
        # As a last resort, print; avoid raising
        try:
            print(f"[LOGBACKUP] {level}: {message} ({e})")
        except Exception:
            pass

async def safe_run(coro, context=None):
    """Run a coroutine and log any exceptions, never let them escape."""
    try:
        await coro
    except Exception as e:
        await log_error(str(e), context)

class TMONAI:
    """Basic AI for system operations, error response, and self-healing."""
    def __init__(self):
        self.error_count = 0
        self.last_error = None
        self.recovery_actions = []

    async def observe_error(self, error_msg, context=None):
        self.error_count += 1
        self.last_error = (error_msg, context)
        # Example: escalate if too many errors
        if self.error_count > 5:
            await log_error('AI: Too many errors, attempting system recovery', context)
            await self.recover_system()

    async def recover_system(self):
        # Example: restart network, re-init hardware, or soft reset
        try:
            import machine
            await log_error('AI: Performing soft reset', 'recovery')
            machine.soft_reset()
        except Exception as e:
            await log_error(f'AI: Recovery failed: {e}', 'recovery')

    async def suggest_action(self, context):
        # Example: suggest user actions based on context
        if 'wifi' in str(context).lower():
            return 'Check WiFi credentials or signal.'
        if 'ota' in str(context).lower():
            return 'Retry OTA or check file integrity.'
        return 'Check device logs and power cycle if needed.'

# Singleton instance
TMON_AI = TMONAI()

def get_machine_id():
    try:
        # Import locally to avoid desktop lints; valid on MicroPython firmware
        import machine as _m
        import ubinascii as _ub
        uid = _m.unique_id() if hasattr(_m, 'unique_id') else None
        if uid is None:
            return ''
        return _ub.hexlify(uid).decode('utf-8')
    except Exception:
        return ''

# Provisioning log file
PROVISION_LOG_FILE = getattr(settings, 'LOG_DIR', '/logs') + '/provisioning.log'

def provisioning_log(msg):
    """Append provisioning-specific debug to the provisioning log + console."""
    try:
        ts = time.localtime()
        timestamp = f"{ts[0]:04}-{ts[1]:02}-{ts[2]:02} {ts[3]:02}:{ts[4]:02}:{ts[5]:02}"
        entry = f"[{timestamp}] {msg}"
        print("[PROVISION] " + entry)
        try:
            checkLogDirectory()
            with open(PROVISION_LOG_FILE, 'a') as f:
                f.write(entry + '\n')
        except Exception:
            pass
    except Exception:
        pass

# New: provisioning check + apply
async def fetch_admin_provisioning(machine_id=None, unit_id=None):
    """Fetch pending provisioning from TMON Admin REST check-in endpoint."""
    provisioning_log(f"fetch_admin_provisioning: start (machine_id={machine_id}, unit_id={unit_id})")
    try:
        import urequests as requests, ujson
    except Exception:
        provisioning_log("fetch_admin_provisioning: urequests not available")
        return None
    from settings import TMON_ADMIN_API_URL, UNIT_ID as LOCAL_UID
    if not TMON_ADMIN_API_URL:
        provisioning_log("fetch_admin_provisioning: TMON_ADMIN_API_URL not set, abort")
        return None
    key_payload = {}
    if machine_id:
        key_payload['machine_id'] = machine_id
    elif unit_id:
        key_payload['unit_id'] = unit_id
    else:
        # Use persisted or detected ids
        key_payload['machine_id'] = get_machine_id()
        key_payload['unit_id'] = getattr(settings, 'UNIT_ID', '')
    try:
        url = TMON_ADMIN_API_URL.rstrip('/') + '/wp-json/tmon-admin/v1/device/check-in'
        body = ujson.dumps(key_payload)
        provisioning_log(f"fetch_admin_provisioning: POST {url} payload={key_payload}")
        resp = requests.post(url, headers={'Content-Type': 'application/json'}, data=body, timeout=10)
        status = getattr(resp, 'status_code', getattr(resp, 'status', None))
        provisioning_log(f"fetch_admin_provisioning: response status {status}")
        if status and int(status) == 200:
            try:
                data = ujson.loads(resp.content if hasattr(resp, 'content') else resp.text)
            except Exception:
                try:
                    data = ujson.loads(resp.text)
                except Exception:
                    data = None
            provisioning_log(f"fetch_admin_provisioning: response JSON: {data}")
            if isinstance(data, dict):
                # Top-level admin fields (not queued provision)
                if 'unit_id' in data and data.get('unit_id'):
                    new_uid = str(data.get('unit_id'))
                    if new_uid and new_uid != getattr(settings, 'UNIT_ID', ''):
                        settings.UNIT_ID = new_uid
                        try:
                            persist_unit_id(new_uid)
                            provisioning_log(f"fetch_admin_provisioning: UNIT_ID set to {new_uid} and persisted")
                        except Exception:
                            provisioning_log(f"fetch_admin_provisioning: failed to persist UNIT_ID {new_uid}")
                # Accept either 'site_url' or 'wordpress_api_url' to update server endpoint
                maybe_site = data.get('site_url') or data.get('wordpress_api_url') or data.get('site') or None
                if maybe_site:
                    try:
                        settings.WORDPRESS_API_URL = maybe_site
                        try:
                            write_text(getattr(settings, 'WORDPRESS_API_URL_FILE', settings.LOG_DIR + '/wordpress_api_url.txt'), str(maybe_site))
                            provisioning_log(f"fetch_admin_provisioning: WORDPRESS_API_URL set to {maybe_site} and persisted")
                        except Exception:
                            provisioning_log("fetch_admin_provisioning: failed to persist WORDPRESS_API_URL")
                    except Exception as e:
                        provisioning_log(f"fetch_admin_provisioning: failed to apply site_url {maybe_site}: {e}")
                # Persist on 'provisioned' flag if present
                if data.get('provisioned') is True:
                    try:
                        settings.UNIT_PROVISIONED = True
                        write_text(getattr(settings, 'PROVISIONED_FLAG_FILE', '/logs/provisioned.flag'), 'ok')
                        provisioning_log("fetch_admin_provisioning: marked UNIT_PROVISIONED True and wrote flag")
                    except Exception:
                        provisioning_log("fetch_admin_provisioning: failed to write PROVISIONED_FLAG_FILE")

                # Deliver explicit queued provision payload if present
                if data.get('provision'):
                    provisioning_log("fetch_admin_provisioning: found explicit 'provision' payload")
                    return data.get('provision')
                # Otherwise return None (no queued provision)
                return None
    except Exception as e:
        await debug_print(f'fetch_admin_provisioning: exception {e}', 'ERROR')
        provisioning_log(f"fetch_admin_provisioning: exception {e}")
    return None

def apply_staged_settings_and_reboot(staged):
    provisioning_log(f"apply_staged_settings: Begin apply staged settings: {staged}")
    try:
        from config_persist import write_json, write_text, set_flag
        import settings as _settings
        # Persist applied
        try:
            write_json(_settings.REMOTE_SETTINGS_APPLIED_FILE, staged)
        except Exception:
            pass
        # Persist UNIT_ID & WORDPRESS_API_URL & UNIT_Name
        try:
            if 'unit_id' in staged:
                _settings.UNIT_ID = str(staged['unit_id'])
                write_text(_settings.UNIT_ID_FILE, _settings.UNIT_ID)
            site_val = staged.get('site_url') or staged.get('wordpress_api_url') or staged.get('site') or ''
            if site_val:
                _settings.WORDPRESS_API_URL = site_val
                write_text(getattr(_settings, 'WORDPRESS_API_URL_FILE', _settings.LOG_DIR + '/wordpress_api_url.txt'), site_val)
            if 'unit_name' in staged:
                _settings.UNIT_Name = str(staged['unit_name'])
            _settings.UNIT_PROVISIONED = True
            write_text(getattr(_settings, 'PROVISIONED_FLAG_FILE', _settings.LOG_DIR + '/provisioned.flag'), 'ok')
        except Exception:
            pass

        # Post confirm to Admin with token header
        try:
            import urequests, ujson
            admin = getattr(settings, 'TMON_ADMIN_API_URL', '').rstrip('/')
            token = getattr(settings, 'TMON_ADMIN_CONFIRM_TOKEN', '')
            if admin and token:
                hdr = {'Content-Type': 'application/json', 'X-TMON-CONFIRM': token}
                body = ujson.dumps({'unit_id': settings.UNIT_ID, 'machine_id': get_machine_id()})
                for attempt in range(3):
                    try:
                        r = urequests.post(admin + '/wp-json/tmon-admin/v1/device/confirm-applied', headers=hdr, data=body, timeout=10)
                        if getattr(r, 'status_code', 0) == 200:
                            provisioning_log("apply_staged_settings: Confirm applied posted OK")
                            try: r.close()
                            except Exception: pass
                            break
                        provisioning_log("apply_staged_settings: confirm returned " + str(getattr(r,'status_code',0)))
                        try: r.close()
                        except Exception: pass
                    except Exception as e:
                        provisioning_log("apply_staged_settings: confirm POST exception " + str(e))
                        time.sleep(2)
        except Exception as e:
            provisioning_log("apply_staged_settings: confirmation attempt exception " + str(e))
        # clear staged file
        try:
            import os
            if os.path.exists(_settings.REMOTE_SETTINGS_STAGED_FILE):
                os.remove(_settings.REMOTE_SETTINGS_STAGED_FILE)
        except Exception:
            pass
        # Mark applied flag
        try:
            set_flag(_settings.REMOTE_SETTINGS_APPLIED_FILE, True)
        except Exception:
            pass
        # Soft reset
        try:
            import machine
            provisioning_log('apply_staged_settings: soft reset')
            machine.soft_reset()
        except Exception:
            pass
    except Exception as e:
        provisioning_log(f'apply_staged_settings: exception {e}')
        try:
            import uasyncio
            uasyncio.create_task(debug_print(f'apply_staged_settings: failed {e}', 'ERROR'))
        except Exception:
            pass

async def periodic_provision_check():
    """Periodically check TMON Admin endpoint for provisioning updates when not provisioned or a staged flag is set."""
    from settings import PROVISION_CHECK_INTERVAL_S, UNIT_PROVISIONED, REMOTE_SETTINGS_STAGED_FILE, UNIT_ID
    import ujson
    import os
    while True:
        try:
            staged_exists = False
            try:
                os.stat(REMOTE_SETTINGS_STAGED_FILE)
                staged_exists = True
            except Exception:
                staged_exists = False
            provisioning_log(f"periodic_provision_check: check (staged_exists={staged_exists}, provisioned={getattr(settings,'UNIT_PROVISIONED', False)})")
            if not getattr(settings, 'UNIT_PROVISIONED', False) or staged_exists:
                try:
                    payload = await fetch_admin_provisioning(get_machine_id(), getattr(settings, 'UNIT_ID', ''))
                    if payload:
                        provisioning_log(f"periodic_provision_check: received payload => {payload}")
                        try:
                            from config_persist import write_json
                            write_json(REMOTE_SETTINGS_STAGED_FILE, payload)
                            provisioning_log("periodic_provision_check: wrote REMOTE_SETTINGS_STAGED_FILE")
                        except Exception:
                            provisioning_log("periodic_provision_check: failed to write REMOTE_SETTINGS_STAGED_FILE")
                        apply_staged_settings_and_reboot(payload)
                        await asyncio.sleep(PROVISION_CHECK_INTERVAL_S)
                except Exception as e:
                    await debug_print(f'periodic_provision_check: {e}', 'ERROR')
                    provisioning_log(f"periodic_provision_check: exception {e}")
        except Exception as e:
            provisioning_log(f"periodic_provision_check: outer exception {e}")
        await asyncio.sleep(PROVISION_CHECK_INTERVAL_S or 30)

# New: provisioning & field-data start/registration helpers
_provision_task_handle = None
_field_data_task_handle = None

def start_provisioning_check(loop=None):
	"""Create provisioning check task if not already started."""
	global _provision_task_handle
	try:
		import uasyncio as _asyncio
		if _provision_task_handle:
			return _provision_task_handle
		try:
			_provision_task_handle = _asyncio.create_task(periodic_provision_check())
		except Exception:
			# older uasyncio variants may need a loop object
			if loop is None:
				loop = _asyncio.get_event_loop()
			_provision_task_handle = loop.create_task(periodic_provision_check())
		return _provision_task_handle
	except Exception:
		return None

def start_field_data_send(loop=None):
	"""Create background field-data sender task if not already started."""
	global _field_data_task_handle
	try:
		import uasyncio as _asyncio
		if _field_data_task_handle:
			return _field_data_task_handle
		try:
			_field_data_task_handle = _asyncio.create_task(periodic_field_data_send())
		except Exception:
			if loop is None:
				loop = _asyncio.get_event_loop()
			_field_data_task_handle = loop.create_task(periodic_field_data_send())
		return _field_data_task_handle
	except Exception:
		return None

def start_background_tasks(loop=None):
	"""Convenience wrapper to start useful background tasks at device boot."""
	start_provisioning_check(loop=loop)
	start_field_data_send(loop=loop)
	return True