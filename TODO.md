# TMON Next Steps Implementation Log

## Phase 1: Setup and Infrastructure
- [x] Renamed `mircopython` to `micropython`.
- [x] Added missing placeholder `tmon.py` for frost/heat logic.
- [x] Updated LICENSE file to MIT.
- [x] Implemented modular debug system in `micropython/debug.py`.
- [x] Expanded `micropython/settings.py` with all configuration variables and persistence logic.
- [x] Populated `CHANGELOG.md` with initial release notes.
- [x] Tested structure, debug logging, and settings load/save.

## Phase 2: Firmware Basics
- [x] Implemented MACHINE_ID generation and persistence in `micropython/main.py`.
- [x] Expanded WiFi connection logic in `micropython/wifi.py`.
- [x] Added first-boot and firmware update check in `micropython/main.py`.
- [x] Implemented registration/check-in with Admin in `micropython/main.py`.
- [x] Created main async loop with task flags in `micropython/main.py`.
- [x] Optimized OLED display logic in `micropython/oled.py`.
- [x] Implemented environmental sampling in `micropython/sdata.py`.
- [x] Tested boot sequence and basic device flow.

## Phase 3: LoRa and Node-Specific Logic
- [x] Implemented LoRa basics and security in `micropython/lora.py`.
- [x] Developed remote node logic in `micropython/main.py`.
- [x] Developed base node logic in `micropython/main.py`.
- [x] Implemented frost/heat watch logic in `micropython/tmon.py`.
- [x] Implemented data transmission in `micropython/main.py`.
- [x] Tested multi-node LoRa communication and data relay.

## Phase 4: TMON Admin Plugin
- [x] Installation, schema, device mgmt, data handling, OTA, support, wiki, location hierarchy, APIs, UI polish, versioning, UC shared key, UNIT_ID/MACHINE_ID association, suspend/enable, global monitoring, analytics, firmware/plugin push, wiki sync, dashboards, uptime monitoring, remote settings, support portal, customer hierarchy, secure UC access.

### Issues to Resolve & Polishing Steps
- [ ] Firmware page not displaying (submenu, template, permissions, UI polish).
- [ ] Device location page security error (menu removal, move logic, comments, form polish).
- [ ] Move purge data button/function (to includes/settings.php, UI parity, admin notices).
- [ ] Audit page enhancement (verbosity, filter/search, paginate/export, UI polish).
- [ ] Provisioning page redundancy (unified form, tabs/accordions, polish).
- [ ] Provisioned device actions (buttons, handlers, confirmations, polish).
- [ ] Device registration not showing (queries/joins, insert/display, notices, empty states).
- [ ] Location push logic (accessible via provisioning, comments, autocomplete/validation).
- [ ] Non-functional UC pages (menu registration, templates, permissions, UI polish).

## Phase 5: TMON Unit Connector Plugin
- [x] Installation and key refresh, provisioning API, field data rx/normalize/forward, dashboards/templates polish, periodic check-in & settings update, integration with Admin, UC shared key obtain/refresh, approved-assignments filtering, remote manageability, dashboards/shortcodes, data export & device info, connectivity monitoring/alerting.

## Phase 6: System Integration and Polish
- [ ] Uniform UI/UX (colors, buttons, tables).
- [ ] Tooltips/help/icons, responsiveness/accessibility.
- [ ] Loading spinners and empty states.
- [ ] End-to-end tests, docs/screenshots.

---

## Updated Next Actions (Scope-aligned)

Firmware (Micropython)
- [x] LoRa loop dedicated; disabled for wifi role.
- [x] Persist NODE_TYPE; gate tasks until fully provisioned (flag + URL + UNIT_ID).
- [x] Command polling applies set_var/run_func/firmware_update/relay_ctrl.
- [ ] Add persistence helpers for custom vars changed via set_var.
- [ ] Base <-> Remote LoRa envelopes with HMAC + replay protection; optional encryption.

Admin
- [x] Audit page restored and tables ensured.
- [x] UC endpoints: devices, reprovision, command.
- [ ] Add audit hooks across provisioning save/queue paths.

Unit Connector
- [x] Mirror table ensure; refresh assigned/unassigned.
- [x] Reprovision staging & push to Admin hub.
- [x] Commands page for variables/functions/firmware/relay.
- [ ] Widgets/graphs for device data; relay controls; shortcodes polish.

