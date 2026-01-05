# Firmware Version: v2.06.0
# Utility to print remote node info
def print_remote_nodes():
    import settings
    remote_info = getattr(settings, 'REMOTE_NODE_INFO', {})
    for node_id, node_data in remote_info.items():
        print(f"[REMOTE NODE] {node_id}: {node_data}")

# --- All imports at the top ---
import ujson
import os
import uasyncio as asyncio
import select
import random  # Added for jitter/backoff
import ubinascii as _ub  # NEW: base64 encode/decode for chunking
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
from utils import free_pins, checkLogDirectory, debug_print, TMON_AI, safe_run, led_status_flash, write_lora_log, persist_unit_id, record_field_data
from relay import toggle_relay
try:
    from encryption import chacha20_encrypt, derive_nonce
except Exception:
    chacha20_encrypt = None
    derive_nonce = None

# Guarded import of optional wprest helpers to avoid ImportError on devices that don't expose all names.
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

# File to persist remote node info and remote sync schedule
import settings
REMOTE_NODE_INFO_FILE = settings.LOG_DIR + '/remote_node_info.json'
REMOTE_SYNC_SCHEDULE_FILE = settings.LOG_DIR + '/remote_sync_schedule.json'
GPS_STATE_FILE = settings.LOG_DIR + '/gps.json'

# Load REMOTE_NODE_INFO from file at startup
def load_remote_node_info():
    try:
        with open(REMOTE_NODE_INFO_FILE, 'r') as f:
            settings.REMOTE_NODE_INFO = ujson.load(f)
    except Exception:
        settings.REMOTE_NODE_INFO = {}

    # Load remote sync schedule (base only)
    try:
        with open(REMOTE_SYNC_SCHEDULE_FILE, 'r') as f:
            settings.REMOTE_SYNC_SCHEDULE = ujson.load(f)
    except Exception:
        settings.REMOTE_SYNC_SCHEDULE = {}

    # Load last known GPS state
    try:
        with open(GPS_STATE_FILE, 'r') as f:
            gps = ujson.load(f)
            try:
                import sdata as _s
                _s.gps_lat = gps.get('gps_lat')
                _s.gps_lng = gps.get('gps_lng')
                _s.gps_alt_m = gps.get('gps_alt_m')
                _s.gps_accuracy_m = gps.get('gps_accuracy_m')
                _s.gps_last_fix_ts = gps.get('gps_last_fix_ts')
            except Exception:
                pass
            # also project to settings if allowed
            try:
                if getattr(settings, 'GPS_OVERRIDE_ALLOWED', True):
                    if 'gps_lat' in gps: settings.GPS_LAT = gps.get('gps_lat')
                    if 'gps_lng' in gps: settings.GPS_LNG = gps.get('gps_lng')
                    if 'gps_alt_m' in gps: settings.GPS_ALT_M = gps.get('gps_alt_m')
                    if 'gps_accuracy_m' in gps: settings.GPS_ACCURACY_M = gps.get('gps_accuracy_m')
                    if 'gps_last_fix_ts' in gps: settings.GPS_LAST_FIX_TS = gps.get('gps_last_fix_ts')
            except Exception:
                pass
    except Exception:
        pass

# Ensure remote node info is loaded at startup (after settings import)
load_remote_node_info()

# Save REMOTE_NODE_INFO to file
def save_remote_node_info():
    try:
        with open(REMOTE_NODE_INFO_FILE, 'w') as f:
            ujson.dump(settings.REMOTE_NODE_INFO, f)
    except Exception:
        pass

def save_remote_sync_schedule():
    try:
        with open(REMOTE_SYNC_SCHEDULE_FILE, 'w') as f:
            ujson.dump(settings.REMOTE_SYNC_SCHEDULE, f)
    except Exception:
        pass

def save_gps_state(lat=None, lng=None, alt=None, acc=None, ts=None):
    try:
        # Update sdata mirror
        try:
            import sdata as _s
            _s.gps_lat = lat
            _s.gps_lng = lng
            _s.gps_alt_m = alt
            _s.gps_accuracy_m = acc
            _s.gps_last_fix_ts = ts
        except Exception:
            pass
        # Update settings if allowed
        try:
            if getattr(settings, 'GPS_OVERRIDE_ALLOWED', True):
                if lat is not None: settings.GPS_LAT = lat
                if lng is not None: settings.GPS_LNG = lng
                if alt is not None: settings.GPS_ALT_M = alt
                if acc is not None: settings.GPS_ACCURACY_M = acc
                if ts is not None: settings.GPS_LAST_FIX_TS = ts
        except Exception:
            pass
        with open(GPS_STATE_FILE, 'w') as f:
            ujson.dump({
                'gps_lat': lat,
                'gps_lng': lng,
                'gps_alt_m': alt,
                'gps_accuracy_m': acc,
                'gps_last_fix_ts': ts
            }, f)
    except Exception:
        pass

