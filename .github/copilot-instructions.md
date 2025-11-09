## TMON – AI coding agent instructions

This repo has three cooperating parts:
- MicroPython firmware (`tmonCore/mircopython/v1-0-0`): base/remote nodes sampling sensors, LoRa mesh, optional Wi‑Fi → WordPress.
- Unit Connector WordPress plugin (`unit-connector/v1-0-0`): receives device data, normalizes/stores, exports CSV/JSON, forwards to Admin.
- TMON Admin WordPress plugin (`tmon-admin/v1-0-0`): provisioning/claims/hierarchy, centralized aggregation, security/authorization.

Architecture & data flow
- Remote → Base via LoRa. Base schedules remotes by assigning absolute epochs; remotes persist next epoch across reboots.
- Base (and optionally devices directly) → Unit Connector: POST `/wp-json/tmon/v1/device/field-data` with compact payload; UC normalizes and forwards to Admin.
- Admin authorizes via `tmon_admin_authorize_device` and aggregates recent data for dashboards/exports.
- First-boot provisioning: device Wi‑Fi POSTs to Admin `/wp-json/tmon-admin/v1/device/check-in`, then remote nodes disable Wi‑Fi after provision.

Firmware patterns (MicroPython)
- Async single-thread loop in `main.py` using `uasyncio` with tasks: `lora_comm_task`, `sample_task`, base-only `periodic_field_data_task` + command polling.
- Configuration in `settings.py` (UNIT_ID, NODE_TYPE, WORDPRESS_* creds, GPS flags, pins, LoRa params, logging). Logs under `/logs` with rotation caps.
- LoRa in `lora.py`: non-blocking radio, file locks, idle deinit. Base sends ACK with `{ack:'ok', next, next_in, gps_*?}` and returns to RX. Remotes adopt `gps_*` when allowed and persist to `/logs/gps.json`.
- Scheduling: base assigns unique slots using `settings.REMOTE_SYNC_SCHEDULE` with min spacing `LORA_SYNC_WINDOW`; remotes transmit when `now >= nextLoraSync` else probe every 30s.
- Telemetry struct in `sdata.py` (e.g., `cur_temp_f`, `cur_humid`, `sys_voltage`, `wifi_rssi`, `lora_SigStr`, optional `gps_*`). Include last error fields when `TELEMETRY_INCLUDE_LAST_ERROR`.
- WordPress auth: JWT obtained in `wprest.py` from `/wp-json/jwt-auth/v1/token`; subsequent device endpoints use `Authorization: Bearer <token>`.

Unit Connector (WordPress) conventions
- Device POST: `/wp-json/tmon/v1/device/field-data` supports `{ unit_id, machine_id?, data|record | REMOTE_NODE_INFO }`. UC stores per‑unit records and forwards to Admin.
- Admin/hub reads: `GET /wp-json/tmon/v1/admin/field-data(.csv)` secured via headers `X-TMON-ADMIN`, `X-TMON-HUB`, or `X-TMON-READ`. CSV export normalizes legacy keys (`t_f`→temp_f, etc.).
- Shortcodes for UI: `[tmon_active_units]`, `[tmon_device_sdata unit_id="..."]`, `[tmon_device_history unit_id="..." hours="24"]`, `[tmon_claim_device]`.
- Options/keys: UC expects `tmon_uc_admin_key` (shared with Admin), optional hub read token (`tmon_uc_hub_read_token`).

TMON Admin (WordPress) conventions
- Provisioning flow in `tmon-admin.php` + `includes/provisioning.php`. Devices appear after check-in; set Role/company and associate to UC via “Send to UC registry” or “Push Role + GPS”.
- Hooks: `tmon_admin_authorize_device` (filter accept/deny data), `tmon_admin_receive_field_data` (action with normalized records).
- Endpoints used by UC/Admin tooling include `GET /wp-json/tmon-admin/v1/field-data` and `POST /wp-json/tmon-admin/v1/claim`.
- Shared key on Admin: `tmon_admin_uc_key`. Pairings page manages per‑UC read tokens and pushes updates to `/wp-json/tmon/v1/admin/read-token/set` with `X-TMON-ADMIN`.

Project-specific conventions
- Logs & persisted state on device: `/logs/lora.log`, `/logs/lora_errors.log`, `/logs/remote_node_info.json`, `/logs/remote_sync_schedule.json`, `/logs/gps.json`, `/logs/field_data.log` (batched uploads).
- Remotes payload example (LoRa or field-data): `{unit_id,name,ts,t_f,t_c,hum,bar,v,fm}`. Base ACK example: `{"ack":"ok","next":<epoch>,"next_in":<seconds>,"gps_lat"?,"gps_lng"?,...}`.
- When adding firmware tasks, keep them non-blocking, wrap with `debug_print` on errors, and avoid overlapping uploads (see `periodic_field_data_task`).

Developer workflows (quick references)
- Firmware: edit `settings.py`; main entry is `main.py` (async). Field data batching/rotation controlled by `FIELD_DATA_*` settings. First-boot provisioning URL set via `TMON_ADMIN_API_URL`.
- WordPress: install/activate both plugins. Configure shared keys in UC Settings (`tmon_uc_admin_key`) and Admin Settings (`tmon_admin_uc_key`). Ensure permalinks and REST enabled.
- Data exports: UC CSV via `admin-post.php?action=tmon_export_field_data_csv&_wpnonce=...`; OTA jobs CSV via `admin-post.php?action=tmon_export_ota_jobs&_wpnonce=...`.

Where to look
- Firmware: `main.py`, `lora.py`, `wprest.py`, `settings.py`, `sdata.py`, `utils.py`.
- Unit Connector: `tmon-unit-connector.php`, `includes/field-data-api.php`, `includes/api.php`, `includes/settings.php`, `includes/notify.php`.
- Admin: `tmon-admin.php`, `includes/provisioning.php`, `includes/field-data-api.php`, `includes/api.php`, templates in `templates/`.

If anything above is unclear (e.g., specific REST shapes or option keys), ask to confirm before changing cross-component contracts.
