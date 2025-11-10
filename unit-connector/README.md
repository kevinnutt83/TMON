# TMON Unit Connector
## Integration with TMON Admin
- TMON Admin can push configuration (e.g., device role) via the `device/command` endpoint using `settings_update`.
- Unknown devices can be relayed to TMON Admin for provisioning.

## GPS and Notifications
- Field data normalization includes GPS fields; CSV exports contain gps_lat/gps_lng and related columns.
- Offline device detection runs hourly and can notify per-device recipients configured in the Notifications page.

## Quick Start
1. Configure your company, sites, and zones in the Hierarchy menu.
2. Register and provision devices using the admin UI or QR onboarding. From TMON Admin, you can now "Send to UC registry" which:
	- Upserts the Company in UC hierarchy
	- Registers the device in UC registry
	- Applies initial settings (Role, WiFi disable for remote, optional GPS, Company ID)
3. Monitor device status and send OTA updates as needed.
4. Review logs, notifications, and analytics in the dashboard.

## Installation & Activation
- Install and activate both plugins: Unit Connector and TMON Admin.
- On activation, required database tables are created automatically in both plugins (devices, field data, OTA, commands, hierarchy, and claim requests).
	Cross-site admin endpoints are available under `/wp-json/tmon/v1/admin/...` and require header `X-TMON-ADMIN` matching the `tmon_uc_admin_key` option.
- Ensure permalinks are enabled so the REST API routes work.

## API Reference
See `/wp-json/tmon/v1/` for REST endpoints.

## REST Endpoints (tmon/v1)
- POST /device/field-data
	- Body: { unit_id, machine_id?, data?: [records] | record, REMOTE_NODE_INFO?: { <remoteUnitId>: record } }
	- Behavior: Normalizes into per-unit records (base and remote) and persists to DB; forwards to tmon-admin.
- POST /device/data-history (multipart)
	- Fields: unit_id, file
- POST /device/ping
- GET /device/ota-jobs/{unit_id}
- POST /device/ota-job-complete
### Admin/Hub endpoints (read/admin)
- GET /admin/field-data.csv — Normalized CSV export; supports unit_id/since/until/hours/gzip; Auth via headers X-TMON-ADMIN, X-TMON-HUB, or X-TMON-READ.
- GET /admin/field-data — JSON rows for Admin aggregation; same auth.
- POST /admin/device/settings — Admin push of per-device settings (e.g., GPS overrides) authenticated with X-TMON-ADMIN.

## Shortcodes
- [tmon_active_units] — List active (not suspended) devices with last_seen.
- [tmon_device_sdata unit_id="..."] — Latest sdata fields in a friendly table.
- [tmon_device_history unit_id="..." hours="24"] — 24h Chart.js history for a device.
- [tmon_claim_device] — Logged-in users can submit a claim for a device by Unit ID and Machine ID. Claims are reviewed/approved in tmon-admin.
- [tmon_device_list], [tmon_device_status] — Hierarchical list and status table. If firmware enables relays (ENABLE_RELAY1..8), authorized users see inline relay controls with runtime and scheduling.

### Examples
Add these shortcodes to any Page or Post:

- Devices overview:
	- `[tmon_active_units]`
	- `[tmon_device_list]`
	- `[tmon_device_status]`
- Device details (replace with your unit_id):
	- `[tmon_device_sdata unit_id="UNIT123"]`
	- `[tmon_device_history unit_id="UNIT123" hours="24"]`
- Customer device claiming (requires login):
	- `[tmon_claim_device]`

## Configuration & Data Flow
- Devices send data to Unit Connector (`/wp-json/tmon/v1/device/field-data`).
- Unit Connector normalizes base and remote node records per unit and stores them.
- Each record is forwarded to TMON Admin where authorization is enforced via `tmon_admin_authorize_device` (device must be provisioned and active; optional machine_id match).
- Use the Hierarchy admin screens to set up Company, Site, Zone, Cluster, and Unit.
	TMON Admin can upsert Company into UC via "Send to UC registry" to ensure immediate association.
- Use the Provisioned Devices admin screens (mirror view) or TMON Admin to confirm device provisioning.

## Claim Device Flow
1. A logged-in customer submits Unit ID and Machine ID using `[tmon_claim_device]`.
2. The claim is sent to `/wp-json/tmon-admin/v1/claim` with a REST nonce.
3. Admins review and Approve/Deny the claim in TMON Admin > Claims.
4. Once approved and provisioned/active, the device’s data is accepted by authorization.

## Notes
- Authorization is delegated to tmon-admin via the filter `tmon_admin_authorize_device`.
- Field data is also logged to wp-content/tmon-field-logs as JSON and CSV.
 - Claims submitted by users are managed in TMON Admin > Claims.
 - Ensure TMON Admin is active and tables are created on activation.
 - Normalized CSV export is available for admins at: `admin-post.php?action=tmon_export_field_data_csv&_wpnonce=...` (optional unit_id parameter). This CSV uses consistent columns and resolves prior parsing issues.
 - To relay unknown devices to central provisioning, define `TMON_ADMIN_HUB_URL` in wp-config.php to your central TMON Admin base URL.
## Troubleshooting
- Check device connectivity and power.
- Review audit logs and notifications.
- Consult [yourdocs.example.com](https://yourdocs.example.com) for more help.