# Import all WordPress REST API functions from wprest.py (guarded - tolerate missing names)
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
except Exception:
    register_with_wp = send_data_to_wp = send_settings_to_wp = fetch_settings_from_wp = None
    send_file_to_wp = request_file_from_wp = heartbeat_ping = poll_ota_jobs = handle_ota_job = None

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
        headers = {}
        try:
            headers = _auth_headers()
        except Exception:
            headers = {}
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/settings/{settings.UNIT_ID}', headers=headers)
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

# Restore: define WORDPRESS_API_URL safely for this module
try:
    WORDPRESS_API_URL = getattr(settings, 'WORDPRESS_API_URL', '')
except Exception:
    WORDPRESS_API_URL = ''

if not WORDPRESS_API_URL:
    try:
        from config_persist import read_text
        path = getattr(settings, 'WORDPRESS_API_URL_FILE', settings.LOG_DIR + '/wordpress_api_url.txt')
        val = (read_text(path, '') or '').strip()
        if val:
            settings.WORDPRESS_API_URL = val
            WORDPRESS_API_URL = val
    except Exception:
        pass

if not WORDPRESS_API_URL:
    try:
        import wprest as _w
        WORDPRESS_API_URL = getattr(_w, 'WORDPRESS_API_URL', '') or ''
    except Exception:
        pass

def refresh_wp_url():
    """Refresh local WORDPRESS_API_URL from settings/wprest/file."""
    global WORDPRESS_API_URL
    try:
        url = getattr(settings, 'WORDPRESS_API_URL', '') or ''
        if not url:
            try:
                import wprest as _w
                url = getattr(_w, 'WORDPRESS_API_URL', '') or ''
            except Exception:
                url = ''
        if not url:
            try:
                from config_persist import read_text
                path = getattr(settings, 'WORDPRESS_API_URL_FILE', settings.LOG_DIR + '/wordpress_api_url.txt')
                url = (read_text(path, '') or '').strip()
            except Exception:
                pass
        if url:
            WORDPRESS_API_URL = url
    except Exception:
        pass

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
        hdrs = {}
        try:
            hdrs = _auth_headers()
        except Exception:
            hdrs = {}
        resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/settings', headers=hdrs, json=data)
        if resp.status_code == 200:
            await debug_print('Settings sent to WP', 'INFO')
        else:
            await debug_print(f'Failed to send settings to WP: {resp.status_code}', 'ERROR')
    except Exception as e:
        await debug_print(f'send_settings_to_wp error: {e}', 'ERROR')

# NEW: compute an effective max payload size (prevents runtime overrides like 8 bytes from breaking LoRa)
def _effective_lora_max_payload(role):
    try:
        raw = getattr(settings, 'LORA_MAX_PAYLOAD', 160)
        cfg = int(raw) if raw is not None else 160
    except Exception:
        cfg = 160
    try:
        minv = int(getattr(settings, 'LORA_MAX_PAYLOAD_MIN', 96) or 96)
        maxv = int(getattr(settings, 'LORA_MAX_PAYLOAD_MAX', 160) or 160)
    except Exception:
        minv, maxv = 96, 160

    # Hard hardware cap (your code comments already assume this)
    hw_cap = 160

    # Clamp
    eff = cfg
    if eff < minv:
        eff = maxv  # when absurdly low, jump to safe default rather than a tiny clamp that still can't carry JSON
        try:
            # best-effort: show what we saw so you can trace the override source
            asyncio.create_task(debug_print(f"lora: LORA_MAX_PAYLOAD too low ({cfg}); using {eff}", "WARN"))
        except Exception:
            pass
    if eff > maxv:
        eff = maxv
    if eff > hw_cap:
        eff = hw_cap
    return eff

# NEW: base RX helper (different SX1262 ports/drivers vary; try common "start RX" entrypoints)
def _ensure_base_rx(lo):
    if lo is None:
        return
    try:
        lo.setOperatingMode(lo.MODE_RX)
    except Exception:
        pass
    # Try to explicitly start RX if driver requires it
    for m in ('startReceive', 'start_receive', 'receive', 'recv', 'listen', 'startRx', 'setRx'):
        try:
            if hasattr(lo, m):
                fn = getattr(lo, m)
                try:
                    fn()
                except TypeError:
                    # Some variants accept a timeout or "continuous" bool; ignore if signature differs
                    try:
                        fn(0)
                    except Exception:
                        pass
                break
        except Exception:
            pass

