## v2.00j — 2025-10-18

- Firmware: OLED change-detection UI with two pages; added WiFi/LoRa telemetry display.
- Firmware: Field data uploader adds detailed response logging and backlog handling.
- Unit Connector: Field data API now normalizes remote records (REMOTE_NODE_INFO), writes headered CSV with consistent columns, stores per-unit normalized rows, and forwards unknown devices to TMON Admin when `TMON_ADMIN_HUB_URL` is configured.
- TMON Admin: Adds `/tmon-admin/v1/ingest-unknown` endpoint to audit and queue auto-provisioning of unassigned machine IDs.
- Unit Connector: New admin CSV export route for normalized field data to fix prior parsing issues.
 - Unit Connector: Device status shortcode now includes relay controls (if firmware enables relays). Supports immediate and scheduled toggles with runtime.
 - Unit Connector: Added JSON field data listing for Admin hub (`/tmon/v1/admin/field-data`) and enhanced CSV export route with time-window and gzip.
 - TMON Admin: Field Data page shows window filter and a mini chart reflecting REMOTE_SYNC_SCHEDULE; aggregates logs from paired Unit Connectors via `/tmon-admin/v1/field-data`.
 - TMON Admin: Safe nonce verification to avoid "link expired" fatals across pages; improved provisioning schema migrations and error messages.
 - Cross-site GPS overrides: Admin pushes GPS to UC via `/tmon/v1/admin/device/settings` using `X-TMON-ADMIN`.
 - Provisioned Devices in UC falls back to hub endpoint when local table is missing.

# CHANGELOG

All notable changes to this project will be documented in this file.

## Unreleased
- Removed duplicated settings block (deduplicated settings.py).
- Hardened async HTTP client in wprest to support host:port and full reads.
- Made debug/config_persist compatible with MicroPython (removed union type hints).
- Improved utils.checkLogDirectory for safer directory creation.
- Consolidated project docs into TODO.md and updated README/CHANGELOG.

## v0.1.3 - 2025-11-28
- Provisioning: Save & Provision now updates tmon_devices mirror (provisioned, provisioned_at, wordpress_api_url, unit_name).
- Check-in: device check-in returns staged payload from queue or DB and clears settings_staged on delivery.
- Confirm: Added /wp-json/tmon-admin/v1/device/confirm-applied REST route; requires X-TMON-CONFIRM token or read token.
- Admin: Added Provisioning Activity admin UI to view pending queue and history; allow re-enqueue/delete actions.
- Firmware: Device now persists UNIT_ID and WORDPRESS_API_URL, applies staged settings and posts confirm with X-TMON-CONFIRM.

## v0.1.4 - 2025-11-28
- Save & Provision updates tmon_devices mirror and enqueues payloads for both keys.
- Provisioning Activity admin UI added to show queue and history and manage queued payloads.
- Check-in route enhanced to return queued payloads or DB-staged payloads; sets provisioned flags and clears staged state.
- Device confirms applied settings to Admin via protected confirm endpoint.
- DB migrations added to ensure tmon_devices has 'provisioned', 'provisioned_at' and 'wordpress_api_url'.

## v2.01.0 - 2025-11-10

Foundation reboot for Phase 1 (no deletions, additive only):
- Licensing: Added MIT LICENSE at repository root.
- Firmware settings: Expanded `mircopython/settings.py` with provisioning flags, persistent file paths, LoRa network credentials (LORA_NETWORK_NAME/PASSWORD), device suspension flag, OTA parameters, and additional debug categories.
- Debug module: Added `mircopython/debug.py` as a thin wrapper around existing async `utils.debug_print`, enabling category-scoped logging.
- Main firmware: Persist MACHINE_ID on first boot; added suspension checks to skip sampling/LoRa/command polling when suspended; improved first-boot provisioning to persist UNIT_ID when provided.
- Docs: Will update README in subsequent commits as features land in each phase.
- Unit Connector: Fixed improper `wp_localize_script` usage (non-array param) producing WP_Scripts::localize notices; now passes array and adds inline compatibility shim.
- Tests: Extended `tests/harness.py` with ChaCha20 encryption round-trip and nonce derivation tests.

## v.2.00i - 2025-10-17

Firmware (MicroPython):
- Base-managed LoRa sync scheduling
  - Added nextLoraSync default (5 minutes) in settings.py
  - Base assigns per-remote absolute next sync epochs and sends via ACK
  - Overlap avoidance with minimal spacing window (LORA_SYNC_WINDOW)
  - Remotes persist next absolute sync to disk and honor it for future TX windows
  - Fallback probing on remotes before first contact
- LoRa robustness
  - Verifies setBlockingCallback and packet type during init
  - Logs readable error names and device error flags on failures
- WordPress field data delivery
  - Batched file-to-JSON conversion and upload to reduce memory spikes on base
  - Maintains backlog logic and rotates logs after successful delivery
- Version bump banners to v.2.00i across key firmware files

Admin Plugins:
- No changes in this release.

Known issues:
- Lint warnings for MicroPython modules in desktop editor are expected; not applicable on-device.
- Additional memory tuning might be needed for very large field data logs; adjust batch_size in utils.py if needed.

## v2.01.1 - 2025-11-30
- Firmware: Synthesizes staged provisioning payload from check-in metadata (role, plan, unit_name, firmware, site_url).
- Firmware: Persists and reloads WORDPRESS_API_URL prior to each field data send; eliminates repeated missing URL errors.
- Firmware: Added PLAN setting; apply_settings now maps fallback keys (role/unit_name/site_url/plan).
- Admin: Staging events already logged; firmware now confirms applied provisioning via reboot cycle reliably.

## v2.01.2 - 2025-12-01
- Firmware: Added synthesis + persistence of metadata-only provisioning responses (site_url, role, unit_name, plan, firmware).
- Firmware: Soft reboot after first successful metadata persistence (guarded by provision_reboot.flag).
- Firmware: Field data sender now prefers settings.WORDPRESS_API_URL if wprest variable is stale.
- Firmware: Prevent UNIT_ID overwrite with blank unit_id in subsequent responses.
- Docs: Updated README (root + micropython) with new provisioning flow.

## v2.01.3 - 2025-12-01
- Firmware: Restored utils.start_background_tasks and load_persisted_wordpress_api_url.
- Firmware: main.py now imports display_message from oled.
- Runtime: Confirmed dedicated LoRa loop (1s) runs independently of sampling to maintain connection stability.
- Docs: Updated README with background scheduler and loop notes.

## v2.01.4 - 2025-12-01
- Firmware: Added LORA_LOOP_INTERVAL_S to configure dedicated LoRa loop cadence, preserving uninterrupted radio operation.
- Firmware: WiFi node role now runs field-data and command polling tasks similar to base nodes.
- Firmware: OLED operations gated by ENABLE_OLED to avoid unnecessary work when disabled.
- Docs: TODO updated to align with original project scope and prioritized next actions.

## v2.03.0 - YYYY-MM-DD
- Firmware bumped to v2.03.0 (MicroPython) and manifest updated.
- Device endpoint improvements: device/staged-settings endpoint, command lifecycle and staging flow.
- LoRa base: remote telemetry persisted to field logs and per-device settings files; remote samples are evaluated for frost/heat comparisons.
- Devices: staged settings persisted as device_settings-<UNIT_ID>.json and applied safely via settings_apply.
