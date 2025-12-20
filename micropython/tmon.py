# Firmware Version: v2.04.0
from utils import debug_print

async def frostwatchCheck():
    await debug_print(f"Frostwatch Checks", "FROSTWATCH")

async def heatwatchCheck():
    await debug_print(f"Heatwatch Checks", "HEATWATCH")

async def beginFrostOperations():
    await debug_print(f"Frostwatch Operations Start", "FROSTWATCH")
    pass

async def beginHeatOperations():
    await debug_print(f"Heatwatch Operations Start", "HEATWATCH")
    pass

async def endFrostOperations():
    pass

async def endHeatOperations():
    pass