# NEW: remote TX helper for chunked send (uses base-side reassembly already present)
async def _send_chunked(lo, unit_id, payload_bytes, max_frame):
    # Build chunks so that JSON envelope stays <= max_frame.
    # Envelope: {"chunked":1,"unit_id":"...","seq":1,"total":N,"b64":"..."}
    if lo is None:
        try:
            await debug_print("lora: chunked send called with lo=None (radio not initialized)", "ERROR")
        except Exception:
            pass
        return False

    # Compute a conservative raw chunk size given max_frame and base64 overhead.
    try:
        target_raw = int(getattr(settings, 'LORA_CHUNK_RAW_BYTES', 100) or 100)
    except Exception:
        target_raw = 100

    # Ensure envelope fits by shrinking raw size until it does.
    raw_size = min(target_raw, 96)
    while raw_size > 8:
        try:
            # Worst-case base64 length for raw_size
            b64_len = ((raw_size + 2) // 3) * 4
            probe = ujson.dumps({
                'chunked': 1, 'unit_id': str(unit_id),
                'seq': 1, 'total': 1,
                'b64': 'A' * b64_len
            }).encode('utf-8')
            if len(probe) <= max_frame:
                break
        except Exception:
            pass
        raw_size = max(8, raw_size - 8)

    if raw_size <= 8:
        await debug_print(f"lora: chunking impossible (max_frame={max_frame})", "ERROR")
        return False

    total = (len(payload_bytes) + raw_size - 1) // raw_size
    await debug_print(f"lora: chunked send start bytes={len(payload_bytes)} raw_size={raw_size} total={total}", "LORA")

    # Send all chunks (base will ACK only after full reassembly)
    for seq in range(1, total + 1):
        chunk = payload_bytes[(seq - 1) * raw_size: seq * raw_size]
        try:
            b64 = _ub.b2a_base64(chunk).decode().strip()
            frame = ujson.dumps({
                'chunked': 1,
                'unit_id': str(unit_id),
                'seq': seq,
                'total': total,
                'b64': b64
            }).encode('utf-8')
        except Exception as e:
            await debug_print(f"lora: chunk encode failed seq={seq}: {e}", "ERROR")
            return False

        # Defensive: if frame still too big, shrink chunk further for this seq
        while len(frame) > max_frame and len(chunk) > 8:
            chunk = chunk[: max(8, len(chunk) - 8)]
            b64 = _ub.b2a_base64(chunk).decode().strip()
            frame = ujson.dumps({
                'chunked': 1, 'unit_id': str(unit_id), 'seq': seq, 'total': total, 'b64': b64
            }).encode('utf-8')

        if len(frame) > max_frame:
            await debug_print(f"lora: chunk frame too large seq={seq} len={len(frame)} max={max_frame}", "ERROR")
            return False

        # TX
        try:
            lo.setOperatingMode(lo.MODE_TX)
        except Exception:
            pass
        await asyncio.sleep(0.02)

        resp = None
        try:
            resp = lo.send(frame)
        except Exception as e:
            await debug_print(f"lora: chunk send exception seq={seq}: {e}", "ERROR")
            return False

        # Normalize resp like your single-frame path
        st_code = -999
        try:
            if isinstance(resp, (tuple, list)) and len(resp) >= 2:
                size, code = resp[0], resp[1]
                st_code = 0 if (code == -1 and size == len(frame)) else int(code)
            elif isinstance(resp, int):
                st_code = resp
            else:
                st_code = int(resp)
        except Exception:
            st_code = -999

        if st_code != 0:
            await debug_print(f"lora: chunk send failed seq={seq} resp={resp} code={st_code}", "ERROR")
            return False

        # Brief settle between chunks
        await asyncio.sleep(0.05)

    # Return to RX for final ACK window
    try:
        lo.setOperatingMode(lo.MODE_RX)
    except Exception:
        pass
    return True

# NEW: best-effort RX poll (for setups where _events()/IRQ never fire)
def _try_read_rx_bytes(lo, max_bytes=255):
    if lo is None:
        return None
    # Prefer non-blocking-ish APIs; tolerate different driver return shapes.
    for name in ("recv", "receive", "read", "readData"):
        if not hasattr(lo, name):
            continue
        fn = getattr(lo, name)
        try:
            try:
                out = fn(0)
            except TypeError:
                out = fn()
            if not out:
                continue
            if isinstance(out, (tuple, list)) and out:
                out = out[0]
            if isinstance(out, (bytes, bytearray)):
                b = bytes(out)
                return b[:max_bytes] if max_bytes and len(b) > max_bytes else b
            if isinstance(out, str):
                b = out.encode("utf-8")
                return b[:max_bytes] if max_bytes and len(b) > max_bytes else b
        except Exception:
            pass
    return None

# NEW: shared remote ACK wait (used for both chunked and single-frame TX)
async def _wait_for_ack(lo, rx_done_flag, ack_wait_ms=None):
    if lo is None:
        return False
    if ack_wait_ms is None:
        ack_wait_ms = int(getattr(settings, 'LORA_CHUNK_ACK_WAIT_MS', 1500) or 1500)

    start_wait = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start_wait) < ack_wait_ms:
        ev2 = 0
        try:
            ev2 = lo._events()
        except Exception:
            ev2 = 0
        if rx_done_flag is not None and (ev2 & rx_done_flag):
            try:
                msg2, err2 = lo._readData(0)
            except Exception:
                msg2, err2 = None, -1
            if err2 == 0 and msg2:
                txt2 = msg2.decode('utf-8', 'ignore') if isinstance(msg2, (bytes, bytearray)) else str(msg2)
                try:
                    obj2 = ujson.loads(txt2)
                except Exception:
                    obj2 = None
                if isinstance(obj2, dict) and obj2.get('ack') == 'ok':
                    # Adopt next sync
                    try:
                        if 'next_in' in obj2:
                            rel = int(obj2['next_in'])
                            rel = 1 if rel < 1 else rel
                            rel = 24 * 3600 if rel > 24 * 3600 else rel
                            settings.nextLoraSync = int(time.time() + rel)
                        elif 'next' in obj2:
                            settings.nextLoraSync = int(obj2['next'])
                    except Exception:
                        pass
                    # Adopt GPS (optional)
                    try:
                        if getattr(settings, 'GPS_ACCEPT_FROM_BASE', True):
                            blat = obj2.get('gps_lat'); blng = obj2.get('gps_lng')
                            if (blat is not None) and (blng is not None):
                                save_gps_state(blat, blng, obj2.get('gps_alt_m'), obj2.get('gps_accuracy_m'), obj2.get('gps_last_fix_ts'))
                    except Exception:
                        pass
                    # Execute command (optional)
                    try:
                        cmd_str = obj2.get('cmd')
                        if cmd_str:
                            target = obj2.get('cmd_target', 'ALL')
                            if target == 'ALL' or target == str(getattr(settings, 'UNIT_ID', '')):
                                await _execute_command_string(cmd_str)
                    except Exception:
                        pass
                    return True
        await asyncio.sleep(0.01)
    return False

