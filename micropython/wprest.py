# Firmware Version: v2.05.0
# wprest.py
# Handles all WordPress REST API communication for TMON MicroPython device
import settings
import sdata
import ujson
try:
    import urequests as requests
except ImportError:
    import requests
import os
import uasyncio as asyncio
from utils import debug_print, get_machine_id, persist_unit_id
import usocket
import gc

# Minimal async HTTP client for MicroPython
async def async_http_request(url, method='GET', headers=None, data=None):
    gc.collect()
    try:
        # Basic URL parse: support scheme://host[:port]/path
        if '://' not in url:
            await debug_print(f"Malformed URL: {url}", "ERROR")
            return None
        scheme, host_path = url.split('://', 1)
        if '/' in host_path:
            host_port, path = host_path.split('/', 1)
            path = '/' + path
        else:
            host_port = host_path
            path = '/'
        if ':' in host_port:
            host, port_s = host_port.rsplit(':', 1)
            try:
                port = int(port_s)
            except Exception:
                port = 443 if scheme == 'https' else 80
        else:
            host = host_port
            port = 443 if scheme == 'https' else 80
        addr = usocket.getaddrinfo(host, port)[0][-1]
        reader, writer = await asyncio.open_connection(addr[0], port)
        query = f"{method} {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n"
        if headers:
            for k, v in headers.items():
                query += f"{k}: {v}\r\n"
        if data:
            query += f"Content-Length: {len(data)}\r\n"
        query += "\r\n"
        writer.write(query.encode())
        if data:
            if isinstance(data, str):
                writer.write(data.encode('utf-8'))
            else:
                writer.write(data)
        await writer.drain()
        # Read until EOF (Connection: close)
        chunks = []
        while True:
            part = await reader.read(4096)
            if not part:
                break
            chunks.append(part)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        resp_bytes = b''.join(chunks)
        try:
            resp_text = resp_bytes.decode('utf-8', 'ignore')
        except Exception:
            resp_text = str(resp_bytes)
        return resp_text
    except Exception as e:
        await debug_print(f"Async HTTP error: {e}", "ERROR")
        return None

WORDPRESS_API_URL = settings.WORDPRESS_API_URL
WORDPRESS_USERNAME = getattr(settings, 'WORDPRESS_USERNAME', None)
WORDPRESS_PASSWORD = getattr(settings, 'WORDPRESS_PASSWORD', None)
# Legacy stub: JWT removed; return empty string to avoid errors
def get_jwt_token():
    return ''

def _build_auth_headers():
    """Return dict with Authorization: Basic <b64(user:pass)> if credentials exist."""
    headers = {}
    try:
        user = getattr(settings, 'WORDPRESS_USERNAME', '') or getattr(settings, 'FIELD_DATA_APP_USER', '')
        pwd = getattr(settings, 'WORDPRESS_PASSWORD', '') or getattr(settings, 'FIELD_DATA_APP_PASS', '')
        if user and pwd:
            try:
                import ubinascii as _ub
                creds = f"{user}:{pwd}".encode('utf-8')
                b64 = _ub.b2a_base64(creds).decode().strip()
            except Exception:
                import base64 as _b
                b64 = _b.b64encode(f"{user}:{pwd}".encode('utf-8')).decode()
            headers['Authorization'] = 'Basic ' + b64
    except Exception:
        pass
    return headers

