# TMON OLED Display Module
# Complete, production-ready version
# - Smaller header / footer
# - WiFi icon only when ENABLE_WIFI is True
# - LoRa icon only when ENABLE_LORA is True
# - Dual temperature support (interior + exterior)
# - Compatible with boot.py and main.py TaskManager
# - Forces display on at initialization

import uasyncio as asyncio
import time
import settings
import sdata
import machine
import framebuf

from settings import OLED_SCL_PIN, OLED_SDA_PIN

try:
    from diagnostics import get_diagnostics_snapshot
except Exception:
    def get_diagnostics_snapshot():
        return {}

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
_render_task = None
_status_banner_text = None
_status_banner_until = 0
_status_banner_persist = False
_status_banner_level = 'INFO'
_body_override_lines = None
_body_override_until = 0
_last_render_sig = None
_show_voltage = True
_last_flip_time = 0
_page_index = 0
_last_page_flip_time = 0
_loop_started = False

# ---------------------------------------------------------------------------
# Layout (smaller / tighter)
# ---------------------------------------------------------------------------
HEADER_HEIGHT = int(getattr(settings, 'OLED_HEADER_HEIGHT', 14))
FOOTER_HEIGHT = int(getattr(settings, 'OLED_FOOTER_HEIGHT', 10))
BODY_TOP = HEADER_HEIGHT
BODY_BOTTOM = 64 - FOOTER_HEIGHT
BODY_HEIGHT = BODY_BOTTOM - BODY_TOP

FLIP_INTERVAL_S = int(getattr(settings, 'OLED_HEADER_FLIP_S', 4))
RENDER_INTERVAL_S = 0.4
MAX_TEXT_CHARS = 16
PAGE_INTERVAL_S = int(getattr(settings, 'OLED_PAGE_ROTATE_INTERVAL_S', 6))
PAGE_NAMES = ('Summary', 'Runtime', 'Network', 'LoRa Diag', 'Health')
BODY_LINE_H = 7

# ---------------------------------------------------------------------------
# SSD1309 Driver
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Initialize OLED and force it ON
# ---------------------------------------------------------------------------
oled = None
if getattr(settings, 'ENABLE_OLED', False):
    try:
        i2c = machine.I2C(1, scl=machine.Pin(OLED_SCL_PIN), sda=machine.Pin(OLED_SDA_PIN), freq=100000)
        oled = SSD1309_I2C(128, 64, i2c, addr=0x3C)
        oled.poweron()
        oled.contrast(255)
        oled.fill(0)
        oled.text("TMON", 48, 28)
        oled.show()
    except Exception as e:
        print(f"[ERROR] OLED init failed: {e}")
        oled = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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
        short_map = {'No Con': 'No', 'Search': 'Srch', 'Searching': 'Srch'}
        for long, short in short_map.items():
            if s.startswith(long):
                return short[:max_chars]
        return s[:max_chars] if max_chars > 0 else ''
    except Exception:
        return str(txt)[:max_chars] if max_chars > 0 else ''


def _page_title(page):
    try:
        if 0 <= int(page) < len(PAGE_NAMES):
            return PAGE_NAMES[int(page)]
    except Exception:
        pass
    return 'Status'


def _draw_page_marker(o, page, total):
    try:
        if total <= 0:
            return
        marker_w = total * 5 - 1
        start_x = max(2, 128 - marker_w - 2)
        y = BODY_BOTTOM + 2
        for i in range(total):
            x = start_x + i * 5
            if i == page:
                o.fill_rect(x, y, 3, 3, 1)
            else:
                o.rect(x, y, 3, 3, 1)
    except Exception:
        pass


def _banner_text(text, level):
    try:
        prefix_map = {'SUCCESS': '+', 'WARN': '!', 'ERROR': '!'}
        prefix = prefix_map.get(str(level).upper(), '')
        msg = str(text).strip()
        if prefix:
            msg = f"{prefix} {msg}"
        return msg
    except Exception:
        return str(text)


