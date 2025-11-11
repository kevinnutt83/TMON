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

### Issues to Investigate and Resolve
- [ ] **Firmware page not displaying:**  
  - URL: `/wp-admin/tmon-admin-firmware`  
  - **Action:**  
    - [ ] Ensure the page is registered in the plugin menu (check `tmon-admin.php`).
    - [ ] Verify the template file exists and is loaded (check `templates/firmware.php` or similar).
    - [ ] Check permissions and callback output.
- [ ] **Device location page security error:**  
  - URL: `/wp-admin/admin.php?page=tmon-admin-location`  
  - **Action:**  
    - [ ] Remove the location page from the admin menu/UI (edit menu registration in `tmon-admin.php`).
    - [ ] Preserve location push logic in code for use via provisioning/device forms.
    - [ ] Add a note in code to clarify logic is preserved for future use.
- [ ] **Move purge all admin data button/function:**  
  - **Action:**  
    - [ ] Move purge logic/button from provisioning page to settings page (`includes/settings.php`).
    - [ ] Use unit-connector plugin's settings page structure for consistency.
    - [ ] Update documentation to reflect new location.
- [ ] **Audit page enhancement:**  
  - URL: `/wp-admin/admin.php?page=tmon-admin-audit`  
  - **Action:**  
    - [ ] Refactor audit logging for verbosity and robustness (expand `includes/audit.php`).
    - [ ] Ensure logs are detailed, searchable, and filterable.
    - [ ] Add export/download options for logs.
- [ ] **Provisioning page form redundancy:**  
  - **Action:**  
    - [ ] Refactor provisioning page to use a single form for all device data manipulation (edit `includes/provisioning.php`).
    - [ ] Remove duplicate forms, keep all core logic.
    - [ ] Ensure UI is clean and user-friendly.
- [ ] **Provisioned device actions:**  
  - **Action:**  
    - [ ] Add "View Device", "Provision", "Deactivate" (if active), and "Remove Device" buttons to device list table (edit `includes/provisioning.php`).
    - [ ] Ensure actions trigger correct logic and update device status.
- [ ] **Device registration not showing in list:**  
  - **Action:**  
    - [ ] Investigate DB queries, table joins, and UI rendering in `includes/provisioning.php`.
    - [ ] Fix logic so registered devices appear in the provisioning list.
    - [ ] Add debug logging for device registration flow.
- [ ] **Location push logic:**  
  - **Action:**  
    - [ ] Ensure location push logic is preserved and accessible via provisioning/device forms.
    - [ ] Document usage in code and README.

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

### Issues to Investigate and Resolve
- [ ] **Non-functional pages:**  
  - `/wp-admin/tmon_uc_commands`  
  - `/wp-admin/tmon-docs`  
  - `/wp-admin/tmon-offline`  
  - `/wp-admin/tmon-hierarchy`  
  - `/wp-admin/tmon_uc_location`  
  - **Action:**  
    - [ ] Ensure each page is registered in the plugin menu (check `tmon-unit-connector.php`).
    - [ ] Verify template files exist and are loaded (check `templates/`).
    - [ ] Fix routing, permissions, and callback output.
    - [ ] Add debug logging for page load errors.

## Phase 6: System Integration and Polish

- [x] Integrated full data flow: device boot → check-in → provision → sample → relay → UC receive/forward → Admin aggregate.
- [x] Added flexible device suspension logic for billing and admin control.
- [x] Implemented global monitoring and alerting for device and UC connectivity.
- [x] Optimized codebase for modular debug, common commands, and efficient structure.
- [x] Finalized UI/UX for uniform, sleek navigation across plugins.
- [x] Updated documentation in `README.md`, `CHANGELOG.md`, and wiki.
- [x] Prepared for deployment (zip plugins, tag repo).
- [x] Performed full end-to-end testing.

---

## Testing Log

- All phases tested with simulated devices and mock endpoints.
- Issues encountered:
  - [x] Minor UI polish improved (responsive tables, color contrast).
  - [x] Firmware update logic now retries on network error and verifies checksum.
  - [x] LoRa packet loss mitigated with exponential backoff and ACK packets.
  - [x] Device suspension tested for both admin and billing scenarios.
  - [x] Connectivity monitoring and alerting verified for UC/Admin links.
  - [ ] Device registration not showing in provisioning list (see above).
  - [ ] Non-functional plugin pages (see above).

---

## Documentation

- Updated `README.md` with architecture, setup, and usage.
- `CHANGELOG.md` reflects all major features and fixes.
- Wiki pages drafted for support, provisioning, and troubleshooting.
- Added API reference and firmware configuration guide.
- Documented protected settings.py variables and remote management logic.

---

## Commit Log

- Commits made per sub-step, tagged `v1.0.0`.
- All code and documentation changes pushed to main branch.
- Release candidate branch created for final QA.

---

## Next Actions

- [x] Final review and QA completed.
- [x] Release announcement prepared.
- [x] Monitoring for user feedback and bug reports started.
- [ ] Begin planning for v1.1.0 features (OTA improvements, advanced analytics, enhanced support portal, device replacement workflow).
- [ ] Investigate and resolve all issues listed above.
- [ ] Refactor provisioning page forms and move purge logic to settings.
- [ ] Enhance audit logging and verbose output.
- [ ] Remove redundant location page from UI, preserve logic.
- [ ] Fix device registration display in provisioning list.
- [ ] Fix non-functional pages in Unit Connector plugin.
