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
    Returns dict with keys: { 'ok': bool, 'path': path, 'size': int, 'sha256':hex, 'error': msg }
    """
    if not url:
        return {'ok': False, 'error': 'no_url'}

    # Ensure backup dir exists
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

    try:
        resp = requests.get(url, stream=True, timeout=30) if hasattr(requests, 'get') else requests.get(url, timeout=30)
    except Exception as e:
        return {'ok': False, 'error': f'http_error:{e}'}

    status = getattr(resp, 'status_code', None)
    if status not in (200, 201):
        try:
            body = getattr(resp, 'text', '')[:1024]
            _note = f'HTTP {status} body_snip={body[:512]}'
        except Exception:
            _note = f'HTTP {status}'
        try:
            resp.close()
        except Exception:
            pass
        return {'ok': False, 'error': _note}

    total_written = 0
    sha = None
    try:
        # streaming write & incremental SHA256
        try:
            import uhashlib as _uh
            import ubinascii as _ub
            sha = _uh.sha256()
            if hasattr(resp, 'iter_content'):
                with open(target_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size):
                        if not chunk:
                            continue
                        f.write(chunk)
                        try:
                            sha.update(chunk)
                        except Exception:
                            # some uhashlib implementations may differ, ignore update errors
                            pass
                        total_written += len(chunk)
            else:
                data = getattr(resp, 'content', None)
                if data is None and hasattr(resp, 'text'):
                    data = getattr(resp, 'text', '').encode('utf-8', 'ignore')
                if not data:
                    data = b''
                with open(target_path, 'wb') as f:
                    f.write(data)
                try:
                    sha.update(data)
                except Exception:
                    pass
                total_written = len(data)
            hexsum = _ub.hexlify(sha.digest()).decode().lower() if sha else ''
        except Exception:
            # fallback: write whole content
            data = getattr(resp, 'content', None)
            if data is None and hasattr(resp, 'text'):
                data = getattr(resp, 'text', '').encode('utf-8', 'ignore')
            with open(target_path, 'wb') as f:
                f.write(data or b'')
            total_written = len(data or b'')
            hexsum = ''
    finally:
        try:
            resp.close()
        except Exception:
            pass

    if not os.path.exists(target_path) or os.stat(target_path)[6] == 0:
        return {'ok': False, 'error': 'empty_or_missing', 'path': target_path}

    # success
    return {'ok': True, 'path': target_path, 'size': total_written, 'sha256': hexsum}

# Export helper
__all__ = ['download_and_apply_firmware']
