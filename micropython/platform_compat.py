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
    try:
        return "zero" if getattr(sys.implementation, "name", "") != "micropython" else "esp32"
    except Exception:
        return "zero"

MCU_TYPE = _mcu_type()
IS_ZERO = MCU_TYPE == "zero"
IS_MICROPYTHON = (getattr(sys.implementation, "name", "") == "micropython") and not IS_ZERO

# --- asyncio ---
# CHANGED: On Zero/CPython, prefer stdlib asyncio explicitly (avoid importing a local uasyncio.py shim accidentally).
if IS_MICROPYTHON:
    try:
        import uasyncio as asyncio  # type: ignore
    except Exception:
        import asyncio  # type: ignore
else:
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

# --- machine (MicroPython-only) + stubs ---
try:
    if IS_MICROPYTHON:
        import machine as machine  # type: ignore
    else:
        raise ImportError()
except Exception:
    # Prefer machine_compat if present (but only if it provides the attributes we rely on)
    _mc = None
    try:
        import machine_compat as _mc  # type: ignore
    except Exception:
        _mc = None

    def _mc_ok(mod) -> bool:
        try:
            return all(hasattr(mod, k) for k in ("Pin", "I2C", "SPI", "UART", "ADC", "unique_id", "soft_reset"))
        except Exception:
            return False

    if _mc is not None and _mc_ok(_mc):
        machine = _mc  # type: ignore[assignment]
        try:
            sys.modules.setdefault("machine", _mc)
        except Exception:
            pass
    else:
        machine = types.SimpleNamespace()

        class Pin:
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
            def init(self, *a, **k):
                return None

        class UART:
            def __init__(self, *args, **kwargs): pass
            def write(self, *args, **kwargs): return 0
            def any(self): return 0
            def read(self, *args, **kwargs): return b""

        class I2C:
            def __init__(self, *args, **kwargs): pass
            def writeto(self, *args, **kwargs): return 0
            def writeto_mem(self, *args, **kwargs): return 0
            def readfrom_mem(self, addr, mem, n, *args, **kwargs):
                try:
                    n = int(n)
                except Exception:
                    n = 0
                return bytes([0] * max(0, n))
            def writevto(self, *args, **kwargs):
                return 0

        class SPI:
            def __init__(self, *args, **kwargs): pass
            def init(self, *args, **kwargs): return None
            def write(self, *args, **kwargs): return None
            def read(self, nbytes, *args, **kwargs): return bytes([0] * int(nbytes))
            def readinto(self, *args, **kwargs): return None
            def write_readinto(self, *args, **kwargs): return None
            def deinit(self, *args, **kwargs): return None

        class ADC:
            def __init__(self, *args, **kwargs): pass
            def read_u16(self): return 0

        def unique_id():
            # CHANGED: provide stable identity on Zero so utils.get_machine_id() is non-empty.
            try:
                if IS_ZERO:
                    try:
                        with open("/etc/machine-id", "r") as f:
                            mid = (f.read() or "").strip()
                    except Exception:
                        mid = ""
                    if not mid:
                        try:
                            import uuid as _uuid  # type: ignore
                            mid = hex(int(_uuid.getnode()))[2:]
                        except Exception:
                            mid = ""
                    try:
                        import hashlib as _hh  # type: ignore
                        return _hh.sha256(mid.encode("utf-8")).digest()[:12]
                    except Exception:
                        return (mid or "0").encode("utf-8")[:12]
            except Exception:
                pass
            return b""

        def soft_reset():
            raise SystemExit("soft_reset requested")

        machine.Pin = Pin
        machine.UART = UART
        machine.I2C = I2C
        machine.SPI = SPI
        machine.ADC = ADC
        machine.unique_id = unique_id
        machine.soft_reset = soft_reset

Pin = getattr(machine, "Pin", None)
UART = getattr(machine, "UART", None)
I2C = getattr(machine, "I2C", None)
SPI = getattr(machine, "SPI", None)
ADC = getattr(machine, "ADC", None)

