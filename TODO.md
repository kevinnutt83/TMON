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
- [x] Firmware page not displaying (submenu, template, permissions, UI polish).
- [x] Device location page security error (menu removal, move logic, comments, form polish).
- [x] Move purge data button/function (to includes/settings.php, UI parity, admin notices).
- [x] Audit page enhancement (verbosity, filter/search, paginate/export, UI polish).
- [x] Provisioning page redundancy (unified form, tabs/accordions, polish).
- [x] Provisioned device actions (buttons, handlers, confirmations, polish).
- [x] Device registration not showing (queries/joins, insert/display, notices, empty states).
- [x] Location push logic (accessible via provisioning, comments, autocomplete/validation).
- [x] Non-functional UC pages (menu registration, templates, permissions, UI polish).

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
- [ ] Add persistence helpers for custom vars changed via set_var.
- [ ] Base <-> Remote LoRa envelopes with HMAC + replay protection; optional encryption.

Admin
- [ ] Add audit hooks across provisioning save/queue paths.

Unit Connector
- [ ] Widgets/graphs for device data; relay controls; shortcodes polish.

Docs/QA
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
- [ ] Add per-device HMAC confirmation or device-specific key to confirm endpoint.
- [ ] Add email notifications for provisioning events (optional).
- [ ] Add per-device staging preview and direct push tools in UI.
- [ ] Add tests to verify full provisioning lifecycle.

# TMON Admin — Updated TODO

High-priority
- [x] Define missing vars in inline update branch in provisioning page.
- [x] Validate nonce usage across forms/handlers.
- [ ] Confirm device-side queue consumption and normalized key matching.

Medium
- [ ] Device mirror consistency updates and backfills.
- [ ] Admin notices reliability.
- [ ] Hierarchy Sync audit logs.

Lower-priority
- [ ] UX: typeahead for Known IDs; loading spinners.
- [ ] Security: verify cross-site tokens and rotation.
- [ ] Maintenance: centralize purge ops in settings.php; docs.
- [ ] Docs: admin guide for provisioning workflow and diagnostics.

Notes
- Migrations idempotent; keep in `admin_init`.
- Unique index `unit_machine (unit_id, machine_id)` ensures deduplication; ensure updates match normalized columns.

Unit Connector — Configuration UI and Staging
- [ ] Extend schema coverage to all firmware variables and advanced types (arrays/maps), with JSON validation.
- [ ] Admin hub integration button to push staged settings to Admin hub (optional).

UC Pairings and Device Listing
- [ ] Add settings to control refresh cadence (hourly/daily/off) and diagnostics.

REST and Admin-post Endpoints (UC)
- [ ] Add retry/backoff and result notice details.

TMON Admin — Fixes
- [ ] Wire full provisioning page to includes/provisioning.php and remove fallback after verification.

Unit Connector — Notices and Pairing
- [ ] (no pending items)

Firmware (Micropython) — Optimization Plan
- [ ] Implement compact telemetry keys and conditional inclusion (skip zeros/defaults).
- [ ] Single scheduler guard: prevent duplicate background tasks across main/startup/utils.
- [ ] OLED/debug output bounded and non-blocking; centralize through utils.
- [ ] Add adaptive upload backpressure: reduce batch size on errors/low memory.

Testing
- [ ] Verify UC hourly backfill populates devices when Admin is reachable.
- [ ] Verify Push-to-Admin triggers reprovision queue and devices receive staged settings.

TMON Admin — Provisioned Devices
- [ ] (no pending items beyond other sections)

Unit Connector — Settings Page
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
- [x] Ensure OTA manifest.json includes version v2.02.2 and updated file hashes.
- [x] Verify version.txt reflects v2.02.2 for lightweight checks.
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
- Session removals (pruned from TODO for clarity)
  - Setup & Infrastructure: rename to micropython, LICENSE → MIT, debug system, expanded settings with persistence, CHANGELOG seeded, initial testing.
  - Firmware Basics: MACHINE_ID persistence, WiFi logic, first-boot + OTA check, admin registration/check-in, async loop/task flags, OLED optimization, environmental sampling, boot flow tests.
  - LoRa & Node Logic: LoRa security/basics, remote/base node logic, frost/heat watch, data relay, multi-node communication tests.
  - Admin fixes: audit page restore, UC endpoints (devices/reprovision/command), migrations for normalized IDs, firmware metadata, settings_staged, device mirror columns, history page renderer.
  - Unit Connector: mirror ensure/refresh, reprovision staging + push to Admin, commands page, pairing helper/shortcodes, cron requeue safety.
  - White screen fix: enforced redirect-after-POST on Save & Provision.
  - DB schema guards: column existence checks for commands/status/updated_at and OTA/action.
  - Firmware/OTA: version bumps to v2.02.1, OTA mirrors/headers for stable fetch.