def _layout_header_right(vol_w, right_blocks):
    try:
        gap = 3
        total = sum(b.get('w', 0) + gap for b in right_blocks)
        total = max(0, total - gap)
        start_x = 128 - 2 - total
        xs = []
        cur = start_x
        for b in right_blocks:
            xs.append(cur)
            cur += b.get('w', 0) + gap
        return start_x, xs
    except Exception:
        return 128, [128] * len(right_blocks)


def _draw_body_line(o, y, text):
    try:
        o.text(str(text)[:MAX_TEXT_CHARS], 2, y)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Page Renderers
# ---------------------------------------------------------------------------
def _render_summary_page(o):
    y = BODY_TOP + 1
    probe_f = _safe_attr(sdata, 'cur_temp_f', None)
    device_f = _safe_attr(sdata, 'cur_device_temp_f', None)

    if probe_f is not None:
        _draw_body_line(o, y, f"Ext {probe_f:.1f}F")
        y += BODY_LINE_H
    if device_f is not None:
        _draw_body_line(o, y, f"Int {device_f:.1f}F")
        y += BODY_LINE_H

    humid = _safe_attr(sdata, 'cur_humid', None)
    if humid is not None:
        _draw_body_line(o, y, f"Hum {humid:.0f}%")
        y += BODY_LINE_H

    bar = _safe_attr(sdata, 'cur_bar_pres', None)
    if bar is not None:
        _draw_body_line(o, y, f"Bar {bar:.0f}")
        y += BODY_LINE_H

    volt = _safe_attr(sdata, 'sys_voltage', None)
    if volt is not None:
        _draw_body_line(o, y, f"Bat {volt:.2f}V")


def _render_runtime_page(o):
    y = BODY_TOP + 1
    _draw_body_line(o, y, f"Mem {int(_safe_attr(sdata, 'free_mem', 0) / 1024)}k")
    y += BODY_LINE_H
    _draw_body_line(o, y, f"CPU {_safe_attr(sdata, 'cpu_temp', '--')}")
    y += BODY_LINE_H
    _draw_body_line(o, y, f"Err {_safe_attr(sdata, 'error_count', 0)}")
    y += BODY_LINE_H
    _draw_body_line(o, y, f"Run {_safe_attr(sdata, 'script_runtime', 0)}s")


def _render_network_page(o):
    y = BODY_TOP + 1
    if getattr(settings, 'ENABLE_WIFI', False):
        rssi = _safe_attr(sdata, 'wifi_rssi', None)
        _draw_body_line(o, y, f"WiFi {rssi if rssi is not None else '--'}")
        y += BODY_LINE_H
        _draw_body_line(o, y, f"WAN {'OK' if _safe_attr(sdata, 'WAN_CONNECTED', False) else 'No'}")
        y += BODY_LINE_H
    if getattr(settings, 'ENABLE_LORA', False):
        _draw_body_line(o, y, f"LoRa {_safe_attr(sdata, 'lora_SigStr', '--')}")
        y += BODY_LINE_H
        _draw_body_line(o, y, f"SNR {_safe_attr(sdata, 'lora_snr', '--')}")


def _render_lora_diag_page(o):
    y = BODY_TOP + 1
    diag = get_diagnostics_snapshot() or {}
    lora = diag.get('lora', {}) if isinstance(diag, dict) else {}
    _draw_body_line(o, y, f"Miss {lora.get('missed_syncs', 0)}")
    y += BODY_LINE_H
    _draw_body_line(o, y, f"Nodes {lora.get('remote_nodes', 0)}")
    y += BODY_LINE_H
    last_hb = lora.get('last_heartbeat_ts', 0)
    age = int(time.time() - last_hb) if last_hb else None
    _draw_body_line(o, y, f"HB {age if age is not None else '--'}s")
    y += BODY_LINE_H
    _draw_body_line(o, y, f"Conn {'Y' if _safe_attr(sdata, 'LORA_CONNECTED', False) else 'N'}")


