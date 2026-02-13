# Firmware Version: v2.06.0

from platform_compat import asyncio, time, os, gc, requests, machine, network, IS_ZERO, IS_MICROPYTHON  # CHANGED

# CHANGED: import-safe settings/sdata
try:
	import settings  # type: ignore
except Exception:
	settings = None  # type: ignore
try:
	import sdata  # type: ignore
except Exception:
	sdata = None  # type: ignore

# CHANGED: ujson/ubinascii/uhashlib fallbacks
try:
	import ujson as ujson  # type: ignore
except Exception:
	import json as ujson  # type: ignore
try:
	import ubinascii as ubinascii  # type: ignore
except Exception:
	import binascii as ubinascii  # type: ignore
try:
	import uhashlib as uhashlib  # type: ignore
except Exception:
	import hashlib as uhashlib  # type: ignore

# CHANGED: SX1262 driver import (MicroPython)
try:
	from sx1262 import SX1262  # type: ignore
except Exception:
	try:
		from lib.sx1262 import SX1262  # type: ignore
	except Exception:
		SX1262 = None  # type: ignore

# CHANGED: utilities are optional on Zero; provide safe fallbacks
try:
	from utils import (
		free_pins,
		debug_print,
		TMON_AI,
		led_status_flash,
		write_lora_log,
		append_field_data_entry,
		stage_remote_field_data,
		stage_remote_files,
	)
except Exception:
	TMON_AI = None  # type: ignore

	async def debug_print(msg, tag="DEBUG"):
		try:
			print(f"[{tag}] {msg}")
		except Exception:
			pass

	async def free_pins():
		return None

	def led_status_flash(*a, **k):
		return None

	def write_lora_log(*a, **k):
		return None

	def append_field_data_entry(*a, **k):
		return None

	def stage_remote_field_data(*a, **k):
		return None

	def stage_remote_files(*a, **k):
		return None

_LOG_DIR = (getattr(settings, "LOG_DIR", "/logs") if settings else "/logs")
ERROR_LOG_FILE = (getattr(settings, "ERROR_LOG_FILE", _LOG_DIR + "/lora_errors.log") if settings else (_LOG_DIR + "/lora_errors.log"))

_file_lock = asyncio.Lock()
_pin_lock = asyncio.Lock()

async def log_error(error_msg):
	try:
		ts = int(time.time())
	except Exception:
		ts = 0
	line = f"{ts}: {error_msg}\n"
	try:
		async with _file_lock:
			with open(ERROR_LOG_FILE, "a") as f:
				f.write(line)
	except Exception:
		pass
	try:
		gc.collect()
	except Exception:
		pass

# CHANGED: Zero/CPython (or missing driver/settings): keep imports working, no hardware ops.
if IS_ZERO or (not IS_MICROPYTHON) or (settings is None) or (SX1262 is None):
	async def connectLora():
		return False

	__all__ = ["connectLora", "log_error", "TMON_AI"]