## Upgrade Notes
- Devices will detect v2.02.0 via version.txt and manifest.json; ensure both are published before rollout.
- Admin/UC plugins should be upgraded together to 0.2.0 to keep pairing/staged settings features compatible.
- After upgrade, re-pair UC with Admin to populate hub_key/read_token and normalized pairing store.

Admin — Provisioning History
- [ ] (no pending items)

Unit Connector — Post-provisioning
- [ ] (no pending items)

Commands
- [ ] Add Admin-side mirror/log viewer for commands (status timeline).

White screen on Save & Provision
- [ ] (no pending items)

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
- [ ] Add admin UI notice for manifest/version and last fetch time.

TMON Admin — Provisioned Devices
- [ ] (no pending items beyond other sections)

Unit Connector — Command Table & Cron
- [ ] (no pending items beyond other sections)

Firmware — Version & OTA
- [ ] (no pending items beyond OTA section)

Verification
- [ ] Firmware metadata fetch works via AJAX (no 400).
- [ ] Provisioned Devices page loads without fatal and displays rows.
- [ ] Pairing/backfill populates UC devices; Admin offline notice clears via check-ins.
- [ ] Commands staged → polled → executed → confirmed flow visible in UC/Admin logs.

TMON Admin — Provisioning Save
- [ ] (no pending items)

Unit Connector — Pairing Persistence
- [ ] (no pending items)

TMON Admin — Provisioning Save & History
- [ ] (no pending items)

Unit Connector — Pairing & Backfill
- [ ] (no pending items)

Firmware/OTA
- [ ] (no pending items beyond OTA section)

Open items
- [ ] Add Admin UI notices for firmware manifest/version and last fetch timestamp.
- [ ] Add Admin/UC command logs viewer with status timeline and filters.

# TMON Admin — Provisioning
- [ ] (no pending items beyond provisioning sections)

# TMON Implementation Tracker

Completed
- Provisioning UI: Restored legacy form structure; integrated Save & Provision logic and notices.
- Provisioning: CSV export for provisioning history added (Export History link).
- Admin: Compact UI assets enqueued; modal JS remains available for list/commands.
- Admin: Command Logs page with filter + CSV export; AJAX endpoint reads tmon_device_commands.
- Firmware/Admin/UC: Removed JWT usage; switched to native WP auth (Application Passwords) where needed.
- UC: v2.00m REST endpoints loaded; optional Basic Auth guard added.

Pending verification
- Save & Provision persists rows and appends history; queued/failed notice visible.
- Provisioning History page renders cleanly and CSV export works.
- UC pairing persists on both sides; devices backfill visible in UC cache.
- Device first check-in confirms/applies; UC mirror updated.
- Commands staged→polled→executed→confirmed; visible in Command Logs.

Next
- Validate Basic Auth configuration on UC (TMON_UC_REQUIRE_APP_PASSWORD option/constant).
- Confirm manifest fetch sets version/time transients and notice displays on Admin pages.

# TMON Admin & Unit Connector – Implementation Tracker (Consolidated)

Status summary
- Pairing completed but UC not listed in Admin.
- Multiple admin pages show placeholders or fatal errors.
- Command logs schema mismatches (status column missing).
- Provisioning callbacks missing or using invalid function names.
- Shortcodes not rendering; UC REST include collisions; CSS overlaying admin menu.
- JWT removed; migrate to native WP Application Passwords verified in firmware.

Priorities (P0 = critical, P1 = high, P2 = normal)

P0 – Critical fixes
- Pairing visibility in Admin:
  - Ensure tmon-admin shows paired Unit Connectors under “Registered Unit Connectors”.
  - Read from pairing storage (options or tmon_uc_sites table) and render normalized Hub URL, paired time, tokens.
  - Verify capability mapping so plugin users with tmon_view_devices see paired UCs.

- Menu and pages wire-up:
  - Move “TMON Command Logs” under TMON Admin submenu.
  - Ensure main “TMON Admin” menu links to dashboard page rendering:
    - Tables: Unit Connectors + status + last check-in.
    - Device alerts and health (device/network/connection KPIs).
    - Scrollable logs area; hyperlink keys to device/UC detail pages.

