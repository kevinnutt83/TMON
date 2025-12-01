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

- [x] Ensured installation and schema creation in `tmon-admin.php`.
- [x] Expanded device management in `includes/provisioning.php`.
- [x] Implemented data handling in `includes/field-data-api.php`.
- [x] Added updates and wiki features in `includes/ota.php`.
- [x] Built support portal in `includes/support.php`.
- [x] Developed customer profiles and hierarchy UI in `includes/location.php`.
- [x] Implemented APIs/endpoints in `includes/api.php`.
- [x] Polished UI in `templates/`.
- [x] Tested plugin features with mocks and Postman.
- [x] Implemented version reporting and plugin update logic for Unit Connectors and devices.
- [x] Added logic for generating and managing "Shared Key for UC Integration" and hub ID.
- [x] Ensured UNIT_ID and MACHINE_ID association and management.
- [x] Added device suspension/enable logic and UI button in device listings.
- [x] Implemented global device monitoring and health status dashboard.
- [x] Tabulated all device record data for global aggregation and analytics.
- [x] Implemented firmware and plugin update push to Unit Connectors and devices.
- [x] Created Wiki management and customer-facing wiki sync.
- [x] Added user-controlled dashboards and shortcodes for device/group/location views.
- [x] Implemented customer uptime and health monitoring with GUI.
- [x] Made all settings.py options (except protected) remotely manageable.
- [x] Built robust admin support portal for ticketing, KPIs, remote access, and device health.
- [x] Created customer profile and location hierarchy management UI.
- [x] Implemented secure customer Unit Connector access for admins.

### Issues to Resolve & Polishing Steps

- [ ] **Firmware page not displaying:**  
  - [ ] Ensure submenu is registered in `tmon-admin.php` for `/wp-admin/tmon-admin-firmware`.
  - [ ] Create or update `templates/firmware.php` with a clear, styled UI and fallback message if no firmware info.
  - [ ] Add permission checks and error handling for missing template.
  - [ ] Polish UI: Add headings, icons, and responsive layout.

- [ ] **Device location page security error:**  
  - [ ] Remove location page from menu in `tmon-admin.php`.
  - [ ] Move location push logic to provisioning/device forms.
  - [ ] Add comments in code to clarify logic is preserved.
  - [ ] Polish: Add location fields to provisioning form with tooltips/help text.

- [ ] **Move purge all admin data button/function:**  
  - [ ] Move purge logic/button from provisioning to settings page (`includes/settings.php`).
  - [ ] Match UI to unit-connector plugin: use cards, icons, and confirmation modal.
  - [ ] Add admin notice on success/failure.

- [ ] **Audit page enhancement:**  
  - [ ] Refactor audit logging for verbosity (add timestamps, user info, action type).
  - [ ] Add search/filter UI (date, user, action).
  - [ ] Paginate logs, add export to CSV/JSON.
  - [ ] Polish: Use table with sticky headers, color-coded log levels, and responsive design.

- [ ] **Provisioning page form redundancy:**  
  - [ ] Refactor to a single form for device data manipulation.
  - [ ] Remove duplicate forms, keep all logic.
  - [ ] Add tabs or accordions for device actions (view, provision, deactivate, remove).
  - [ ] Polish: Add icons, tooltips, and responsive layout.

- [ ] **Provisioned device actions:**  
  - [ ] Add "View Device", "Provision", "Deactivate", "Remove Device" buttons to device list table.
  - [ ] Ensure correct action handlers and confirmation dialogs.
  - [ ] Polish: Use button groups, color coding, and modal dialogs for confirmation.

- [ ] **Device registration not showing in list:**  
  - [ ] Debug DB queries and joins in `includes/provisioning.php`.
  - [ ] Ensure new devices are inserted and queried for display.
  - [ ] Add admin notice if no devices found.
  - [ ] Polish: Add loading spinner, empty state message, and refresh button.

- [ ] **Location push logic:**  
  - [ ] Ensure location push logic is accessible via provisioning/device forms.
  - [ ] Add comment in code to clarify logic is preserved.
  - [ ] Polish: Add location autocomplete and validation.

## Phase 5: TMON Unit Connector Plugin

