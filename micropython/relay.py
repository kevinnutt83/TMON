"""Relay control with safety caps and runtime telemetry.
Firmware Version: v2.06.0
"""
try:
    from platform_compat import asyncio, machine  # CHANGED: unified import for MicroPython + CPython (Zero)
except Exception:
    import uasyncio as asyncio
    import machine

import sdata
import settings
from utils import debug_print

# Internal state per relay: start time and scheduled task
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
    # Initialize runtime counters in sdata
    try:
        key = f'relay{n}_runtime_s'
        if not hasattr(sdata, key):
            setattr(sdata, key, 0)
    except Exception:
        pass

async def _runtime_tracker(n: int):
    key = f'relay{n}_runtime_s'
    _relay_start_ts[n] = _relay_start_ts.get(n) or 0
    while getattr(sdata, f'relay{n}_on', False):
        try:
            cur = getattr(sdata, key, 0)
            setattr(sdata, key, int(cur) + 1)
        except Exception:
            pass
        await asyncio.sleep(1)

async def toggle_relay(relay_num, state, runtime):
    try:
        # Validate relay_num (1-8)
        if not relay_num.isdigit() or not (1 <= int(relay_num) <= 8):
            await debug_print(f"Invalid relay number: {relay_num} (must be 1-8)", "ERROR")
            return
        n = int(relay_num)
        if not _relay_enabled(n):
            await debug_print(f"Relay {n} disabled by settings", "WARN")
            return

        # Get pin from settings (e.g., settings.RELAY_PIN1)
        pin_attr = f"RELAY_PIN{n}"
        if not hasattr(settings, pin_attr):
            await debug_print(f"Missing pin setting: {pin_attr}", "ERROR")
            return
        pin_num = getattr(settings, pin_attr)
        pin = machine.Pin(pin_num, machine.Pin.OUT)

        # Get sdata variable (e.g., 'relay1_on')
        sdata_var = f"relay{n}_on"
        if not hasattr(sdata, sdata_var):
            await debug_print(f"Missing sdata variable: {sdata_var}", "ERROR")
            return

        on = state.lower() == 'on'
        current_state = 1 if on else 0  # Assume active high: 1 = on, 0 = off

        pin.value(current_state)
        setattr(sdata, sdata_var, on)
        await debug_print(f"Relay {n} set to {state}", "COMMAND")

        # Cancel prior tracker if toggling off
        if not on:
            t = _relay_tasks.get(n)
            if t:
                try:
                    t.cancel()
                except Exception:
                    pass
                _relay_tasks[n] = None
            return

        if runtime != '0':
            try:
                req_s = int(runtime)
            except Exception:
                req_s = 0
            # Enforce safety caps
            limit_s = _relay_runtime_cap_s(n, req_s)
            if limit_s == 0 and req_s > 0:
                await debug_print(f"Relay {n} runtime capped to 0s (safety)", "WARN")
                pin.value(0)
                _set_sdata_on(n, False)
                return
            if limit_s < req_s:
                await debug_print(f"Relay {n} runtime capped to {limit_s}s (requested {req_s}s)", "WARN")
            # Start runtime tracker
            _set_sdata_on(n, True)
            try:
                _relay_tasks[n] = asyncio.create_task(_runtime_tracker(n))
            except Exception:
                pass
            await asyncio.sleep(limit_s)
            pin.value(0)
            _set_sdata_on(n, False)
            await debug_print(f"Relay {n} reverted after {limit_s}s", "COMMAND")

    except Exception as e:
        await debug_print(f"Error in toggle_relay: {str(e)}", "ERROR")