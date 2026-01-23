# Firmware Version: v2.06.0

# NOTE: This restores the previously working utils.py behavior (as provided),
# and adds small compatibility aliases (free_pins_lora/free_pins_i2c) without changing logic.

import ujson
import uasyncio as asyncio
import os
import utime as time
import settings
import machine
import gc

from config_persist import write_text, read_json, set_flag, is_flag_set, write_json, read_text

# Persistent backlog file for unsent field data
FIELD_DATA_BACKLOG = settings.LOG_DIR + '/field_data_backlog.log'
UNIT_ID_FILE = settings.UNIT_ID_FILE if hasattr(settings, 'UNIT_ID_FILE') else (settings.LOG_DIR + '/unit_id.txt')
SUSPENDED_FLAG = getattr(settings, 'DEVICE_SUSPENDED_FILE', settings.LOG_DIR + '/suspended.flag')

ERROR_LOG_FILE = getattr(settings, 'ERROR_LOG_FILE', '/logs/lora_errors.log')
PROVISION_LOG_FILE = getattr(settings, 'LOG_DIR', '/logs') + '/provisioning.log'

# Log caps (non-field-data logs only)
_LOG_MAX_BYTES = int(getattr(settings, 'LOG_MAX_BYTES', 3 * 1024 * 1024))
_LOG_TRIM_KEEP_RATIO = 0.5

def _enforce_log_caps_before_write(path: str):
    try:
        if not path:
            return
        p = str(path)
        if 'field_data' in p.lower():
            return
        st = os.stat(p)
        size = st[6] if isinstance(st, (tuple, list)) else getattr(st, 'st_size', 0)
        if not size or size <= _LOG_MAX_BYTES:
            return
        keep = int(_LOG_MAX_BYTES * _LOG_TRIM_KEEP_RATIO)
        if keep < 256:
            keep = 256
        with open(p, 'rb') as f:
            try:
                f.seek(max(0, size - keep))
            except Exception:
                f.seek(0)
            tail = f.read()
        try:
            nl = tail.find(b'\n')
            if nl != -1 and nl + 1 < len(tail):
                tail = tail[nl + 1:]
        except Exception:
            pass
        with open(p, 'wb') as f:
            f.write(tail)
    except Exception:
        pass

def enforce_log_caps(path: str):
    try:
        _enforce_log_caps_before_write(path)
    except Exception:
        pass

def checkLogDirectory():
    """Create log directory (idempotent)."""
    try:
        from config_persist import ensure_dir
        ensure_dir(getattr(settings, 'LOG_DIR', '/logs'))
    except Exception:
        try:
            d = getattr(settings, 'LOG_DIR', '/logs')
            try:
                os.stat(d)
            except Exception:
                os.mkdir(d)
        except Exception:
            pass

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
            with open(settings.FIELD_DATA_LOG, 'r') as src, open(settings.DATA_HISTORY_LOG, 'a') as dst:
                for line in src:
                    dst.write(line)
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

def persist_wordpress_api_url(url):
    """Persist WORDPRESS_API_URL to file and sync wprest."""
    try:
        if not url:
            return
        path = getattr(settings, 'WORDPRESS_API_URL_FILE', settings.LOG_DIR + '/wordpress_api_url.txt')
        write_text(path, url.strip())
        settings.WORDPRESS_API_URL = url.strip()
        try:
            import wprest as _w
            _w.WORDPRESS_API_URL = settings.WORDPRESS_API_URL
        except Exception:
            pass
    except Exception:
        pass

def load_persisted_wordpress_api_url():
    """Load WORDPRESS_API_URL from persisted file and propagate to settings/wprest."""
    try:
        path = getattr(settings, 'WORDPRESS_API_URL_FILE', settings.LOG_DIR + '/wordpress_api_url.txt')
        try:
            val = read_text(path, None)
        except Exception:
            val = None
        if val:
            val = val.strip()
            if val:
                settings.WORDPRESS_API_URL = val
                try:
                    import wprest as _w
                    _w.WORDPRESS_API_URL = val
                except Exception:
                    pass
    except Exception:
        pass

def get_machine_id():
    try:
        try:
            import ubinascii as _ub
        except Exception:
            import binascii as _ub
        uid = machine.unique_id() if hasattr(machine, 'unique_id') else None
        if uid is None:
            return ''
        return _ub.hexlify(uid).decode('utf-8')
    except Exception:
        return ''

