# TMON v2.06.0 - User Commands Module (rewritten for current firmware)
# Non-blocking async CLI that cooperates with LoRa and all other tasks.
# Uses uselect.poll() on sys.stdin so input never blocks the event loop.

import uasyncio as asyncio
import settings
import sdata
import machine
import uos as os
import sys

try:
    import uselect
except ImportError:
    uselect = None

from utils import debug_print

# Non-blocking stdin poller
_poller = None
_input_buf = ""

def _init_poller():
    global _poller
    if _poller is None and uselect is not None:
        try:
            _poller = uselect.poll()
            _poller.register(sys.stdin, uselect.POLLIN)
        except Exception:
            pass

def _poll_stdin():
    """Return a complete line from stdin if available, else None. Non-blocking."""
    global _input_buf
    if _poller is None:
        _init_poller()
    if _poller is None:
        return None
    try:
        if _poller.poll(0):
            ch = sys.stdin.read(1)
            if ch is None:
                return None
            if ch in ('\n', '\r'):
                line = _input_buf.strip()
                _input_buf = ""
                return line if line else None
            _input_buf += ch
    except Exception:
        pass
    return None


async def user_commands_task():
    """Async task that polls stdin for user commands without blocking LoRa."""
    _init_poller()
    if _poller is None:
        await debug_print("User commands: uselect not available, CLI disabled", "WARN")
        return
    await debug_print("User commands: CLI ready", "INFO")
    while True:
        try:
            line = _poll_stdin()
            if line:
                await process_command(line)
        except Exception as e:
            await debug_print(f"User commands error: {e}", "ERROR")
        await asyncio.sleep(0.1)


async def process_command(command):
    """Parse and dispatch a user command."""
    parts = command.split()
    if not parts:
        print("Invalid command")
        return

    action = parts[0].lower()
    handlers = {
        'set': handle_set_command,
        'see': handle_see_command,
        'status': handle_status_command,
        'reboot': handle_reboot_command,
        'file': handle_file_command,
        'help': handle_help_command,
        'sdata': handle_sdata_command,
        'debug': handle_debug_command,
        'relay': handle_relay_command,
        'info': handle_info_command,
    }

    handler = handlers.get(action)
    if handler:
        await handler(parts)
    else:
        print(f"Unknown command: {action}. Type 'help' for available commands.")


async def handle_set_command(parts):
    """set var <name> <value> - Set a settings variable."""
    if len(parts) < 4 or parts[1] != "var":
        print("Usage: set var <variable_name> <value>")
        return
    var_name = parts[2]
    raw_value = ' '.join(parts[3:])

    if not hasattr(settings, var_name):
        print(f"Variable {var_name} does not exist in settings")
        return

    # Restricted settings cannot be changed via CLI
    restricted = (
        'MACHINE_ID', 'UNIT_PROVISIONED', 'TMON_ADMIN_API_URL',
        'PROVISION_CHECK_INTERVAL_S', 'PROVISION_MAX_RETRIES',
        'WIFI_ALWAYS_ON_WHEN_UNPROVISIONED', 'WIFI_DISABLE_AFTER_PROVISION',
        'FIRMWARE_VERSION',
    )
    if var_name in restricted:
        print(f"Variable {var_name} is restricted and cannot be changed via CLI")
        return

    current = getattr(settings, var_name)
    try:
        if isinstance(current, bool):
            new_val = raw_value.lower() in ('true', '1', 'yes', 'on')
        elif isinstance(current, int):
            new_val = int(raw_value)
        elif isinstance(current, float):
            new_val = float(raw_value)
        else:
            new_val = raw_value
        setattr(settings, var_name, new_val)
        print(f"{var_name} = {new_val}")
        await debug_print(f"CLI: set {var_name} = {new_val}", "COMMAND")
    except Exception as e:
        print(f"Error setting {var_name}: {e}")


