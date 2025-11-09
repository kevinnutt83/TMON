# Firmware Version: v2.00j

# --- Header Section Management ---
import uasyncio as asyncio
import time
import settings
import sdata
import machine
import framebuf
from settings import I2C_B_SCL_PIN, I2C_B_SDA_PIN

_header_task = None
_status_banner_text = None
_status_banner_until = 0
_status_banner_persist = False

async def fade_display(on=True, steps=10, delay=0.03):
    # Fade in or out by adjusting contrast
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

async def show_header():
    global _header_task
    if _header_task is None or _header_task.done():
        _header_task = asyncio.create_task(_header_loop())

async def _header_loop():
    if not getattr(settings, 'DEBUG', False):
        await fade_display(on=True)
    while True:
        oled.fill_rect(0, 0, 128, 20, 0)  # Clear header area (taller)
        # Voltage (large, top left)
        try:
            import sdata
            voltage = getattr(sdata, 'sys_voltage', 0)
        except Exception:
            voltage = 0
        volt_str = f"{voltage:.2f}V"
        for i, ch in enumerate(volt_str):
            _draw_big_char(oled, ch, 2 + i*14, 1, scale=2)

        # LoRa signal bars (top right, 0-3 bars)
        try:
            import sdata
            sig = getattr(sdata, 'lora_SigStr', None)
            if sig is not None:
                if sig > -80:
                    bars = 3
                elif sig > -100:
                    bars = 2
                elif sig > -120:
                    bars = 1
                else:
                    bars = 0
            else:
                bars = 0
            bar_x = 128 - 26
            bar_y = 4
            for i in range(3):
                x = bar_x + i*7
                h = 6 + i*6
                y = bar_y + 14 - h
                color = 1 if i < bars else 0
                oled.fill_rect(x, y, 6, h, color)
            if bars == 0:
                for i in range(3):
                    x = bar_x + i*7
                    h = 6 + i*6
                    y = bar_y + 14 - h
                    oled.rect(x, y, 6, h, 1)
        except Exception:
            bar_x = 128 - 26
            bar_y = 4
            for i in range(3):
                x = bar_x + i*7
                h = 6 + i*6
                y = bar_y + 14 - h
                oled.rect(x, y, 6, h, 1)

        # WiFi status icon (top center)
        try:
            import sdata
            wifi = getattr(sdata, 'wifi_connected', None)
            # Draw a minimalist WiFi icon (3 arcs)
            cx, cy = 64, 8
            for r, val in zip([8, 6, 4], [1, 1 if wifi else 0, 1 if wifi else 0]):
                if val:
                    for a in range(-45, 46, 5):
                        x = int(cx + r * 0.01745 * a)
                        y = int(cy + r * 0.01745 * abs(a))
                        oled.pixel(x, y, 1)
            if wifi:
                oled.fill_rect(cx-1, cy+5, 3, 3, 1)
        except Exception:
            pass

        # Schema/operation icon (top left, below voltage)
        try:
            import sdata
            schema = getattr(sdata, 'schema_mode', None)
            # Draw a minimalist icon for schema/operation mode
            if schema == 'normal':
                oled.rect(2, 18, 12, 4, 1)  # Rectangle for normal
            elif schema == 'alert':
                oled.line(2, 18, 14, 22, 1)
                oled.line(14, 18, 2, 22, 1)  # X for alert
            elif schema == 'maintenance':
                oled.line(2, 18, 14, 18, 1)
                oled.line(8, 18, 8, 22, 1)  # T for maintenance
        except Exception:
            pass

        # Optional status banner (non-blocking)
        try:
            import time as _t
            global _status_banner_text, _status_banner_until, _status_banner_persist
            if _status_banner_text and (_status_banner_persist or _t.time() < _status_banner_until):
                txt = str(_status_banner_text)
                if len(txt) > 16:
                    txt = txt[:16]
                # Draw small text strip near top center
                # Clear a narrow band to improve legibility
                oled.fill_rect(30, 10, 98, 10, 0)
                oled.text(txt, 32, 12)
            elif _status_banner_text and not _status_banner_persist and _t.time() >= _status_banner_until:
                _status_banner_text = None
        except Exception:
            pass

        oled.show()
        await asyncio.sleep(0.1)

