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
- [x] Add basic CI that runs readiness validation and build packaging (GitHub Actions, `.github/workflows/release-readiness.yml`).
- [x] Fix OTA task errors: `_get_ota()` now validates module attributes and won't cache a partial/wrong module; wrappers check validity before calling; `ota.py` `maybe_gc` import wrapped in try/except with inline fallback.
- [x] Suppress expected OTA idle noise: `apply_pending_update` no longer logs WARN when `OTA_PENDING_FILE` is missing (`ENOENT`).

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
- [ ] Provisioning page UX polish (unified form, tabs/accordions, responsive design).
- [ ] Location push logic (accessible via provisioning, comments, autocomplete/validation).
- [ ] Advanced device filters/search (status, role, company, date range).
- [ ] Batch device actions (enable/disable, firmware queue, settings push).
- [ ] Device export (CSV with full device history and diagnostics).

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
- [x] Add persistence helpers for custom vars changed via set_var.
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
- [x] Fix LoRa remote initial stagger too long (up to 600s); reduced to 30s max.
- [x] Fix LoRa remote response_timeout too long (300s); reduced to 60s.
- [x] Fix LoRa remote STATE_WAIT_RESPONSE blocking full timeout even after ACK received; now transitions immediately on ACK with 10s post-listen for CMD/OTA.
- [x] Fix LoRa base sending ACK after slow HTTP proxy calls; restructured to send ACK+CMD+OTA first, then proxy HTTP.
- [x] Rewrite user_commands.py: replaced blocking input() and non-existent module references with non-blocking uselect.poll() async CLI; integrates with TaskManager.
- [x] Add user_commands_task integration in main.py with safe import fallback.
- [x] Add DEBUG_USER_CMD flag to settings.py for user command debug output control.
- [x] Fix _unsecure_message dropping all encrypted messages: replay protection was checking UID in encrypted wire string before decryption; restructured to decrypt first, then extract UID, then replay check.
- [x] Fix _unsecure_message HMAC verification for non-encrypted messages: msg_str still contained ,CNT: suffix that wasn't in the original signed payload; now stripped before HMAC computation.
- [x] Fix user_commands CLI not visible: added TMON> prompt, character echo, backspace support, and always-visible startup banner.
- [x] Fix _unsecure_message `break` in HMAC parsing loop: loop iterates backwards so HMAC (always last) is found first and break fires before CNT/ENC are ever parsed, causing cnt_str=None and every message silently dropped. Removed break, changed to elif chain.
- [x] Add diagnostic logging when base or remote rx message fails auth/decrypt, so failures are no longer silent.
- [x] Fix OTA failing for subdirectory files (lib/BME280.py): temp path embedded raw name with `/` creating non-existent dir; `_ensure_dir` only created one level. Fixed by sanitizing temp filename (`/` → `_`), making `_ensure_dir` recursive, and adding dir creation before backup and final writes.

Admin
- [x] Add audit hooks across provisioning save/queue paths.
- [x] Add diagnostics observability in Admin (secure list endpoint + diagnostics page).
- [x] Harden diagnostics auth defaults and payload bounds (Admin + Unit Connector).
- [x] Add settings-page toggles for diagnostics no-auth legacy compatibility (Admin + UC).
- [x] Improve admin dashboard device overview (live counts + recent diagnostics).
- [x] Enhance provisioning flow visibility (activity/history pages with summary cards, queue snapshot, and richer filters).

Firmware
- [x] Acknowledge unsupported command types in poll loop to avoid infinite re-delivery churn.
- [x] Add battery remote deep-sleep mode: remote wake -> sample -> LoRa send -> persist next sync -> deep sleep.
- [x] Add field-testing hardening for battery remotes: ACK-driven next sync persistence, voltage-adaptive deep sleep, and optional EXT wake recovery fallback.
- [x] Add COMMAND_ACK_UNSUPPORTED setting and staged-apply support.
- [x] Reduce command polling blocking: add cooperative yields in WP command/result loops and local per-poll command caps.
- [x] Make command polling cadence configurable with jitter/timeouts (COMMANDS_POLL_INTERVAL_S, COMMANDS_POLL_JITTER_S, COMMANDS_RESULT_TIMEOUT_S).
- [x] Fix LoRa airtime congestion and field-data accumulation: enable `FIELD_DATA_COMPACT_KEYS`, cap LoRa batches via `FIELD_DATA_LORA_MAX_BATCH=3`, trim `field_data.log` immediately on batch delivery, and remove redundant raw state file uploads.