- Firmware page:
  - Display current TMON version (read transients or option).
  - Fetch repository README.md and render content.
  - Provide links to download current MicroPython firmware files from repository (manifest-driven).

- Provisioning pages:
  - Fix callbacks: implement tmon_admin_provisioning_activity_page and tmon_admin_provisioning_history_page.
  - Resolve warnings Undefined array keys: guard access for id and settings_staged in includes/provisioning.php.
  - Ensure queue updates/clears after device provisioning; add job to clear claimed/applied items and UI refresh.

- Notifications page:
  - Replace placeholder “Ensure includes/notifications.php is active” with live list:
    - Unread + recent logs, SSE stream status, filters, mark-as-read, export.
    - Use existing tmon_notifications table and rendering helpers.

- OTA admin page:
  - Replace placeholder; render OTA logs and actions:
    - Commands: download device logs, reboot device, update firmware, clear logs (preserve settings/provisioning), etc.
    - Show job queue, last run, error messages.

- Files admin page:
  - Replace placeholder; render uploaded user files list with actions:
    - Send to device, run as MicroPython script, function override notes, dependency merge hints.
    - Provide secure download and “load with custom logic” toggle.
    - Display execution policy and override safeguards.

- Groups admin page:
  - Render hierarchy Companies > Locations > Zones > Groups > Devices.
  - Provide CRUD and drag-and-drop organization; link devices to groups.

- Provisioned device admin page:
  - Fix “Renderer not loaded.” – ensure renderer function exists and hooked to the page slug.
  - Render provisioned devices list with filters, details modal, health status.

- CSS overlay fix:
  - Fix provisioning page CSS overlaying admin left menu; adjust container top/left padding and z-index.
  - Audit .tmon-provision-grid and modal to avoid fixed positioning collisions.

- Remove deprecated page:
  - Remove “Device location” admin page.

- DB schema fix – command logs:
  - Add status column to tmon_device_commands (Admin) and Unit Connector tables if absent.
  - Migrate and back-fill workflow: staged → queued → claimed → applied → failed.
  - Update requeue cron queries to use existing columns safely (guards when status column missing).

- UC include collisions:
  - Prevent redeclare errors: guard function_exists for tmon_uc_pull_install and class_exists TMON_AI.
  - Single-include v2-api with define guard.
  - Ensure shortcodes registered and frontend JS enqueued or localized AJAX URL.

P1 – High-priority improvements
- Add “Clear Audit Log” button beside “Purge Data” on settings page:
  - Wire to admin_post action clearing tmon_admin audit logs table.
  - Add “Export CSV” button on audit log admin page to export all entries.

- Command Logs CSV export:
  - Fix SQL to avoid missing status column.
  - Add CSV export endpoint and button.

- Admin Notices:
  - Ensure firmware fetch AJAX sets transients and notice renders without parse errors.
  - Fix parse errors in includes/provisioning.php (clean echo blocks).

- JWT removal follow-through:
  - Confirm all endpoints/auth use native WP Application Passwords where required.
  - Remove residual JWT paths and logic from Admin/UC code.

P2 – Normal maintenance and UX
- Add hyperlinks across tables for drill-down (devices, UCs, sites, companies).
- Improve error messaging in pages for clearer diagnostics.
- Add job/history export for provisioning activity.

Action checklist

1) Pairing display and Admin dashboard
- Query paired UCs storage and render in Admin dashboard.
- Ensure capabilities allow non-admin plugin users to view.

2) Menus and pages
- Register “TMON Command Logs” as submenu under TMON Admin.
- Implement dashboard renderer: UCs, device alerts, KPIs, logs with hyperlinks.

3) Firmware page
- Read TMON version from option/transient.
- Fetch README.md via GitHub raw URL; render markdown (simple sanitized HTML).
- Link to current firmware files per manifest.

4) Provisioning pages
- Implement missing functions: tmon_admin_provisioning_activity_page, tmon_admin_provisioning_history_page.
- Add null/array key guards for id and settings_staged.
- Fix CSS overlay; adjust layout container padding.
- Ensure queue worker clears staged/applied; refresh counts.

5) Notifications
- Render unread notifications and logs; SSE heartbeat status.
- Filters and mark-as-read UX.

6) OTA page
- Render logs; actions for device commands (download logs, reboot, update firmware, clear logs preserving settings).
- Show OTA job queue and last runs.

