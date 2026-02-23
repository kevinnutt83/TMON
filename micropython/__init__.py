# TMON Verion 2.00.1d - Centralized module imports for TMON MicroPython firmware. This __init__.py file serves as the main entry point for importing the various modules that make up the firmware, such as provisioning, firmware updating, settings management, OTA updates, OLED display control, engine control, encryption, relay management, and debugging. By centralizing these imports here, it allows other parts of the firmware to simply import from micropython to access all of these functionalities in a consistent way. The __version__ variable provides a single source of truth for the firmware version that can be accessed throughout the codebase.

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
