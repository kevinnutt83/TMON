"""
Minimal CPython/Zero-compatible shim for MicroPython's framebuf module.

Only implements the surface used by oled.py when imported.
"""

MONO_VLSB = 0

class FrameBuffer:
    def __init__(self, buffer, width, height, format=MONO_VLSB):
        self.buffer = buffer
        self.width = int(width)
        self.height = int(height)
        self.format = format

    def fill(self, c):
        return None

    def pixel(self, x, y, c=None):
        return 0

    def text(self, s, x, y, c=1):
        return None

    def rect(self, x, y, w, h, c):
        return None

    def fill_rect(self, x, y, w, h, c):
        return None
