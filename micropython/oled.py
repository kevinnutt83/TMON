# TMON v2.01.0 - Polished non-blocking OLED
# Uses queue for banners (no hanging), signal bars for WiFi/LoRa, voltage/temp flip,
# sampling display in body, unit name in footer. Fully compatible with Core 1 LoRa.

import uasyncio as asyncio
import time
import settings
import sdata
import machine
import framebuf
from settings import OLED_SCL_PIN, OLED_SDA_PIN

# ===================== State =====================
_render_task = None
_status_queue = []           # Non-blocking banner queue
_body_override_lines = None
_body_override_until = 0
_last_render_sig = None
_show_voltage = True
_last_flip_time = 0

# Constants
HEADER_HEIGHT = int(getattr(settings, 'OLED_HEADER_HEIGHT', 16))
FOOTER_HEIGHT = int(getattr(settings, 'OLED_FOOTER_HEIGHT', 12))
BODY_TOP = HEADER_HEIGHT
BODY_BOTTOM = 64 - FOOTER_HEIGHT
BODY_HEIGHT = BODY_BOTTOM - BODY_TOP
FLIP_INTERVAL_S = int(getattr(settings, 'OLED_HEADER_FLIP_S', 4))
RENDER_INTERVAL_S = 0.4
MAX_TEXT_CHARS = 16

# ===================== SSD1309 Driver (full original) =====================
class SSD1309_I2C(framebuf.FrameBuffer):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.i2c = i2c
        self.addr = addr
        self.temp = bytearray(2)
        self.write_list = [b'\x40', None]
        self.external_vcc = external_vcc
        self.width = width
        self.height = height
        self.pages = height // 8
        self.buffer = bytearray(self.pages * self.width)
        self.col_start = 0
        self.col_end = self.col_start + self.width - 1
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_VLSB)
        self.init_display()

    def write_cmd(self, cmd):
        self.temp[0] = 0x00
        self.temp[1] = cmd
        self.i2c.writeto(self.addr, self.temp)

    def write_data(self, buf):
        self.write_list[1] = buf
        try:
            self.i2c.writevto(self.addr, self.write_list)
        except Exception:
            self.i2c.writeto(self.addr, b'\x40' + buf)

    def init_display(self):
        for cmd in (
            0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40,
            0x8D, 0x14 if not self.external_vcc else 0x10,
            0x20, 0x00, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF,
            0xD9, 0xF1 if not self.external_vcc else 0x22, 0xDB, 0x40,
            0xA4, 0xA6, 0xAF
        ):
            try:
                self.write_cmd(cmd)
            except Exception:
                pass
        self.fill(0)
        self.show()

    def show(self):
        try:
            self.write_cmd(0x21)
            self.write_cmd(self.col_start)
            self.write_cmd(self.col_end)
            self.write_cmd(0x22)
            self.write_cmd(0)
            self.write_cmd(self.pages - 1)
            self.write_data(self.buffer)
        except Exception:
            pass

    def poweroff(self):
        try:
            self.write_cmd(0xAE)
        except Exception:
            pass

    def poweron(self):
        try:
            self.write_cmd(0xAF)
        except Exception:
            pass

    def contrast(self, contrast):
        try:
            self.write_cmd(0x81)
            self.write_cmd(contrast)
        except Exception:
            pass

    def invert(self, invert):
        try:
            self.write_cmd(0xA6 | (invert & 1))
        except Exception:
            pass

# Initialize OLED
oled = None
if getattr(settings, 'ENABLE_OLED', False):
    try:
        i2c = machine.I2C(1, scl=machine.Pin(OLED_SCL_PIN), sda=machine.Pin(OLED_SDA_PIN), freq=100000)
        oled = SSD1309_I2C(128, 64, i2c, addr=0x3C)
    except Exception as e:
        print(f"[ERROR] OLED init failed: {e}")
        oled = None

