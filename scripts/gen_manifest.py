"""
Generate micropython/manifest.json mapping filename -> sha256:<hex>
Usage:
  python3 scripts/gen_manifest.py           # generate for micropython/ into micropython/manifest.json
  python3 scripts/gen_manifest.py -d micropython -o micropython/manifest.json --sign-secret-file .hmac_secret
  python3 scripts/gen_manifest.py --check   # compare with existing manifest and show diffs
"""
import os
import sys
import argparse
import hashlib
import json
import hmac
import ast
import re

def find_allowlist(base_dir):
    settings_path = os.path.join(base_dir, 'settings.py')
    if not os.path.exists(settings_path):
        return None
    txt = open(settings_path, 'r', encoding='utf-8', errors='ignore').read()
    m = re.search(r'OTA_FILES_ALLOWLIST\s*=\s*(\[[\s\S]*?\])', txt, re.M)
    if not m:
        return None
    try:
        arr = ast.literal_eval(m.group(1))
        if isinstance(arr, (list, tuple)):
            return [str(x) for x in arr]
    except Exception:
        return None
    return None

def collect_files(base_dir, allowlist=None):
    out = []
    if allowlist:
        for p in allowlist:
            p = p.strip()
            if not p:
                continue
            fp = os.path.join(base_dir, p)
            if os.path.exists(fp) and os.path.isfile(fp):
                out.append(os.path.normpath(p))
            else:
                # try top-level fallback
                if os.path.exists(os.path.join(base_dir, os.path.basename(p))):
                    out.append(os.path.basename(p))
    else:
        # default: all .py files in base_dir (non-recursive) except manifest/version files
        for fn in sorted(os.listdir(base_dir)):
            if not fn.endswith('.py'):
                continue
            if fn in ('manifest.json', 'version.txt'):
                continue
            out.append(fn)
    return out

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def load_existing(path):
    if not os.path.exists(path):
        return {}
    try:
        return json.load(open(path, 'r', encoding='utf-8'))
    except Exception:
        return {}

def main():
    ap = argparse.ArgumentParser(description='Generate micropython/manifest.json with sha256 hashes')
    ap.add_argument('-d', '--dir', default='micropython', help='directory to scan (default: micropython)')
    ap.add_argument('-o', '--output', default=None, help='output manifest path (default: <dir>/manifest.json)')
    ap.add_argument('--sign-secret', help='HMAC secret string to sign manifest (hex or raw)')
    ap.add_argument('--sign-secret-file', help='File containing HMAC secret')
    ap.add_argument('--check', action='store_true', help='Compare with existing manifest and report diffs')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    base = args.dir
    if not os.path.isdir(base):
        print('Error: base dir not found:', base)
        sys.exit(2)
    out_path = args.output or os.path.join(base, 'manifest.json')

    allowlist = find_allowlist(base)
    files = collect_files(base, allowlist=allowlist)

    manifest = {'files': {}}
    for rel in files:
        path = os.path.join(base, rel)
        if not os.path.exists(path):
            if args.verbose:
                print('Skipping missing', rel)
            continue
        digest = sha256_file(path)
        manifest['files'][rel] = 'sha256:' + digest
        if args.verbose:
            print(rel, manifest['files'][rel])

    # Sort for stable output
    manifest_sorted = {'files': dict(sorted(manifest['files'].items()))}

    if args.check:
        existing = load_existing(out_path)
        changed = []
        added = []
        removed = []
        old_files = existing.get('files', {}) if isinstance(existing, dict) else {}
        for k, v in manifest_sorted['files'].items():
            if k not in old_files:
                added.append(k)
            elif old_files.get(k) != v:
                changed.append(k)
        for k in old_files.keys():
            if k not in manifest_sorted['files']:
                removed.append(k)
        print('Check manifest differences:')
        print('  added:', added)
        print('  changed:', changed)
        print('  removed:', removed)
        if not (added or changed or removed):
            print('  manifest matches')
        # still write unless user only wanted check?
    # Write manifest
    tmp = out_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(manifest_sorted, f, indent=2, sort_keys=True)
        f.write('\n')
    os.replace(tmp, out_path)
    print('Wrote manifest to', out_path)

    # Optional HMAC signing
    secret = None
    if args.sign_secret_file:
        try:
            secret = open(args.sign_secret_file, 'r', encoding='utf-8').read().strip()
        except Exception:
            secret = None
    if not secret and args.sign_secret:
        secret = args.sign_secret
    if not secret:
        # try env
        secret = os.environ.get('TMON_MANIFEST_HMAC_SECRET') or os.environ.get('OTA_MANIFEST_HMAC_SECRET')
    if secret:
        # ensure secret is bytes
        if isinstance(secret, str):
            secret_b = secret.encode('utf-8')
        else:
            secret_b = secret
        payload = json.dumps(manifest_sorted, sort_keys=True).encode('utf-8')
        sig = hmac.new(secret_b, payload, hashlib.sha256).hexdigest()
        sig_path = out_path + '.sig'
        with open(sig_path, 'w', encoding='utf-8') as f:
            f.write(sig + '\n')
        print('Wrote manifest signature to', sig_path)

if __name__ == '__main__':
    main()