def get_unix_time():
    try:
        epoch_year = time.gmtime(0)[0] if hasattr(time, 'gmtime') else 1970
        t = int(time.time())
        if epoch_year >= 2000:
            return t + 946684800
        return t
    except Exception:
        return int(time.time())

async def debug_print(message, status):
    debug_flags = {
        # sensors/telemetry
        'TEMP': getattr(settings, 'DEBUG_TEMP', False),
        'BAR': getattr(settings, 'DEBUG_BAR', False),
        'HUMID': getattr(settings, 'DEBUG_HUMID', False),
        'BME280': getattr(settings, 'DEBUG_BME280', False),
        'DHT11': getattr(settings, 'DEBUG_DHT11', False),
        'SAMPLING': getattr(settings, 'DEBUG_SAMPLING', False),
        'SAMPLE_': getattr(settings, 'DEBUG_SAMPLING', False),  # matches SAMPLE_TEMP/HUMID/BAR...

        # connectivity / radio
        'LORA': getattr(settings, 'DEBUG_LORA', False),
        'LORA_RX': getattr(settings, 'DEBUG_LORA', False),
        'LORA_TX': getattr(settings, 'DEBUG_LORA', False),
        'WIFI': getattr(settings, 'DEBUG_WIFI_CONNECT', False),
        'WIFI_CONNECT': getattr(settings, 'DEBUG_WIFI_CONNECT', False),

        # system subsystems
        'OTA': getattr(settings, 'DEBUG_OTA', False),
        'PROVISION': getattr(settings, 'DEBUG_PROVISION', False),
        'DISPLAY': getattr(settings, 'DEBUG_DISPLAY', False),
        'WPREST': getattr(settings, 'DEBUG_WPREST', False),
        'FIELD_DATA': getattr(settings, 'DEBUG_FIELD_DATA', False),
        'RS485': getattr(settings, 'DEBUG_RS485', False),

        # node roles
        'BASE_NODE': getattr(settings, 'DEBUG_BASE_NODE', False),
        'REMOTE_NODE': getattr(settings, 'DEBUG_REMOTE_NODE', False),
        'WIFI_NODE': getattr(settings, 'DEBUG_WIFI_NODE', False),
        
        # Info, Error, and Warning
        'INFO': getattr(settings, 'DEBUG', False),
        'WARN': getattr(settings, 'DEBUG', False),
        'ERROR': getattr(settings, 'DEBUG', False),
    }
    should_print = bool(getattr(settings, 'DEBUG', False))
    for key, enabled in debug_flags.items():
        if key in str(status) and enabled:
            should_print = True
    if should_print:
        try:
            safe_msg = message
            if isinstance(safe_msg, bytes):
                safe_msg = safe_msg.decode('utf-8', 'ignore')
            safe_msg = ''.join(ch if 32 <= ord(ch) <= 126 else ' ' for ch in str(safe_msg))
        except Exception:
            safe_msg = '<unprintable>'
        try:
            unixt = get_unix_time()
            ts = time.localtime(unixt) if hasattr(time, 'localtime') else None
            if ts:
                timestamp = f"{ts[0]:04}-{ts[1]:02}-{ts[2]:02} {ts[3]:02}:{ts[4]:02}:{ts[5]:02}"
            else:
                timestamp = str(unixt)
        except Exception:
            timestamp = '0'
        print(f"[{timestamp}] [{status}] {safe_msg}")
    await asyncio.sleep(0)

    
# --- LED support (restored) ---
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
    'black': (0, 0, 0),
    'light_blue': (173, 216, 230),  # Light blue (sky-like)
    'dark_blue': (0, 0, 139),      # Dark blue (close to navy but deeper)
    'light_green': (144, 238, 144),  # Light green
    'dark_green': (0, 100, 0),     # Dark green (forest)
    'light_yellow': (255, 255, 224),  # Light yellow (lemon chiffon)
    'dark_red': (139, 0, 0),       # Dark red (crimson-like)
    'indigo': (75, 0, 130),        # Indigo
    'violet': (238, 130, 238),     # Violet
    'turquoise': (64, 224, 208),   # Turquoise
    'gold': (255, 215, 0),         # Gold
    'silver': (192, 192, 192),     # Silver (light gray)
    'coral': (255, 127, 80),       # Coral
    'salmon': (250, 128, 114),     # Salmon
    'khaki': (240, 230, 140),      # Khaki
    'sienna': (160, 82, 45),       # Sienna (earthy brown)
    'chocolate': (210, 105, 30),   # Chocolate brown
    'tan': (210, 180, 140),        # Tan
    'plum': (221, 160, 221),       # Plum (light purple)
    'orchid': (218, 112, 214),     # Orchid
    'azure': (240, 255, 255),      # Azure (light cyan)
    'mint': (189, 252, 201),       # Mint green
    'chartreuse': (127, 255, 0),   # Chartreuse (alternative to your lime)
    'fuchsia': (255, 0, 255),      # Fuchsia (same as magenta, but added for completeness)
    'crimson': (220, 20, 60),      # Crimson
    'aqua': (0, 255, 255),         # Aqua (same as cyan)
    'sky_blue': (135, 206, 235),   # Sky blue
    'forest_green': (34, 139, 34), # Forest green
    'dark_orange': (255, 140, 0),  # Dark orange
    'hot_pink': (255, 105, 180),   # Hot pink
    'dark_purple': (148, 0, 211),  # Dark violet/purple
    'light_grey': (211, 211, 211), # Light gray
    'dark_grey': (169, 169, 169),  # Dark gray
    'ivory': (255, 255, 240),      # Ivory (off-white)
    'snow': (255, 250, 250)        # Snow (another off-white)
}