async def handle_see_command(parts):
    """see var <name> - Show a settings variable value."""
    if len(parts) < 3 or parts[1] != "var":
        print("Usage: see var <variable_name>")
        return
    var_name = parts[2]
    if hasattr(settings, var_name):
        print(f"{var_name} = {getattr(settings, var_name)}")
    elif hasattr(sdata, var_name):
        print(f"sdata.{var_name} = {getattr(sdata, var_name)}")
    else:
        print(f"Variable {var_name} not found in settings or sdata")


async def handle_status_command(parts):
    """status - Show device status overview."""
    print("--- TMON Device Status ---")
    print(f"  UNIT_ID:      {settings.UNIT_ID}")
    print(f"  UNIT_Name:    {settings.UNIT_Name}")
    print(f"  NODE_TYPE:    {settings.NODE_TYPE}")
    print(f"  FIRMWARE:     {settings.FIRMWARE_VERSION}")
    print(f"  MACHINE_ID:   {settings.MACHINE_ID}")
    print(f"  PROVISIONED:  {settings.UNIT_PROVISIONED}")
    print(f"  WiFi:         {sdata.WIFI_CONNECTED} (RSSI: {sdata.wifi_rssi})")
    print(f"  LoRa:         {sdata.LORA_CONNECTED} (RSSI: {sdata.lora_SigStr})")
    print(f"  Temp (probe): {sdata.cur_temp_f}F / {sdata.cur_temp_c}C")
    print(f"  Temp (device):{sdata.cur_device_temp_f}F / {sdata.cur_device_temp_c}C")
    print(f"  Humidity:     {sdata.cur_humid}%")
    print(f"  Pressure:     {sdata.cur_bar_pres}")
    print(f"  Voltage:      {sdata.sys_voltage}V")
    print(f"  Free mem:     {sdata.free_mem} bytes")
    print(f"  Errors:       {sdata.error_count}")
    print(f"  Suspended:    {getattr(settings, 'DEVICE_SUSPENDED', False)}")
    for i in range(1, 9):
        if getattr(settings, f'ENABLE_RELAY{i}', False):
            on = getattr(sdata, f'relay{i}_on', False)
            rt = getattr(sdata, f'relay{i}_runtime_s', 0)
            print(f"  Relay {i}:      {'ON' if on else 'OFF'} (runtime: {rt}s)")
    print("--------------------------")


async def handle_relay_command(parts):
    """relay <1-8> <on|off> [runtime_s] - Control a relay."""
    if len(parts) < 3:
        print("Usage: relay <1-8> <on|off> [runtime_seconds]")
        return
    relay_num = parts[1]
    state = parts[2].lower()
    runtime = parts[3] if len(parts) >= 4 else '0'

    if state not in ('on', 'off'):
        print("State must be 'on' or 'off'")
        return

    try:
        from relay import toggle_relay
        await toggle_relay(relay_num, state, runtime)
        print(f"Relay {relay_num} -> {state}")
    except Exception as e:
        print(f"Relay error: {e}")


async def handle_reboot_command(parts):
    """reboot [delay_s] - Reboot the device."""
    if len(parts) >= 2:
        try:
            delay = int(parts[1])
            print(f"Rebooting in {delay} seconds...")
            await asyncio.sleep(delay)
        except ValueError:
            print("Invalid delay")
            return
    else:
        print("Rebooting...")
    machine.reset()


async def handle_file_command(parts):
    """file <list|read|delete|create> <path> - File operations."""
    if len(parts) < 3:
        print("Usage: file <list|read|delete|create> <path>")
        return

    action = parts[1].lower()
    path = parts[2]

    if action == "list":
        try:
            if os.stat(path)[0] & 0x4000:
                files = os.listdir(path)
                for f in files:
                    print(f"  {f}")
            else:
                print(f"{path} is not a directory")
        except OSError:
            print(f"{path} does not exist")

    elif action == "read":
        try:
            with open(path, 'r') as f:
                content = f.read()
            print(content)
        except OSError:
            print(f"{path} does not exist")

    elif action == "delete":
        try:
            os.remove(path)
            print(f"Deleted {path}")
        except OSError:
            print(f"Cannot delete {path}")

    elif action == "create":
        try:
            with open(path, 'w') as f:
                f.write('')
            print(f"Created {path}")
        except OSError:
            print(f"Cannot create {path}")

    else:
        print(f"Unknown file action: {action}")


