# Firmware download helper for MicroPython clients; writes file to OTA_BACKUP_DIR.
# Actual flash/install must be implemented per-hardware in device-specific code.

import os
from platform_compat import requests  # CHANGED

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

# --- New helpers for SHA256 and manifest lookup ---
def _get_hashlib():
    try:
        import uhashlib as _uh
        import ubinascii as _ub
        return _uh, _ub
    except Exception:
        import hashlib as _uh
        import binascii as _ub
        return _uh, _ub

def compute_file_sha256(path):
    _uh, _ub = _get_hashlib()
    h = _uh.sha256()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                try:
                    h.update(chunk)
                except Exception:
                    # some uhashlib variants may behave differently; ignore update errors
                    pass
    except Exception:
        return ''
    try:
        digest = h.digest()
        hexsum = _ub.hexlify(digest).decode().lower()
    except Exception:
        # fallback: attempt hexdigest or empty
        try:
            hexsum = h.hexdigest().lower()
        except Exception:
            hexsum = ''
    return hexsum

def fetch_manifest_expected_sha(manifest_url, filename):
    """
    Fetch manifest JSON from manifest_url and try to find the expected sha for filename.
    Returns expected sha hex (no 'sha256:' prefix) or None on failure.
    """
    if not manifest_url:
        return None
    try:
        r = requests.get(manifest_url, timeout=10) if hasattr(requests, 'get') else requests.get(manifest_url)
        if not r:
            return None
        try:
            mj = r.json()
        except Exception:
            import json as _json
            try:
                mj = _json.loads(getattr(r, 'text', '') or '{}')
            except Exception:
                mj = {}
        try:
            r.close()
        except Exception:
            pass
        files = mj.get('files', {}) if isinstance(mj, dict) else {}
        if not files:
            return None
        # direct match
        if filename in files:
            val = files[filename]
            return val.split(':', 1)[1] if isinstance(val, str) and ':' in val else None
        # fallback: try basename match
        import os as _os
        base = _os.path.basename(filename)
        for k, v in files.items():
            if _os.path.basename(k) == base:
                return v.split(':', 1)[1] if isinstance(v, str) and ':' in v else None
    except Exception:
        pass
    return None

# --- Modified download function: verify against expected or manifest ---
def download_and_apply_firmware(url, version_hint=None, target_path=None, chunk_size=CHUNK_SIZE, expected_sha=None, manifest_url=None):
    """
    Download firmware to the device OTA backup path and verify SHA against expected_sha or manifest_url.
    Returns dict: {
      'ok': bool,
      'path': path,
      'size': int,
      'sha256': computed_hex,
      'expected_sha': expected_hex_or_none,
      'manifest_checked': bool,
      'error': msg
    }
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

    # If manifest_url provided and expected_sha not given, attempt to fetch expected sha first
    manifest_checked = False
    server_expected = None
    try:
        if manifest_url and not expected_sha:
            # Use the filename part of URL as hint
            import os as _os
            fname_hint = _os.path.basename(url) or (version_hint or 'firmware.bin')
            server_expected = fetch_manifest_expected_sha(manifest_url, fname_hint)
            if server_expected:
                expected_sha = server_expected
            manifest_checked = True
    except Exception:
        pass

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
    try:
        # streaming write
        if hasattr(resp, 'iter_content'):
            with open(target_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    total_written += len(chunk)
        else:
            data = getattr(resp, 'content', None)
            if data is None and hasattr(resp, 'text'):
                data = getattr(resp, 'text', '').encode('utf-8', 'ignore')
            if not data:
                data = b''
            with open(target_path, 'wb') as f:
                f.write(data)
            total_written = len(data)
    finally:
        try:
            resp.close()
        except Exception:
            pass

    if not os.path.exists(target_path) or os.stat(target_path)[6] == 0:
        return {'ok': False, 'error': 'empty_or_missing', 'path': target_path}

    # Compute SHA256 of downloaded file
    computed = compute_file_sha256(target_path)

    # NEW: GC after file hash computation
    try:
        import gc
        gc.collect()
    except Exception:
        pass

    # If expected_sha not known and manifest_url provided, try fetching manifest now
    if not expected_sha and manifest_url:
        try:
            import os as _os
            fname_hint = _os.path.basename(url) or (version_hint or 'firmware.bin')
            server_expected = fetch_manifest_expected_sha(manifest_url, fname_hint)
            if server_expected:
                expected_sha = server_expected
            manifest_checked = True
        except Exception:
            pass

    # Compare if expected present
    if expected_sha:
        # Normalize (strip sha256: if present)
        if expected_sha.lower().startswith('sha256:'):
            expected_sha_clean = expected_sha.split(':', 1)[1].lower()
        else:
            expected_sha_clean = expected_sha.lower()
        if computed != expected_sha_clean:
            # Final attempt: if manifest_url was not fetched earlier, try fetching and re-evaluating server value
            if manifest_url and not manifest_checked:
                try:
                    import os as _os
                    fname_hint = _os.path.basename(url) or (version_hint or 'firmware.bin')
                    server_expected = fetch_manifest_expected_sha(manifest_url, fname_hint)
                    if server_expected and server_expected.lower() == computed:
                        return {'ok': True, 'path': target_path, 'size': total_written, 'sha256': computed, 'expected_sha': server_expected, 'manifest_checked': True}
                except Exception:
                    pass
            return {
                'ok': False,
                'path': target_path,
                'size': total_written,
                'sha256': computed,
                'expected_sha': expected_sha_clean,
                'manifest_checked': bool(manifest_checked),
                'error': 'hash_mismatch'
            }

    # NEW: GC on success path as well (post-IO)
    try:
        import gc
        gc.collect()
    except Exception:
        pass

    return {'ok': True, 'path': target_path, 'size': total_written, 'sha256': computed, 'expected_sha': (expected_sha or None), 'manifest_checked': bool(manifest_checked)}

# Export helper
__all__ = ['download_and_apply_firmware']

"""
Optional firmware updater hook.

Provisioning calls this if present; keep it as a no-op unless/until a real implementation is added.
"""

def download_and_apply_firmware(url, version_hint=None, chunk_size=1024):
    try:
        print("firmware_updater: no-op download_and_apply_firmware:", url, version_hint)
    except Exception:
        pass
    return True
