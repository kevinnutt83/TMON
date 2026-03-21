# TMON v2.01.0 - Sampling module
# All sensors (BME280 interior/probe, soil probe) with frost/heat watch.
# Non-blocking, GC calls added, fully compatible with LoRa on Core 1.

import sdata
import settings
from utils import free_pins_i2c
import uasyncio as asyncio
from utils import debug_print, log_error
from tmon import frostwatchCheck, heatwatchCheck, beginFrostOperations, beginHeatOperations, endFrostOperations, endHeatOperations
from machine import I2C, Pin

# ===================== Sampling Routine =====================
async def sampleEnviroment():
    from utils import led_status_flash
    import sdata as _s
    _s.sampling_active = True
    try:
        led_status_flash('SAMPLE_TEMP')
        await sampleTemp()
        
        if getattr(settings, 'SAMPLE_SOIL', False):
            led_status_flash('SAMPLE_SOIL')
            await sampleSoil()
        
        led_status_flash('SAMPLE_BAR')
        await frost_and_heat_watch()
    finally:
        _s.sampling_active = False

async def sampleTemp():
    if not getattr(settings, 'SAMPLE_TEMP', True):
        return

    if not getattr(settings, 'ENABLE_sensorBME280', False):
        return

    # === INTERIOR DEVICE ENCLOSURE SENSOR ===
    if (getattr(settings, 'SAMPLE_DEVICE_TEMP', False) or
        getattr(settings, 'SAMPLE_DEVICE_BAR', False) or
        getattr(settings, 'SAMPLE_DEVICE_HUMID', False)) and settings.ENABLE_DEVICE_BME280:
        await free_pins_i2c()
        await sampleBME280Interior()
        await free_pins_i2c()

    # === EXTERIOR PROBE SENSOR ===
    if (getattr(settings, 'SAMPLE_PROBE_TEMP', False) or
        getattr(settings, 'SAMPLE_PROBE_BAR', False) or
        getattr(settings, 'SAMPLE_PROBE_HUMID', False)) and settings.ENABLE_PROBE_BME280:
        await free_pins_i2c()
        await sampleBME280Probe()
        await free_pins_i2c()

async def _read_bme280(i2c, target="probe"):
    sensor = None
    try:
        from BME280 import BME280
        try:
            sensor = BME280(i2c=i2c)
        except TypeError:
            # Device has older BME280.py without i2c parameter support
            sensor = BME280()
            if i2c is not None:
                try:
                    sensor.i2c.deinit()
                except Exception:
                    pass
                sensor.i2c = i2c
                # Re-send config registers on the correct I2C bus
                sensor.writeReg(0xF2, sensor.osrs_h)
                sensor.writeReg(0xF4, (sensor.osrs_t << 5) | (sensor.osrs_p << 2) | sensor.mode)
                sensor.writeReg(0xF5, (sensor.t_sb << 5) | (sensor.filter << 2) | sensor.spi3w_en)
        sensor.get_calib_param()
        data = sensor.readData()

        temp_c = data[1]
        temp_f = (temp_c * 9/5) + 32
        humid = data[2]
        bar = data[0]

        if target == "probe":
            if getattr(settings, 'SAMPLE_PROBE_TEMP', False):
                sdata.cur_temp_c = temp_c
                sdata.cur_temp_f = temp_f
                await findLowestTemp(temp_f)
                await findHighestTemp(temp_f)
            if getattr(settings, 'SAMPLE_PROBE_BAR', False):
                sdata.cur_bar_pres = bar
                await findLowestBar(bar)
                await findHighestBar(bar)
            if getattr(settings, 'SAMPLE_PROBE_HUMID', False):
                sdata.cur_humid = humid
                await findLowestHumid(humid)
                await findHighestHumid(humid)

        else:  # device
            if getattr(settings, 'SAMPLE_DEVICE_TEMP', False):
                sdata.cur_device_temp_c = temp_c
                sdata.cur_device_temp_f = temp_f
            if getattr(settings, 'SAMPLE_DEVICE_BAR', False):
                sdata.cur_device_bar_pres = bar
            if getattr(settings, 'SAMPLE_DEVICE_HUMID', False):
                sdata.cur_device_humid = humid

        if settings.DEBUG and settings.DEBUG_TEMP:
            await debug_print(
                f"BME280 {target}: p:{bar:7.2f} t:{temp_c:6.2f} h:{humid:6.2f}",
                "DEBUG TEMP"
            )
        return data

    except Exception as e:
        await log_error(f"BME280 {target} fatal error: {e}", "BME280")
        await debug_print(f"BME280 {target} fatal error – disabling sensor", "ERROR")
        
        if target == "device":
            settings.ENABLE_DEVICE_BME280 = False
            settings.SAMPLE_DEVICE_TEMP = False
            settings.SAMPLE_DEVICE_BAR = False
            settings.SAMPLE_DEVICE_HUMID = False
        else:
            settings.ENABLE_PROBE_BME280 = False
            settings.SAMPLE_PROBE_TEMP = False
            settings.SAMPLE_PROBE_BAR = False
            settings.SAMPLE_PROBE_HUMID = False
        return None
    finally:
        if sensor is not None:
            try:
                if hasattr(sensor, "i2c") and hasattr(sensor.i2c, "deinit"):
                    sensor.i2c.deinit()
            except:
                pass
            sensor.i2c = None

