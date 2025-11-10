import machine
import utime
import gc

# Standalone configuration
# Adjust these as needed for your board
PIN_START = 8
PIN_END = 9  # inclusive
FREQS = (100_000, 400_000)  # standard and fast mode
BREAK_ON_FIRST_FOUND = False  # stop early if you just need the first hit


BME280_ADDRESSES = (0x76, 0x77)
BME280_CHIP_ID_REG = 0xD0
EXPECTED_CHIP_ID = 0x60


def try_i2c_instance(backend: str, scl_pin: int, sda_pin: int, freq: int, bus_id: int = None):
    """Create an I2C instance for the given backend. Returns (i2c, err_msg)."""
    try:
        scl = machine.Pin(scl_pin)
        sda = machine.Pin(sda_pin)
    except Exception as e:
        return None, f"Pin construct failed: SCL={scl_pin}, SDA={sda_pin}: {e}"

    try:
        if backend == "SoftI2C" and hasattr(machine, "SoftI2C"):
            i2c = machine.SoftI2C(scl=scl, sda=sda, freq=freq)
            return i2c, None
        elif backend.startswith("I2C("):
            assert bus_id is not None
            i2c = machine.I2C(bus_id, scl=scl, sda=sda, freq=freq)
            return i2c, None
        else:
            return None, f"Unsupported backend {backend}"
    except Exception as e:
        return None, f"I2C init failed [{backend}] freq={freq}: {e}"


def probe_bme280(i2c, address: int):
    """Probe BME280 by reading chip ID register; return (ok, chip_id_or_err)."""
    try:
        data = i2c.readfrom_mem(address, BME280_CHIP_ID_REG, 1)
        chip_id = data[0] if data and len(data) else None
        return (chip_id == EXPECTED_CHIP_ID), chip_id
    except Exception as e:
        return False, e


def main():
    start_ms = utime.ticks_ms()
    found = []  # list of dicts
    total_attempts = 0

    print(
        f"Starting BME280 pin/address scan over SCL/SDA pins {PIN_START}..{PIN_END}"
    )
    print(f"Frequencies: {list(FREQS)}; Backends: ['SoftI2C', 'I2C(0)', 'I2C(1)']")
    print(f"Candidate addresses: {[hex(a) for a in BME280_ADDRESSES]}")

    for scl_pin in range(PIN_START, PIN_END + 1):
        for sda_pin in range(PIN_START, PIN_END + 1):
            if scl_pin == sda_pin:
                continue

            print(f"\n=== Testing combo SCL={scl_pin} SDA={sda_pin} ===")

            # Build list of backends to try
            backends = []
            if hasattr(machine, "SoftI2C"):
                backends.append(("SoftI2C", None))
            backends.extend([(f"I2C({bid})", bid) for bid in (0, 1)])

            for backend, bid in backends:
                for freq in FREQS:
                    total_attempts += 1
                    print(f"- Attempt {total_attempts}: backend={backend} freq={freq}")
                    i2c, err = try_i2c_instance(backend, scl_pin, sda_pin, freq, bus_id=bid)
                    if err:
                        print(f"  Init: FAIL -> {err}")
                        continue
                    print("  Init: OK")

                    try:
                        # Quick bus scan for debug
                        try:
                            scanned = i2c.scan()
                            print(
                                f"  Scan: found {len(scanned)} device(s): {[hex(d) for d in scanned]}"
                            )
                        except Exception as e:
                            print(f"  Scan: error -> {e}")

                        # Probe specific BME280 addresses
                        for addr in BME280_ADDRESSES:
                            print(f"  Probe: address={hex(addr)} reg=0x{BME280_CHIP_ID_REG:02X}")
                            ok, info = probe_bme280(i2c, addr)
                            if ok:
                                print(
                                    f"    RESULT: BME280 detected (chip_id=0x{EXPECTED_CHIP_ID:02X})"
                                )
                                found.append(
                                    {
                                        "scl": scl_pin,
                                        "sda": sda_pin,
                                        "backend": backend,
                                        "freq": freq,
                                        "addr": addr,
                                    }
                                )
                                if BREAK_ON_FIRST_FOUND:
                                    try:
                                        if hasattr(i2c, "deinit"):
                                            i2c.deinit()
                                    except Exception:
                                        pass
                                    elapsed = utime.ticks_diff(utime.ticks_ms(), start_ms)
                                    print(
                                        f"\nStopped after first find. Attempts={total_attempts}, time={elapsed} ms"
                                    )
                                    # Print a short summary of the first success
                                    f0 = found[0]
                                    print(
                                        f"Found: SCL={f0['scl']} SDA={f0['sda']} backend={f0['backend']} freq={f0['freq']} addr={hex(f0['addr'])}"
                                    )
                                    return
                            else:
                                if isinstance(info, int):
                                    print(
                                        f"    Not a match (chip_id=0x{info:02X} != 0x{EXPECTED_CHIP_ID:02X})"
                                    )
                                else:
                                    print(f"    Probe error -> {info}")
                    finally:
                        try:
                            if hasattr(i2c, "deinit"):
                                i2c.deinit()
                        except Exception:
                            pass

                    # Housekeeping for long scans
                    if (total_attempts % 8) == 0:
                        gc.collect()
                        utime.sleep_ms(5)

    elapsed = utime.ticks_diff(utime.ticks_ms(), start_ms)
    print("\n=== Scan Summary ===")
    print(f"Total attempts: {total_attempts}")
    print(f"Duration: {elapsed} ms")
    if not found:
        print("No BME280 detected on any tested pin/address/backend combination.")
    else:
        print(f"Found {len(found)} candidate(s):")
        for i, fnd in enumerate(found, 1):
            print(
                f"  {i}. SCL={fnd['scl']} SDA={fnd['sda']} backend={fnd['backend']} freq={fnd['freq']} addr={hex(fnd['addr'])}"
            )


if __name__ == "__main__":
    main()