7) Files page
- Render uploaded files table with actions.
- Safe execution policy details and override mechanism docs.

8) Groups page
- Implement hierarchy rendering and CRUD.

9) Provisioned devices page
- Implement renderer to list devices with filters and modal.

10) DB schema – Command logs
- Add status column if absent:
  - ALTER TABLE {prefix}tmon_device_commands ADD COLUMN status varchar(32) DEFAULT 'staged';
  - Same for UC table if needed.
- Update cron queries to guard when status not present and migrate to new column.

11) UC guards and shortcodes
- Guard function/class redeclarations in includes/v2-api.php.
- Include v2-api once.
- Register shortcodes: [tmon_device_list], [tmon_device_status]; ensure AJAX URL localization.

12) Parse errors and warnings
- Fix parse/echo blocks in tmon-admin/includes/provisioning.php.
- Verify admin_notices blocks and enqueue functions use balanced PHP.

13) Remove Device location admin page
- Unregister/remove the page from admin menu.

14) CSV exports
- Add “Export CSV” to Audit Log and Command Logs pages.

Verification plan
- Visit Admin dashboard and confirm paired UCs listed.
- Open each Admin page: dashboards, notifications, OTA, files, groups, provisioning, provisioned devices – ensure content renders.
- Trigger provisioning queue and observe processing + clearing.
- Confirm command logs schema; requeue cron runs without DB errors.
- Run CSV exports; confirm file download and encoding.
- Confirm shortcodes render on frontend.
- Confirm Application Password auth on UC endpoints works (no JWT refs).

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
- [ ] Add persistence helpers for custom vars changed via set_var.
- [ ] Base <-> Remote LoRa envelopes with HMAC + replay protection; optional encryption.

Admin
- [ ] Add audit hooks across provisioning save/queue paths.

Unit Connector
- [ ] Widgets/graphs for device data; relay controls; shortcodes polish.

Docs/QA
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
- [ ] Add per-device HMAC confirmation or device-specific key to confirm endpoint.
- [ ] Add email notifications for provisioning events (optional).
- [ ] Add per-device staging preview and direct push tools in UI.
- [ ] Add tests to verify full provisioning lifecycle.

# TMON Admin — Updated TODO

High-priority
- [x] Define missing vars in inline update branch in provisioning page.
- [ ] Validate nonce usage across forms/handlers.
- [ ] Confirm device-side queue consumption and normalized key matching.

Medium
- [ ] Device mirror consistency updates and backfills.
- [ ] Admin notices reliability.
- [ ] Hierarchy Sync audit logs.

Lower-priority
- [ ] UX: typeahead for Known IDs; loading spinners.
- [ ] Security: verify cross-site tokens and rotation.
- [ ] Maintenance: centralize purge ops in settings.php; docs.
- [ ] Docs: admin guide for provisioning workflow and diagnostics.

Notes
- Migrations idempotent; keep in `admin_init`.
- Unique index `unit_machine (unit_id, machine_id)` ensures deduplication; ensure updates match normalized columns.

Unit Connector — Configuration UI and Staging
- [ ] Extend schema coverage to all firmware variables and advanced types (arrays/maps), with JSON validation.
- [ ] Admin hub integration button to push staged settings to Admin hub (optional).

UC Pairings and Device Listing
- [ ] Add settings to control refresh cadence (hourly/daily/off) and diagnostics.

REST and Admin-post Endpoints (UC)
- [ ] Add retry/backoff and result notice details.

TMON Admin — Fixes
- [ ] Wire full provisioning page to includes/provisioning.php and remove fallback after verification.

Unit Connector — Notices and Pairing
- [ ] (no pending items)

Firmware (Micropython) — Optimization Plan
- [ ] Implement compact telemetry keys and conditional inclusion (skip zeros/defaults).
- [ ] Single scheduler guard: prevent duplicate background tasks across main/startup/utils.
- [ ] OLED/debug output bounded and non-blocking; centralize through utils.
- [ ] Add adaptive upload backpressure: reduce batch size on errors/low memory.

Testing
- [ ] Verify UC hourly backfill populates devices when Admin is reachable.
- [ ] Verify Push-to-Admin triggers reprovision queue and devices receive staged settings.

TMON Admin — Provisioned Devices
- [ ] (no pending items beyond other sections)

