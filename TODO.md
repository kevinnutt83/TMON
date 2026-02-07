# TMON Development TODO List

## Legend
- ✅ **COMPLETED** - Fully implemented and working
- 🚧 **IN PROGRESS** - Partially implemented or being worked on
- ⏳ **PENDING** - Not started yet
- 🔄 **NEEDS REVIEW** - Implemented but needs testing/verification

---

## 1. Device Firmware (MicroPython)

### 1.1 Core Device Identity & Registration
- [✅] MACHINE_ID detection from chipset on first boot
- [✅] MACHINE_ID persistence to disk
- [✅] UNIT_ID generation and association with MACHINE_ID
- [✅] Device check-in with TMON Admin plugin using MACHINE_ID
- [✅] Device registration tracking (registered/unprovisioned status)
- [🚧] Device suspension toggle (backend exists, needs full integration)
- [✅] Settings persistence system (config_persist.py)

### 1.2 Firmware Update & OTA
- [✅] Firmware version detection and tracking
- [✅] Check GitHub repository for latest firmware on boot
- [✅] Download firmware updates from GitHub
- [✅] OTA firmware update application with reboot
- [✅] Firmware update logging to device and TMON Admin
- [✅] OTA pending flag system
- [🚧] Version control logic to ensure devices use TMON Admin specified version
- [⏳] Firmware version distribution control from TMON Admin to devices

### 1.3 WiFi Communication
- [✅] WiFi connection logic (wifi.py)
- [✅] WiFi SSID and password configuration
- [✅] WiFi connection retry logic with backoff
- [✅] WiFi signal strength (RSSI) monitoring
- [✅] WiFi auto-disable for remote nodes after provisioning
- [✅] WiFi always-on for unprovisioned devices
- [🔄] WiFi signal strength display on OLED with bars

### 1.4 LoRa Communication
- [✅] LoRa SX1262 module initialization
- [✅] LoRa connection logic for base and remote nodes
- [✅] LoRa message transmission and reception
- [✅] LoRa HMAC signing for frame authentication
- [✅] LoRa encryption (ChaCha20) for secure payload
- [✅] LoRa replay protection with counter tracking
- [⏳] LORA_NETWORK_NAME and LORA_NETWORK_PASSWORD variables
- [⏳] Base station secure LoRa network management with credential verification
- [🚧] Remote node scheduled check-in time assignment from base station
- [🚧] Base station tracking table for remote nodes (UNIT IDs, check-in times)
- [🚧] Automatic base station listening during remote node check-in windows
- [✅] CAD (Channel Activity Detection) before transmission
- [✅] LoRa backoff when channel busy
- [✅] Remote node info logging (LORA_REMOTE_INFO_LOG)

### 1.5 Environmental Sampling
- [✅] Temperature sampling (BME280, DHT11)
- [✅] Humidity sampling (BME280, DHT11)
- [✅] Barometric pressure sampling (BME280)
- [✅] Sampling enable/disable controls in settings.py
- [✅] Sensor device selection (BME280 vs DHT11)
- [✅] Field data logging system
- [✅] Voltage monitoring (system voltage via ADC)
- [✅] CPU temperature monitoring
- [🚧] Additional sensors (LTR390, MPU925x, SGP40, TSL2591) - partial implementation
- [✅] Data collection intervals configurable

### 1.6 Field Data Management
- [✅] Field data log creation and persistence
- [✅] Field data chunking and rotation
- [✅] Field data delivery tracking (delivered log)
- [✅] Field data batch upload to Unit Connector
- [✅] Field data GZIP compression
- [✅] Field data max size limits and rotation
- [✅] Backoff on HTTP failures
- [✅] Remote node data integration into base node logs
- [🚧] Unit Connector parsing of base vs remote node data

