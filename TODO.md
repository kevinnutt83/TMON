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
- [ ] Create Device Configuration admin page (menu: TMON Devices → Settings) that renders a form for all variables from micropython/settings.py.
- [ ] Add a settings schema mapper in UC (PHP) to describe types, defaults, help text, and constraints for each firmware variable.
- [ ] Render inputs by type:
  - string/number: text/number fields
  - boolean: checkbox
  - enums: select
  - arrays/maps: textarea with JSON validation
- [ ] Persist posted values as staged settings:
  - DB: tmon_uc_devices.staged_settings + staged_at (already present)
  - File: wp-content/tmon-field-logs/data_history_UNITID_*.log optional snapshot
- [ ] Expose staged settings via UC REST:
  - GET /wp-json/tmon/v1/admin/device/settings-staged?unit_id=... → returns JSON
  - POST /wp-json/tmon/v1/admin/device/settings-applied (device confirms apply; includes unit_id, machine_id, firmware, role)
- [ ] Device-side polling (firmware):
  - On each sync cycle: poll UC for staged settings
  - Persist to device settings, apply, soft reset once (guard flag)
  - Post confirm-applied to UC, UC forwards summary to Admin (best-effort)
- [ ] Admin hub integration (optional push):
  - When staged in UC, optionally POST to Admin hub to enqueue provisioning (already supported); ensure keys are used (X-TMON-HUB or X-TMON-ADMIN)

UC Pairings and Device Listing
- [ ] Harden UC Pairings page:
  - Guard calls to tmon_admin_uc_pairings_get with function_exists (fallback to option store)
  - Normalize URLs consistently (host[:port]) to prevent duplicate entries
- [ ] Ensure device registration flows populate UC mirror:
  - Upsert into tmon_uc_devices on device check-ins (unit_id, machine_id, assigned flag)
  - Display in admin pages and shortcodes
  - Add empty-state diagnostics and refresh-from-admin button
- [ ] Add cron-like refresh from Admin hub (best-effort) to backfill UC mirror

MicroPython Sync Behavior
- [x] Fix timestamp in debug_print using Unix-epoch-safe helper.
- [ ] Ensure periodic_provision_check runs per sync cycle and logs with correct time.
- [ ] Confirm field data uploader respects NODE_TYPE and suspension flags; retry/backlog logic validated.

REST and Admin-post Endpoints (UC)
- [ ] admin_post: tmon_uc_generate_key (exists), tmon_uc_pair_with_hub (exists), add:
  - tmon_uc_stage_settings: accepts UNIT settings from form, saves to mirror DB
- [ ] REST:
  - GET /tmon/v1/admin/device/settings-staged: returns staged JSON by unit_id/machine_id
  - POST /tmon/v1/admin/device/settings-applied: device confirms application
  - POST /tmon/v1/admin/devices: list devices (assigned/unassigned) with pagination and filters
- [ ] Security:
  - Require X-TMON-ADMIN or X-TMON-HUB/X-TMON-READ as applicable
  - Nonce for admin actions

UI/UX
- [ ] Build configuration form sections (network, LoRa, sensors, OLED, OTA, debug) from schema
- [ ] Validation and descriptions; show current applied vs staged values
- [ ] Buttons: Save, Save & Push to Admin, Clear Staged
- [ ] Notices: staged queued, device confirmed, errors

Testing
- [ ] Firmware: staged settings fetch/apply path; confirm-applied POST
- [ ] UC: config form save/load; REST staging endpoints; device mirroring
- [ ] Admin: enqueue provisioning from UC post; UC pairings display; device lists in shortcodes