async def register_with_wp():
    if not WORDPRESS_API_URL:
        await debug_print('wp: no url', 'ERROR')
        return
    # Build settings snapshot (persistent settings only)
    settings_snapshot = {}
    try:
        import settings as _s
        for k in dir(_s):
            if k.startswith('__') or callable(getattr(_s, k)) or k in ('LOG_DIR',):
                continue
            settings_snapshot[k] = getattr(_s, k)
    except Exception:
        settings_snapshot = {}
    data = {
        'unit_id': settings.UNIT_ID,
        'unit_name': settings.UNIT_Name,
        'company': getattr(settings, 'COMPANY', ''),
        'site': getattr(settings, 'SITE', ''),
        'zone': getattr(settings, 'ZONE', ''),
        'cluster': getattr(settings, 'CLUSTER', ''),
        'machine_id': get_machine_id() or '',
        'firmware_version': getattr(settings, 'FIRMWARE_VERSION', ''),
        'node_type': getattr(settings, 'NODE_TYPE', ''),
        'settings_snapshot': settings_snapshot  # NEW: send persistent settings on check-in
    }
    try:
        headers = {'Content-Type': 'application/json'}
        # include basic auth if configured
        headers.update(_build_auth_headers())
        payload = ujson.dumps(data)
        response = await async_http_request(
            WORDPRESS_API_URL + '/wp-json/tmon/v1/device/register',
            method='POST', headers=headers, data=payload
        )
        if response:
            try:
                import ujson as _j
                resp_obj = _j.loads(response)
            except Exception:
                resp_obj = None
            if isinstance(resp_obj, dict):
                new_uid = resp_obj.get('unit_id')
                if new_uid and str(new_uid) != str(settings.UNIT_ID):
                    settings.UNIT_ID = str(new_uid)
                    try:
                        persist_unit_id(settings.UNIT_ID)
                    except Exception:
                        pass
                    await debug_print(f'wp: unit {settings.UNIT_ID} updated', 'HTTP')
        # NEW: Always attempt to flush any queued command confirmations on check-in (best-effort)
        try:
            await _flush_pending_command_confirms()
        except Exception:
            pass
    except Exception as e:
        await debug_print(f'wp: register fail: {e}', 'ERROR')

async def send_data_to_wp():
    if not WORDPRESS_API_URL:
        return
    # Build sdata full snapshot (keep separate from persistent settings)
    try:
        import sdata as _sd
        sdata_snapshot = {}
        for k in dir(_sd):
            if k.startswith('__') or callable(getattr(_sd, k)):
                continue
            sdata_snapshot[k] = getattr(_sd, k)
    except Exception:
        sdata_snapshot = {}

    data = { 'unit_id': settings.UNIT_ID, 'firmware_version': getattr(settings,'FIRMWARE_VERSION',''), 'node_type': getattr(settings,'NODE_TYPE',''), 'sdata': sdata_snapshot, 'data': {} }
    headers = {'Content-Type':'application/json'}
    headers.update(_build_auth_headers())
    try:
        resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/field-data', headers=headers, json=data)
        await debug_print(f'wp:data status {getattr(resp,"status_code",None)}', 'HTTP')
    except Exception as e:
        await debug_print(f'wp:data fail: {e}', 'ERROR')

async def send_settings_to_wp():
    if not WORDPRESS_API_URL:
        await debug_print('wp: no url', 'ERROR')
        return
    data = {
        'unit_id': settings.UNIT_ID,
        'unit_name': settings.UNIT_Name,
        'company': getattr(settings, 'COMPANY', ''),
        'site': getattr(settings, 'SITE', ''),
        'zone': getattr(settings, 'ZONE', ''),
        'cluster': getattr(settings, 'CLUSTER', ''),
        'machine_id': get_machine_id() or '',
        'firmware_version': getattr(settings, 'FIRMWARE_VERSION', ''),
        'node_type': getattr(settings, 'NODE_TYPE', ''),
    }
    headers = {'Content-Type':'application/json'}
    headers.update(_build_auth_headers())
    try:
        resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/settings', headers=headers, json=data)
        await debug_print(f'wp:settings status {getattr(resp,"status_code",None)}', 'HTTP')
    except Exception as e:
        await debug_print(f'wp:settings fail: {e}', 'ERROR')

async def fetch_settings_from_wp():
    if not WORDPRESS_API_URL:
        await debug_print('wp: no url', 'ERROR')
        return
    try:
        headers = _build_auth_headers()
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/settings/{settings.UNIT_ID}', headers=headers)
        if resp.status_code == 200:
            new_settings = resp.json().get('settings', {})
            for k in ['COMPANY', 'SITE', 'ZONE', 'CLUSTER']:
                if k in new_settings:
                    setattr(settings, k, new_settings[k])
            for k, v in new_settings.items():
                if hasattr(settings, k):
                    setattr(settings, k, v)
            await debug_print('wp: settings updated', 'HTTP')
        else:
            await debug_print(f'wp: fetch settings {resp.status_code}', 'ERROR')
    except Exception as e:
        await debug_print(f'wp: fetch fail: {e}', 'ERROR')

