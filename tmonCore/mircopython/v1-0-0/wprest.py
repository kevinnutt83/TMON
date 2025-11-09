# Firmware Version: 2.0.0h
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
        scheme, host_path = url.split('://', 1)
        host, path = host_path.split('/', 1)
        path = '/' + path
        port = 443 if scheme == 'https' else 80
        addr = usocket.getaddrinfo(host, port)[0][-1]
        reader, writer = await asyncio.open_connection(addr[0], port)
        query = f"{method} {path} HTTP/1.0\r\nHost: {host}\r\n"
        if headers:
            for k, v in headers.items():
                query += f"{k}: {v}\r\n"
        if data:
            query += f"Content-Length: {len(data)}\r\n"
        query += "\r\n"
        writer.write(query.encode())
        if data:
            writer.write(data)
        await writer.drain()
        response = await reader.read(4096)  # Adjust buffer as needed
        writer.close()
        await writer.wait_closed()
        return response.decode()
    except Exception as e:
        await debug_print(f"Async HTTP error: {e}", "ERROR")
        return None

WORDPRESS_API_URL = settings.WORDPRESS_API_URL
WORDPRESS_USERNAME = getattr(settings, 'WORDPRESS_USERNAME', None)
WORDPRESS_PASSWORD = getattr(settings, 'WORDPRESS_PASSWORD', None)
_jwt_token = None

def get_jwt_token():
    global _jwt_token
    if _jwt_token:
        return _jwt_token
    if not WORDPRESS_USERNAME or not WORDPRESS_PASSWORD:
        raise Exception('WordPress username/password not set in settings.py')
    url = WORDPRESS_API_URL + '/wp-json/jwt-auth/v1/token'
    payload = ujson.dumps({"username": WORDPRESS_USERNAME, "password": WORDPRESS_PASSWORD})
    headers = {'Content-Type': 'application/json'}
    try:
        resp = requests.post(url, headers=headers, data=payload)
        if resp.status_code == 200:
            data = resp.json()
            _jwt_token = data.get('token')
            return _jwt_token
        else:
            raise Exception('Failed to obtain JWT token: %s' % resp.text)
    except Exception as e:
        raise Exception('JWT token error: %s' % e)

async def register_with_wp():
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    data = {
        'unit_id': settings.UNIT_ID,
        'unit_name': settings.UNIT_Name,
        'company': getattr(settings, 'COMPANY', ''),
        'site': getattr(settings, 'SITE', ''),
        'zone': getattr(settings, 'ZONE', ''),
        'cluster': getattr(settings, 'CLUSTER', ''),
        'machine_id': get_machine_id() or '',
    }
    try:
        token = get_jwt_token()
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        payload = ujson.dumps(data)
        response = await async_http_request(
            WORDPRESS_API_URL + '/wp-json/tmon/v1/device/register',
            method='POST', headers=headers, data=payload
        )
        if response:
            # Try to parse JSON cleanly
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
                    await debug_print(f'UNIT_ID updated from WP: {settings.UNIT_ID}', 'HTTP')
    except Exception as e:
        await debug_print(f'Failed to register with WP: {e}', 'ERROR')

async def send_data_to_wp():
    if not WORDPRESS_API_URL:
        return
    data = {
        'unit_id': settings.UNIT_ID,
        'data': {
            'runtime': getattr(sdata, 'loop_runtime', 0),
            'script_runtime': getattr(sdata, 'script_runtime', 0),
            'temp_c': getattr(sdata, 'cur_temp_c', 0),
            'temp_f': getattr(sdata, 'cur_temp_f', 0),
            'bar': getattr(sdata, 'cur_bar_pres', 0),
            'humid': getattr(sdata, 'cur_humid', 0),
            # optional GPS fields
            'gps_lat': getattr(sdata, 'gps_lat', None),
            'gps_lng': getattr(sdata, 'gps_lng', None),
            'gps_alt_m': getattr(sdata, 'gps_alt_m', None),
            'gps_accuracy_m': getattr(sdata, 'gps_accuracy_m', None),
            'gps_last_fix_ts': getattr(sdata, 'gps_last_fix_ts', None),
        }
    }
    try:
        token = get_jwt_token()
        headers = {'Authorization': f'Bearer {token}'}
        resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/data', headers=headers, json=data)
        await debug_print(f'Sent data to WP: {resp.status_code}', 'HTTP')
    except Exception as e:
        await debug_print(f'Failed to send data to WP: {e}', 'ERROR')

async def send_settings_to_wp():
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    data = {
        'unit_id': settings.UNIT_ID,
        'unit_name': settings.UNIT_Name,
        'company': getattr(settings, 'COMPANY', ''),
        'site': getattr(settings, 'SITE', ''),
        'zone': getattr(settings, 'ZONE', ''),
        'cluster': getattr(settings, 'CLUSTER', ''),
        'settings': {k: getattr(settings, k) for k in dir(settings) if not k.startswith('__') and not callable(getattr(settings, k))}
    }
    try:
        token = get_jwt_token()
        headers = {'Authorization': f'Bearer {token}'}
        resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/settings', headers=headers, json=data)
        await debug_print(f'Sent settings to WP: {resp.status_code}', 'HTTP')
    except Exception as e:
        await debug_print(f'Failed to send settings to WP: {e}', 'ERROR')