Unit Connector — Settings Page
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
- Session removals (pruned from TODO for clarity)
  - Setup & Infrastructure: rename to micropython, LICENSE → MIT, debug system, expanded settings with persistence, CHANGELOG seeded, initial testing.
  - Firmware Basics: MACHINE_ID persistence, WiFi logic, first-boot + OTA check, admin registration/check-in, async loop/task flags, OLED optimization, environmental sampling, boot flow tests.
  - LoRa & Node Logic: LoRa security/basics, remote/base node logic, frost/heat watch, data relay, multi-node communication tests.
  - Admin fixes: audit page restore, UC endpoints (devices/reprovision/command), migrations for normalized IDs, firmware metadata, settings_staged, device mirror columns, history page renderer.
  - Unit Connector: mirror ensure/refresh, reprovision staging + push to Admin, commands page, pairing helper/shortcodes, cron requeue safety.
  - White screen fix: enforced redirect-after-POST on Save & Provision.
  - DB schema guards: column existence checks for commands/status/updated_at and OTA/action.
  - Firmware/OTA: version bumps to v2.02.1, OTA mirrors/headers for stable fetch.

## Upgrade Notes
- Devices will detect v2.02.0 via version.txt and manifest.json; ensure both are published before rollout.
- Admin/UC plugins should be upgraded together to 0.2.0 to keep pairing/staged settings features compatible.
- After upgrade, re-pair UC with Admin to populate hub_key/read_token and normalized pairing store.

Admin — Provisioning History
- [ ] (no pending items)

Unit Connector — Post-provisioning
- [ ] (no pending items)

Commands
- [ ] Add Admin-side mirror/log viewer for commands (status timeline).

White screen on Save & Provision
- [ ] (no pending items)

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
- [ ] Add admin UI notice for manifest/version and last fetch time.

TMON Admin — Provisioned Devices
- [ ] (no pending items beyond other sections)

Unit Connector — Command Table & Cron
- [ ] (no pending items beyond other sections)

Firmware — Version & OTA
- [ ] (no pending items beyond OTA section)

Verification
- [ ] Firmware metadata fetch works via AJAX (no 400).
- [ ] Provisioned Devices page loads without fatal and displays rows.
- [ ] Pairing/backfill populates UC devices; Admin offline notice clears via check-ins.
- [ ] Commands staged → polled → executed → confirmed flow visible in UC/Admin logs.

TMON Admin — Provisioning Save
- [ ] (no pending items)

Unit Connector — Pairing Persistence
- [ ] (no pending items)

TMON Admin — Provisioning Save & History
- [ ] (no pending items)

Unit Connector — Pairing & Backfill
- [ ] (no pending items)

Firmware/OTA
- [ ] (no pending items beyond OTA section)

Open items
- [ ] Add Admin UI notices for firmware manifest/version and last fetch timestamp.
- [ ] Add Admin/UC command logs viewer with status timeline and filters.

# TMON Admin — Provisioning
- [ ] (no pending items beyond provisioning sections)

# TMON Implementation Tracker

Completed
- Provisioning UI: Restored legacy form structure; integrated Save & Provision logic and notices.
- Provisioning: CSV export for provisioning history added (Export History link).
- Admin: Compact UI assets enqueued; modal JS remains available for list/commands.
- Admin: Command Logs page with filter + CSV export; AJAX endpoint reads tmon_device_commands.
- Firmware/Admin/UC: Removed JWT usage; switched to native WP auth (Application Passwords) where needed.
- UC: v2.00m REST endpoints loaded; optional Basic Auth guard added.

Pending verification
- Save & Provision persists rows and appends history; queued/failed notice visible.
- Provisioning History page renders cleanly and CSV export works.
- UC pairing persists on both sides; devices backfill visible in UC cache.
- Device first check-in confirms/applies; UC mirror updated.
- Commands staged→polled→executed→confirmed; visible in Command Logs.

Next
- Validate Basic Auth configuration on UC (TMON_UC_REQUIRE_APP_PASSWORD option/constant).
- Confirm manifest fetch sets version/time transients and notice displays on Admin pages.

# TMON Admin & Unit Connector – Implementation Tracker (Consolidated)

Status summary
- Pairing completed but UC not listed in Admin.
- Multiple admin pages show placeholders or fatal errors.
- Command logs schema mismatches (status column missing).
- Provisioning callbacks missing or using invalid function names.
- Shortcodes not rendering; UC REST include collisions; CSS overlaying admin menu.
- JWT removed; migrate to native WP Application Passwords verified in firmware.

Priorities (P0 = critical, P1 = high, P2 = normal)