# --- network stub on Zero ---
try:
    if IS_MICROPYTHON:
        import network as network  # type: ignore
    else:
        raise ImportError()
except Exception:
    network = types.ModuleType("network")
    network.STA_IF = 0  # type: ignore[attr-defined]

    class WLAN:
        def __init__(self, iface):
            self.iface = iface
            self._active = False
            self._connected = False
        def active(self, v=None):
            if v is None:
                return bool(self._active)
            self._active = bool(v)
            if not self._active:
                self._connected = False
            return bool(self._active)
        def isconnected(self):
            return bool(self._connected)
        def scan(self):
            return []
        def connect(self, *a, **kw):
            self._connected = False
            return None
        def ifconfig(self):
            return ("0.0.0.0", "0.0.0.0", "0.0.0.0", "0.0.0.0")
        def config(self, *a, **kw):
            if a and a[0] == "mac":
                return b"\x00\x00\x00\x00\x00\x00"
            if a and a[0] == "rssi":
                return -100
            return None
        def status(self, *a, **kw):
            if a and a[0] == "rssi":
                return -100
            return 0

    network.WLAN = WLAN  # type: ignore[attr-defined]
    try:
        sys.modules.setdefault("network", network)
    except Exception:
        pass

# --- framebuf shim ---
try:
    if IS_MICROPYTHON:
        import framebuf as framebuf  # type: ignore
    else:
        raise ImportError()
except Exception:
    _fb = None
    try:
        import framebuf_compat as _fb  # type: ignore
    except Exception:
        _fb = None
    framebuf = _fb
    if _fb is not None:
        try:
            sys.modules.setdefault("framebuf", _fb)
        except Exception:
            pass

# --- MicroPython module aliases on Zero ---
if IS_ZERO:
    def _alias(name: str, mod) -> None:
        try:
            if mod is not None and name not in sys.modules:
                sys.modules[name] = mod
        except Exception:
            pass

    _alias("uasyncio", asyncio)
    _alias("ujson", json)
    if requests is not None:
        _alias("urequests", requests)
    _alias("utime", time)
    _alias("uos", os)

# --- NeoPixel compatibility ---
NeoPixel = None
if IS_MICROPYTHON:
    try:
        from neopixel import NeoPixel as NeoPixel  # type: ignore
    except Exception:
        NeoPixel = None  # type: ignore
elif IS_ZERO:
    try:
        from rpi_ws281x import PixelStrip as _PixelStrip, Color as _Color  # type: ignore

        class NeoPixel:  # type: ignore[no-redef]
            def __init__(self, pin, n, bpp=3, timing=1):
                self.n = int(n or 0)
                gpio = None
                for attr in ("pin", "id", "gpio", "_id"):
                    try:
                        gpio = getattr(pin, attr)
                        break
                    except Exception:
                        pass
                if gpio is None:
                    try:
                        gpio = int(pin)
                    except Exception:
                        gpio = 18
                self._strip = _PixelStrip(self.n, int(gpio), freq_hz=800000, dma=10, invert=False, brightness=255)
                self._strip.begin()

            def __setitem__(self, i, rgb):
                try:
                    r, g, b = rgb
                except Exception:
                    r = g = b = 0
                self._strip.setPixelColor(int(i), _Color(int(g) & 255, int(r) & 255, int(b) & 255))

            def write(self):
                self._strip.show()

            def fill(self, rgb):
                for i in range(self.n):
                    self[i] = rgb
                self.write()

    except Exception:
        class NeoPixel:  # type: ignore[no-redef]
            def __init__(self, *_a, **_kw): self.n = 0
            def __setitem__(self, *_a, **_kw): return None
            def write(self): return None
            def fill(self, *_a, **_kw): return None

    try:
        _np_mod = types.ModuleType("neopixel")
        _np_mod.NeoPixel = NeoPixel  # type: ignore[attr-defined]
        sys.modules.setdefault("neopixel", _np_mod)
    except Exception:
        pass

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
    "NeoPixel",
]