Unit Connector
- [x] Update field-data-api.php $flatten to include device interior sensors (cur_device_temp_f/c, cur_device_humid, cur_device_bar_pres), soil sensors (cur_soil_moisture, cur_soil_temp_c/f), engine data, CPU temp, runtime metrics, and diagnostics.
- [x] Update tmon_uc_get_device_history points array to return device interior, soil, engine, and CPU temp fields for charting.
- [x] Update tmon_uc_get_device_sdata friendly names to include all new telemetry fields with human-readable labels.
- [x] Update tmon_devices_sdata shortcode table to display device interior temp/humidity/pressure and soil moisture instead of probe-only values.
- [x] Update tmon_device_history chart datasets to graph device interior temp/humidity/pressure and soil moisture alongside probe data.
- [x] Widgets/graphs for device data; relay controls; shortcodes polish.
- [x] Fix PHP error log spam from dashboard widgets / shortcodes (`tmon_pending_commands_summary_refresh`) and prevent Elementor `Attempt to read property "post_status" on null in document.php` warnings by excluding `tmon_custom_code` from Elementor and avoiding global `$post` loop variable collisions.
- [x] Fix shortcode ID selector collisions on the Device Data page (`[tmon_device_settings]` and `[tmon_device_history]`) and ensure immediate initial population of Applied/Staged JSON status boxes.
- [x] Restore Device Data unit selector and shortcode dropdown behavior by routing the Device Data menu to `tmon_uc_device_data_page()` and adding standalone local unit-picker fallback for `[tmon_device_settings]`.
- [x] Harden `templates/device-data.php` fallback path by removing conflicting legacy picker scripts, aligning staging AJAX payload to `settings_json` + `nonce`, and tying unit-name updates to the active picker selection.
- [x] Remove duplicate `wp_ajax_tmon_uc_update_unit_name` handler to keep one consistent nonce/check + staged-name update path.
- [x] Harden pending-commands summary polling + AJAX diagnostics filter
  - Expanded diagnostics skip logic to suppress routine `tmon_pending_commands_*`, `tmon_device_status_*`, `tmon_uc_device_*`, and `tmon_uc_queue_*` polling actions.
  - Normalized AJAX action parsing with `sanitize_key(wp_unslash(...))` to avoid false-positive logging.
  - Reworked pending summary auto-refresh scripts to use structured POST requests with encoded values to avoid inline parse edge cases.
- [x] Restore relay control shortcodes and harden Device Data / hierarchy pages
  - Added compatibility shortcodes for `tmon_relay_on`, `tmon_relay_off`, `tmon_relay_toggle`, and `tmon_relay_controls` that queue relay commands via the existing AJAX pipeline.
  - Hardened Device Data unit-name picker null handling and made Hierarchy accessible to admins even when custom caps are missing.
  - Added safer Leaflet loading for the hierarchy page and guarded the WordPress auto-update checker with package fallback + debug logging.

Docs/QA
- [ ] Add data flow graphics/screenshots.
- [ ] End-to-end tests for reprovision and command relay via base.
- [x] Add host-side validation script for reprovision + command relay flow (`scripts/validate_reprovision_command_relay.py`).

Firmware
- [x] Add atomic staged-settings JSON write/read helpers and use them in settings fetch/apply paths.
- [x] Add centralized diagnostics snapshot module, structured exception capture in core runtime files, and 5-page OLED diagnostics/health views.
- [x] Apply second-wave structured exception consistency across remaining runtime modules (WiFi, OTA, settings apply, provisioning, firmware updater, relay/sampling, CLI helpers) with behavior-preserving best-effort logging.

## Testing Log
- [x] Provisioned Devices page functional with edit/delete actions
- [x] All firmware files validated (no syntax errors)
- [x] All WordPress plugins validated (schema/REST endpoints functional)
- [x] Comprehensive error checking completed
- [ ] End-to-end testing with real hardware (WiFi, Base, Remote nodes)
- [ ] Load testing (100+ devices simultaneous check-in)
- [ ] Security audit (penetration testing, input validation)

## Deployment Log
- [x] Created TESTING_AND_DEPLOYMENT.md (comprehensive QA/deployment guide)
- [ ] Staged firmware binary ready for OTA
- [ ] Admin plugin ready for activation
- [ ] Unit Connector plugin ready for deployment
- [ ] Database schema verified on staging
- [ ] SSL certificates validated
- [ ] Backup & recovery procedures documented

