# Firmware Version: v2.06.0
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

import uos as os

try:
    import gc
except Exception:
    gc = None

import settings

# ---------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------
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

async def debug_print(message, category="INFO"):
    """Async-safe debug logger used throughout firmware."""
    try:
        if bool(getattr(settings, 'DEBUG', False)) or category in ("ERROR", "WARN"):
            try:
                print(f"[{category}] {message}")
            except Exception:
                pass
    finally:
        _gc_collect()
        if asyncio:
            await asyncio.sleep(0)

def safe_run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception:
        return None

# ---------------------------------------------------------------------
# LEDs / Pins
# ---------------------------------------------------------------------
def flash_led(pin_num=None, times=1, delay_ms=80):
    try:
        import machine
        pnum = pin_num if pin_num is not None else int(getattr(settings, 'LED_PIN', getattr(settings, 'STATUS_LED_PIN', 25)))
        p = machine.Pin(pnum, machine.Pin.OUT)
        for _ in range(int(times)):
            p.value(1)
            time.sleep_ms(int(delay_ms))
            p.value(0)
            time.sleep_ms(int(delay_ms))
    except Exception:
        pass

def led_status_flash(kind='INFO'):
    # Minimal mapping; keep safe on boards without RGB.
    try:
        k = str(kind).upper()
        if k in ('ERROR',):
            flash_led(times=5, delay_ms=25)
        elif k in ('WARN',):
            flash_led(times=3, delay_ms=35)
        elif k in ('SUCCESS',):
            flash_led(times=2, delay_ms=45)
        else:
            flash_led(times=1, delay_ms=60)
    except Exception:
        pass

async def free_pins():
    # Best-effort placeholder. Drivers handle their own pin state; keep non-blocking.
    if asyncio:
        await asyncio.sleep(0)

# ---------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------
def _path(name, default):
    try:
        return getattr(settings, name, default)
    except Exception:
        return default

def persist_unit_id(unit_id: str):
    checkLogDirectory()
    path = _path('UNIT_ID_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/unit_id.txt')
    try:
        with open(path, 'w') as f:
            f.write(str(unit_id))
    except Exception:
        pass
    finally:
        _gc_collect()

def load_persisted_unit_id():
    path = _path('UNIT_ID_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/unit_id.txt')
    try:
        with open(path, 'r') as f:
            return (f.read() or '').strip() or None
    except Exception:
        return None

def persist_unit_name(name: str):
    checkLogDirectory()
    path = _path('UNIT_NAME_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/unit_name.txt')
    try:
        with open(path, 'w') as f:
            f.write(str(name))
    except Exception:
        pass
    finally:
        _gc_collect()

def persist_node_type(node_type: str):
    checkLogDirectory()
    path = _path('NODE_TYPE_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/node_type.txt')
    try:
        with open(path, 'w') as f:
            f.write(str(node_type))
    except Exception:
        pass
    finally:
        _gc_collect()

def load_persisted_node_type():
    path = _path('NODE_TYPE_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/node_type.txt')
    try:
        with open(path, 'r') as f:
            return (f.read() or '').strip() or None
    except Exception:
        return None

def persist_wordpress_api_url(url: str):
    checkLogDirectory()
    path = _path('WORDPRESS_API_URL_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/wordpress_api_url.txt')
    try:
        with open(path, 'w') as f:
            f.write(str(url))
    except Exception:
        pass
    finally:
        _gc_collect()

