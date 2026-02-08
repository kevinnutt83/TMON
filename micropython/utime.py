"""
CPython/Zero shim for MicroPython's utime API.

On CPython: wrap time and provide ticks_ms/ticks_diff/sleep_ms.
On MicroPython: the built-in/frozen utime should be used.
"""

import sys

try:
    _is_mpy = str(getattr(sys.implementation, "name", "")).lower() == "micropython"
except Exception:
    _is_mpy = False

if _is_mpy:
    # If this file is loaded on MicroPython, fall back to time-like functions if available.
    try:
        import utime as _t  # type: ignore
    except Exception:
        import time as _t  # type: ignore
else:
    import time as _t  # CPython

time = _t.time
sleep = _t.sleep
localtime = _t.localtime
gmtime = getattr(_t, "gmtime", None)

try:
    _t0 = _t.monotonic()
except Exception:
    _t0 = 0.0

def ticks_ms() -> int:
    try:
        return int((_t.monotonic() - _t0) * 1000)
    except Exception:
        return int(time() * 1000)

def ticks_diff(a: int, b: int) -> int:
    return int(a) - int(b)

def sleep_ms(ms: int) -> None:
    _t.sleep(float(ms) / 1000.0)

__all__ = ["time", "sleep", "localtime", "gmtime", "ticks_ms", "ticks_diff", "sleep_ms"]
