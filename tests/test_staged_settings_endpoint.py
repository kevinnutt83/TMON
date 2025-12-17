import os
import sys
import json
import requests

# ... small test script to verify staged-settings endpoint responds correctly ...
WP_URL = os.environ.get('WP_URL', 'http://localhost')
UNIT_ID = os.environ.get('TEST_UNIT_ID', 'test-unit-001')
URL = WP_URL.rstrip('/') + f'/wp-json/tmon/v1/device/staged-settings?unit_id={UNIT_ID}'

def main():
    try:
        r = requests.get(URL, timeout=10)
    except Exception as e:
        print(f"ERROR: Request failed: {e}")
        sys.exit(2)
    if r.status_code != 200:
        print(f"ERROR: Unexpected HTTP status: {r.status_code} (url={URL})")
        print("Response body:", r.text[:200])
        sys.exit(3)
    try:
        payload = r.json()
    except Exception as e:
        print(f"ERROR: Failed to parse JSON: {e}")
        print("Body:", r.text[:500])
        sys.exit(4)
    if payload.get('status') != 'ok':
        print("ERROR: Endpoint did not return status=ok:", json.dumps(payload, indent=2)[:400])
        sys.exit(5)
    # Basic checks
    print("SUCCESS: staged-settings OK for unit", UNIT_ID)
    print("Applied keys:", list(payload.get('applied', {}).keys())[:10])
    print("Staged keys:", list(payload.get('staged', {}).keys())[:10])
    print("Commands count:", len(payload.get('commands', [])))
    sys.exit(0)

if __name__ == '__main__':
    main()
