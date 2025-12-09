# Firmware Version: 2.0.0h

import utime as time
import settings
import network
import uasyncio as asyncio
import urequests
import gc
from utils import runGC, debug_print
import sdata

gc.enable()

from settings import FIELD_DATA_APP_PASS

if not FIELD_DATA_APP_PASS:
    # Skip auth-required flows or log a warning; prevents boot-time NameError
    pass

def _should_attempt_connect():
    # If remote node and provisioned, and policy disables WiFi, don't attempt
    try:
        if getattr(settings, 'NODE_TYPE', 'base') == 'remote' and getattr(settings, 'UNIT_PROVISIONED', False):
            if getattr(settings, 'WIFI_DISABLE_AFTER_PROVISION', True):
                return False
    except Exception:
        pass
    return getattr(settings, 'ENABLE_WIFI', True)

def _refresh_rssi(wlan):
    try:
        rssi = None
        try:
            rssi = wlan.status('rssi')
        except Exception:
            try:
                rssi = wlan.config('rssi')
            except Exception:
                rssi = 0
        sdata.wifi_rssi = rssi if isinstance(rssi, int) else 0
    except Exception:
        sdata.wifi_rssi = 0

async def connectToWifiNetwork():
    if not _should_attempt_connect():
        try:
            wlan = network.WLAN(network.STA_IF)
            wlan.active(False)
        except Exception:
            pass
        sdata.WIFI_CONNECTED = False
        return
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        _refresh_rssi(wlan)
        sdata.WIFI_CONNECTED = True
        await debug_print("Already connected.", "WIFI")
        return
    await debug_print("Scanning for networks...", "WIFI")
    try:
        available_networks = wlan.scan()
    except Exception:
        available_networks = []
    target_found = False
    for ssid, *_ in available_networks:
        try:
            if ssid.decode() == settings.WIFI_SSID:
                target_found = True
                break
        except Exception:
            pass
    if not target_found:
        await debug_print("Target SSID not found.", "WARN")
        return
    await debug_print(f"Network {settings.WIFI_SSID} found, connecting...", "WIFI")
    retries = int(getattr(settings, 'WIFI_CONN_RETRIES', 5))
    backoff = int(getattr(settings, 'WIFI_BACKOFF_S', 15))
    for attempt in range(1, retries + 1):
        try:
            wlan.connect(settings.WIFI_SSID, settings.WIFI_PASS)
            timeout = 10
            start_time = time.time()
            while not wlan.isconnected():
                if time.time() - start_time > timeout:
                    break
                await asyncio.sleep(1)
            if wlan.isconnected():
                await debug_print("Connected.", "WIFI")
                sdata.WIFI_CONNECTED = True
                try:
                    settings.net_wifi_MAC = wlan.config('mac')
                    settings.net_wifi_IP = wlan.ifconfig()[0]
                    await debug_print(f"IP: {settings.net_wifi_IP}, MAC: {settings.net_wifi_MAC}", "WIFI")
                except Exception as e:
                    await debug_print(f"Error obtaining network details: {e}", "ERROR")
                _refresh_rssi(wlan)
                return
            else:
                await debug_print(f"WiFi attempt {attempt}/{retries} timed out.", "WARN")
        except Exception as e:
            await debug_print(f"WiFi error on attempt {attempt}: {e}", "ERROR")
        # backoff between attempts
        await asyncio.sleep(backoff)
    # all attempts failed
    sdata.WIFI_CONNECTED = False
    await debug_print("Failed to connect to WiFi after retries.", "ERROR")

async def scanToWifiNetwork():
    await debug_print("This is was called in place of scanning for wifi network...shhhh, don't tell anyone", "DEBUG")
    drawLCDNetworkStatus()
    await asyncio.sleep(0)

async def showNetworkWIFI():
    await debug_print("This is was called in place of displaying network iformation...shhhh, don't tell anyone", "DEBUG")
    await asyncio.sleep(0)

async def check_internet_connection():
    try:
        response = urequests.get("http://www.google.com")
        if response.status_code == 200:
            sdata.WAN_CONNECTED = True
            await debug_print("Internet access verified.", "WIFI")
        else:
            await debug_print("Connected to WiFi but no internet access.", "WARN")
            await runGC()
    except:
        await debug_print("Failed to connect to the internet.", "ERROR")
    await asyncio.sleep(0)

def disable_wifi():
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(False)
    except Exception:
        pass
    sdata.WIFI_CONNECTED = False

async def wifi_rssi_monitor():
    """Periodic RSSI sampler for OLED display and telemetry."""
    interval = int(getattr(settings, 'WIFI_SIGNAL_SAMPLE_INTERVAL_S', 30))
    while True:
        try:
            wlan = network.WLAN(network.STA_IF)
            if wlan.isconnected():
                _refresh_rssi(wlan)
                sdata.WIFI_CONNECTED = True
            else:
                sdata.WIFI_CONNECTED = False
        except Exception:
            sdata.WIFI_CONNECTED = False
        await asyncio.sleep(interval)