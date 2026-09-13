# TMON device dispatch — settings/commands for base, wifi, and LoRa remotes
import ujson
import uasyncio as asyncio
import ubinascii as _ub

try:
    import settings
    import sdata
except Exception:
    settings = None
    sdata = None

try:
    from utils import debug_print, get_machine_id, persist_custom_settings, write_json_atomic
except Exception:
    async def debug_print(msg, tag='INFO'):
        print('[%s] %s' % (tag, msg))
    def get_machine_id():
        return ''
    def persist_custom_settings(_payload):
        return False
    def write_json_atomic(_path, _obj):
        return False

_pending_settings = {}
_pending_cmds = {}


def _node_role():
    try:
        return str(getattr(settings, 'NODE_TYPE', 'base') or 'base').lower()
    except Exception:
        return 'base'


def _staged_path():
    return getattr(settings, 'REMOTE_SETTINGS_STAGED_FILE', settings.LOG_DIR + '/remote_settings.staged.json')


def _queue_settings(uid, payload):
    if uid and isinstance(payload, dict) and payload:
        _pending_settings[str(uid)] = payload


def _queue_commands(uid, commands):
    if not uid or not isinstance(commands, list):
        return
    bucket = _pending_cmds.setdefault(str(uid), [])
    seen = set()
    for item in bucket:
        if isinstance(item, dict) and item.get('id') is not None:
            seen.add(item.get('id'))
    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        cid = cmd.get('id')
        if cid is not None and cid in seen:
            continue
        bucket.append(cmd)
        if cid is not None:
            seen.add(cid)


def pop_pending_settings(uid):
    return _pending_settings.pop(str(uid), None)


def peek_pending_settings(uid):
    return _pending_settings.get(str(uid))


def pop_pending_command(uid):
    bucket = _pending_cmds.get(str(uid)) or []
    if not bucket:
        return None
    cmd = bucket.pop(0)
    if not bucket:
        _pending_cmds.pop(str(uid), None)
    return cmd


def peek_pending_command(uid):
    bucket = _pending_cmds.get(str(uid)) or []
    return bucket[0] if bucket else None


async def _http_json(method, path, body=None):
    try:
        from wprest import _current_wp_url, _auth_headers, _extract_response
    except Exception:
        return 0, None
    try:
        import urequests as requests
    except Exception:
        try:
            import requests
        except Exception:
            return 0, None
    wp_url = ''
    try:
        wp_url = _current_wp_url()
    except Exception:
        wp_url = str(getattr(settings, 'WORDPRESS_API_URL', '') or '')
    if not wp_url:
        return 0, None
    resp = None
    try:
        url = wp_url.rstrip('/') + path
        headers = _auth_headers()
        if method == 'GET':
            try:
                resp = requests.get(url, headers=headers, timeout=8)
            except TypeError:
                resp = requests.get(url, headers=headers)
        else:
            try:
                resp = requests.post(url, json=body or {}, headers=headers, timeout=8)
            except TypeError:
                resp = requests.post(url, json=body or {}, headers=headers)
        code, _text, parsed = _extract_response(resp, max_chars=2000)
        return code, parsed
    except Exception as e:
        await debug_print('dispatch http %s %s failed: %s' % (method, path, e), 'WARN')
        return 0, None
    finally:
        try:
            if resp:
                resp.close()
        except Exception:
            pass


async def fetch_staged_settings_for(unit_id, persist_local=False):
    unit_id = str(unit_id or '').strip()
    if not unit_id:
        return None
    paths = [
        '/wp-json/tmon/v1/device/staged-settings?unit_id=%s' % unit_id,
        '/wp-json/tmon/v1/device/settings/%s' % unit_id,
        '/wp-json/tmon/v1/device/provision?unit_id=%s' % unit_id,
    ]
    for path in paths:
        code, parsed = await _http_json('GET', path)
        if code not in (200, 201) or not isinstance(parsed, dict):
            continue
        staged = parsed.get('staged') if isinstance(parsed.get('staged'), dict) else None
        if staged is None and isinstance(parsed.get('settings'), dict):
            staged = parsed.get('settings')
        if isinstance(staged, dict) and staged:
            if persist_local:
                try:
                    write_json_atomic(_staged_path(), staged)
                except Exception as e:
                    await debug_print('dispatch write staged failed: %s' % e, 'ERROR')
                    return None
            await debug_print('dispatch staged settings for %s via %s keys=%s' % (
                unit_id, path, ','.join(list(staged.keys())[:8])
            ), 'INFO')
            return staged
        if parsed.get('staged_exists') is False:
            return None
    return None


async def fetch_commands_for(unit_id, claim=False):
    unit_id = str(unit_id or '').strip()
    if not unit_id:
        return []
    body = {
        'unit_id': unit_id,
        'device_id': unit_id,
        'machine_id': str(get_machine_id() or ''),
        'limit': int(getattr(settings, 'COMMANDS_MAX_PER_POLL', 10) or 10),
        'claim': bool(claim),
    }
    paths = [
        '/wp-json/tmon/v1/device/commands',
        '/wp-json/tmon-uc/v1/device/commands',
    ]
    for path in paths:
        code, parsed = await _http_json('POST', path, body)
        if code not in (200, 201) or parsed is None:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get('commands'), list):
            return parsed.get('commands')
        if isinstance(parsed, list):
            return parsed
    return []