P0 – Critical fixes
- Pairing visibility in Admin:
  - Ensure tmon-admin shows paired Unit Connectors under “Registered Unit Connectors”.
  - Read from pairing storage (options or tmon_uc_sites table) and render normalized Hub URL, paired time, tokens.
  - Verify capability mapping so plugin users with tmon_view_devices see paired UCs.

- Menu and pages wire-up:
  - Move “TMON Command Logs” under TMON Admin submenu.
  - Ensure main “TMON Admin” menu links to dashboard page rendering:
    - Tables: Unit Connectors + status + last check-in.
    - Device alerts and health (device/network/connection KPIs).
    - Scrollable logs area; hyperlink keys to device/UC detail pages.

- Firmware page:
  - Display current TMON version (read transients or option).
  - Fetch repository README.md and render content.
  - Provide links to download current MicroPython firmware files from repository (manifest-driven).

- Provisioning pages:
  - Fix callbacks: implement tmon_admin_provisioning_activity_page and tmon_admin_provisioning_history_page.
  - Resolve warnings Undefined array keys: guard access for id and settings_staged in includes/provisioning.php.
  - Ensure queue updates/clears after device provisioning; add job to clear claimed/applied items and UI refresh.

- Notifications page:
  - Replace placeholder “Ensure includes/notifications.php is active” with live list:
    - Unread + recent logs, SSE stream status, filters, mark-as-read, export.
    - Use existing tmon_notifications table and rendering helpers.

- OTA admin page:
  - Replace placeholder; render OTA logs and actions:
    - Commands: download device logs, reboot device, update firmware, clear logs (preserve settings/provisioning), etc.
    - Show job queue, last run, error messages.

- Files admin page:
  - Replace placeholder; render uploaded user files list with actions:
    - Send to device, run as MicroPython script, function override notes, dependency merge hints.
    - Provide secure download and “load with custom logic” toggle.
    - Display execution policy and override safeguards.

- Groups admin page:
  - Render hierarchy Companies > Locations > Zones > Groups > Devices.
  - Provide CRUD and drag-and-drop organization; link devices to groups.

- Provisioned device admin page:
  - Fix “Renderer not loaded.” – ensure renderer function exists and hooked to the page slug.
  - Render provisioned devices list with filters, details modal, health status.

- CSS overlay fix:
  - Fix provisioning page CSS overlaying admin left menu; adjust container top/left padding and z-index.
  - Audit .tmon-provision-grid and modal to avoid fixed positioning collisions.

- Remove deprecated page:
  - Remove “Device location” admin page.

- DB schema fix – command logs:
  - Add status column to tmon_device_commands (Admin) and Unit Connector tables if absent.
  - Migrate and back-fill workflow: staged → queued → claimed → applied → failed.
  - Update requeue cron queries to use existing columns safely (guards when status column missing).

- UC include collisions:
  - Prevent redeclare errors: guard function_exists for tmon_uc_pull_install and class_exists TMON_AI.
  - Single-include v2-api with define guard.
  - Ensure shortcodes registered and frontend JS enqueued or localized AJAX URL.

P1 – High-priority improvements
- Add “Clear Audit Log” button beside “Purge Data” on settings page:
  - Wire to admin_post action clearing tmon_admin audit logs table.
  - Add “Export CSV” button on audit log admin page to export all entries.

- Command Logs CSV export:
  - Fix SQL to avoid missing status column.
  - Add CSV export endpoint and button.

- Admin Notices:
  - Ensure firmware fetch AJAX sets transients and notice renders without parse errors.
  - Fix parse errors in includes/provisioning.php (clean echo blocks).

- JWT removal follow-through:
  - Confirm all endpoints/auth use native WP Application Passwords where required.
  - Remove residual JWT paths and logic from Admin/UC code.

P2 – Normal maintenance and UX
- Add hyperlinks across tables for drill-down (devices, UCs, sites, companies).
- Improve error messaging in pages for clearer diagnostics.
- Add job/history export for provisioning activity.

Action checklist

1) Pairing display and Admin dashboard
- Query paired UCs storage and render in Admin dashboard.
- Ensure capabilities allow non-admin plugin users to view.

2) Menus and pages
- Register “TMON Command Logs” as submenu under TMON Admin.
- Implement dashboard renderer: UCs, device alerts, KPIs, logs with hyperlinks.

3) Firmware page
- Read TMON version from option/transient.
- Fetch README.md via GitHub raw URL; render markdown (simple sanitized HTML).
- Link to current firmware files per manifest.

