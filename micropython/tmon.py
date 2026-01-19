# Firmware Version: v2.06.0
from utils import debug_print

async def frostwatchCheck():
    try:
        await debug_print("frostwatchCheck: new low observed", "FROSTWATCH")
    except Exception:
        pass

async def heatwatchCheck():
    try:
        await debug_print("heatwatchCheck: new high observed", "HEATWATCH")
    except Exception:
        pass

async def beginFrostOperations():
    try:
        await debug_print("beginFrostOperations: executing frost response", "FROSTWATCH")
    except Exception:
        pass

async def endFrostOperations():
    try:
        await debug_print("endFrostOperations: ending frost response", "FROSTWATCH")
    except Exception:
        pass

async def beginHeatOperations():
    try:
        await debug_print("beginHeatOperations: executing heat response", "HEATWATCH")
    except Exception:
        pass

async def endHeatOperations():
    try:
        await debug_print("endHeatOperations: ending heat response", "HEATWATCH")
    except Exception:
        pass