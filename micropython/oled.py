# Firmware Version: v2.00j

import uasyncio as asyncio
import time
import settings
import sdata
import machine
import framebuf
from settings import I2C_B_SCL_PIN, I2C_B_SDA_PIN

# Globals / state
_render_task = None
_status_banner_text = None
_status_banner_until = 0
_status_banner_persist = False
_last_render_sig = None
_show_voltage = True
_last_flip_time = 0

# Constants derived from settings (fall back to sensible defaults)
HEADER_HEIGHT = int(getattr(settings, 'OLED_HEADER_HEIGHT', 16))
FOOTER_HEIGHT = int(getattr(settings, 'OLED_FOOTER_HEIGHT', 12))
BODY_TOP = HEADER_HEIGHT
BODY_BOTTOM = 64 - FOOTER_HEIGHT
BODY_HEIGHT = BODY_BOTTOM - BODY_TOP
FLIP_INTERVAL_S = int(getattr(settings, 'OLED_HEADER_FLIP_S', 4))
RENDER_INTERVAL_S = 0.5
MAX_TEXT_CHARS = 16

# Simple SSD1309 driver (robust for 128x64)
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
            # Some ports may not implement writevto
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

# Initialize OLED if enabled
oled = None
if getattr(settings, 'ENABLE_OLED', False):
    try:
        i2c = machine.I2C(1, scl=machine.Pin(I2C_B_SCL_PIN), sda=machine.Pin(I2C_B_SDA_PIN), freq=100000)
        oled = SSD1309_I2C(128, 64, i2c, addr=0x3C)
    except Exception as e:
        print(f"[ERROR] OLED init failed: {e}")
        oled = None

# Utils
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

def _net_bars_from_rssi(rssi, cuts):
    try:
        if rssi is None:
            return 0
        if rssi > cuts[0]:
            return 3
        if rssi > cuts[1]:
            return 2
        if rssi > cuts[2]:
            return 1
    except Exception:
        pass
    return 0

def _draw_bars(o, x, y, bars):
    try:
        for i in range(3):
            h = 3 + i * 3
            o.fill_rect(x + i * 5, y + (3 * 3) - h, 4, h, 1 if i < bars else 0)
    except Exception:
        pass

def _render_signature(page):
    try:
        return (
            page,
            _status_banner_text,
            _status_banner_until,
            _status_banner_persist,
            _show_voltage,
            _safe_attr(sdata, 'sys_voltage', 0),
            _safe_attr(sdata, 'r_temp_f', None),
            _safe_attr(sdata, 'cur_temp_f', None),
            _safe_attr(sdata, 'wifi_rssi', None),
            _safe_attr(sdata, 'lora_SigStr', None),
            _safe_attr(sdata, 'last_message', ''),
            _safe_attr(sdata, 'free_mem', 0),
            _safe_attr(settings, 'UNIT_ID', ''),
            _safe_attr(settings, 'UNIT_Name', ''),
        )
    except Exception:
        return (page,)

