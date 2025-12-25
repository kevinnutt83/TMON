# Minimal one-off field data POST test
import ujson
import uasyncio as asyncio
from wprest import WORDPRESS_API_URL, get_jwt_token

async def test_field_data_once():
    try:
        import urequests as requests
    except Exception:
        import requests
    if not WORDPRESS_API_URL:
        print('[TEST] WORDPRESS_API_URL not set')
        return False
    payload = {
        'unit_id': 'TEST_UNIT',
        'name': 'FieldDataTest',
        't_f': 72.5,
        'hum': 45.2,
        'bar': 1012.3,
    }
    try:
        # Use same auth builder as device requests (Application Password / Basic)
        from wprest import _auth_headers
        headers = _auth_headers() if callable(_auth_headers) else {}
        print('[TEST] POST /device/field-data ...')
        resp = requests.post(WORDPRESS_API_URL + '/wp-json/tmon/v1/device/field-data', headers=headers, json=payload, timeout=10)
        try:
            print('[TEST] status:', resp.status_code)
            try:
                print('[TEST] text:', resp.text)
            except Exception:
                pass
            try:
                print('[TEST] json:', resp.json())
            except Exception as e:
                print('[TEST] json parse error:', e)
        finally:
            try:
                resp.close()
            except Exception:
                pass
        return resp.status_code == 200
    except Exception as e:
        print('[TEST] exception:', type(e).__name__, e)
        return False

if __name__ == '__main__':
    asyncio.run(test_field_data_once())
