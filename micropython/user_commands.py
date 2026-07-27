# TMON v2.06.x - User Commands Module (updated)
# Non-blocking async CLI that cooperates with LoRa and all other tasks.
# Uses uselect.poll() on sys.stdin so input never blocks the event loop.
#
# New in this version:
# - pins command (show pin assignments)
# - config command (key configuration summary)
# - Expanded contextual help system

import uasyncio as asyncio
import settings
import sdata
import machine
import uos as os
import sys
import ubinascii as _ub

try:
    import uselect
except ImportError:
    uselect = None

from utils import (
    debug_print,
    persist_custom_setting,
    persist_node_type,
    persist_unit_name,
    persist_wordpress_api_url,
    persist_suspension_state,
    record_exception,
    log_exception,
)

# Non-blocking stdin poller
_poller = None
_input_buf = ""

def _init_poller():
    global _poller
    if _poller is None and uselect is not None:
        try:
            _poller = uselect.poll()
            _poller.register(sys.stdin, uselect.POLLIN)
        except Exception as e:
            record_exception('user_commands._init_poller', e, status='WARN')

def _print_prompt():
    sys.stdout.write("TMON> ")

def _poll_stdin():
    """Return a complete line from stdin if available, else None. Non-blocking."""
    global _input_buf
    if _poller is None:
        _init_poller()
    if _poller is None:
        return None
    try:
        while _poller.poll(0):
            ch = sys.stdin.read(1)
            if ch is None:
                break
            if ch in ('\n', '\r'):
                line = _input_buf.strip()
                _input_buf = ""
                print()
                return line if line else None
            if ch == '\x7f' or ch == '\x08':
                if _input_buf:
                    _input_buf = _input_buf[:-1]
                    sys.stdout.write('\x08 \x08')
            else:
                _input_buf += ch
                sys.stdout.write(ch)
    except Exception as e:
        record_exception('user_commands._poll_stdin', e, status='WARN')
    return None


async def user_commands_task():
    """Async task that polls stdin for user commands without blocking LoRa."""
    _init_poller()
    if _poller is None:
        await debug_print("User commands: uselect not available, CLI disabled", "WARN")
        return
    print("[TMON CLI] Type 'help' for available commands.")
    _print_prompt()
    while True:
        try:
            line = _poll_stdin()
            if line:
                await process_command(line)
                _print_prompt()
        except Exception as e:
            await log_exception('user_commands.user_commands_task', e)
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
        'pins': handle_pins_command,        # NEW
        'config': handle_config_command,    # NEW
        'hmactest': handle_hmactest_command,
    }

    handler = handlers.get(action)
    if handler:
        await handler(parts)
    else:
        print(f"Unknown command: {action}. Type 'help' for available commands.")


# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------

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
        if var_name == 'UNIT_Name':
            persist_unit_name(new_val)
        elif var_name == 'NODE_TYPE':
            persist_node_type(new_val)
        elif var_name == 'WORDPRESS_API_URL':
            persist_wordpress_api_url(new_val)
        elif var_name == 'DEVICE_SUSPENDED':
            persist_suspension_state(bool(new_val))
        else:
            persist_custom_setting(var_name, new_val)
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


async def handle_pins_command(parts):
    """pins - Show current pin assignments."""
    print("--- Pin Assignments ---")
    pin_list = [
        ("DEVICE_TEMP_SCL", "DEVICE_TEMP_SCL_PIN"),
        ("DEVICE_TEMP_SDA", "DEVICE_TEMP_SDA_PIN"),
        ("PROBE_SCL", "BME280_PROBE_SCL_PIN"),
        ("PROBE_SDA", "BME280_PROBE_SDA_PIN"),
        ("OLED_SCL", "OLED_SCL_PIN"),
        ("OLED_SDA", "OLED_SDA_PIN"),
        ("RELAY1", "RELAY_PIN1"),
        ("RELAY2", "RELAY_PIN2"),
        ("RELAY3", "RELAY_PIN3"),
        ("RELAY4", "RELAY_PIN4"),
        ("RELAY5", "RELAY_PIN5"),
        ("RELAY6", "RELAY_PIN6"),
        ("RELAY7", "RELAY_PIN7"),
        ("RELAY8", "RELAY_PIN8"),
        ("SYS_VOLTAGE", "SYS_VOLTAGE_PIN"),
        ("LED", "LED_PIN"),
        ("SOIL_PROBE", "SOIL_PROBE_PIN"),
        ("SPI_CLK", "CLK_PIN"),
        ("SPI_MOSI", "MOSI_PIN"),
        ("SPI_MISO", "MISO_PIN"),
        ("SPI_CS", "CS_PIN"),
        ("LORA_IRQ", "IRQ_PIN"),
        ("LORA_RST", "RST_PIN"),
        ("LORA_BUSY", "BUSY_PIN"),
    ]
    for label, attr in pin_list:
        val = getattr(settings, attr, None)
        print(f"  {label:18} : {val}")
    print("-----------------------")
    print("Use 'set var <PIN_NAME> <gpio>' to change a pin (most are allowed).")
    print("Example: set var RELAY_PIN3 19")


