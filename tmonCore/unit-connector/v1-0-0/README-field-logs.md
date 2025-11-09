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
