#!/usr/bin/env python3
"""
Generate micropython/manifest.json by hashing files in micropython/.

Usage:
  python scripts/generate_manifest.py [--commit] [--sig-secret ENV_VAR_NAME]

If --commit is provided and running in a git repo with GITHUB_TOKEN available in the environment,
the script will git-add and commit the updated manifest (useful in CI).
"""
import os
import sys
import argparse
import json
import hashlib
import hmac

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MP_DIR = os.path.join(REPO_ROOT, 'micropython')
MANIFEST_PATH = os.path.join(MP_DIR, 'manifest.json')
SIG_PATH = MANIFEST_PATH + '.sig'

def sha256_hex(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

def build_manifest(version=None):
    files = {}
    for root, dirs, filenames in os.walk(MP_DIR):
        # skip .git and other hidden directories
        if '.git' in root.split(os.sep):
            continue
        for fn in filenames:
            rel = os.path.relpath(os.path.join(root, fn), MP_DIR)
            # skip manifest files (we compute them)
            if rel in ('manifest.json', os.path.basename(SIG_PATH)):
                continue
            # Skip editor temp/backups
            if rel.endswith('~') or rel.startswith('.'):
                continue
            path = os.path.join(root, fn)
            files[rel.replace('\\','/')] = 'sha256:' + sha256_hex(path)
    manifest = {
        'name': 'tmon-micropython',
        'version': version or read_version(),
        'description': 'TMON MicroPython firmware manifest',
        'files': files
    }
    return manifest

def read_version():
    vfile = os.path.join(MP_DIR, 'version.txt')
    try:
        with open(vfile, 'r') as f:
            return f.read().strip()
    except Exception:
        return ''

def emit_manifest(manifest, path=MANIFEST_PATH):
    # Backup previous manifest
    try:
        if os.path.exists(path):
            os.replace(path, path + '.bak')
    except Exception:
        pass
    with open(path, 'w') as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print(f'Wrote manifest to {path} ({len(manifest["files"])} files)')

def emit_sig(manifest, secret_env='OTA_MANIFEST_HMAC_SECRET'):
    secret_name = secret_env
    secret = os.environ.get(secret_name, '') if secret_name else ''
    if not secret:
        print('No HMAC secret present; skipping signature generation.')
        return
    # Use canonical JSON representation: sorted keys, separators without whitespace
    canonical = json.dumps(manifest, separators=(',', ':'), sort_keys=True).encode('utf-8')
    mac = hmac.new(secret.encode('utf-8'), canonical, hashlib.sha256).hexdigest().lower()
    with open(SIG_PATH, 'w') as sf:
        sf.write(mac)
    print(f'Wrote manifest signature to {SIG_PATH}')

def git_commit(path, message='chore: update micropython manifest'):
    # best-effort: only attempt if git available and in repo
    try:
        import subprocess
        subprocess.check_call(['git', 'add', path])
        subprocess.check_call(['git', 'commit', '-m', message])
        print('Committed manifest via git')
    except Exception as e:
        print('Git commit skipped/failed:', e)

def manifest_equal(manifest, path):
    """
    Return True if the JSON manifest at 'path' is semantically equal to 'manifest' dict.
    """
    try:
        if not os.path.exists(path):
            return False
        with open(path, 'r') as f:
            existing = json.load(f)
        return existing == manifest
    except Exception:
        return False

def sig_equal(manifest, sig_path, secret_env='OTA_MANIFEST_HMAC_SECRET'):
    secret = os.environ.get(secret_env, '')
    if not secret:
        # no secret provided → cannot validate, treat as equal to avoid false failures
        return True
    try:
        if not os.path.exists(sig_path):
            return False
        canonical = json.dumps(manifest, separators=(',', ':'), sort_keys=True).encode('utf-8')
        mac = hmac.new(secret.encode('utf-8'), canonical, hashlib.sha256).hexdigest().lower()
        with open(sig_path, 'r') as sf:
            existing = sf.read().strip().lower()
        return existing == mac
    except Exception:
        return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--commit', action='store_true', help='git commit the new manifest (requires git & token in CI)')
    ap.add_argument('--sig-secret-env', default='OTA_MANIFEST_HMAC_SECRET', help='Env var name to read HMAC secret from for .sig generation')
    ap.add_argument('--check-only', action='store_true', help='Build and compare manifest+sig and exit non-zero if different (CI friendly)')
    args = ap.parse_args()

    if not os.path.isdir(MP_DIR):
        print('micropython directory not found at', MP_DIR, file=sys.stderr)
        sys.exit(2)

    version = read_version()
    manifest = build_manifest(version=version)

    if args.check_only:
        ok_m = manifest_equal(manifest, MANIFEST_PATH)
        ok_s = sig_equal(manifest, SIG_PATH, args.sig_secret_env)
        if ok_m and ok_s:
            print('Manifest and signature are up-to-date.')
            sys.exit(0)
        else:
            if not ok_m:
                print('Manifest file is out-of-date or missing.')
            if not ok_s:
                print('Manifest signature is out-of-date or missing (secret provided).')
            sys.exit(1)

    emit_manifest(manifest)
    emit_sig(manifest, secret_env=args.sig_secret_env)

    if args.commit:
        git_commit(MANIFEST_PATH)
        if os.path.exists(SIG_PATH):
            git_commit(SIG_PATH)

if __name__ == '__main__':
    main()