async def handle_config_command(parts):
    """config - Show key configuration summary."""
    print("--- Key Configuration ---")
    print(f"  NODE_TYPE                 : {settings.NODE_TYPE}")
    print(f"  ENABLE_WIFI               : {settings.ENABLE_WIFI}")
    print(f"  ENABLE_LORA               : {settings.ENABLE_LORA}")
    print(f"  ENABLE_OLED               : {settings.ENABLE_OLED}")
    print(f"  ENABLE_DEVICE_BME280      : {getattr(settings, 'ENABLE_DEVICE_BME280', False)}")
    print(f"  ENABLE_PROBE_BME280       : {getattr(settings, 'ENABLE_PROBE_BME280', False)}")
    print(f"  SAMPLE_DEVICE_TEMP        : {getattr(settings, 'SAMPLE_DEVICE_TEMP', False)}")
    print(f"  SAMPLE_PROBE_TEMP         : {getattr(settings, 'SAMPLE_PROBE_TEMP', False)}")
    print(f"  LORA_SYNC_RATE            : {getattr(settings, 'LORA_SYNC_RATE', 300)}")
    print(f"  REQUIRE_SYNC_BEFORE_SLEEP : {getattr(settings, 'REMOTE_REQUIRE_SUCCESSFUL_SYNC_BEFORE_SLEEP', True)}")
    print(f"  FAILED_SYNC_RETRY_S       : {getattr(settings, 'REMOTE_FAILED_SYNC_RETRY_S', 45)}")
    print(f"  ENABLE_SDCARD             : {getattr(settings, 'ENABLE_SDCARD', False)}")
    print(f"  DEVICE_SUSPENDED          : {getattr(settings, 'DEVICE_SUSPENDED', False)}")
    print("-------------------------")


async def handle_hmactest_command(parts):
    """hmactest [message] - Print deterministic HMAC digest for cross-device verification."""
    if len(parts) > 1:
        message = ' '.join(parts[1:])
    else:
        message = 'TMON_HMAC_TEST'

    secret = getattr(settings, 'LORA_HMAC_SECRET', '') or ''
    if not secret:
        print('LORA_HMAC_SECRET is empty')
        return

    try:
        from lora import hmac_sha256
        digest = hmac_sha256(secret, message)
        full_hex = _ub.hexlify(digest).decode()
        trunc = int(getattr(settings, 'LORA_HMAC_TRUNCATE', 16))
        trunc_hex = full_hex[:max(1, trunc)]

        print('--- HMAC Test ---')
        print(f'Message     : {message}')
        print(f'Secret len  : {len(secret)}')
        print(f'Truncate    : {trunc}')
        print(f'HMAC full   : {full_hex}')
        print(f'HMAC trunc  : {trunc_hex}')
        print('Use same message on base and remote; HMAC values must match exactly.')
        print('-----------------')
    except Exception as e:
        print(f'hmactest failed: {e}')


async def handle_help_command(parts):
    """Expanded contextual help."""
    if len(parts) <= 1:
        print("""
Available commands:
  help [command]                 - Show this help or detailed help for a command
  status                         - Full device status overview
  info                           - Feature overview (enabled modules)
  config                         - Key configuration summary
  pins                           - Show all important pin assignments
    hmactest [message]             - Show deterministic LoRa HMAC digest
  set var <name> <value>         - Set a settings variable
  see var <name>                 - View a settings or sdata variable
  sdata [var]                    - Show all or one sdata variable
  relay <1-8> <on|off> [secs]    - Control a relay
  debug <flag> <on|off>          - Toggle a debug flag
  file <list|read|delete|create> <path>
  reboot [delay]                 - Reboot the device

Type 'help <command>' for detailed usage and examples.
""")
        return

    cmd = parts[1].lower()
    details = {
        "help": "help [command]\n  Shows the command list or detailed help for a specific command.",
        "status": "status\n  Displays unit ID, name, node type, firmware, connectivity,\n  both temperatures, humidity, pressure, voltage, memory, errors and relay states.",
        "info": "info\n  Shows which major features are currently enabled or disabled.",
        "config": "config\n  Shows the most important configuration values currently in effect\n  (node type, sensors, sleep behaviour, etc.).",
        "pins": "pins\n  Lists all important GPIO pin assignments used by the firmware.\n  You can change most of them with:\n    set var RELAY_PIN3 19",
        "hmactest": "hmactest [message]\n  Computes LoRa HMAC for a fixed message using current LORA_HMAC_SECRET.\n  Run on both base and remote; both outputs must match.\n  Default message: TMON_HMAC_TEST",
        "set": "set var <name> <value>\n  Changes a settings variable.\n  Restricted variables (MACHINE_ID, UNIT_PROVISIONED, etc.) cannot be changed.\n  Example: set var ENABLE_OLED true",
        "see": "see var <name>\n  Displays the current value of a settings or sdata variable.\n  Example: see var UNIT_Name",
        "sdata": "sdata [var_name]\n  With no argument shows all sdata variables.\n  With a name shows only that variable.",
        "relay": "relay <1-8> <on|off> [runtime_s]\n  Turns a relay on or off.\n  Optional runtime_s limits how long the relay stays on (in seconds).\n  Example: relay 1 on 300     # on for 5 minutes",
        "debug": "debug <flag> <on|off>\n  Toggles a debug flag (DEBUG, DEBUG_LORA, DEBUG_SAMPLING, etc.).\n  Example: debug LORA on",
        "file": "file <list|read|delete|create> <path>\n  Basic file system operations.\n  Examples:\n    file list /logs\n    file read /logs/lora.log",
        "reboot": "reboot [delay_s]\n  Reboots the device immediately or after a delay in seconds.",
    }
    print(details.get(cmd, f"No detailed help available for '{cmd}'.\nType 'help' for the full list of commands."))