# --- Simple big font drawing (2x scale, only for digits, V, N, A, E, -) ---
def _draw_big_char(oled, ch, x, y, scale=2):
    # Only supports 0-9, V, N, A, E, -
    font = {
        '0': [0x3E,0x51,0x49,0x45,0x3E],
        '1': [0x00,0x42,0x7F,0x40,0x00],
        '2': [0x42,0x61,0x51,0x49,0x46],
        '3': [0x21,0x41,0x45,0x4B,0x31],
        '4': [0x18,0x14,0x12,0x7F,0x10],
        '5': [0x27,0x45,0x45,0x45,0x39],
        '6': [0x3C,0x4A,0x49,0x49,0x30],
        '7': [0x01,0x71,0x09,0x05,0x03],
        '8': [0x36,0x49,0x49,0x49,0x36],
        '9': [0x06,0x49,0x49,0x29,0x1E],
        'V': [0x3F,0x40,0x40,0x40,0x3F],
        'N': [0x7F,0x04,0x08,0x10,0x7F],
        'A': [0x7E,0x11,0x11,0x11,0x7E],
        'E': [0x7F,0x49,0x49,0x49,0x41],
        '-': [0x08,0x08,0x08,0x08,0x08],
        '.': [0x00,0x60,0x60,0x00,0x00],
    }
    pattern = font.get(ch, font.get('0'))
    for col, bits in enumerate(pattern):
        for row in range(8):
            if bits & (1 << row):
                for dx in range(scale):
                    for dy in range(scale):
                        oled.pixel(x + col*scale + dx, y + row*scale + dy, 1)
# settings.py (assumed to exist with the pin definitions)
# I2C_B_SCL_PIN = 11
# I2C_B_SDA_PIN = 12


# Import necessary modules

import machine
import uasyncio as asyncio
import framebuf
import time
from settings import I2C_B_SCL_PIN, I2C_B_SDA_PIN

# SSD1309 driver class (custom, adjusted for 128x64 without column offset, flipped orientation)
class SSD1309_I2C(framebuf.FrameBuffer):
    def __init__(self, width, height, i2c, addr=0x3C, external_vcc=False):
        self.i2c = i2c
        self.addr = addr
        self.temp = bytearray(2)
        self.write_list = [b'\x40', None]  # Co=0, D/C=1 for data
        self.external_vcc = external_vcc
        self.width = width
        self.height = height
        self.pages = height // 8
        self.buffer = bytearray(self.pages * self.width)
        self.col_start = 0  # Try without column offset
        self.col_end = self.col_start + self.width - 1
        super().__init__(self.buffer, self.width, self.height, framebuf.MONO_VLSB)
        self.init_display()

    def write_cmd(self, cmd):
        self.temp[0] = 0x00  # Co=0, D/C=0 for command
        self.temp[1] = cmd
        self.i2c.writeto(self.addr, self.temp)

    def write_data(self, buf):
        self.write_list[1] = buf
        self.i2c.writevto(self.addr, self.write_list)

    def init_display(self):
        for cmd in (
            0xAE,          # Display off
            0xD5, 0x80,    # Set display clock divide ratio/oscillator frequency
            0xA8, 0x3F,    # Set multiplex ratio (63 for 64 lines)
            0xD3, 0x00,    # Set display offset
            0x40 | 0x00,   # Set start line address
            0x8D, 0x14 if not self.external_vcc else 0x10,  # Enable charge pump regulator
            0x20, 0x00,    # Set memory addressing mode (horizontal)
            0xA1,          # Set segment re-map (A1 = flip, right side up)
            0xC8,          # Set COM output scan direction (C8 = flip, right side up)
            0xDA, 0x12,    # Set COM pins hardware configuration (alternative, enable remap)
            0x81, 0xCF,    # Set contrast control (try higher like 0xFF if dim)
            0xD9, 0xF1 if not self.external_vcc else 0x22,  # Set pre-charge period
            0xDB, 0x40,    # Set VCOMH deselect level
            0xA4,          # Entire display on (follow RAM content)
            0xA6,          # Set normal display (not inverted)
            0xAF           # Display on
        ):
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def show(self):
        self.write_cmd(0x21)  # Column address
        self.write_cmd(self.col_start)     # Column start
        self.write_cmd(self.col_end)       # Column end
        self.write_cmd(0x22)  # Page address
        self.write_cmd(0)     # Page start
        self.write_cmd(self.pages - 1)  # Page end
        self.write_data(self.buffer)

    def poweroff(self):
        self.write_cmd(0xAE)  # Turn off the display to conserve power

    def poweron(self):
        self.write_cmd(0xAF)  # Turn on the display

    def contrast(self, contrast):
        self.write_cmd(0x81)
        self.write_cmd(contrast)

    def invert(self, invert):
        self.write_cmd(0xA6 | (invert & 1))