# TODO
- [x] Add per-device HMAC confirmation or device-specific key to confirm endpoint.
- [ ] Add email notifications for provisioning events (optional).
- [ ] Add per-device staging preview and direct push tools in UI.
- [ ] Add tests to verify full provisioning lifecycle.

# TMON Admin — Updated TODO

High-priority
- [x] Define missing vars in inline update branch in provisioning page.
- [ ] Validate nonce usage across forms/handlers.
- [x] Confirm device-side queue consumption and normalized key matching.
- [x] Consolidate duplicate UC command routes/UI to canonical includes/commands.php.

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
- [x] Integrate staged settings form into Device Data page
  - Removed duplicate "Device Configuration (Staged Settings)" form from Settings page and linked to Device Data as canonical workflow.
  - Device Data now uses consistent selector + staging payload contract (`settings_json` + `nonce`) and updates applied/staged/bundle views.
  - Bool controls in `[tmon_device_settings]` now use animated on/off switches.
  - Added readiness validator: `scripts/validate_uc_field_testing_readiness.sh`.
  - Added runtime checklist: `unit-connector/README-field-testing.md`.

UC Pairings and Device Listing
- [ ] Add settings to control refresh cadence (hourly/daily/off) and diagnostics.

REST and Admin-post Endpoints (UC)
- [ ] Add retry/backoff and result notice details.

TMON Admin — Fixes
- [ ] Wire full provisioning page to includes/provisioning.php and remove fallback after verification.

Unit Connector — Notices and Pairing
- [ ] (no pending items)

Firmware (Micropython) — Optimization Plan
- [x] Implement compact telemetry keys and conditional inclusion (skip zeros/defaults).
- [x] Single scheduler guard: prevent duplicate background tasks across main/startup/utils.
- [x] OLED/debug output bounded and non-blocking; centralize through utils.
- [x] Reduce blocking I/O in async code (replaced boot/main/provision print calls with provisioning_log).
- [x] Add adaptive upload backpressure: reduce batch size on errors/low memory.
- [x] Improve OLED status/banner rendering and route key sampling failures through structured logging.

Testing
- [ ] Verify UC hourly backfill populates devices when Admin is reachable.
- [ ] Verify Push-to-Admin triggers reprovision queue and devices receive staged settings.

TMON Admin — Provisioned Devices
- [ ] (no pending items beyond other sections)

Unit Connector — Settings Page
- [x] Load hierarchy map JS only when Leaflet is present; suppress console noise.
- [x] Staged settings population bug
  - Investigated and fixed selector wiring, stale AJAX keys, and duplicate handler conflicts causing population failures.
  - Added regression-oriented readiness checks for REST/API payload contract, selector path, and duplicate-handler detection.
- [x] Fix starter/shortcode runtime regressions
  - `tmon_device_settings` now falls back to local `tmon_devices` rows when provisioned-options helpers are empty.
  - Feature-device detection now accepts compact interior/soil telemetry keys (`dt_f`, `dh`, `db`, `sm`) and connectivity-only payloads.
  - Claim shortcode now posts to local `/wp-json/tmon/v1/device/first-checkin` to avoid browser CORS failures.
  - Field-data ingest now flattens nested `sdata` / `data` objects so charts and sdata views populate expected fields.

Device History Graph & Shortcodes (NEW)
- [High] Fix history chart traces and legends
- [x] Fix history chart traces and legends
  - Added low/high traces for temperature, pressure, and humidity with legend items.
  - Relay state traces are preserved and plotted as stepped on/off lines.
  - Legend visibility now persists using cookies (with localStorage fallback) across auto-refresh updates.
  - Added automated harness + checklist coverage for Device Data flow and chart behavior verification.

- [Medium] New shortcode: frost/heat watch
- [x] New shortcode: frost/heat watch
  - Added `[tmon_frost_heat_watch]` with page-level picker integration and local fallback.
  - Displays frost/heat watch state and required low/high values: temp, pressure, humidity.
  - Includes documented usage and refresh behavior in field-testing docs.

Widgets & Front-end Shortcodes
- [x] Widgets/graphs for device data; relay controls; shortcodes polish.
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
  - [x] Added automated wp-admin smoke harness (Playwright) for Device Data page checks.
  - [x] Added/expanded pre-flight validator checks for staging payload, selector wiring, legend persistence, shortcode presence, and admin asset gating.
  - [x] Added manual QA checklist for release/field-testing in `unit-connector/README-field-testing.md`.

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
