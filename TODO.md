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
- [ ] Build a Device Configuration page that dynamically lists firmware variables from micropython/settings.py.
- [ ] Render inputs for each variable (text, number, boolean, select where applicable) with validation and descriptions.
- [ ] Save posted values to a staged settings record per Unit ID (DB and file), exposed via UC REST for devices.
- [ ] Devices poll UC for staged settings; upon download, persist, apply, and soft-reboot to load new settings.
- [ ] Add admin-post handlers: generate/read/update staged settings; push to Admin hub when appropriate.
- [ ] Add REST endpoints for devices: GET staged settings, POST confirm-applied.
- [ ] Ensure WiFi/base nodes: on each sync, send backlog field data, check Admin for provisioning changes, and consume UC staged settings.

UC Pairings and Device Listing
- [ ] Harden UC Pairings page by guarding helper calls and surfacing friendly errors if pairing store is missing.
- [ ] Ensure device registrations in UC create rows consumed by shortcodes and admin pages (mirror table ensure + upsert on check-ins).
- [ ] Add diagnostics for empty lists (explain pairing and data flow steps).

MicroPython Logging
- [x] Fix timestamp in debug_print using Unix-epoch-safe helper.
- [ ] Confirm periodic_provision_check runs on each UC sync cycle and logs with correct time.