# Unified render loop
async def _render_loop(page=0):
    global _last_render_sig, _show_voltage, _last_flip_time
    if not oled:
        return
    if not getattr(settings, 'DEBUG', False):
        await fade_display(on=True)
    while True:
        try:
            nowt = time.time()
            # Flip voltage/temperature periodically
            if nowt - _last_flip_time >= FLIP_INTERVAL_S:
                _show_voltage = not _show_voltage
                _last_flip_time = nowt

            sig = _render_signature(page)
            if sig == _last_render_sig:
                await asyncio.sleep(RENDER_INTERVAL_S)
                continue
            _last_render_sig = sig

            # Header band
            oled.fill_rect(0, 0, 128, HEADER_HEIGHT, 0)
            try:
                voltage = _safe_attr(sdata, 'sys_voltage', 0.0)
                rtemp = _safe_attr(sdata, 'r_temp_f', _safe_attr(sdata, 'cur_temp_f', None))
                if _show_voltage:
                    txt = f"{voltage:.2f}V"
                else:
                    txt = ("--.-F" if rtemp is None else f"{rtemp:.1f}F")
                oled.text(txt, 2, 0)
            except Exception:
                pass

            # Optional compact net bars on top row
            if getattr(settings, 'DISPLAY_NET_BARS', False):
                try:
                    wrssi = _safe_attr(sdata, 'wifi_rssi', None)
                    wb = _net_bars_from_rssi(wrssi, (-60, -80, -90))
                    oled.text('W', 60, 0)
                    _draw_bars(oled, 68, 0, wb)
                    lrssi = _safe_attr(sdata, 'lora_SigStr', None)
                    lb = _net_bars_from_rssi(lrssi, (-80, -100, -120))
                    oled.text('L', 96, 0)
                    _draw_bars(oled, 104, 0, lb)
                except Exception:
                    pass

            # Status banner (centered lower in header band)
            try:
                if _status_banner_text and (_status_banner_persist or time.time() < _status_banner_until):
                    txt = str(_status_banner_text)[:16]
                    bx = (128 - len(txt) * 8) // 2
                    oled.fill_rect(bx - 1, 8, len(txt) * 8 + 2, 8, 0)
                    oled.text(txt, bx, 8)
                elif _status_banner_text and not _status_banner_persist and time.time() >= _status_banner_until:
                    _status_banner_text = None
            except Exception:
                pass

            # Body area (below header)
            oled.fill_rect(0, BODY_TOP, 128, BODY_HEIGHT, 0)
            # Secondary label under header
            try:
                from utils import get_machine_id
                mid_suf = get_machine_id()[-4:] if get_machine_id() else '----'
            except Exception:
                mid_suf = '----'
            uid = str(_safe_attr(settings, 'UNIT_ID', ''))[-6:]
            label = f"U {uid} M {mid_suf}"[:MAX_TEXT_CHARS]
            oled.text(label, 0, BODY_TOP + 0)

            if page == 0:
                oled.text(f"T {_safe_attr(sdata, 'cur_temp_f', 0):.1f}F", 0, BODY_TOP + 10)
                oled.text(f"H {_safe_attr(sdata, 'cur_humid', 0):.1f}%", 0, BODY_TOP + 20)
                oled.text(f"B {_safe_attr(sdata, 'cur_bar_pres', 0):.1f}", 0, BODY_TOP + 30)
            else:
                for i in range(8):
                    st = 'ON' if _safe_attr(sdata, f'relay{i+1}_on', False) else 'OFF'
                    x = (i % 4) * 32
                    y = BODY_TOP + 10 + (i // 4) * 10
                    oled.text(f"R{i+1}:{st}", x, y)
                memkb = int(_safe_attr(sdata, 'free_mem', 0) // 1024)
                rt = _safe_attr(sdata, 'script_runtime', 0)
                err = _safe_attr(sdata, 'error_count', 0)
                oled.text(f"Mem {memkb}KB", 0, BODY_TOP + 30)
                oled.text(f"Run {rt}s Err {err}", 64, BODY_TOP + 30)

            # Last message bottom
            try:
                msg = str(_safe_attr(sdata, 'last_message', ''))[:MAX_TEXT_CHARS]
                oled.text(msg, 0, 56)
            except Exception:
                pass

            # Footer band
            oled.fill_rect(0, BODY_BOTTOM, 128, FOOTER_HEIGHT, 0)
            try:
                temp_f = _safe_attr(sdata, 'cur_temp_f', None)
                temp_str = f"{temp_f:.1f}F" if temp_f is not None else "--.-F"
                oled.text(temp_str, 0, BODY_BOTTOM + 2)
                unit_name = str(_safe_attr(settings, 'UNIT_Name', ''))[:12]
                name_x = max(0, 128 - len(unit_name) * 8)
                oled.text(unit_name, name_x, BODY_BOTTOM + 2)
            except Exception:
                pass

            oled.show()
        except Exception as e:
            try:
                print("[OLED] render error:", e)
            except Exception:
                pass
        await asyncio.sleep(RENDER_INTERVAL_S)

# Public APIs
async def show_header():
    global _render_task
    if _render_task is None or _render_task.done():
        _render_task = asyncio.create_task(_render_loop())
    # footer loop not separate anymore; header start ensures full renderer runs
    return True

async def display_message(message, display_time_s=0):
    if not oled:
        return
    await show_header()
    try:
        from utils import update_sys_voltage
        update_sys_voltage()
    except Exception:
        pass
    msg = ' '.join(str(message).split())
    # Compute lines based on body height
    max_lines = max(1, BODY_HEIGHT // 8)
    while msg:
        page_lines = []
        rem = msg
        for _ in range(max_lines):
            if not rem:
                break
            if len(rem) <= MAX_TEXT_CHARS:
                page_lines.append(rem)
                rem = ''
                break
            idx = rem.rfind(' ', 0, MAX_TEXT_CHARS)
            if idx == -1:
                idx = MAX_TEXT_CHARS
            page_lines.append(rem[:idx].rstrip())
            rem = rem[idx:].lstrip()
        oled.fill_rect(0, BODY_TOP, 128, BODY_HEIGHT, 0)
        start_y = BODY_TOP + max(0, (BODY_HEIGHT - len(page_lines) * 8) // 2)
        for i, line in enumerate(page_lines):
            x = max(0, (128 - len(line) * 8) // 2)
            oled.text(line, x, start_y + i * 8)
        oled.show()
        if rem:
            await asyncio.sleep(display_time_s if display_time_s else 1.2)
            msg = rem
        else:
            if display_time_s and display_time_s > 0:
                await asyncio.sleep(display_time_s)
            break
    if not getattr(settings, 'DEBUG', False):
        await screen_off()

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
    await fade_display(on=False)
    oled.poweroff()

async def screen_on():
    if not oled:
        return
    await show_header()
    oled.poweron()

def set_status_banner(message, duration_s=5, persist=False):
    global _status_banner_text, _status_banner_until, _status_banner_persist
    if not oled:
        return False
    _status_banner_text = str(message)
    _status_banner_until = time.time() + int(duration_s)
    _status_banner_persist = bool(persist)
    return True

def clear_status_banner():
    global _status_banner_text, _status_banner_until, _status_banner_persist
    _status_banner_text = None
    _status_banner_until = 0
    _status_banner_persist = False
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
    # Backwards compatibility: start unified render loop with given page
    await show_header()

