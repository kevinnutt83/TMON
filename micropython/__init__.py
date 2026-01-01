__all__ = ['provision', 'firmware_updater', 'settings']
__version__ = "0.2.3"

# Provide convenience import aliases (useful in host Python tests)
from . import provision as provision
from . import firmware_updater as firmware_updater

# Attempt to import settings module to make `from micropython import settings` available
try:
    from . import settings as settings
except Exception:
    # If settings not present, leave as None — calling code should handle missing settings
    settings = None