async def handle_sdata_command(parts):
    """sdata [var_name] - Show sdata variables."""
    if len(parts) >= 2:
        var_name = parts[1]
        if hasattr(sdata, var_name):
            print(f"sdata.{var_name} = {getattr(sdata, var_name)}")
        else:
            print(f"sdata.{var_name} not found")
    else:
        print("--- sdata snapshot ---")
        for attr in sorted(dir(sdata)):
            if not attr.startswith('_') and not callable(getattr(sdata, attr)):
                print(f"  {attr} = {getattr(sdata, attr)}")
        print("----------------------")


async def handle_debug_command(parts):
    """debug <flag> <on|off> - Toggle a debug flag."""
    if len(parts) < 3:
        print("Usage: debug <flag_name> <on|off>")
        print("Flags: DEBUG, DEBUG_LORA, DEBUG_SAMPLING, DEBUG_BME280, etc.")
        return
    flag = parts[1].upper()
    if not flag.startswith('DEBUG'):
        flag = 'DEBUG_' + flag
    state = parts[2].lower() in ('on', 'true', '1', 'yes')
    if hasattr(settings, flag):
        setattr(settings, flag, state)
        print(f"{flag} = {state}")
    else:
        print(f"Debug flag {flag} not found")


async def handle_info_command(parts):
    """info - Show device info and enabled features."""
    print("--- TMON Device Info ---")
    print(f"  Firmware:     {settings.FIRMWARE_VERSION}")
    print(f"  Node Type:    {settings.NODE_TYPE}")
    print(f"  WiFi:         {'Enabled' if settings.ENABLE_WIFI else 'Disabled'}")
    print(f"  LoRa:         {'Enabled' if settings.ENABLE_LORA else 'Disabled'}")
    print(f"  OLED:         {'Enabled' if settings.ENABLE_OLED else 'Disabled'}")
    print(f"  GPS:          {'Enabled' if settings.GPS_ENABLED else 'Disabled'}")
    print(f"  BME280:       {'Enabled' if settings.ENABLE_sensorBME280 else 'Disabled'}")
    print(f"  Device BME:   {'Enabled' if getattr(settings, 'ENABLE_DEVICE_BME280', False) else 'Disabled'}")
    print(f"  Probe BME:    {'Enabled' if getattr(settings, 'ENABLE_PROBE_BME280', False) else 'Disabled'}")
    print(f"  Frostwatch:   {'Enabled' if getattr(settings, 'ENABLE_FROSTWATCH', False) else 'Disabled'}")
    print(f"  Heatwatch:    {'Enabled' if getattr(settings, 'ENABLE_HEATWATCH', False) else 'Disabled'}")
    print(f"  OTA:          {'Enabled' if getattr(settings, 'OTA_ENABLED', False) else 'Disabled'}")
    print(f"  Soil:         {'Enabled' if getattr(settings, 'SAMPLE_SOIL', False) else 'Disabled'}")
    print(f"  Suspended:    {getattr(settings, 'DEVICE_SUSPENDED', False)}")
    print("------------------------")


async def handle_help_command(parts=None):
    """help - Show available commands."""
    help_message = """
Available commands:
  set var <name> <value>           - Set a settings variable
  see var <name>                   - View a settings or sdata variable
  status                           - Show device status overview
  info                             - Show device info and features
  relay <1-8> <on|off> [runtime_s] - Control a relay
  sdata [var_name]                 - Show sdata variables (all or specific)
  debug <flag> <on|off>            - Toggle a debug flag
  reboot [delay_s]                 - Reboot the device
  file list <directory>            - List files in a directory
  file read <file_path>            - Read a file
  file delete <file_path>          - Delete a file
  file create <file_path>          - Create an empty file
  help                             - Show this help message
"""
    print(help_message)