async def confirm_remote_settings_applied(unit_id, changed_keys=None):
    body = {
        'unit_id': str(unit_id or ''),
        'device_id': str(unit_id or ''),
        'status': 'applied',
        'changed_keys': list(changed_keys or []),
    }
    code, parsed = await _http_json('POST', '/wp-json/tmon/v1/device/settings-applied', body)
    return code in (200, 201, 202)


async def confirm_remote_command(unit_id, cmd_id, ok=True, result=None):
    if cmd_id is None:
        return False
    body = {
        'id': cmd_id,
        'job_id': cmd_id,
        'unit_id': str(unit_id or ''),
        'ok': bool(ok),
        'status': 'done' if ok else 'failed',
        'result': result if isinstance(result, dict) else {},
    }
    for path in (
        '/wp-json/tmon/v1/device/command-complete',
        '/wp-json/tmon/v1/device/command-result',
        '/wp-json/tmon-uc/v1/device/command-result',
    ):
        code, _parsed = await _http_json('POST', path, body)
        if code in (200, 201, 202):
            return True
    return False


def _remote_uids():
    uids = []
    info = getattr(settings, 'REMOTE_NODE_INFO', {}) or {}
    for uid, st in info.items():
        if not uid:
            continue
        uids.append(str(uid))
    return uids


async def sync_hub_dispatch():
    """Base/WiFi: apply local work. Base also caches remote settings/commands."""
    role = _node_role()
    if role == 'remote':
        return False
    local_uid = str(getattr(settings, 'UNIT_ID', '') or '').strip()
    try:
        from wprest import fetch_settings_from_wp, poll_device_commands
        await fetch_settings_from_wp()
        await poll_device_commands()
    except Exception as e:
        await debug_print('dispatch local sync error: %s' % e, 'WARN')
    if role != 'base' or not local_uid:
        return True
    for uid in _remote_uids():
        if uid == local_uid:
            continue
        try:
            staged = await fetch_staged_settings_for(uid, persist_local=False)
            if staged:
                _queue_settings(uid, staged)
            commands = await fetch_commands_for(uid, claim=False)
            if commands:
                _queue_commands(uid, commands)
                await debug_print('dispatch queued %d cmds for remote %s' % (len(commands), uid), 'BASE_NODE')
        except Exception as e:
            await debug_print('dispatch remote cache %s failed: %s' % (uid, e), 'WARN')
        await asyncio.sleep_ms(20)
    return True


async def send_lora_settings(uid, payload):
    if not isinstance(payload, dict) or not uid:
        return False
    try:
        from lora import _send_chunked
    except Exception as e:
        await debug_print('dispatch lora settings import failed: %s' % e, 'ERROR')
        return False
    try:
        raw = ujson.dumps(payload).encode()
        b64 = _ub.b2a_base64(raw).rstrip(b'\n').decode()
        ok = await _send_chunked('SETTINGS', b64, target_uid=uid, chunk_len=80)
        await debug_print('dispatch SETTINGS to %s ok=%s keys=%s' % (
            uid, ok, ','.join(list(payload.keys())[:8])
        ), 'BASE_NODE')
        return bool(ok)
    except Exception as e:
        await debug_print('dispatch SETTINGS TX failed for %s: %s' % (uid, e), 'ERROR')
        return False


async def after_remote_ready(uid):
    """Call from base HELLO/READY handler. Sends staged settings before field data."""
    uid = str(uid or '').strip()
    if not uid:
        return None
    payload = peek_pending_settings(uid)
    if payload is None:
        payload = await fetch_staged_settings_for(uid, persist_local=False)
        if payload:
            _queue_settings(uid, payload)
    payload = pop_pending_settings(uid)
    if payload:
        ok = await send_lora_settings(uid, payload)
        if ok:
            await confirm_remote_settings_applied(uid, list(payload.keys()))
            return 'settings'
        _queue_settings(uid, payload)
    return None


def next_ack_command(uid):
    """Return one command dict for ACK :CMD: piggyback."""
    return peek_pending_command(uid)


async def mark_ack_command_sent(uid, cmd, delivered=True):
    popped = pop_pending_command(uid)
    if popped is None:
        popped = cmd
    if delivered and isinstance(popped, dict):
        await confirm_remote_command(uid, popped.get('id'), ok=True, result={'delivered': 'lora-ack'})


async def apply_inbound_settings_payload(payload):
    """Remote: persist SETTINGS frame then let settings_apply_loop consume it."""
    if not isinstance(payload, dict) or not payload:
        return False
    try:
        write_json_atomic(_staged_path(), payload)
    except Exception:
        persist_custom_settings(payload)
        return True
    persist_custom_settings(payload)
    await debug_print('dispatch remote staged %d keys' % len(payload), 'REMOTE_NODE')
    return True