4) Provisioning pages
- Implement missing functions: tmon_admin_provisioning_activity_page, tmon_admin_provisioning_history_page.
- Add null/array key guards for id and settings_staged.
- Fix CSS overlay; adjust layout container padding.
- Ensure queue worker clears staged/applied; refresh counts.

5) Notifications
- Render unread notifications and logs; SSE heartbeat status.
- Filters and mark-as-read UX.

6) OTA page
- Render logs; actions for device commands (download logs, reboot, update firmware, clear logs preserving settings).
- Show OTA job queue and last runs.

7) Files page
- Render uploaded files table with actions.
- Safe execution policy details and override mechanism docs.

8) Groups page
- Implement hierarchy rendering and CRUD.

9) Provisioned devices page
- Implement renderer to list devices with filters and modal.

10) DB schema – Command logs
- Add status column if absent:
  - ALTER TABLE {prefix}tmon_device_commands ADD COLUMN status varchar(32) DEFAULT 'staged';
  - Same for UC table if needed.
- Update cron queries to guard when status not present and migrate to new column.

11) UC guards and shortcodes
- Guard function/class redeclarations in includes/v2-api.php.
- Include v2-api once.
- Register shortcodes: [tmon_device_list], [tmon_device_status]; ensure AJAX URL localization.

12) Parse errors and warnings
- Fix parse/echo blocks in tmon-admin/includes/provisioning.php.
- Verify admin_notices blocks and enqueue functions use balanced PHP.

13) Remove Device location admin page
- Unregister/remove the page from admin menu.

14) CSV exports
- Add “Export CSV” to Audit Log and Command Logs pages.

Verification plan
- Visit Admin dashboard and confirm paired UCs listed.
- Open each Admin page: dashboards, notifications, OTA, files, groups, provisioning, provisioned devices – ensure content renders.
- Trigger provisioning queue and observe processing + clearing.
- Confirm command logs schema; requeue cron runs without DB errors.
- Run CSV exports; confirm file download and encoding.
- Confirm shortcodes render on frontend.
- Confirm Application Password auth on UC endpoints works (no JWT refs).

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
- [ ] Add persistence helpers for custom vars changed via set_var.
- [ ] Base <-> Remote LoRa envelopes with HMAC + replay protection; optional encryption.

Admin
- [ ] Add audit hooks across provisioning save/queue paths.

Unit Connector
- [ ] Widgets/graphs for device data; relay controls; shortcodes polish.

Docs/QA
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
- [ ] Add per-device HMAC confirmation or device-specific key to confirm endpoint.
- [ ] Add email notifications for provisioning events (optional).
- [ ] Add per-device staging preview and direct push tools in UI.
- [ ] Add tests to verify full provisioning lifecycle.

# TMON Admin — Updated TODO

High-priority
- [x] Define missing vars in inline update branch in provisioning page.
- [ ] Validate nonce usage across forms/handlers.
- [ ] Confirm device-side queue consumption and normalized key matching.

Medium
- [ ] Device mirror consistency updates and backfills.
- [ ] Admin notices reliability.
- [ ] Hierarchy Sync audit logs.

Lower-priority
- [ ] UX: typeahead for Known IDs; loading spinners.
- [ ] Security: verify cross-site tokens and rotation.
- [ ] Maintenance: centralize purge ops in settings.php; docs.
- [ ] Docs: admin guide for provisioning workflow and diagnostics.

Notes
- Migrations idempotent; keep in `admin_init`.
- Unique index `unit_machine (unit_id, machine_id)` ensures deduplication; ensure updates match normalized columns.

Unit Connector — Configuration UI and Staging
- [ ] Extend schema coverage to all firmware variables and advanced types (arrays/maps), with JSON validation.
- [ ] Admin hub integration button to push staged settings to Admin hub (optional).

UC Pairings and Device Listing
- [ ] Add settings to control refresh cadence (hourly/daily/off) and diagnostics.

REST and Admin-post Endpoints (UC)
- [ ] Add retry/backoff and result notice details.

TMON Admin — Fixes
- [ ] Wire full provisioning page to includes/provisioning.php and remove fallback after verification.

Unit Connector — Notices and Pairing
- [ ] (no pending items)

Firmware (Micropython) — Optimization Plan
- [ ] Implement compact telemetry keys and conditional inclusion (skip zeros/defaults).
- [ ] Single scheduler guard: prevent duplicate background tasks across main/startup/utils.
- [ ] OLED/debug output bounded and non-blocking; centralize through utils.
- [ ] Add adaptive upload backpressure: reduce batch size on errors/low memory.

