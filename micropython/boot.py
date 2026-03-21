# TMON v2.01.0 - Boot sequence
# Resilient boot with OLED feedback, persisted remote sync time, and conditional WiFi.
# LoRa/CLI readiness prepared. No blocking operations.

from wifi import connectToWifiNetwork
import settings
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

    # Only connect to WiFi when enabled. For remotes, allow connect if not yet provisioned.
    try:
        node_type = getattr(settings, 'NODE_TYPE', None)
        enabled = getattr(settings, 'ENABLE_WIFI', False)
        allow_remote_wifi_if_unprovisioned = bool(getattr(settings, 'WIFI_ALWAYS_ON_WHEN_UNPROVISIONED', True))
        should_connect = False
        if enabled:
            if node_type != 'remote':
                should_connect = True
            else:
                if not getattr(settings, 'UNIT_PROVISIONED', False) and allow_remote_wifi_if_unprovisioned:
                    should_connect = True
        if should_connect:
            await connectToWifiNetwork()
    except Exception:
        pass

asyncio.run(boot())