def _render_health_page(o):
    y = BODY_TOP + 1
    diag = get_diagnostics_snapshot() or {}
    tx = diag.get('transmission', {}) if isinstance(diag, dict) else {}
    _draw_body_line(o, y, f"Back {tx.get('backlog_size', 0)}")
    y += BODY_LINE_H
    _draw_body_line(o, y, f"Frost {'Y' if _safe_attr(sdata, 'frostwatch_active', False) else 'N'}")
    y += BODY_LINE_H
    _draw_body_line(o, y, f"Heat {'Y' if _safe_attr(sdata, 'heatwatch_active', False) else 'N'}")
    y += BODY_LINE_H
    _draw_body_line(o, y, f"UID {str(_safe_attr(settings, 'UNIT_ID', ''))[:8]}")


# ---------------------------------------------------------------------------
# Main Render Loop
# ---------------------------------------------------------------------------
async def _render_loop():
    global _last_render_sig, _show_voltage, _last_flip_time
    global _body_override_lines, _body_override_until, _page_index, _last_page_flip_time

    if not oled:
        return

    oled.poweron()
    oled.contrast(255)

    while True:
        try:
            nowt = time.time()

            if nowt - _last_flip_time >= FLIP_INTERVAL_S:
                _show_voltage = not _show_voltage
                _last_flip_time = nowt

            if nowt - _last_page_flip_time >= PAGE_INTERVAL_S:
                _page_index = (_page_index + 1) % max(1, len(PAGE_NAMES))
                _last_page_flip_time = nowt

            # ----- Header -----
            oled.fill_rect(0, 0, 128, HEADER_HEIGHT, 0)
            try:
                voltage = _safe_attr(sdata, 'sys_voltage', 0.0)
                rtemp = _safe_attr(sdata, 'cur_temp_f', None)
                if rtemp is None:
                    rtemp = _safe_attr(sdata, 'cur_device_temp_f', None)

                if _show_voltage:
                    txt = f"{voltage:.2f}V"
                else:
                    txt = ("--.-F" if rtemp is None else f"{rtemp:.1f}F")
                oled.text(txt, 2, 0)
                vol_w = _measure_text_w(txt) + 4
            except Exception:
                vol_w = 16

            # Network icons – only when the corresponding feature is enabled
            if getattr(settings, 'DISPLAY_NET_BARS', True):
                try:
                    blocks = []

                    if getattr(settings, 'ENABLE_WIFI', False):
                        if getattr(sdata, 'WIFI_CONNECTED', False):
                            wb = _net_bars_from_rssi(_safe_attr(sdata, 'wifi_rssi', None), (-60, -80, -90))
                            wtext = ''
                        else:
                            wb = 0
                            wtext = 'No'
                        blocks.append({
                            'icon': 'W',
                            'bars': wb,
                            'text': wtext,
                            'w': 8 + 2 + 18 + (4 if wtext else 0) + _measure_text_w(wtext)
                        })

                    if getattr(settings, 'ENABLE_LORA', False):
                        now_epoch = time.time()
                        stale_s = int(getattr(settings, 'OLED_LORA_STALE_S', 120))
                        last_rx = int(_safe_attr(sdata, 'lora_last_rx_ts', 0) or 0)
                        last_tx = int(_safe_attr(sdata, 'lora_last_tx_ts', 0) or 0)
                        recent = (last_rx and (now_epoch - last_rx) <= stale_s) or (last_tx and (now_epoch - last_tx) <= stale_s)
                        connected = bool(_safe_attr(sdata, 'LORA_CONNECTED', False)) or recent
                        if connected:
                            lb = _net_bars_from_rssi(_safe_attr(sdata, 'lora_SigStr', None), (-60, -90, -120))
                            ltext = ''
                        else:
                            lb = 0
                            ltext = 'Srch' if str(getattr(settings, 'NODE_TYPE', '')).lower() == 'remote' else 'No'
                        blocks.append({
                            'icon': 'L',
                            'bars': lb,
                            'text': ltext,
                            'w': 8 + 2 + 18 + (4 if ltext else 0) + _measure_text_w(ltext)
                        })

                    _, xs = _layout_header_right(vol_w, blocks)
                    for i, b in enumerate(blocks):
                        x = xs[i] if i < len(xs) else 100
                        oled.text(b['icon'], x, 0)
                        _draw_bars(oled, x + 10, 0, b['bars'])
                        if b.get('text'):
                            oled.text(_compact_label(b['text'], 4), x + 30, 0)
                except Exception:
                    pass

            # ----- Body -----
            oled.fill_rect(0, BODY_TOP, 128, BODY_HEIGHT, 0)

            if _status_banner_text and (_status_banner_persist or time.time() < _status_banner_until):
                ban = _banner_text(_status_banner_text, _status_banner_level)[:MAX_TEXT_CHARS]
                oled.text(ban, 2, BODY_TOP + 1)
            elif _body_override_lines and time.time() < _body_override_until:
                for i, line in enumerate(_body_override_lines[: BODY_HEIGHT // BODY_LINE_H]):
                    oled.text(str(line)[:MAX_TEXT_CHARS], 2, BODY_TOP + 1 + i * BODY_LINE_H)
            else:
                if _page_index == 0:
                    _render_summary_page(oled)
                elif _page_index == 1:
                    _render_runtime_page(oled)
                elif _page_index == 2:
                    _render_network_page(oled)
                elif _page_index == 3:
                    _render_lora_diag_page(oled)
                else:
                    _render_health_page(oled)

            # ----- Footer -----
            oled.fill_rect(0, BODY_BOTTOM, 128, FOOTER_HEIGHT, 0)
            try:
                uname = str(_safe_attr(settings, 'UNIT_Name', '') or _safe_attr(settings, 'UNIT_ID', ''))[:12]
                oled.text(uname, 2, BODY_BOTTOM + 1)
                title = _page_title(_page_index)[:8]
                oled.text(title, 128 - _measure_text_w(title) - 2, BODY_BOTTOM + 1)
                _draw_page_marker(oled, _page_index, len(PAGE_NAMES))
            except Exception:
                pass

            oled.show()
        except Exception:
            pass

        await asyncio.sleep(RENDER_INTERVAL_S)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def display_message(message, display_time_s=1.5):
    """Show a temporary message (used by boot.py)."""
    global _body_override_lines, _body_override_until, _last_render_sig
    if not oled:
        return
    try:
        lines = []
        msg = str(message or '')
        while msg:
            lines.append(msg[:MAX_TEXT_CHARS])
            msg = msg[MAX_TEXT_CHARS:]
        _body_override_lines = lines[: max(1, BODY_HEIGHT // BODY_LINE_H)]
        _body_override_until = time.time() + float(display_time_s or 1.5)
        _last_render_sig = None
        await update_display()
    except Exception:
        pass


def set_status_banner(message, duration_s=5, persist=False, level='INFO'):
    global _status_banner_text, _status_banner_until, _status_banner_persist, _status_banner_level, _last_render_sig
    _status_banner_text = str(message or '')
    _status_banner_level = str(level or 'INFO')
    _status_banner_persist = bool(persist)
    _status_banner_until = time.time() + float(duration_s or 5)
    _last_render_sig = None


def clear_status_banner():
    global _status_banner_text, _status_banner_persist, _last_render_sig
    _status_banner_text = None
    _status_banner_persist = False
    _last_render_sig = None


async def screen_off():
    if oled:
        oled.poweroff()


async def screen_on():
    if oled:
        oled.poweron()
        oled.contrast(255)


async def update_display(page=0):
    """Async function expected by main.py TaskManager."""
    global _render_task, _loop_started
    if not oled:
        return
    if not _loop_started:
        _loop_started = True
        try:
            _render_task = asyncio.create_task(_render_loop())
        except Exception as e:
            print(f"[OLED] failed to start render loop: {e}")
    await asyncio.sleep(0)


def show_header():
    """Compatibility helper."""
    try:
        asyncio.create_task(update_display())
    except Exception:
        pass