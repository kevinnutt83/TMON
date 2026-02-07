"""
CPython/Linux compatibility shim for code written against MicroPython's `machine` module.

Goal: allow modules to import on `MCU_TYPE="zero"` (Raspberry Pi Zero / Linux) without
crashing at import time. Hardware operations are best-effort and may raise if unsupported.
"""

import os
import time as _time
import uuid

# --- Reset helpers ---
def soft_reset():
	# Best-effort: exit process; systemd/supervisor can restart.
	raise SystemExit("soft_reset requested")

def reset():
	raise SystemExit("reset requested")

# --- Timing helpers commonly used in MicroPython ---
def ticks_ms():
	return int(_time.monotonic() * 1000)

def ticks_diff(a, b):
	return int(a) - int(b)

def sleep_ms(ms):
	_time.sleep(max(0, ms) / 1000.0)

# --- machine.unique_id() compatibility (used by many device-id flows) ---
def unique_id():
	# Prefer /etc/machine-id when present for stable identity on Linux
	try:
		with open("/etc/machine-id", "r") as f:
			mid = (f.read() or "").strip()
			if mid:
				return bytes.fromhex(mid[:32])
	except Exception:
		pass
	# Fallback: MAC-based UUID node value (may be stable)
	try:
		node = uuid.getnode()
		return int(node).to_bytes(6, "big", signed=False)
	except Exception:
		return b"\x00" * 6

# --- Pin shim (RPi.GPIO if available, otherwise in-memory no-op) ---
class Pin:
	IN = 0
	OUT = 1
	PULL_UP = 2
	PULL_DOWN = 3

	def __init__(self, pin, mode=OUT, pull=None):
		self.pin = pin
		self.mode = mode
		self.pull = pull
		self._val = 0
		self._gpio = None
		try:
			import RPi.GPIO as GPIO  # type: ignore
			self._gpio = GPIO
			GPIO.setwarnings(False)
			GPIO.setmode(GPIO.BCM)
			if mode == self.OUT:
				GPIO.setup(pin, GPIO.OUT)
			else:
				pud = GPIO.PUD_OFF
				if pull == self.PULL_UP:
					pud = GPIO.PUD_UP
				elif pull == self.PULL_DOWN:
					pud = GPIO.PUD_DOWN
				GPIO.setup(pin, GPIO.IN, pull_up_down=pud)
		except Exception:
			self._gpio = None

	def value(self, v=None):
		if v is None:
			if self._gpio:
				try:
					return int(self._gpio.input(self.pin))
				except Exception:
					return int(self._val)
			return int(self._val)
		self._val = 1 if v else 0
		if self._gpio:
			try:
				self._gpio.output(self.pin, self._val)
			except Exception:
				pass
		return self._val

	# NEW: common MicroPython Pin helpers used by some callsites
	def on(self):
		return self.value(1)

	def off(self):
		return self.value(0)

	def init(self, mode=None, pull=None):
		if mode is not None:
			self.mode = mode
		if pull is not None:
			self.pull = pull
		return None

# --- I2C shim (smbus2 if available) ---
class I2C:
	def __init__(self, bus, scl=None, sda=None, freq=100000):
		self.bus = bus
		self._dev = None
		try:
			from smbus2 import SMBus  # type: ignore
			self._dev = SMBus(bus)
		except Exception:
			self._dev = None

	def writeto(self, addr, buf):
		if not self._dev:
			raise RuntimeError("I2C not available")
		data = bytes(buf)
		if len(data) == 0:
			return 0
		# If first byte is a control byte (OLED style), just write raw as a block where possible
		try:
			self._dev.write_i2c_block_data(addr, data[0], list(data[1:]))
			return len(data)
		except Exception:
			# fallback: write byte-by-byte
			for b in data:
				self._dev.write_byte(addr, b)
			return len(data)

	def writevto(self, addr, seq):
		# seq is typically [prefix_bytes, data_bytes]
		out = b"".join(bytes(x) for x in seq if x is not None)
		return self.writeto(addr, out)

	def writeto_mem(self, addr, memaddr, data):
		if not self._dev:
			raise RuntimeError("I2C not available")
		self._dev.write_i2c_block_data(addr, memaddr, list(bytes(data)))

	def readfrom_mem(self, addr, memaddr, n):
		if not self._dev:
			raise RuntimeError("I2C not available")
		data = self._dev.read_i2c_block_data(addr, memaddr, n)
		return bytes(bytearray(data))

# --- SPI shim (spidev if available) ---
class SPI:
	def __init__(self, bus, baudrate=1000000, sck=None, mosi=None, miso=None):
		self.bus = bus
		self.baudrate = baudrate
		self._dev = None
		try:
			import spidev  # type: ignore
			self._dev = spidev.SpiDev()
			# On Linux spidev uses (bus, device). Default device 0.
			self._dev.open(int(bus), 0)
			self._dev.max_speed_hz = int(baudrate)
		except Exception:
			self._dev = None

	def init(self, baudrate=1000000, **_kw):
		self.baudrate = baudrate
		try:
			if self._dev:
				self._dev.max_speed_hz = int(baudrate)
		except Exception:
			pass

	def write(self, buf):
		if not self._dev:
			raise RuntimeError("SPI not available")
		self._dev.xfer2(list(bytes(buf)))

	def read(self, nbytes, write=0x00):
		if not self._dev:
			raise RuntimeError("SPI not available")
		return bytes(self._dev.xfer2([write] * int(nbytes)))

	def write_readinto(self, out, into):
		if not self._dev:
			raise RuntimeError("SPI not available")
		r = self._dev.xfer2(list(bytes(out)))
		into[:] = bytes(bytearray(r))

	def deinit(self):
		try:
			if self._dev:
				self._dev.close()
		except Exception:
			pass
		self._dev = None

# --- UART shim (pyserial if available) ---
class UART:
	def __init__(self, idx, baudrate=9600, parity=None, stop=1, tx=None, rx=None):
		self.idx = idx
		self.baudrate = baudrate
		self._ser = None
		try:
			import serial  # type: ignore
			# Convention: /dev/ttyS0 or /dev/ttyAMA0 on Pi; allow env override
			dev = os.getenv("TMON_UART_DEV", "/dev/ttyS0")
			self._ser = serial.Serial(dev, baudrate=baudrate, timeout=0)
		except Exception:
			self._ser = None

	def any(self):
		try:
			return self._ser.in_waiting if self._ser else 0
		except Exception:
			return 0

	def read(self, n=None):
		try:
			if not self._ser:
				return b""
			if n is None:
				n = self._ser.in_waiting or 1
			return self._ser.read(int(n))
		except Exception:
			return b""

	def write(self, data):
		try:
			if self._ser:
				return self._ser.write(bytes(data))
		except Exception:
			pass
		return 0

# --- ADC shim (often used for CPU temp / voltage on MCUs; not generally available on Pi Zero) ---
class ADC:
	def __init__(self, *_a, **_kw):
		pass
	def read_u16(self):
		return 0
