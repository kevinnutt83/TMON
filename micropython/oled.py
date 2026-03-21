# TMON v2.01.0 - Polished non-blocking OLED
# Lazy initialization to prevent stack overflow during import.
# All heavy imports deferred until first use.
# Driver class cached at module level, init_display separated from __init__
# to reduce peak C stack depth during OLED bring-up.

import gc

# Deferred imports - these will be loaded on first use
_asyncio = None
_time = None
_settings = None
_sdata = None
_machine = None
_framebuf = None

def _load_imports():
    """Load imports on demand to reduce import-time stack depth"""
    global _asyncio, _time, _settings, _sdata, _machine, _framebuf
    if _asyncio is None:
        import uasyncio
        _asyncio = uasyncio
    if _time is None:
        import time
        _time = time
    if _settings is None:
        import settings
        _settings = settings
    if _sdata is None:
        import sdata
        _sdata = sdata
    if _machine is None:
        import machine
        _machine = machine
    if _framebuf is None:
        import framebuf
        _framebuf = framebuf

# ===================== State =====================
_render_task = None
_status_msg = None
_status_expires = 0
_show_voltage = True
_last_flip_time = 0
_gc_counter = 0
_oled = None
_oled_init_tried = False
_SSD1309_cls = None

# Constants
HEADER_HEIGHT = 16
FOOTER_HEIGHT = 12
BODY_TOP = 16
BODY_BOTTOM = 52
BODY_HEIGHT = 36
FLIP_INTERVAL_S = 4
RENDER_INTERVAL_S = 0.5
GC_INTERVAL = 10

# ===================== SSD1309 Driver =====================
# Init command sequence as module-level constant (avoids runtime tuple allocation)
_INIT_CMDS_INT = (0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D)
_INIT_CMDS_TAIL = (0x20, 0x00, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF, 0xD9)
_INIT_CMDS_END = (0xDB, 0x40, 0xA4, 0xA6, 0xAF)

def _ensure_driver_class():
    """Create and cache SSD1309 class on first use. Requires _load_imports() first."""
    global _SSD1309_cls
    if _SSD1309_cls is not None:
        return
    class _SSD1309(_framebuf.FrameBuffer):
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
            super().__init__(self.buffer, self.width, self.height, _framebuf.MONO_VLSB)
            # init_display NOT called here — called separately after __init__
            # returns, so __init__ + FrameBuffer.__init__ frames unwind first

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
            for cmd in _INIT_CMDS_INT:
                try:
                    self.write_cmd(cmd)
                except Exception:
                    pass
            try:
                self.write_cmd(0x14 if not self.external_vcc else 0x10)
            except Exception:
                pass
            for cmd in _INIT_CMDS_TAIL:
                try:
                    self.write_cmd(cmd)
                except Exception:
                    pass
            try:
                self.write_cmd(0xF1 if not self.external_vcc else 0x22)
            except Exception:
                pass
            for cmd in _INIT_CMDS_END:
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

        def contrast(self, c):
            try:
                self.write_cmd(0x81)
                self.write_cmd(c)
            except Exception:
                pass
    _SSD1309_cls = _SSD1309

def _get_oled():
    """Lazy OLED initialization - called when needed, not at import"""
    global _oled, _oled_init_tried
    if _oled is not None:
        return _oled
    if _oled_init_tried:
        return None
    _oled_init_tried = True
    _load_imports()
    if not getattr(_settings, 'ENABLE_OLED', False):
        return None
    try:
        scl = getattr(_settings, 'OLED_SCL_PIN', 18)
        sda = getattr(_settings, 'OLED_SDA_PIN', 17)
        i2c = _machine.I2C(1, scl=_machine.Pin(scl), sda=_machine.Pin(sda), freq=100000)
        _ensure_driver_class()
        _oled = _SSD1309_cls(128, 64, i2c, addr=0x3C)
        # init_display called after constructor returns, reducing peak stack
        # depth by ~2 frames (__init__ + FrameBuffer.__init__ have unwound)
        _oled.init_display()
        gc.collect()
    except Exception as e:
        print("[OLED] init failed:", e)
        _oled = None
    return _oled

