"""
CPython (Pi Zero) shim for MicroPython's `utime` module.

Purpose:
- Keep existing firmware imports working: `import utime as time`
- Provide minimal API used across TMON firmware: time/sleep, sleep_ms/us, ticks_ms/us, ticks_diff/add.

On MicroPython builds, the real `utime` is typically built-in; this file is intended for CPython only.
"""
import time as _time

_epoch0 = _time.monotonic()

def time():
    return _time.time()

def sleep(seconds):
    return _time.sleep(seconds)

def sleep_ms(ms):
    return _time.sleep(max(0.0, float(ms) / 1000.0))

def sleep_us(us):
    return _time.sleep(max(0.0, float(us) / 1_000_000.0))

def ticks_ms():
    return int((_time.monotonic() - _epoch0) * 1000)

def ticks_us():
    return int((_time.monotonic() - _epoch0) * 1_000_000)

def ticks_add(ticks, delta):
    return int(ticks) + int(delta)

def ticks_diff(ticks1, ticks2):
    return int(ticks1) - int(ticks2)

def localtime(secs=None):
    return _time.localtime(time() if secs is None else secs)

def mktime(t):
    return _time.mktime(t)
