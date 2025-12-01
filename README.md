<!--
	TMON Root README
	This document gives a high-level project overview.  For firmware details see mircopython/README.md.
-->

# TMON – Environmental Monitoring & Device Management Platform

TMON is a multi-component system for environmental sensing, secure device provisioning, telemetry collection, and operational control. It couples MicroPython-based field devices (base + remotes via LoRa) with a pair of WordPress plugins that provide ingestion, administration, analytics, and orchestration.

## Table of Contents
1. [Architecture](#architecture)
2. [Components](#components)
3. [Data Flow](#data-flow)
4. [Device Roles](#device-roles)
5. [Provisioning Lifecycle](#provisioning-lifecycle)
6. [Quick Start](#quick-start)
7. [Development Layout](#development-layout)
8. [Telemetry & Logs](#telemetry--logs)
9. [Security & Integrity](#security--integrity)
10. [Planned Enhancements](#planned-enhancements)
11. [License](#license)

## Architecture

```
 ┌────────────┐      LoRa SX1262       ┌──────────────┐
 │ Remote Node│  <-------------------> │ Base Station │
 │ (Sensors)  │                        │ (Aggregator) │
 └─────▲──────┘                         └──────┬───────┘
			 │  Periodic field data + sync epochs    │ Wi-Fi REST
			 │                                       ▼
			 │                              ┌────────────────────┐
			 │                              │ Unit Connector WP  │
			 │                              └─────────▲──────────┘
			 │                                Forward + Normalize
			 │                              ┌─────────┴──────────┐
			 │                              │  TMON Admin WP     │
			 │                              └────────────────────┘
```

## Components
| Layer | Purpose |
|-------|---------|
| Firmware (`mircopython/`) | Sampling, LoRa mesh, Wi-Fi provisioning, OLED UX, OTA scaffold, persistence. |
| Unit Connector Plugin | Accepts device field data (`/wp-json/tmon/v1/device/field-data`), normalizes, archives, forwards to Admin. |
| TMON Admin Plugin | Device registration, provisioning pushes, settings distribution, dashboards, audit, OTA coordination. |

## Data Flow
1. Remote nodes collect sensor readings and transmit to the base during scheduled sync windows.
2. Base batches field data and POSTs to Unit Connector.
3. Unit Connector stores + relays cleaned payloads to Admin.
4. Admin aggregates, applies policy, can push staged settings or suspension/command directives.

## Device Roles
- **Base**: Maintains LoRa timing, relays upstream via Wi-Fi, can remain powered with Wi-Fi enabled.
- **Remote**: Primarily LoRa; Wi-Fi enabled only until provisioning completes (then optionally disabled to save power).

## Provisioning Lifecycle
1. Boot → Device reads hardware `MACHINE_ID` and attempts Admin check-in if not provisioned.
2. Admin returns/assigns `UNIT_ID`; firmware persists to `/logs/unit_id.txt` and writes `/logs/provisioned.flag`.
3. Remote nodes optionally disable Wi-Fi (`WIFI_DISABLE_AFTER_PROVISION`) and rely solely on LoRa.
4. Future: staged settings file `/logs/remote_settings.staged.json` applied then archived.

## Quick Start
1. Flash firmware; edit `mircopython/settings.py` (Wi-Fi, API URLs, NODE_TYPE, sensor flags).
2. Install & activate WordPress plugins (`tmon-admin`, `unit-connector`).
3. Configure shared secrets / keys in each plugin settings page.
4. Power device → confirm first-boot check-in appears in Admin dashboard.
5. Observe field data ingestion in Unit Connector logs & Admin dashboards.

## Quick Ops & Diagnostics
- WP-CLI: Inspect pending provisioning queue and assert keys:
  - wp tmon-admin queue — lists pending queue entries and provisioned device snapshot.
  - wp tmon-admin assert-queue --key=<machine_or_unit_id> — returns success if a queued payload exists for the key.
- UI: Provisioning page includes per-row "Queue Provision" quick action and a banner showing the number of pending queued payloads.
- Payload fields: Saved/queued payloads now include both 'site_url' and 'wordpress_api_url' (site_url is mirrored into wordpress_api_url) so devices set WORDPRESS_API_URL correctly after applying staged settings.
- Re-enqueue: On Provisioning Activity, click "Re-enqueue". A dialog is pre-filled with the current payload JSON. Leave the field empty to re-enqueue unchanged payload; otherwise edit to change payload.

## Development Layout

| Path | Description |
|------|-------------|
| `mircopython/` | Core MicroPython firmware (tasks, LoRa, Wi-Fi, OLED, OTA, sampling). |
| `tmon-admin/` | Admin plugin (provisioning, audit, dashboards, notifications). |
| `unit-connector/` | Device ingestion + data relay plugin. |
| `CHANGELOG.md` | Release notes & feature progression. |
| `LICENSE` | Project licensing (MIT). |

Additional firmware doc: `mircopython/README.md`.

## Telemetry & Logs
- Field data: `/logs/field_data.log` (rotated into `data_history.log` after delivery).
- Delivered archive: `/logs/field_data.delivered.log` (future enhancement – archival snapshot).
- Errors: `/logs/lora_errors.log`.
- General LoRa: `/logs/lora.log`.
- State flags: `/logs/provisioned.flag`, `/logs/suspended.flag`, `/logs/ota_pending.flag`.

## Security & Integrity
- LoRa handshake planned with `LORA_NETWORK_NAME` + `LORA_NETWORK_PASSWORD`.
- Suspension flag halts active tasks while allowing periodic check-ins.
- OTA scaffold only marks pending; future secure download & signature verification planned.

## Planned Enhancements
- Staged settings apply & validation with rollback.
- LoRa network credential enforcement.
- Robust OTA (delta or full firmware package, backup & rollback).
- Extended GPS positioning + network-based geolocation fallback.
- Command queue ACK tracking and relay safety runtime enforcement.

## License
MIT License – see `LICENSE` for full text.

---
For detailed configuration keys, see the forthcoming `docs/FIRMWARE-SETTINGS.md`.

## Provisioning Improvements (v0.1.4)
- Admin Save & Provision now:
  - Marks the provisioned_devices.settings_staged flag = 1.
  - Mirrors provisioning info to the device mirror tmon_devices (wordpress_api_url, unit_name) and sets provisioned = 1 and provisioned_at timestamp.
  - Enqueues pending payloads for both machine_id and unit_id waring keys.
- Device check-in:
  - Will receive queued payloads in tmon_admin_pending_provision or a DB-staged payload derived from provisioned_devices row when settings_staged=1.
  - Device writes a staged file, applies settings and posts a confirm to Admin with header X-TMON-CONFIRM or X-TMON-READ.
- Admin UI:
  - New Provisioning Activity page shows pending queue, staged flags, and recent history; supports re-enqueue and delete.
- Security:
  - Device confirms applied settings using X-TMON-CONFIRM token; Admin validates token or existing read token.

# TMON Repository

## MicroPython Provisioning Flow (v2.01.2)
1. Initial check-in returns metadata (possibly without explicit settings object).
2. Firmware synthesizes payload, writes unit_id.txt, wordpress_api_url.txt, provisioned.flag, provisioning.meta.json.
3. Soft reset occurs once (provision_reboot.flag guards repeats).
4. Reboot loads WORDPRESS_API_URL early; field data uploads start immediately to Unit Connector.