led_lock = asyncio.Lock()

def set_color(rgb_led, color):
    try:
        rgb_led[0] = color
        rgb_led.write()
    except Exception:
        pass

async def flash_led(num_flashes, interval, lightColor, pattern):
    from neopixel import NeoPixel
    from machine import Pin
    duty_cycle = color_to_duty.get(str(lightColor).lower())
    if duty_cycle is None:
        return
    rgb_led_pin = Pin(settings.LED_PIN, Pin.OUT)
    rgb_led = NeoPixel(rgb_led_pin, 1)
    await asyncio.sleep(0.1)
    async with led_lock:
        try:
            if pattern == "on":
                set_color(rgb_led, duty_cycle)
                await asyncio.sleep(0.1)
                return
            elif pattern in ("off", "clear"):
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
                for _ in range(num_flashes):
                    set_color(rgb_led, duty_cycle)
                    await asyncio.sleep(flash_interval)
                    set_color(rgb_led, (0, 0, 0))
                    await asyncio.sleep(interval)
            set_color(rgb_led, (0, 0, 0))
            await asyncio.sleep(0.1)
        finally:
            try:
                rgb_led_pin.init(Pin.IN)
            except Exception:
                pass

def led_status_flash(status):
    import uasyncio as _a
    color_map = {
        'INFO': 'light_green',
        'SUCCESS': 'green',
        'OK': 'lime',
        'WARN': 'light_yellow',
        'WARNING': 'orange',
        'ERROR': 'red',
        'WIFI': 'blue',
        'REMOTE_NODE': 'purple',
        'BASE_NODE': 'lavender',
        'WIFI_NODE': 'indigo',
        'LORA_RX': 'violet',
        'LORA_TX': 'teal',
        'SAMPLE_TEMP': 'magenta',
        'SAMPLE_HUMID': 'cyan',
        'SAMPLE_BAR': 'sky_blue',
        'RELAY_1_ON': 'turquoise',
        'RELAY_2_ON': 'gold',
        'RELAY_3_ON': 'coral',
        'RELAY_4_ON': 'salmon',
        'RELAY_5_ON': 'khaki',
        'RELAY_6_ON': 'sienna',
        'RELAY_7_ON': 'chocolate',
        'RELAY_8_ON': 'tan',
        'RELAY_1_OFF': 'plum',
        'RELAY_2_OFF': 'orchid',
        'RELAY_3_OFF': 'azure',
        'RELAY_4_OFF': 'mint',
        'RELAY_5_OFF': 'chartreuse',
        'RELAY_6_OFF': 'crimson',
        'RELAY_7_OFF': 'dark_orange',
        'RELAY_8_OFF': 'hot_pink',
        'RS485_TX': 'dark_purple',
        'RS485_RX': 'light_blue',
        'WPREST': 'dark_blue'
    }
    color = color_map.get(status, 'white')
    try:
        _a.create_task(flash_led(1, 0.2, color, 'short'))
    except Exception:
        pass
    