async def sampleBME280Interior():
    from utils import led_status_flash
    led_status_flash('SAMPLE_DEVICE_TEMP')
    try:
        from oled import display_message
        await display_message("Sampling Interior Temp", 1)
    except:
        pass

    i2c = I2C(0, scl=Pin(settings.DEVICE_TEMP_SCL_PIN),
              sda=Pin(settings.DEVICE_TEMP_SDA_PIN), freq=400000)
    await _read_bme280(i2c, target="device")

async def sampleBME280Probe():
    from utils import led_status_flash
    led_status_flash('SAMPLE_BME280')
    try:
        from oled import display_message
        await display_message("Sampling Exterior Probe", 1)
    except:
        pass

    import lora as lora_module
    async with lora_module.pin_lock:
        if lora_module.lora is not None:
            try:
                lora_module.lora.spi.deinit()
            except:
                pass
            lora_module.lora = None

    i2c = I2C(1, scl=Pin(settings.BME280_PROBE_SCL_PIN),
              sda=Pin(settings.BME280_PROBE_SDA_PIN), freq=400000)
    await _read_bme280(i2c, target="probe")

async def sampleSoil():
    if not getattr(settings, 'SAMPLE_SOIL', False):
        return

    import sdata as _s
    from utils import led_status_flash
    _s.sampling_active = True

    try:
        try:
            from oled import display_message
            await display_message("Sampling Soil Probe", 1)
        except Exception:
            pass

        result = await sample_soil_probe()

        if result and result.get("status") == "success":
            _s.cur_soil_moisture = result.get("moisture_percent", 0.0)
            _s.cur_soil_temp_c = result.get("temperature_c")
            _s.cur_soil_temp_f = result.get("temperature_f")

            if getattr(settings, 'DEBUG_SOIL_PROBE', False):
                await debug_print(
                    f"Soil Moisture: {_s.cur_soil_moisture:.1f}% | SoilTemp: {_s.cur_soil_temp_f:.1f}°F",
                    "SOIL"
                )
        else:
            await debug_print("Soil probe returned no valid data", "SOIL")

    except Exception as e:
        await debug_print(f"sampleSoil wrapper error: {e}", "ERROR")
    finally:
        _s.sampling_active = False

# ===================== Min/Max Trackers =====================
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

# ===================== Frost / Heat Watch =====================
async def frost_and_heat_watch():
    try:
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
        

async def sample_soil_probe():
    if not getattr(settings, 'SAMPLE_SOIL', False):
        await debug_print("Soil sampling disabled (SAMPLE_SOIL=False)", "SOIL")
        return {"status": "disabled"}

    await debug_print("Starting soil probe sampling...", "SOIL")

    try:
        adc_moist = machine.ADC(settings.SOIL_PROBE_PIN)
        adc_moist.atten(machine.ADC.ATTN_11DB)          

        readings = []
        for _ in range(10):
            readings.append(adc_moist.read_u16())
            await asyncio.sleep_ms(10)                  

        raw_moisture = sum(readings) // len(readings)

        await debug_print(f"Raw moisture (u16 avg): {raw_moisture}", "SOIL")

        min_raw = getattr(settings, 'MIN_SOIL_MOISTURE', 45)
        max_raw = getattr(settings, 'MAX_SOIL_MOISTURE', 120)

        if raw_moisture >= 65500:
            await debug_print("Error: Sensor maxed out — check wiring/power", "SOIL")
            moisture_pct = 0.0
        elif max_raw > min_raw:
            moisture_pct = (max_raw - raw_moisture) * 100.0 / (max_raw - min_raw)
            moisture_pct = max(0.0, min(100.0, moisture_pct))
        else:
            moisture_pct = 50.0

        await debug_print(f"Soil Moisture: {moisture_pct:.1f}%", "SOIL")

        temperature_c = None
        temperature_f = None
        try:
            adc_temp = machine.ADC(9)                   
            adc_temp.atten(machine.ADC.ATTN_11DB)

            t_readings = [adc_temp.read_u16() for _ in range(8)]
            raw_temp = sum(t_readings) // len(t_readings)

            await debug_print(f"Raw temperature (u16 avg): {raw_temp}", "SOIL")

            temperature_c = (raw_temp / 65535.0) * 100.0 - 50.0
            temperature_c -= 16.666666666666668
            temperature_f = (temperature_c * 9 / 5) + 32

            await debug_print(f"Temperature: {temperature_c:.2f}°C ({temperature_f:.1f}°F)", "SOIL")
        except Exception as temp_e:
            await debug_print(f"Temperature sensor issue: {temp_e}", "ERROR")

        return {
            "status": "success",
            "moisture_percent": round(moisture_pct, 1),
            "raw_moisture": raw_moisture,
            "temperature_c": round(temperature_c, 2) if temperature_c is not None else None,
            "temperature_f": round(temperature_f, 1) if temperature_f is not None else None,
            "raw_temperature": raw_temp if 'raw_temp' in locals() else None
        }

    except Exception as e:
        await debug_print(f"Soil probe error: {e}", "ERROR")
        return {"status": "error", "message": str(e)}

# ===================== End of sampling.py =====================
