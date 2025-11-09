# Firmware Version: 2.0.0h
import uasyncio as asyncio
import machine
import sdata
import settings
from utils import debug_print

async def toggle_relay(relay_num, state, runtime):
    try:
        # Validate relay_num (1-8)
        if not relay_num.isdigit() or not (1 <= int(relay_num) <= 8):
            await debug_print(f"Invalid relay number: {relay_num} (must be 1-8)", "ERROR")
            return

        # Get pin from settings (e.g., settings.RELAY_PIN1)
        pin_attr = f"RELAY_PIN{relay_num}"
        if not hasattr(settings, pin_attr):
            await debug_print(f"Missing pin setting: {pin_attr}", "ERROR")
            return
        pin_num = getattr(settings, pin_attr)
        pin = machine.Pin(pin_num, machine.Pin.OUT)

        # Get sdata variable (e.g., 'relay1_on')
        sdata_var = f"relay{relay_num}_on"
        if not hasattr(sdata, sdata_var):
            await debug_print(f"Missing sdata variable: {sdata_var}", "ERROR")
            return

        on = state.lower() == 'on'
        current_state = 1 if on else 0  # Assume active high: 1 = on, 0 = off

        pin.value(current_state)
        setattr(sdata, sdata_var, on)
        await debug_print(f"Relay {relay_num} set to {state}", "COMMAND")

        if runtime != '0':
            await asyncio.sleep(int(runtime))
            opposite_state = 0 if on else 1
            opposite_on = not on
            pin.value(opposite_state)
            setattr(sdata, sdata_var, opposite_on)
            await debug_print(f"Relay {relay_num} reverted after {runtime}s", "COMMAND")

    except Exception as e:
        await debug_print(f"Error in toggle_relay: {str(e)}", "ERROR")