# TMON Verion 2.00.1d - OTA update module for TMON MicroPython firmware. This module defines functions to check for available firmware updates from a configured endpoint, and to apply pending updates by fetching files listed in a manifest, verifying their integrity, and replacing existing files on the device. The OTA process includes robust error handling, retry logic, and diagnostic artifact generation to facilitate troubleshooting. It also includes GC management to ensure stability during potentially heavy operations on resource-constrained hardware. The check_for_update function can be called periodically to detect new firmware versions, while apply_pending_update can be called at startup to apply any updates that have been flagged as pending.

# OTA scaffolding: version check and pending flag
try:
    import urequests as requests
except Exception:
    requests = None

# Ensure we can use asyncio.sleep in this async module
try:
    import uasyncio as asyncio
except Exception:
    try:
        import asyncio
    except Exception:
        asyncio = None

async def _sleep(seconds):
    """Robust async sleep: prefer event loop sleep, fall back to blocking sleep."""
    try:
        if 'asyncio' in globals() and asyncio:
            await asyncio.sleep(seconds)
            return
    except Exception:
        pass
    # Try common async variants dynamically
    try:
        import uasyncio as _u
        await _u.sleep(seconds)
        return
    except Exception:
        pass
    try:
        import asyncio as _a
        await _a.sleep(seconds)
        return
    except Exception:
        pass
    # Last-resort blocking sleep to avoid NameError during retries
    try:
        import utime as _t
        _t.sleep(seconds)
    except Exception:
        try:
            import time as _t
            _t.sleep(seconds)
        except Exception:
            # give up silently
            pass

import settings
from config_persist import write_text
from utils import debug_print
# NEW: GC helper
from utils import maybe_gc
import ujson as json
import os
import binascii as _binascii
import re as _re

def _safe_join(base: str, name: str) -> str
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

def _normalize_version(s: str) -> str
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
        status = getattr(resp, 'status_code', None)
        if status == 200:
            remote_ver = _normalize_version(resp.text if hasattr(resp, 'text') else '')
            await debug_print(f'ota: ver {remote_ver} fetched', 'OTA')
            if is_newer(remote_ver, getattr(settings, 'FIRMWARE_VERSION', '')):
                await debug_print(f'ota: update {remote_ver} available', 'OTA')
                try:
                    from oled import display_message
                    # concise user message
                    import uasyncio
                    await display_message("OTA Available", 2)
                except Exception:
                    pass
                try:
                    write_text(getattr(settings, 'OTA_PENDING_FILE', '/logs/ota_pending.flag'), remote_ver)
                except Exception:
                    pass
            else:
                await debug_print('ota: up-to-date', 'OTA')
                try:
                    from oled import display_message
                    await display_message("OTA Up-to-date", 1.5)
                except Exception:
                    pass
        else:
            await debug_print(f'ota: ver fetch {status}', 'ERROR')
        try:
            resp.close()
        except Exception:
            pass
        # NEW: GC after HTTP response handling
        try:
            maybe_gc("ota_check_for_update", min_interval_ms=8000, mem_free_below=45 * 1024)
        except Exception:
            pass
    except Exception as e:
        await debug_print(f'OTA check failed: {e}', 'ERROR')

