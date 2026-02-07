"""
CPython/Linux compatibility shim for MicroPython `framebuf`.

This is intentionally minimal: it only supports the attributes/methods
used by `oled.py` so the module can import on MCU_TYPE="zero".
"""

MONO_VLSB = 0

class FrameBuffer:
	def __init__(self, buffer, width, height, fmt=MONO_VLSB):
		self.buffer = buffer
		self.width = int(width)
		self.height = int(height)
		self.fmt = fmt

	def fill(self, *_a, **_kw): 
		return None

	def pixel(self, *_a, **_kw):
		return None

	def rect(self, *_a, **_kw):
		return None

	def fill_rect(self, *_a, **_kw):
		return None

	def text(self, *_a, **_kw):
		return None