async def send_file_to_wp(filepath):
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    try:
        with open(filepath, 'rb') as f:
            files = {'file': (os.path.basename(filepath), f.read())}
            headers = _build_auth_headers()
            resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/file', headers=headers, files=files)
            await debug_print(f'Sent file to WP: {getattr(resp,"status_code",None)}', 'HTTP')
    except Exception as e:
        await debug_print(f'Failed to send file to WP: {e}', 'ERROR')

async def request_file_from_wp(filename):
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    try:
        headers = _build_auth_headers()
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/file/{settings.UNIT_ID}/{filename}', headers=headers)
        if resp.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(resp.content)
            await debug_print(f'Received file from WP: {filename}', 'HTTP')
        else:
            await debug_print(f'Failed to fetch file: {resp.status_code}', 'ERROR')
    except Exception as e:
        await debug_print(f'Failed to fetch file from WP: {e}', 'ERROR')

async def heartbeat_ping():
    if not WORDPRESS_API_URL:
        return
    try:
        requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/ping', json={'unit_id': settings.UNIT_ID})
    except Exception:
        pass

async def poll_ota_jobs():
    if not WORDPRESS_API_URL:
        return
    try:
        headers = _build_auth_headers()
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/ota-jobs/{settings.UNIT_ID}', headers=headers)
        if resp.status_code == 200:
            jobs = resp.json().get('jobs', [])
            for job in jobs:
                await handle_ota_job(job)
    except Exception as e:
        await debug_print(f'Failed to poll OTA jobs: {e}', 'ERROR')

async def poll_device_commands():
    """Poll Unit Connector for device commands and apply."""
    if not WORDPRESS_API_URL:
        return
    try:
        import urequests as requests
    except Exception:
        return
    # Remotes don't poll UC directly
    if str(getattr(settings, 'NODE_TYPE', 'base')).lower() == 'remote':
        return
    url = WORDPRESS_API_URL.rstrip('/') + '/wp-json/tmon/v1/device/commands'
    payload = {
        'unit_id': settings.UNIT_ID,
        'machine_id': getattr(settings, 'MACHINE_ID', '')
    }
    try:
        headers = _build_auth_headers()
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
    except TypeError:
        resp = requests.post(url, json=payload, headers=headers)
    ok = (resp is not None and getattr(resp, 'status_code', 0) == 200)
    if not ok:
        try:
            resp.close()
        except Exception:
            pass
        return
    cmds = []
    try:
        body = resp.json() or {}
    except Exception:
        body = {}
    # Accept both shapes: top-level list or {commands: [...]}
    if isinstance(body, list):
        cmds = body
    elif isinstance(body, dict) and 'commands' in body and isinstance(body['commands'], list):
        cmds = body['commands']
    elif isinstance(body, dict) and isinstance(body.get('data'), list):
        cmds = body.get('data', [])
    else:
        cmds = []
    try:
        resp.close()
    except Exception:
        pass

    # Normalize and process each command via the unified handler (handle_device_command)
    for c in cmds:
        try:
            # Support both formats:
            # - new: { id, command, params }
            # - legacy: { id, type, payload }
            job_id = c.get('id') or c.get('command_id') or c.get('job_id') or None
            cmd_name = c.get('command') or c.get('type') or c.get('name') or None
            params = c.get('params') or c.get('payload') or c.get('payload', {}) or {}
            # If params is JSON string, try decode
            if isinstance(params, str):
                try:
                    import ujson as _j
                    params = _j.loads(params)
                except Exception:
                    params = params
            job = {'id': job_id, 'command': cmd_name, 'params': params}
            # Reuse existing handler which will POST completion
            await handle_device_command(job)
        except Exception as e:
            await debug_print(f'command apply error (poll): {e}', 'ERROR')
    await asyncio.sleep(0)

async def handle_ota_job(job):
    job_type = job.get('job_type')
    payload = job.get('payload')
    job_id = job.get('id')
    if job_type == 'settings_update' and payload:
        for k, v in payload.items():
            if hasattr(settings, k):
                setattr(settings, k, v)
        await debug_print('Settings updated from OTA job', 'OTA')
    elif job_type == 'file_update' and payload:
        filename = payload.get('filename')
        if filename:
            await request_file_from_wp(filename)
    try:
        requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/ota-job-complete', json={'job_id': job_id})
    except Exception:
        pass