# --- error + lora logs (restored) ---
async def log_error(error_msg, context=None):
    try:
        ts = time.localtime()
        timestamp = f"{ts[0]:04}-{ts[1]:02}-{ts[2]:02} {ts[3]:02}:{ts[4]:02}:{ts[5]:02}"
        entry = {'timestamp': timestamp, 'error': error_msg, 'context': context}
        try:
            os.stat(settings.LOG_DIR)
        except OSError:
            os.mkdir(settings.LOG_DIR)
        _enforce_log_caps_before_write(ERROR_LOG_FILE)
        with open(ERROR_LOG_FILE, 'a') as f:
            f.write(ujson.dumps(entry) + '\n')
        if getattr(settings, 'DEBUG', False):
            print(f"[ERROR] {timestamp}: {error_msg} | {context}")
    except Exception as e:
        print(f"[FATAL] Failed to log error: {e}")
    await asyncio.sleep(0)

def write_lora_log(message, level='INFO'):
    try:
        ts = time.localtime()
        timestamp = f"{ts[0]:04}-{ts[1]:02}-{ts[2]:02} {ts[3]:02}:{ts[4]:02}:{ts[5]:02}"
        entry = {'timestamp': timestamp, 'level': level, 'message': message}
        try:
            os.stat(settings.LOG_DIR)
        except OSError:
            os.mkdir(settings.LOG_DIR)
        _enforce_log_caps_before_write(settings.LOG_FILE)
        with open(settings.LOG_FILE, 'a') as f:
            f.write(ujson.dumps(entry) + '\n')
    except Exception as e:
        try:
            print(f"[LOGBACKUP] {level}: {message} ({e})")
        except Exception:
            pass

def provisioning_log(msg):
    try:
        ts = time.localtime()
        timestamp = f"{ts[0]:04}-{ts[1]:02}-{ts[2]:02} {ts[3]:02}:{ts[4]:02}:{ts[5]:02}"
        entry = f"[{timestamp}] {msg}"
        print("[PROVISION] " + entry)
        try:
            checkLogDirectory()
            _enforce_log_caps_before_write(PROVISION_LOG_FILE)
            with open(PROVISION_LOG_FILE, 'a') as f:
                f.write(entry + '\n')
        except Exception:
            pass
    except Exception:
        pass

# --- node type persistence (restored) ---
NODE_TYPE_FILE = getattr(settings, 'NODE_TYPE_FILE', settings.LOG_DIR + '/node_type.txt')

def persist_node_type(role: str):
    try:
        if not role:
            return
        checkLogDirectory()
        write_text(NODE_TYPE_FILE, str(role).strip())
        try:
            import settings as _s
            _s.NODE_TYPE = str(role).strip()
        except Exception:
            pass
        try:
            if str(role).strip().lower() == 'remote':
                try:
                    from wifi import disable_wifi
                    disable_wifi()
                except Exception:
                    pass
                try:
                    import settings as _s2
                    _s2.ENABLE_WIFI = False
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass

def load_persisted_node_type():
    try:
        checkLogDirectory()
        val = read_text(NODE_TYPE_FILE, None)
        if not val:
            return None
        val = val.strip()
        return val if val else None
    except Exception:
        return None

# --- unit name persistence (restored) ---
def persist_unit_name(unit_name: str):
    try:
        if not unit_name:
            return
        checkLogDirectory()
        path = getattr(settings, 'UNIT_NAME_FILE', settings.LOG_DIR + '/unit_name.txt')
        try:
            prev = read_text(path, None)
        except Exception:
            prev = None
        write_text(path, str(unit_name).strip())
        try:
            import settings as _s
            _s.UNIT_Name = str(unit_name).strip()
        except Exception:
            pass
        try:
            if not prev or not str(prev).strip():
                try:
                    import uasyncio as _a
                    from oled import display_message
                    try:
                        _a.create_task(display_message("Unit: " + str(unit_name).strip(), 2))
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass

def load_persisted_unit_name():
    try:
        checkLogDirectory()
        path = getattr(settings, 'UNIT_NAME_FILE', settings.LOG_DIR + '/unit_name.txt')
        try:
            val = read_text(path, None)
        except Exception:
            val = None
        if val:
            val = val.strip()
            if val:
                try:
                    settings.UNIT_Name = val
                except Exception:
                    pass
                return val
        return None
    except Exception:
        return None

try:
    load_persisted_unit_name()
except Exception:
    pass

# --- voltage (restored) ---
def update_sys_voltage():
    import sdata
    try:
        adc = machine.ADC(machine.Pin(settings.SYS_VOLTAGE_PIN))
        raw = adc.read_u16()
        voltage = (raw / 65535) * settings.SYS_VOLTAGE_MAX
        sdata.sys_voltage = voltage
        return voltage
    except Exception:
        try:
            sdata.sys_voltage = 0
        except Exception:
            pass
        return 0

