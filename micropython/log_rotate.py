try:
    import uos as os
except Exception:
    import os

try:
    import utime as time
except Exception:
    import time

import settings

_last_check = 0


def _file_size(path):
    try:
        return os.stat(path)[6]
    except Exception:
        return 0


def _rotate_one(path, max_rotations=3):
    try:
        if _file_size(path) <= 0:
            return False

        try:
            os.remove('%s.%d' % (path, max_rotations))
        except Exception:
            pass

        for i in range(max_rotations - 1, 0, -1):
            src = '%s.%d' % (path, i)
            dst = '%s.%d' % (path, i + 1)
            try:
                os.rename(src, dst)
            except Exception:
                pass

        try:
            os.rename(path, path + '.1')
        except Exception:
            return False

        try:
            with open(path, 'w') as handle:
                handle.write('')
        except Exception:
            pass

        return True
    except Exception:
        return False


def rotate_logs_if_needed(force=False):
    global _last_check
    try:
        now = time.time()
        interval = int(getattr(settings, 'LOG_ROTATE_CHECK_INTERVAL_S', 300))
        if not force and (now - _last_check) < interval:
            return
        _last_check = now

        max_bytes = int(getattr(settings, 'LOG_MAX_BYTES', 64 * 1024))
        max_rotations = int(getattr(settings, 'LOG_MAX_ROTATIONS', 3))
        files = getattr(settings, 'LOG_FILES_TO_ROTATE', []) or []

        for path in files:
            try:
                if _file_size(path) >= max_bytes:
                    _rotate_one(path, max_rotations=max_rotations)
            except Exception:
                pass
    except Exception:
        pass


async def log_rotate_loop(interval_s=None):
    try:
        import uasyncio as asyncio
    except Exception:
        import asyncio

    if interval_s is None:
        interval_s = int(getattr(settings, 'LOG_ROTATE_CHECK_INTERVAL_S', 300))

    while True:
        try:
            rotate_logs_if_needed(force=True)
        except Exception:
            pass
        await asyncio.sleep(interval_s)