# Helper: write debug artifact
def _write_debug_artifact(name, data_bytes):
    try:
        dbg_dir = getattr(settings, 'LOG_DIR', '/logs')
        try:
            os.stat(dbg_dir)
        except Exception:
            try:
                os.mkdir(dbg_dir)
            except Exception:
                pass
        path = dbg_dir.rstrip('/') + '/' + name
        with open(path, 'wb') as wf:
            wf.write(data_bytes)
    except Exception:
        pass

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
            await debug_print('OTA: no base URL or requests unavailable', 'ERROR')
            return False

        # Fetch manifest (support multiple fallbacks)
        manifest = {}
        manifest_urls = getattr(settings, 'OTA_MANIFEST_URLS', [getattr(settings, 'OTA_MANIFEST_URL','')])
        manifest_fetched = False
        for murl in manifest_urls:
            if not murl:
                continue
            try:
                await debug_print(f'OTA: fetching manifest {murl}', 'OTA')
                r = requests.get(murl, timeout=15)
                status = getattr(r, 'status_code', None)
                body = getattr(r, 'text', '') if hasattr(r, 'text') else ''
                await debug_print(f'OTA: manifest response {status} length={len(body)}', 'OTA')
                if status == 200 and body:
                    # NEW: quick scan for placeholder/invalid hashes (e.g., sha256:0000...)
                    try:
                        js = json.loads(body)
                        bad_files = []
                        files = js.get('files') if isinstance(js, dict) else {}
                        if isinstance(files, dict):
                            for fname, hval in files.items():
                                hv = str(hval or '').lower()
                                m = _re.search(r'([0-9a-f]{64})', hv)
                                if not m:
                                    continuation = False
                                else:
                                    hexpart = m.group(1)
                                    # treat all-zero hex (placeholder) as invalid manifest
                                    if hexpart == ('0'*64):
                                        bad_files.append(fname)
                        if bad_files:
                            await debug_print(f'OTA: manifest contains placeholder hashes for files: {bad_files}; aborting manifest', 'ERROR')
                            try:
                                _write_debug_artifact('ota_manifest_placeholder_hashes.txt', (json.dumps({'url': murl, 'bad_files': bad_files}, indent=2)).encode('utf-8'))
                            except Exception:
                                pass
                            try:
                                r.close()
                            except Exception:
                                pass
                            # try next manifest URL if available
                            continue
                    except Exception:
                        # if we cannot parse, proceed to the normal signature/parse flow
                        pass

                    # NEW: verify detached sig or HMAC secret if configured
                    sig_url = getattr(settings, 'OTA_MANIFEST_SIG_URL', '') or ''
                    secret = getattr(settings, 'OTA_MANIFEST_HMAC_SECRET', '') or ''
                    if sig_url or secret:
                        ok_sig = _verify_manifest_signature(body, sig_url, secret)
                        if not ok_sig:
                            await debug_print(f'OTA: manifest signature/HMAC verification failed for {murl}; trying next manifest', 'ERROR')
                            try:
                                _write_debug_artifact('ota_manifest_bad_signature.txt', (body or '').encode('utf-8', 'ignore'))
                            except Exception:
                                pass
                            try:
                                r.close()
                            except Exception:
                                pass
                            continue
                    try:
                        manifest = json.loads(body)
                        manifest_fetched = True
                        # NEW: GC after manifest parse/persist
                        try:
                            maybe_gc("ota_manifest_loaded", min_interval_ms=3000, mem_free_below=55 * 1024)
                        except Exception:
                            pass
                        # persist manifest for analysis
                        try:
                            mpath = getattr(settings, 'LOG_DIR','/logs').rstrip('/') + '/ota_manifest.json'
                            with open(mpath, 'w') as mf:
                                mf.write(json.dumps(manifest, indent=2))
                            await debug_print(f'OTA: manifest saved to {mpath}', 'OTA')
                        except Exception:
                            pass
                        try:
                            r.close()
                        except Exception:
                            pass
                        break
                    except Exception as pe:
                        await debug_print(f'OTA: manifest parse failed from {murl}: {pe}', 'ERROR')
                        # save page for inspection
                        try:
                            _write_debug_artifact('ota_manifest_fetch_error.txt', (body or '').encode('utf-8', 'ignore'))
                        except Exception:
                            pass
                else:
                    await debug_print(f'OTA: manifest fetch returned {status} from {murl}', 'ERROR')
                    try:
                        _write_debug_artifact('ota_manifest_fetch_response.txt', (body or '').encode('utf-8', 'ignore'))
                    except Exception:
                        pass
                try:
                    r.close()
                except Exception:
                    pass
            except Exception as e:
                await debug_print(f'OTA: manifest request exception for {murl}: {e}', 'ERROR')

        if not manifest_fetched:
            await debug_print('OTA: manifest not available; aborting OTA apply', 'ERROR')
            return False

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

        import ubinascii as _ub
        import uhashlib as _uh

        max_hash_failures = int(getattr(settings, 'OTA_MAX_HASH_FAILURES', 3))
        retry_interval_s = int(getattr(settings, 'OTA_HASH_RETRY_INTERVAL_S', 2))

        downloaded = {}
        for name in allow:
            expected_hex = None
            # Support manifest formats: { "files": { name: sha256 } } or { name: sha256 } or manifest['files'][name]['sha256']
            try:
                if isinstance(manifest, dict):
                    if 'files' in manifest and isinstance(manifest['files'], dict):
                        fentry = manifest['files'].get(name)
                        if isinstance(fentry, dict):
                            expected_hex = fentry.get('sha256') or fentry.get('hash')
                        else:
                            expected_hex = manifest['files'].get(name)
                    else:
                        entry = manifest.get(name)
                        if isinstance(entry, dict):
                            expected_hex = entry.get('sha256') or entry.get('hash')
                        else:
                            expected_hex = entry
                if expected_hex:
                    # normalize various manifest formats like "sha256:hex" or just "hex"
                    expected_hex = str(expected_hex).lower().split(':')[-1].strip()
                    if len(expected_hex) != 64 or not all(c in '0123456789abcdef' for c in expected_hex):
                        expected_hex = None
            except Exception:
                expected_hex = None

            url = _safe_join(base_url, name)
            hash_failures = 0
            while hash_failures < max_hash_failures:
                try:
                    await debug_print(f'OTA: downloading {name} from {url}', 'OTA')
                    r = requests.get(url, timeout=30)
                    status = getattr(r, 'status_code', None)
                    if status != 200:
                        await debug_print(f'OTA: download {name} {status}', 'ERROR')
                        break
                    content = r.content if hasattr(r, 'content') else r.text.encode('utf-8')
                    try:
                        r.close()
                    except Exception:
                        pass
                    if not content:
                        await debug_print(f'OTA: empty file {name}', 'ERROR')
                        break
                    if len(content) > getattr(settings, 'OTA_MAX_FILE_BYTES', 256*1024):
                        await debug_print(f'OTA: file {name} too large', 'ERROR')
                        break

                    # Verify hash if enabled and expected provided
                    if getattr(settings, 'OTA_HASH_VERIFY', True) and expected_hex:
                        hasher = _uh.sha256()
                        hasher.update(content)
                        actual_hex = _ub.hexlify(hasher.digest()).decode().lower()
                        if actual_hex != expected_hex:
                            await debug_print(f'OTA: hash mismatch {name} expected {expected_hex[:16]}... actual {actual_hex[:16]}...', 'ERROR')
                            hash_failures += 1
                            if getattr(settings, 'OTA_ABORT_ON_HASH_MISMATCH', False):
                                return False
                            if getattr(settings, 'OTA_RETRY_ON_HASH_MISMATCH', True):
                                await _sleep(retry_interval_s)
                                continue
                            break

                    # Backup current if exists
                    target_path = '/' + name.lstrip('/')
                    backup_path = _safe_join(backup_dir, name)
                    try:
                        _ensure_dir(backup_path)
                        if os.stat(target_path):
                            with open(target_path, 'rb') as src, open(backup_path, 'wb') as dst:
                                dst.write(src.read())
                    except Exception:
                        pass

                    # Write new
                    _ensure_dir(target_path)
                    with open(target_path, 'wb') as wf:
                        wf.write(content)
                    downloaded[name] = True
                    await debug_print(f'OTA: applied {name}', 'OTA')
                except Exception as e:
                    await debug_print(f'OTA: download/apply {name} exc {e}', 'ERROR')
                    break

        if downloaded:
            await debug_print('OTA: apply success; updating version', 'OTA')
            settings.FIRMWARE_VERSION = target_ver
            try:
                os.remove(pending_file)
            except Exception:
                pass
            machine.reset()
        else:
            await debug_print('OTA: no files applied', 'WARN')
            if getattr(settings, 'OTA_RESTORE_ON_FAIL', True):
                for name in allow:
                    backup_path = _safe_join(backup_dir, name)
                    target_path = '/' + name.lstrip('/')
                    try:
                        if os.stat(backup_path):
                            with open(backup_path, 'rb') as src, open(target_path, 'wb') as dst:
                                dst.write(src.read())
                    except Exception:
                        pass
        return bool(downloaded)
    except Exception as e:
        await debug_print(f'OTA apply exc {e}', 'ERROR')
        return False