# ===================== Helpers =====================
async def fade_display(on=True, steps=10, delay=0.03):
    _load_imports()
    oled = _get_oled()
    if not oled:
        return
    if on:
        for c in range(0, 256, max(1, 255 // steps)):
            oled.contrast(c)
            await _asyncio.sleep(delay)
        oled.contrast(255)
    else:
        for c in range(255, -1, -max(1, 255 // steps)):
            oled.contrast(c)
            await _asyncio.sleep(delay)
        oled.contrast(0)

def _net_bars_from_rssi(rssi, cuts=(-60, -80, -90)):
    if rssi is None:
        return 0
    try:
        r = int(rssi)
        if r > cuts[0]: return 3
        if r > cuts[1]: return 2
        if r > cuts[2]: return 1
    except Exception:
        pass
    return 0

def _draw_bars(o, x, y, bars):
    """Draw 3 signal strength bars"""
    for i in range(3):
        h = 3 + i * 3
        bx = x + i * 6
        by = y + 9 - h
        o.rect(bx, by, 4, h, 1)
        if i < bars:
            o.fill_rect(bx + 1, by + 1, 2, h - 2, 1)

# ===================== Render Loop =====================
async def _render_loop():
    """Simplified render loop with minimal allocations"""
    global _show_voltage, _last_flip_time, _status_msg, _status_expires, _gc_counter
    # _load_imports() already called by show_header() before this task starts
    oled = _get_oled()
    if not oled:
        return
    
    enable_wifi = getattr(_settings, 'ENABLE_WIFI', False)
    enable_lora = getattr(_settings, 'ENABLE_LORA', False)
    
    while True:
        now = _time.time()
        
        if now - _last_flip_time >= FLIP_INTERVAL_S:
            _show_voltage = not _show_voltage
            _last_flip_time = now

        if _status_msg and now >= _status_expires:
            _status_msg = None

        # === HEADER ===
        oled.fill_rect(0, 0, 128, HEADER_HEIGHT, 0)
        
        if _show_voltage:
            v = getattr(_sdata, 'sys_voltage', 0.0) or 0.0
            oled.text(str(round(v, 2)) + "V", 2, 0)
        else:
            t = getattr(_sdata, 'cur_temp_f', None)
            if t is not None:
                oled.text(str(round(t, 1)) + "F", 2, 0)
            else:
                oled.text("--.-F", 2, 0)
        
        x_pos = 70
        
        if enable_wifi:
            oled.text("W", x_pos, 0)
            rssi = getattr(_sdata, 'wifi_rssi', None)
            bars = _net_bars_from_rssi(rssi)
            _draw_bars(oled, x_pos + 10, 0, bars)
            x_pos += 30
        
        if enable_lora:
            oled.text("L", x_pos, 0)
            rssi = getattr(_sdata, 'lora_SigStr', None)
            bars = _net_bars_from_rssi(rssi, (-60, -90, -120))
            _draw_bars(oled, x_pos + 10, 0, bars)

        # === BODY ===
        oled.fill_rect(0, BODY_TOP, 128, BODY_HEIGHT, 0)
        
        if _status_msg:
            msg_len = len(_status_msg)
            bx = max(0, (128 - msg_len * 8) // 2)
            oled.text(_status_msg, bx, BODY_TOP + 8)
        elif getattr(_sdata, 'sampling_active', False):
            y = BODY_TOP + 2
            oled.text("Interior:", 0, y)
            dt = getattr(_sdata, 'cur_device_temp_f', None)
            if dt is not None:
                oled.text("T" + str(round(dt, 1)) + "F", 80, y)
            y += 10
            oled.text("Probe:", 0, y)
            pt = getattr(_sdata, 'cur_temp_f', None)
            if pt is not None:
                oled.text("T" + str(round(pt, 1)) + "F", 80, y)

        # === FOOTER ===
        oled.fill_rect(0, BODY_BOTTOM, 128, FOOTER_HEIGHT, 0)
        unit_name = getattr(_settings, 'UNIT_Name', '')
        if unit_name:
            oled.text(str(unit_name)[:16], 0, BODY_BOTTOM + 2)

        oled.show()
        
        _gc_counter += 1
        if _gc_counter >= GC_INTERVAL:
            _gc_counter = 0
            gc.collect()
        
        await _asyncio.sleep(RENDER_INTERVAL_S)

# ===================== Public API =====================
async def set_status_banner(message, duration_s=2):
    """Non-blocking status banner - sets single message"""
    global _status_msg, _status_expires
    _load_imports()
    _status_msg = str(message)[:16]
    _status_expires = _time.time() + duration_s

async def show_header():
    """Start the render loop if not already running"""
    global _render_task
    _load_imports()
    try:
        if _render_task is not None and not _render_task.done():
            return True
    except Exception:
        _render_task = None
    _render_task = _asyncio.create_task(_render_loop())
    return True

async def display_message(message, display_time_s=1.5):
    """Main public message display (non-blocking)"""
    await set_status_banner(message, display_time_s)
    await show_header()

async def display_time(display_time_s=0):
    _load_imports()
    oled = _get_oled()
    if not oled:
        return
    await show_header()
    area_top = HEADER_HEIGHT + 2
    area_bottom = 64 - FOOTER_HEIGHT - 2
    oled.fill_rect(0, area_top, 128, area_bottom - area_top, 0)
    t = _time.localtime()
    hour = t[3] % 12 or 12
    ampm = "AM" if t[3] < 12 else "PM"
    timestr = "{:02}:{:02}:{:02} {}".format(hour, t[4], t[5], ampm)
    y = area_top + max(0, ((area_bottom - area_top) - 8) // 2)
    oled.text(timestr, 10, y)
    oled.show()
    if display_time_s and display_time_s > 0:
        await _asyncio.sleep(display_time_s)
        if not getattr(_settings, 'DEBUG', False):
            await screen_off()

async def screen_off():
    _load_imports()
    oled = _get_oled()
    if not oled or getattr(_settings, 'DEBUG', False):
        return
    try:
        for c in range(255, -1, -25):
            oled.contrast(c)
            await _asyncio.sleep(0.03)
        oled.poweroff()
    except Exception:
        pass

async def screen_on():
    _load_imports()
    oled = _get_oled()
    if not oled:
        return
    try:
        oled.poweron()
        for c in range(0, 256, 25):
            oled.contrast(c)
            await _asyncio.sleep(0.03)
        oled.contrast(255)
    except Exception:
        pass

def clear_status_banner():
    global _status_msg, _status_expires
    _status_msg = None
    _status_expires = 0
    return True

def clear_message_area():
    oled = _get_oled()
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