# Lightweight debug/logging module
# Wraps utils.debug_print and centralizes category toggles.

try:
    import uasyncio as asyncio
except Exception:  # desktop lint fallback
    import asyncio

import settings

# Map categories to settings flags
CATEGORY_FLAGS = {
    'TEMP': 'DEBUG_TEMP',
    'HUMID': 'DEBUG_HUMID',
    'BAR': 'DEBUG_BAR',
    'LORA': 'DEBUG_LORA',
    'WIFI': 'DEBUG_WIFI',
    'OTA': 'DEBUG_OTA',
    'PROVISION': 'DEBUG_PROVISION',
    'SAMPLING': 'DEBUG_SAMPLING',
    'DISPLAY': 'DEBUG_DISPLAY',
    'REMOTE': 'DEBUG_REMOTE',
}

async def log(message, level='INFO', category=None):
    """Unified async debug logger.
    - Respects settings.DEBUG and category-specific flags.
    - Delegates rendering to utils.debug_print (console + OLED when enabled).
    """
    enabled = getattr(settings, 'DEBUG', False)
    if category:
        flag_name = CATEGORY_FLAGS.get(category.upper())
        if flag_name:
            enabled = enabled or getattr(settings, flag_name, False)
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
