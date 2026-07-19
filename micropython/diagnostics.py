import gc
import os
import utime as time

import settings
import sdata


def _ticks_to_s():
    try:
        return int(time.ticks_ms() // 1000)
    except Exception:
        return 0


def _safe_attr(obj, name, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _backlog_size():
    try:
        path = getattr(settings, 'LOG_DIR', '/logs') + '/field_data_backlog.log'
        with open(path, 'r') as f:
            n = 0
            for _ in f:
                n += 1
        return n
    except Exception:
        return 0


def _last_upload_ts():
    try:
        # Prefer explicit runtime value if available.
        ts = _safe_attr(sdata, 'last_successful_upload', None)
        if ts:
            return int(ts)
    except Exception:
        pass
    try:
        p = getattr(settings, 'FIELD_DATA_DELIVERED_LOG', '/logs/field_data.delivered.log')
        st = os.stat(p)
        # MicroPython stat tuple index 7 is mtime on most ports.
        if isinstance(st, (tuple, list)) and len(st) > 7:
            return int(st[7])
    except Exception:
        pass
    return 0


def get_system_health():
    return {
        'free_memory': int(gc.mem_free() if hasattr(gc, 'mem_free') else 0),
        'uptime_s': _ticks_to_s(),
        'last_error': _safe_attr(sdata, 'last_error', ''),
        'error_count': int(_safe_attr(sdata, 'error_count', 0) or 0),
    }


def get_lora_health():
    info = _safe_attr(settings, 'REMOTE_NODE_INFO', {}) or {}
    remote_count = 0
    max_missed = 0
    latest_hb = 0
    try:
        for _, node in info.items():
            if not isinstance(node, dict):
                continue
            remote_count += 1
            mm = int(node.get('missed_syncs', 0) or 0)
            if mm > max_missed:
                max_missed = mm
            hb = int(node.get('last_heartbeat_ts', 0) or 0)
            if hb > latest_hb:
                latest_hb = hb
    except Exception:
        pass

    return {
        'rssi': _safe_attr(sdata, 'lora_SigStr', None),
        'snr': _safe_attr(sdata, 'lora_snr', None),
        'connected': bool(_safe_attr(sdata, 'LORA_CONNECTED', False)),
        'last_rx_ts': int(_safe_attr(sdata, 'lora_last_rx_ts', 0) or 0),
        'last_tx_ts': int(_safe_attr(sdata, 'lora_last_tx_ts', 0) or 0),
        'missed_syncs': max_missed,
        'remote_nodes': remote_count,
        'last_heartbeat_ts': latest_hb,
    }


def get_transmission_stats():
    return {
        'backlog_size': _backlog_size(),
        'last_successful_upload': _last_upload_ts(),
    }


def get_diagnostics_snapshot():
    return {
        'system': get_system_health(),
        'lora': get_lora_health(),
        'transmission': get_transmission_stats(),
    }