async def handle_device_command(job):
    try:
        cmd = job.get('command')
        params = job.get('params') or {}
        job_id = job.get('id')
        ok = True
        result = None
        if cmd == 'toggle_relay':
            from relay import toggle_relay
            relay_num = str(params.get('relay_num', '1'))
            state = str(params.get('state', 'on'))
            runtime = str(params.get('runtime', '0'))
            await toggle_relay(relay_num, state, runtime)
            result = f"relay {relay_num} {state} runtime {runtime}"
        elif cmd == 'settings_update':
            # Apply a subset of settings dynamically
            try:
                for k, v in params.items():
                    if hasattr(settings, k):
                        setattr(settings, k, v)
                result = 'settings updated'
            except Exception as e:
                ok = False
                result = f'settings error: {e}'
        elif cmd == 'set_oled_message':
            try:
                msg = str(params.get('message', ''))
                duration = int(params.get('duration', 5))
                if not msg:
                    ok = False
                    result = 'missing message'
                else:
                    from oled import display_message
                    await display_message(msg, duration)
                    result = f'message shown ({duration}s)'
            except Exception as e:
                ok = False
                result = f'oled error: {e}'
        elif cmd == 'set_oled_banner':
            try:
                from oled import set_status_banner
                msg = str(params.get('message', ''))
                duration = int(params.get('duration', 5))
                persist = bool(params.get('persist', False))
                if not msg:
                    ok = False
                    result = 'missing message'
                else:
                    if set_status_banner(msg, duration, persist):
                        result = f'banner set ({duration}s)'
                    else:
                        ok = False
                        result = 'banner set failed'
            except Exception as e:
                ok = False
                result = f'oled error: {e}'
        elif cmd == 'clear_oled':
            try:
                from oled import clear_status_banner, clear_message_area
                clear_status_banner()
                clear_message_area()
                result = 'oled cleared'
            except Exception as e:
                ok = False
                result = f'oled error: {e}'
        else:
            ok = False
            result = f"unknown command: {cmd}"
        # confirm completion with fallback to /device/ack for older servers
        try:
            resp = requests.post(
                WORDPRESS_API_URL + '/wp-json/tmon/v1/device/command-complete',
                json={'job_id': job_id, 'ok': ok, 'result': result}
            )
            # Fallback if route isn't present or returns error
            if getattr(resp, 'status_code', 500) == 404 or getattr(resp, 'status_code', 500) >= 400:
                try:
                    # try legacy ack
                    resp2 = requests.post(
                        WORDPRESS_API_URL + '/wp-json/tmon/v1/device/ack',
                        json={'command_id': job_id, 'ok': ok, 'result': result}
                    )
                    code2 = getattr(resp2, 'status_code', None)
                    try:
                        if resp2: resp2.close()
                    except Exception:
                        pass
                    if code2 not in (200, 201):
                        _queue_command_confirm({'job_id': job_id, 'ok': ok, 'result': result, 'ts': int(__import__('time').time())})
                    else:
                        _remove_pending_confirm(job_id)
                except Exception:
                    _queue_command_confirm({'job_id': job_id, 'ok': ok, 'result': result, 'ts': int(__import__('time').time())})
            else:
                # success -> ensure any queued confirmations are removed
                _remove_pending_confirm(job_id)
            try:
                if resp: resp.close()
            except Exception:
                pass
        except Exception:
            # If posting immediately fails, persist for later flush during checkin
            _queue_command_confirm({'job_id': job_id, 'ok': ok, 'result': result, 'ts': int(__import__('time').time())})
    except Exception as e:
        await debug_print(f'Command error: {e}', 'ERROR')

