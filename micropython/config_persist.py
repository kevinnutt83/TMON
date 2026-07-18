# TMON Verion 2.00.1d - Simple persistence helpers for MicroPython firmware settings/state. This module provides utility functions to read and write text and JSON files, as well as to manage simple flag files that can be used to track state across reboots. The functions include error handling to ensure that failures do not raise exceptions, which is important for stability on resource-constrained hardware. The ensure_dir function creates necessary directories for a given path, while the read/write functions handle file operations with optional defaults. The set_flag and is_flag_set functions provide a simple interface for managing boolean flags using the filesystem.

# Simple persistence helpers for MicroPython firmware settings/state
try:
    import ujson as json
except Exception:
    import json

import os

def ensure_dir(path):
    try:
        d = path
        # if path is a file path, take directory
        if '/' in path and not path.endswith('/'):
            d = path.rsplit('/', 1)[0]
        if not d:
            return
        parts = d.split('/')
        cur = ''
        for p in parts:
            if not p:
                continue
            cur += '/' + p if cur else '/' + p
            try:
                os.stat(cur)
            except OSError:
                try:
                    os.mkdir(cur)
                except Exception:
                    pass
    except Exception:
        pass

def write_text(path, text):
    try:
        ensure_dir(path)
        with open(path, 'w') as f:
            f.write(text if isinstance(text, str) else str(text))
        return True
    except Exception:
        return False

def read_text(path, default=None):
    try:
        with open(path, 'r') as f:
            return f.read()
    except Exception:
        return default

def write_json(path, obj):
    try:
        ensure_dir(path)
        with open(path, 'w') as f:
            f.write(json.dumps(obj))
        return True
    except Exception:
        return False

def write_json_atomic(path, obj):
    try:
        ensure_dir(path)
        tmp_path = path + '.tmp'
        with open(tmp_path, 'w') as f:
            f.write(json.dumps(obj))
        try:
            os.remove(path)
        except Exception:
            pass
        try:
            os.rename(tmp_path, path)
        except Exception:
            # Fallback for filesystems where rename semantics differ.
            with open(path, 'w') as f:
                f.write(json.dumps(obj))
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return True
    except Exception:
        return False

def read_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.loads(f.read())
    except Exception:
        return default

def read_json_safe(path, default=None):
    data = read_json(path, None)
    if isinstance(data, dict) or isinstance(data, list):
        return data
    return default

def set_flag(path: str, enabled: bool) -> bool:
    try:
        if enabled:
            return write_text(path, '1')
        else:
            try:
                os.remove(path)
                return True
            except Exception:
                return True
    except Exception:
        return False

def is_flag_set(path: str) -> bool:
    try:
        os.stat(path)
        return True
    except Exception:
        return False
