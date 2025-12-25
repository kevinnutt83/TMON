TMON Unit Connector — Field Data Logs

The Unit Connector WordPress plugin writes incoming device field data logs to:

- wp-content/tmon-field-logs/
  - field_data_<unit_id>.log (raw JSON envelopes)
  - field_data_<unit_id>.csv (CSV rows derived from inbound JSON)

These files are NOT stored inside the plugin directory. If the directory does not exist,
the plugin will create it with permissions 0777.

REST endpoints used by devices:
- POST /wp-json/tmon/v1/device/field-data
- POST /wp-json/tmon/v1/device/data-history
- GET  /wp-json/tmon/v1/device/history?unit_id=...&hours=...

If you do not see logs, check:
- wp-content/tmon-field-logs directory exists and is writable by the web server
- WordPress REST is reachable from the device (firewall/SSL)
- JWT credentials are correct on the device (settings.py)

# Field Logs & Device Settings Files

Storage locations:
- Server-side (WP): `wp-content/tmon-field-logs/`
- Device-side (devices): `LOG_DIR` (default `/logs` on device firmware)

Per-device staged settings (device-side)
- Filename: `device_settings-<UNIT_ID>.json`
- Example content:
  {
    "WIFI_SSID": "my-ssid",
    "WIFI_PASS": "redacted",
    "NODE_TYPE": "remote",
    "FIELD_DATA_SEND_INTERVAL": 60
  }
- Devices write this file when they fetch staged settings from the UC `staged-settings` endpoint.

Field data (uniform upload pipeline)
- Devices (base and remotes) append 1 JSON object per line to `field_data.log`.
- Each record must include `unit_id` so the server can separate telemetry from multiple units in a single log.
- Base nodes also append remote entries to their `field_data.log` and upload them using the same backhaul behavior.

Parsing tips
- Small JSON objects per line are preferred (lighter to parse on device and on server streaming processors).
- The UC will attempt to extract `settings` objects embedded in logs, but explicit staged settings should use the `staged-settings` endpoint or the per-device file.