# --- free pins + GC (restored) ---
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
    await asyncio.sleep(0)

# Compatibility aliases used elsewhere in the repo
async def free_pins_lora():
    await free_pins()

async def free_pins_i2c():
    try:
        machine.Pin(settings.I2C_A_SCL_PIN, machine.Pin.IN)
        machine.Pin(settings.I2C_A_SDA_PIN, machine.Pin.IN)
    except Exception:
        pass
    await asyncio.sleep(0)

async def runGC():
    gc.enable()
    try:
        unreachable_objects = gc.collect()
        print(f"Unreachable objects collected: {unreachable_objects}")
        used_memory = gc.mem_alloc()
        total_memory = used_memory + gc.mem_free()
        avail_memory = total_memory - used_memory
        print(f"Memory used (RAM): {used_memory} bytes / Total available: {total_memory} bytes | Bytes Remaining - {avail_memory} bytes")
    except MemoryError:
        print("MemoryError: Failed to allocate memory during garbage collection")
        gc.collect()
        print("Garbage collection completed after MemoryError")
    await asyncio.sleep(0)

# Optional throttled GC helper (does not change behavior unless called by other modules)
_last_gc_ms = 0
def maybe_gc(reason: str = None, min_interval_ms: int = 8000, mem_free_below: int = None):
    global _last_gc_ms
    try:
        do = False
        if mem_free_below is not None:
            try:
                if gc.mem_free() < int(mem_free_below):
                    do = True
            except Exception:
                pass
        try:
            now = time.ticks_ms()
            if time.ticks_diff(now, _last_gc_ms) >= int(min_interval_ms):
                do = True
                _last_gc_ms = now
        except Exception:
            do = True
        if do:
            gc.collect()
    except Exception:
        pass

async def safe_run(coro, context=None):
    try:
        await coro
    except Exception as e:
        await log_error(str(e), context)

class TMONAI:
    def __init__(self):
        self.error_count = 0
        self.last_error = None
        self.recovery_actions = []

    async def observe_error(self, error_msg, context=None):
        self.error_count += 1
        self.last_error = (error_msg, context)
        if self.error_count > 5:
            await log_error('AI: Too many errors, attempting system recovery', context)
            await self.recover_system()

    async def recover_system(self):
        try:
            await log_error('AI: Performing soft reset', 'recovery')
            machine.soft_reset()
        except Exception as e:
            await log_error(f'AI: Recovery failed: {e}', 'recovery')

    async def suggest_action(self, context):
        if 'wifi' in str(context).lower():
            return 'Check WiFi credentials or signal.'
        if 'ota' in str(context).lower():
            return 'Retry OTA or check file integrity.'
        return 'Check device logs and power cycle if needed.'

TMON_AI = TMONAI()

# --- field data record + sender (restored) ---
def record_field_data():
    """Append a minimal telemetry record for the device."""
    import sdata
    entry = {'timestamp': int(get_unix_time())}
    try:
        ts = time.localtime()
        entry['ts_iso'] = f"{ts[0]:04}-{ts[1]:02}-{ts[2]:02} {ts[3]:02}:{ts[4]:02}:{ts[5]:02}"
    except Exception:
        pass

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

    # Engine
    _copy(entry, sdata, 'engine1_speed_rpm')
    _copy(entry, sdata, 'engine2_speed_rpm')
    _copy(entry, sdata, 'engine1_batt_v')
    _copy(entry, sdata, 'engine2_batt_v')
    _copy(entry, sdata, 'engine_last_poll_ts')

    for i in range(1, 9):
        try:
            val = getattr(sdata, f'relay{i}_runtime_s')
            if val:
                entry[f'relay{i}_runtime_s'] = val
            on_state = getattr(sdata, f'relay{i}_on')
            if on_state:
                entry[f'relay{i}_on'] = 1
        except Exception:
            pass

    # GPS mirrors
    _copy(entry, sdata, 'gps_lat')
    _copy(entry, sdata, 'gps_lng')
    _copy(entry, sdata, 'gps_alt_m')
    _copy(entry, sdata, 'gps_accuracy_m')
    _copy(entry, sdata, 'gps_last_fix_ts')

    entry['unit_id'] = getattr(settings, 'UNIT_ID', '')
    entry['firmware_version'] = getattr(settings, 'FIRMWARE_VERSION', '')
    entry['NODE_TYPE'] = getattr(settings, 'NODE_TYPE', '')

    if getattr(settings, 'NODE_TYPE', 'base') == 'remote':
        return

    checkLogDirectory()
    try:
        with open(settings.FIELD_DATA_LOG, 'a') as f:
            f.write(ujson.dumps(entry) + '\n')
        gc.collect()
    except Exception as e:
        print(f"Error recording field data: {e}")

