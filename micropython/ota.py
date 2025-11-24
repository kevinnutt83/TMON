# OTA scaffolding: version check and pending flag
try:
    import urequests as requests
except Exception:
    requests = None

import settings
from config_persist import write_text
from utils import debug_print
import ujson as json
import os

def _safe_join(base: str, name: str) -> str:
    if not base.endswith('/'):
        base += '/'
    return base + name.lstrip('/')

def _ensure_dir(path: str):
    try:
        d = path.rsplit('/', 1)[0]
        if d and d != path and d != '.':
            try:
                os.stat(d)
            except Exception:
                try:
                    os.mkdir(d)
                except Exception:
                    pass
    except Exception:
        pass

def _normalize_version(s: str) -> str:
    if not s:
        return ''
    return s.strip().replace('\n', '').replace('\r', '')

def is_newer(remote: str, local: str) -> bool:
    # Simple string compare fallback; can be improved to semver later
    r = _normalize_version(remote)
    l = _normalize_version(local)
    return r and r != l

async def check_for_update():
    if not getattr(settings, 'OTA_ENABLED', True):
        return
    url = getattr(settings, 'OTA_VERSION_ENDPOINT', None)
    if not url or not requests:
        return
    try:
        resp = requests.get(url, timeout=10)
        if getattr(resp, 'status_code', 0) == 200:
            remote_ver = _normalize_version(resp.text if hasattr(resp, 'text') else '')
            if is_newer(remote_ver, getattr(settings, 'FIRMWARE_VERSION', '')):
                await debug_print(f'OTA: update available {remote_ver} (current {settings.FIRMWARE_VERSION})', 'OTA')
                # mark pending for later application flow
                try:
                    write_text(getattr(settings, 'OTA_PENDING_FILE', '/logs/ota_pending.flag'), remote_ver)
                except Exception:
                    pass
            else:
                await debug_print('OTA: firmware up to date', 'OTA')
        try:
            resp.close()
        except Exception:
            pass
    except Exception as e:
        await debug_print(f'OTA check failed: {e}', 'ERROR')

