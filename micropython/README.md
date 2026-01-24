# TMON MicroPython Device Firmware (v2.06.x)

## Overview
MicroPython-based firmware for TMON environmental monitoring devices supporting LoRa mesh networking, WiFi connectivity, sensor sampling, relay control, and WordPress/Unit Connector integration.

## Quick Start
1. Flash the firmware to your ESP32/RP2040 device.
2. Configure `settings.py` with your deployment parameters:
   - `WORDPRESS_API_URL` — Unit Connector site URL
   - `TMON_ADMIN_API_URL` — Admin hub URL for provisioning
   - `WIFI_SSID` / `WIFI_PASS` — WiFi credentials
   - `NODE_TYPE` — Device role (`base`, `remote`, or `wifi`)
3. Power on; the device auto-registers with the TMON Admin hub.
4. Monitor and manage via the WordPress admin UI.

## Device Roles (NODE_TYPE)

| Role | Description |
|------|-------------|
| `base` | Hosts LoRa network, connects to WordPress/Unit Connector via WiFi, backhauls remote telemetry and relays commands. |
| `wifi` | WiFi-only node (no LoRa). Uses WiFi for telemetry, commands, and OTA. |
| `remote` | LoRa-only device that syncs with a base station; does not perform HTTP calls after provisioning. |

## Key Features

### Provisioning & Registration
- First-boot WiFi check-in to TMON Admin hub (`TMON_ADMIN_API_URL`)
- Automatic UNIT_ID assignment and persistence
- Staged settings delivery and application
- Reboot guard to prevent soft-reset loops
- Remote nodes disable WiFi after provisioning (LoRa-only mode)

### LoRa Communication
- SX1262-based LoRa radio with configurable frequency, bandwidth, spreading factor
- Base-managed sync scheduling (`nextLoraSync` epochs assigned to remotes)
- Chunked payload transfer for large telemetry
- Optional HMAC authentication and ChaCha20 encryption
- Replay protection via monotonic counters
- CAD (Channel Activity Detection) with backoff

### Sensor Sampling
- BME280 (temperature, humidity, barometric pressure)
- DHT11 support (optional)
- Frost/heat watch with configurable thresholds and relay actions
- GPS coordinates (manual, module, or network source)

### Relay Control
- Up to 8 relays with per-relay enable flags
- Runtime caps and safety limits
- Runtime telemetry tracking

### OLED Display
- 128x64 SSD1309 display support
- Header: voltage/temperature flip, WiFi/LoRa signal bars
- Body: sensor readings during sampling, relay states
- Footer: device name
- Status banners and message overlays
- Configurable update interval and page rotation

### OTA Updates
- Version check against GitHub repository
- Manifest-based file downloads with SHA256 verification
- Backup/restore on failure
- Signature verification (HMAC or detached sig)
- Files allowlist for security

### WordPress/Unit Connector Integration
- Field data uploads with batching and backlog
- Staged settings fetch and application
- Command polling and execution
- Heartbeat/check-in endpoints
- Native WordPress Application Password authentication

## Directory Structure

```
micropython/
├── main.py              # Main event loop and task orchestration
├── boot.py              # Boot sequence, early WiFi/provisioning
├── settings.py          # All configuration constants
├── settings_apply.py    # Staged settings application logic
├── lora.py              # LoRa radio driver and protocol
├── wifi.py              # WiFi connection management
├── wprest.py            # WordPress REST API client
├── oled.py              # OLED display driver and rendering
├── sampling.py          # Sensor sampling routines
├── relay.py             # Relay control with safety caps
├── ota.py               # OTA update scaffolding
├── provision.py         # Provisioning client
├── utils.py             # Utilities, logging, persistence helpers
├── sdata.py             # Runtime telemetry state variables
├── encryption.py        # ChaCha20/Poly1305 encryption
├── config_persist.py    # File persistence helpers
├── debug.py             # Debug logging module
├── engine_controller.py # RS485 engine/pump control
├── firmware_updater.py  # Firmware download helper
├── tmon.py              # Frost/heat watch operations
├── lib/                 # Third-party libraries (BME280, SX126x, etc.)
└── tests/               # Test scripts
```

## Configuration (settings.py)

### Identity & Provisioning
- `UNIT_ID` — 6-digit unit identifier (assigned by Admin)
- `UNIT_Name` — Human-friendly device name
- `MACHINE_ID` — Chipset UID (auto-detected)
- `NODE_TYPE` — Device role
- `TMON_ADMIN_API_URL` — Admin hub for provisioning
- `WORDPRESS_API_URL` — Unit Connector site URL

### WiFi
- `WIFI_SSID` / `WIFI_PASS` — Network credentials
- `WIFI_CONN_RETRIES` / `WIFI_BACKOFF_S` — Connection retry settings
- `WIFI_ALWAYS_ON_WHEN_UNPROVISIONED` — Allow WiFi for unprovisioned remotes
- `WIFI_DISABLE_AFTER_PROVISION` — Disable WiFi for remotes post-provisioning

### LoRa Radio
- `FREQ` — Operating frequency (default 915.0 MHz)
- `BW` / `SF` / `CR` — Bandwidth, spreading factor, coding rate
- `POWER` — Transmit power
- `LORA_HMAC_ENABLED` / `LORA_HMAC_SECRET` — Frame authentication
- `LORA_ENCRYPT_ENABLED` / `LORA_ENCRYPT_SECRET` — Payload encryption
- `LORA_SYNC_WINDOW` / `LORA_SLOT_SPACING_S` — Sync scheduling

