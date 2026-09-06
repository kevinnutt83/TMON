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
_page_index = 0
_last_page_flip_ticks = 0
_loop_started = False

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
HEADER_HEIGHT = int(getattr(settings, 'OLED_HEADER_HEIGHT', 16))
FOOTER_HEIGHT = int(getattr(settings, 'OLED_FOOTER_HEIGHT', 8))
BODY_TOP = HEADER_HEIGHT
BODY_BOTTOM = 64 - FOOTER_HEIGHT
BODY_HEIGHT = BODY_BOTTOM - BODY_TOP

RENDER_INTERVAL_MS = 400
MAX_TEXT_CHARS = 16
PAGE_INTERVAL_MS = int(getattr(settings, 'OLED_PAGE_ROTATE_INTERVAL_S', 8) * 1000)
PAGE_NAMES = ('Summary', 'Runtime', 'Network', 'LoRa Diag', 'Health')
BODY_LINE_H = 8

_FONT5X7 = {
    ' ': (0, 0, 0, 0, 0), '-': (8, 8, 8, 8, 8), '+': (8, 8, 62, 8, 8),
    '.': (0, 0, 0, 0, 8), ':': (0, 20, 0, 20, 0), '/': (2, 4, 8, 16, 32),
    '%': (25, 2, 4, 8, 19),
    '0': (62, 81, 73, 69, 62), '1': (0, 66, 127, 64, 0),
    '2': (98, 81, 73, 73, 70), '3': (34, 65, 73, 73, 54),
    '4': (24, 20, 18, 127, 16), '5': (47, 73, 73, 73, 49),
    '6': (62, 73, 73, 73, 50), '7': (1, 1, 121, 5, 3),
    '8': (54, 73, 73, 73, 54), '9': (38, 73, 73, 73, 62),
    'A': (126, 9, 9, 9, 126), 'B': (127, 73, 73, 73, 54),
    'C': (62, 65, 65, 65, 34), 'D': (127, 65, 65, 34, 28),
    'E': (127, 73, 73, 73, 65), 'F': (127, 9, 9, 9, 1),
    'G': (62, 65, 73, 73, 122), 'H': (127, 8, 8, 8, 127),
    'I': (0, 65, 127, 65, 0), 'J': (32, 64, 65, 63, 1),
    'K': (127, 8, 20, 34, 65), 'L': (127, 64, 64, 64, 64),
    'M': (127, 2, 12, 2, 127), 'N': (127, 4, 8, 16, 127),
    'O': (62, 65, 65, 65, 62), 'P': (127, 9, 9, 9, 6),
    'Q': (62, 65, 81, 33, 94), 'R': (127, 9, 25, 41, 70),
    'S': (38, 73, 73, 73, 50), 'T': (1, 1, 127, 1, 1),
    'U': (63, 64, 64, 64, 63), 'V': (31, 32, 64, 32, 31),
    'W': (63, 64, 56, 64, 63), 'X': (99, 20, 8, 20, 99),
    'Y': (7, 8, 112, 8, 7), 'Z': (97, 81, 73, 69, 67),
}

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
        oled.text("TMON", 48, 24)
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


def _radio_level(connected, rssi, thresholds):
    if not connected:
        return 0
    return _net_bars_from_rssi(rssi, thresholds)


def _measure_text_w(text):
    try:
        return max(0, len(str(text)) * 8)
    except Exception:
        return 0


def _measure_text5_w(text):
    try:
        return max(0, len(str(text)) * 6)
    except Exception:
        return 0


def _text5(o, text, x, y):
    try:
        for char in str(text).upper():
            glyph = _FONT5X7.get(char, _FONT5X7[' '])
            for col, bits in enumerate(glyph):
                for row in range(7):
                    if bits & (1 << row):
                        o.pixel(x + col, y + row, 1)
            x += 6
    except Exception:
        pass


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
        if BODY_TOP <= y < BODY_BOTTOM and y % 8 == 0:
            o.text(str(text)[:MAX_TEXT_CHARS], 2, y)
    except Exception:
        pass


def _lora_state_label():
    if bool(getattr(sdata, 'LORA_CONNECTED', False)):
        return 'OK'
    last = getattr(sdata, 'lora_last_rx_ticks', 0)
    try:
        if last and time.ticks_diff(time.ticks_ms(), last) < 120000:
            return 'OK'
    except Exception:
        pass
    return 'WAIT'