async def fetch_staged_settings():
    """Fetch staged/applied settings and pending commands for this unit; save staged settings to disk."""
    if not WORDPRESS_API_URL:
        await debug_print('wp: no url (staged)', 'ERROR')
        return False
    try:
        url = WORDPRESS_API_URL.rstrip('/') + f'/wp-json/tmon/v1/device/staged-settings?unit_id={settings.UNIT_ID}'
        headers = _build_auth_headers()
        resp = requests.get(url, timeout=10, headers=headers)
        if getattr(resp, 'status_code', 0) != 200:
            await debug_print(f'fetch_staged_settings: non-200 {getattr(resp,"status_code",None)}', 'DEBUG')
            return False
        data = resp.json() or {}
        # Save staged settings to per-device file if present
        staged = data.get('staged') or data.get('settings') or {}
        if isinstance(staged, dict) and staged:
            fname = getattr(settings, 'LOG_DIR', '/logs') + '/device_settings-' + str(settings.UNIT_ID) + '.json'
            try:
                with open(fname, 'w') as f:
                    ujson.dump(staged, f)
                await debug_print(f'wp: staged saved {fname}', 'HTTP')
            except Exception as e:
                await debug_print(f'wp: staged save fail: {e}', 'ERROR')
            # Also write to global staged file path so settings_apply can find it
            try:
                gpath = getattr(settings, 'REMOTE_SETTINGS_STAGED_FILE', settings.LOG_DIR + '/remote_settings.staged.json')
                with open(gpath, 'w') as gf:
                    ujson.dump(staged, gf)
            except Exception:
                pass
            # Optionally apply staged settings immediately (best-effort)
            try:
                if getattr(settings, 'APPLY_STAGED_SETTINGS_ON_SYNC', True):
                    try:
                        import settings_apply as _sa
                        await _sa.apply_staged_settings_once()
                    except Exception:
                        pass
            except Exception:
                pass

        # If there are commands, process them (base & wifi nodes handle direct commands here)
        cmds = data.get('commands', []) or []
        if cmds:
            await debug_print(f'wp: staged cmds {len(cmds)}', 'HTTP')
            # Process commands inline for base & wifi nodes (remote nodes get commands via LoRa)
            node_role = str(getattr(settings, 'NODE_TYPE', 'base')).lower()
            if node_role in ('base', 'wifi'):
                for c in cmds:
                    try:
                        # Normalize shape to what handle_device_command expects (id, command, params)
                        job = {
                            'id': c.get('id') or c.get('command_id') or c.get('job_id'),
                            'command': c.get('command') or c.get('type') or c.get('type_name'),
                            'params': c.get('params') or c.get('payload') or c.get('payload', {}),
                        }
                        # reuse existing command handler
                        await handle_device_command(job)
                    except Exception as e:
                        await debug_print(f'Error processing staged command: {e}', 'ERROR')
        return {'staged': staged, 'commands': cmds}
    except Exception as e:
        await debug_print(f'fetch_staged_settings exception: {e}', 'ERROR')
        return False

# --- Pending command confirmations queue helpers ---
# NEW: persist confirmations locally when immediate confirm POST fails,
# and flush them on next checkin so the UC marks the command processed.
try:
	import ujson as _j
except Exception:
	import json as _j

def _pending_confirms_path():
	try:
		import settings as _s
		return getattr(_s, 'LOG_DIR', '/logs').rstrip('/') + '/pending_cmd_confirms.json'
	except Exception:
		return '/logs/pending_cmd_confirms.json'

def _load_pending_confirms():
	try:
		p = _pending_confirms_path()
		with open(p, 'r') as f:
			return _j.loads(f.read()) or []
	except Exception:
		return []

def _save_pending_confirms(arr):
	try:
		p = _pending_confirms_path()
		with open(p, 'w') as f:
			f.write(_j.dumps(arr))
		return True
	except Exception:
		return False

def _queue_command_confirm(entry):
	try:
		arr = _load_pending_confirms()
		# dedupe by job_id if present
		if entry.get('job_id'):
			arr = [e for e in arr if e.get('job_id') != entry.get('job_id')]
		arr.append(entry)
		_save_pending_confirms(arr)
	except Exception:
		pass

def _remove_pending_confirm(job_id):
	try:
		if not job_id:
			return
		arr = _load_pending_confirms()
		arr = [e for e in arr if e.get('job_id') != job_id]
		_save_pending_confirms(arr)
	except Exception:
		pass