Docs/QA
- [x] README updated with data flow.
- [ ] Add data flow graphics/screenshots.
- [ ] End-to-end tests for reprovision and command relay via base.

## Testing Log
- [ ] Verify UC refresh populates devices after Admin handoff.
- [ ] Dispatch set_var and run_func; confirm device applied and logs reflect.
- [ ] Verify wifi role disables LoRa and base manages remotes via LoRa.

## Commit Log
- [ ] Commit Admin UC API and UC commands/provisioning updates.
- [ ] Tag minor release after QA.

# TODO

- [x] Mirror provisioned settings to tmon_devices (provisioned, wordpress_api_url, unit_name, provisioned_at) on Save & Provision.
- [x] Migration: add provisioned/provisioned_at/wordpress_api_url columns if missing.
- [x] Deliver staged provisioning to devices (settings_staged).
- [x] Add device confirm endpoint with token; device posts confirm after apply.
- [x] Admin UI Provisioning Activity page with pending queue and history.
- [x] Add history auditing/logging option in Admin.
- [ ] Add per-device HMAC confirmation or device-specific key to confirm endpoint.
- [ ] Add email notifications for provisioning events (optional).
- [ ] Add per-device staging preview and direct push tools in UI.
- [ ] Add tests to verify full provisioning lifecycle.

# TMON Admin — Updated TODO

Completed (from this session)
- Fixed fatal parse error at file end.
- Restored redirect-after-POST in `admin_post_tmon_admin_provision_device`.
- Added firmware fields and GitHub manifest fetch (AJAX: `tmon_admin_fetch_github_manifest`).
- Added migrations: normalized IDs, firmware metadata, settings_staged, device mirror columns.
- Queue helpers: enqueue/dequeue/lookup by normalized keys.
- Diagnostics: known IDs refresh, queue/DB staging check, API calls and provisioning history tables.
- Claims approval/denial flow and provisioning history page.

High-priority
- Define missing vars in inline update branch in provisioning page.
- Validate nonce usage across forms/handlers.
- Confirm device-side queue consumption and normalized key matching.

Medium
- Device mirror consistency updates and backfills.
- Admin notices reliability.
- Hierarchy Sync audit logs.

Lower-priority
- UX: typeahead for Known IDs; loading spinners.
- Security: verify cross-site tokens and rotation.
- Maintenance: centralize purge ops in settings.php; docs.
- Docs: admin guide for provisioning workflow and diagnostics.

Notes
- Migrations idempotent; keep in `admin_init`.
- Unique index `unit_machine (unit_id, machine_id)` ensures deduplication; ensure updates match normalized columns.

Unit Connector — Configuration UI and Staging
- [x] Create Device Configuration admin page (menu: TMON Devices → Settings) that renders a form for core variables from micropython/settings.py.
- [x] Add a settings schema mapper in UC (PHP) to describe types, defaults, help text, and constraints for key firmware variables.
- [x] Persist posted values as staged settings (DB: tmon_uc_devices.staged_settings + staged_at).
- [x] Expose staged settings via UC REST:
  - GET /wp-json/tmon/v1/admin/device/settings-staged → returns JSON
  - POST /wp-json/tmon/v1/admin/device/settings-applied → device confirms apply
- [ ] Extend schema coverage to all firmware variables and advanced types (arrays/maps), with JSON validation.
- [ ] Admin hub integration button to push staged settings to Admin hub (optional).

UC Pairings and Device Listing
- [x] Add cron-like refresh from Admin hub to backfill UC mirror (hourly).
- [ ] Add settings to control refresh cadence (hourly/daily/off) and diagnostics.

REST and Admin-post Endpoints (UC)
- [x] Admin push handler for staged settings → Admin hub reprovision endpoint.
- [ ] Add retry/backoff and result notice details.

TMON Admin — Fixes
- [x] Fallback tmon_admin_provisioned_devices_page to prevent missing-callback fatal.
- [ ] Wire full provisioning page to includes/provisioning.php and remove fallback after verification.

Unit Connector — Notices and Pairing
- [x] Make admin notices dismissible and auto-hide.
- [x] Store normalized hub URL with pairing diagnostics in settings.

Firmware (Micropython) — Optimization Plan
- [ ] Implement compact telemetry keys and conditional inclusion (skip zeros/defaults).
- [ ] Single scheduler guard: prevent duplicate background tasks across main/startup/utils.
- [ ] OLED/debug output bounded and non-blocking; centralize through utils.
- [ ] Add adaptive upload backpressure: reduce batch size on errors/low memory.