# OLED initialization with error handling
oled = None
if getattr(settings, 'ENABLE_OLED', False):
    try:
        i2c = machine.I2C(1, scl=machine.Pin(I2C_B_SCL_PIN), sda=machine.Pin(I2C_B_SDA_PIN), freq=100000)
        oled = SSD1309_I2C(128, 64, i2c, addr=0x3C)
    except Exception as e:
        print(f"[ERROR] OLED initialization failed: {e}")
        oled = None


# Async display utility functions

async def display_message(message, display_time_s):
    await show_header()
    # Always update system voltage before displaying
    try:
        from utils import update_sys_voltage
        update_sys_voltage()
    except Exception:
        pass
    debug_mode = getattr(settings, 'DEBUG', False)
    # Do not power on/off OLED here to avoid flashing
    # Message area: y=24 to y=52 (4 lines max, 8px each)
    max_chars = 16
    max_lines = 4
    area_top = 24
    area_bottom = 52
    lines = []
    msg = message
    while msg:
        # Split message into lines for this screen
        page_lines = []
        msg_left = msg
        for _ in range(max_lines):
            if not msg_left:
                break
            if len(msg_left) <= max_chars:
                page_lines.append(msg_left)
                msg_left = ""
                break
            break_idx = msg_left.rfind(' ', 0, max_chars)
            if break_idx == -1:
                break_idx = max_chars
            page_lines.append(msg_left[:break_idx].rstrip())
            msg_left = msg_left[break_idx:].lstrip()
        # Draw this page
        oled.fill_rect(0, area_top, 128, area_bottom-area_top, 0)
        for i, line in enumerate(page_lines):
            oled.text(line, 0, area_top + i*8)
        oled.show()
        # If more to show, wait, then continue
        if msg_left:
            await asyncio.sleep(display_time_s if display_time_s else 2)
            msg = msg_left
        else:
            if display_time_s and display_time_s > 0:
                await asyncio.sleep(display_time_s)
            break
    if not debug_mode:
        oled.poweroff()

async def display_time(display_time_s):
    await show_header()
    debug_mode = getattr(settings, 'DEBUG', False)
    # Message area: y=24 to y=52
    oled.fill_rect(0, 24, 128, 28, 0)
    t = time.localtime()
    hour = t[3] % 12
    if hour == 0:
        hour = 12
    ampm = "AM" if t[3] < 12 else "PM"
    timestr = "{:02}:{:02}:{:02} {}".format(hour, t[4], t[5], ampm)
    oled.text(timestr, 10, 36)
    oled.show()
    if display_time_s and display_time_s > 0:
        await asyncio.sleep(display_time_s)
        if not debug_mode:
            oled.poweroff()

