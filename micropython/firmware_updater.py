# Firmware download helper for MicroPython clients; writes file to OTA_BACKUP_DIR.
# Actual flash/install must be implemented per-hardware in device-specific code.

import os
try:
    import urequests as requests
except Exception:
    import requests

# Import device settings robustly: prefer package import micropython.settings; fallback to local 'settings' if present
device_settings = None
try:
    from micropython import settings as device_settings
except Exception:
    try:
        import settings as device_settings
    except Exception:
        device_settings = None

OTA_BACKUP_DIR = getattr(device_settings, 'OTA_BACKUP_DIR', '/ota/backup') if device_settings else '/ota/backup'
OTA_MAX_FILE_BYTES = getattr(device_settings, 'OTA_MAX_FILE_BYTES', 256 * 1024) if device_settings else 256 * 1024
CHUNK_SIZE = getattr(device_settings, 'FIRMWARE_DOWNLOAD_CHUNK_SIZE', 1024) if device_settings else 1024

def download_and_apply_firmware(url, version_hint=None, target_path=None, chunk_size=CHUNK_SIZE):
    """
    Download firmware to the device OTA backup path (does not perform platform flashing).
    Returns True on successful download; actual apply is hardware-specific and should be executed by device code.
    """
    if not url:
        raise ValueError("No firmware URL provided")

    # Ensure backup dir exists (MicroPython may not support makedirs)
    try:
        os.makedirs(OTA_BACKUP_DIR, exist_ok=True)
    except Exception:
        try:
            os.mkdir(OTA_BACKUP_DIR)
        except Exception:
            pass

    if not target_path:
        fname = "firmware_{v}.bin".format(v=(version_hint or "latest"))
        target_path = OTA_BACKUP_DIR.rstrip('/') + '/' + fname

    resp = requests.get(url, stream=True, timeout=30)
    if not resp or getattr(resp, 'status_code', None) not in (200, 201):
        raise RuntimeError("HTTP error: %s" % (getattr(resp, 'status_code', None)))

    total_written = 0
    try:
        # urequests may not implement iter_content; try iter_content then fallback to content
        if hasattr(resp, 'iter_content'):
            with open(target_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    total_written += len(chunk)
                    if total_written > OTA_MAX_FILE_BYTES:
                        raise RuntimeError("Firmware exceeds maximum allowed size")
        else:
            data = getattr(resp, 'content', None)
            if data:
                with open(target_path, 'wb') as f:
                    f.write(data)
                total_written = len(data)
    finally:
        try:
            resp.close()
        except Exception:
            pass

    if not os.path.exists(target_path) or os.stat(target_path)[6] == 0:
        raise RuntimeError("Downloaded firmware is empty or missing")

    # DO NOT AUTO-FLASH: return path for device to apply safely per hardware platform
    print("Firmware downloaded to:", target_path, "size:", total_written)
    return True

# Export helper
__all__ = ['download_and_apply_firmware']