async def send_field_data_log():
    """Send field_data.log to WordPress and rotate on confirmation."""
    try:
        load_persisted_wordpress_api_url()
        import wprest as _w
        if getattr(settings, 'WORDPRESS_API_URL', '') and not getattr(_w, 'WORDPRESS_API_URL', ''):
            _w.WORDPRESS_API_URL = settings.WORDPRESS_API_URL
    except Exception:
        pass

    if getattr(settings, 'NODE_TYPE', 'base') == 'remote':
        return

    from wprest import WORDPRESS_API_URL as _wp_mod
    local_url = getattr(settings, 'WORDPRESS_API_URL', '') or _wp_mod
    if not local_url:
        await debug_print('sfd: no WP url', 'ERROR')
        return
    WORDPRESS_API_URL = local_url

    checkLogDirectory()
    try:
        try:
            os.stat(settings.FIELD_DATA_LOG)
        except OSError:
            with open(settings.FIELD_DATA_LOG, 'w') as f:
                f.write('')
            await debug_print('sfd: created empty field log', 'DEBUG')
    except Exception as e:
        await debug_print(f'send_field_data_log: Exception checking/creating FIELD_DATA_LOG: {e}', 'ERROR')
        return

    max_retries = 5
    try:
        if _send_field_data_lock.locked():
            await debug_print('send_field_data_log: another send in progress, skipping this cycle', 'DEBUG')
            return

        async with _send_field_data_lock:
            await debug_print('sfd: reading log', 'DEBUG')
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

            await debug_print(f'sfd: read {total_lines} lines, {len(payloads)} batches', 'DEBUG')

            backlog = read_backlog()
            await debug_print(f'sfd: backlog {len(backlog)}', 'DEBUG')
            payloads = backlog + payloads
            backlog_count = len(backlog)

            if not payloads:
                await debug_print('sfd: no payloads', 'DEBUG')
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
                            import ubinascii as _ub2
                        except Exception:
                            import binascii as _ub2
                        try:
                            return _ub2.hexlify(obj).decode('ascii')
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
                try:
                    payload['firmware_version'] = getattr(settings, 'FIRMWARE_VERSION', '')
                except Exception:
                    pass
                try:
                    payload['node_type'] = getattr(settings, 'NODE_TYPE', '')
                except Exception:
                    pass

                delivered = False
                await debug_print(f'sfd: send {idx+1}/{len(payloads)}', 'DEBUG')

                for attempt in range(1, max_retries + 1):
                    try:
                        gc.collect()
                    except Exception:
                        pass
                    try:
                        headers = {'Content-Type': 'application/json; charset=utf-8'}
                        await debug_print(f'sfd: POST att{attempt} to WP', 'DEBUG')
                        safe_payload = _sanitize_json(payload)
                        try:
                            encoded = ujson.dumps(safe_payload)
                        except Exception:
                            minimal = {'unit_id': settings.UNIT_ID, 'data': []}
                            if isinstance(payload, dict) and 'data' in payload:
                                minimal['data'] = _sanitize_json(payload['data'])
                            encoded = ujson.dumps(minimal)

                        resp = requests.post(
                            WORDPRESS_API_URL + '/wp-json/tmon/v1/device/field-data',
                            headers=headers,
                            data=encoded,
                            timeout=10
                        )
                        try:
                            await debug_print(f'sfd: resp {resp.status_code}', 'DEBUG')
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
                                    except Exception:
                                        resp_json = {}
                                except Exception:
                                    pass
                            ok_resp = (resp.status_code == 200) and ((resp_json.get('status') == 'ok') or (resp_bytes == b'OK'))
                            if ok_resp:
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
                                await debug_print(f'sfd: payload {idx+1} ok', 'DEBUG')
                                try:
                                    from oled import display_message
                                    await display_message("Field Data Sent", 1.5)
                                except Exception:
                                    pass
                                break
                            else:
                                await log_error(f'sfd: delivery fail att{attempt} {resp.status_code}', 'field_data')
                        finally:
                            try:
                                resp.close()
                            except Exception:
                                pass
                    except Exception as e:
                        await debug_print(f'sfd: delivery exc att{attempt}: {type(e).__name__}: {e}', 'ERROR')
                        await log_error(f'Field data log delivery exception (attempt {attempt}): {type(e).__name__}: {e}', 'field_data')
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)

                if delivered:
                    sent_indices.append(idx)
                else:
                    await debug_print(f'sfd: payload {idx+1} failed after max', 'ERROR')
                    await log_error('Field data log delivery failed after max retries, will try again later.', 'field_data')

            if total_lines:
                current_indices = range(backlog_count, len(payloads))
                delivered_current_all = all(i in sent_indices for i in current_indices) if len(payloads) > backlog_count else False
                if delivered_current_all:
                    await debug_print('sfd: rotate field log', 'DEBUG')
                    rotate_field_data_log()

            unsent = [payloads[i] for i in range(len(payloads)) if i not in sent_indices]
            if unsent:
                await debug_print(f'sfd: backlog write {len(unsent)}', 'DEBUG')
                clear_backlog()
                for p in unsent:
                    append_to_backlog(p)
            else:
                await debug_print('sfd: all delivered, clear backlog', 'DEBUG')
                clear_backlog()
    except Exception as e:
        await debug_print(f'sfd: exception {type(e).__name__}: {e}', 'ERROR')
        await log_error(f'sfd: failed send: {type(e).__name__}: {e}', 'field_data')