async def screen_off():
    debug_mode = getattr(settings, 'DEBUG', False)
    if not debug_mode:
        await fade_display(on=False)
        oled.poweroff()
    # If debug, do not power off or fade the header; header stays on

async def screen_on():
    await show_header()
    oled.poweron()


# --- Footer Section Management ---
_footer_task = None

async def show_footer():
    global _footer_task
    if _footer_task is None or _footer_task.done():
        _footer_task = asyncio.create_task(_footer_loop())

async def _footer_loop():
    while True:
        # Draw footer (bottom 12px)
        oled.fill_rect(0, 52, 128, 12, 0)
        # Temp (bottom left)
        try:
            import sdata
            temp_f = getattr(sdata, 'cur_temp_f', None)
            if temp_f is not None:
                temp_str = f"{temp_f:.1f}F"
            else:
                temp_str = "--.-F"
        except Exception:
            temp_str = "--.-F"
        oled.text(temp_str, 0, 56)
        # Unit name (bottom right)
        try:
            import settings
            unit_name = getattr(settings, 'UNIT_Name', None)
            if unit_name is None:
                unit_name = ""
        except Exception:
            unit_name = ""
        # Right align
        name_x = 128 - len(str(unit_name))*8
        oled.text(str(unit_name), name_x, 56)
        oled.show()
        await asyncio.sleep(0.1)

# --- Update header/footer show calls ---
async def show_header():
    global _header_task
    if _header_task is None or _header_task.done():
        _header_task = asyncio.create_task(_header_loop())
    await show_footer()

def set_status_banner(message, duration_s=5, persist=False):
    global _status_banner_text, _status_banner_until, _status_banner_persist
    try:
        if not oled:
            return False
        _status_banner_text = str(message)
        import time as _t
        _status_banner_until = _t.time() + int(duration_s)
        _status_banner_persist = bool(persist)
        return True
    except Exception:
        return False

def clear_status_banner():
    global _status_banner_text, _status_banner_until, _status_banner_persist
    _status_banner_text = None
    _status_banner_until = 0
    _status_banner_persist = False
    return True

def clear_message_area():
    # Clear the central message region without affecting header/footer
    if not oled:
        return False
    try:
        oled.fill_rect(0, 24, 128, 28, 0)
        oled.show()
        return True
    except Exception:
        return False

# Minimal working async example
# Uncomment to test on device:
# async def main():
#     await screen_on()
#     await display_message("Hello, World!", 3)
#     await asyncio.sleep(1)
#     await screen_on()
#     await display_time(3)
#     await asyncio.sleep(1)
#     await screen_off()
# asyncio.run(main())

# --- Persistent display update (new) ---
try:
    import sdata as _sdata
    import settings as _settings
except Exception:
    _sdata = None
    _settings = None

def _safe_attr(obj, name, default=0):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default

def _draw_bars(o, x, y, bars):
    try:
        for i in range(4):
            h = (i + 1) * 3
            o.fill_rect(x + i * 6, y + 12 - h, 4, h, 1 if i < bars else 0)
    except Exception:
        pass

def _net_bars_from_rssi(rssi, cuts):
    # cuts is a tuple of thresholds high->low
    try:
        if rssi is None:
            return 0
        if rssi > cuts[0]:
            return 3
        if rssi > cuts[1]:
            return 2
        if rssi > cuts[2]:
            return 1
        return 0
    except Exception:
        return 0

_last_render_sig = None

