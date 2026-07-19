# Remote node deep-sleep cycle runner for battery-powered LoRa remotes.

import gc
import machine
import settings
import uasyncio as asyncio
import utime as time

try:
    import random
except Exception:
    random = None

from sampling import sampleEnviroment
from lora import init_lora, ensure_lora_listening, wait_for_next_sync_ack
from utils import (
    debug_print,
    log_exception,
    load_next_lora_sync,
    persist_next_lora_sync,
    record_field_data,
    send_field_data_via_lora,
    update_sys_voltage,
)


def _safe_int(value, fallback):
    try:
        return int(value)
    except Exception:
        return fallback


def _now_epoch():
    try:
        return int(time.time())
    except Exception:
        return 0


def _compute_next_sync_epoch(now_epoch):
    persisted = load_next_lora_sync(default=None)
    guard_s = max(10, _safe_int(getattr(settings, 'LORA_SYNC_WINDOW', 2), 2))
    if isinstance(persisted, int) and persisted > (now_epoch + guard_s):
        return persisted

    sync_hint_s = _safe_int(getattr(settings, 'LORA_NEXT_SYNC', 0), 0)
    if sync_hint_s >= 30:
        interval_s = sync_hint_s
    else:
        interval_s = max(30, _safe_int(getattr(settings, 'LORA_SYNC_RATE', 300), 300))
    jitter_max_s = max(0, _safe_int(getattr(settings, 'LORA_SYNC_WINDOW', 2), 2))
    jitter_s = 0
    if random and jitter_max_s > 0:
        try:
            jitter_s = random.randint(0, jitter_max_s)
        except Exception:
            jitter_s = 0
    return now_epoch + interval_s + jitter_s


def _apply_voltage_adaptive_sleep(base_sleep_s, voltage_v):
    sleep_s = max(5, _safe_int(base_sleep_s, 60))
    if voltage_v is None:
        return sleep_s

    try:
        v = float(voltage_v)
    except Exception:
        return sleep_s

    low_v = float(getattr(settings, 'REMOTE_BATTERY_LOW_V', 3.45))
    crit_v = float(getattr(settings, 'REMOTE_BATTERY_CRITICAL_V', 3.30))
    low_mult = float(getattr(settings, 'REMOTE_SLEEP_MULTIPLIER_LOW', 1.5))
    crit_mult = float(getattr(settings, 'REMOTE_SLEEP_MULTIPLIER_CRITICAL', 3.0))

    if v <= crit_v:
        sleep_s = int(sleep_s * max(1.0, crit_mult))
    elif v <= low_v:
        sleep_s = int(sleep_s * max(1.0, low_mult))

    min_s = max(5, _safe_int(getattr(settings, 'REMOTE_DEEPSLEEP_MIN_S', 15), 15))
    max_s = max(min_s, _safe_int(getattr(settings, 'REMOTE_DEEPSLEEP_MAX_S', 1800), 1800))
    return min(max(sleep_s, min_s), max_s)


def _configure_ext_wake():
    pin_num = getattr(settings, 'REMOTE_EXT_WAKE_PIN', None)
    if pin_num is None:
        return False
    try:
        import esp32
        level = 1 if int(getattr(settings, 'REMOTE_EXT_WAKE_LEVEL', 0)) else 0
        pin = machine.Pin(int(pin_num), machine.Pin.IN)
        if hasattr(esp32, 'wake_on_ext0'):
            esp32.wake_on_ext0(pin=pin, level=level)
            return True
        if hasattr(esp32, 'wake_on_ext1'):
            pins_mask = 1 << int(pin_num)
            wake_mode = esp32.WAKEUP_ANY_HIGH if level else esp32.WAKEUP_ALL_LOW
            esp32.wake_on_ext1(pins=pins_mask, level=wake_mode)
            return True
    except Exception:
        return False
    return False


def _is_external_wake_event():
    try:
        reason = machine.wake_reason()
    except Exception:
        return False
    try:
        known = (
            getattr(machine, 'PIN_WAKE', None),
            getattr(machine, 'EXT0_WAKE', None),
            getattr(machine, 'EXT1_WAKE', None),
        )
        if reason in known:
            return True
    except Exception:
        pass
    try:
        reason_text = str(reason).upper()
        return ('PIN' in reason_text) or ('EXT' in reason_text)
    except Exception:
        return False


async def _run_remote_cycle_once():
    try:
        from wifi import disable_wifi
        disable_wifi()
    except Exception:
        pass

    await sampleEnviroment()
    record_field_data()

    if not await init_lora():
        raise RuntimeError('remote_sleep: LoRa init failed')
    await ensure_lora_listening()
    await send_field_data_via_lora()

    now_epoch = _now_epoch()
    ack_wait_s = max(2, _safe_int(getattr(settings, 'REMOTE_ACK_WAIT_S', 8), 8))
    next_delay = await wait_for_next_sync_ack(timeout_s=ack_wait_s)
    if isinstance(next_delay, int) and next_delay > 0:
        next_epoch = now_epoch + next_delay
        await debug_print(f"remote_sleep: ACK next delay {next_delay}s", "REMOTE_NODE")
    else:
        next_epoch = _compute_next_sync_epoch(now_epoch)
    persist_next_lora_sync(next_epoch)

    sleep_s = max(15, next_epoch - now_epoch)
    sys_v = update_sys_voltage()
    sleep_s = _apply_voltage_adaptive_sleep(sleep_s, sys_v)
    await debug_print(f"remote_sleep: next wake in {sleep_s}s", "REMOTE_NODE")
    return sleep_s


def run_remote_deep_sleep():
    sleep_s = max(30, _safe_int(getattr(settings, 'LORA_SYNC_RATE', 300), 300))
    try:
        sleep_s = _safe_int(asyncio.run(_run_remote_cycle_once()), sleep_s)
    except Exception as exc:
        try:
            asyncio.run(log_exception('remote_node.run_remote_deep_sleep', exc))
        except Exception:
            pass
        retry_base = max(30, _safe_int(getattr(settings, 'LORA_RETRY_BASE_DELAY_S', 2), 2) * 10)
        sleep_s = retry_base

    try:
        gc.collect()
    except Exception:
        pass

    ext_cfg = _configure_ext_wake()
    if ext_cfg:
        try:
            asyncio.run(debug_print("remote_sleep: EXT wake configured", "REMOTE_NODE"))
        except Exception:
            pass

    if _is_external_wake_event() and bool(getattr(settings, 'REMOTE_EXT_WAKE_RECOVERY_DISABLE_SLEEP', False)):
        try:
            asyncio.run(debug_print("remote_sleep: external wake recovery mode active; skipping deepsleep", "WARN"))
        except Exception:
            pass
        while True:
            time.sleep(5)

    try:
        machine.deepsleep(int(max(5, sleep_s) * 1000))
    except Exception:
        while True:
            time.sleep(5)