async def periodic_field_data_send():
    while True:
        await send_field_data_log()
        await asyncio.sleep(settings.FIELD_DATA_SEND_INTERVAL)

# --- provisioning loop (restored, single definition) ---
_provision_reboot_guard_written = False

async def periodic_provision_check():
    global _provision_reboot_guard_written
    import uasyncio as _a
    interval = int(getattr(settings, 'PROVISION_CHECK_INTERVAL_S', 25))
    timeout_s = int(getattr(settings, 'PROVISION_CHECK_TIMEOUT_S', 8))
    hub = getattr(settings, 'TMON_ADMIN_API_URL', '')
    flag_file = getattr(settings, 'PROVISIONED_FLAG_FILE', settings.LOG_DIR + '/provisioned.flag')
    guard_file = getattr(settings, 'PROVISION_REBOOT_GUARD_FILE', settings.LOG_DIR + '/provision_reboot.flag')

    while True:
        try:
            try:
                flag_exists = False
                try:
                    os.stat(flag_file)
                    flag_exists = True
                except OSError:
                    flag_exists = False
                wp_url_set = bool(str(getattr(settings, 'WORDPRESS_API_URL', '')).strip())
                uid_set = bool(str(getattr(settings, 'UNIT_ID', '')).strip())
                if hub and flag_file and flag_exists and wp_url_set and uid_set:
                    await debug_print('prov: provisioned', 'PROVISION')
                    try:
                        settings.UNIT_PROVISIONED = True
                    except Exception:
                        pass
                    return
            except Exception:
                pass

            if not hub:
                await debug_print('prov: no hub', 'PROVISION')
            else:
                try:
                    import urequests as _r
                except Exception:
                    _r = None

                resp = None
                if _r:
                    try:
                        import usocket as _sock
                        _sock.setdefaulttimeout(timeout_s)
                    except Exception:
                        pass
                    mid = get_machine_id()
                    uid = getattr(settings, 'UNIT_ID', None)
                    body = {'machine_id': mid}
                    if uid:
                        body['unit_id'] = uid

                    await _a.sleep(0)
                    try:
                        resp = _r.post(hub.rstrip('/') + '/wp-json/tmon-admin/v1/device/check-in', json=body, timeout=10)
                    except TypeError:
                        resp = _r.post(hub.rstrip('/') + '/wp-json/tmon-admin/v1/device/check-in', json=body)

                    status = getattr(resp, 'status_code', 0)
                    if status == 200:
                        try:
                            resp_json = resp.json()
                        except Exception:
                            resp_json = {}

                        staged = bool(resp_json.get('staged_exists'))
                        provisioned = bool(resp_json.get('provisioned'))
                        await debug_print(f'prov: check staged={staged} prov={provisioned}', 'PROVISION')

                        new_uid = resp_json.get('unit_id')
                        if new_uid and str(new_uid).strip():
                            if str(new_uid).strip() != str(getattr(settings, 'UNIT_ID', '')):
                                settings.UNIT_ID = str(new_uid).strip()
                                try:
                                    persist_unit_id(settings.UNIT_ID)
                                except Exception:
                                    pass

                        site_val = (resp_json.get('site_url') or resp_json.get('wordpress_api_url') or '').strip()
                        if site_val:
                            persist_wordpress_api_url(site_val)

                        unit_name = (resp_json.get('unit_name') or '').strip()
                        role_val = (resp_json.get('role') or '').strip()
                        plan_val = (resp_json.get('plan') or '').strip()
                        fw_ver = (resp_json.get('firmware') or '').strip()

                        if unit_name:
                            try:
                                settings.UNIT_Name = unit_name
                            except Exception:
                                pass
                            try:
                                persist_unit_name(unit_name)  # ensure UNIT_Name.txt is written (remotes too)
                            except Exception:
                                pass
                        if role_val:
                            try:
                                settings.NODE_TYPE = role_val
                            except Exception:
                                pass
                            try:
                                persist_node_type(role_val)
                            except Exception:
                                pass
                        if plan_val:
                            try:
                                settings.PLAN = plan_val
                            except Exception:
                                pass
                        if fw_ver:
                            try:
                                settings.FIRMWARE_VERSION = fw_ver
                            except Exception:
                                pass

                        if (provisioned or staged) and site_val:
                            try:
                                with open(flag_file, 'w') as f:
                                    f.write('ok')
                            except Exception:
                                pass
                            try:
                                settings.UNIT_PROVISIONED = True
                            except Exception:
                                pass
                            if not _provision_reboot_guard_written:
                                reboot_needed = True
                                try:
                                    os.stat(guard_file)
                                    reboot_needed = False
                                except OSError:
                                    reboot_needed = True
                                if reboot_needed:
                                    try:
                                        with open(guard_file, 'w') as gf:
                                            gf.write('1')
                                    except Exception:
                                        pass
                                    await debug_print('prov: applied -> soft reset', 'PROVISION')
                                    _provision_reboot_guard_written = True
                                    try:
                                        machine.soft_reset()
                                    except Exception:
                                        pass
                    else:
                        await debug_print('prov: no requests', 'PROVISION')

                    try:
                        if resp:
                            resp.close()
                    except Exception:
                        pass
        except Exception as e:
            try:
                await debug_print(f'prov: error {e}', 'ERROR')
            except Exception:
                pass

        await _a.sleep(interval)

