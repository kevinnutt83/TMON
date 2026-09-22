# TMON — Environmental Monitoring, LoRa Networking & Device Management Platform

TMON is an end-to-end IoT platform for deploying, monitoring, configuring, and maintaining environmental monitoring devices.

The platform combines:

- **MicroPython firmware** running on ESP32-class hardware
- **SX1262 LoRa communications** for remote/battery-powered devices
- **WiFi/HTTPS connectivity** for cloud-connected devices and base stations
- **WordPress-based TMON Admin** for centralized provisioning and fleet management
- **WordPress Unit Connector** installations for customer/site-level device management
- **Sensor, relay, OLED, diagnostics, logging, and telemetry subsystems**
- **Remote command and staged-settings delivery**
- **OTA firmware distribution and integrity verification**
- **Remote-node scheduling and deep-sleep operation**
- **Device hierarchy, claims, authorization, audit logging, and reporting**

TMON is designed around a distributed architecture in which remote devices can operate without direct Internet access while a base station provides the LoRa-to-WiFi bridge.

---

## Table of Contents

1. [Platform Overview](#platform-overview)
2. [Architecture](#architecture)
3. [How TMON Works](#how-tmon-works)
4. [Device Roles](#device-roles)
5. [Device Lifecycle](#device-lifecycle)
6. [LoRa Network](#lora-network)
7. [LoRa Session Model](#lora-session-model)
8. [Telemetry Pipeline](#telemetry-pipeline)
9. [Commands and Remote Control](#commands-and-remote-control)
10. [Settings Management](#settings-management)
11. [Provisioning](#provisioning)
12. [TMON Admin](#tmon-admin)
13. [Unit Connector](#unit-connector)
14. [Sensors and Actuators](#sensors-and-actuators)
15. [Remote Deep-Sleep Operation](#remote-deep-sleep-operation)
16. [OLED and Device Observability](#oled-and-device-observability)
17. [OTA Firmware Updates](#ota-firmware-updates)
18. [Security and Integrity](#security-and-integrity)
19. [Persistence and Logs](#persistence-and-logs)
20. [REST API Overview](#rest-api-overview)
21. [Repository Structure](#repository-structure)
22. [Configuration](#configuration)
23. [Development and Release Workflow](#development-and-release-workflow)
24. [Testing](#testing)
25. [Troubleshooting](#troubleshooting)
26. [Documentation Map](#documentation-map)
27. [Current Repository Status](#current-repository-status)
28. [License](#license)

---

# Platform Overview

TMON separates the system into four major layers:

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         TMON PLATFORM                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  DEVICE LAYER                                                      │
│                                                                     │
│   ┌─────────────┐       LoRa        ┌──────────────┐               │
│   │   REMOTE    │◄─────────────────►│     BASE     │               │
│   │    NODE     │                   │    NODE      │               │
│   │             │                   │              │               │
│   │ Sensors     │                   │ LoRa + WiFi  │               │
│   │ Battery     │                   │ Aggregation  │               │
│   │ Deep Sleep  │                   │ Backhaul     │               │
│   └─────────────┘                   └──────┬───────┘               │
│                                             │                       │
│                                             │ HTTPS                 │
│                                             ▼                       │
│  SITE / EDGE LAYER                                                   │
│                                                                     │
│                                    ┌──────────────────┐             │
│                                    │ UNIT CONNECTOR   │             │
│                                    │                  │             │
│                                    │ Device Registry  │             │
│                                    │ Telemetry        │             │
│                                    │ Commands         │             │
│                                    │ Settings         │             │
│                                    │ Dashboards       │             │
│                                    └────────┬─────────┘             │
│                                             │                       │
│                                             │ Admin API             │
│                                             ▼                       │
│  CENTRAL MANAGEMENT LAYER                                            │
│                                                                     │
│                                    ┌──────────────────┐             │
│                                    │   TMON ADMIN     │             │
│                                    │                  │             │
│                                    │ Provisioning     │             │
│                                    │ Fleet Management │             │
│                                    │ Authorization    │             │
│                                    │ Hierarchy        │             │
│                                    │ Claims           │             │
│                                    │ Diagnostics      │             │
│                                    │ OTA Coordination │             │
│                                    └──────────────────┘             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

A deployment does not require every device to have Internet access.

A typical deployment is:

```text
                    Internet / HTTPS
                           │
                           ▼
                  ┌─────────────────┐
                  │   TMON ADMIN    │
                  │ Central Control │
                  └────────┬────────┘
                           │
                     Admin / UC API
                           │
                           ▼
                  ┌─────────────────┐
                  │ UNIT CONNECTOR │
                  │ Customer Site   │
                  └────────┬────────┘
                           │
                         WiFi
                           │
                           ▼
                  ┌─────────────────┐
                  │   BASE NODE     │
                  │   LoRa + WiFi   │
                  └────────┬────────┘
                           │
                     SX1262 LoRa
                           │
             ┌─────────────┼─────────────┐
             │             │             │
             ▼             ▼             ▼
        ┌─────────┐   ┌─────────┐   ┌─────────┐
        │ REMOTE  │   │ REMOTE  │   │ REMOTE  │
        │ SENSOR  │   │ SENSOR  │   │ SENSOR  │
        └─────────┘   └─────────┘   └─────────┘
```

---

# How TMON Works

At a high level, TMON performs five continuous functions:

| Function | Responsibility |
|---|---|
| **Measure** | Devices collect environmental and system telemetry |
| **Communicate** | Devices exchange data using LoRa or WiFi/HTTPS |
| **Persist** | Telemetry, settings, identities, and diagnostics survive transient failures |
| **Manage** | WordPress interfaces control provisioning, settings, commands, and devices |
| **Maintain** | OTA, diagnostics, logging, health monitoring, and recovery keep deployments operational |

The normal lifecycle is:

```text
BOOT
  │
  ▼
Load persisted identity/settings
  │
  ▼
Determine NODE_TYPE
  │
  ├───────────────┬────────────────┐
  ▼               ▼                ▼
REMOTE           BASE             WIFI
  │               │                │
  ▼               ▼                ▼
LoRa startup    LoRa + WiFi       WiFi
  │               │                │
  └───────────────┴────────────────┘
                  │
                  ▼
             Sample sensors
                  │
                  ▼
             Create telemetry
                  │
          ┌───────┴────────┐
          ▼                ▼
      LoRa path        WiFi path
          │                │
          ▼                ▼
       Base       Unit Connector
          │                │
          └───────┬────────┘
                  ▼
             TMON Admin
                  │
                  ▼
       Commands / Settings / OTA
```

---

# Device Roles

TMON firmware supports three primary operating roles.

| Role | WiFi | LoRa | Internet | Typical Purpose |
|---|---:|---:|---:|---|
| `base` | Yes | Yes | Yes | LoRa coordinator and cloud backhaul |
| `remote` | Normally disabled after provisioning | Yes | No | Battery-powered field sensor |
| `wifi` | Yes | No | Yes | Directly connected monitoring device |

## Base Node

A base node acts as the bridge between the LoRa field network and WordPress.

Responsibilities include:

- Maintaining the LoRa radio
- Accepting remote-node sessions
- Receiving remote telemetry
- Sending acknowledgements
- Managing remote synchronization
- Forwarding remote telemetry to Unit Connector
- Relaying applicable commands/settings
- Maintaining remote-node state
- Providing the Internet backhaul

```text
Remote A ─┐
Remote B ─┼── LoRa ──► BASE ── WiFi/HTTPS ──► Unit Connector
Remote C ─┘
```

## Remote Node

Remote nodes are designed for installations where continuous WiFi connectivity is undesirable or unavailable.

They can:

- Sample sensors
- Store telemetry
- Wake at scheduled intervals
- Communicate with a base over LoRa
- Receive synchronization timing
- Receive applicable commands/settings
- Enter deep sleep to reduce power consumption

## WiFi Node

A WiFi node bypasses LoRa and communicates directly with the WordPress backend.

```text
WiFi Node
    │
    │ HTTPS
    ▼
Unit Connector
    │
    ▼
TMON Admin
```

---

# Device Lifecycle

TMON separates device identity, provisioning, configuration, operation, and maintenance.

```text
┌─────────────┐
│ Manufactured │
│ / Unassigned │
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│ First Boot       │
│ MACHINE_ID known │
└──────┬───────────┘
       │ WiFi
       ▼
┌──────────────────┐
│ Admin Check-In   │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Provisioning     │
│ UNIT_ID / Role   │
│ Site / Settings  │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Configuration    │
│ Applied + Saved  │
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Normal Operation │
│ Sampling         │
│ Communications   │
│ Commands         │
└──────┬───────────┘
       │
       ├──── Settings update
       ├──── Command
       ├──── Diagnostics
       ├──── OTA update
       └──── Suspension / recovery
```

Device identity uses the relationship between:

```text
MACHINE_ID
     │
     │ permanently associated
     ▼
UNIT_ID
     │
     ▼
Device / Site / Company
```

---

# LoRa Network

TMON uses an SX1262-based LoRa radio.

The current repository configuration includes:

| Parameter | Current Repository Value |
|---|---:|
| Frequency | 915 MHz |
| Bandwidth | 125 kHz |
| Spreading Factor | SF10 |
| Coding Rate | 4/7 |
| Sync Word | `0xF4` |
| TX Power | 17 |
| Hardware CRC | Enabled |
| CAD | Enabled |
| Preamble | 12 symbols |

These values are configuration defaults rather than protocol requirements; deployments can override applicable settings through `settings.py` and the staged-settings system.

The SX1262 radio is used for:

- Base/remote communication
- Remote registration
- Session establishment
- Telemetry transfer
- ACKs
- Synchronization timing
- Command delivery
- Remote control traffic
- Optional OTA traffic

---

# LoRa Session Model

TMON does not treat a remote telemetry exchange as a collection of unrelated packets.

A controlled session is used to coordinate communication between a base and remote.

```text
REMOTE                                  BASE
  │                                      │
  │──────────── HELLO ──────────────────►│
  │                                      │
  │◄──────────── READY ─────────────────│
  │                                      │
  │──────────── DATA / CHUNKS ──────────►│
  │                                      │
  │◄──────────── ACK / REPAIR ──────────│
  │                                      │
  │──────────── END ────────────────────►│
  │                                      │
  │◄──────────── FINAL ACK ─────────────│
  │                                      │
  │──────────── release / sleep ────────│
  │                                      │
```

The session exists to solve several problems inherent to low-bandwidth radio:

- Payloads may exceed a practical single-frame size.
- Frames can be lost.
- ACKs can be lost.
- A remote may wake at a scheduled time rather than remaining online.
- The base must distinguish a new session from stale FIFO/radio data.
- The radio FIFO must be handled using the packet's actual offset/length rather than assuming a fixed receive window.
- Repair traffic must be bounded so that one bad exchange does not hold the network indefinitely.

The firmware contains explicit controls for:

- HELLO retry timing
- Session timeout
- Idle release
- Repair windows
- ACK intervals
- Maximum missed rounds
- Inter-chunk spacing
- Chunk sizing
- CAD/backoff
- Remote ACK wait periods

---

# Telemetry Pipeline

Telemetry begins at the sensor and ultimately becomes a normalized field-data record.

```text
┌───────────────┐
│ Physical      │
│ Sensors       │
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ sampling.py   │
│ Sensor reads  │
└───────┬───────┘
        │
        ▼
┌────────────────────┐
│ Field-data record  │
│ Compact / batched  │
└─────────┬──────────┘
          │
      ┌───┴────┐
      │        │
      ▼        ▼
    LoRa      WiFi
      │        │
      ▼        ▼
    Base       UC
      │        │
      └───┬────┘
          ▼
      TMON Admin
```

Supported telemetry includes:

- Temperature
- Humidity
- Barometric pressure
- System voltage
- CPU/device temperature
- Sensor status
- Relay state/runtime
- GPS
- LoRa RSSI/SNR
- WiFi signal information
- Error information
- Device health information
- Frost/heat monitoring
- Optional additional sensors

Field data is optimized using batching, compact keys, optional omission of default values, retry/backoff, and adaptive backpressure.

---

# Commands and Remote Control

Commands can originate from the management layer and ultimately reach a device through Unit Connector, WiFi, or the base/LoRa path.

| Command | Purpose |
|---|---|
| `set_var` | Change an allowed runtime setting |
| `run_func` | Invoke an approved device-side function |
| `firmware_update` | Schedule/check an OTA update |
| `relay_ctrl` | Turn a relay on/off with runtime controls |
| `toggle_relay` | Relay state control |
| `settings_update` | Apply a complete or partial settings payload |
| `settings_change` | Alternate settings update operation |
| `set_oled_message` | Display a message |
| `set_oled_banner` | Display a status banner |
| `clear_oled` | Remove an OLED message/banner |

Commands are queued and acknowledged so that a successful command is not repeatedly delivered.

---

# Settings Management

TMON has two distinct configuration concepts.

### Firmware defaults

```text
micropython/settings.py
```

### Runtime/staged configuration

```text
                 TMON Admin
                     │
                     ▼
              Unit Connector
                     │
              staged settings
                     │
                     ▼
                   Device
                     │
              validate allowlist
                     │
                     ▼
              persist locally
                     │
                     ▼
               apply settings
                     │
                     ▼
              applied snapshot
```

The firmware maintains staged and applied settings files and supports an allowlist for settings that may be changed remotely. Sensitive identity values such as `FIRMWARE_VERSION` and `MACHINE_ID` are excluded from staged modification.

Important persisted files include:

```text
/logs/remote_settings.staged.json
/logs/remote_settings.applied.json
/logs/custom_settings.json
/logs/device_settings-<UNIT_ID>.json
```

---

# Provisioning

Provisioning is centered around TMON Admin.

## First Boot

An unprovisioned device uses WiFi to contact the Admin hub.

```text
Device
  │
  │ MACHINE_ID
  │ check-in
  ▼
TMON Admin
  │
  │ assign configuration
  ▼
Device
```

Provisioning can establish:

- Unit ID
- Device name
- Node role
- Company association
- Site/hierarchy association
- WordPress/Unit Connector URL
- WiFi configuration
- GPS configuration
- Runtime settings

After provisioning:

- Remote nodes can disable WiFi.
- Base nodes retain WiFi for backhaul.
- WiFi nodes remain Internet-connected.
- Configuration is persisted locally.

---

# TMON Admin

`tm​on-admin/` provides the centralized management layer.

Its responsibilities include:

| Area | Function |
|---|---|
| Provisioning | Register and configure devices |
| Devices | View provisioned devices and state |
| Hierarchy | Company → Site → Zone → Cluster → Unit |
| Authorization | Determine whether incoming devices/data are trusted |
| Claims | Customer device claim workflow |
| Diagnostics | Device health and failure information |
| Field Data | Aggregate data from paired connectors |
| Audit | Record administrative actions |
| OTA | Coordinate firmware deployment |
| UC Integration | Pair and synchronize Unit Connector installations |

---

# Unit Connector

`unit-connector/` is the site/customer-side integration layer.

It provides:

- Device registry
- Field-data ingestion
- Telemetry normalization
- Device history
- Device status
- Relay controls
- Commands
- Staged settings
- Hub pairing
- Device claims
- CSV exports
- Notifications
- Offline-device detection
- Dashboard shortcodes
- Forwarding to TMON Admin

Its position in the architecture is:

```text
                    TMON Admin
                         ▲
                         │
                   Admin API
                         │
                         ▼
Device ──► Unit Connector ──► Site/User UI
             │
             ├── telemetry
             ├── commands
             ├── settings
             ├── OTA state
             └── device registry
```

---

# Sensors and Actuators

The firmware contains support for multiple environmental and device-control subsystems.

## Sensors

| Sensor / Source | Purpose |
|---|---|
| BME280 | Temperature, humidity, pressure |
| BME280 probe | External/additional environmental readings |
| DHT11 | Optional temperature/humidity |
| LTR390 | Optional light/UV |
| SGP40 | Optional VOC |
| TSL2591 | Optional high-range light measurement |
| Soil probe | Optional soil moisture |
| MPU925x | Optional motion/IMU |
| GPS | Position and accuracy information |
| System voltage | Battery/power monitoring |
| CPU/device temperature | Device health |

Not every sensor is enabled in every deployment.

## Relays

The firmware supports up to eight logical relays.

Relay management includes:

- Enable/disable flags
- GPIO assignments
- Runtime tracking
- Runtime safety limits
- Remote commands
- Device telemetry

---

# Remote Deep-Sleep Operation

Remote nodes are designed for low-power deployments.

```text
             ┌───────────────┐
             │ Deep Sleep    │
             └───────┬───────┘
                     │ timer / wake
                     ▼
             ┌───────────────┐
             │ Boot / Wake   │
             └───────┬───────┘
                     ▼
             ┌───────────────┐
             │ Read Sensors  │
             └───────┬───────┘
                     ▼
             ┌───────────────┐
             │ Build Data    │
             └───────┬───────┘
                     ▼
             ┌───────────────┐
             │ LoRa Session  │
             └───────┬───────┘
                     ▼
             ┌───────────────┐
             │ Receive ACK / │
             │ Next Timing   │
             └───────┬───────┘
                     ▼
             ┌───────────────┐
             │ Persist Sync  │
             │ Schedule      │
             └───────┬───────┘
                     ▼
             ┌───────────────┐
             │ Deep Sleep    │
             └───────────────┘
```

Remote sleep behavior can account for:

- Configured minimum/maximum sleep values
- Battery voltage
- Low-voltage thresholds
- Critical-voltage thresholds
- Sleep multipliers
- Base-provided synchronization timing
- External wake/recovery configuration

Remote nodes can persist the next synchronization epoch in:

```text
/logs/lora_next_sync.txt
```

---

# OLED and Device Observability

TMON devices can use a 128×64 SSD1309 OLED.

Typical information includes:

```text
┌──────────────────────────────┐
│ TMON     WiFi / LoRa   3.8V │
├──────────────────────────────┤
│                              │
│ Temperature       72.4 F     │
│ Humidity           48.2 %    │
│ Pressure         29.91 inHg │
│                              │
│ Relay 1           ON         │
│ Relay 2           OFF        │
│                              │
├──────────────────────────────┤
│        ● ○ ○ ○ ○             │
└──────────────────────────────┘
```

The display provides local visibility without requiring a network connection and supports configurable status pages, banners, and page rotation.

---

# OTA Firmware Updates

TMON supports manifest-driven firmware updates.

```text
TMON Admin
    │
    │ OTA job
    ▼
Unit Connector
    │
    ▼
Device
    │
    │ version check
    ▼
Manifest
    │
    │ file URLs + hashes
    ▼
Download
    │
    ▼
SHA256 verification
    │
    ▼
Backup / staging
    │
    ▼
Apply update
    │
    ▼
Reboot
    │
    ▼
Version acknowledgement
```

The update system supports:

- Version checking
- Manifest retrieval
- File allowlists
- SHA256 verification
- Retry handling
- Backup/restore
- Version comparison
- Update status reporting
- Optional manifest signature verification

Release packages are generated by:

```text
scripts/build_release_artifacts.sh
```

Typical output:

```text
dist/<tag>/
├── unit-connector-<tag>.zip
├── tmon-admin-<tag>.zip
├── micropython-<tag>.zip
└── SHA256SUMS.txt
```

---

# Security and Integrity

TMON uses multiple security layers.

## WordPress/API Security

The platform uses:

- WordPress authentication
- Application Passwords
- REST authorization
- Nonces for administrative forms
- WordPress capability checks
- Prepared SQL statements
- Input sanitization
- Output escaping
- Shared integration keys

## Unit Connector ↔ Admin

The two WordPress systems can authenticate using dedicated headers such as:

```text
X-TMON-ADMIN
X-TMON-HUB
X-TMON-READ
X-TMON-CONFIRM
```

## LoRa

LoRa communications can use:

- SX1262 hardware CRC
- Application-level CRC
- HMAC authentication
- Replay counters
- Replay windows
- Optional payload protection/encryption
- CAD/backoff

Important distinction:

```text
SX1262 Hardware CRC
        ≠
Application Authentication
        ≠
Payload Encryption
```

Hardware CRC detects transmission corruption; it does not establish that a packet originated from a trusted device.

---

# Persistence and Logs

Important device-side files include:

| File | Purpose |
|---|---|
| `/logs/unit_id.txt` | Persisted Unit ID |
| `/logs/machine_id.txt` | Persisted hardware identity |
| `/logs/unit_name.txt` | Persisted device name |
| `/logs/wordpress_api_url.txt` | Persisted WordPress endpoint |
| `/logs/provisioned.flag` | Provisioning state |
| `/logs/field_data.log` | Pending field data |
| `/logs/field_data.delivered.log` | Delivered field data |
| `/logs/data_history.log` | Historical telemetry |
| `/logs/lora.log` | LoRa activity |
| `/logs/lora_errors.log` | LoRa/error information |
| `/logs/provisioning.log` | Provisioning events |
| `/logs/debug.log` | Debug information |
| `/logs/remote_info.log` | Remote-node information |
| `/logs/custom_settings.json` | Persisted custom settings |
| `/logs/remote_settings.staged.json` | Pending staged settings |
| `/logs/remote_settings.applied.json` | Last applied settings |
| `/logs/lora_next_sync.txt` | Remote next-sync timing |

---

# REST API Overview

TMON uses multiple REST namespaces.

## TMON Admin

Representative endpoints include:

```text
POST /wp-json/tmon-admin/v1/device/check-in
POST /wp-json/tmon-admin/v1/device/confirm-applied
POST /wp-json/tmon-admin/v1/claim

GET  /wp-json/tmon-admin/v1/field-data

POST /wp-json/tmon-admin/v1/uc/key/register
POST /wp-json/tmon-admin/v1/uc/key/refresh
```

## Unit Connector

Representative device endpoints include:

```text
POST /wp-json/tmon/v1/device/field-data
POST /wp-json/tmon/v1/device/data-history
POST /wp-json/tmon/v1/device/ping

GET  /wp-json/tmon/v1/device/staged-settings

POST /wp-json/tmon/v1/device/commands
POST /wp-json/tmon/v1/device/command-complete

GET  /wp-json/tmon/v1/device/ota-jobs/{unit_id}
POST /wp-json/tmon/v1/device/ota-job-complete
```

The exact API surface is maintained by the plugin implementations and their documentation.

---

# Repository Structure

```text
TMON/
│
├── .github/
│   └── workflows/                 # CI / release workflows
│
├── micropython/                   # Device firmware
│   ├── main.py                    # Main scheduler / runtime
│   ├── boot.py                    # Boot sequence
│   ├── settings.py                # Firmware configuration
│   ├── settings_apply.py          # Staged settings
│   ├── lora.py                    # SX1262 / LoRa protocol
│   ├── remote_node.py             # Remote wake/sleep operation
│   ├── wifi.py                    # WiFi management
│   ├── wprest.py                  # WordPress REST client
│   ├── provision.py               # Provisioning
│   ├── sampling.py                # Sensor sampling
│   ├── sdata.py                   # Telemetry state
│   ├── oled.py                    # OLED display
│   ├── relay.py                   # Relay control
│   ├── ota.py                     # OTA handling
│   ├── firmware_updater.py        # Firmware update helper
│   ├── encryption.py              # Payload protection
│   ├── config_persist.py          # Persistent configuration
│   ├── utils.py                   # Logging/utilities
│   ├── debug.py                   # Debug subsystem
│   ├── engine_controller.py       # Optional RS485 engine control
│   ├── tmon.py                    # Frost/heat monitoring
│   ├── lib/                       # Third-party libraries
│   └── tests/                     # Firmware tests
│
├── tmon-admin/                    # Central WordPress plugin
├── unit-connector/                # Customer/site WordPress plugin
├── scripts/                       # Build and validation tooling
├── tests/                         # Repository-level tests
├── dist/                          # Generated release artifacts
│
├── COMMANDS.md                   # Device command reference
├── CHANGELOG.md                  # Change history
├── CONTEXT_RESTORE.md            # Development/context recovery
├── DEPLOYMENT_READY.md           # Deployment status/documentation
├── IMPLEMENTATION_COMPLETE.md    # Implementation record
├── TESTING_AND_DEPLOYMENT.md     # QA and deployment guide
├── TODO.md                       # Remaining work
└── README.md                     # This document
```

---

# Configuration

Most device-level configuration is centralized in:

```text
micropython/settings.py
```

| Category | Examples |
|---|---|
| Identity | `UNIT_ID`, `UNIT_Name`, `MACHINE_ID`, `NODE_TYPE` |
| Provisioning | Admin URL, provisioning intervals, retry limits |
| WiFi | SSID, password, retry/backoff |
| LoRa | Frequency, bandwidth, SF, CR, sync word, power |
| LoRa Sessions | HELLO timing, session timeout, ACK timing, repair |
| Remote Power | Deep sleep, battery thresholds, wake sources |
| Sensors | BME280, DHT11, light, VOC, soil, motion |
| Sampling | Temperature, pressure, humidity, voltage |
| Relays | GPIO, enable flags, runtime limits |
| OLED | Refresh, page rotation, network indicators |
| OTA | Version endpoint, manifest, hash verification |
| Commands | Poll interval, timeout, command limits |
| Diagnostics | Upload interval, retries, failure cooldown |
| Field Data | Batch size, retry policy, compression |
| Debugging | LoRa, WiFi, provisioning, OTA, sampling, display |

---

# Development and Release Workflow

A typical development cycle is:

```text
             ┌─────────────────┐
             │ Modify Firmware │
             │ or WordPress    │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │ Static Checks   │
             │ PHP / Python    │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │ Functional Test │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │ Field Testing   │
             │ Base + Remote   │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │ Build Release   │
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │ SHA256 Checksums│
             └────────┬────────┘
                      │
                      ▼
             ┌─────────────────┐
             │ Deploy / OTA    │
             └─────────────────┘
```

The release script is:

```text
scripts/build_release_artifacts.sh
```

A normal build validates PHP syntax, validates repository structure, packages both WordPress plugins, packages MicroPython, and generates SHA256 checksums.

---

# Testing

TMON testing spans firmware, WordPress, communications, and end-to-end operation.

## Firmware

- Boot sequence
- Provisioning
- WiFi
- LoRa initialization
- Base sessions
- Remote sessions
- Deep sleep
- Sensor sampling
- Field-data persistence
- Command processing
- Settings application
- OLED operation
- Diagnostics
- OTA
- Exception recovery

## WordPress

- Plugin activation
- Database creation/migration
- REST APIs
- Authorization
- Nonces
- Capability checks
- Provisioning
- Device management
- Field-data ingestion
- Commands
- Settings
- Claims
- OTA jobs

## End-to-End

```text
Remote Sensor
     │
     ▼
LoRa
     │
     ▼
Base
     │
     ▼
WiFi
     │
     ▼
Unit Connector
     │
     ▼
TMON Admin
     │
     ▼
Dashboard / Management
```

---

# Troubleshooting

When troubleshooting TMON, work from the bottom of the communication stack upward.

## 1. Hardware

Check:

- Device power
- SX1262 wiring
- SPI pins
- IRQ/RST/BUSY pins
- Sensor wiring
- I2C addresses
- Relay wiring
- OLED wiring

## 2. Firmware Boot

Check:

```text
Firmware version
MACHINE_ID
UNIT_ID
NODE_TYPE
Provisioned state
```

## 3. WiFi

For base/WiFi devices:

```text
WiFi association
IP address
DNS
HTTPS/TLS
WordPress URL
credentials
```

## 4. LoRa

For base/remote devices:

```text
Frequency
Bandwidth
Spreading Factor
Coding Rate
Sync Word
CRC
CAD
TX power
antenna
radio state
```

Then inspect:

```text
/logs/lora.log
/logs/lora_errors.log
```

## 5. Provisioning

Inspect:

```text
/logs/provisioning.log
```

Verify:

```text
MACHINE_ID
UNIT_ID
NODE_TYPE
TMON_ADMIN_API_URL
WORDPRESS_API_URL
provisioned.flag
```

## 6. Telemetry

Verify:

```text
/logs/field_data.log
/logs/data_history.log
```

Then trace:

```text
Device
  ↓
LoRa or HTTP
  ↓
Unit Connector
  ↓
Normalization
  ↓
TMON Admin
  ↓
Dashboard
```

## 7. Commands

Check:

```text
command queued
      ↓
device polls
      ↓
command validated
      ↓
command executes
      ↓
completion acknowledged
```

## 8. OTA

Verify:

```text
version
manifest
download
SHA256
allowlist
staging
apply
reboot
version acknowledgement
```

---

# Documentation Map

The root README explains **what TMON is and how its components fit together**.

Use the following documents for implementation-specific work:

| Document | Use |
|---|---|
| `README.md` | Overall architecture and platform guide |
| `micropython/README.md` | Firmware architecture and configuration |
| `COMMANDS.md` | Device commands and staged settings |
| `tmon-admin/README.md` | Central Admin plugin |
| `unit-connector/README.md` | Unit Connector integration |
| `TESTING_AND_DEPLOYMENT.md` | QA and deployment procedures |
| `DEPLOYMENT_READY.md` | Deployment readiness/history |
| `CHANGELOG.md` | Version/change history |
| `TODO.md` | Outstanding work |
| `CONTEXT_RESTORE.md` | Development context/recovery |
| `IMPLEMENTATION_COMPLETE.md` | Implementation records |
| `AGENT_INSTRUCTIONS.md` | Repository development instructions |

---

# Current Repository Status

The repository contains:

- MicroPython device firmware
- Base, remote, and WiFi device roles
- SX1262 LoRa networking
- Remote deep-sleep support
- Sensor sampling
- Relay control
- OLED status display
- WiFi/HTTPS backhaul
- WordPress REST integration
- TMON Admin provisioning
- Unit Connector telemetry ingestion
- Device commands
- Staged settings
- Device claims
- Hierarchical organization
- Diagnostics
- Audit logging
- OTA update infrastructure
- Release packaging
- Validation/testing scripts
- CI/release workflow support

The checked-in firmware version is defined by:

```text
micropython/version.txt
```

The README should be updated when major architecture or workflow changes are introduced, while detailed implementation information should remain in the component-specific documentation.

---

# License

See the repository's `LICENSE` file for the complete license terms.