async def connectLora():
    """Non-blocking LoRa routine called frequently from lora_comm_task.
    - Initializes radio once (with retry cap)
    - Remote: sends payload at interval, waits for TX_DONE briefly, then returns
    - Base: polls for RX_DONE and processes any message
    - Idle timeout: deinit after prolonged inactivity to save power
    Returns True if LoRa is initialized and usable, else False.
    """
    global lora, _last_send_ms, _last_activity_ms, _init_failures, _last_tx_exception_ms
    global _connected_remotes, _pending_commands

    # Respect ENABLE_LORA flag like previous version
    if not getattr(settings, 'ENABLE_LORA', True):
        try:
            await debug_print("connectLora: ENABLE_LORA is False, skipping LoRa work", "LORA")
        except Exception:
            pass
        return False

    # NEW: serialize connectLora() to avoid any mid-send lora=None surprises
    async with _connect_lock:
        # --- INITIALIZE SHARED LOCALS TO AVOID UnboundLocalError ---
        # Defensive defaults for locals that may be referenced in exception handlers
        state = -999
        resp = None
        st = None
        st2 = None
        dev_err = None
        busy_val = None
        msg2 = None
        err2 = None
        tb = ''
        tx_start = 0
        # Extra locals that may otherwise be referenced before assignment in complex flows
        parts = []
        total = 0
        part_failure = False
        chunk_sent = False
        attempt = 0
        st_code = None
        # TX/RX flags: evaluate early and reuse (safe even if SX1262 missing)
        TX_DONE_FLAG = getattr(SX1262, 'TX_DONE', None) if SX1262 is not None else None
        RX_DONE_FLAG = getattr(SX1262, 'RX_DONE', None) if SX1262 is not None else None

        now = time.ticks_ms()
        role = getattr(settings, 'NODE_TYPE', 'base')

        # NEW: restore "ensure initialized" guard (required for remote chunked send + base RX)
        try:
            await debug_print(
                f"connectLora: entry role={role} lora_is_none={lora is None} "
                f"init_failures={_init_failures} last_send_ms={_last_send_ms} last_activity_ms={_last_activity_ms}",
                "LORA",
            )
        except Exception:
            pass

        if lora is None:
            if _init_failures >= _MAX_INIT_FAILS:
                try:
                    await debug_print("connectLora: max init failures reached; not reinitializing", "ERROR")
                except Exception:
                    pass
                return False
            try:
                await debug_print("LoRa: initializing...", "LORA")
            except Exception:
                pass
            try:
                async with pin_lock:
                    ok = await init_lora()
            except Exception as e:
                ok = False
                try:
                    await debug_print(f"connectLora: init_lora exception: {e}", "ERROR")
                except Exception:
                    pass
            if not ok:
                _init_failures += 1
                try:
                    await debug_print(f"connectLora: init_lora failed (count={_init_failures})", "ERROR")
                except Exception:
                    pass
                return False
            _init_failures = 0
            _last_activity_ms = now

        # --- Base: listen for remote messages and persist them ---
        if role == 'base':
            try:
                # NEW: make sure base is actually in RX and listening each cycle
                _ensure_base_rx(lora)
                # Keep base "active" so it doesn't get idle-deinit'd
                _last_activity_ms = now

                # Poll events briefly for incoming RX frames
                RX_DONE_FLAG = getattr(SX1262, 'RX_DONE', None)
                ev = 0
                try:
                    ev = lora._events()
                except Exception:
                    ev = 0

                # NEW: if events never fire, optionally poll RX directly
                msg_bytes = None
                if not ev and bool(getattr(settings, 'LORA_RX_POLL_FALLBACK', True)):
                    msg_bytes = _try_read_rx_bytes(
                        lora,
                        int(getattr(settings, 'LORA_RX_POLL_MAX_BYTES', 255) or 255),
                    )

                # Existing IRQ/event-driven path (keep)
                if msg_bytes is None and RX_DONE_FLAG is not None and (ev & RX_DONE_FLAG):
                    try:
                        msg_bytes, err = lora._readData(0)
                    except Exception:
                        msg_bytes, err = None, -1
                    if err != 0 or not msg_bytes:
                        msg_bytes = None

                if msg_bytes:
                    # Update activity
                    _last_activity_ms = now

                    # Decode and persist
                    txt = msg_bytes.decode('utf-8', 'ignore') if isinstance(msg_bytes, (bytes, bytearray)) else str(msg_bytes)
                    try:
                        obj = ujson.loads(txt)
                    except Exception:
                        obj = None

                    if isinstance(obj, dict):
                        unit_id = obj.get('unit_id')
                        if unit_id:
                            # Update connected remotes
                            _connected_remotes[unit_id] = time.time()

                            # Handle chunked reassembly
                            if obj.get('chunked'):
                                seq = obj.get('seq')
                                total = obj.get('total')
                                b64 = obj.get('b64')
                                if seq and total and b64:
                                    if unit_id not in _lora_incoming_chunks:
                                        _lora_incoming_chunks[unit_id] = {'total': total, 'parts': {}, 'ts': time.time()}
                                    try:
                                        chunk = _ub.a2b_base64(b64)
                                        _lora_incoming_chunks[unit_id]['parts'][seq] = chunk
                                    except Exception:
                                        pass
                                    # Check if complete
                                    if len(_lora_incoming_chunks[unit_id]['parts']) == total:
                                        parts = sorted(_lora_incoming_chunks[unit_id]['parts'].items())
                                        full_payload = b''.join(p[1] for p in parts)
                                        try:
                                            obj = ujson.loads(full_payload.decode('utf-8'))
                                        except Exception:
                                            obj = None
                                        del _lora_incoming_chunks[unit_id]
                                        # Proceed with reassembled obj
                            # Persist data (chunked or single)
                            if obj:
                                await record_field_data(obj)
                            # Send ACK with next sync and optional command
                            ack = {'ack': 'ok'}
                            try:
                                next_sync = get_next_sync_for_remote(unit_id)
                                ack['next_in'] = next_sync
                            except Exception:
                                pass
                            try:
                                if unit_id in _pending_commands:
                                    ack['cmd'] = _pending_commands.pop(unit_id)
                            except Exception:
                                pass
                            try:
                                if getattr(settings, 'GPS_BROADCAST_TO_REMOTES', True):
                                    ack['gps_lat'] = getattr(settings, 'GPS_LAT', None)
                                    ack['gps_lng'] = getattr(settings, 'GPS_LNG', None)
                                    ack['gps_alt_m'] = getattr(settings, 'GPS_ALT_M', None)
                                    ack['gps_accuracy_m'] = getattr(settings, 'GPS_ACCURACY_M', None)
                                    ack['gps_last_fix_ts'] = getattr(settings, 'GPS_LAST_FIX_TS', None)
                            except Exception:
                                pass
                            try:
                                ack_json = ujson.dumps(ack).encode('utf-8')
                                lora.send(ack_json)
                            except Exception as e:
                                await debug_print(f"lora: base ACK send failed: {e}", "ERROR")
                return True
            except Exception as e:
                await debug_print(f"lora: base RX error: {e}", "ERROR")
                return False

        # --- Remote: check-in TX ---
        if role == 'remote':
            # Remote: check if due for check-in (or forced)
            check_in_ms = getattr(settings, 'LORA_CHECK_IN_MINUTES', 5) * 60 * 1000
            if time.ticks_diff(now, _last_send_ms) < check_in_ms:
                return True  # Initialized and not yet due

            # NEW: collect payload and send chunked if needed
            data = {}
            try:
                data = sdata.toDict()
            except Exception:
                data = {}

            payload = ujson.dumps(data).encode('utf-8')

            max_frame = _effective_lora_max_payload(role)

            if len(payload) > max_frame:
                chunk_sent = await _send_chunked(lora, settings.UNIT_ID, payload, max_frame)
            else:
                chunk_sent = False
                # Single-frame send
                frame = ujson.dumps(data).encode('utf-8')
                try:
                    lo.setOperatingMode(lo.MODE_TX)
                except Exception:
                    pass
                await asyncio.sleep(0.02)

                resp = None
                try:
                    resp = lo.send(frame)
                except Exception as e:
                    await debug_print(f"lora: remote TX exception: {e}", "ERROR")
                    return False

                # Normalize resp
                st_code = -999
                try:
                    if isinstance(resp, (tuple, list)) and len(resp) >= 2:
                        size, code = resp[0], resp[1]
                        st_code = 0 if (code == -1 and size == len(frame)) else int(code)
                    elif isinstance(resp, int):
                        st_code = resp
                    else:
                        st_code = int(resp)
                except Exception:
                    st_code = -999

                if st_code != 0:
                    await debug_print(f"lora: remote TX failed resp={resp} code={st_code}", "ERROR")
                    return False

            # Wait for ACK (shared for chunked/single)
            ack_ok = await _wait_for_ack(lora, RX_DONE_FLAG)

            # Update last send (even on failure to avoid thrashing)
            _last_send_ms = now
            _last_activity_ms = now

            # Success LED if ACK ok
            if ack_ok:
                led_status_flash('SUCCESS')
            else:
                led_status_flash('WARN')

            return True

        # Idle timeout: deinit radio if inactive
        idle_timeout_ms = getattr(settings, 'LORA_IDLE_TIMEOUT_MS', 300000) or 300000
        if time.ticks_diff(now, _last_activity_ms) > idle_timeout_ms:
            await _deinit_lora()

        return True