### 1.7 Provisioning System
- [✅] First boot provisioning check
- [✅] Provisioning flag file system
- [✅] Remote settings staging system (REMOTE_SETTINGS_STAGED_FILE)
- [✅] Remote settings application system (REMOTE_SETTINGS_APPLIED_FILE)
- [✅] Settings apply on next check-in
- [✅] Device reboot after provisioning
- [✅] WORDPRESS_API_URL assignment during provisioning
- [✅] Provisioning status tracking
- [🚧] All settings.py variables user-changeable remotely (except restricted ones)
- [🚧] Unit Connector check-in interval (300 seconds)

### 1.8 OLED Display
- [✅] OLED initialization and messaging system
- [✅] OLED enable/disable control
- [⏳] Temperature display in Fahrenheit (when sampling enabled)
- [⏳] WiFi signal strength bars display
- [⏳] LoRa signal strength bars display
- [⏳] Current time display
- [⏳] Node name/Unit ID display
- [🔄] Optimized display message function review in oled.py

### 1.9 Relay Control
- [✅] Relay pin configuration (8 relays)
- [✅] Relay enable/disable controls per relay
- [✅] Relay toggle functionality
- [✅] Relay runtime limits per relay
- [✅] Relay safety maximum runtime
- [🚧] Remote relay control commands from plugins
- [🚧] Scheduled relay operations

### 1.10 Node Type Logic
- [✅] NODE_TYPE variable (base, wifi, remote)
- [✅] Base node WiFi + LoRa operation
- [✅] WiFi node WiFi-only operation
- [✅] Remote node LoRa-only operation (WiFi disabled after provision)
- [🚧] LoRa logic disabled for wifi nodes
- [🚧] Base node as LoRa hub/router for remote nodes
- [🚧] Base node relay of remote data to plugins
- [🚧] Base node receiving and relaying commands/files to remote nodes

### 1.11 Frost & Heat Watch
- [⏳] Frost watch enable/disable
- [⏳] Frost threshold temperature configuration
- [⏳] Frost operation start threshold
- [⏳] Frost operation stop threshold
- [⏳] Heat watch enable/disable
- [⏳] Heat threshold temperature configuration
- [⏳] Heat operation start threshold
- [⏳] Heat operation stop threshold
- [⏳] Sync rate increase during frost/heat watch
- [⏳] Base node monitoring of remote node temps for frost/heat
- [⏳] Automated command execution on frost/heat detection
- [⏳] Group-based frost/heat monitoring

### 1.12 Debugging System
- [✅] Modular debug flags per functionality
- [✅] DEBUG flags for major systems (LORA, WIFI, SAMPLING, etc.)
- [✅] Debug print utility function
- [✅] Debug logging to files
- [🔄] Enhanced debug system for more granular control

### 1.13 Task Management
- [✅] Async task manager system
- [✅] Sample task (environmental sampling)
- [✅] LoRa communication task
- [✅] Field data send task
- [✅] Command poll task
- [✅] Settings apply loop task
- [✅] Provision check task
- [✅] WiFi RSSI monitor task
- [🚧] Engine controller task (partial, disabled by default)
- [✅] Task suspension when device suspended
- [✅] Garbage collection optimization in tasks

### 1.14 GPS & Location
- [✅] GPS enable/disable control
- [✅] GPS source selection (manual, module, network)
- [✅] GPS coordinate storage (lat, lng, alt, accuracy)
- [✅] GPS override allowed flag
- [✅] GPS broadcast to remotes from base station
- [🚧] GPS acceptance from base on remote nodes

### 1.X Raspberry Pi Zero (CPython) Compatibility
- [🚧] Remove/guard direct imports of MicroPython-only modules on Zero (e.g., `import machine`, `import network`, `import urequests`)
- [⏳] Update `micropython/utils.py` to import `machine` via `platform_compat` (fixes current `ModuleNotFoundError: machine` on Zero)
- [⏳] Audit all modules for hardware backends and ensure `MCU_TYPE == "zero"` paths no-op safely (relay, I2C sensors, LoRa, UART/RS485)
- [🔄] Validate that `platform_compat.py` exports safe stubs/None for `machine`, `network`, `framebuf`, `requests` on Zero and real modules on MicroPython

---

## 2. TMON Admin Plugin (WordPress)

