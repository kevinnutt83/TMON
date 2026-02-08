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

    def _in_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height

    def _idx_mask(self, x, y):
        # MONO_VLSB: one byte per vertical 8px column; LSB is top pixel in the byte.
        page = (y >> 3)
        idx = int(x) + self.width * page
        mask = 1 << (y & 7)
        return idx, mask

    def fill(self, c):
        v = 0xFF if c else 0x00
        try:
            buf = self.buffer
            for i in range(len(buf)):
                buf[i] = v
        except Exception:
            pass
        return None

    def pixel(self, x, y, c=None):
        try:
            x = int(x); y = int(y)
            if not self._in_bounds(x, y):
                return 0
            idx, mask = self._idx_mask(x, y)
            if c is None:
                return 1 if (self.buffer[idx] & mask) else 0
            if c:
                self.buffer[idx] |= mask
            else:
                self.buffer[idx] &= (~mask) & 0xFF
        except Exception:
            return 0
        return None

    def rect(self, x, y, w, h, c):
        try:
            x = int(x); y = int(y); w = int(w); h = int(h)
            if w <= 0 or h <= 0:
                return None
            # top/bottom
            self.fill_rect(x, y, w, 1, c)
            self.fill_rect(x, y + h - 1, w, 1, c)
            # left/right
            self.fill_rect(x, y, 1, h, c)
            self.fill_rect(x + w - 1, y, 1, h, c)
        except Exception:
            pass
        return None

    def fill_rect(self, x, y, w, h, c):
        try:
            x = int(x); y = int(y); w = int(w); h = int(h)
            if w <= 0 or h <= 0:
                return None

            # Clamp to framebuffer bounds
            x0 = max(0, x)
            y0 = max(0, y)
            x1 = min(self.width, x + w)
            y1 = min(self.height, y + h)
            if x0 >= x1 or y0 >= y1:
                return None

            for yy in range(y0, y1):
                for xx in range(x0, x1):
                    self.pixel(xx, yy, c)
        except Exception:
            pass
        return None

    def text(self, s, x, y, c=1):
        # Optional: render via Pillow if present; otherwise no-op (keeps import/runtime safe).
        try:
            from PIL import Image, ImageDraw, ImageFont  # type: ignore
        except Exception:
            return None

        try:
            s = str(s)
            x = int(x); y = int(y)
            font = ImageFont.load_default()

            # Determine a tight bbox for the string
            try:
                bbox = font.getbbox(s)
                tw = max(1, bbox[2] - bbox[0])
                th = max(1, bbox[3] - bbox[1])
                ox = -bbox[0]; oy = -bbox[1]
            except Exception:
                tw, th = max(1, len(s) * 8), 8
                ox = oy = 0

            img = Image.new("1", (tw, th), 0)
            draw = ImageDraw.Draw(img)
            draw.text((ox, oy), s, font=font, fill=1)

            px = img.load()
            for yy in range(th):
                for xx in range(tw):
                    if px[xx, yy]:
                        self.pixel(x + xx, y + yy, 1 if c else 0)
        except Exception:
            pass
        return None
