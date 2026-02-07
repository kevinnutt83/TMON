# Lightweight debug/logging module
# Wraps utils.debug_print and centralizes category toggles.

try:
    from platform_compat import asyncio  # CHANGED: unified import for MicroPython + CPython (Zero)
except Exception:  # fallback if platform_compat isn't available in some contexts
    try:
        import uasyncio as asyncio
    except Exception:
        import asyncio

import settings

# Map categories to settings flags
CATEGORY_FLAGS = {
    'TEMP': 'DEBUG_TEMP',
    'HUMID': 'DEBUG_HUMID',
    'BAR': 'DEBUG_BAR',
    'LORA': 'DEBUG_LORA',
    'WIFI': 'DEBUG_WIFI_CONNECT',   # CHANGED (was DEBUG_WIFI)
    'OTA': 'DEBUG_OTA',
    'PROVISION': 'DEBUG_PROVISION',
    'SAMPLING': 'DEBUG_SAMPLING',
    'DISPLAY': 'DEBUG_DISPLAY',

    # NEW: role-specific toggles present in settings.py
    'BASE_NODE': 'DEBUG_BASE_NODE',
    'REMOTE_NODE': 'DEBUG_REMOTE_NODE',
    'WIFI_NODE': 'DEBUG_WIFI_NODE',

    # NEW: RS485 category present in settings.py
    'RS485': 'DEBUG_RS485',
}

# NEW: legacy flag aliases for compatibility (best-effort)
_LEGACY_FLAG_ALIASES = {
    'DEBUG_WIFI_CONNECT': ('DEBUG_WIFI_CONNECTION', 'DEBUG_WIFI'),
    'DEBUG_REMOTE_NODE': ('DEBUG_REMOTE',),
}

def _flag_enabled(flag_name: str) -> bool:
    try:
        if getattr(settings, flag_name, False):
            return True
    except Exception:
        pass
    for legacy in _LEGACY_FLAG_ALIASES.get(flag_name, ()):
        try:
            if getattr(settings, legacy, False):
                return True
        except Exception:
            pass
    return False

async def log(message, level='INFO', category=None):
    """Unified async debug logger.
    - Respects settings.DEBUG and category-specific flags.
    - Delegates rendering to utils.debug_print (console + OLED when enabled).
    """
    enabled = getattr(settings, 'DEBUG', False)
    if category:
        flag_name = CATEGORY_FLAGS.get(category.upper())
        if flag_name:
            enabled = enabled or _flag_enabled(flag_name)  # CHANGED: use shim
    if not enabled:
        return
    try:
        from utils import debug_print  # import late to avoid cycles
        await debug_print(f"[{category or 'GEN'}] {message}", level)
    except Exception:
        # Best-effort fallback print without raising
        try:
            print(f"[{level}] {category or 'GEN'}: {message}")
        except Exception:
            pass

# Convenience helpers
async def info(msg, category=None):
    await log(msg, 'INFO', category)

async def warn(msg, category=None):
    await log(msg, 'WARN', category)

async def error(msg, category=None):
    await log(msg, 'ERROR', category)