### Sensors
- `ENABLE_sensorBME280` / `ENABLE_sensorDHT11` — Sensor enables
- `SAMPLE_TEMP` / `SAMPLE_BAR` / `SAMPLE_HUMID` — Sampling toggles
- `FROSTWATCH_*` / `HEATWATCH_*` — Threshold temperatures

### Relays
- `ENABLE_RELAY1..8` — Per-relay enable flags
- `RELAY_PIN1..8` — GPIO pin assignments
- `RELAY_SAFETY_MAX_RUNTIME_MIN` — Global runtime cap
- `RELAY_RUNTIME_LIMITS` — Per-relay caps (dict)

### OLED Display
- `ENABLE_OLED` — Display enable
- `OLED_UPDATE_INTERVAL_S` — Refresh interval
- `OLED_SCROLL_ENABLED` / `OLED_PAGE_ROTATE_INTERVAL_S` — Page rotation
- `DISPLAY_NET_BARS` — Show WiFi/LoRa signal bars

### OTA
- `OTA_ENABLED` — Enable OTA updates
- `OTA_VERSION_ENDPOINT` — Version check URL
- `OTA_MANIFEST_URL` — Manifest JSON URL
- `OTA_FIRMWARE_BASE_URL` — Base URL for file downloads
- `OTA_FILES_ALLOWLIST` — Permitted files for update
- `OTA_HASH_VERIFY` — Enable SHA256 verification

### Field Data & Logging
- `FIELD_DATA_SEND_INTERVAL` — Upload interval (seconds)
- `FIELD_DATA_MAX_BATCH` — Max records per POST
- `LOG_DIR` — Log directory path
- `DEBUG` / `DEBUG_*` — Debug output toggles

## Logs

| File | Purpose |
|------|---------|
| `/logs/lora.log` | LoRa confirmations and activity |
| `/logs/lora_errors.log` | LoRa and general errors |
| `/logs/field_data.log` | Pending telemetry records |
| `/logs/data_history.log` | Rotated historical data |
| `/logs/provisioning.log` | Provisioning events |
| `/logs/unit_id.txt` | Persisted UNIT_ID |
| `/logs/unit_name.txt` | Persisted UNIT_Name |
| `/logs/wordpress_api_url.txt` | Persisted WordPress URL |
| `/logs/provisioned.flag` | Provisioning complete flag |
| `/logs/remote_settings.staged.json` | Pending settings |
| `/logs/remote_settings.applied.json` | Applied settings snapshot |

## Runtime Tasks

| Task | Interval | Description |
|------|----------|-------------|
| `lora_comm_task` | 1s | LoRa init/retry and communication |
| `sample_task` | 60s | Sensor sampling and field data recording |
| `periodic_field_data_task` | configurable | Field data upload to WordPress |
| `periodic_command_poll_task` | 10s | Poll for queued commands |
| `periodic_provision_check` | 30s | Provisioning check-in loop |
| `periodic_uc_checkin_task` | 300s | Unit Connector heartbeat |
| `settings_apply_loop` | 60s | Apply staged settings |
| `ota_version_task` | 30min | Check for OTA updates |
| `ota_apply_task` | 10min | Apply pending OTA updates |
| `wifi_rssi_monitor` | 30s | WiFi signal strength sampling |
| `_oled_loop` | 10s | OLED display refresh |

## LED Status Colors

| Status | Color |
|--------|-------|
| INFO/SUCCESS | Green/Lime |
| WARN/WARNING | Yellow/Orange |
| ERROR | Red |
| WIFI | Blue |
| LORA_RX | Violet |
| LORA_TX | Teal |
| SAMPLE_TEMP | Magenta |
| SAMPLE_HUMID | Cyan |
| SAMPLE_BAR | Sky Blue |

## Troubleshooting

### Common Issues

**"ImportError: can't import name X"**
- Ensure all firmware files are uploaded and match the manifest version.

**LoRa error -1 or radio faults**
- Firmware re-initializes the radio automatically.
- Check pin assignments and power supply.

**Field data upload failures**
- Verify `WORDPRESS_API_URL` and `FIELD_DATA_APP_PASS` credentials.
- Check WiFi connectivity and server availability.

**Memory errors**
- Batching is enabled by default to reduce memory pressure.
- GC runs automatically at key points; check `free_mem` in telemetry.

**Provisioning not completing**
- Ensure `TMON_ADMIN_API_URL` is correct and reachable.
- Check `/logs/provisioning.log` for errors.

### Debug Toggles

Enable specific debug output in `settings.py`:
```python
DEBUG = True
DEBUG_LORA = True
DEBUG_WIFI_CONNECT = True
DEBUG_PROVISION = True
DEBUG_OTA = True
DEBUG_SAMPLING = True
```

## API Endpoints Used

### TMON Admin (Provisioning)
- `POST /wp-json/tmon-admin/v1/device/check-in` — Device registration
- `POST /wp-json/tmon-admin/v1/device/confirm-applied` — Confirm provisioning

### Unit Connector (Operations)
- `POST /wp-json/tmon/v1/device/field-data` — Telemetry upload
- `GET /wp-json/tmon/v1/device/staged-settings` — Fetch staged settings
- `POST /wp-json/tmon/v1/admin/device/settings-applied` — Confirm settings applied
- `POST /wp-json/tmon/v1/device/commands` — Poll for commands
- `POST /wp-json/tmon/v1/device/command/confirm` — Confirm command execution
- `POST /wp-json/tmon/v1/device/heartbeat` — Heartbeat ping

## Security Notes

- Use Application Passwords for WordPress authentication (not legacy JWT).
- LoRa HMAC and encryption secrets should be unique per deployment.
- OTA manifest signatures prevent tampering with update files.
- Credentials in `settings.py` should be secured in production.

## License

See repository root for license information.