async def fetch_settings_from_wp():
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    try:
        token = get_jwt_token()
        headers = {'Authorization': f'Bearer {token}'}
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/settings/{settings.UNIT_ID}', headers=headers)
        if resp.status_code == 200:
            new_settings = resp.json().get('settings', {})
            for k in ['COMPANY', 'SITE', 'ZONE', 'CLUSTER']:
                if k in new_settings:
                    setattr(settings, k, new_settings[k])
            for k, v in new_settings.items():
                if hasattr(settings, k):
                    setattr(settings, k, v)
            await debug_print('Settings updated from WP', 'HTTP')
        else:
            await debug_print(f'Failed to fetch settings: {resp.status_code}', 'ERROR')
    except Exception as e:
        await debug_print(f'Failed to fetch settings from WP: {e}', 'ERROR')

async def fetch_admin_thresholds_via_uc():
    """Fetch frost/heat thresholds from Admin hub via Unit Connector proxy endpoint.
    Requires UC device key set in settings.UC_DEVICE_POST_KEY and ADMIN_SHARED_KEY on UC.
    Populates CLEAR/LORA_INTERVAL variables when present.
    """
    try:
        uc_url = getattr(settings, 'WORDPRESS_API_URL', '')
        device_key = getattr(settings, 'UC_DEVICE_POST_KEY', '')
        if not uc_url or not device_key:
            return
        endpoint = uc_url.rstrip('/') + '/wp-json/tmon/v1/admin/thresholds'
        headers = {'X-TMON-DEVICE': device_key}
        resp = requests.get(endpoint, headers=headers, timeout=10)
        if resp.status_code != 200:
            await debug_print(f'Admin thresholds fetch failed: {resp.status_code}', 'WARN')
            return
        try:
            payload = resp.json()
        except Exception:
            payload = None
        if not isinstance(payload, dict):
            return
        frost = payload.get('frost', {})
        heat = payload.get('heat', {})
        # Map into settings if keys present
        try:
            if 'active_temp_f' in frost:
                settings.FROSTWATCH_ACTIVE_TEMP = int(frost.get('active_temp_f'))
            if 'clear_temp_f' in frost:
                settings.FROSTWATCH_CLEAR_TEMP = int(frost.get('clear_temp_f'))
            if 'lora_interval_s' in frost:
                settings.FROSTWATCH_LORA_INTERVAL = int(frost.get('lora_interval_s'))
            if 'active_temp_f' in heat:
                settings.HEATWATCH_ACTIVE_TEMP = int(heat.get('active_temp_f'))
            if 'clear_temp_f' in heat:
                settings.HEATWATCH_CLEAR_TEMP = int(heat.get('clear_temp_f'))
            if 'lora_interval_s' in heat:
                settings.HEATWATCH_LORA_INTERVAL = int(heat.get('lora_interval_s'))
            await debug_print('Admin thresholds applied', 'HTTP')
        except Exception:
            pass
    except Exception as e:
        await debug_print(f'Failed to fetch admin thresholds via UC: {e}', 'WARN')

async def send_file_to_wp(filepath):
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    try:
        token = get_jwt_token()
        headers = {'Authorization': f'Bearer {token}'}
        with open(filepath, 'rb') as f:
            files = {'file': (os.path.basename(filepath), f.read())}
            resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/file', headers=headers, files=files)
            await debug_print(f'Sent file to WP: {resp.status_code}', 'HTTP')
    except Exception as e:
        await debug_print(f'Failed to send file to WP: {e}', 'ERROR')

async def request_file_from_wp(filename):
    if not WORDPRESS_API_URL:
        await debug_print('No WordPress API URL set', 'ERROR')
        return
    try:
        token = get_jwt_token()
        headers = {'Authorization': f'Bearer {token}'}
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
        token = get_jwt_token()
        headers = {'Authorization': f'Bearer {token}'}
        requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/ping', headers=headers, json={'unit_id': settings.UNIT_ID})
    except Exception:
        pass

async def poll_ota_jobs():
    if not WORDPRESS_API_URL:
        return
    try:
        token = get_jwt_token()
        headers = {'Authorization': f'Bearer {token}'}
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/ota-jobs/{settings.UNIT_ID}', headers=headers)
        if resp.status_code == 200:
            jobs = resp.json().get('jobs', [])
            for job in jobs:
                await handle_ota_job(job)
    except Exception as e:
        await debug_print(f'Failed to poll OTA jobs: {e}', 'ERROR')

async def poll_device_commands():
    if not WORDPRESS_API_URL:
        return
    try:
        token = get_jwt_token()
        headers = {'Authorization': f'Bearer {token}'}
        resp = requests.get(WORDPRESS_API_URL + f'/wp-json/tmon/v1/device/commands/{settings.UNIT_ID}', headers=headers)
        if resp.status_code == 200:
            payload = resp.json()
            jobs = payload.get('jobs', []) if isinstance(payload, dict) else []
            for job in jobs:
                await handle_device_command(job)
    except Exception as e:
        await debug_print(f'Failed to poll commands: {e}', 'ERROR')

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
        token = get_jwt_token()
        headers = {'Authorization': f'Bearer {token}'}
        requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/ota-job-complete', headers=headers, json={'job_id': job_id})
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
        # confirm completion
        try:
            token = get_jwt_token()
            headers = {'Authorization': f'Bearer {token}'}
            requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/command-complete', headers=headers, json={'job_id': job_id, 'ok': ok, 'result': result})
        except Exception:
            pass
    except Exception as e:
        await debug_print(f'Command error: {e}', 'ERROR')
