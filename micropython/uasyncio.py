"""
CPython/Zero shim for MicroPython's uasyncio API.

This module exists because some firmware modules import uasyncio directly.
On MicroPython, the built-in/frozen uasyncio should be used.
On CPython (Zero), we map the subset used by this repo onto asyncio.
"""

import sys

try:
    _is_mpy = str(getattr(sys.implementation, "name", "")).lower() == "micropython"
except Exception:
    _is_mpy = False

if _is_mpy:
    # On MicroPython, prefer the real uasyncio (frozen). If this file is loaded anyway,
    # provide a minimal compatible surface using whatever is available.
    try:
        import uasyncio as _ua  # type: ignore  # may resolve to frozen module on some ports
    except Exception:
        _ua = None  # type: ignore

    if _ua is not None:
        # Re-export commonly used names
        sleep = _ua.sleep
        sleep_ms = getattr(_ua, "sleep_ms", None)
        create_task = _ua.create_task
        Lock = getattr(_ua, "Lock", None)
        Event = getattr(_ua, "Event", None)
        get_event_loop = getattr(_ua, "get_event_loop", None)

        def run(coro):
            return _ua.run(coro)
    else:
        raise ImportError("uasyncio unavailable on this MicroPython build")
else:
    import asyncio as _a  # CPython

    sleep = _a.sleep

    async def sleep_ms(ms: int):
        return await _a.sleep(float(ms) / 1000.0)

    create_task = _a.create_task
    Lock = _a.Lock
    Event = _a.Event
    get_event_loop = _a.get_event_loop

    def run(coro):
        return _a.run(coro)

__all__ = [
    "sleep",
    "sleep_ms",
    "create_task",
    "Lock",
    "Event",
    "get_event_loop",
    "run",
]