### 2.1 Core Admin Features
- [✅] Plugin installation and activation on tmonsystems.com
- [✅] Hub ID / Shared Key for UC Integration generation
- [✅] Admin dashboard with device overview
- [✅] Device registration system
- [✅] UNIT_ID generation (6-digit)
- [✅] MACHINE_ID association with UNIT_ID
- [✅] Device provisioning interface
- [✅] Provisioned devices listing
- [✅] Unprovisioned devices listing
- [🚧] Device suspension toggle with easy UI button
- [🚧] Suspension enforcement (stop task processing, allow check-in)

### 2.2 Device Management
- [✅] Device check-in API endpoint
- [✅] Device registration API endpoint
- [✅] Device profile creation and storage
- [✅] Device status tracking (registered, provisioned, etc.)
- [✅] Device settings storage and retrieval
- [✅] Device last seen tracking
- [🚧] All settings.py variables manageable from Admin UI
- [🚧] Remote settings staging and pushing to devices
- [🚧] Settings history tracking

### 2.3 Unit Connector Integration
- [✅] Unit Connector pairing system
- [✅] Unit Connector listing page
- [✅] Shared key management between Admin and UCs
- [✅] Unit Connector last seen tracking
- [🚧] Automatic shared key refresh mechanism
- [🚧] Connectivity monitoring and alerting
- [🔄] One-click secure access to customer UC admin area

### 2.4 Customer & Location Management
- [✅] Customer company profile creation
- [✅] Customer ID assignment
- [🚧] Customer field locations hierarchy
- [🚧] Device zones within locations
- [🚧] Device groups within zones
- [🚧] Device specific locations
- [🚧] Location-based device organization and filtering
- [🚧] Unit Connector association by domain URL
- [✅] Device assignment to customers

### 2.5 Firmware Management
- [✅] Firmware file listing from GitHub
- [✅] Firmware version tracking
- [✅] Firmware manifest computation (SHA256)
- [✅] Firmware refresh from GitHub
- [✅] OTA firmware push to Unit Connectors
- [⏳] Version control: Admin specifies which firmware version devices should use
- [⏳] Firmware version distribution to Unit Connectors
- [⏳] Automated firmware update orchestration

### 2.6 Data Collection & Analytics
- [✅] Field data API endpoints
- [✅] Field data logging from Unit Connectors
- [🚧] Global data tabulation across all devices
- [🚧] Metric calculation and aggregation
- [🚧] Data parsing and manipulation tools
- [🚧] Dashboard widgets for data visualization
- [🚧] Shortcodes for data display with arguments
- [🚧] Customer location-based data grouping

### 2.7 Monitoring & Health
- [🚧] Device health status monitoring
- [🚧] Customer uptime monitoring
- [🚧] Performance KPI tracking
- [🚧] Response time monitoring
- [🚧] Alert system for connectivity loss
- [🚧] Alert system for device failures
- [✅] Audit logging system
- [✅] Command logging
- [✅] Notification system (basic)

### 2.8 Support System
- [⏳] Admin support portal creation
- [⏳] Customer ticket submission from Unit Connector
- [⏳] Ticket listing and management interface
- [⏳] Ticket routing and assignment
- [⏳] Support request tracking
- [⏳] Customer UC secure access for admins
- [⏳] Support metrics and SLA tracking
- [⏳] Response time tracking

### 2.9 API Endpoints (Admin)
- [✅] /wp-json/tmon-admin/v1/device/check-in
- [✅] /wp-json/tmon-admin/v1/device/register
- [✅] /wp-json/tmon-admin/v1/device/provision
- [✅] /wp-json/tmon-admin/v1/field-data/upload
- [✅] /wp-json/tmon-admin/v1/uc/pair
- [🚧] /wp-json/tmon-admin/v1/device/suspend
- [🚧] /wp-json/tmon-admin/v1/device/resume
- [🚧] /wp-json/tmon-admin/v1/firmware/version-control
- [⏳] All API endpoints fully documented

