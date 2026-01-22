# Firmware Version: v2.06.0

import utime as time
import network
import uasyncio as asyncio
import urequests
import gc
import sdata

gc.enable()

# --- GC: best-effort cleanup after module import / heavy init ---
try:
    import gc
    gc.collect()
except Exception:
    pass

# Inserted: lazy settings accessor must exist before use
_settings_mod = None
def get_settings():
	# Return the real settings module or a safe proxy if import fails.
	global _settings_mod
	if _settings_mod is not None:
		return _settings_mod
	try:
		import settings as _s
		_settings_mod = _s
		return _settings_mod
	except Exception:
		class _SettingsProxy:
			FIELD_DATA_APP_PASS = ""
			NODE_TYPE = 'base'
			UNIT_PROVISIONED = False
			WIFI_DISABLE_AFTER_PROVISION = False
			ENABLE_WIFI = True
			WIFI_SSID = ""
			WIFI_PASS = ""
			WIFI_CONN_RETRIES = 5
			WIFI_BACKOFF_S = 15
			WIFI_SIGNAL_SAMPLE_INTERVAL_S = 30
			net_wifi_MAC = None
			net_wifi_IP = None
		_settings_mod = _SettingsProxy()
		return _settings_mod

# Lazy settings accessor and bootstrap remain as implemented.

# 1) Ensure settings has FIELD_DATA_APP_PASS before importing utils (which imports settings)
_s = get_settings()
try:
	getattr(_s, 'FIELD_DATA_APP_PASS')
except Exception:
	# Declare with safe default; real value will override later when persisted config loads.
	setattr(_s, 'FIELD_DATA_APP_PASS', "")

# 2) Import utils after bootstrap; provide safe fallbacks if import fails
try:
	from utils import runGC, debug_print
except Exception:
	async def debug_print(msg, tag="DEBUG"):
		try:
			print("[{}] {}".format(tag, msg))
		except Exception:
			pass
	async def runGC():
		try:
			gc.collect()
		except Exception:
			pass

# Use getattr to avoid NameError when settings initializes later.
FIELD_DATA_APP_PASS = getattr(get_settings(), 'FIELD_DATA_APP_PASS', '')
if not FIELD_DATA_APP_PASS:
	# Skip auth-required flows or log a warning; prevents boot-time NameError
	pass

def _should_attempt_connect():
	# If node is remote, allow WiFi when unprovisioned and policy allows it; otherwise avoid WiFi for provisioned remotes.
	s = get_settings()
	try:
		node_type = getattr(s, 'NODE_TYPE', 'base')
		# Remote devices: permit WiFi if they are NOT yet provisioned and WIFI_ALWAYS_ON_WHEN_UNPROVISIONED is True
		if node_type == 'remote':
			if not bool(getattr(s, 'UNIT_PROVISIONED', False)) and bool(getattr(s, 'WIFI_ALWAYS_ON_WHEN_UNPROVISIONED', True)):
				return getattr(s, 'ENABLE_WIFI', True)
			# otherwise do not attempt WiFi for provisioned remotes
			return False
		# Non-remote: use global ENABLE_WIFI flag
	except Exception:
		pass
	return getattr(s, 'ENABLE_WIFI', True)

def _refresh_rssi(wlan):
	# ...existing code...
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
	s = get_settings()
	# Enforce explicit early return for remote nodes
	if getattr(s, 'NODE_TYPE', 'base') == 'remote':
		try:
			wlan = network.WLAN(network.STA_IF)
			wlan.active(False)
		except Exception:
			pass
		sdata.WIFI_CONNECTED = False
		return False
	if not _should_attempt_connect():
		try:
			wlan = network.WLAN(network.STA_IF)
			wlan.active(False)
		except Exception:
			pass
		sdata.WIFI_CONNECTED = False
		return False
	wlan = network.WLAN(network.STA_IF)
	wlan.active(True)
	if wlan.isconnected():
		_refresh_rssi(wlan)
		sdata.WIFI_CONNECTED = True
		await debug_print("wifi: already connected", "WIFI")
		# Friendly OLED notice
		try:
			from oled import display_message
			await display_message("WiFi Connected", 1.5)
		except Exception:
			pass
		return True
	await debug_print("wifi: scanning", "WIFI")
	try:
		available_networks = wlan.scan()
	except Exception:
		available_networks = []
	target_found = False
	for ssid, *_ in available_networks:
		try:
			if ssid.decode() == getattr(s, 'WIFI_SSID', ""):
				target_found = True
				break
		except Exception:
			pass
	if not target_found:
		await debug_print("wifi: ssid not found", "WARN")
		try:
			from oled import display_message
			await display_message("SSID Not Found", 2)
		except Exception:
			pass
		return
	await debug_print(f"wifi: connect {getattr(s, 'WIFI_SSID', '')}", "WIFI")
	retries = int(getattr(s, 'WIFI_CONN_RETRIES', 5))
	backoff = int(getattr(s, 'WIFI_BACKOFF_S', 15))
	for attempt in range(1, retries + 1):
		try:
			wlan.connect(getattr(s, 'WIFI_SSID', ''), getattr(s, 'WIFI_PASS', ''))
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
					s.net_wifi_MAC = wlan.config('mac')
					s.net_wifi_IP = wlan.ifconfig()[0]
					await debug_print(f"IP: {s.net_wifi_IP}, MAC: {s.net_wifi_MAC}", "WIFI")
				except Exception as e:
					await debug_print(f"Error obtaining network details: {e}", "ERROR")
				_refresh_rssi(wlan)
				return True
			else:
				await debug_print(f"WiFi attempt {attempt}/{retries} timed out.", "WARN")
		except Exception as e:
			await debug_print(f"WiFi error on attempt {attempt}: {e}", "ERROR")
		# backoff between attempts
		await asyncio.sleep(backoff)
	# all attempts failed
	sdata.WIFI_CONNECTED = False
	await debug_print("wifi: connect failed", "ERROR")
	try:
		from oled import display_message
		await display_message("WiFi Failed", 2)
	except Exception:
		pass
	return False