Testing
- [ ] Verify UC hourly backfill populates devices when Admin is reachable.
- [ ] Verify Push-to-Admin triggers reprovision queue and devices receive staged settings.

TMON Admin — Provisioned Devices
- [x] Render table with joined fields and fallback to UC hub when local table is missing.
- [x] Update DB on device confirm-applied: set provisioned, site_url, clear queued payloads.
- [x] Add canBill column and set true on claim approval (hook-based).

Unit Connector — Settings Page
- [x] Remove duplicate element IDs (avoid multiple id="submit"/"_wpnonce").
- [ ] Load hierarchy map JS only when Leaflet is present; suppress console noise.

Command Flow (v2.00m review)
- [ ] Verify command generation (relay on/off) format and endpoint usage in UC/Admin.
- [ ] Ensure device firmware processes commands correctly (WiFi/LoRa paths) and posts confirmations.
- [ ] Add command result logging to Admin/UC with status, timing, and device acknowledgements.
- [ ] UI: add per-device command history table and current relay states.

Billing (future)
- [ ] Build billing scheduler: start when canBill=true, track cycles and usage.
- [ ] UI: billing status per device; export/report.

Testing
- [ ] E2E: claim → canBill toggle → confirm-applied → provisioned table updates.
- [ ] Commands: dispatch relay toggle, confirm back via device, logs reflected in Admin/UC.

## Release Bump
- MicroPython Firmware: v2.02.0
  - Changes: corrected timestamps (Unix-epoch helper), staged settings fetch/apply path hooks, debug and OLED gating, backpressure prep for uploads.
- TMON Admin: 0.2.0
  - Changes: Provisioned Devices table rendering, device confirm-applied sync (provisioned/site_url/clear queue), UC pairing endpoint, canBill column migration and claim hook.
- TMON Unit Connector: 0.2.0
  - Changes: Settings schema + staged configuration UI, REST endpoints for staged/applied settings, pairing diagnostics, Admin push handler, hourly backfill refresh from Admin.

## OTA / Repository Update Process Enhancements
- [x] Firmware version updated in micropython/settings.py (v2.02.0).
- [ ] Ensure OTA manifest.json includes version v2.02.0 and updated file hashes.
- [ ] Verify version.txt reflects v2.02.0 for lightweight checks.
- [ ] Confirm OTA client respects manifest HMAC (optional) and size caps.
- [ ] Add CI step to validate manifest/version alignment and file integrity before tagging.
- [ ] Document OTA rollback process in README and CHANGELOG.

## CHANGELOG (to be added in repo)
- v2.02.0 (Firmware)
  - Fixed timestamp generation across logs.
  - Added staged settings flow integration with UC/Admin.
  - Prepared adaptive upload/backpressure hooks.
- 0.2.0 (Admin/UC)
  - Admin: Provisioned Devices page restored; device confirm-applied updates; UC pairing API.
  - UC: Staged settings form; REST endpoints; pairing diagnostics; Admin push.

## Upgrade Notes
- Devices will detect v2.02.0 via version.txt and manifest.json; ensure both are published before rollout.
- Admin/UC plugins should be upgraded together to 0.2.0 to keep pairing/staged settings features compatible.
- After upgrade, re-pair UC with Admin to populate hub_key/read_token and normalized pairing store.

Admin — Provisioning History
- [x] Add renderer to display latest actions; verify table exists.

Unit Connector — Post-provisioning
- [x] Normalize URL helper defined early to avoid fatal.
- [x] Ensure command table includes status; fix requeue cron UPDATE.
- [x] First check-in REST: call Admin to confirm and upsert UC cache; mark claimed.
- [x] Shortcode: claim device by UNIT_ID + MACHINE_ID using first-checkin flow.
- [x] Backfill provisioned devices after pairing and on page load if empty.

Commands
- [x] Stage commands in UC, devices poll, confirm applied; add cron requeue for stale claimed.
- [ ] Add Admin-side mirror/log viewer for commands (status timeline).

White screen on Save & Provision
- [x] Force redirect-after-POST in handler to avoid blank page; add safe fallback redirect.

Verification
- [ ] UC pairing populates hub_key/read_token; Provisioned Devices page shows devices post-backfill.
- [ ] Admin offline notice cleared via UC/device check-ins (last_seen updated).
- [ ] Relay commands toggle: staged, device executes, confirmation recorded.