async def apply_from_local(manifest_path='/logs/ota_manifest.json'):
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)

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

        import ubinascii as _ub
        import uhashlib as _uh

        applied = {}
        for name in allow:
            expected_hex = None
            # Get expected hash from manifest
            try:
                if isinstance(manifest, dict):
                    if 'files' in manifest and isinstance(manifest['files'], dict):
                        fentry = manifest['files'].get(name)
                        if isinstance(fentry, dict):
                            expected_hex = fentry.get('sha256') or fentry.get('hash')
                        else:
                            expected_hex = manifest['files'].get(name)
                    else:
                        entry = manifest.get(name)
                        if isinstance(entry, dict):
                            expected_hex = entry.get('sha256') or entry.get('hash')
                        else:
                            expected_hex = entry
                if expected_hex:
                    expected_hex = str(expected_hex).lower().split(':')[-1].strip()
                    if len(expected_hex) != 64 or not all(c in '0123456789abcdef' for c in expected_hex):
                        expected_hex = None
            except Exception:
                expected_hex = None

            local_path = '/logs/' + name
            try:
                with open(local_path, 'rb') as f:
                    content = f.read()
            except Exception:
                await debug_print(f'OTA local: missing {name}', 'ERROR')
                continue

            if not content:
                await debug_print(f'OTA local: empty {name}', 'ERROR')
                continue

            # Verify hash if enabled and expected provided
            if getattr(settings, 'OTA_HASH_VERIFY', True) and expected_hex:
                hasher = _uh.sha256()
                hasher.update(content)
                actual_hex = _ub.hexlify(hasher.digest()).decode().lower()
                if actual_hex != expected_hex:
                    await debug_print(f'OTA local: hash mismatch {name}', 'ERROR')
                    continue

            # Backup current if exists
            target_path = '/' + name.lstrip('/')
            backup_path = _safe_join(backup_dir, name)
            try:
                _ensure_dir(backup_path)
                if os.stat(target_path):
                    with open(target_path, 'rb') as src, open(backup_path, 'wb') as dst:
                        dst.write(src.read())
            except Exception:
                pass

            # Write new
            _ensure_dir(target_path)
            with open(target_path, 'wb') as wf:
                wf.write(content)
            applied[name] = True
            await debug_print(f'OTA local: applied {name}', 'OTA')

        if applied:
            await debug_print('OTA local: apply success; rebooting', 'OTA')
            machine.reset()
        else:
            await debug_print('OTA local: no files applied', 'WARN')
            if getattr(settings, 'OTA_RESTORE_ON_FAIL', True):
                for name in allow:
                    backup_path = _safe_join(backup_dir, name)
                    target_path = '/' + name.lstrip('/')
                    try:
                        if os.stat(backup_path):
                            with open(backup_path, 'rb') as src, open(target_path, 'wb') as dst:
                                dst.write(src.read())
                    except Exception:
                        pass
        return bool(applied)
    except Exception as e:
        await debug_print(f'OTA local apply exc {e}', 'ERROR')
        return False

