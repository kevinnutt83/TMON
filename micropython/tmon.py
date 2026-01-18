# Firmware Version: v2.06.0
try:
    import uasyncio as asyncio
except Exception:
    asyncio = None

from utils import debug_print

async def frostwatchCheck():
    try:
        await debug_print("frostwatchCheck", "FROSTWATCH")
    except Exception:
        pass
    if asyncio:
        await asyncio.sleep(0)

async def heatwatchCheck():
    try:
        await debug_print("heatwatchCheck", "HEATWATCH")
    except Exception:
        pass
    if asyncio:
        await asyncio.sleep(0)

async def beginFrostOperations():
    try:
        await debug_print("beginFrostOperations", "FROSTWATCH")
    except Exception:
        pass
    if asyncio:
        await asyncio.sleep(0)

async def beginHeatOperations():
    try:
        await debug_print("beginHeatOperations", "HEATWATCH")
    except Exception:
        pass
    if asyncio:
        await asyncio.sleep(0)

async def endFrostOperations():
    try:
        await debug_print("endFrostOperations", "FROSTWATCH")
    except Exception:
        pass
    if asyncio:
        await asyncio.sleep(0)

async def endHeatOperations():
    try:
        await debug_print("endHeatOperations", "HEATWATCH")
    except Exception:
        pass
    if asyncio:
        await asyncio.sleep(0)