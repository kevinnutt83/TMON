# TMON MicroPython Device (v2.04.0)

## Quick Start
1. Flash the firmware and configure `settings.py`.
2. Set `WORDPRESS_API_URL`, WiFi credentials, and pins in `settings.py`.
3. Power on; the device auto-registers with the WordPress server.
4. Use the admin UI to monitor, update OTA, and manage the device.

## Key Features in v2.01.1
- Base-managed LoRa scheduling: base assigns `nextLoraSync` epochs to remotes; remotes persist next sync across reboots.
- LED mapping: distinct colors for LoRa RX/TX, sampling categories, and errors.
- Structured logs: confirmations/errors written to `/logs/lora.log` and `/logs/lora_errors.log`.
- Batched field-data uploads to reduce memory usage on base.
- OTA version check scaffold with pending flag to support future safe updates.
- Wi-Fi RSSI monitor and OLED pages showing UNIT_ID, machine suffix, temp in F, and bars for Wi-Fi/LoRa.
- Command completion with primary /device/command-complete endpoint and automatic fallback to legacy /device/ack if the server lacks the newer route.

## First-boot provisioning (WiFi check-in)
- On first boot (or until provisioned), the device enables WiFi and posts its `unit_id` and `machine_id` to the TMON Admin hub at `TMON_ADMIN_API_URL`.
- On success, it writes `/logs/provisioned.flag`. If the device role is `remote`, WiFi is then disabled and LoRa is used to relay data via the base station.
- Configure `TMON_ADMIN_API_URL` in `settings.py`.

## Roles
- `NODE_TYPE = 'base' | 'remote'` determines how the device behaves. Remote nodes prefer LoRa and disable WiFi after provisioning.

## GPS
- GPS fields are supported end-to-end: firmware sends GPS in payloads; base can broadcast to remotes; remotes adopt and persist coordinates. Admin can remotely override GPS via UC/Admin settings; devices honor overrides when allowed by settings policy.

## Settings
- `nextLoraSync` and `LORA_SYNC_WINDOW` control LoRa sync cadence and windowing.
- `WORDPRESS_API_URL`, `WIFI_SSID`, `WIFI_PASS` are required for server connectivity.
- Pin mappings and sensor addresses are centralized here.

## Logs
- Device logs are stored in `/logs`. LoRa confirmations in `lora.log`; errors in `lora_errors.log`.

## Display
- Background OLED update runs at `OLED_UPDATE_INTERVAL_S`.
- If `OLED_SCROLL_ENABLED=True`, pages rotate every `OLED_PAGE_ROTATE_INTERVAL_S` seconds between:
	- Page 0: Sensors + Wi-Fi/LoRa bars, voltage, unit name, message line
	- Page 1: Relay grid + system runtime and memory

## Runtime loops
- LoRa loop: lora_comm_task runs at 1s cadence independently to avoid disruptions.
- Sampling loop: sample_task runs at 60s cadence.
- Background tasks: utils.start_background_tasks schedules provisioning and field-data send (guarded to avoid duplication).

## Troubleshooting
- If you saw “ImportError: can't import name start_background_tasks”, upgrade to v2.01.3 where utils.start_background_tasks exists. display_message is provided by oled.
- For LoRa error -1 or radio faults, the firmware re-initializes the radio and logs error flags.
- If uploads fail due to memory, ensure batching is enabled (default in v2.00i).
- Check power and WiFi signal; confirm server URL and credentials.
 - On desktop, MicroPython modules (`uasyncio`, `machine`) will show lint warnings; they are valid on-device.

## Provisioning (Enhanced v2.01.x)
- Metadata-only responses (provisioned/staged_exists + site_url) now synthesize a staged payload.
- Persisted: UNIT_ID, WORDPRESS_API_URL (wordpress_api_url.txt), UNIT_Name, NODE_TYPE, PLAN, FIRMWARE_VERSION.
- Guard flag prevents reboot loop; single soft reset after first metadata persistence.
- Field data uploader prefers settings.WORDPRESS_API_URL (falls back to wprest) eliminating "No WORDPRESS_API_URL set" errors.

# TMON MicroPython Agent — Integration Notes

Node types
- base: hosts LoRa network, connects to WordPress/Unit Connector via WiFi, backhauls remote telemetry and settings.
- wifi: a WiFi-only node (no LoRa). Uses WiFi for telemetry, commands, and OTA.
- remote: LoRa-only device that uses LoRa to reach a base; does not send HTTP to the Unit Connector.

Staged settings & persistence
- Devices fetch staged settings using:
  GET /wp-json/tmon/v1/device/staged-settings?unit_id=<UNIT_ID>
- Staged settings are saved to:
  `<LOG_DIR>/device_settings-<UNIT_ID>.json`
- The settings_apply module will look for this per-unit file and move it to the canonical staged file path before applying:
  `/logs/remote_settings.staged.json` -> the apply loop persists `/logs/remote_settings.applied.json` snapshot.

Telemetry (sdata) vs persistent settings
- Telemetry snapshot is sent under `sdata` (full runtime snapshot) and a minimal `data` block for legacy compatibility.
- Persistent settings are delivered separately via staged settings and must not be mixed with telemetry streams.

Commands
- Devices poll for queued commands (base & wifi) via `/wp-json/tmon/v1/device/commands` and apply them.
- On receipt, devices should call the appropriate handler (implemented in wprest.handle_device_command).
- After completion devices report via `/wp-json/tmon/v1/device/command-complete`.

Base behavior for LoRa remotes
- Base writes each remote payload as an independent JSON line to its `field_data.log` including `unit_id`.
- If remote payload includes a `settings` object, the base writes `<LOG_DIR>/device_settings-<REMOTE_UNIT_ID>.json` for that remote; Admin/UC can then read or push those staged settings to the remote (via base → Admin).
- Base calls sampling compare helpers using the remote values so alarms (frost/heat) can trigger from remote samples.

Notes for integrators
- The device will apply staged settings automatically (configurable with `APPLY_STAGED_SETTINGS_ON_SYNC`).
- Command and staged-settings endpoints are the canonical device sources; devices write staged settings to the per-unit file for auditing and fallback.
- For more, see root `COMMANDS.md` and Unit Connector READMEs.
