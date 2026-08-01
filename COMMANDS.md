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

## Hub and UC Install Guide (Quick)

1. Install and activate `tmon-admin` on the hub site.
2. Install and activate `tmon-unit-connector` on each customer site.
3. In UC, open `TMON Devices -> Hub Pairing` and set `TMON Admin Hub URL`.
4. Click `Pair with Hub` to register the UC and receive:
   - `hub_key` used in `X-TMON-HUB`
   - `read_token` for read-only admin sync calls
5. Optional: click `Refresh Hub Credentials` to rotate read token and refresh shared credentials.
6. In Admin, verify paired sites under `TMON Admin -> Deploy UC -> Paired Unit Connectors`.
7. Run `Refresh Devices` in UC to backfill assigned devices.

## Provisioning Operations (Admin)

- `TMON Admin -> Provisioning`
  - Filter by status, role, company, date range, and search text.
  - Batch actions: enable, disable, queue settings push, queue firmware check.
  - Export options:
    - Provision history CSV
    - Full device export CSV

## Security Notes

- Unit IDs are enforced as exactly 6 digits in provisioning and confirm-applied paths.
- Machine ID <-> Unit ID mapping is immutable once established.
- UC key lifecycle endpoints:
  - `POST /wp-json/tmon-admin/v1/uc/key/register`
  - `POST /wp-json/tmon-admin/v1/uc/key/refresh`
