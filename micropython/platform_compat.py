"""
TMON platform compatibility shim.

Goal:
- Keep firmware logic unchanged while allowing the same modules to import on:
  - MicroPython (pico/esp32): use uasyncio/urequests/ujson/utime/machine/network/framebuf
  - CPython (zero): use asyncio/requests/json/time and provide minimal stubs for machine/network/framebuf

Selection is keyed off settings.MCU_TYPE ('pico'|'esp32'|'zero').
"""

from __future__ import annotations

import sys
import types

# --- settings / MCU selection ---
try:
    import settings as _settings
except Exception:
    _settings = None

def _mcu_type() -> str:
    try:
        v = getattr(_settings, "MCU_TYPE", "") if _settings else ""
        v = (v or "").strip().lower()
        if v:
            return v
    except Exception:
        pass
    # Fallback: infer from interpreter
    try:
        return "zero" if getattr(sys.implementation, "name", "") != "micropython" else "esp32"
    except Exception:
        return "zero"

MCU_TYPE = _mcu_type()
IS_ZERO = MCU_TYPE == "zero"
IS_MICROPYTHON = not IS_ZERO and (getattr(sys.implementation, "name", "") == "micropython")

# --- asyncio ---
try:
    import uasyncio as asyncio  # type: ignore
except Exception:
    import asyncio  # type: ignore

# --- json ---
try:
    import ujson as json  # type: ignore
except Exception:
    import json  # type: ignore

# --- requests ---
requests = None
if IS_MICROPYTHON:
    try:
        import urequests as requests  # type: ignore
    except Exception:
        requests = None
else:
    try:
        import requests as requests  # type: ignore
    except Exception:
        requests = None

# --- time / ticks shims ---
try:
    import utime as _time  # type: ignore
except Exception:
    import time as _time  # type: ignore

# Provide MicroPython-style APIs when running on CPython.
if not hasattr(_time, "ticks_ms"):
    _t0 = _time.monotonic()

    def ticks_ms() -> int:
        return int((_time.monotonic() - _t0) * 1000)

    def ticks_diff(a: int, b: int) -> int:
        return int(a - b)

    def sleep_ms(ms: int) -> None:
        _time.sleep(float(ms) / 1000.0)

    _time.ticks_ms = ticks_ms  # type: ignore[attr-defined]
    _time.ticks_diff = ticks_diff  # type: ignore[attr-defined]
    _time.sleep_ms = sleep_ms  # type: ignore[attr-defined]

time = _time

# --- os ---
import os  # noqa: E402

# --- gc / mem_free shim ---
try:
    import gc as gc  # type: ignore
except Exception:
    gc = None  # type: ignore

if gc and not hasattr(gc, "mem_free"):
    def _mem_free() -> int:
        return 0
    gc.mem_free = _mem_free  # type: ignore[attr-defined]

# --- machine/network/framebuf (MicroPython-only) + stubs ---
try:
    if IS_MICROPYTHON:
        import machine as machine  # type: ignore
    else:
        raise ImportError()
except Exception:
    machine = types.SimpleNamespace()

    class Pin:  # minimal no-op stub
        IN = 0
        OUT = 1
        PULL_UP = 2
        PULL_DOWN = 3

        def __init__(self, *args, **kwargs):
            self._v = 0

        def value(self, v=None):
            if v is None:
                return self._v
            self._v = 1 if v else 0
            return self._v

    class UART:  # minimal no-op stub
        def __init__(self, *args, **kwargs):
            pass

        def write(self, *args, **kwargs):
            return 0

        def any(self):
            return 0

        def read(self, *args, **kwargs):
            return b""

    class I2C:  # minimal no-op stub
        def __init__(self, *args, **kwargs):
            pass

        def writeto_mem(self, *args, **kwargs):
            return 0

        def readfrom_mem(self, addr, mem, n, *args, **kwargs):
            try:
                n = int(n)
            except Exception:
                n = 0
            return bytes([0] * max(0, n))

    class SPI:  # minimal no-op stub
        def __init__(self, *args, **kwargs):
            pass

        def init(self, *args, **kwargs):
            return None

        def write(self, *args, **kwargs):
            return None

        def read(self, nbytes, *args, **kwargs):
            return bytes([0] * int(nbytes))

        def readinto(self, *args, **kwargs):
            return None

        def write_readinto(self, *args, **kwargs):
            return None

        def deinit(self, *args, **kwargs):
            return None

    class ADC:  # minimal no-op stub
        def __init__(self, *args, **kwargs):
            pass

        def read_u16(self):
            return 0

    def soft_reset():
        # Keep callsites intact; on Zero this is a no-op.
        return None

    machine.Pin = Pin
    machine.UART = UART
    machine.I2C = I2C
    machine.SPI = SPI
    machine.ADC = ADC
    machine.soft_reset = soft_reset

Pin = getattr(machine, "Pin", None)
UART = getattr(machine, "UART", None)
I2C = getattr(machine, "I2C", None)
SPI = getattr(machine, "SPI", None)
ADC = getattr(machine, "ADC", None)

try:
    if IS_MICROPYTHON:
        import network as network  # type: ignore
    else:
        raise ImportError()
except Exception:
    network = None

try:
    if IS_MICROPYTHON:
        import framebuf as framebuf  # type: ignore
    else:
        raise ImportError()
except Exception:
    framebuf = None

__all__ = [
    "MCU_TYPE",
    "IS_ZERO",
    "IS_MICROPYTHON",
    "asyncio",
    "json",
    "requests",
    "time",
    "os",
    "gc",
    "machine",
    "Pin",
    "UART",
    "I2C",
    "SPI",
    "ADC",
    "network",
    "framebuf",
]
