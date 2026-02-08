"""
CPython/Zero shim for MicroPython's uasyncio API.

On CPython/Zero: re-export asyncio primitives so legacy `import uasyncio as asyncio` keeps working.
On MicroPython: this file is expected to be ignored in favor of the built-in/frozen uasyncio.
"""

import sys as _sys

try:
    _is_mpy = str(getattr(_sys.implementation, "name", "")).lower() == "micropython"
except Exception:
    _is_mpy = False

try:
    import asyncio as _a  # CPython asyncio; also exists on some MicroPython builds
except Exception:
    _a = None  # type: ignore

if _a is None:
    # Minimal placeholders (should not be used in normal firmware paths)
    class CancelledError(Exception):
        pass
    def get_event_loop(): raise NotImplementedError("asyncio unavailable")
    def run(_coro): raise NotImplementedError("asyncio unavailable")
    def create_task(_coro): raise NotImplementedError("asyncio unavailable")
    async def sleep(_s): return None
    class Lock:
        def __init__(self): raise NotImplementedError("asyncio unavailable")
else:
    CancelledError = getattr(_a, "CancelledError", Exception)
    Lock = getattr(_a, "Lock")
    Event = getattr(_a, "Event", None)
    Queue = getattr(_a, "Queue", None)
    create_task = getattr(_a, "create_task")
    sleep = getattr(_a, "sleep")
    gather = getattr(_a, "gather", None)
    get_event_loop = getattr(_a, "get_event_loop")
    run = getattr(_a, "run")

__all__ = [
    "CancelledError",
    "Lock",
    "Event",
    "Queue",
    "create_task",
    "sleep",
    "gather",
    "get_event_loop",
    "run",
]
