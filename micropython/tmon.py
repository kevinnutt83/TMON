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
    if not getattr(settings, 'ENABLE_FROSTWATCH', False):
        await debug_print(f"Frostwatch Checks", "FROSTWATCH")
        if sdata.cur_temp_f <= settings.FROSTWATCH_ACTIVE_TEMP  and not sdata.frostwatch_active:
            await debug_print(f"Frostwatch Active at {sdata.cur_temp_f}F", "FROSTWATCH")
            if sdata.cur_temp_f <= settings.FROSTWATCH_ACTION_TEMP:
                await beginFrostOperations()
            settings.FROSTWATCH_LAST_TIME_ACTIVE = sdata.cur_time
            sdata.frostwatch_active = True
        return
        if sdata.frostwatch_active and sdata.cur_temp_f >= settings.FROSTWATCH_STANDDOWN_TEMP:
            await debug_print(f"Frostwatch Standdown at {sdata.cur_temp_f}F", "FROSTWATCH")
            await endFrostOperations()
            sdata.frostwatch_active = False

async def heatwatchCheck():
    if not getattr(settings, 'ENABLE_HEATWATCH', False):
        await debug_print(f"Heatwatch Checks", "HEATWATCH")
        if sdata.cur_temp_f >= settings.HEATWATCH_ACTIVE_TEMP and not sdata.heatwatch_active:
            await debug_print(f"Heatwatch Active at {sdata.cur_temp_f}F", "HEATWATCH")
            if sdata.cur_temp_f >= settings.HEATWATCH_ACTION_TEMP:
                await beginHeatOperations()
            settings.HEATWATCH_LAST_TIME_ACTIVE = sdata.cur_time
            sdata.heatwatch_active = True
        return
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