### 2.10 UI/UX
- [✅] Admin menu structure
- [✅] Device provisioning page
- [✅] Provisioned devices page
- [✅] Unit Connectors page
- [✅] Firmware management page
- [✅] Audit log page
- [✅] Notifications page
- [🚧] Groups & hierarchy page (partial)
- [🚧] Global dashboard with fleet overview
- [🚧] Customer management interface
- [🚧] Support portal interface
- [🔄] Uniform UI feel across all admin pages
- [🔄] Responsive design optimization

### 2.11 Wiki System
- [⏳] Wiki creation and management interface
- [⏳] Wiki content editor
- [⏳] Wiki categories and organization
- [⏳] Wiki content pushed to Unit Connectors
- [⏳] Customer-facing wiki display in Unit Connector

---

## 3. Unit Connector Plugin (WordPress)

### 3.1 Core UC Features
- [✅] Plugin installation and activation on customer sites
- [✅] Shared Key for UC Integration configuration
- [✅] TMON Admin hub URL configuration
- [✅] Device check-in API endpoint
- [✅] Device data ingestion
- [✅] Device listing and status display
- [🚧] Automatic shared key refresh button and registration
- [🚧] Only assigned devices visible/accessible to customer

### 3.2 Device Management (UC)
- [✅] Device provisioning interface for customers
- [✅] Device claiming system
- [✅] Device settings management
- [✅] Device last seen tracking
- [✅] Device status monitoring
- [🚧] All settings.py variables manageable from UC UI
- [🚧] Remote settings staging to devices via UC
- [🔄] Device assignment verification from Admin

### 3.3 Data Display & Visualization
- [✅] Shortcodes for device data display
- [✅] Device status widgets
- [✅] Field data table display
- [✅] Historical data charts
- [✅] Data export to CSV
- [🚧] Single sensor value widgets (temp, humidity)
- [🚧] Dashboard widgets for system info and status
- [🚧] Location-based device grouping in displays
- [🚧] Customizable dashboards
- [🚧] Multiple device display with arguments

### 3.4 Command System
- [✅] Device command queueing
- [✅] Command status tracking (pending, delivered, completed)
- [✅] Command poll endpoint for devices
- [✅] Relay control commands
- [✅] Reboot command
- [🚧] Firmware update command via UC
- [🚧] Settings update command
- [🚧] File transfer commands
- [✅] Command history and logging
- [✅] Command shortcodes for UI

### 3.5 Field Data Management (UC)
- [✅] Field data upload endpoint
- [✅] Field data storage in database
- [✅] Field data log file storage
- [✅] Field data CSV export
- [✅] Field data forwarding to Admin
- [✅] Data filtering and search
- [🚧] Data retention policies
- [🚧] Automated data cleanup

### 3.6 API Endpoints (UC)
- [✅] /wp-json/tmon-uc/v1/device/check-in
- [✅] /wp-json/tmon-uc/v1/device/claim
- [✅] /wp-json/tmon-uc/v1/field-data/upload
- [✅] /wp-json/tmon-uc/v1/device/commands
- [✅] /wp-json/tmon-uc/v1/device/settings
- [🚧] /wp-json/tmon-uc/v1/device/file-transfer
- [⏳] All API endpoints fully documented

### 3.7 UI/UX (UC)
- [✅] UC settings page
- [✅] Provisioned devices page
- [✅] Device commands page
- [✅] Hub pairing page
- [🚧] Customer dashboard page
- [🚧] Data visualization dashboards
- [🚧] Wiki display page
- [🔄] Uniform UI feel with Admin plugin
- [🔄] Responsive design optimization
- [🔄] Ajax-based dynamic updates

### 3.8 Support Integration
- [⏳] Support ticket submission interface
- [⏳] Ticket listing for customer users
- [⏳] Ticket status tracking
- [⏳] Communication with Admin support portal
- [⏳] Support request API endpoints

### 3.9 Hub Integration
- [✅] Hub pairing with Admin plugin
- [✅] Hub key validation
- [✅] Device list sync from Admin
- [✅] Settings sync from Admin
- [🚧] Firmware version control from Admin
- [🔄] Connectivity status monitoring
- [🔄] Auto-reconnect on connection loss