def _const_time_eq(a, b):
    try:
        if isinstance(a, str): a = a.encode('utf-8')
        if isinstance(b, str): b = b.encode('utf-8')
        if len(a) != len(b):
            return False
        res = 0
        for x, y in zip(a, b):
            res |= x ^ y
        return res == 0
    except Exception:
        return False

def _normalize_sig_text(sig_txt):
    """Return raw hex string (lowercase) if recognized, else None.
       Accept formats: raw hex, 'sha256:<hex>', or base64 (decode to hex)."""
    if not sig_txt:
        return None
    s = sig_txt.strip()
    # strip sha256: prefix
    for p in ('sha256:', 'sha256=', 'sha256-'):
        if s.lower().startswith(p):
            s = s[len(p):]
            break
    s = s.strip()
    # If looks like hex
    try:
        if all(c in '0123456789abcdefABCDEF' for c in s) and len(s) >= 64:
            return s.lower()
    except Exception:
        pass
    # Try base64 decode
    try:
        raw = _binascii.a2b_base64(s)
        return _binascii.hexlify(raw).decode().lower()
    except Exception:
        pass
    return None

def _verify_manifest_signature(body_text, sig_url, secret):
    try:
        if not secret and not sig_url:
            return True
        # If signature URL present, fetch and normalize
        sig_hex = None
        if sig_url and requests:
            try:
                sresp = requests.get(sig_url, timeout=10)
            except TypeError:
                sresp = requests.get(sig_url)
            if sresp and getattr(sresp, 'status_code', 0) == 200:
                raw_sig = (getattr(sresp, 'text', '') or '').strip().splitlines()[0]
                sig_hex = _normalize_sig_text(raw_sig)
            try:
                if sresp: sresp.close()
            except Exception:
                pass
            if not sig_hex and secret:
                # If remote signature missing but secret present, reject (explicit policy)
                return False
        # If secret present, compute expected HMAC-SHA256 and compare
        if secret:
            try:
                import hmac as _h, hashlib as _hl
                expected = _h.new(secret.encode(), body_text.encode('utf-8'), _hl.sha256).hexdigest().lower()
            except Exception:
                try:
                    import uhashlib as _uh
                    h = _uh.sha256(secret.encode() + body_text.encode('utf-8'))
                    expected = _binascii.hexlify(h.digest()).decode().lower()
                except Exception:
                    return False
            if sig_hex:
                return _const_time_eq(expected.encode('ascii'), sig_hex.encode('ascii'))
            # If no sig_hex but secret provided treat signature absence as failure
            return False
        # If no secret but sig_hex present, compute plain sha256 of manifest body and compare
        if sig_hex:
            try:
                import hashlib as _hl
                computed = _hl.sha256(body_text.encode('utf-8')).hexdigest().lower()
            except Exception:
                try:
                    import uhashlib as _uh
                    computed = _binascii.hexlify(_uh.sha256(body_text.encode('utf-8')).digest()).decode().lower()
                except Exception:
                    return False
            return _const_time_eq(computed.encode('ascii'), sig_hex.encode('ascii'))
        return True
    except Exception:
        return False