file_lock = asyncio.Lock()
pin_lock = asyncio.Lock()
# NEW: prevent re-entrancy / mid-send races if connectLora ever gets called from more than one task
_connect_lock = asyncio.Lock()

lora = None

# In-memory reassembly buffers for incoming chunked messages (base-side)
_lora_incoming_chunks = {}  # unit_id -> {'total': int, 'parts': {seq: bytes}, 'ts': epoch}

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

# NEW: base-side tracking of connected remotes and pending commands
_connected_remotes = {}       # {unit_id: last_seen_epoch}
_pending_commands = {}        # {unit_id: "func(arg1,arg2,...)"}

# NEW: helper to parse and execute "func(arg1,arg2,...)" command strings
async def _execute_command_string(command):
    try:
        # Expect "func(arg1,arg2,...)" like previous version
        if '(' in command and command.endswith(')'):
            func_name, args_str = command.split('(', 1)
            func_name = func_name.strip()
            args_str = args_str.rstrip(')')
            args = [arg.strip() for arg in args_str.split(',')] if args_str else []
            if func_name in command_handlers:
                try:
                    await command_handlers[func_name](*args)
                    await debug_print(f"Executed command: {command}", "COMMAND")
                except Exception as e:
                    await debug_print(f"Command handler error for {func_name}: {e}", "ERROR")
            else:
                await debug_print(f"Unknown command: {func_name}", "ERROR")
        else:
            await debug_print(f"Invalid command format: {command}", "ERROR")
    except Exception as e:
        await debug_print(f"_execute_command_string failed: {e}", "ERROR")

