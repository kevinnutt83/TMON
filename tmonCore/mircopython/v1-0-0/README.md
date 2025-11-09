# TMON MicroPython Device (v2.00j)

## Quick Start
1. Flash the firmware and configure `settings.py`.
2. Set `WORDPRESS_API_URL`, WiFi credentials, and pins in `settings.py`.
3. Power on; the device auto-registers with the WordPress server.
4. Use the admin UI to monitor, update OTA, and manage the device.

## Key Features in v2.00j
- Base-managed LoRa scheduling: base assigns `nextLoraSync` epochs to remotes; remotes persist next sync across reboots.
- LED mapping: distinct colors for LoRa RX/TX, sampling categories, and errors.
- Structured logs: confirmations/errors written to `/logs/lora.log` and `/logs/lora_errors.log`.
- Batched field-data uploads to reduce memory usage on base.

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

## Troubleshooting
- For LoRa error -1 or radio faults, the firmware re-initializes the radio and logs error flags.
- If uploads fail due to memory, ensure batching is enabled (default in v2.00i).
- Check power and WiFi signal; confirm server URL and credentials.
