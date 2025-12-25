#!/usr/bin/env python3
"""
Simple WP endpoint validator for Unit Connector / Admin routes.

Usage:
  python scripts/validate_wp_endpoints.py https://example.com --unit 170170 --auth "user:pass" --retries 2 --timeout 8
"""
import sys
import argparse
import requests
import json
import os
import base64
from time import sleep

ENDPOINTS = [
    '/wp-json/tmon/v1/device/field-data',
    '/wp-json/tmon/v1/device/commands',
    '/wp-json/tmon/v1/device/settings',  # may be queried with /{unit}
    '/wp-json/tmon-admin/v1/device/check-in'
]

def build_auth_header(auth):
    if not auth:
        return {}
    auth = auth.strip()
    # If 'Bearer ' prefix present, pass through
    if auth.lower().startswith('bearer '):
        return {'Authorization': auth}
    # If looks like user:pass, encode as Basic
    if ':' in auth and ' ' not in auth:
        b64 = base64.b64encode(auth.encode('utf-8')).decode('ascii')
        return {'Authorization': 'Basic ' + b64}
    # otherwise treat as raw Authorization value
    return {'Authorization': auth}

def check_url(base, path, method='GET', json_body=None, headers=None, timeout=8):
    url = base.rstrip('/') + path
    try:
        if method == 'GET':
            r = requests.get(url, headers=headers, timeout=timeout)
        else:
            r = requests.post(url, json=json_body, headers=headers, timeout=timeout)
        return {'url': url, 'status': r.status_code, 'ok': r.status_code in (200,201)}
    except Exception as e:
        return {'url': url, 'status': None, 'ok': False, 'error': str(e)}

def try_endpoint_with_retries(base, path, headers, timeout, retries):
    for attempt in range(1, retries + 1):
        res = check_url(base, path, 'GET', headers=headers, timeout=timeout)
        if res.get('ok'):
            return res
        # brief backoff
        if attempt < retries:
            sleep(1)
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('base', nargs='?')
    ap.add_argument('--unit', help='unit_id to populate settings endpoint', default=os.environ.get('STAGING_WP_UNIT',''))
    ap.add_argument('--auth', help='Optional Authorization header value or user:pass', default=os.environ.get('STAGING_WP_AUTH',''))
    ap.add_argument('--retries', type=int, default=1, help='Per-endpoint retry count')
    ap.add_argument('--timeout', type=int, default=int(os.environ.get('STAGING_WP_TIMEOUT', '8')), help='Request timeout seconds')
    args = ap.parse_args()
    base = args.base or os.environ.get('STAGING_WP_URL', '')
    if not base:
        print("No base URL provided (positional arg or STAGING_WP_URL env).", file=sys.stderr)
        sys.exit(2)
    headers = {}
    if args.auth:
        headers.update(build_auth_header(args.auth))
    results = []
    for ep in ENDPOINTS:
        path = ep
        if ep.endswith('/settings') and args.unit:
            path = ep + '/' + args.unit
        res = try_endpoint_with_retries(base, path, headers, args.timeout, max(1, args.retries))
        results.append(res)
    print(json.dumps(results, indent=2))
    ok = all(r.get('ok') for r in results)
    sys.exit(0 if ok else 2)

if __name__ == '__main__':
    main()