---

## 4. System Integration & Communication

### 4.1 Device ↔ TMON Admin
- [✅] First boot registration flow
- [✅] MACHINE_ID to UNIT_ID mapping
- [✅] Firmware version checking
- [✅] Provisioning data retrieval
- [🚧] Firmware version enforcement
- [🔄] Check-in interval optimization

### 4.2 Device ↔ Unit Connector
- [✅] Post-provisioning check-in (300s interval)
- [✅] Field data batch upload
- [✅] Command polling
- [✅] Settings fetch and apply
- [✅] Device status heartbeat
- [🚧] File transfer (device ↔ UC)
- [🔄] Connection resilience and retry

### 4.3 Unit Connector ↔ TMON Admin
- [✅] UC pairing and registration
- [✅] Shared key authentication
- [✅] Device data forwarding
- [✅] Device list synchronization
- [🚧] Firmware update relay to devices
- [🚧] Plugin update distribution
- [🔄] Bidirectional connectivity monitoring

### 4.4 Base Node ↔ Remote Node
- [✅] LoRa mesh communication
- [✅] Scheduled sync windows
- [🚧] Network credential verification
- [🚧] Check-in time assignment
- [🚧] Command relay (Admin/UC → Base → Remote)
- [🚧] Data relay (Remote → Base → UC/Admin)
- [🚧] File transfer relay
- [✅] HMAC authentication between nodes
- [✅] Encrypted payloads

---

## 5. Security & Authentication

### 5.1 Device Security
- [✅] MACHINE_ID as immutable device identifier
- [✅] LoRa HMAC frame signing
- [✅] LoRa ChaCha20 payload encryption
- [✅] LoRa replay protection
- [🚧] Device secrets provisioning
- [🚧] Secure credential storage

### 5.2 API Security
- [✅] Shared key authentication (Admin ↔ UC)
- [✅] Basic auth for device API calls (legacy)
- [🚧] Token-based authentication migration
- [🚧] API rate limiting
- [🚧] Request validation and sanitization
- [✅] Nonce-based CSRF protection in WordPress

### 5.3 LoRa Network Security
- [✅] Network HMAC secret
- [✅] Encryption secret
- [⏳] LORA_NETWORK_NAME and LORA_NETWORK_PASSWORD
- [⏳] Network credential verification
- [✅] Counter-based replay protection
- [✅] Reject unsigned frames option

---

## 6. Testing & Quality Assurance

### 6.1 Unit Tests
- [⏳] Device firmware unit tests
- [⏳] Admin plugin unit tests
- [⏳] UC plugin unit tests
- [⏳] API endpoint tests
- [⏳] LoRa communication tests

### 6.2 Integration Tests
- [🚧] End-to-end provisioning flow test
- [🚧] Data flow test (device → UC → Admin)
- [🚧] Command flow test (Admin → UC → device)
- [⏳] Multi-device LoRa mesh test
- [⏳] Firmware update flow test

### 6.3 Load & Performance Tests
- [⏳] Multiple device simultaneous check-in test
- [⏳] Large data batch upload test
- [⏳] UC plugin performance under load
- [⏳] Admin plugin scalability test

---

## 7. Documentation

### 7.1 User Documentation
- [✅] README.md (root)
- [✅] micropython/README.md
- [🚧] Admin plugin user guide
- [🚧] UC plugin user guide
- [🚧] Device provisioning guide
- [⏳] Customer onboarding guide
- [⏳] Troubleshooting guide

### 7.2 Developer Documentation
- [✅] AGENT_INSTRUCTIONS.md
- [✅] COMMANDS.md
- [✅] CONTEXT_RESTORE.md
- [🚧] API documentation (Admin endpoints)
- [🚧] API documentation (UC endpoints)
- [🚧] MicroPython API documentation
- [🚧] Architecture diagrams
- [🚧] Database schema documentation

### 7.3 Wiki Content
- [⏳] Admin wiki structure
- [⏳] Customer-facing wiki content
- [⏳] FAQ section
- [⏳] Video tutorials