import time as _time  # used for short sleeps during pin toggles

# Helpers: ensure pins / SPI are in a known state for reliable startup
def _safe_pin_out(pin_num, value=1):
    try:
        p = machine.Pin(pin_num, machine.Pin.OUT)
        p.value(value)
        return p
    except Exception:
        return None

def _safe_pin_input(pin_num):
    try:
        p = machine.Pin(pin_num, machine.Pin.IN)
        return p
    except Exception:
        return None

def _pulse_reset(pin_num, low_ms=50, post_high_ms=120):
    try:
        p = _safe_pin_out(pin_num, 0)
        _time.sleep_ms(low_ms)
        p.value(1)
        _time.sleep_ms(post_high_ms)
    except Exception:
        try:
            _time.sleep_ms(post_high_ms)
        except Exception:
            pass

def _deinit_spi_if_any(lora_obj):
    try:
        if lora_obj and hasattr(lora_obj, 'spi') and lora_obj.spi:
            try:
                lora_obj.spi.deinit()
            except Exception:
                pass
            try:
                lora_obj.spi = None
            except Exception:
                pass
    except Exception:
        pass

# NEW helper: attempt to create machine.SPI and return a tolerant shim instance or None.
def _attach_spi_shim():
    """Try various machine.SPI construction patterns and return a compact shim object or None."""
    try:
        if not (machine and hasattr(machine, 'SPI') and getattr(settings, 'CLK_PIN', None) is not None):
            return None
        spi = None
        # Try constructor with kwargs (common on many ports)
        try:
            spi = machine.SPI(
                settings.SPI_BUS,
                baudrate=getattr(settings, 'LORA_SPI_BAUD', 1000000),
                sck=machine.Pin(settings.CLK_PIN),
                mosi=machine.Pin(settings.MOSI_PIN),
                miso=machine.Pin(settings.MISO_PIN)
            )
        except Exception:
            # Fallback: construct then .init()
            try:
                spi = machine.SPI(settings.SPI_BUS)
                try:
                    spi.init(
                        baudrate=getattr(settings, 'LORA_SPI_BAUD', 1000000),
                        sck=machine.Pin(settings.CLK_PIN),
                        mosi=machine.Pin(settings.MOSI_PIN),
                        miso=machine.Pin(settings.MISO_PIN)
                    )
                except Exception:
                    # keep spi instance even if init signature differs
                    pass
            except Exception:
                spi = None
        if not spi:
            return None
        # Compact shim with tolerant methods and attribute passthrough
        class _SPIShim:
            def __init__(self, spi_obj):
                self._spi = spi_obj
            def __getattr__(self, name):
                return getattr(self._spi, name)
            def __call__(self, *a, **kw):
                try:
                    return self._spi(*a, **kw)
                except Exception:
                    return self._spi
            def init(self, *a, **kw):
                try:
                    return self._spi.init(*a, **kw)
                except Exception:
                    return None
            def write(self, buf, *a, **kw):
                try:
                    return self._spi.write(buf, *a, **kw)
                except Exception:
                    try:
                        if hasattr(self._spi, 'write_readinto'):
                            dummy = bytearray(len(buf))
                            return self._spi.write_readinto(buf, dummy)
                    except Exception:
                        pass
                    return None
            def read(self, nbytes, *a, **kw):
                try:
                    if hasattr(self._spi, 'read'):
                        return self._spi.read(nbytes, *a, **kw)
                except Exception:
                    pass
                try:
                    buf = bytearray(nbytes)
                    if hasattr(self._spi, 'readinto'):
                        self._spi.readinto(buf)
                        return bytes(buf)
                    if hasattr(self._spi, 'write_readinto'):
                        out = bytes([0]*nbytes)
                        self._spi.write_readinto(out, buf)
                        return bytes(buf)
                except Exception:
                    pass
                return bytes([0]*nbytes)
            def readinto(self, buf, *a, **kw):
                try:
                    return self._spi.readinto(buf, *a, **kw)
                except Exception:
                    return None
            def write_readinto(self, out, into, *a, **kw):
                try:
                    return self._spi.write_readinto(out, into, *a, **kw)
                except Exception:
                    return None
            def deinit(self, *a, **kw):
                try:
                    if hasattr(self._spi, 'deinit'):
                        return self._spi.deinit(*a, **kw)
                except Exception:
                    pass
                return None
        return _SPIShim(spi)
    except Exception:
        return None

