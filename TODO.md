# TMON Consolidated TODO & Notes

Goals
- Finish deduplication and cleanup in firmware (settings, utils, networking).
- Validate all WordPress REST endpoints end-to-end (Admin ↔ UC ↔ device).
- Add CI/host-side tests for networking, manifest parsing, and OTA flows.
- UI/UX polish for admin pages (provisioning flows, manifest viewer, notices).
- Security: remove hard-coded secrets, use persisted secure storage for credentials.

Immediate tasks
- Add unit/host tests for wprest async_http_request, send_field_data_log JSON shaping, and OTA manifest parsing.
- Run static checks for Python 3 vs MicroPython compatibility (type hints, imports).
- Add basic CI that runs linters and host tests (GitHub Actions).
- [x] Fix OTA task errors: `_get_ota()` now validates module attributes and won't cache a partial/wrong module; wrappers check validity before calling; `ota.py` `maybe_gc` import wrapped in try/except with inline fallback.

Notes
- README.md and CHANGELOG.md consolidated here; plugin READMEs are intentionally minimal as docs are centralized.
- settings.py deduplicated; all code should reference the single source.

# TMON Next Steps Implementation Log

## Phase 1: Setup and Infrastructure
- [x] Renamed `mircopython` to `micropython`.
- [x] Added missing placeholder `tmon.py` for frost/heat logic.
- [x] Updated LICENSE file to MIT.
- [x] Implemented modular debug system in `micropython/debug.py`.
- [x] Fixed `utils.debug_print` to check category-specific DEBUG_* flags, not only global `DEBUG` flag.
- [x] Fixed `debug.py` to print directly instead of delegating back to `debug_print` (avoided double-gating).
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
- [x] Fix OLED stack overflow: removed _make_driver_class wrapper, separated init_display from __init__, removed redundant _load_imports calls, cached driver class.
- [x] Defer heavy imports in main.py (lora, sampling, engine_controller, settings_apply) to first use to reduce C stack depth during module loading.
- [x] Remove module-level execution in wifi.py (get_settings bootstrap, utils import) — deferred to first use.
- [x] Fix Core 1 NULL deref crash: replaced dual-core asyncio.run() with single event loop. MicroPython uasyncio globals are not thread-safe; LoRa now runs as cooperative asyncio task on Core 0.
- [x] Fix BME280 "unexpected keyword argument 'i2c'" crash: added TypeError fallback in _read_bme280 for devices running older BME280.py without i2c parameter support. lib/BME280.py is not in OTA allowlist so devices retain the old constructor signature.
- [x] Fix field data log missing interior device readings and soil data: record_field_data() now includes cur_device_temp_c/f, cur_device_bar_pres, cur_device_humid, cur_soil_moisture.
- [x] Enable probe sampling: SAMPLE_PROBE_TEMP/BAR/HUMID were all False, preventing exterior probe BME280 reads.
- [x] Remove destructive LoRa SPI deinit from sampleBME280Probe: probe uses I2C1 (pins 6/2), not SPI1 — deinit was unnecessary and killed LoRa.
- [x] Fix sampleSoil premature clearing of sampling_active flag (conflicted with sampleEnviroment's own flag management).
- [x] Fix OLED render loop never starting: _update_display imported non-existent update_display; corrected to use show_header().
- [x] Fix debug_print suppressing ERROR/WARN messages: ERROR and WARN tags now always print regardless of DEBUG flags.
- [x] Fix send_field_data_log using 'DEBUG' tag instead of 'FIELD_DATA', bypassing DEBUG_FIELD_DATA=True.
- [x] Fix main.py sample task guard using non-existent settings (SAMPLE_HUMIDITY, SAMPLE_PRESSURE, SAMPLE_GAS); corrected to SAMPLE_HUMID, SAMPLE_BAR.
- [x] Fix free_pins_i2c referencing non-existent I2C_A_SCL_PIN/I2C_A_SDA_PIN; corrected to actual device and probe pin names.
- [x] Fix BME280.py global calibration corruption: digT/digP/digH/t_fine were module-level globals shared across instances; moved to instance variables so interior and probe sensors get independent calibration data.
- [x] Fix _read_bme280 permanently disabling sensor on transient failure: replaced single-try-then-disable with 3-attempt retry, I2C bus scan before init, and detailed per-attempt error logging with exception type.
- [x] Fix BME280 success debug print double-gated (required both DEBUG and DEBUG_TEMP): changed to use 'TEMP' tag so category flag alone controls output.
- [x] Add lib/BME280.py to OTA_FILES_ALLOWLIST: remote nodes were stuck on old BME280 constructor referencing non-existent I2C_A_SCL_PIN because the file wasn't OTA-updatable.
- [x] Fix probe I2C bus conflict with OLED: probe was using hardware I2C(1) which conflicts with OLED on I2C(1) with different pins. Changed probe to SoftI2C so both can coexist.
- [x] Downgrade "address not found on bus" from ERROR to WARN: expected when no physical probe is attached (e.g. base stations without an exterior probe).
- [x] Fix OTA failing for subdirectory files (lib/BME280.py): temp path embedded raw name with `/` creating non-existent dir; `_ensure_dir` only created one level. Fixed by sanitizing temp filename (`/` → `_`), making `_ensure_dir` recursive, and adding dir creation before backup and final writes.

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
- [High] Integrate staged settings form into Device Data page
  - Remove "Device Configuration (Staged Settings)" section from Unit Connector settings page (UI only; preserve backend endpoints).
  - Move form rendering & logic to Device Data page so applied, staged, and staged-new device settings populate correctly.
  - UI control mapping:
    - text, integer, float → text input (with server-side type validation).
    - bool → animated on/off switch (CSS transition on click).
  - Wire controls to AJAX save endpoints with optimistic UI updates and failure handling.
  - Acceptance criteria:
    - Settings appear properly on Device Data page for all three scopes (applied, staged, staged-new).
    - Bool switch animates and toggles state; saves via AJAX and updates persisted state.
    - No duplicate UI for staged settings elsewhere.
  - Testing notes:
    - Unit/integration tests for AJAX endpoints; end-to-end UI test for switch animation and persistence.

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
- [High] Staged settings population bug
  - Investigate why applied/staged/staged-new device settings are not populating; add test case covering REST/API payload, DB fields and rendering path.
  - Add acceptance criteria and regression tests.

Device History Graph & Shortcodes (NEW)
- [High] Fix history chart traces and legends
  - Include additional traces (and legend items) for:
    - lowest_temp_f = 0
    - highest_temp_f = 0
    - lowest_bar = 0
    - highest_bar = 0
    - lowest_humid = 0
    - highest_humid = 0
    - relay state trace(s) (on/off)
  - Ensure traces appear in graph legend and user can toggle each trace on/off.
  - Persist legend visibility in a browser cookie so AJAX refreshes do not reset visibility.
  - Acceptance criteria:
    - All listed variables appear as selectable legend items.
    - Toggling persists between refreshes (cookie-stored state).
  - Testing notes:
    - Add browser-based test for cookie persistence across AJAX refresh.

- [Medium] New shortcode: frost/heat watch
  - Create a shortcode that reports the frost/heat watch state and exposes:
    - lowest_temp_f, highest_temp_f, lowest_bar, highest_bar, lowest_humid, highest_humid
  - Acceptance criteria:
    - Shortcode outputs sanitized HTML/text reflecting current watch states.
    - Document shortcode arguments and usage.

Widgets & Front-end Shortcodes
- [ ] Widgets/graphs for device data; relay controls; shortcodes polish.
- [Medium] New compact widget/shortcode: unit quick-view
  - Implement a widget and matching shortcode that accepts:
    - unit_id (required)
    - data source option: sdata | settings (default sdata)
  - Output: single-box HTML snippet with key/value pairs (compact, sanitized).
  - Acceptance criteria:
    - Shortcode renders correctly in posts/pages; widget available in WP widget UI and block editor.
    - Widget supports caching and momentary AJAX refresh.

Docs / Starter / Wiki
- [ ] Add data flow graphics/screenshots.
- [ ] End-to-end tests for reprovision and command relay via base.
- [Medium] Update public docs & starter page generation
  - Update README, public docs and starter page generator to reflect current plugin version and features (include new shortcodes, widgets and staged-settings UI changes).
- [Medium] Update the wiki
  - Add application, usage, examples, shortcode/widget docs, and upgrade notes for current version.
  - Add troubleshooting steps for staged settings not populating and graph visibility issues.

Testing & QA
- [ ] Add unit/integration tests for:
  - AJAX settings updates
  - Graph trace inclusion and cookie persistence
  - Shortcode outputs
- [ ] Add manual test cases for UI behaviors and animations.
- [High] Test plan additions
  - Add automated tests for:
    - AJAX save/load for staged/applied settings (device data page).
    - Switch toggle animation + server update.
    - Graph legend cookie persistence and toggling across AJAX refreshes.
    - Frost/heat watch shortcode output.
  - Add manual QA checklist for release.

# TMON TODO

## Fixed / Implemented
- Unit Connector relay buttons now enqueue `toggle_relay` commands via admin-ajax.
- Unit Connector REST endpoints added:
  - `GET /wp-json/tmon/v1/device/commands`
  - `POST /wp-json/tmon/v1/device/command-complete`
- TMON Admin “Customers” template added (basic CRUD; option-backed model).
- Admin REST: `GET /wp-json/tmon-admin/v1/customers` (admin-only placeholder).

## Next (required by original scope)
- Secure UC↔Admin shared key lifecycle:
  - Admin generates “Shared Key for UC Integration”
  - UC can request/refresh/register key via Admin endpoints (button-driven)
  - Use shared key to authorize UC→Admin lookups
- Device registry on Admin (machine_id ↔ 6-digit unit_id), and confirm-applied pipeline:
  - Ensure unit_id is exactly 6 digits and immutable association with machine_id
  - Ensure Admin is single source of truth across all UCs
- Customer hierarchy (Admin):
  - locations → zones → groups models + assignment of devices to customers
  - UC pulls only devices assigned to its customer profile
- UC telemetry ingest + parsing:
  - Base node field_data.log lines include remotes and must be distinguishable on UC
- UI polish:
  - show relay state (from latest sdata) and disable invalid actions when device offline
- Documentation:
  - fill in root `COMMANDS.md`, plugin READMEs, and hub/UC install guides