def _render_signature(page):
    # Build a compact signature to detect display-relevant changes
    try:
        return (
            page,
            _safe_attr(_sdata, 'sys_voltage', 0),
            _safe_attr(_sdata, 'cur_temp_f', 0),
            _safe_attr(_sdata, 'cur_humid', 0),
            _safe_attr(_sdata, 'cur_bar_pres', 0),
            _safe_attr(_sdata, 'wifi_rssi', 0),
            _safe_attr(_sdata, 'lora_SigStr', 0),
            _safe_attr(_sdata, 'error_count', 0),
            _safe_attr(_sdata, 'free_mem', 0),
            _safe_attr(_sdata, 'script_runtime', 0),
            _safe_attr(_sdata, 'last_message', ''),
            _safe_attr(_sdata, 'relay1_on', False),
            _safe_attr(_sdata, 'relay2_on', False),
            _safe_attr(_sdata, 'relay3_on', False),
            _safe_attr(_sdata, 'relay4_on', False),
            _safe_attr(_sdata, 'relay5_on', False),
            _safe_attr(_sdata, 'relay6_on', False),
            _safe_attr(_sdata, 'relay7_on', False),
            _safe_attr(_sdata, 'relay8_on', False),
        )
    except Exception:
        return (page,)

async def update_display(page=0):
    """Draw a compact, readable UI with two pages. Update only when data changes.
    Page 0: sensors + network. Page 1: relays + system.
    """
    global _last_render_sig
    if not oled:
        return
    sig = _render_signature(page)
    if sig == _last_render_sig:
        return  # no change; avoid flicker and I2C traffic
    _last_render_sig = sig

    try:
        oled.fill(0)
        # Top row: unit name (left), time (right), voltage (center)
        try:
            unit = (_settings.UNIT_Name if hasattr(_settings, 'UNIT_Name') else '')
            unit = unit[:10]
        except Exception:
            unit = ''
        oled.text(unit, 0, 0)
        try:
            t = time.localtime()
            ts = f"{t[3]:02}:{t[4]:02}"
        except Exception:
            ts = "--:--"
        oled.text(ts, 128 - len(ts) * 8, 0)
        volt = _safe_attr(_sdata, 'sys_voltage', 0.0)
        vstr = f"{volt:.1f}V"
        oled.text(vstr, 64 - len(vstr) * 4, 0)

        if page == 0:
            # Network bars: WiFi left, LoRa right
            wrssi = _safe_attr(_sdata, 'wifi_rssi', 0)
            lrssi = _safe_attr(_sdata, 'lora_SigStr', 0)
            _draw_bars(oled, 0, 8, _net_bars_from_rssi(wrssi, (-60, -80, -90)))
            _draw_bars(oled, 104, 8, _net_bars_from_rssi(lrssi, (-80, -100, -120)))
            # Sensors
            oled.text(f"T { _safe_attr(_sdata,'cur_temp_f',0):.1f}F", 0, 16)
            oled.text(f"H { _safe_attr(_sdata,'cur_humid',0):.1f}%", 0, 26)
            oled.text(f"B { _safe_attr(_sdata,'cur_bar_pres',0):.1f}", 0, 36)
            # Last message bottom
            msg = str(_safe_attr(_sdata, 'last_message', ''))[:20]
            oled.text(msg, 0, 56)
        else:
            # Relays 2x4 grid
            for i in range(8):
                st = 'ON' if _safe_attr(_sdata, f'relay{i+1}_on', False) else 'OFF'
                x = (i % 4) * 32
                y = 16 + (i // 4) * 10
                oled.text(f"R{i+1}:{st}", x, y)
            # System info
            memkb = int(_safe_attr(_sdata, 'free_mem', 0) // 1024)
            rt = _safe_attr(_sdata, 'script_runtime', 0)
            err = _safe_attr(_sdata, 'error_count', 0)
            oled.text(f"Mem {memkb}KB", 0, 40)
            oled.text(f"Run {rt}s", 0, 50)
            oled.text(f"Err {err}", 72, 50)
        oled.show()
    except Exception as _e:
        # Best-effort; avoid raising
        try:
            print('[OLED] update_display error:', _e)
        except Exception:
            pass