else:
	lora = None
	_last_send_ms = 0
	_last_activity_ms = 0

	# NEW: legacy remote info / sync schedule / GPS persistence
	REMOTE_NODE_INFO_FILE = _LOG_DIR + "/remote_node_info.json"
	REMOTE_SYNC_SCHEDULE_FILE = _LOG_DIR + "/remote_sync_schedule.json"
	GPS_STATE_FILE = _LOG_DIR + "/gps.json"

	def _load_json_file(path, default):
		try:
			with open(path, "r") as f:
				return ujson.loads(f.read())
		except Exception:
			return default

	def _save_json_file(path, obj):
		try:
			with open(path, "w") as f:
				f.write(ujson.dumps(obj))
		except Exception:
			pass

	def _load_remote_node_info():
		try:
			settings.REMOTE_NODE_INFO = _load_json_file(REMOTE_NODE_INFO_FILE, {})
		except Exception:
			settings.REMOTE_NODE_INFO = {}
		try:
			settings.REMOTE_SYNC_SCHEDULE = _load_json_file(REMOTE_SYNC_SCHEDULE_FILE, {})
		except Exception:
			settings.REMOTE_SYNC_SCHEDULE = {}
		try:
			gps = _load_json_file(GPS_STATE_FILE, {})
			if sdata is not None:
				sdata.gps_lat = gps.get("gps_lat")
				sdata.gps_lng = gps.get("gps_lng")
				sdata.gps_alt_m = gps.get("gps_alt_m")
				sdata.gps_accuracy_m = gps.get("gps_accuracy_m")
				sdata.gps_last_fix_ts = gps.get("gps_last_fix_ts")
			if getattr(settings, "GPS_OVERRIDE_ALLOWED", True):
				if "gps_lat" in gps: settings.GPS_LAT = gps.get("gps_lat")
				if "gps_lng" in gps: settings.GPS_LNG = gps.get("gps_lng")
				if "gps_alt_m" in gps: settings.GPS_ALT_M = gps.get("gps_alt_m")
				if "gps_accuracy_m" in gps: settings.GPS_ACCURACY_M = gps.get("gps_accuracy_m")
				if "gps_last_fix_ts" in gps: settings.GPS_LAST_FIX_TS = gps.get("gps_last_fix_ts")
		except Exception:
			pass

	def _save_remote_node_info():
		try:
			_save_json_file(REMOTE_NODE_INFO_FILE, getattr(settings, "REMOTE_NODE_INFO", {}) or {})
		except Exception:
			pass

	def _save_remote_sync_schedule():
		try:
			_save_json_file(REMOTE_SYNC_SCHEDULE_FILE, getattr(settings, "REMOTE_SYNC_SCHEDULE", {}) or {})
		except Exception:
			pass

	def _save_gps_state(lat=None, lng=None, alt=None, acc=None, ts=None):
		try:
			if sdata is not None:
				sdata.gps_lat = lat
				sdata.gps_lng = lng
				sdata.gps_alt_m = alt
				sdata.gps_accuracy_m = acc
				sdata.gps_last_fix_ts = ts
			if getattr(settings, "GPS_OVERRIDE_ALLOWED", True):
				if lat is not None: settings.GPS_LAT = lat
				if lng is not None: settings.GPS_LNG = lng
				if alt is not None: settings.GPS_ALT_M = alt
				if acc is not None: settings.GPS_ACCURACY_M = acc
				if ts is not None: settings.GPS_LAST_FIX_TS = ts
			_save_json_file(GPS_STATE_FILE, {
				"gps_lat": lat, "gps_lng": lng, "gps_alt_m": alt,
				"gps_accuracy_m": acc, "gps_last_fix_ts": ts
			})
		except Exception:
			pass

	# NEW: load persisted remote/GPS state at import
	try:
		_load_remote_node_info()
	except Exception:
		pass

	# NEW: base-side chunk reassembly store
	_lora_incoming_chunks = {}  # unit_id -> {"total": int, "parts": {seq: bytes}, "ts": epoch}

	def _cleanup_stale_chunks(max_age_s=3600):
		try:
			now = int(time.time())
			for uid in list(_lora_incoming_chunks.keys()):
				if now - int(_lora_incoming_chunks[uid].get("ts", now)) > max_age_s:
					del _lora_incoming_chunks[uid]
		except Exception:
			pass

	def _load_remote_counters():
		path = getattr(settings, "LORA_REMOTE_COUNTERS_FILE", _LOG_DIR + "/remote_ctr.json")
		return _load_json_file(path, {})

	def _save_remote_counters(ctrs):
		path = getattr(settings, "LORA_REMOTE_COUNTERS_FILE", _LOG_DIR + "/remote_ctr.json")
		_save_json_file(path, ctrs)

	def _hmac_verify(payload):
		try:
			if not getattr(settings, "LORA_HMAC_ENABLED", False):
				return True
			if "sig" not in payload:
				return not bool(getattr(settings, "LORA_HMAC_REJECT_UNSIGNED", True))
			secret = (getattr(settings, "LORA_HMAC_SECRET", "") or "").encode()
			ctr = payload.get("ctr", 0)
			src = b"|".join([
				secret,
				str(payload.get("unit_id", "")).encode(),
				str(payload.get("ts", "")).encode(),
				str(ctr).encode(),
			])
			h = uhashlib.sha256(src)
			expect = ubinascii.hexlify(h.digest())[:32].decode()
			if expect != payload.get("sig"):
				return False
			if getattr(settings, "LORA_HMAC_REPLAY_PROTECT", True):
				ctrs = _load_remote_counters()
				uid = str(payload.get("unit_id", "") or "")
				last = int(ctrs.get(uid, 0) or 0)
				if int(ctr) <= last:
					return False
				ctrs[uid] = int(ctr)
				_save_remote_counters(ctrs)
			return True
		except Exception:
			return False

	def _decrypt_payload_if_needed(payload):
		try:
			if not (isinstance(payload, dict) and payload.get("enc") == 1):
				return payload
			if _chacha20_decrypt is None:
				return None
			secret = (getattr(settings, "LORA_ENCRYPT_SECRET", "") or "").encode()
			key = (secret + b"\x00" * 32)[:32]
			nonce_hex = payload.get("nonce", "") or ""
			ct_hex = payload.get("ct", "") or ""
			try:
				nonce = ubinascii.unhexlify(nonce_hex)
				ct = ubinascii.unhexlify(ct_hex)
			except Exception:
				return None
			pt = _chacha20_decrypt(key, nonce, 1, ct)
			return ujson.loads(pt.decode("utf-8", "ignore"))
		except Exception:
			return None

	async def _send_ota_file_to_remote(remote_uid, file_path, sha256):
		try:
			if lora is None or _b64e is None:
				return False
			raw_chunk = int(getattr(settings, "LORA_CHUNK_RAW_BYTES", 80) or 80)
			size = os.stat(file_path)[6]
			total = (size // raw_chunk) + (1 if size % raw_chunk else 0)
			with open(file_path, "rb") as f:
				seq = 1
				chunk = f.read(raw_chunk)
				while chunk:
					b64 = _b64e(chunk).decode().strip()
					msg = {
						"ota_file": 1,
						"filename": os.path.basename(file_path),
						"sha": sha256,
						"seq": seq,
						"total": total,
						"b64": b64,
						"unit_id": remote_uid,
					}
					try:
						lora.setOperatingMode(lora.MODE_TX)
						lora.send(ujson.dumps(msg).encode("utf-8"))
					except Exception:
						return False
					await asyncio.sleep(0.1)
					seq += 1
					chunk = f.read(raw_chunk)
			return True
		except Exception:
			return False

	async def connectLora():
		"""
		Non-blocking LoRa routine called frequently from main.lora_comm_task().
		Preserves the core behavior:
		- base: RX and persist/stage remote payloads + ACK next_in
		- remote: TX telemetry and adopt next_in from ACK
		"""
		global lora, _last_send_ms

		if lora is None:
			async with _pin_lock:
				ok = await init_lora()
			if not ok:
				return False

		role = str(getattr(settings, "NODE_TYPE", "base")).lower()

		# Base RX path
		if role == "base":
			try:
				_cleanup_stale_chunks()
				rx_flag = getattr(SX1262, "RX_DONE", None)
				ev = 0
				try:
					ev = lora._events()
				except Exception:
					ev = 0
				if rx_flag is not None and (ev & rx_flag):
					msg, err = lora._readData(0)
					if err != 0 or not msg:
						return True
					txt = msg.decode("utf-8", "ignore") if isinstance(msg, (bytes, bytearray)) else str(msg)
					try:
						payload = ujson.loads(txt)
					except Exception:
						payload = {"raw": txt}

					# NEW: chunk reassembly
					if isinstance(payload, dict) and payload.get("chunked"):
						if _b64d is None:
							return True
						uid = str(payload.get("unit_id") or "unknown")
						seq = int(payload.get("seq", 1))
						total = int(payload.get("total", 1))
						b64 = payload.get("b64", "") or ""
						if not b64:
							return True
						raw = _b64d(b64)
						entry = _lora_incoming_chunks.get(uid, {"total": total, "parts": {}, "ts": int(time.time())})
						entry["total"] = total
						entry["parts"][seq] = raw
						entry["ts"] = int(time.time())
						_lora_incoming_chunks[uid] = entry
						if len(entry["parts"]) < entry["total"]:
							return True
						try:
							assembled = b"".join(entry["parts"][i] for i in range(1, entry["total"] + 1))
							payload = ujson.loads(assembled.decode("utf-8", "ignore"))
						except Exception:
							payload = {"raw": assembled.decode("utf-8", "ignore")}
						try:
							del _lora_incoming_chunks[uid]
						except Exception:
							pass

					# NEW: decrypt if needed
					payload = _decrypt_payload_if_needed(payload) or payload

					# NEW: HMAC verify + replay protect
					if not _hmac_verify(payload):
						await debug_print("lora: invalid or replayed signature", "ERROR")
						return True
					try:
						if "sig" in payload: payload.pop("sig", None)
						if "ctr" in payload: payload.pop("ctr", None)
					except Exception:
						pass

					uid = str(payload.get("unit_id", "") or "")
					if isinstance(payload, dict) and isinstance(payload.get("data"), list):
						stage_remote_field_data(uid, payload["data"])
					elif isinstance(payload, dict) and isinstance(payload.get("files"), dict):
						stage_remote_files(uid, payload["files"])
					else:
						rec = {
							"timestamp": int(time.time()),
							"remote_timestamp": payload.get("ts"),
							"cur_temp_f": payload.get("t_f"),
							"cur_temp_c": payload.get("t_c"),
							"cur_humid": payload.get("hum"),
							"cur_bar_pres": payload.get("bar"),
							"sys_voltage": payload.get("v"),
							"free_mem": payload.get("fm"),
							"remote_unit_id": uid,
							"node_type": "remote",
							"source": "remote",
						}
						append_field_data_entry(rec)

					# NEW: persist remote info + RSSI/SNR
					try:
						settings.REMOTE_NODE_INFO = getattr(settings, "REMOTE_NODE_INFO", {}) or {}
						settings.REMOTE_NODE_INFO[uid] = {
							"last_seen": int(time.time()),
							"last_payload": payload,
						}
						try:
							settings.REMOTE_NODE_INFO[uid]["last_rssi"] = lora.getRSSI()
							settings.REMOTE_NODE_INFO[uid]["last_snr"] = lora.getSNR()
						except Exception:
							pass
						_save_remote_node_info()
					except Exception:
						pass

					# ACK with next_in + optional GPS
					try:
						next_in = int(getattr(settings, "LORA_CHECK_IN_MINUTES", 5) * 60)
						if next_in < 60:
							next_in = 66
						ack = {"ack": "ok", "next_in": next_in}
						if getattr(settings, "GPS_BROADCAST_TO_REMOTES", False):
							ack["gps_lat"] = getattr(settings, "GPS_LAT", None)
							ack["gps_lng"] = getattr(settings, "GPS_LNG", None)
							ack["gps_alt_m"] = getattr(settings, "GPS_ALT_M", None)
							ack["gps_accuracy_m"] = getattr(settings, "GPS_ACCURACY_M", None)
							ack["gps_last_fix_ts"] = getattr(settings, "GPS_LAST_FIX_TS", None)

						# NEW: OTA job announcement (best-effort)
						try:
							if _poll_ota_jobs:
								for job in (await _poll_ota_jobs()) or []:
									if str(job.get("target")) == uid and job.get("type") == "firmware_update":
										ack["ota_pending"] = True
										ack["ota_filename"] = os.path.basename(job.get("url", ""))
										ack["ota_sha"] = job.get("sha")
										break
						except Exception:
							pass

						lora.setOperatingMode(lora.MODE_TX)
						lora.send(ujson.dumps(ack).encode("utf-8"))
						lora.setOperatingMode(lora.MODE_RX)
						try:
							if sdata is not None:
								sdata.lora_last_tx_ts = int(time.time())
						except Exception:
							pass

						# NEW: schedule tracking
						try:
							settings.REMOTE_SYNC_SCHEDULE = getattr(settings, "REMOTE_SYNC_SCHEDULE", {}) or {}
							settings.REMOTE_SYNC_SCHEDULE[uid] = {"next_expected": int(time.time() + next_in)}
							_save_remote_sync_schedule()
						except Exception:
							pass
					except Exception:
						try:
							lora.setOperatingMode(lora.MODE_RX)
						except Exception:
							pass

					# NEW: OTA file push after ACK (best-effort)
					try:
						if _poll_ota_jobs:
							for job in (await _poll_ota_jobs()) or []:
								if str(job.get("target")) == uid and job.get("type") == "firmware_update":
									path = job.get("local_path")
									sha = job.get("sha")
									if path and sha:
										await _send_ota_file_to_remote(uid, path, sha)
									break
					except Exception:
						pass
			except Exception as e:
				await debug_print(f"lora: base rx exception {e}", "ERROR")
				try:
					await log_error(f"base_rx: {e}")
				except Exception:
					pass
			finally:
				try:
					gc.collect()
				except Exception:
					pass
			return True

		# Remote TX path (restored chunking/encrypt/ack/GPS)
		if role == "remote":
			try:
				now_ms = time.ticks_ms()
				probe_interval_ms = 30 * 1000
				if _last_send_ms and time.ticks_diff(now_ms, _last_send_ms) < probe_interval_ms:
					return True

				payload = {
					"unit_id": getattr(settings, "UNIT_ID", ""),
					"name": getattr(settings, "UNIT_Name", ""),
					"ts": int(time.time()),
					"t_f": getattr(sdata, "cur_temp_f", 0) if sdata is not None else 0,
					"t_c": getattr(sdata, "cur_temp_c", 0) if sdata is not None else 0,
					"hum": getattr(sdata, "cur_humid", 0) if sdata is not None else 0,
					"bar": getattr(sdata, "cur_bar_pres", 0) if sdata is not None else 0,
					"v": getattr(sdata, "sys_voltage", 0) if sdata is not None else 0,
					"fm": getattr(sdata, "free_mem", 0) if sdata is not None else 0,
					"net": getattr(settings, "LORA_NETWORK_NAME", "tmon"),
					"key": getattr(settings, "LORA_NETWORK_PASSWORD", ""),
				}

				# HMAC attach
				if bool(getattr(settings, "LORA_HMAC_ENABLED", False)):
					ctr = _load_ctr() + 1
					_save_ctr(ctr)
					payload["ctr"] = ctr
					payload["sig"] = _hmac_sig(payload["unit_id"], payload["ts"], ctr)

				# Optional encryption
				if bool(getattr(settings, "LORA_ENCRYPT_ENABLED", False)) and _chacha20_encrypt and _derive_nonce:
					try:
						secret = (getattr(settings, "LORA_ENCRYPT_SECRET", "") or "").encode()
						key = (secret + b"\x00" * 32)[:32]
						nonce = _derive_nonce(int(time.time()), int(payload.get("ctr", 0)))
						pt = ujson.dumps(payload).encode("utf-8")
						ct = _chacha20_encrypt(key, nonce, 1, pt)
						payload = {
							"enc": 1,
							"nonce": ubinascii.hexlify(nonce).decode(),
							"ct": ubinascii.hexlify(ct).decode(),
							"net": payload.get("net"),
							"key": payload.get("key"),
						}
					except Exception:
						pass

				data = ujson.dumps(payload).encode("utf-8")
				max_payload = int(getattr(settings, "LORA_MAX_PAYLOAD", 255) or 255)

				# NEW: single-frame fast path
				if len(data) <= max_payload:
					retries = int(getattr(settings, "LORA_SINGLE_FRAME_RETRIES", 2))
					for _ in range(retries):
						try:
							lora.setOperatingMode(lora.MODE_TX)
							resp = lora.send(data)
							if int(resp) == 0:
								break
						except Exception:
							await asyncio.sleep(0.05)
					_last_send_ms = time.ticks_ms()
				else:
					# NEW: chunked send
					if _b64e is None:
						return True
					raw_chunk = int(getattr(settings, "LORA_CHUNK_RAW_BYTES", 80) or 80)
					parts = [data[i:i + raw_chunk] for i in range(0, len(data), raw_chunk)]
					total = len(parts)
					for seq, chunk in enumerate(parts, start=1):
						msg = {
							"unit_id": getattr(settings, "UNIT_ID", ""),
							"chunked": 1,
							"seq": seq,
							"total": total,
							"b64": _b64e(chunk).decode().strip(),
						}
						lora.setOperatingMode(lora.MODE_TX)
						lora.send(ujson.dumps(msg).encode("utf-8"))
						await asyncio.sleep(0.05)
					_last_send_ms = time.ticks_ms()

				# Wait briefly for ACK (next_in + GPS)
				try:
					lora.setOperatingMode(lora.MODE_RX)
				except Exception:
					pass
				ack_wait_ms = int(getattr(settings, "LORA_CHUNK_ACK_WAIT_MS", 1500))
				start = time.ticks_ms()
				rx_flag = getattr(SX1262, "RX_DONE", None)
				while time.ticks_diff(time.ticks_ms(), start) < ack_wait_ms:
					ev = 0
					try:
						ev = lora._events()
					except Exception:
						ev = 0
					if rx_flag is not None and (ev & rx_flag):
						msg, err = lora._readData(0)
						if err == 0 and msg:
							txt = msg.decode("utf-8", "ignore") if isinstance(msg, (bytes, bytearray)) else str(msg)
							try:
								obj = ujson.loads(txt)
							except Exception:
								obj = None
							if isinstance(obj, dict) and obj.get("ack") == "ok":
								if "next_in" in obj:
									rel = int(obj["next_in"])
									if rel < 60:
										rel = 60
									settings.nextLoraSync = int(time.time() + rel)
									try:
										with open(_LOG_DIR + "/remote_next_sync.json", "w") as f:
											f.write(ujson.dumps({"next": int(settings.nextLoraSync)}))
									except Exception:
										pass
								if getattr(settings, "GPS_ACCEPT_FROM_BASE", True):
									blat = obj.get("gps_lat"); blng = obj.get("gps_lng")
									if blat is not None and blng is not None:
										_save_gps_state(blat, blng, obj.get("gps_alt_m"), obj.get("gps_accuracy_m"), obj.get("gps_last_fix_ts"))
								break
					await asyncio.sleep(0.01)

			except Exception as e:
				await debug_print(f"lora: remote tx exception {e}", "ERROR")
				try:
					await log_error(f"remote_tx: {e}")
				except Exception:
					pass
			finally:
				try:
					gc.collect()
				except Exception:
					pass
			return True

		return True

	__all__ = ["connectLora", "log_error", "TMON_AI"]