async def init_lora():
    global lora
    print('[DEBUG] init_lora start')
    try:
        # Defensive hardware prep: ensure CS high (inactive), RST pulsed, BUSY/IRQ as inputs
        try:
            _safe_pin_out(settings.CS_PIN, 1)  # CS high
        except Exception:
            pass
        try:
            _safe_pin_input(settings.BUSY_PIN)
            _safe_pin_input(settings.IRQ_PIN)
        except Exception:
            pass
        # Pulse reset to try to put chip into known state before instantiation
        try:
            _pulse_reset(settings.RST_PIN, low_ms=50, post_high_ms=120)
        except Exception:
            pass

        print('[DEBUG] init_lora: BEFORE SX1262 instantiation (pins prepped)')
        lora = SX1262(
            settings.SPI_BUS, settings.CLK_PIN, settings.MOSI_PIN, settings.MISO_PIN,
            settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN
        )
        print('[DEBUG] init_lora: SX1262 object created')
        # Ensure any leftover SPI is clean
        _deinit_spi_if_any(lora)
        # Guarded begin: retry and attempt to attach a machine.SPI instance if the driver
        # throws an AttributeError referencing a missing 'write' (common when SPI wasn't bound).
        async def _attempt_begin(lo, attempts=3):
            # Try proactively attaching a shim (helps drivers that expect spi already present)
            try:
                shim = _attach_spi_shim()
                if shim and not getattr(lo, 'spi', None):
                    lo.spi = shim
                    await debug_print("lora: pre-attached machine.SPI shim before begin attempts", "LORA")
            except Exception:
                pass

            # Try several begin invocation patterns to handle differing driver signatures
            for i in range(attempts):
                try:
                    # Preferred / full signature first
                    status = lo.begin(
                        freq=settings.FREQ, bw=settings.BW, sf=settings.SF, cr=settings.CR,
                        syncWord=settings.SYNC_WORD, power=settings.POWER,
                        currentLimit=settings.CURRENT_LIMIT, preambleLength=settings.PREAMBLE_LEN,
                        implicit=False, implicitLen=0xFF, crcOn=settings.CRC_ON, txIq=False, rxIq=False,
                        tcxoVoltage=settings.TCXO_VOLTAGE, useRegulatorLDO=settings.USE_LDO
                    )
                    return status
                except AttributeError as ae:
                    # Missing attribute on underlying SPI/native binding: attach shim and retry
                    try:
                        msg = str(ae)
                    except Exception:
                        msg = ''
                    await debug_print(f"lora.begin AttributeError: {msg}", "ERROR")
                    try:
                        shim = _attach_spi_shim()
                        if shim:
                            lo.spi = shim
                            await debug_print("lora: attached machine.SPI shim and retrying begin", "LORA")
                        else:
                            await debug_print("lora: no usable machine.SPI instance available", "ERROR")
                    except Exception:
                        pass
                    try:
                        _time.sleep_ms(120)
                    except Exception:
                        pass
                    continue
                except TypeError as te:
                    # Some ports/drivers may raise TypeError (unexpected keyword arg). Try fallback signatures.
                    try:
                        msg = str(te)
                    except Exception:
                        msg = ''
                    await debug_print(f"lora.begin TypeError: {msg} (attempt {i+1})", "WARN")
                    # Try reduced signatures one-by-one
                    tried = False
                    try:
                        # Minimal kwargs
                        status = lo.begin(freq=settings.FREQ, power=settings.POWER)
                        return status
                    except Exception:
                        tried = True
                    try:
                        # Positional: freq, bw, sf
                        status = lo.begin(settings.FREQ, settings.BW, settings.SF)
                        return status
                    except Exception:
                        pass
                    # Try attaching a fresh SPI shim and re-instantiating driver with spi object if constructor allows
                    try:
                        shim = _attach_spi_shim()
                        if shim:
                            try:
                                # Some SX1262 wrappers accept a pre-constructed SPI instance as first argument
                                try:
                                    lo2 = SX1262(shim, settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN)
                                except Exception:
                                    # Try keyword form
                                    lo2 = SX1262(spi=shim, cs=settings.CS_PIN, irq=settings.IRQ_PIN, rst=settings.RST_PIN, busy=settings.BUSY_PIN)
                                # swap and retry begin
                                lo = lo2
                                status = lo.begin(freq=settings.FREQ)
                                return status
                            except Exception as re:
                                await debug_print(f"lora: re-instantiation with SPI shim failed: {re}", "ERROR")
                    except Exception:
                        pass
                    # Give a small settle time and try again outer loop
                    try:
                        _time.sleep_ms(120)
                    except Exception:
                        pass
                    continue
                except Exception as e:
                    await debug_print(f"lora.begin exception: {e}", "ERROR")
                    return -999
            return -999

        status = await _attempt_begin(lora, attempts=2)
        print(f'[DEBUG] init_lora: lora.begin() returned {status}')
        # If chip not found, attempt diagnostics, re-instantiation with shim, reset and a single retry.
        if status == -2:
            await debug_print('lora: chip not found, performing diagnostics & retry', 'LORA')
            try:
                # Diagnostics: device errors, status, and SPI presence/type
                try:
                    dev_err = lora.getDeviceErrors()
                    await debug_print(f"lora: device errors 0x{dev_err:04X}", "LORA")
                except Exception:
                    pass
                try:
                    st = lora.getStatus()
                    await debug_print(f"lora: status {st}", "LORA")
                except Exception:
                    pass
                try:
                    spi_obj = getattr(lora, 'spi', None)
                    await debug_print(f"lora: spi present? {bool(spi_obj)} type={type(spi_obj)} has_write={hasattr(spi_obj, 'write') if spi_obj else False}", "LORA")
                except Exception:
                    pass

                # Try to reinstantiate driver using a shim (some ports accept an SPI instance in constructor)
                try:
                    shim = _attach_spi_shim()
                    if shim:
                        await debug_print("lora: attempting re-instantiation with SPI shim", "LORA")
                        newlo = None
                        try:
                            # positional variant (common)
                            newlo = SX1262(shim, settings.CS_PIN, settings.IRQ_PIN, settings.RST_PIN, settings.BUSY_PIN)
                        except Exception:
                            # Try keyword form
                            newlo = SX1262(spi=shim, cs=settings.CS_PIN, irq=settings.IRQ_PIN, rst=settings.RST_PIN, busy=settings.BUSY_PIN)
                        # swap and retry begin
                        lora = newlo
                        status = await _attempt_begin(lora, attempts=1)
                        if status == -2:
                            await debug_print("lora: re-instantiation failed, still chip not found", "ERROR")
                        else:
                            await debug_print("lora: re-instantiation with SPI shim succeeded", "LORA")
                    else:
                        await debug_print("lora: no SPI shim available for re-instantiation", "ERROR")
                except Exception as e:
                    await debug_print(f"lora: re-instantiation attempt failed: {e}", "ERROR")
            except Exception as e:
                await debug_print(f"lora: diagnostics failed: {e}", "ERROR")

        if status != 0:
            await debug_print(f"lora: begin failed status={status}", "ERROR")
            return False

        # Optional: set blocking (prefer non-blocking for asyncio, but match your previous)
        try:
            lora.setBlockingCallback(False)
        except Exception:
            pass

        # NEW: start RX on init for base/remote (remote needs for ACK)
        try:
            lora.setOperatingMode(lora.MODE_RX)
        except Exception:
            pass
        try:
            lora.startReceive()
        except Exception:
            pass

        await debug_print("LoRa: initialized", "LORA")
        return True
    except Exception as e:
        tb = ''
        try:
            import sys
            sys.print_exception(e)
            tb = ' | tb=' + str(e)
        except Exception:
            tb = ''
        await debug_print(f"init_lora exception: {e}{tb}", "ERROR")
        return False

async def _deinit_lora():
    global lora
    if lora is None:
        return
    try:
        await debug_print("LoRa: deinitializing...", "LORA")
        try:
            lora.setOperatingMode(lora.MODE_STDBY)
        except Exception:
            pass
        try:
            lora.standby()
        except Exception:
            pass
        try:
            lora.reset()
        except Exception:
            pass
        _deinit_spi_if_any(lora)
        lora = None
        await debug_print("LoRa: deinitialized", "LORA")
    except Exception as e:
        await debug_print(f"_deinit_lora error: {e}", "ERROR")
    # Free pins (optional)
    try:
        free_pins()
    except Exception:
        pass