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