Fixes logged
- [x] Guard $wpdb in Admin db helpers to avoid undefined warnings.
- [x] Check column existence before ALTER to prevent duplicate-column errors.
- [x] Define tmon_uc_normalize_url early in UC includes to avoid fatal.

Pending (from conversation)
- [ ] Provisioning History: ensure table tmon_provision_history exists and is populated on each queue/confirm step.
- [ ] UC connection (v2.00m parity): align pairing, first-checkin claim, and Admin→UC device record push; verify device mirror populated.
- [ ] Commands: stage from Admin shortcode buttons, device polls via UC, executes, and confirms; add Admin/UC logs and UI.
- [ ] Save & Provision: enforce redirect-after-POST; surface admin notices and errors.
- [ ] UC Settings: show all firmware settings (typed + raw JSON), default Admin API URL to home_url().
- [ ] Admin offline notice: update last_seen via UC heartbeat/check-in.

TMON Admin — Firmware Fetch
- [x] AJAX handler uses fallback mirrors with headers to avoid GitHub 400s.
- [ ] Add admin UI notice for manifest/version and last fetch time.

TMON Admin — Provisioned Devices
- [x] Ensure menu callback exists and delegates to renderer.
- [x] Renderer shows provisioned devices with canBill and staged flags.
- [x] Save & Provision handler always redirects (no white screen).

Unit Connector — Command Table & Cron
- [x] Normalize URL helper defined early (prevents fatal).
- [x] Ensure tmon_device_commands table schema includes status column.
- [x] Requeue cron safely updates claimed → queued when stale.

Firmware — Version & OTA
- [x] Bump to v2.02.1.
- [x] Add OTA fallback mirrors and headers.

Verification
- [ ] Firmware metadata fetch works via AJAX (no 400).
- [ ] Provisioned Devices page loads without fatal and displays rows.
- [ ] Pairing/backfill populates UC devices; Admin offline notice clears via check-ins.
- [ ] Commands staged → polled → executed → confirmed flow visible in UC/Admin logs.

TMON Admin — Provisioning Save
- [x] Persist Save & Provision to tmon_provisioned_devices and mirror to tmon_devices.
- [x] Redirect-after-POST with success/failure notice.

Unit Connector — Pairing Persistence
- [x] Persist hub_key/read_token and normalized pairing.
- [x] Backfill devices after pairing.

Verification
- [ ] Save & Provision updates DB rows and shows queued notice.
- [ ] UC pairing creates records and devices backfill visible on UC provisioned page.
- [ ] Device first check-in claims via Admin confirm and updates UC mirror.
- [ ] Commands staged, polled, executed, confirmed; status visible.

TMON Admin — Provisioning Save & History
- [x] Persist Save & Provision into tmon_provisioned_devices and mirror into tmon_devices.
- [x] Append provisioning history on save and device confirm; render History page.
- [x] Enforce redirect-after-POST to avoid blank page; show queued/failed notice.

Unit Connector — Pairing & Backfill
- [x] Persist hub_key/read_token; normalized pairing record.
- [x] Backfill provisioned devices from Admin after pairing.

Firmware/OTA
- [x] v2.02.1 settings and OTA mirrors; headers for fetch stability.

Verification
- [ ] Save & Provision updates DB and history; queued notice visible.
- [ ] UC pairing creates records on both sides; UC provisioned page shows devices.
- [ ] First device check-in triggers Admin confirm and UC claim; mirrors updated.
- [ ] Commands staged/polled/executed/confirmed; status reflects in UC/Admin.

Open items
- [ ] Add Admin UI notices for firmware manifest/version and last fetch timestamp.
- [ ] Add Admin/UC command logs viewer with status timeline and filters.

# TMON Admin — Provisioning
- [x] Fix parse error in includes/provisioning.php (short array → array(), balanced brackets).
- [x] Persist Save & Provision and append history; redirect with queued/failed.
- [x] Provisioned Devices page callback delegates to renderer; no invalid callback fatal.

Verification
- [ ] Save & Provision writes to tmon_provisioned_devices and tmon_devices; history row added.
- [ ] Provisioning History page lists latest actions.
- [ ] Devices that confirm-applied update records and history.
- [ ] UC pairing persists on both sides; UC backfills devices.
