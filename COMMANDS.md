# TMON Device Commands

List of commands the Unit Connector / Admin may stage for devices and how devices handle them:

- set_var
  - payload: { "key": "<SETTING_KEY>", "value": <value> }
  - Action: Sets a runtime setting on the device (if present in allowlist) and persists if appropriate.

- run_func
  - payload: { "name": "<function_name>", "args": <optional args> }
  - Action: Calls a device-side function (if present). Device should guard and log missing functions.

- firmware_update
  - payload: { "version": "<version>", "manifest": <optional> }
  - Action: Device will schedule/check OTA update and fetch/apply via OTA logic.

- relay_ctrl / toggle_relay
  - payload: { "relay": <1-8>, "state": "on"|"off", "runtime": "<minutes>" }
  - Action: Toggle a named relay with safety caps enforced by firmware.

- settings_update
  - payload: a settings dict
  - Action: Device applies allowed settings and stores staged settings file.

- set_oled_message
  - payload: { "message": "<text>", "duration": <seconds> }
  - Action: Displays an on-device message.

- set_oled_banner
  - payload: { "message": "<text>", "duration": <seconds>, "persist": <bool> }
  - Action: Set banner on the OLED.

- clear_oled
  - payload: {}
  - Action: Clear any OLED messages/banners.

Notes:
- Devices poll `/wp-json/tmon/v1/device/commands` (or fetch staged commands via check-in endpoints) and apply commands using local handlers.
- The Unit Connector exposes staged commands via the device-oriented endpoint `/tmon/v1/device/staged-settings` (returns settings + pending commands).