---

## 8. DevOps & Deployment

### 8.1 Version Control
- [✅] Git repository structure
- [✅] Firmware version in settings.py
- [✅] Changelog tracking
- [🚧] Automated version bumping
- [🚧] Release tagging strategy

### 8.2 CI/CD
- [⏳] Automated testing pipeline
- [⏳] Firmware build automation
- [⏳] Plugin build and packaging
- [⏳] Deployment automation
- [⏳] Rollback procedures

### 8.3 Monitoring & Logging
- [✅] Device logging to files
- [✅] Admin audit logging
- [✅] UC command logging
- [🚧] Centralized log aggregation
- [🚧] Real-time monitoring dashboard
- [🚧] Alert system for critical errors

---

## 9. Performance & Optimization

### 9.1 Device Performance
- [✅] Garbage collection optimization
- [✅] Memory management in tasks
- [✅] Efficient field data batching
- [✅] Log file rotation
- [🔄] Power consumption optimization for remote nodes
- [🔄] LoRa transmission efficiency

### 9.2 Plugin Performance
- [✅] Database query optimization
- [✅] Caching strategies
- [🚧] Ajax-based UI updates
- [🚧] Lazy loading for large datasets
- [🚧] Background job processing

### 9.3 Network Optimization
- [✅] GZIP compression for data upload
- [✅] Batch data transmission
- [✅] Connection retry with exponential backoff
- [🔄] Network request minimization
- [🔄] CDN for static assets

---

## 10. Maintenance & Support Tools

### 10.1 Admin Tools
- [✅] Device diagnostics page
- [✅] Endpoint validation tool
- [✅] OTA job management
- [🚧] Bulk device operations
- [🚧] Database maintenance tools
- [⏳] System health check utility

### 10.2 Customer Tools
- [✅] Device claiming interface
- [✅] Basic device controls
- [🚧] Self-service settings management
- [🚧] Data export tools
- [⏳] Support ticket system

### 10.3 Developer Tools
- [✅] Debug mode toggles
- [✅] Test scripts (scripts/)
- [🚧] Device simulator
- [🚧] API testing suite
- [⏳] Development environment setup automation

---

## Priority Items for Next Sprint

### High Priority (Critical Path)
1. ⏳ Implement LORA_NETWORK_NAME and LORA_NETWORK_PASSWORD authentication
2. 🚧 Complete base station remote node tracking table
3. 🚧 Finish scheduled check-in time assignment for remote nodes
4. 🚧 Implement device suspension toggle UI and enforcement
5. ⏳ Build frost and heat watch system
6. 🚧 Create all settings.py remote management UI (Admin + UC)
7. ⏳ Implement firmware version control from Admin
8. ⏳ Develop OLED display enhancements (temp in F, signal bars, time, Unit ID)

### Medium Priority (Important Features)
1. 🚧 Customer location hierarchy system
2. ⏳ Support ticket system (Admin + UC)
3. 🚧 Global data tabulation and analytics
4. 🚧 Dashboard widgets and shortcodes expansion
5. 🚧 UC automatic shared key refresh mechanism
6. 🚧 Complete file transfer system (device ↔ UC)
7. ⏳ Wiki system implementation

### Low Priority (Nice to Have)
1. 🔄 UI/UX polish and uniformity
2. 🔄 Performance optimization across all components
3. ⏳ Comprehensive test suite
4. ⏳ Complete documentation
5. ⏳ CI/CD pipeline setup
6. ⏳ Video tutorials and training materials

---

## Notes
- This TODO list is based on the comprehensive scope provided and existing repository analysis
- Status indicators reflect current implementation state as of analysis date
- Items marked as ✅ COMPLETED have working code in the repository
- Items marked as 🚧 IN PROGRESS have partial implementation
- Items marked as ⏳ PENDING have no implementation yet
- Items marked as 🔄 NEEDS REVIEW are implemented but require verification

---

**Last Updated:** February 1, 2026  
**Repository:** github.com/kevinnutt83/TMON  
**Firmware Version:** v2.06.9

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

---

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