def load_persisted_wordpress_api_url():
    path = _path('WORDPRESS_API_URL_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/wordpress_api_url.txt')
    try:
        with open(path, 'r') as f:
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
    """Required by settings_apply.py (fixes ImportError)."""
    checkLogDirectory()
    path = _path('SUSPENDED_FLAG_FILE', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/suspended.flag')
    try:
        if suspended:
            with open(path, 'w') as f:
                f.write('1')
        else:
            try:
                os.remove(path)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        _gc_collect()

def get_machine_id():
    try:
        import machine
        if hasattr(machine, 'unique_id'):
            try:
                import ubinascii
                return ubinascii.hexlify(machine.unique_id()).decode()
            except Exception:
                return str(machine.unique_id())
    except Exception:
        pass
    return None

# ---------------------------------------------------------------------
# Voltage / GC / Logs
# ---------------------------------------------------------------------
def update_sys_voltage():
    try:
        import machine
        pin = int(getattr(settings, 'SYS_VOLTAGE_PIN', getattr(settings, 'VBAT_ADC_PIN', 26)))
        adc = machine.ADC(pin)
        raw = adc.read_u16()
        vref = float(getattr(settings, 'ADC_VREF', 3.3))
        div = float(getattr(settings, 'VBAT_DIVIDER', 2.0))
        v = (raw / 65535.0) * vref * div
        try:
            import sdata
            sdata.sys_voltage = v
        except Exception:
            pass
        return v
    except Exception:
        return 0.0

def check_log_size(file_path, max_bytes=512000):
    try:
        if not file_path:
            return
        st = os.stat(file_path)
        size = st[6]
        if size <= int(max_bytes):
            return
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
        # Per markup: do NOT rotate FIELD_DATA_LOG
        files = [
            getattr(settings, 'LOG_FILE', None),
            getattr(settings, 'ERROR_LOG_FILE', None),
            getattr(settings, 'FIELD_DATA_DELIVERED_LOG', None),
            getattr(settings, 'DATA_HISTORY_LOG', None),
        ]
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

# ---------------------------------------------------------------------
# Field data (record for ALL node types)
# ---------------------------------------------------------------------
def record_field_data():
    try:
        import sdata
        checkLogDirectory()
        path = getattr(settings, 'FIELD_DATA_LOG', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/field_data.log')
        row = {
            'ts': int(time.time()),
            'unit_id': getattr(settings, 'UNIT_ID', ''),
            'unit_name': getattr(settings, 'UNIT_Name', ''),
            'node_type': getattr(settings, 'NODE_TYPE', ''),
            't_f': getattr(sdata, 'cur_temp_f', 0),
            'hum': getattr(sdata, 'cur_humid', 0),
            'bar': getattr(sdata, 'cur_bar_pres', 0),
            'v': getattr(sdata, 'sys_voltage', 0),
            'fm': getattr(sdata, 'free_mem', 0),
        }
        with open(path, 'a') as f:
            f.write(json.dumps(row) + '\n')
    except Exception:
        pass
    finally:
        _gc_collect()

def delete_field_data_log():
    try:
        path = getattr(settings, 'FIELD_DATA_LOG', getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + '/field_data.log')
        os.remove(path)
    except Exception:
        pass
    finally:
        _gc_collect()

async def send_field_data_log():
    """Base/WiFi nodes upload via wprest if available; remotes no-op."""
    try:
        role = str(getattr(settings, 'NODE_TYPE', 'base')).lower()
        if role == 'remote':
            return False
        try:
            import wprest
            fn = getattr(wprest, 'send_data_to_wp', None)
        except Exception:
            fn = None
        if fn:
            await fn()
            return True
        return False
    finally:
        _gc_collect()
        if asyncio:
            await asyncio.sleep(0)

# ---------------------------------------------------------------------
# Background loops referenced by main.py
# ---------------------------------------------------------------------
def start_background_tasks():
    # main.py schedules its own tasks; keep as a safe no-op.
    return True

async def periodic_provision_check():
    """Best-effort loop so main.py can import/schedule it without crashing."""
    while True:
        try:
            await asyncio.sleep(int(getattr(settings, 'PROVISION_CHECK_INTERVAL_S', 60)))
        except Exception:
            if asyncio:
                await asyncio.sleep(60)

async def periodic_field_data_send():
    # Legacy import name in main.py; delegate to send_field_data_log().
    while True:
        try:
            await send_field_data_log()
        except Exception:
            pass
        await asyncio.sleep(int(getattr(settings, 'FIELD_DATA_SEND_INTERVAL', 300)))