def _header_radio_line():
    def _fmt_rssi(rssi):
        try:
            return '--' if rssi is None else '%d' % int(rssi)
        except Exception:
            return '--'
    wifi_rssi = _safe_attr(sdata, 'wifi_rssi', None)
    lora_rssi = _safe_attr(sdata, 'lora_SigStr', None)
    wifi = 'W%s' % (_fmt_rssi(wifi_rssi) if _safe_attr(sdata, 'WIFI_CONNECTED', False) else '--')
    lora = 'L%s' % (_fmt_rssi(lora_rssi) if _lora_state_label() == 'OK' else '--')
    wp = 'WP+' if getattr(settings, 'WORDPRESS_API_URL', '') else 'WP-'
    return '%s %s %s' % (wifi, lora, wp)


def _next_sync_label():
    next_expected = None
    try:
        if str(getattr(settings, 'NODE_TYPE', '')).lower() == 'remote':
            next_expected = getattr(settings, 'NEXT_LORA_SYNC_EPOCH', None)
        else:
            node_info = getattr(settings, 'REMOTE_NODE_INFO', {}) or {}
            expected = [info.get('next_expected') for info in node_info.values() if isinstance(info, dict) and info.get('next_expected')]
            next_expected = min(expected) if expected else None
        if next_expected:
            remaining = max(0, int(float(next_expected) - time.time()))
            return '%dm' % max(1, (remaining + 59) // 60)
    except Exception:
        pass
    return '--'


# ---------------------------------------------------------------------------
# Page Renderers
# ---------------------------------------------------------------------------
def _render_summary_page(o):
    y = BODY_TOP
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
        bar = _safe_attr(sdata, 'cur_bar_pres', None)
        _draw_body_line(o, y, f"Hum {humid:.0f}%  {bar:.1f}" if bar is not None else f"Hum {humid:.0f}%")
        y += BODY_LINE_H
    elif _safe_attr(sdata, 'cur_bar_pres', None) is not None:
        _draw_body_line(o, y, f"Bar {_safe_attr(sdata, 'cur_bar_pres'):.1f}")
        y += BODY_LINE_H

    if getattr(settings, 'ENABLE_LORA', False) and y < BODY_BOTTOM:
        remote_count = len(getattr(settings, 'REMOTE_NODE_INFO', {}) or {}) if str(getattr(settings, 'NODE_TYPE', '')).lower() == 'base' else 0
        _draw_body_line(o, y, 'LoRa %s%s' % (_lora_state_label(), ('  %dn' % remote_count) if remote_count else ''))
        y += BODY_LINE_H
    if y < BODY_BOTTOM:
        label = 'Sleep' if str(getattr(settings, 'NODE_TYPE', '')).lower() == 'remote' else 'Next'
        _draw_body_line(o, y, '%s %s' % (label, _next_sync_label()))


def _render_runtime_page(o):
    y = BODY_TOP
    _draw_body_line(o, y, f"Mem {int(_safe_attr(sdata, 'free_mem', 0) / 1024)}k")
    y += BODY_LINE_H
    _draw_body_line(o, y, f"CPU {_safe_attr(sdata, 'cpu_temp', '--')}")
    y += BODY_LINE_H
    _draw_body_line(o, y, f"Err {_safe_attr(sdata, 'error_count', 0)}")
    y += BODY_LINE_H
    _draw_body_line(o, y, f"Run {_safe_attr(sdata, 'script_runtime', 0)}s")


def _render_network_page(o):
    y = BODY_TOP
    if not getattr(settings, 'WORDPRESS_API_URL', ''):
        _draw_body_line(o, y, 'WP --')
        y += BODY_LINE_H
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
    y = BODY_TOP
    diag = get_diagnostics_snapshot() or {}
    lora = diag.get('lora', {}) if isinstance(diag, dict) else {}
    _draw_body_line(o, y, 'Miss %s' % lora.get('missed_syncs', 0)); y += BODY_LINE_H
    nodes = lora.get('remote_nodes', 0)
    try:
        nodes = len(getattr(settings, 'REMOTE_NODE_INFO', {}) or {}) or nodes
    except Exception:
        pass
    _draw_body_line(o, y, 'Nodes %s' % nodes); y += BODY_LINE_H
    last_hb = lora.get('last_heartbeat_ts', 0) or _safe_attr(sdata, 'lora_last_rx_ts', 0)
    if last_hb:
        age = max(0, int(time.time() - float(last_hb)))
        hb = '%ds' % age if age < 1000 else 'old'
    else:
        hb = '--'
    _draw_body_line(o, y, 'HB %s' % hb); y += BODY_LINE_H
    _draw_body_line(o, y, 'LoRa %s' % _lora_state_label()); y += BODY_LINE_H
    rssi = _safe_attr(sdata, 'lora_SigStr', None)
    _draw_body_line(o, y, 'RSSI %s' % ('--' if rssi is None else int(rssi)))


def _render_health_page(o):
    y = BODY_TOP
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
    global _last_render_sig, _body_override_lines, _body_override_until
    global _page_index, _last_page_flip_ticks

    if not oled:
        return

    oled.poweron()
    oled.contrast(255)
    _last_page_flip_ticks = time.ticks_ms()

    while True:
        try:
            now_ticks = time.ticks_ms()
            if time.ticks_diff(now_ticks, _last_page_flip_ticks) >= PAGE_INTERVAL_MS:
                _page_index = (_page_index + 1) % max(1, len(PAGE_NAMES))
                _last_page_flip_ticks = now_ticks

            if getattr(sdata, 'lora_session_busy', False):
                await asyncio.sleep_ms(RENDER_INTERVAL_MS)
                continue

            # ----- Header -----
            oled.fill_rect(0, 0, 128, HEADER_HEIGHT, 0)
            try:
                voltage = _safe_attr(sdata, 'sys_voltage', None)
                name = str(_safe_attr(settings, 'UNIT_Name', '') or _safe_attr(settings, 'UNIT_ID', '') or '').strip()[:6] or 'TMON'
                role = str(_safe_attr(settings, 'NODE_TYPE', '?') or '?')[0:1].upper()
                identity = name if name[:1].upper() == role else '%s %s' % (name, role)
                voltage_text = '--.-V' if voltage is None else '%.2fV' % float(voltage)
                _text5(oled, identity[:10], 2, 0)
                _text5(oled, voltage_text, 128 - _measure_text5_w(voltage_text) - 2, 0)
            except Exception:
                pass

            if _status_banner_text and (_status_banner_persist or time.time() < _status_banner_until):
                    _text5(oled, _banner_text(_status_banner_text, _status_banner_level)[:20], 2, 8)
            elif getattr(settings, 'DISPLAY_NET_BARS', True):
                try:
                    _text5(oled, _header_radio_line(), 2, 8)
                except Exception:
                    pass

            # ----- Body -----
            oled.fill_rect(0, BODY_TOP, 128, BODY_HEIGHT, 0)

            if _body_override_lines and time.time() < _body_override_until:
                for i, line in enumerate(_body_override_lines[: BODY_HEIGHT // BODY_LINE_H]):
                    _draw_body_line(oled, BODY_TOP + i * BODY_LINE_H, line)
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
                short_names = ('Sum', 'Run', 'Net', 'LoRa', 'Health')
                title = _page_title(_page_index)
                left = short_names[_page_index] if 0 <= _page_index < len(short_names) else title[:6]
                page = '%d/%d' % (_page_index + 1, len(PAGE_NAMES))
                footer_identity = str(_safe_attr(settings, 'UNIT_Name', '') or _safe_attr(settings, 'UNIT_ID', '') or 'TMON')[:4]
                _text5(oled, footer_identity, 2, BODY_BOTTOM)
                _text5(oled, page, 54, BODY_BOTTOM)
                _text5(oled, left, 82, BODY_BOTTOM)
            except Exception:
                pass

            oled.show()
        except Exception:
            pass

        await asyncio.sleep_ms(RENDER_INTERVAL_MS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def display_message(message, display_time_s=1.5):
    """Show a temporary message (used by boot.py)."""
    global _body_override_lines, _body_override_until, _last_render_sig
    if not oled:
        return
    try:
        _body_override_lines = [str(message or '')[:MAX_TEXT_CHARS]]
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