Testing
- [ ] Verify UC hourly backfill populates devices when Admin is reachable.
- [ ] Verify Push-to-Admin triggers reprovision queue and devices receive staged settings.

TMON Admin — Provisioned Devices
- [ ] (no pending items beyond other sections)

Unit Connector — Settings Page
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
- Session removals (pruned from TODO for clarity)
  - Setup & Infrastructure: rename to micropython, LICENSE → MIT, debug system, expanded settings with persistence, CHANGELOG seeded, initial testing.
  - Firmware Basics: MACHINE_ID persistence, WiFi logic, first-boot + OTA check, admin registration/check-in, async loop/task flags, OLED optimization, environmental sampling, boot flow tests.
  - LoRa & Node Logic: LoRa security/basics, remote/base node logic, frost/heat watch, data relay, multi-node communication tests.
  - Admin fixes: audit page restore, UC endpoints (devices/reprovision/command), migrations for normalized IDs, firmware metadata, settings_staged, device mirror columns, history page renderer.
  - Unit Connector: mirror ensure/refresh, reprovision staging + push to Admin, commands page, pairing helper/shortcodes, cron requeue safety.
  - White screen fix: enforced redirect-after-POST on Save & Provision.
  - DB schema guards: column existence checks for commands/status/updated_at and OTA/action.
  - Firmware/OTA: version bumps to v2.02.1, OTA mirrors/headers for stable fetch.

## Upgrade Notes
- Devices will detect v2.02.0 via version.txt and manifest.json; ensure both are published before rollout.
- Admin/UC plugins should be upgraded together to 0.2.0 to keep pairing/staged settings features compatible.
- After upgrade, re-pair UC with Admin to populate hub_key/read_token and normalized pairing store.

Admin — Provisioning History
- [ ] (no pending items)

Unit Connector — Post-provisioning
- [ ] (no pending items)

Commands
- [ ] Add Admin-side mirror/log viewer for commands (status timeline).

White screen on Save & Provision
- [ ] (no pending items)

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
- [ ] Add admin UI notice for manifest/version and last fetch time.

TMON Admin — Provisioned Devices
- [ ] (no pending items beyond other sections)

Unit Connector — Command Table & Cron
- [ ] (no pending items beyond other sections)

Firmware — Version & OTA
- [ ] (no pending items beyond OTA section)

Verification
- [ ] Firmware metadata fetch works via AJAX (no 400).
- [ ] Provisioned Devices page loads without fatal and displays rows.
- [ ] Pairing/backfill populates UC devices; Admin offline notice clears via check-ins.
- [ ] Commands staged → polled → executed → confirmed flow visible in UC/Admin logs.

TMON Admin — Provisioning Save
- [ ] (no pending items)

Unit Connector — Pairing Persistence
- [ ] (no pending items)

TMON Admin — Provisioning Save & History
- [ ] (no pending items)

Unit Connector — Pairing & Backfill
- [ ] (no pending items)

Firmware/OTA
- [ ] (no pending items beyond OTA section)

Open items
- [ ] Add Admin UI notices for firmware manifest/version and last fetch timestamp.
- [ ] Add Admin/UC command logs viewer with status timeline and filters.

# TMON Admin — Provisioning
- [ ] (no pending items beyond provisioning sections)

# TMON Implementation Tracker

Completed
- Provisioning UI: Restored legacy form structure; integrated Save & Provision logic and notices.
- Provisioning: CSV export for provisioning history added (Export History link).
- Admin: Compact UI assets enqueued; modal JS remains available for list/commands.
- Admin: Command Logs page with filter + CSV export; AJAX endpoint reads tmon_device_commands.
- Firmware/Admin/UC: Removed JWT usage; switched to native WP auth (Application Passwords) where needed.
- UC: v2.00m REST endpoints loaded; optional Basic Auth guard added.

Pending verification
- Save & Provision persists rows and appends history; queued/failed notice visible.
- Provisioning History page renders cleanly and CSV export works.
- UC pairing persists on both sides; devices backfill visible in UC cache.
- Device first check-in confirms/applies; UC mirror updated.
- Commands staged→polled→executed→confirmed; visible in Command Logs.

Next
- Validate Basic Auth configuration on UC (TMON_UC_REQUIRE_APP_PASSWORD option/constant).
- Confirm manifest fetch sets version/time transients and notice displays on Admin pages.
