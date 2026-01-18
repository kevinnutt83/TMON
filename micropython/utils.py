"""
TMON MicroPython utilities: logging, persistence, GC/log maintenance, telemetry recording,
LED helpers, and misc glue used across the firmware.
"""

try:
    import ujson as json
except Exception:
    import json  # type: ignore

try:
    import uasyncio as asyncio
except Exception:
    asyncio = None

try:
    import utime as time
except Exception:
    import time  # type: ignore

import os

try:
    import gc
except Exception:
    gc = None

import settings

# --- Simple AI/health placeholder used by lora/main ---
class _AIState:
    error_count = 0
    last_error = ''

TMON_AI = _AIState()

def _gc_collect():
    try:
        if gc:
            gc.collect()
    except Exception:
        pass

def checkLogDirectory():
    try:
        d = getattr(settings, 'LOG_DIR', '/logs')
        try:
            os.stat(d)
        except Exception:
            try:
                os.mkdir(d)
            except Exception:
                pass
    except Exception:
        pass

# --- Debug print (console + optional OLED banner) ---
async def debug_print(message, category="INFO"):
    try:
        if getattr(settings, 'DEBUG', False) or category in ("ERROR", "WARN"):
            try:
                print(f"[{category}] {message}")
            except Exception:
                pass
        # Optional OLED status banner
        try:
            if bool(getattr(settings, 'ENABLE_OLED', False)) and bool(getattr(settings, 'OLED_DEBUG_BANNER', False)):
                from oled import set_status_banner
                set_status_banner(str(message)[:16], duration_s=3, persist=False)
        except Exception:
            pass
    finally:
        _gc_collect()

def safe_run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception:
        return None

# --- Pins/LED helpers ---
async def free_pins():
    # Best-effort placeholder: many ports/drivers manage pin state internally.
    await asyncio.sleep(0) if asyncio else None

def flash_led(pin_num=None, times=1, delay_ms=80):
    try:
        import machine
        p = machine.Pin(pin_num if pin_num is not None else getattr(settings, 'STATUS_LED_PIN', 25), machine.Pin.OUT)
        for _ in range(int(times)):
            p.value(1)
            time.sleep_ms(int(delay_ms))
            p.value(0)
            time.sleep_ms(int(delay_ms))
    except Exception:
        pass

def led_status_flash(kind='INFO'):
    # Map logical names to blink patterns; keep cheap.
    try:
        m = {
            'INFO': (1, 40),
            'SUCCESS': (2, 40),
            'WARN': (3, 30),
            'ERROR': (5, 25),
            'SAMPLE_TEMP': (1, 20),
            'SAMPLE_BAR': (1, 20),
        }
        t, d = m.get(str(kind).upper(), (1, 40))
        flash_led(times=t, delay_ms=d)
    except Exception:
        pass

# --- Voltage helpers (best-effort) ---
def update_sys_voltage():
    try:
        # If hardware ADC wiring differs, this remains a placeholder.
        import machine
        adc = machine.ADC(getattr(settings, 'VBAT_ADC_PIN', 26))
        raw = adc.read_u16()
        vref = float(getattr(settings, 'ADC_VREF', 3.3))
        # Basic scale; adjust via settings.VBAT_DIVIDER if used.
        v = (raw / 65535.0) * vref * float(getattr(settings, 'VBAT_DIVIDER', 2.0))
        try:
            import sdata
            sdata.sys_voltage = v
        except Exception:
            pass
        return v
    except Exception:
        return 0.0

# --- Persistence helpers ---
def get_machine_id():
    try:
        import machine
        mid = getattr(machine, 'unique_id', None)
        if callable(mid):
            try:
                import ubinascii
                return ubinascii.hexlify(machine.unique_id()).decode()
            except Exception:
                return str(machine.unique_id())
    except Exception:
        pass
    return None

def persist_unit_id(unit_id: str):
    try:
        p = getattr(settings, 'UNIT_ID_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/unit_id.txt')
        checkLogDirectory()
        with open(p, 'w') as f:
            f.write(str(unit_id))
    except Exception:
        pass
    finally:
        _gc_collect()

def load_persisted_unit_id():
    try:
        p = getattr(settings, 'UNIT_ID_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/unit_id.txt')
        with open(p, 'r') as f:
            return (f.read() or '').strip() or None
    except Exception:
        return None

def persist_unit_name(name: str):
    try:
        p = getattr(settings, 'UNIT_NAME_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/unit_name.txt')
        checkLogDirectory()
        with open(p, 'w') as f:
            f.write(str(name))
    except Exception:
        pass
    finally:
        _gc_collect()

def persist_node_type(node_type: str):
    try:
        p = getattr(settings, 'NODE_TYPE_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/node_type.txt')
        checkLogDirectory()
        with open(p, 'w') as f:
            f.write(str(node_type))
    except Exception:
        pass
    finally:
        _gc_collect()

def load_persisted_node_type():
    try:
        p = getattr(settings, 'NODE_TYPE_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/node_type.txt')
        with open(p, 'r') as f:
            return (f.read() or '').strip() or None
    except Exception:
        return None

def persist_wordpress_api_url(url: str):
    try:
        p = getattr(settings, 'WORDPRESS_API_URL_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/wordpress_api_url.txt')
        checkLogDirectory()
        with open(p, 'w') as f:
            f.write(str(url))
    except Exception:
        pass
    finally:
        _gc_collect()

