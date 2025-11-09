"""
TMON frost/heat operations helpers
- Tighten LoRa sync interval during active frost/heat conditions
- Write simple operational events to ops log

Non-blocking: these functions only adjust settings and append a tiny log line.
"""

# Firmware Version: 2.0.0i

try:
    import utime as time
except Exception:
    import time

import ujson

try:
    import settings
except Exception:
    settings = None

from utils import debug_print

# Module state for active modes and saved baseline interval
_ops_log_file = None
_active_modes = set()  # {'frost','heat'}
_saved_base_interval = None  # seconds

def _ops_log_path():
    global _ops_log_file
    if _ops_log_file:
        return _ops_log_file
    try:
        log_dir = getattr(settings, 'LOG_DIR', '/logs')
        _ops_log_file = log_dir + '/ops.log'
    except Exception:
        _ops_log_file = '/logs/ops.log'
    return _ops_log_file

def _write_op_log(event, data=None):
    try:
        entry = {
            'ts': int(time.time()),
            'event': event,
            'data': data or {}
        }
        path = _ops_log_path()
        # Append one JSON line per entry (compact)
        with open(path, 'a') as f:
            f.write(ujson.dumps(entry) + "\n")
    except Exception:
        pass

def _get_current_base_interval():
    """Return the base interval seconds used by the base scheduler.
    lora.py reads settings.nextLoraSync as the base interval if <= 100000.
    """
    try:
        iv = getattr(settings, 'nextLoraSync', 300)
        if not isinstance(iv, (int, float)):
            return 300
        # If an absolute epoch was accidentally stored, fall back to default 300s
        return iv if iv <= 100000 else 300
    except Exception:
        return 300

def _apply_base_interval(new_seconds):
    """Apply a tighter base interval on the base station.
    Safe on remotes as it is ignored there.
    """
    try:
        if new_seconds < 1:
            new_seconds = 1
        if new_seconds > 24 * 3600:
            new_seconds = 24 * 3600
        setattr(settings, 'nextLoraSync', int(new_seconds))
    except Exception:
        pass

def _recalc_interval():
    """Recalculate desired interval from active modes, or restore baseline."""
    global _saved_base_interval
    # Baseline save
    if _saved_base_interval is None:
        _saved_base_interval = _get_current_base_interval()

    if not _active_modes:
        # Restore
        _apply_base_interval(_saved_base_interval)
        _write_op_log('ops_restore_interval', {'interval_s': _saved_base_interval})
        return

    # Compute minimal interval among active modes
    frost_iv = getattr(settings, 'FROSTWATCH_LORA_INTERVAL', 60)
    heat_iv = getattr(settings, 'HEATWATCH_LORA_INTERVAL', 120)
    wanted = []
    if 'frost' in _active_modes:
        wanted.append(frost_iv)
    if 'heat' in _active_modes:
        wanted.append(heat_iv)
    if not wanted:
        wanted = [_saved_base_interval]
    new_iv = int(min(max(1, int(wanted[0])), 24 * 3600)) if len(wanted) == 1 else int(min([max(1, int(x)) for x in wanted]))
    _apply_base_interval(new_iv)
    _write_op_log('ops_set_interval', {'interval_s': new_iv, 'modes': list(_active_modes)})


async def frostwatchCheck():
    """Called when frost condition is detected; ensure frost operations active."""
    if 'frost' not in _active_modes:
        _active_modes.add('frost')
        await beginFrostOperations()

async def heatwatchCheck():
    """Called when heat condition is detected; ensure heat operations active."""
    if 'heat' not in _active_modes:
        _active_modes.add('heat')
        await beginHeatOperations()

async def beginFrostOperations():
    await debug_print("Frostwatch Operations Start", "FROSTWATCH")
    try:
        _recalc_interval()
    except Exception:
        pass

async def beginHeatOperations():
    await debug_print("Heatwatch Operations Start", "HEATWATCH")
    try:
        _recalc_interval()
    except Exception:
        pass

async def endFrostOperations():
    if 'frost' in _active_modes:
        _active_modes.discard('frost')
        await debug_print("Frostwatch Operations End", "FROSTWATCH")
        try:
            _recalc_interval()
        except Exception:
            pass

async def endHeatOperations():
    if 'heat' in _active_modes:
        _active_modes.discard('heat')
        await debug_print("Heatwatch Operations End", "HEATWATCH")
        try:
            _recalc_interval()
        except Exception:
            pass

async def maybe_end_ops(cur_temp_f):
    """Auto-relax active modes using hysteresis thresholds."""
    try:
        frost_active = 'frost' in _active_modes
        heat_active = 'heat' in _active_modes
        fa = getattr(settings, 'FROSTWATCH_ACTIVE_TEMP', 70)
        ha = getattr(settings, 'HEATWATCH_ACTIVE_TEMP', 90)
        frost_clear = getattr(settings, 'FROSTWATCH_CLEAR_TEMP', fa + 3)
        heat_clear = getattr(settings, 'HEATWATCH_CLEAR_TEMP', ha - 3)
        if frost_active and cur_temp_f >= frost_clear:
            await endFrostOperations()
        if heat_active and cur_temp_f <= heat_clear:
            await endHeatOperations()
    except Exception:
        pass