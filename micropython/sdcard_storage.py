# sdcard_storage.py
# Optional SD card storage with automatic fallback to internal flash.

import os
import settings
from utils import debug_print

_sd_mounted = False
_sd_root = "/sd"


def _rewrite_settings_paths(old_dir, new_dir):
    """Rewrite settings path strings when log storage root changes."""
    if not old_dir or not new_dir or old_dir == new_dir:
        return
    old_prefix = old_dir.rstrip('/') + '/'
    new_prefix = new_dir.rstrip('/') + '/'
    try:
        for name in dir(settings):
            if name.startswith('__'):
                continue
            try:
                value = getattr(settings, name)
            except Exception:
                continue
            if not isinstance(value, str):
                continue
            try:
                if value == old_dir:
                    setattr(settings, name, new_dir)
                elif value.startswith(old_prefix):
                    setattr(settings, name, new_prefix + value[len(old_prefix):])
            except Exception:
                pass
    except Exception:
        pass

def try_mount_sd():
    """Attempt to mount SD card. Returns True on success."""
    global _sd_mounted
    if not getattr(settings, "ENABLE_SDCARD", False):
        return False
    try:
        from machine import SPI, Pin
        import sdcard

        spi = SPI(2,
                  sck=Pin(settings.SD_SCK_PIN),
                  mosi=Pin(settings.SD_MOSI_PIN),
                  miso=Pin(settings.SD_MISO_PIN))
        cs = Pin(settings.SD_CS_PIN, Pin.OUT)
        sd = sdcard.SDCard(spi, cs)
        os.mount(sd, _sd_root)

        for d in ["/logs", "/ota", "/backup"]:
            try:
                os.mkdir(_sd_root + d)
            except OSError:
                pass

        old_dir = settings.LOG_DIR
        _sd_mounted = True
        new_dir = _sd_root + "/logs"
        try:
            settings.LOG_DIR = new_dir
        except Exception:
            pass
        _rewrite_settings_paths(old_dir, new_dir)
        debug_print("SD card mounted successfully", "STORAGE")
        return True
    except Exception as e:
        debug_print(f"SD mount failed: {e}", "STORAGE")
        _sd_mounted = False
        return False


def get_log_dir():
    """Return the correct log directory (SD if available, otherwise internal)."""
    if _sd_mounted:
        return _sd_root + "/logs"
    return settings.LOG_DIR


def is_sd_active():
    return _sd_mounted


def unmount_sd():
    """Safely unmount SD card."""
    global _sd_mounted
    if not _sd_mounted:
        return
    try:
        os.umount(_sd_root)
    except Exception:
        pass
    _sd_mounted = False