async def scanToWifiNetwork():
	# Real scan implementation: return list of (ssid, channel, RSSI, authmode) tuples and show a brief OLED page
	try:
		wlan = network.WLAN(network.STA_IF)
		if not wlan.active():
			wlan.active(True)
		try:
			networks = wlan.scan()
		except Exception:
			networks = []
		# Sanitize results: (ssid, channel, RSSI, auth)
		clean = []
		for row in networks:
			try:
				ssid = row[0].decode() if isinstance(row[0], (bytes, bytearray)) else str(row[0])
				channel = row[2] if len(row) > 2 else 0
				rssi = row[3] if len(row) > 3 else None
				auth = row[4] if len(row) > 4 else None
				clean.append((ssid, channel, rssi, auth))
			except Exception:
				pass
		# Show a short OLED summary page if available
		try:
			from oled import display_message
			if clean:
				msg = "Found: " + ", ".join([n[0] for n in clean[:3]])
			else:
				msg = "No SSIDs"
			await display_message(msg, 1.5)
		except Exception:
			pass
		return clean
	except Exception as e:
		await debug_print(f"wifi: scan error {e}", "ERROR")
		return []

async def showNetworkWIFI():
	# Display current WiFi state (SSID / IP / MAC / RSSI) on OLED
	try:
		wlan = network.WLAN(network.STA_IF)
		if not wlan.active() or not wlan.isconnected():
			try:
				await display_message("WiFi: Not connected", 1.8)
			except Exception:
				pass
			return
		try:
			ssid = getattr(get_settings(), 'WIFI_SSID', '') or ''
		except Exception:
			ssid = ''
		ip = ''
		mac = ''
		rssi = None
		try:
			if wlan.isconnected():
				ip = wlan.ifconfig()[0]
				try:
					mac = ':'.join('{:02X}'.format(b) for b in wlan.config('mac'))
				except Exception:
					try:
						mac = str(wlan.config('mac'))
					except Exception:
						mac = ''
				# try rssi via .status or .config
				try:
					rssi = wlan.status('rssi')
				except Exception:
					try:
						rssi = wlan.config('rssi')
					except Exception:
						rssi = None
		except Exception:
			pass
		msg_lines = [f"SSID: {ssid}", f"IP: {ip}", f"MAC: {mac}", f"RSSI: {rssi}"]
		try:
			from oled import display_message
			await display_message("\n".join(msg_lines), 3)
		except Exception:
			# fallback to debug print
			await debug_print("wifi: " + ", ".join([l for l in msg_lines if l]), "WIFI")
	except Exception as e:
		await debug_print(f"showNetworkWIFI err: {e}", "ERROR")

async def check_internet_connection():
	# ...existing code...
	try:
		response = urequests.get("http://www.google.com")
		try:
			if response and getattr(response, 'status_code', 0) == 200:
				sdata.WAN_CONNECTED = True
				await debug_print("Internet access verified.", "WIFI")
				try:
					response.close()
				except Exception:
					pass
				return True
			else:
				await debug_print("Connected to WiFi but no internet access.", "WARN")
				await runGC()
				try:
					response.close()
				except Exception:
					pass
				return False
		except Exception:
			try:
				response.close()
			except Exception:
				pass
			await debug_print("Connected to WiFi but no internet access (response error).", "WARN")
			return False
	except Exception:
		await debug_print("Failed to connect to the internet.", "ERROR")
		return False
	finally:
		await asyncio.sleep(0)

def disable_wifi():
	# ...existing code...
	try:
		wlan = network.WLAN(network.STA_IF)
		wlan.active(False)
	except Exception:
		pass
	sdata.WIFI_CONNECTED = False

async def wifi_rssi_monitor():
	"""Periodic RSSI sampler for OLED display and telemetry."""
	s = get_settings()
	interval = int(getattr(s, 'WIFI_SIGNAL_SAMPLE_INTERVAL_S', 30))
	while True:
		try:
			if not getattr(s, 'ENABLE_WIFI', True):
				sdata.WIFI_CONNECTED = False
				sdata.wifi_rssi = None
				await asyncio.sleep(interval)
				continue
			wlan = network.WLAN(network.STA_IF)
			if wlan.isconnected():
				_refresh_rssi(wlan)
				sdata.WIFI_CONNECTED = True
			else:
				sdata.WIFI_CONNECTED = False
				sdata.wifi_rssi = None
		except Exception:
			sdata.WIFI_CONNECTED = False
			sdata.wifi_rssi = None
		await asyncio.sleep(interval)