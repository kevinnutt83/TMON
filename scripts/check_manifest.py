#!/usr/bin/env python3
"""
Check manifest.json entries vs the served raw files and local repo files.
Usage:
  python3 scripts/check_manifest.py \
      --manifest https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/manifest.json \
      --base https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/
"""
import argparse
import hashlib
import json
import sys
from urllib.parse import urljoin
import os

try:
    import requests
except Exception as e:
    print("Install requests (python3 -m pip install requests) to use this script.")
    raise

def sha256_bytes(b: bytes) -> str:
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def normalize_expected(exp):
    if not exp: return ''
    s = str(exp).strip().lower()
    for p in ('sha256:', 'sha256=', 'sha256-'):
        if s.startswith(p):
            s = s[len(p):]
            break
    return s

def fetch_url(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.content

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', default='https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/manifest.json')
    ap.add_argument('--base', default='https://raw.githubusercontent.com/kevinnutt83/TMON/main/micropython/')
    ap.add_argument('--local-dir', default='micropython')
    args = ap.parse_args()

    print("Fetching manifest:", args.manifest)
    try:
        mbytes = fetch_url(args.manifest)
        manifest = json.loads(mbytes.decode('utf-8', 'ignore'))
    except Exception as e:
        print("Failed to fetch/parse manifest:", e)
        sys.exit(2)

    files = manifest.get('files') if isinstance(manifest, dict) else {}
    if not files:
        print("No 'files' object found in manifest.")
        sys.exit(1)

    any_mismatch = False
    for name, expected in sorted(files.items()):
        expected_hex = normalize_expected(expected)
        file_url = urljoin(args.base, name)
        print(f"\nChecking {name}\n  manifest expected: {expected_hex}\n  url: {file_url}")
        try:
            remote_bytes = fetch_url(file_url)
            remote_hash = sha256_bytes(remote_bytes)
            print(f"  remote sha256: {remote_hash}")
        except Exception as e:
            print(f"  ERROR fetching remote file: {e}")
            any_mismatch = True
            continue

        local_path = os.path.join(args.local_dir, name)
        local_hash = None
        if os.path.exists(local_path):
            try:
                with open(local_path, 'rb') as f:
                    local_hash = sha256_bytes(f.read())
                print(f"  local  sha256: {local_hash}")
            except Exception as e:
                print(f"  ERROR reading local file: {e}")

        if expected_hex and expected_hex != remote_hash:
            print("  => MISMATCH: manifest expected != remote content")
            any_mismatch = True
        elif expected_hex:
            print("  => OK: manifest matches remote")
        else:
            print("  => WARNING: no expected hash in manifest for this entry")

        if local_hash and local_hash != remote_hash:
            print("  NOTE: local repo file differs from remote raw file (possible CRLF/hosting transform or stale commit)")
            any_mismatch = True

    if any_mismatch:
        print("\nSummary: One or more mismatches detected.")
        print("Actions: regenerate manifest (scripts/gen_manifest.py), commit/push and re-run this check.")
        sys.exit(3)
    print("\nAll manifest entries match remote raw files.")
    sys.exit(0)

if __name__ == '__main__':
    main()
