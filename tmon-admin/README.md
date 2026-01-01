# TMON Admin
## Device provisioning flow
1) Device boots and performs a WiFi check-in to `/wp-json/tmon-admin/v1/device/check-in` with `unit_id` and `machine_id`.
2) The device appears under Provisioning, organized by Machine ID and Unit ID. Set the device Role (base/remote) and Company association.
3) Either:
	- Push configuration to the appropriate Unit Connector site ("Push Config to UC") to enqueue a `settings_update` command, or
	- Use "Send to UC registry" to upsert the Company in UC, register the device, and apply settings (Role, Company ID, optional GPS) immediately.
4) After provisioning, the device associates with the customer’s Unit Connector for day-to-day management, with TMON Admin maintaining oversight.

## Notifications & Security
- Offline device scanning produces notifications and can target per-device recipients.
- UC deployment supports HTTPS-only and optional SHA-256 pinning with Authorization header forwarding.

## Overview
TMON Admin is the central authority for provisioning, authorization, hierarchy management, and device claim workflows. It receives normalized device data forwarded from the Unit Connector.

## Key Features
- Provisioning: Register devices (unit_id, optional machine_id), set status (Active/Suspended), associate to hierarchy.
 - GPS override: POST `/wp-json/tmon-admin/v1/device/gps-override` to push `GPS_LAT/LNG/ALT_M/ACCURACY_M` to a UC site’s device settings.
- Hierarchy: Company, Site, Zone, Cluster, and Unit tables created on activation.
- Authorization: Enforces access via the `tmon_admin_authorize_device` filter.
- Claims: Logged-in users can submit device claims; admins approve/deny in the Claims UI.
 - Field Data Aggregation: Admin aggregates recent field data from paired Unit Connectors using `/wp-json/tmon-admin/v1/field-data`. The Field Data page includes a time window filter and a mini chart of upcoming LoRa remote syncs (REMOTE_SYNC_SCHEDULE).

## Workflows
1. Provision devices in Admin > Provisioning and set status Active.
2. Set the shared key for UC integration on both hubs and spokes:
	- On TMON Admin: Settings → set `Shared Key for UC Integration` (option: `tmon_admin_uc_key`).
	- On Unit Connector: Settings → set `Shared Key (X-TMON-ADMIN)` (option: `tmon_uc_admin_key`).
3. In Provisioning, use "Send to UC registry" or "Push Role + GPS (direct)" as required.
2. Organize devices into hierarchy for visibility and permissions.
3. Use Admin > Claims to approve/deny customer claims.
4. Monitor incoming field data via hooks from Unit Connector and the Field Data page. If a spoke lacks the local Provisioned Devices table, the Unit Connector admin view will fall back to the hub endpoint to render devices.

## REST Endpoints
- POST `/wp-json/tmon-admin/v1/claim` — Submit a device claim (requires login).
 - GET `/wp-json/tmon-admin/v1/field-data` — Aggregated recent field data from paired Unit Connectors; requires manage_options.

## Hooks
- `tmon_admin_receive_field_data` — Receives normalized records (unit_id, sdata, timestamps) from Unit Connector.
- `tmon_admin_authorize_device` — Filter invoked to accept/reject incoming device data.

## Troubleshooting
- Ensure plugin activation creates all tables (including hierarchy and claim requests).
- Check Audit for authorization denials and malformed data.
- Confirm device status is Active and machine_id matches (if required).