- [x] Ensured installation and key refresh logic in `unit-connector/includes/settings.php`.
- [x] Implemented device provisioning from Admin in `unit-connector/includes/api.php`.
- [x] Handled data reception, normalization, and forwarding in `unit-connector/includes/field-data-api.php`.
- [x] Built dashboards and interfaces in `unit-connector/templates/`.
- [x] Implemented periodic check-in and settings update logic in `unit-connector/includes/api.php`.
- [x] Polished UI for customer views in `unit-connector/templates/`.
- [x] Tested integration with Admin and device provisioning.
- [x] Implemented logic for Unit Connector to obtain and refresh "Shared Key for UC Integration" from Admin.
- [x] Ensured only assigned/approved devices are provisionable and visible per customer.
- [x] Made all settings.py options (except protected) remotely manageable from Unit Connector.
- [x] Added user dashboards and shortcodes for device/group/location views.
- [x] Built robust data export and device info interface.
- [x] Implemented connectivity monitoring and alerting for Admin/Unit Connector communication.

### Issues to Resolve & Polishing Steps

- [ ] **Non-functional pages:**  
  - [ ] Ensure menu registration for all pages.
  - [ ] Create/update template files with fallback messages and styled UI.
  - [ ] Add permission checks and error handling.
  - [ ] Polish: Add icons, headings, and responsive layout to all pages.

## Phase 6: System Integration and Polish

- [ ] Polish all UI/UX for uniform look:  
  - [ ] Use consistent color scheme, button styles, and table layouts.
  - [ ] Add tooltips, help text, and icons where appropriate.
  - [ ] Ensure all forms are responsive and accessible.
  - [ ] Add loading spinners and empty state messages.
  - [ ] Test all flows end-to-end and update documentation/screenshots.

---

## Testing Log

- [ ] Retest all plugin pages for display, logic, and UI/UX.
- [ ] Retest device registration and provisioning flow.
- [ ] Retest audit logging, purge, and location logic.
- [ ] Retest unit connector plugin pages and data flows.

---

## Documentation

- [ ] Update README.md with screenshots of polished UI.
- [ ] Update CHANGELOG.md with all fixes and enhancements.
- [ ] Document new UI/UX features and logic changes.

---

## Commit Log

- [ ] Commit all code and UI/UX changes per feature.
- [ ] Tag release after QA.

---

## Next Actions

- [ ] Implement and polish all listed corrections and enhancements.
- [ ] Continue testing and polish based on user feedback.
- [ ] Begin planning for v1.1.0 features (OTA improvements, advanced analytics, enhanced support portal, device replacement workflow).

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
- [ ] Frost/Heat watch: integrate with tmon.py on base; adjust LoRa sync cadence during alerts.
- [ ] Base aggregates remote field data into local field_data.log; UC differentiates base vs remote records.

LoRa
- [x] Network name/password enforcement (LORA_NETWORK_NAME/PASSWORD).
- [x] Base assigns per-remote next sync epoch; collision avoidance window.
- [x] Remotes persist next sync across reboots (remote_next_sync.json).
- [ ] Optional HMAC signing + replay protection per-device (LORA_HMAC_*).
- [ ] Optional payload encryption (ChaCha20); manifest/provision keys.
- [ ] Persist last_error state; robust radio recovery thresholds.

Provisioning lifecycle
- [x] First-boot check-in to Admin; persist UNIT_ID and WORDPRESS_API_URL; guarded soft reset.
- [ ] Staged settings apply snapshot + confirm to Admin endpoint.

Unit Connector integration
- [ ] Periodic UC check-in after provisioning; machine_id fetch; appear only when assigned/approved.
- [ ] Batched field-data posts include unit_id/machine_id/role; UC normalization of base vs remote.

OLED/UI
- [ ] Status: temp F (if sampling), WiFi/LoRa RSSI bars, clock, UNIT_ID/name; relay grid when enabled.
- [ ] Optimize display updates; debounce messages.

Security
- [ ] Admin suspend/enable honored; reflected in UC/Admin UIs; tokens/headers checked.
- [ ] Cross-site tokens: X-TMON-READ, X-TMON-HUB, X-TMON-ADMIN, X-TMON-CONFIRM.

