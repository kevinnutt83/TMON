# Firmware Version: v2.06.0

try:
    import uasyncio as asyncio
except Exception:
    asyncio = None

try:
    import network
except Exception:
    network = None

try:
    import urequests as requests
except Exception:
    requests = None

try:
    import gc
except Exception:
    gc = None

import settings

def _gc_collect():
    try:
        if gc:
            gc.collect()
    except Exception:
        pass

def _wlan():
    try:
        if not network:
            return None
        return network.WLAN(network.STA_IF)
    except Exception:
        return None

def disable_wifi():
    try:
        wlan = _wlan()
        if not wlan:
            return False
        wlan.active(False)
        return True
    except Exception:
        return False
    finally:
        _gc_collect()

async def connectToWifiNetwork():
    """Connect to WiFi using settings.WIFI_SSID/WIFI_PASS; returns bool."""
    if not bool(getattr(settings, 'ENABLE_WIFI', False)):
        return False
    wlan = _wlan()
    if not wlan:
        return False
    try:
        if not wlan.active():
            wlan.active(True)
    except Exception:
        try:
            wlan.active(True)
        except Exception:
            return False

    ssid = str(getattr(settings, 'WIFI_SSID', '') or '')
    pwd = str(getattr(settings, 'WIFI_PASS', '') or '')
    if not ssid:
        return False

    try:
        if wlan.isconnected():
            return True
    except Exception:
        pass

    try:
        wlan.connect(ssid, pwd)
    except Exception:
        return False

    retries = int(getattr(settings, 'WIFI_CONN_RETRIES', 20))
    backoff_s = int(getattr(settings, 'WIFI_BACKOFF_S', 1))
    for _ in range(retries):
        try:
            if wlan.isconnected():
                _gc_collect()
                return True
        except Exception:
            pass
        if asyncio:
            await asyncio.sleep(backoff_s)
        else:
            break
    _gc_collect()
    return False

async def check_internet_connection(url=None):
    """Best-effort internet test (HEAD/GET) used during boot/provision."""
    if not requests:
        return False
    test_url = url or str(getattr(settings, 'INTERNET_TEST_URL', 'https://example.com') or 'https://example.com')
    r = None
    try:
        try:
            r = requests.get(test_url, timeout=6)
        except TypeError:
            r = requests.get(test_url)
        return bool(r) and getattr(r, 'status_code', 0) in (200, 301, 302, 204)
    except Exception:
        return False
    finally:
        try:
            if r:
                r.close()
        except Exception:
            pass
        _gc_collect()
        if asyncio:
            await asyncio.sleep(0)

async def wifi_rssi_monitor():
    """Periodic RSSI sample into sdata.wifi_rssi."""
    try:
        import sdata
    except Exception:
        sdata = None
    interval = int(getattr(settings, 'WIFI_SIGNAL_SAMPLE_INTERVAL_S', 10))
    while True:
        try:
            wlan = _wlan()
            if wlan and sdata:
                try:
                    if wlan.isconnected():
                        # MicroPython ports vary: WLAN.status('rssi') exists on ESP32
                        try:
                            sdata.wifi_rssi = int(wlan.status('rssi'))
                        except Exception:
                            pass
                    else:
                        sdata.wifi_rssi = 0
                except Exception:
                    pass
        finally:
            _gc_collect()
        if asyncio:
            await asyncio.sleep(interval)
        else:
            break