# Firmware Version: v.2.00i
# This file is executed on every boot (including wake-boot from deepsleep)
# import esp
# esp.osdebug(None)
# import webrepl
# webrepl.start()

from wifi import connectToWifiNetwork
import settings
from utils import flash_led
import uasyncio as asyncio
from oled import display_message

async def boot():
    fw_msg = f"Firmware: {settings.FIRMWARE_VERSION}"
    await display_message(fw_msg, 2)
    print(fw_msg)
    await display_message("Booting TMON Device", 3)
    # If remote node, try to load persisted next sync time
    try:
        if getattr(settings, 'NODE_TYPE', None) == 'remote':
            import ujson, os
            path = settings.LOG_DIR + '/remote_next_sync.json'
            try:
                os.stat(path)
                with open(path, 'r') as f:
                    obj = ujson.load(f)
                    if 'next' in obj:
                        settings.nextLoraSync = int(obj['next'])
            except OSError:
                pass
    except Exception:
        pass
    # Only connect to WiFi if NODE_TYPE is not 'remote' and ENABLE_WIFI is True
    if getattr(settings, 'NODE_TYPE', None) != 'remote' and getattr(settings, 'ENABLE_WIFI', False):
        await connectToWifiNetwork()   

asyncio.run(boot())