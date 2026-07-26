# sdcard_storage.py
# Optional SD card storage with automatic fallback to internal flash.

import os
import settings
from utils import debug_print

_sd_mounted = False
_sd_root = "/sd"

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

        _sd_mounted = True
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
    return getattr(settings, "LOG_DIR", "/logs")


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