def load_persisted_wordpress_api_url():
    try:
        p = getattr(settings, 'WORDPRESS_API_URL_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/wordpress_api_url.txt')
        with open(p, 'r') as f:
            val = (f.read() or '').strip()
        if val:
            try:
                settings.WORDPRESS_API_URL = val
            except Exception:
                pass
        return val or None
    except Exception:
        return None

def persist_suspension_state(suspended: bool):
    try:
        p = getattr(settings, 'SUSPENDED_FLAG_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/suspended.flag')
        checkLogDirectory()
        if suspended:
            with open(p, 'w') as f:
                f.write('1')
        else:
            try:
                os.remove(p)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        _gc_collect()

# --- Log maintenance (exclude FIELD_DATA_LOG explicitly) ---
def check_log_size(file_path, max_bytes=512000):
    try:
        if not file_path:
            return
        st = os.stat(file_path)
        size = st[6]
        if size <= int(max_bytes):
            return
        # Keep last half of max_bytes to reduce memory footprint
        keep = int(max_bytes // 2)
        buf = bytearray()
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(512)
                if not chunk:
                    break
                buf += chunk
                if len(buf) > keep:
                    buf = buf[-keep:]
        with open(file_path, 'wb') as f:
            f.write(buf)
    except Exception:
        pass
    finally:
        _gc_collect()

async def runGC():
    try:
        _gc_collect()
        # Do not rotate FIELD_DATA_LOG (per markup)
        files = []
        try:
            files = [
                getattr(settings, 'LOG_FILE', None),
                getattr(settings, 'ERROR_LOG_FILE', None),
                getattr(settings, 'FIELD_DATA_DELIVERED_LOG', None),
                getattr(settings, 'DATA_HISTORY_LOG', None),
            ]
        except Exception:
            files = []
        for fp in files:
            try:
                if fp:
                    check_log_size(fp)
            except Exception:
                pass
    finally:
        _gc_collect()
    if asyncio:
        await asyncio.sleep(0)

# --- Field data recording + upload helpers ---
def _field_data_path():
    return getattr(settings, 'FIELD_DATA_LOG', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/field_data.log')

def record_field_data():
    """Append one JSON line to FIELD_DATA_LOG for ALL node types (including remotes)."""
    try:
        checkLogDirectory()
        try:
            import sdata
        except Exception:
            sdata = None
        payload = {
            'ts': int(time.time()),
            'unit_id': getattr(settings, 'UNIT_ID', ''),
            'unit_name': getattr(settings, 'UNIT_Name', ''),
            'node_type': getattr(settings, 'NODE_TYPE', ''),
        }
        if sdata:
            # Keep it small; the uploader can send full sdata elsewhere
            payload.update({
                't_f': getattr(sdata, 'cur_temp_f', 0),
                'hum': getattr(sdata, 'cur_humid', 0),
                'bar': getattr(sdata, 'cur_bar_pres', 0),
                'v': getattr(sdata, 'sys_voltage', 0),
                'fm': getattr(sdata, 'free_mem', 0),
            })
        with open(_field_data_path(), 'a') as f:
            f.write(json.dumps(payload) + '\n')
    except Exception as e:
        try:
            TMON_AI.error_count += 1
            TMON_AI.last_error = str(e)
        except Exception:
            pass
    finally:
        _gc_collect()

def delete_field_data_log():
    try:
        os.remove(_field_data_path())
    except Exception:
        pass
    finally:
        _gc_collect()

def append_field_data_lines(text_blob: str):
    """Append already-serialized field data lines (used by base receiving remote field logs)."""
    try:
        if not text_blob:
            return
        checkLogDirectory()
        with open(_field_data_path(), 'a') as f:
            f.write(str(text_blob).rstrip() + '\n')
    except Exception:
        pass
    finally:
        _gc_collect()

async def send_field_data_log():
    """Best-effort uploader for base/wifi nodes using wprest.send_data_to_wp if available."""
    try:
        node_role = str(getattr(settings, 'NODE_TYPE', 'base')).lower()
        if node_role == 'remote':
            return
        try:
            from wprest import send_data_to_wp
        except Exception:
            return
        await send_data_to_wp()
    finally:
        _gc_collect()
        if asyncio:
            await asyncio.sleep(0)

# --- Background task scheduler hooks used by main.py ---
def start_background_tasks():
    # Keep minimal to avoid duplicate loops; main.py already schedules most tasks.
    return True

async def periodic_provision_check():
    # Minimal stub: provisioning is handled in main/boot in this repo snapshot.
    while True:
        try:
            await asyncio.sleep(int(getattr(settings, 'PROVISION_CHECK_INTERVAL_S', 60)))
        except Exception:
            if asyncio:
                await asyncio.sleep(60)

# Legacy names imported by main.py but not required in this snapshot
async def periodic_field_data_send():
    while True:
        await send_field_data_log()
        await asyncio.sleep(int(getattr(settings, 'FIELD_DATA_SEND_INTERVAL', 300)))

def write_lora_log(line, level='INFO'):
    try:
        checkLogDirectory()
        p = getattr(settings, 'LORA_LOG_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/lora.log')
        with open(p, 'a') as f:
            f.write(f"{int(time.time())} [{level}] {line}\n")
    except Exception:
        pass
    finally:
        _gc_collect()