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

	def _safe_pin_out(pin_num, value=1):
		try:
			p = machine.Pin(pin_num, machine.Pin.OUT)
			p.value(value)
			return p
		except Exception:
			return None

	def _safe_pin_input(pin_num):
		try:
			return machine.Pin(pin_num, machine.Pin.IN)
		except Exception:
			return None

	def _pulse_reset(pin_num, low_ms=50, post_high_ms=120):
		try:
			p = _safe_pin_out(pin_num, 0)
			time.sleep_ms(low_ms)
			if p:
				p.value(1)
			time.sleep_ms(post_high_ms)
		except Exception:
			try:
				time.sleep_ms(post_high_ms)
			except Exception:
				pass

	async def init_lora():
		global lora
		try:
			# Pins prep (preserve existing intent)
			try:
				_safe_pin_out(settings.CS_PIN, 1)
				_safe_pin_input(settings.BUSY_PIN)
				_safe_pin_input(settings.IRQ_PIN)
			except Exception:
				pass
			try:
				_pulse_reset(settings.RST_PIN, low_ms=50, post_high_ms=120)
			except Exception:
				pass

			lora = SX1262(
				settings.SPI_BUS,
				settings.CLK_PIN,
				settings.MOSI_PIN,
				settings.MISO_PIN,
				settings.CS_PIN,
				settings.IRQ_PIN,
				settings.RST_PIN,
				settings.BUSY_PIN,
			)

			status = lora.begin(
				freq=settings.FREQ,
				bw=settings.BW,
				sf=settings.SF,
				cr=settings.CR,
				syncWord=settings.SYNC_WORD,
				power=settings.POWER,
				currentLimit=settings.CURRENT_LIMIT,
				preambleLength=settings.PREAMBLE_LEN,
				implicit=False,
				implicitLen=0xFF,
				crcOn=settings.CRC_ON,
				txIq=False,
				rxIq=False,
				tcxoVoltage=settings.TCXO_VOLTAGE,
				useRegulatorLDO=settings.USE_LDO,
			)

			if status != 0:
				await debug_print(f"lora: begin failed status={status}", "ERROR")
				lora = None
				return False

			try:
				lora.setBlockingCallback(False)
			except Exception:
				pass

			# Base starts listening
			try:
				if str(getattr(settings, "NODE_TYPE", "base")).lower() == "base":
					lora.setOperatingMode(lora.MODE_RX)
			except Exception:
				pass

			await debug_print("lora: initialized", "LORA")
			return True
		except Exception as e:
			await debug_print(f"lora: init exception {e}", "ERROR")
			try:
				await log_error(f"init_lora: {e}")
			except Exception:
				pass
			lora = None
			return False
		finally:
			try:
				gc.collect()
			except Exception:
				pass

	def _load_ctr():
		path = getattr(settings, "LORA_HMAC_COUNTER_FILE", _LOG_DIR + "/lora_ctr.json")
		try:
			with open(path, "r") as f:
				obj = ujson.loads(f.read())
				return int(obj.get("ctr", 0))
		except Exception:
			return 0

	def _save_ctr(v):
		path = getattr(settings, "LORA_HMAC_COUNTER_FILE", _LOG_DIR + "/lora_ctr.json")
		try:
			with open(path, "w") as f:
				f.write(ujson.dumps({"ctr": int(v)}))
		except Exception:
			pass

	def _hmac_sig(unit_id, ts, ctr):
		try:
			secret = (getattr(settings, "LORA_HMAC_SECRET", "") or "").encode()
			mac_src = b"|".join([secret, str(unit_id).encode(), str(ts).encode(), str(ctr).encode()])
			h = uhashlib.sha256(mac_src)
			return ubinascii.hexlify(h.digest())[:32].decode()
		except Exception:
			return ""

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

					# ACK with next_in (preserves scheduling intent)
					try:
						next_in = int(getattr(settings, "LORA_CHECK_IN_MINUTES", 5) * 60)
						if next_in < 60:
							next_in = 60
						ack = {"ack": "ok", "next_in": next_in}
						lora.setOperatingMode(lora.MODE_TX)
						lora.send(ujson.dumps(ack).encode("utf-8"))
						lora.setOperatingMode(lora.MODE_RX)
						try:
							if sdata is not None:
								sdata.lora_last_tx_ts = int(time.time())
						except Exception:
							pass
					except Exception:
						try:
							lora.setOperatingMode(lora.MODE_RX)
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

		# Remote TX path (basic, bounded)
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

				# HMAC attach (preserve existing setting semantics)
				if bool(getattr(settings, "LORA_HMAC_ENABLED", False)):
					ctr = _load_ctr() + 1
					_save_ctr(ctr)
					payload["ctr"] = ctr
					payload["sig"] = _hmac_sig(payload["unit_id"], payload["ts"], ctr)

				data = ujson.dumps(payload).encode("utf-8")

				lora.setOperatingMode(lora.MODE_TX)
				lora.send(data)
				_last_send_ms = time.ticks_ms()

				# Wait briefly for ACK to adopt next sync
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
								try:
									if "next_in" in obj:
										rel = int(obj["next_in"])
										if rel < 60:
											rel = 60
										settings.nextLoraSync = int(time.time() + rel)
										# persist for boot.py (already reads /logs/remote_next_sync.json)
										try:
											with open(_LOG_DIR + "/remote_next_sync.json", "w") as f:
												f.write(ujson.dumps({"next": int(settings.nextLoraSync)}))
										except Exception:
											pass
								except Exception:
									pass
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
