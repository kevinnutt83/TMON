# TMON Device Commands & Staged Settings (Reference)

Supported commands (staged by Admin/UC and consumed by devices):

- set_var
  - Payload: { "key": "<SETTING_KEY>", "value": <value> }
  - Action: Sets a runtime setting on the device (subject to firmware allowlist/policy).

- run_func
  - Payload: { "name": "<function_name>", "args": <optional args> }
  - Action: Calls a device-side function (if present); device must guard missing functions.

- firmware_update
  - Payload: { "version": "<version>", "manifest": <optional> }
  - Action: Device schedules/checks OTA and applies via OTA flow.

- relay_ctrl / toggle_relay
  - Payload: { "relay": <1-8>, "state": "on"|"off", "runtime": "<seconds/minutes>" }
  - Action: Toggle a relay with firmware safety caps enforced.

- settings_update / settings_change
  - Payload: full or partial settings dictionary
  - Action: Device writes staged settings file and may apply them per allowlist.

- set_oled_message / set_oled_banner / clear_oled
  - Payload: message & timing controls
  - Action: Display or clear messages on the device OLED.

Command endpoints for devices (Unit Connector):
- POST /wp-json/tmon/v1/device/commands
  - Body: { "unit_id": "<unit>", "machine_id": "<machine>" }
  - Returns: list of queued commands for device.

- POST /wp-json/tmon/v1/device/command-complete
  - Body: { "job_id": <id>, "ok": true/false, "result": <string> }
  - Marks the queued command done/failed.

Device check-in (settings & staged commands):
- GET /wp-json/tmon/v1/device/staged-settings?unit_id=<unit_id>
  - Returns: { applied: {...}, staged: {...}, commands: [...] }

File naming & storage conventions (device-side):
- Staged settings fetched by the device are saved to:
  - device side: `<LOG_DIR>/device_settings-<UNIT_ID>.json` (example: `/logs/device_settings-12345.json`)
- Base slices remote telemetry by appending JSON lines to `field_data.log` (each line contains its `unit_id`).

Notes
- Telemetry (sdata) and persistent settings are kept separate: device POSTs include a `sdata` snapshot and an optional minimal `data` block.
- Base nodes persist remote device readings into `field_data.log`, and will also write per-remote `device_settings-<unit_id>.json` if remote sends settings.
