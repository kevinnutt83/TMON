# TMON v2.01.0 - Relay control with safety caps and runtime telemetry
# Full safety limits (per-relay and global), async runtime tracker, sdata updates,
# CLI-compatible toggle_relay. Works seamlessly with LoRa on Core 1.

import uasyncio as asyncio
import machine
import sdata
import settings
from utils import debug_print, led_status_flash

# Internal state per relay
_relay_tasks = {}
_relay_start_ts = {}

def _relay_enabled(n: int) -> bool:
    try:
        return bool(getattr(settings, f'ENABLE_RELAY{n}', False))
    except Exception:
        return False

def _relay_pin(n: int):
    try:
        pin_num = getattr(settings, f'RELAY_PIN{n}')
        return machine.Pin(pin_num, machine.Pin.OUT)
    except Exception:
        return None

def _relay_runtime_cap_s(n: int, requested_s: int) -> int:
    try:
        base_min = int(getattr(settings, 'RELAY_SAFETY_MAX_RUNTIME_MIN', 1440))
    except Exception:
        base_min = 1440
    try:
        override = int(getattr(settings, 'RELAY_RUNTIME_LIMITS', {}).get(int(n), base_min))
    except Exception:
        override = base_min
    cap_s = max(0, min(requested_s, override * 60))
    return cap_s

def _set_sdata_on(n: int, on: bool):
    try:
        setattr(sdata, f'relay{n}_on', bool(on))
    except Exception:
        pass
    # Initialize runtime counter
    try:
        key = f'relay{n}_runtime_s'
        if not hasattr(sdata, key):
            setattr(sdata, key, 0)
    except Exception:
        pass

async def _runtime_tracker(n: int):
    key = f'relay{n}_runtime_s'
    while getattr(sdata, f'relay{n}_on', False):
        try:
            cur = getattr(sdata, key, 0)
            setattr(sdata, key, int(cur) + 1)
        except Exception:
            pass
        await asyncio.sleep(1)

async def toggle_relay(relay_num, state, runtime="0"):
    """Main public function - called from CLI and LoRa CMD"""
    try:
        if not relay_num.isdigit() or not (1 <= int(relay_num) <= 8):
            await debug_print(f"Invalid relay number: {relay_num} (must be 1-8)", "ERROR")
            return
        n = int(relay_num)
        if not _relay_enabled(n):
            await debug_print(f"Relay {n} disabled by settings", "WARN")
            return

        pin = _relay_pin(n)
        if pin is None:
            await debug_print(f"Missing pin for relay {n}", "ERROR")
            return

        on = state.lower() == 'on'
        current_state = 1 if on else 0

        pin.value(current_state)
        _set_sdata_on(n, on)
        await debug_print(f"Relay {n} set to {state}", "COMMAND")
        led_status_flash(f'RELAY_{n}_{"ON" if on else "OFF"}')

        # Cancel any existing tracker if turning off
        if not on:
            t = _relay_tasks.get(n)
            if t:
                try:
                    t.cancel()
                except Exception:
                    pass
                _relay_tasks[n] = None
            return

        # Turn on with runtime limit
        if runtime != '0':
            try:
                req_s = int(runtime)
            except Exception:
                req_s = 0
            limit_s = _relay_runtime_cap_s(n, req_s)
            if limit_s == 0 and req_s > 0:
                await debug_print(f"Relay {n} runtime capped to 0s (safety)", "WARN")
                pin.value(0)
                _set_sdata_on(n, False)
                return
            if limit_s < req_s:
                await debug_print(f"Relay {n} runtime capped to {limit_s}s (requested {req_s}s)", "WARN")

            _set_sdata_on(n, True)
            try:
                _relay_tasks[n] = asyncio.create_task(_runtime_tracker(n))
            except Exception:
                pass
            await asyncio.sleep(limit_s)
            pin.value(0)
            _set_sdata_on(n, False)
            await debug_print(f"Relay {n} reverted after {limit_s}s", "COMMAND")
            led_status_flash(f'RELAY_{n}_OFF')

    except Exception as e:
        await debug_print(f"Error in toggle_relay: {str(e)}", "ERROR")

# ===================== End of relay.py =====================