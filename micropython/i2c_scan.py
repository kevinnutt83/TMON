import machine
import utime
import gc

# Config
PIN_START = 1
PIN_END = 40  # inclusive
FREQS = (100_000, 400_000)  # Try standard and fast mode
LOG_FILE = "i2c_scan.log"
ONLY_LOG_SUCCESSES = True  # Reduce log noise on large scans
BREAK_ON_FIRST_FOUND = False  # Set True to stop after first successful combo


def now_str():
    try:
        y, m, d, hh, mm, ss, *_ = utime.localtime()
        return f"{y:04d}-{m:02d}-{d:02d} {hh:02d}:{mm:02d}:{ss:02d}"
    except Exception:
        return "0000-00-00 00:00:00"


def log_line(msg: str):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"[{now_str()}] {msg}\n")
    except Exception:
        # As a fallback, at least print it
        print(msg)


def try_scan_i2c(scl_pin: int, sda_pin: int):
    """Attempt to initialize I2C on the provided pins and return discovered devices.

    Tries SoftI2C when available first (more flexible pin mux), then falls back
    to hardware I2C controllers (IDs 0 and 1) if SoftI2C is unavailable.
    Returns (devices_list, info_dict) where info includes which backend was used
    and the frequency.
    """
    # Validate pins are constructible
    try:
        scl = machine.Pin(scl_pin)
        sda = machine.Pin(sda_pin)
    except Exception as e:
        if not ONLY_LOG_SUCCESSES:
            log_line(f"Pin error: SCL={scl_pin}, SDA={sda_pin}: {e}")
        return [], {"backend": None, "freq": None}

    # Try SoftI2C first if available
    if hasattr(machine, "SoftI2C"):
        for freq in FREQS:
            i2c = None
            try:
                i2c = machine.SoftI2C(scl=scl, sda=sda, freq=freq)
                devices = i2c.scan()
                return devices, {"backend": "SoftI2C", "freq": freq}
            except Exception as e:
                if not ONLY_LOG_SUCCESSES:
                    log_line(f"SoftI2C init/scan failed SCL={scl_pin}, SDA={sda_pin}, freq={freq}: {e}")
            finally:
                try:
                    if i2c and hasattr(i2c, "deinit"):
                        i2c.deinit()
                except Exception:
                    pass

    # Fallback to hardware I2C buses (common IDs 0 and 1)
    for bus_id in (0, 1):
        for freq in FREQS:
            i2c = None
            try:
                i2c = machine.I2C(bus_id, scl=scl, sda=sda, freq=freq)
                devices = i2c.scan()
                return devices, {"backend": f"I2C({bus_id})", "freq": freq}
            except Exception as e:
                if not ONLY_LOG_SUCCESSES:
                    log_line(
                        f"I2C({bus_id}) init/scan failed SCL={scl_pin}, SDA={sda_pin}, freq={freq}: {e}"
                    )
            finally:
                try:
                    if i2c and hasattr(i2c, "deinit"):
                        i2c.deinit()
                except Exception:
                    pass

    return [], {"backend": None, "freq": None}


def main():
    pins_to_scan = range(PIN_START, PIN_END + 1)
    header = f"Starting I2C scan on pin range {PIN_START}-{PIN_END} (SCL!=SDA)."
    print(header)
    log_line(header)

    total_attempts = 0
    found_count = 0
    start_ms = utime.ticks_ms()

    for scl_pin in pins_to_scan:
        for sda_pin in pins_to_scan:
            if scl_pin == sda_pin:
                continue

            total_attempts += 1
            devices, meta = try_scan_i2c(scl_pin, sda_pin)

            if devices:
                found_count += 1
                addr_str = ", ".join(f"0x{d:02X}" for d in devices)
                msg = (
                    f"FOUND: SCL={scl_pin}, SDA={sda_pin}, backend={meta['backend']}, "
                    f"freq={meta['freq']} -> addr(s): {addr_str}"
                )
                print(msg)
                log_line(msg)

                if BREAK_ON_FIRST_FOUND:
                    elapsed = utime.ticks_diff(utime.ticks_ms(), start_ms)
                    summary = f"Stopped after first find. Attempts={total_attempts}, time={elapsed} ms"
                    print(summary)
                    log_line(summary)
                    return

            # Give scheduler/GC a chance; scanning many combos can be heavy
            if (total_attempts % 10) == 0:
                gc.collect()
                utime.sleep_ms(5)

    elapsed = utime.ticks_diff(utime.ticks_ms(), start_ms)
    summary = (
        f"Scan complete. Attempts={total_attempts}, combos_found={found_count}, "
        f"duration={elapsed} ms. Log: {LOG_FILE}"
    )
    print(summary)
    log_line(summary)


if __name__ == "__main__":
    main()