async def _flush_pending_command_confirms():
	"""Attempt to deliver queued confirmations to the configured WORDPRESS_API_URL.
	   Called from register_with_wp() (check-in) so confirmations are sent reliably on next checkin.
	"""
	try:
		if not getattr(globals(), 'WORDPRESS_API_URL', ''):
			return False
		arr = _load_pending_confirms()
		if not arr:
			return True
		remaining = []
		for e in arr:
			try:
				# Build payload shape compatible with command-complete and legacy ack
				payload = { 'job_id': e.get('job_id') or e.get('command_id'), 'ok': e.get('ok', False), 'result': e.get('result', '') }
				try:
					resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/command-complete', json=payload, timeout=10)
				except TypeError:
					resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/command-complete', json=payload)
				code = getattr(resp, 'status_code', None) if resp is not None else None
				ok = code in (200, 201)
				try:
					if resp:
						resp.close()
				except Exception:
					pass
				if not ok:
					# Try legacy ack endpoint
					try:
						payload_legacy = { 'command_id': payload.get('job_id'), 'ok': payload.get('ok'), 'result': payload.get('result') }
						try:
							resp2 = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/ack', json=payload_legacy, timeout=10)
						except TypeError:
							resp2 = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/ack', json=payload_legacy)
						code2 = getattr(resp2, 'status_code', None) if resp2 is not None else None
						try:
							if resp2:
								resp2.close()
						except Exception:
							pass
						ok = code2 in (200, 201)
					except Exception:
						ok = False
				if not ok:
					# keep for retry later
					e['last_try'] = int(__import__('time').time())
					remaining.append(e)
				else:
					# remove any duplicates on success (handled implicitly by not adding to remaining)
					_remove_pending_confirm(payload.get('job_id'))
			except Exception:
				# keep this entry for later attempts
				e['last_try'] = int(__import__('time').time())
				remaining.append(e)
		_save_pending_confirms(remaining)
		return True
	except Exception:
		return False

async def register_with_wp():
    if not WORDPRESS_API_URL:
        await debug_print('wp: no url', 'ERROR')
        return
    # Build settings snapshot (persistent settings only)
    settings_snapshot = {}
    try:
        import settings as _s
        for k in dir(_s):
            if k.startswith('__') or callable(getattr(_s, k)) or k in ('LOG_DIR',):
                continue
            settings_snapshot[k] = getattr(_s, k)
    except Exception:
        settings_snapshot = {}
    data = {
        'unit_id': settings.UNIT_ID,
        'unit_name': settings.UNIT_Name,
        'company': getattr(settings, 'COMPANY', ''),
        'site': getattr(settings, 'SITE', ''),
        'zone': getattr(settings, 'ZONE', ''),
        'cluster': getattr(settings, 'CLUSTER', ''),
        'machine_id': get_machine_id() or '',
        'firmware_version': getattr(settings, 'FIRMWARE_VERSION', ''),
        'node_type': getattr(settings, 'NODE_TYPE', ''),
        'settings_snapshot': settings_snapshot  # NEW: send persistent settings on check-in
    }
    try:
        headers = {'Content-Type': 'application/json'}
        # include basic auth if configured
        headers.update(_build_auth_headers())
        payload = ujson.dumps(data)
        response = await async_http_request(
            WORDPRESS_API_URL + '/wp-json/tmon/v1/device/register',
            method='POST', headers=headers, data=payload
        )
        if response:
            try:
                import ujson as _j
                resp_obj = _j.loads(response)
            except Exception:
                resp_obj = None
            if isinstance(resp_obj, dict):
                new_uid = resp_obj.get('unit_id')
                if new_uid and str(new_uid) != str(settings.UNIT_ID):
                    settings.UNIT_ID = str(new_uid)
                    try:
                        persist_unit_id(settings.UNIT_ID)
                    except Exception:
                        pass
                    await debug_print(f'wp: unit {settings.UNIT_ID} updated', 'HTTP')
        # NEW: Always attempt to flush any queued command confirmations on check-in (best-effort)
        try:
            await _flush_pending_command_confirms()
        except Exception:
            pass
    except Exception as e:
        await debug_print(f'wp: register fail: {e}', 'ERROR')