Docs/QA
- [ ] README/CHANGELOG updates for loops, provisioning, UC pairing, LoRa schedule, OLED pages.
- [ ] Tests for provisioning lifecycle and LoRa sync.

## Testing Log
- [ ] Retest device registration/provisioning (Admin→Device→UC).
- [ ] Retest purge functions.
- [ ] Retest UC filtering (assigned devices only).
- [ ] Retest UI/UX improvements.

## Commit Log
- [ ] Commit per feature; tag release after QA.

# TODO

- [x] Mirror provisioned settings to tmon_devices (provisioned, wordpress_api_url, unit_name, provisioned_at) on Save & Provision.
- [x] If tmon_devices lacks provisioned flags, add migration to add provisioned/provisioned_at/wordpress_api_url columns.
- [x] Deliver staged provisioning to devices from queue or DB row (settings_staged).
- [x] Add device confirm endpoint with token; device posts confirm after apply.
- [x] Admin UI Provisioning Activity page with pending queue and history.
- [x] Add history auditing/logging option in Admin.
- [ ] Add per-device HMAC confirmation or device-specific key to confirm endpoint.
- [ ] Add email notifications for provisioning events (optional).
- [ ] Add per-device staging preview and direct push tools in UI.
- [ ] Add tests to verify full provisioning lifecycle.

# TMON Admin — Updated TODO

Completed (from this session)
- Fixed fatal parse error by removing stray standalone `if ($action === 'update')` block at file end.
- Restored redirect-after-POST in `admin_post_tmon_admin_provision_device` with status: fail, success, queued, queued-notified.
- Added firmware fields and GitHub manifest fetch (AJAX: `tmon_admin_fetch_github_manifest`) to top form and per-row actions.
- Added migrations: normalized IDs (`unit_id_norm`, `machine_id_norm`), firmware metadata, settings_staged, device mirror columns.
- Ensured queue helpers: enqueue/dequeue/lookup based on normalized keys.
- Added diagnostic tools: known IDs refresh, queue/DB staging check, API calls and provisioning history tables.
- Added claims approval/denial flow and provisioning history page callback.

High-priority
- Scope audit in provisioning page inline update branch:
  - Variables referenced but not defined in-branch: `$exists`, `$site_url`, `$firmware`, `$firmware_url`, `$role`, `$plan`, `$notes`, `$company_id`, `$row_tmp` (used in UC push).
  - Define from POST or DB `$row_tmp` before usage to avoid notices and inconsistent payloads.
- Ensure nonce usage aligns:
  - Page inline forms use `tmon_admin_provision` nonce; top unified form posts to `admin-post` with `tmon_admin_provision_device`. Verify both nonces are validated in their handlers.
- Queue consumer path:
  - Confirm device-side or REST endpoint consumes `tmon_admin_pending_provision` queue and clears items on success.
  - Validate normalized key matching across MAC formats and unit IDs.

Medium
- Device mirror consistency:
  - When enqueueing with only one identifier present, ensure mirror updates select by both `unit_id` and `machine_id` if available.
  - Backfill `tmon_devices.unit_name` from provisioning payload when set.
- Admin notices:
  - After inline update (not provisioning), page uses immediate redirect; ensure success/fail messages show reliably for all branches.
- Hierarchy Sync:
  - Add success/failure audit logs mirroring other actions.
  - Consider mapping validation and server response parsing for better admin feedback.

Lower-priority
- UX polish:
  - Debounced typeahead for Known IDs (AJAX `tmon_admin_known_units`) with input filters role/company on client-side.
  - Add loading spinners for firmware fetch buttons.
- Security:
  - Where cross-site pushes require UC auth, verify tokens: `X-TMON-READ`, `X-TMON-HUB`, `X-TMON-ADMIN` stored and rotated securely.
- Maintenance:
  - Centralize purge operations in `includes/settings.php` (already referenced); document commands and safeguards.
- Docs:
  - Add admin guide: provisioning workflow, queue semantics, UC pairing, diagnostics usage.

Notes
- Migrations are idempotent and guarded; keep them in `admin_init` to avoid unknown column errors.
- Unique index `unit_machine (unit_id, machine_id)` ensures deduplication; verify insert/updates use normalized columns as needed.
