from platform_compat import asyncio, time, Pin, UART, IS_ZERO  # CHANGED
import struct
import settings
import sdata
from utils import debug_print

# Build UARTs lazily to allow re-init

def _build_uart(idx, tx_pin, rx_pin):
    # NEW: On Zero, UART is a stub unless you later wire a real backend; keep import/load safe.
    if IS_ZERO or UART is None or Pin is None:
        return None
    try:
        return UART(idx, baudrate=settings.COMM_BAUD, parity=settings.COMM_PARITY, stop=settings.COMM_STOP_BITS, tx=Pin(tx_pin), rx=Pin(rx_pin))
    except Exception as e:
        try:
            asyncio.create_task(debug_print(f"UART init failed ({idx}): {e}", "ERROR"))
        except Exception:
            pass
        return None

uart1 = _build_uart(1, settings.CH1_TX_PIN, settings.CH1_RX_PIN)
uart2 = _build_uart(2, settings.CH2_TX_PIN, settings.CH2_RX_PIN)


def calculate_crc(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc


def _read_holding(uart, dev_addr, start_addr, num_regs):
    if not uart:
        return None
    try:
        request = struct.pack('>BBHH', dev_addr, 3, start_addr, num_regs)
        crc = calculate_crc(request)
        request += struct.pack('<H', crc)
        uart.write(request)
        time.sleep_ms(100)

        response = bytearray()
        start_time = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start_time) < 1000:
            if uart.any():
                response.extend(uart.read())
                break

        expected_length = 5 + 2 * num_regs
        if len(response) < expected_length:
            return None

        _, _, byteCount = struct.unpack('>BBB', response[:3])
        return struct.unpack('>' + 'H' * (byteCount // 2), response[3:])
    except Exception:
        return None


def _write_single_coil(uart, dev_addr, coil_addr, turn_on):
    if not uart:
        return False
    try:
        payload = struct.pack('>BBHH', dev_addr, 5, coil_addr, 0xFF00 if turn_on else 0x0000)
        crc = calculate_crc(payload)
        payload += struct.pack('<H', crc)
        uart.write(payload)
        time.sleep_ms(100)
        return True
    except Exception:
        return False


async def poll_engine(dev_idx):
    if getattr(settings, 'ENGINE_FORCE_DISABLED', False):
        return {}
    if not settings.ENABLE_RS485 or not settings.ENABLE_ENGINE_CONTROLLER:
        return {}
    dev_addr = settings.ENGINE_DEV_ADDR + dev_idx
    uart_a = uart1
    uart_b = uart2
    stats = {}
    # Engine speed register 0, battery voltage register 3
    res_a = _read_holding(uart_a, dev_addr, 0, 4)
    if res_a:
        stats['engine_speed_ch1'] = res_a[0]
        stats['battery_voltage_ch1'] = res_a[3] / 10
        sdata.engine1_speed_rpm = res_a[0]
        sdata.engine1_batt_v = res_a[3] / 10
    res_b = _read_holding(uart_b, dev_addr, 0, 4)
    if res_b:
        stats['engine_speed_ch2'] = res_b[0]
        stats['battery_voltage_ch2'] = res_b[3] / 10
        sdata.engine2_speed_rpm = res_b[0]
        sdata.engine2_batt_v = res_b[3] / 10
    sdata.engine_last_poll_ts = time.time()
    return stats


async def start_pump(channel, pump_number):
    if getattr(settings, 'ENGINE_FORCE_DISABLED', False):
        return
    if not settings.ENABLE_RS485 or not settings.ENABLE_ENGINE_CONTROLLER:
        return
    coil = settings.ENGINE_PUMP1_COIL if pump_number == 1 else settings.ENGINE_PUMP2_COIL
    uart = uart1 if channel == 1 else uart2
    _write_single_coil(uart, settings.ENGINE_DEV_ADDR, coil, True)


async def stop_pump(channel, pump_number):
    if getattr(settings, 'ENGINE_FORCE_DISABLED', False):
        return
    if not settings.ENABLE_RS485 or not settings.ENABLE_ENGINE_CONTROLLER:
        return
    coil = settings.ENGINE_PUMP1_COIL if pump_number == 1 else settings.ENGINE_PUMP2_COIL
    uart = uart1 if channel == 1 else uart2
    _write_single_coil(uart, settings.ENGINE_DEV_ADDR, coil, False)


async def reset_rs485():
    if getattr(settings, 'ENGINE_FORCE_DISABLED', False):
        return
    if not settings.ENABLE_RS485:
        return
    global uart1, uart2
    try:
        uart1 = _build_uart(1, settings.CH1_TX_PIN, settings.CH1_RX_PIN)
        uart2 = _build_uart(2, settings.CH2_TX_PIN, settings.CH2_RX_PIN)
        await debug_print("RS485 reset", "debugRS485")
    except Exception:
        pass


async def engine_loop():
    if getattr(settings, 'ENGINE_FORCE_DISABLED', False):
        await asyncio.sleep(5)
        return
    if not settings.ENABLE_RS485 or not settings.ENABLE_ENGINE_CONTROLLER:
        await asyncio.sleep(5)
        return
    while True:
        try:
            for devIdx in range(settings.ENGINE_DEV_COUNT):
                await poll_engine(devIdx)
            await asyncio.sleep(settings.ENGINE_POLL_INTERVAL_S)
        except Exception as e:
            try:
                await debug_print(f"engine_loop error: {e}", "ERROR")
            except Exception:
                pass
            await asyncio.sleep(settings.ENGINE_POLL_INTERVAL_S)