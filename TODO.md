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
- [x] Restore background scheduler and persisted URL loader (utils.start_background_tasks, load_persisted_wordpress_api_url).
- [x] Dedicated LoRa loop; configurable interval (LORA_LOOP_INTERVAL_S).
- [x] OLED guards with ENABLE_OLED.
- [x] WiFi node role: enable field-data send and command polling like base.
- [ ] First-boot OTA: verify against GitHub manifest; apply safely; reboot; audit to Admin.
- [ ] Confirm applied provisioning to Admin (optional per-device token/HMAC).
- [ ] Suspension: halt sampling/LoRa/commands while allowing check-ins; persist flag.
- [ ] Frost/Heat watch: integrate tmon.py triggers on base; increase LoRa cadence during alerts.
- [ ] Base aggregates remote field data into local field_data.log; UC differentiates base vs remote records.

LoRa
- [x] Enforce LORA_NETWORK_NAME/PASSWORD for secure network.
- [x] Base assigns per-remote next sync epoch; collision avoidance window (LORA_SYNC_WINDOW).
- [x] Remotes persist next sync across reboots (remote_next_sync.json).
- [ ] Optional HMAC signing + replay protection per-device (LORA_HMAC_*).
- [ ] Optional payload encryption (ChaCha20); provision secrets.
- [ ] Persist last_error and recovery thresholds; re-init strategy.

Provisioning lifecycle
- [x] First-boot Admin check-in; persist UNIT_ID & WORDPRESS_API_URL; guarded soft reset.
- [ ] Staged settings apply snapshot (prev/applied) and device confirm to Admin endpoint.

Unit Connector integration
- [ ] Periodic UC check-in after provisioning; machine_id fetch; appear only when assigned/approved.
- [ ] Batched field-data posts include unit_id/machine_id/role; UC normalization of base vs remote.

OLED/UI
- [ ] Status page: temp F (if sampling), WiFi/LoRa RSSI bars, clock, UNIT_ID/name; relay grid when enabled.
- [ ] Optimize display updates; debounce messages.

Security
- [ ] Admin suspend/enable honored; persist flag; reflected in UC/Admin UIs.
- [ ] Cross-site tokens verified: X-TMON-READ, X-TMON-HUB, X-TMON-ADMIN, X-TMON-CONFIRM.

Docs/QA
- [ ] README/CHANGELOG updates for loops, provisioning, UC pairing, LoRa schedule, OLED pages.
- [ ] Tests for provisioning lifecycle and LoRa sync.

---

## Testing Log
- [ ] Retest device registration/provisioning (Admin→Device→UC).
- [ ] Retest purge functions.
- [ ] Retest UC filtering (assigned devices only).
- [ ] Retest UI/UX improvements.

---

## Commit Log
- [ ] Commit per feature; tag release after QA.

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
