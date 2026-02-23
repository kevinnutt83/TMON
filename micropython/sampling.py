# Firmware Version: v2.06.0

import sdata
import settings
from utils import free_pins_i2c
from platform_compat import asyncio, time, gc  # CHANGED: replaces `import uasyncio as asyncio`
from utils import debug_print
from tmon import frostwatchCheck, heatwatchCheck, beginFrostOperations, beginHeatOperations, endFrostOperations, endHeatOperations

# CHANGED: don't hard-import sensor drivers at module import time (Zero/CPython-safe)
try:
    from lib.BME280 import BME280 as _BME280
except Exception:
    _BME280 = None


#Sampling Routine for sample all sensor types if they are enabled
async def sampleEnviroment():
    from utils import led_status_flash
    import sdata as _s
    _s.sampling_active = True
    try:
        led_status_flash('SAMPLE_TEMP')
        await sampleTemp()
        led_status_flash('SAMPLE_BAR')
        await frost_and_heat_watch()  # Call frost and heat watch after sampling
    finally:
        _s.sampling_active = False
        try:
            gc.collect()
        except Exception:
            pass

async def _dbg(msg, tag="SAMPLING"):
    try:
        from utils import debug_print  # type: ignore
        await debug_print(msg, tag)
    except Exception:
        try:
            print(f"[{tag}] {msg}")
        except Exception:
            pass

async def sampleTemp():
    if settings.SAMPLE_TEMP:
        if settings.ENABLE_sensorBME280:
            await free_pins_i2c()  # Ensure pins are free before BME280
            await sampleBME280()
            await free_pins_i2c()  # Free pins after BME280 for next device

async def sampleBME280():
    if settings.ENABLE_sensorBME280:
        # NEW: Zero/CPython does not have the MicroPython I2C/sensor stack by default.
        if str(getattr(settings, "MCU_TYPE", "")).lower() == "zero":
            if settings.DEBUG and settings.DEBUG_TEMP:
                await debug_print("sample:BME280 skipped on MCU_TYPE=zero", "DEBUG TEMP")
            return

        from utils import led_status_flash
        import sdata as _s
        _s.sampling_active = True
        try:
            try:
                from oled import display_message
                await display_message("Sampling BME280", 1)
            except Exception:
                pass
            import lora as lora_module
            # Deinit LoRa and free pins before using BME280
            async with lora_module.pin_lock:
                if lora_module.lora is not None:
                    try:
                        lora_module.lora.spi.deinit()
                    except Exception:
                        pass
                    lora_module.lora = None
            await free_pins_i2c()
            # CHANGED: resolve driver via guarded import above; keep fallback for legacy layouts
            BME = _BME280
            if BME is None:
                try:
                    from BME280 import BME280 as BME  # legacy path on some builds
                except Exception:
                    BME = None
            if BME is None:
                if settings.DEBUG and settings.DEBUG_TEMP:
                    await debug_print("sample:BME280 driver missing", "SAMPLE ERROR TEMP")
                return

            sensor = BME()
            sensor.get_calib_param()
            try:
                led_status_flash('SAMPLE_BME280')
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
                    try:
                        from oled import display_message
                        await display_message("BME280 Sample OK", 1.5)
                    except Exception:
                        pass
            except Exception as e:
                if settings.DEBUG and settings.DEBUG_TEMP:
                    await debug_print(f"sample:BME280 err: {e}", "SAMPLE ERROR TEMP")
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
            # NEW: GC after BME280 sampling and bus cleanup
            try:
                from utils import maybe_gc
                maybe_gc("sample_bme280", min_interval_ms=3000, mem_free_below=50 * 1024)
            except Exception:
                pass
        finally:
            _s.sampling_active = False

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

async def update_minmax_from_payload(payload, source='remote'):
    try:
        if not isinstance(payload, dict):
            return
        t_f = payload.get('t_f')
        bar = payload.get('bar')
        hum = payload.get('hum')
        if t_f is not None:
            await findLowestTemp(t_f, source=source)
            await findHighestTemp(t_f, source=source)
        if bar is not None:
            await findLowestBar(bar, source=source)
            await findHighestBar(bar, source=source)
        if hum is not None:
            await findLowestHumid(hum, source=source)
            await findHighestHumid(hum, source=source)
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