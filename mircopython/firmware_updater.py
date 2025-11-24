# Minimal firmware downloader; uses settings in mircopython/settings.py where available.

import os
try:
    import urequests as requests
except Exception:
    import requests  # fallback
try:
    import settings as settings
except Exception:
    settings = None

# Use OTA-related settings if present
OTA_BASE_URL = getattr(settings, 'OTA_FIRMWARE_BASE_URL', None) if settings else None
OTA_MAX_FILE_BYTES = getattr(settings, 'OTA_MAX_FILE_BYTES', 256 * 1024) if settings else 256 * 1024
OTA_BACKUP_DIR = getattr(settings, 'OTA_BACKUP_DIR', '/ota/backup') if settings else '/ota/backup'
CHUNK_SIZE = getattr(settings, 'FIRMWARE_DOWNLOAD_CHUNK_SIZE', 1024) if settings else 1024

def download_and_apply_firmware(url, version_hint=None, target_path=None, chunk_size=CHUNK_SIZE):
    """
    Download firmware and implement hardware-specific flash logic.
    Returns True on download success (install is device-specific).
    """
    if not url:
        raise ValueError("No firmware URL provided")

    # Default download location: use OTA_BACKUP_DIR if provided
    if not target_path:
        os.makedirs(OTA_BACKUP_DIR, exist_ok=True)
        fname = "firmware_{v}.bin".format(v=version_hint or "latest")
        target_path = os.path.join(OTA_BACKUP_DIR, fname)

    # Basic safety checks
    req = requests.get(url, stream=True, timeout=30)
    if not req or getattr(req, 'status_code', 0) not in (200, 201):
        raise RuntimeError("HTTP error or no response: %s" % (getattr(req, 'status_code', None)))

    total_written = 0
    try:
        with open(target_path, 'wb') as f:
            # urequests iter_content may not be implemented the same as CPython; handle generically
            try:
                for chunk in req.iter_content(chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    total_written += len(chunk)
                    if total_written > OTA_MAX_FILE_BYTES:
                        raise RuntimeError("Firmware exceeds maximum allowed size")
            except AttributeError:
                # Fallback: read by .raw.read for streams or .content for small files
                data = getattr(req, 'content', None)
                if data:
                    f.write(data)
                    total_written = len(data)
    finally:
        try:
            req.close()
        except Exception:
            pass

    if not os.path.exists(target_path) or os.stat(target_path)[6] == 0:
        raise RuntimeError("Downloaded firmware is empty or missing")

    # Platform-specific: call the actual flashing path here.
    # For safety, we only write the file; flashing must be implemented for the target platform.
    print("Firmware downloaded to:", target_path, "size:", total_written)
    # Optionally, return path and let caller trigger flashing code
    return True
