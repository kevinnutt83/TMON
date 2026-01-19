# Firmware Version: v2.06.0
try:
    import uasyncio as asyncio
except Exception:
    import asyncio  # type: ignore

try:
    import ujson as json
except Exception:
    import json  # type: ignore

try:
    import uos as os
except Exception:
    import os  # type: ignore

try:
    import utime as time
except Exception:
    import time  # type: ignore

import settings

class _TMONAI:
    def __init__(self):
        self.error_count = 0
        self.last_error = ""

TMON_AI = _TMONAI()

def checkLogDirectory():
    try:
        os.stat(settings.LOG_DIR)
    except Exception:
        try:
            os.mkdir(settings.LOG_DIR)
        except Exception:
            pass

async def debug_print(message, level="INFO"):
    try:
        print(f"[{level}] {message}")
    except Exception:
        pass
    await asyncio.sleep(0)

def led_status_flash(_code="INFO"):
    return

def flash_led(*_a, **_kw):
    return

async def free_pins():
    await asyncio.sleep(0)

def write_lora_log(line: str, level="INFO"):
    try:
        checkLogDirectory()
        path = settings.LOG_DIR.rstrip("/") + "/lora.log"
        ts = int(time.time()) if hasattr(time, "time") else 0
        with open(path, "a") as f:
            f.write(f"{ts} [{level}] {line}\n")
    except Exception:
        pass

def persist_unit_id(unit_id: str):
    try:
        checkLogDirectory()
        with open(settings.UNIT_ID_FILE, "w") as f:
            f.write(str(unit_id).strip())
        return True
    except Exception:
        return False

def load_persisted_unit_id():
    try:
        with open(settings.UNIT_ID_FILE, "r") as f:
            v = (f.read() or "").strip()
        return v or None
    except Exception:
        return None

def persist_unit_name(unit_name: str):
    try:
        checkLogDirectory()
        with open(settings.UNIT_NAME_FILE, "w") as f:
            f.write(str(unit_name).strip())
        return True
    except Exception:
        return False

def persist_node_type(node_type: str):
    try:
        checkLogDirectory()
        with open(settings.NODE_TYPE_FILE, "w") as f:
            f.write(str(node_type).strip())
        return True
    except Exception:
        return False

def load_persisted_node_type():
    try:
        with open(settings.NODE_TYPE_FILE, "r") as f:
            v = (f.read() or "").strip()
        return v or None
    except Exception:
        return None

def persist_wordpress_api_url(url: str):
    try:
        checkLogDirectory()
        settings.WORDPRESS_API_URL = str(url).strip()
        with open(settings.WORDPRESS_API_URL_FILE, "w") as f:
            f.write(settings.WORDPRESS_API_URL)
        return True
    except Exception:
        return False

def load_persisted_wordpress_api_url():
    try:
        with open(settings.WORDPRESS_API_URL_FILE, "r") as f:
            v = (f.read() or "").strip()
        if v:
            settings.WORDPRESS_API_URL = v
        return v
    except Exception:
        return ""

def get_machine_id():
    try:
        import machine, ubinascii
        return ubinascii.hexlify(machine.unique_id()).decode()
    except Exception:
        return None

async def safe_run(coro, label="task"):
    try:
        return await coro
    except Exception as e:
        try:
            TMON_AI.error_count += 1
            TMON_AI.last_error = f"{label}: {e}"
        except Exception:
            pass
        try:
            await debug_print(f"{label} error: {e}", "ERROR")
        except Exception:
            pass
        return None

def update_sys_voltage():
    return 0.0

def record_field_data():
    try:
        import sdata
        checkLogDirectory()
        rec = {
            "ts": int(time.time()) if hasattr(time, "time") else 0,
            "unit_id": getattr(settings, "UNIT_ID", ""),
            "name": getattr(settings, "UNIT_Name", ""),
            "node_type": getattr(settings, "NODE_TYPE", ""),
            "sdata": {k: getattr(sdata, k) for k in dir(sdata) if not k.startswith("_") and not callable(getattr(sdata, k))},
        }
        with open(settings.FIELD_DATA_LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass

def delete_field_data_log():
    try:
        os.remove(settings.FIELD_DATA_LOG)
    except Exception:
        pass

async def send_field_data_log():
    # Keep minimal; main/lora handle most transport logic
    await asyncio.sleep(0)
    return True

async def periodic_field_data_send():
    while True:
        try:
            await send_field_data_log()
        except Exception:
            pass
        await asyncio.sleep(int(getattr(settings, "FIELD_DATA_SEND_INTERVAL", 300)))

async def periodic_provision_check():
    while True:
        try:
            load_persisted_wordpress_api_url()
        except Exception:
            pass
        await asyncio.sleep(int(getattr(settings, "PROVISION_CHECK_INTERVAL_S", 60)))

_started = False
def start_background_tasks():
    global _started
    if _started:
        return
    _started = True

async def runGC():
    try:
        import gc
        gc.collect()
    except Exception:
        pass
    await asyncio.sleep(0)