def compute_bars(rssi, cuts=None):
    try:
        if rssi is None:
            return 0
        if cuts is None:
            cuts = getattr(settings, 'WIFI_RSSI_CUTS', (-60, -80, -90))
        if not isinstance(cuts, (list, tuple)):
            cuts = tuple(cuts)
        try:
            r = int(rssi)
        except Exception:
            return 0
        if r > cuts[0]:
            return 3
        if r > cuts[1]:
            return 2
        if r > cuts[2]:
            return 1
    except Exception:
        pass
    return 0

def is_http_allowed_for_node():
    try:
        if getattr(settings, 'NODE_TYPE', '').lower() == 'remote':
            if getattr(settings, 'UNIT_PROVISIONED', False):
                return False
            try:
                flag = getattr(settings, 'PROVISIONED_FLAG_FILE', settings.LOG_DIR + '/provisioned.flag')
                try:
                    os.stat(flag)
                    return False
                except Exception:
                    pass
            except Exception:
                pass
        return True
    except Exception:
        return True

def start_background_tasks():
    try:
        import uasyncio as _a
        if not hasattr(settings, '_BG_TASKS_STARTED'):
            settings._BG_TASKS_STARTED = True
            try:
                _a.create_task(periodic_provision_check())
            except Exception:
                pass
            try:
                wp_url = str(getattr(settings, 'WORDPRESS_API_URL', '')).strip()
                role = str(getattr(settings, 'NODE_TYPE', 'base')).lower()
                if wp_url and role in ('base', 'wifi'):
                    _a.create_task(periodic_field_data_send())
            except Exception:
                pass
    except Exception:
        pass

__all__ = [
    'debug_print',
    'free_pins',
    'free_pins_lora',
    'free_pins_i2c',
    'persist_unit_id',
    'load_persisted_unit_id',
    'persist_wordpress_api_url',
    'load_persisted_wordpress_api_url',
    'periodic_field_data_send',
    'periodic_provision_check',
    'get_machine_id',
    'start_background_tasks',
    'persist_node_type',
    'load_persisted_node_type',
    'persist_unit_name',
    'load_persisted_unit_name',
    'send_field_data_log',
    'record_field_data',
    'update_sys_voltage',
    'runGC',
    'write_lora_log',
    'log_error',
    'TMON_AI',
    'compute_bars',
    'is_http_allowed_for_node',
]

