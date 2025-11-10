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

async def connectToWifiNetwork():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        await debug_print("Scanning for networks...", "WIFI")
        available_networks = wlan.scan()
        for ssid, *_ in available_networks:
            if ssid.decode() == settings.WIFI_SSID:
                await debug_print(f"Network {settings.WIFI_SSID} found, connecting...", "WIFI")
                wlan.connect(settings.WIFI_SSID, settings.WIFI_PASS)
                timeout = 10  # seconds
                start_time = time.time()
                while not wlan.isconnected():
                    if time.time() - start_time > timeout:
                        await debug_print("Connection timed out.", "WARN")
                        return
                    await asyncio.sleep(1)
                await debug_print("Connected.", "WIFI")
                sdata.WIFI_CONNECTED = True
                try:
                    settings.net_wifi_MAC = wlan.config('mac')
                    settings.net_wifi_IP = wlan.ifconfig()[0]
                    await debug_print(f"IP: {settings.net_wifi_IP}, MAC: {settings.net_wifi_MAC}", "WIFI") 
                except Exception as e:
                    await debug_print(f"Error obtaining network details: {e}", "ERROR")
                return
        await debug_print("Network not found, scanning again...", "WARN")
    else:
        await debug_print("Already connected.", "WIFI")
    sdata.WIFI_CONNECTED = True
    # Capture RSSI if available
    try:
        rssi = None
        try:
            rssi = wlan.status('rssi')
        except Exception:
            pass
        if rssi is None:
            try:
                rssi = wlan.config('rssi')
            except Exception:
                rssi = 0
        sdata.wifi_rssi = rssi if isinstance(rssi, int) else 0
    except Exception:
        sdata.wifi_rssi = 0

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