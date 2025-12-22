# Firmware Version: v2.06.0

import sdata
import settings
from utils import free_pins
import uasyncio as asyncio
from utils import debug_print
from tmon import frostwatchCheck, heatwatchCheck, beginFrostOperations, beginHeatOperations, endFrostOperations, endHeatOperations
from BME280 import BME280


#Sampling Routine for sample all sensor types if they are enabled
async def sampleEnviroment():
    from utils import led_status_flash
    led_status_flash('SAMPLE_TEMP')
    await sampleTemp()
    led_status_flash('SAMPLE_BAR')
    await frost_and_heat_watch()  # Call frost and heat watch after sampling

#Sample Temperatures from enabled sensors devices
async def sampleTemp():
    if settings.SAMPLE_TEMP:
        if settings.ENABLE_sensorBME280:
            await free_pins()  # Ensure pins are free before BME280
            await sampleBME280()
            await free_pins()  # Free pins after BME280 for next device

async def sampleBME280():
    if settings.ENABLE_sensorBME280:
        from utils import led_status_flash
        import lora as lora_module
        # Deinit LoRa and free pins before using BME280
        async with lora_module.pin_lock:
            if lora_module.lora is not None:
                lora_module.lora.spi.deinit()
                lora_module.lora = None
        await free_pins()
        from BME280 import BME280
        sensor = BME280()
        sensor.get_calib_param()
        try:
            led_status_flash('SAMPLE_TEMP')
            data = []
            data = sensor.readData()
            sdata.cur_temp_c = data[1]
            sdata.cur_temp_f = (sdata.cur_temp_c * 9/5) + 32
            sdata.cur_humid = data[2]
            sdata.cur_bar_pres = data[0]

            # NEW: evaluate local sample against historical min/max for frost/heat logic
            try:
                await findLowestTemp(sdata.cur_temp_f, source='local')
                await findHighestTemp(sdata.cur_temp_f, source='local')
                await findLowestBar(sdata.cur_bar_pres, source='local')
                await findHighestBar(sdata.cur_bar_pres, source='local')
                await findLowestHumid(sdata.cur_humid, source='local')
                await findHighestHumid(sdata.cur_humid, source='local')
            except Exception:
                pass

            if settings.DEBUG and settings.DEBUG_TEMP:
                await debug_print(
                    "sample:BME p:%7.2f t:%-6.2f h:%6.2f" % (data[0], data[1], data[2]),
                    "DEBUG TEMP"
                )
        except Exception as e:
            if settings.DEBUG and settings.DEBUG_TEMP:
                await debug_print(f"sample:BME err: {e}", "SAMPLE ERROR TEMP")
        finally:
            # Some MicroPython ports do not implement I2C.deinit(); guard accordingly
            try:
                if getattr(sensor, "i2c", None):
                    i2c_obj = sensor.i2c
                    if hasattr(i2c_obj, "deinit"):
                        i2c_obj.deinit()
            except Exception as e:
                if settings.DEBUG and settings.DEBUG_TEMP:
                    await debug_print(f"BME: deinit skipped: {e}", "DEBUG TEMP")
            finally:
                # Help GC release the bus reference
                sensor.i2c = None
        # Optionally, re-initialize LoRa here if needed for next operation

async def findLowestTemp(compareTemp, source='local'):
    try:
        if compareTemp is None:
            return
        if sdata.lowest_temp_f == 0 or compareTemp < sdata.lowest_temp_f:
            sdata.lowest_temp_f = compareTemp
            await frostwatchCheck()
    except Exception:
        pass

async def findLowestBar(compareBar, source='local'):
    try:
        if compareBar is None:
            return
        if sdata.lowest_bar == 0 or compareBar < sdata.lowest_bar:
            sdata.lowest_bar = compareBar
    except Exception:
        pass

async def findLowestHumid(compareHumid, source='local'):
    try:
        if compareHumid is None:
            return
        if sdata.lowest_humid == 0 or compareHumid < sdata.lowest_humid:
            sdata.lowest_humid = compareHumid
    except Exception:
        pass

async def findHighestTemp(compareTemp, source='local'):
    try:
        if compareTemp is None:
            return
        if compareTemp > sdata.highest_temp_f:
            sdata.highest_temp_f = compareTemp
            await heatwatchCheck()
    except Exception:
        pass

async def findHighestBar(compareBar, source='local'):
    try:
        if compareBar is None:
            return
        if compareBar > sdata.highest_bar:
            sdata.highest_bar = compareBar
    except Exception:
        pass

async def findHighestHumid(compareHumid, source='local'):
    try:
        if compareHumid is None:
            return
        if compareHumid > sdata.highest_humid:
            sdata.highest_humid = compareHumid
    except Exception:
        pass

async def beginFrostOperations():
    # Implement frost operations (e.g., engage relays or notify)
    await debug_print("beginFrostOperations: executing frost response", "FROSTWATCH")
    # ...existing code or hardware actions...
    pass

async def frost_and_heat_watch():
    try:
        # FROSTWATCH LOGIC
        if getattr(settings, 'ENABLE_FROSTWATCH', False):
            if sdata.cur_temp_f < getattr(settings, 'FROSTWATCH_ACTIVE_TEMP', 70):
                sdata.frostwatch_active = True
            else:
                sdata.frostwatch_active = False
            if sdata.cur_temp_f < getattr(settings, 'FROSTWATCH_ALERT_TEMP', 42):
                sdata.frost = True
            else:
                sdata.frost = False
            if not sdata.frost_act:
                if sdata.cur_temp_f < getattr(settings, 'FROSTWATCH_ACTION_TEMP', 38):
                    sdata.frost_act = True
                    await beginFrostOperations()
            else:
                if sdata.cur_temp_f > getattr(settings, 'FROSTWATCH_STANDDOWN_TEMP', 40):
                    sdata.frost_act = False
                    await endFrostOperations()
        # HEATWATCH LOGIC
        if getattr(settings, 'ENABLE_HEATWATCH', False):
            if sdata.cur_temp_f > getattr(settings, 'HEATWATCH_ACTIVE_TEMP', 90):
                sdata.heatwatch_active = True
            else:
                sdata.heatwatch_active = False
            if sdata.cur_temp_f > getattr(settings, 'HEATWATCH_ALERT_TEMP', 100):
                sdata.heat = True
            else:
                sdata.heat = False
            if not sdata.heat_act:
                if sdata.cur_temp_f > getattr(settings, 'HEATWATCH_ACTION_TEMP', 110):
                    sdata.heat_act = True
                    await beginHeatOperations()
            else:
                if sdata.cur_temp_f < getattr(settings, 'HEATWATCH_STANDDOWN_TEMP', 105):
                    sdata.heat_act = False
                    await endHeatOperations()
    except Exception as e:
        await debug_print(f"sample:frost/heat err: {e}", "FROSTHEATWATCH ERROR")