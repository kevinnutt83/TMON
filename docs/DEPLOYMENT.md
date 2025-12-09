# Deployment Guide

## Firmware (MicroPython)
1. Prepare board (ESP32-S3 recommended); flash MicroPython firmware.
2. Copy `micropython/` contents to the device filesystem (e.g., via `mpremote` or `ampy`).
3. Edit `micropython/settings.py` minimally:
   - `TMON_ADMIN_API_URL`, `WORDPRESS_API_URL`
   - `WIFI_SSID`, `WIFI_PASS`
   - `NODE_TYPE` (`base` or `remote`)
4. Power cycle; observe serial logs for provisioning check-in and LoRa init.

## WordPress Plugins
1. Install `tmon-admin/` and `unit-connector/` plugins into your WordPress `wp-content/plugins/` directory.
2. Activate both plugins in WordPress Admin.
3. In each plugin settings page, set shared keys and REST/JWT options as required.
4. Confirm REST namespace availability:
   - `/wp-json/tmon/v1/` (Unit Connector)
   - `/wp-json/tmon-admin/v1/` (Admin)

## First-Boot Provisioning
- Device performs POST to Admin `.../device/check-in` with `unit_id` (placeholder), `machine_id` and version.
- Admin returns canonical `unit_id`; firmware persists to `/logs/unit_id.txt` and writes `/logs/provisioned.flag`.
- Remote devices may disable Wi-Fi after provisioning depending on `WIFI_DISABLE_AFTER_PROVISION`.

## Field Data Flow
- Base nodes collect & batch data into `/logs/field_data.log`.
- Background task POSTs batches to Unit Connector at a fixed interval.
- On success, `field_data.log` rotates to `data_history.log`. Unsent payloads are buffered in `field_data_backlog.log`.

## OTA (Scaffold)
- Firmware periodically checks `OTA_VERSION_ENDPOINT`.
- When a newer version is detected, `/logs/ota_pending.flag` is written; future steps include download, backup, and apply.

## Troubleshooting
- Verify serial logs for Wi-Fi connection and LoRa initialization.
- Ensure WordPress permalinks are enabled and JWT configuration is correct.
- Check `/logs/lora_errors.log` on-device for firmware-side exceptions.
- Use WordPress debug log for plugin-side issues.

---
Generated November 10, 2025.
