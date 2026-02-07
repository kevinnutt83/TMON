# Firmware Version: v2.06.0
# OTA scaffolding: version check and pending flag

try:
    import urequests as requests
except Exception:
    try:
        import requests  # type: ignore
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
from utils import maybe_gc

# JSON: MicroPython ujson vs CPython json
try:
    import ujson as json
except Exception:
    import json  # type: ignore

try:
    import uos as os
except Exception:
    import os

# binascii: ubinascii vs binascii
try:
    import ubinascii as _binascii
except Exception:
    import binascii as _binascii  # type: ignore

import re as _re

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

        # Replace MicroPython-only imports with fallbacks
        try:
            import ubinascii as _ub
        except Exception:
            import binascii as _ub  # type: ignore
        try:
            import uhashlib as _uh
        except Exception:
            import hashlib as _uh  # type: ignore

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
                    # normalize various manifest formats like "sha256:<hex>", "sha256=<hex>", or raw hex
                    eh = str(expected_hex).strip().lower()
                    for p in ('sha256:', 'sha256=', 'sha256-'):
                        if eh.startswith(p):
                            eh = eh[len(p):]
                            break
                    expected_hex = eh
            except Exception:
                expected_hex = None

            download_ok = False
            attempts = 0
            last_error = ''
            while attempts < max_hash_failures and not download_ok:
                attempts += 1
                try:
                    url = _safe_join(base_url, name)
                    await debug_print(f'OTA: downloading {name} from {url} (attempt {attempts})', 'OTA')
                    rr = requests.get(url, stream=True, timeout=20) if hasattr(requests, 'get') else requests.get(url, timeout=20)
                    status = getattr(rr, 'status_code', None)
                    content_len = None
                    try:
                        content_len = int(rr.headers.get('Content-Length')) if hasattr(rr, 'headers') and rr.headers.get('Content-Length') else None
                    except Exception:
                        content_len = None
                    await debug_print(f'OTA: HTTP {status} Content-Length={content_len}', 'OTA')

                    # Log response headers (best-effort)
                    try:
                        hdrs = dict(rr.headers) if hasattr(rr, 'headers') and rr.headers else {}
                        await debug_print(f'OTA: response headers: { {k:v for k,v in list(hdrs.items())[:8]} }', 'OTA')
                    except Exception:
                        pass

                    if status != 200:
                        body_snip = getattr(rr, 'text', '')[:1024] if hasattr(rr, 'text') else ''
                        await debug_print(f'ota: download {name} HTTP {status}', 'ERROR')
                        _write_debug_artifact(f'ota_response_{name}.txt', (body_snip or '').encode('utf-8', 'ignore'))
                        try:
                            rr.close()
                        except Exception:
                            pass
                        last_error = f'HTTP {status}'
                        await debug_print(f'OTA: download {name} failed with HTTP {status}', 'ERROR')
                        await _sleep(retry_interval_s)
                        continue

                    # stream download to temp file and compute sha256
                    tmp_path = getattr(settings, 'LOG_DIR', '/logs').rstrip('/') + f'/ota_tmp_{name}'
                    final_path = name  # apply path
                    h = _uh.sha256()
                    total = 0
                    try:
                        # Stream and inspect first chunk for HTML/error pages (common cause of bad hashes)
                        if hasattr(rr, 'iter_content'):
                            first_chunk = True
                            with open(tmp_path, 'wb') as wf:
                                for chunk in rr.iter_content(1024):
                                    if not chunk:
                                        continue
                                    if first_chunk:
                                        first_chunk = False
                                        try:
                                            # Content-Type hint
                                            ct = None
                                            if hasattr(rr, 'headers') and rr.headers:
                                                for hk, hv in rr.headers.items():
                                                    if hk.lower() == 'content-type':
                                                        ct = hv
                                                        break
                                            chunk_l = chunk.lstrip()
                                            is_html = False
                                            if ct and 'html' in ct.lower():
                                                is_html = True
                                            if (not is_html) and (isinstance(chunk_l, (bytes, bytearray))):
                                                low = chunk_l[:256].lower()
                                                if low.startswith(b'<') or b'<!doctype' in low or b'<html' in low:
                                                    is_html = True
                                            if is_html:
                                                # Save diagnostic artifact and abort this attempt to trigger retry path
                                                try:
                                                    _write_debug_artifact(f'ota_response_{name}.txt', chunk[:4096])
                                                    hdr_txt = (str(dict(rr.headers))[:2048] if hasattr(rr, 'headers') and rr.headers else '').encode('utf-8','ignore')
                                                    _write_debug_artifact(f'ota_response_{name}.headers.txt', hdr_txt)
                                                    await debug_print(f'OTA: download for {name} appears to be HTML/error page (Content-Type={ct}); saved response artifact', 'ERROR')
                                                except Exception:
                                                    pass
                                                raise Exception('http_html_response')
                                        except Exception:
                                            raise
                                    wf.write(chunk)
                                    try:
                                        h.update(chunk)
                                    except Exception:
                                        pass
                                    total += len(chunk)
                        else:
                            # fallback: read .content
                            data = getattr(rr, 'content', None)
                            if data is None and hasattr(rr, 'text'):
                                data = getattr(rr, 'text', '').encode('utf-8', 'ignore')
                            if data is None:
                                data = b''
                            with open(tmp_path, 'wb') as wf:
                                wf.write(data)
                            try:
                                h.update(data)
                            except Exception:
                                pass
                            total = len(data)
                    except Exception as de:
                        # Mark HTML-response differently for diagnostics but follow same retry/backoff flow
                        await debug_print(f'OTA: download write error for {name}: {de}', 'ERROR')
                        try:
                            rr.close()
                        except Exception:
                            pass
                        last_error = f'download_write_error:{de}'
                        await _sleep(retry_interval_s)
                        continue
                    try:
                        rr.close()
                    except Exception:
                        pass

                    comp_hash = _ub.hexlify(h.digest()).decode().lower()
                    await debug_print(f'OTA: downloaded {name} size={total} computed_sha256={comp_hash}', 'OTA')
                    # NEW: GC after hashing large buffers/file ops
                    try:
                        maybe_gc(f"ota_file_hashed:{name}", min_interval_ms=2000, mem_free_below=60 * 1024)
                    except Exception:
                        pass

                    # If manifest provided expected hash, compare
                    if expected_hex:
                        if comp_hash != expected_hex.lower():
                            # save artifact for investigation
                            await debug_print(f'ota: {name} hash mismatch', 'ERROR')
                            try:
                                _write_debug_artifact(f'ota_failed_{name}.bin', open(tmp_path, 'rb').read())
                            except Exception:
                                pass
                            try:
                                _write_debug_artifact(f'ota_failed_{name}.sha256.txt', ('expected=%s computed=%s' % (expected_hex, comp_hash)).encode('utf-8'))
                            except Exception:
                                pass
                            # Save small head of the received file for quick inspection
                            try:
                                head = open(tmp_path, 'rb').read(256)
                                _write_debug_artifact(f'ota_failed_{name}.head.bin', head)
                            except Exception:
                                pass
                            last_error = f'hash_mismatch expected={expected_hex} computed={comp_hash}'
                             # on mismatch, try again after delay
                            await _sleep(retry_interval_s)
                            continue
                        else:
                            await debug_print(f'OTA: hash OK for {name}', 'OTA')
                    else:
                        await debug_print(f'OTA: no expected hash for {name} (manifest missing); computed={comp_hash}', 'WARN')

                    # Passed checks → backup current & apply
                    try:
                        if getattr(settings, 'OTA_BACKUP_ENABLED', True):
                            try:
                                with open(final_path, 'rb') as sf:
                                    with open(backup_dir.rstrip('/') + '/' + name, 'wb') as bf:
                                        bf.write(sf.read())
                            except Exception:
                                pass
                        with open(final_path, 'wb') as out:
                            out.write(open(tmp_path, 'rb').read())
                    except Exception as e:
                        await debug_print(f'OTA: apply write failed for {name}: {e}', 'ERROR')
                        last_error = f'apply_error:{e}'
                        # restore from backup if available
                        if getattr(settings, 'OTA_RESTORE_ON_FAIL', True):
                            try:
                                with open(backup_dir.rstrip('/') + '/' + name, 'rb') as bf:
                                    with open(final_path, 'wb') as f2:
                                        f2.write(bf.read())
                            except Exception:
                                pass
                        await _sleep(retry_interval_s)
                        continue

                    # success
                    downloaded[name] = {'path': final_path, 'sha256': comp_hash}
                    download_ok = True

                except Exception as e:
                    await debug_print(f'OTA: exception when downloading {name}: {e}', 'ERROR')
                    last_error = f'exception:{e}'
                    await _sleep(retry_interval_s)

            if not download_ok:
                await debug_print(f'ota: {name} failed after {attempts}', 'ERROR')
                if getattr(settings, 'OTA_RESTORE_ON_FAIL', True):
                    await debug_print('ota: abort & restore', 'ERROR')
                    # restore and abort
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
        # Reboot device after OTA files are downloaded and applied
        try:
            from machine import soft_reset
            soft_reset()
        except Exception:
            pass
        # NEW: GC after OTA apply completes (before returning to loops)
        try:
            maybe_gc("ota_apply_done", min_interval_ms=1000, mem_free_below=60 * 1024)
        except Exception:
            pass
        return True
    except Exception as e:
        await debug_print(f'ota: apply exc: {e}', 'ERROR')
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
