# OTA scaffolding: version check and pending flag
try:
    import urequests as requests
except Exception:
    requests = None

import settings
from config_persist import write_text
from utils import debug_print

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