async def apply_pending_update():
    """If OTA_PENDING_FILE exists, fetch manifest and apply allowed files.
    Steps:
    - Read pending version string
    - Fetch manifest JSON (optional); filter to OTA_FILES_ALLOWLIST
    - Backup current files to OTA_BACKUP_DIR
    - Download and verify each file (sha256 when enabled)
    - Replace files atomically (best-effort)
    - On success: update FIRMWARE_VERSION and clear pending flag
    - On failure: restore from backup when configured
    """
    try:
        pending_file = getattr(settings, 'OTA_PENDING_FILE', '/logs/ota_pending.flag')
        try:
            with open(pending_file, 'r') as f:
                target_ver = _normalize_version(f.read())
        except Exception:
            return False
        base_url = getattr(settings, 'OTA_FIRMWARE_BASE_URL', '')
        if not base_url or not requests:
            return False
        # Manifest is optional but recommended
        manifest_url = getattr(settings, 'OTA_MANIFEST_URL', '')
        manifest = {}
        if manifest_url:
            try:
                r = requests.get(manifest_url, timeout=15)
                if getattr(r, 'status_code', 0) == 200:
                    manifest = json.loads(r.text) if hasattr(r, 'text') else {}
                try:
                    r.close()
                except Exception:
                    pass
            except Exception:
                manifest = {}
        # Optional manifest signature verification (HMAC)
        try:
            sig_url = getattr(settings, 'OTA_MANIFEST_SIG_URL', '')
            secret = getattr(settings, 'OTA_MANIFEST_HMAC_SECRET', '')
            if sig_url and secret:
                rs = requests.get(sig_url, timeout=10)
                if getattr(rs, 'status_code', 0) == 200:
                    remote_sig = rs.text.strip() if hasattr(rs, 'text') else ''
                    import uhashlib as _uh, ubinascii as _ub
                    h = _uh.sha256(secret.encode() + json.dumps(manifest, sort_keys=True).encode())
                    local_sig = _ub.hexlify(h.digest()).decode()
                    if remote_sig[:len(local_sig)] != local_sig:
                        await debug_print('OTA: manifest signature mismatch', 'ERROR')
                        return False
                try:
                    rs.close()
                except Exception:
                    pass
        except Exception:
            pass
        allow = getattr(settings, 'OTA_FILES_ALLOWLIST', [])
        if not allow:
            allow = ['main.py']
        backup_dir = getattr(settings, 'OTA_BACKUP_DIR', '/ota/backup')
        if getattr(settings, 'OTA_BACKUP_ENABLED', True):
            try:
                os.stat(backup_dir)
            except Exception:
                try:
                    os.makedirs(backup_dir)
                except Exception:
                    try:
                        os.mkdir(backup_dir)
                    except Exception:
                        pass
        downloaded = {}
        import ubinascii as _ub
        import uhashlib as _uh
        for name in allow:
            url = _safe_join(base_url, name)
            try:
                rr = requests.get(url, timeout=20)
                if getattr(rr, 'status_code', 0) != 200:
                    await debug_print(f'OTA: download failed {name}: {getattr(rr,"status_code",0)}', 'ERROR')
                    raise Exception('download failed')
                content = rr.content if hasattr(rr, 'content') else (rr.text.encode() if hasattr(rr, 'text') else b'')
                if not content:
                    raise Exception('empty file')
                if len(content) > int(getattr(settings, 'OTA_MAX_FILE_BYTES', 262144)):
                    raise Exception('file too large')
                if getattr(settings, 'OTA_HASH_VERIFY', True) and isinstance(manifest, dict):
                    # Support manifest as { files: { name: sha256 } } or { name: sha256 }
                    files_map = manifest.get('files', manifest)
                    expected = files_map.get(name) if isinstance(files_map, dict) else None
                    if expected:
                        h = _uh.sha256(content).digest()
                        digest = _ub.hexlify(h).decode()
                        if digest.lower() != str(expected).lower():
                            await debug_print(f'OTA: hash mismatch for {name}', 'ERROR')
                            raise Exception('hash mismatch')
                downloaded[name] = content
            except Exception as e:
                try:
                    rr.close()
                except Exception:
                    pass
                # Abort and optionally restore
                if getattr(settings, 'OTA_RESTORE_ON_FAIL', True):
                    await debug_print(f'OTA: abort due to error {e}', 'ERROR')
                return False
            finally:
                try:
                    rr.close()
                except Exception:
                    pass
        # Backup and apply
        for name, data in downloaded.items():
            try:
                # Backup existing file
                src = name
                if getattr(settings, 'OTA_BACKUP_ENABLED', True):
                    _ensure_dir(backup_dir + '/' + name)
                    try:
                        with open(src, 'rb') as sf:
                            with open(backup_dir + '/' + name, 'wb') as bf:
                                bf.write(sf.read())
                    except Exception:
                        pass
                # Write new file
                _ensure_dir(src)
                with open(src, 'wb') as out:
                    out.write(data)
            except Exception as e:
                await debug_print(f'OTA: apply failed for {name}: {e}', 'ERROR')
                if getattr(settings, 'OTA_RESTORE_ON_FAIL', True):
                    # Try to restore backups
                    try:
                        with open(backup_dir + '/' + name, 'rb') as bf:
                            with open(src, 'wb') as sf:
                                sf.write(bf.read())
                    except Exception:
                        pass
                return False
        # Success: update version and clear pending
        try:
            settings.FIRMWARE_VERSION = target_ver
        except Exception:
            pass
        try:
            os.remove(pending_file)
        except Exception:
            pass
        await debug_print('OTA: apply completed', 'OTA')
        return True
    except Exception as e:
        await debug_print(f'OTA apply exception: {e}', 'ERROR')
        return False
