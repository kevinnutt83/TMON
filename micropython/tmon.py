# TMON Verion 2.00.1d - Main module for TMON MicroPython firmware: defines core async tasks for frostwatch and heatwatch checks and operations. This module is responsible for orchestrating the main functionality of the device, including sensor sampling, LoRa communication, field data uploads, command polling, OTA updates, and display updates. It also includes a first-boot provisioning check-in to the TMON Admin hub. The tasks are designed to run periodically with error handling and GC management to ensure stable operation on resource-constrained hardware.

# Firmware Version: v2.06.0
from utils import debug_print
import settings
import sdata

# --- GC: best-effort cleanup after module import / heavy init ---
try:
    import gc
    gc.collect()
except Exception:
    pass

async def frostwatchCheck():
    # Only run checks when enabled; preserves existing calls/variables while fixing control flow.
    if not getattr(settings, 'ENABLE_FROSTWATCH', False):
        return

    await debug_print(f"Frostwatch Checks", "FROSTWATCH")

    if sdata.cur_temp_f <= settings.FROSTWATCH_ACTIVE_TEMP and not sdata.frostwatch_active:
        await debug_print(f"Frostwatch Active at {sdata.cur_temp_f}F", "FROSTWATCH")
        if sdata.cur_temp_f <= settings.FROSTWATCH_ACTION_TEMP:
            await beginFrostOperations()
        settings.FROSTWATCH_LAST_TIME_ACTIVE = sdata.cur_time
        sdata.frostwatch_active = True

    if sdata.frostwatch_active and sdata.cur_temp_f >= settings.FROSTWATCH_STANDDOWN_TEMP:
        await debug_print(f"Frostwatch Standdown at {sdata.cur_temp_f}F", "FROSTWATCH")
        await endFrostOperations()
        sdata.frostwatch_active = False

async def heatwatchCheck():
    # Only run checks when enabled; preserves existing calls/variables while fixing control flow.
    if not getattr(settings, 'ENABLE_HEATWATCH', False):
        return

    await debug_print(f"Heatwatch Checks", "HEATWATCH")

    if sdata.cur_temp_f >= settings.HEATWATCH_ACTIVE_TEMP and not sdata.heatwatch_active:
        await debug_print(f"Heatwatch Active at {sdata.cur_temp_f}F", "HEATWATCH")
        if sdata.cur_temp_f >= settings.HEATWATCH_ACTION_TEMP:
            await beginHeatOperations()
        settings.HEATWATCH_LAST_TIME_ACTIVE = sdata.cur_time
        sdata.heatwatch_active = True

    if sdata.heatwatch_active and sdata.cur_temp_f <= settings.HEATWATCH_STANDDOWN_TEMP:
        await debug_print(f"Heatwatch Standdown at {sdata.cur_temp_f}F", "HEATWATCH")
        await endHeatOperations()
        sdata.heatwatch_active = False

async def beginFrostOperations():
    await debug_print(f"Frostwatch Operations Start", "FROSTWATCH")
    pass

async def beginHeatOperations():
    await debug_print(f"Heatwatch Operations Start", "HEATWATCH")
    pass

async def endFrostOperations():
    await debug_print(f"Frostwatch Operations End", "FROSTWATCH")
    pass

async def endHeatOperations():
    await debug_print(f"Heatwatch Operations End", "HEATWATCH")
    pass