# ===================== Helpers =====================
async def fade_display(on=True, steps=10, delay=0.03):
    if not oled:
        return
    if on:
        for c in range(0, 256, max(1, 255 // steps)):
            oled.contrast(c)
            await asyncio.sleep(delay)
        oled.contrast(255)
    else:
        for c in range(255, -1, -max(1, 255 // steps)):
            oled.contrast(c)
            await asyncio.sleep(delay)
        oled.contrast(0)

def _safe_attr(obj, name, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default

def _net_bars_from_rssi(rssi, cuts=(-60, -80, -90)):
    try:
        if rssi is None:
            return 0
        r = int(rssi)
        if r > cuts[0]: return 3
        if r > cuts[1]: return 2
        if r > cuts[2]: return 1
    except Exception:
        pass
    return 0

def _draw_bars(o, x, y, bars):
    try:
        for i in range(3):
            h = 3 + i * 3
            bx = x + i * 6
            by = y + 9 - h
            o.rect(bx, by, 4, h, 1)
            if i < bars:
                o.fill_rect(bx + 1, by + 1, 2, h - 2, 1)
    except Exception:
        pass

def _measure_text_w(text):
    try:
        return max(0, len(str(text)) * 8)
    except Exception:
        return 0

def _compact_label(txt, max_chars):
    try:
        s = str(txt or '')
        if len(s) <= max_chars:
            return s
        return s[:max_chars]
    except Exception:
        return str(txt)[:max_chars]

def _layout_header_right(vol_w, right_blocks):
    try:
        gap = 4
        total = sum(b.get('w', 0) + gap for b in right_blocks) - gap
        start_x = 128 - 2 - total
        xs = []
        cur = start_x
        for b in right_blocks:
            xs.append(cur)
            cur += b.get('w', 0) + gap
        return start_x, xs
    except Exception:
        return 128, [128] * len(right_blocks)

# ===================== Render Loop =====================
async def _render_loop():
    global _last_render_sig, _show_voltage, _last_flip_time, _body_override_lines, _body_override_until
    if not oled:
        return
    while True:
        try:
            now = time.time()
            if now - _last_flip_time >= FLIP_INTERVAL_S:
                _show_voltage = not _show_voltage
                _last_flip_time = now

            # Process status queue
            if _status_queue and now >= _status_queue[0][1]:
                _status_queue.pop(0)

            # Header
            oled.fill_rect(0, 0, 128, HEADER_HEIGHT, 0)
            try:
                voltage = _safe_attr(sdata, 'sys_voltage', 0.0)
                rtemp = _safe_attr(sdata, 'cur_temp_f', None)
                txt = f"{voltage:.2f}V" if _show_voltage else (f"{rtemp:.1f}F" if rtemp is not None else "--.-F")
                oled.text(txt, 2, 0)
                vol_w = _measure_text_w(txt) + 4
            except Exception:
                vol_w = 16

            # Signal bars (WiFi + LoRa)
            blocks = []
            # WiFi block
            if getattr(settings, 'ENABLE_WIFI', False):
                wifi_text = 'No Con' if not getattr(sdata, 'WIFI_CONNECTED', False) else ''
                wb = _net_bars_from_rssi(_safe_attr(sdata, 'wifi_rssi', None))
                w = _measure_text_w('W') + 2 + 18 + (_measure_text_w(wifi_text) + 4 if wifi_text else 0)
                blocks.append({'icon': 'W', 'bars': wb, 'text': wifi_text, 'w': w})
            # LoRa block
            if getattr(settings, 'ENABLE_LORA', False):
                lora_text = 'Search' if getattr(settings, 'NODE_TYPE', '') == 'remote' else 'No Con'
                lb = _net_bars_from_rssi(_safe_attr(sdata, 'lora_SigStr', None), (-60, -90, -120))
                w = _measure_text_w('L') + 2 + 18 + (_measure_text_w(lora_text) + 4 if lora_text else 0)
                blocks.append({'icon': 'L', 'bars': lb, 'text': lora_text, 'w': w})

            start_x, xs = _layout_header_right(vol_w, blocks)
            for b, x in zip(blocks, xs):
                oled.text(b['icon'], x, 0)
                _draw_bars(oled, x + _measure_text_w(b['icon']) + 2, 0, b['bars'])
                if b['text']:
                    oled.text(b['text'], x + _measure_text_w(b['icon']) + 2 + 18 + 4, 0)

            # Body
            oled.fill_rect(0, BODY_TOP, 128, BODY_HEIGHT, 0)
            if _status_queue:
                txt = _status_queue[0][0]
                bx = (128 - len(txt) * 8) // 2
                oled.text(txt, bx, BODY_TOP + 8)
            elif getattr(sdata, 'sampling_active', False):
                y = BODY_TOP + 2
                oled.text("Interior:", 0, y)
                oled.text(f"T{sdata.cur_device_temp_f:.1f}F", 80, y)
                y += 10
                oled.text("Probe:", 0, y)
                oled.text(f"T{sdata.cur_temp_f:.1f}F", 80, y)
            else:
                pass

            # Footer
            oled.fill_rect(0, BODY_BOTTOM, 128, FOOTER_HEIGHT, 0)
            try:
                unit_name = str(_safe_attr(settings, 'UNIT_Name', ''))[:16]
                oled.text(unit_name, 0, BODY_BOTTOM + 2)
            except Exception:
                pass

            oled.show()
        except Exception as e:
            print("[OLED] render error:", e)
        await asyncio.sleep(RENDER_INTERVAL_S)

# ===================== Public API =====================
async def set_status_banner(message, duration_s=2):
    """Non-blocking status banner"""
    global _status_queue
    _status_queue.append((str(message)[:16], time.time() + duration_s))

async def show_header():
    global _render_task
    if _render_task is None or _render_task.done():
        _render_task = asyncio.create_task(_render_loop())
    return True

async def display_message(message, display_time_s=1.5):
    """Main public message display (non-blocking)"""
    await set_status_banner(message, display_time_s)

async def display_time(display_time_s=0):
    if not oled:
        return
    await show_header()
    header_h = HEADER_HEIGHT
    footer_h = FOOTER_HEIGHT
    area_top = header_h + 2
    area_bottom = 64 - footer_h - 2
    oled.fill_rect(0, area_top, 128, area_bottom - area_top, 0)
    t = time.localtime()
    hour = t[3] % 12 or 12
    ampm = "AM" if t[3] < 12 else "PM"
    timestr = "{:02}:{:02}:{:02} {}".format(hour, t[4], t[5], ampm)
    y = area_top + max(0, ((area_bottom - area_top) - 8) // 2)
    oled.text(timestr, 10, y)
    oled.show()
    if display_time_s and display_time_s > 0:
        await asyncio.sleep(display_time_s)
        if not getattr(settings, 'DEBUG', False):
            await screen_off()

async def screen_off():
    if not oled or getattr(settings, 'DEBUG', False):
        return
    try:
        for c in range(255, -1, -25):
            oled.contrast(c)
            await asyncio.sleep(0.03)
        oled.poweroff()
    except Exception:
        pass

async def screen_on():
    if not oled:
        return
    try:
        oled.poweron()
        for c in range(0, 256, 25):
            oled.contrast(c)
            await asyncio.sleep(0.03)
        oled.contrast(255)
    except Exception:
        pass

def clear_status_banner():
    global _status_queue
    _status_queue = []
    return True

def clear_message_area():
    if not oled:
        return False
    try:
        oled.fill_rect(0, BODY_TOP, 128, BODY_HEIGHT, 0)
        oled.show()
        return True
    except Exception:
        return False

async def update_display(page=0):
    await show_header()