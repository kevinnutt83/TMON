<!--
    TMON Root README
    This document gives a high-level project overview.  For firmware details see micropython/README.md.
-->

# TMON – Environmental Monitoring & Device Management Platform

TMON is an IoT platform for environmental monitoring using MicroPython-powered devices with WordPress-based Admin and Unit Connector backends.

## Highlights

- **MicroPython Firmware** (`micropython/`) — ESP32/RP2040 firmware supporting LoRa mesh, WiFi, sensor sampling, relay control, OLED display, and OTA updates.
- **WordPress Plugins** — Admin (`tmon-admin/`) for device provisioning and fleet management; Unit Connector (`unit-connector/`) for field data ingestion and command dispatch.
- **Current Version**: Firmware v2.06.x

## Table of Contents
1. [Architecture](#architecture)
2. [Components](#components)
3. [Data Flow](#data-flow)
4. [Device Roles](#device-roles)
5. [Provisioning Lifecycle](#provisioning-lifecycle)
6. [Quick Start](#quick-start)
7. [Development Layout](#development-layout)
8. [Telemetry & Logs](#telemetry--logs)
9. [Security & Integrity](#security--integrity)
10. [Documentation](#documentation)
11. [License](#license)

## Architecture

```
┌─────────────┐     LoRa SX1262      ┌──────────────┐
│   Remote    │◄────────────────────►│     Base     │
│   Device    │                      │   Station    │
│  (sensors)  │                      │ (WiFi+LoRa)  │
└─────────────┘                      └──────┬───────┘
                                            │ WiFi/HTTPS
                                            ▼
                                   ┌────────────────┐
                                   │ Unit Connector │
                                   │  (WordPress)   │
                                   └────────┬───────┘
                                            │ REST API
                                            ▼
                                   ┌────────────────┐
                                   │   TMON Admin   │
                                   │  (WordPress)   │
                                   └────────────────┘
```

## Components

| Layer | Purpose |
|-------|---------|
| **Firmware** (`micropython/`) | Sensor sampling, LoRa mesh networking, WiFi provisioning, OLED display, relay control, OTA updates, field data persistence. |
| **Unit Connector Plugin** | Accepts device field data, normalizes telemetry, stages commands, forwards data to Admin. |
| **TMON Admin Plugin** | Device registration, provisioning, settings distribution, fleet dashboards, audit logging, OTA coordination. |

## Data Flow

1. **Remote nodes** collect sensor readings and transmit to the base station during scheduled LoRa sync windows.
2. **Base station** aggregates local and remote telemetry, uploads batched field data to Unit Connector via WiFi.
3. **Unit Connector** stores telemetry, exposes REST endpoints for commands and staged settings.
4. **TMON Admin** manages device provisioning, firmware updates, and fleet-wide configuration.

## Device Roles

| Role | Network | Description |
|------|---------|-------------|
| `base` | WiFi + LoRa | Hosts LoRa network, backhauling remote data to cloud |
| `wifi` | WiFi only | Direct cloud connectivity, no LoRa |
| `remote` | LoRa only | Battery-optimized, syncs with base station |

## Provisioning Lifecycle

1. **First Boot**: Device enables WiFi and posts `machine_id` to TMON Admin hub.
2. **Admin Assignment**: Admin assigns `unit_id`, site URL, role, and optional staged settings.
3. **Device Applies**: Device persists configuration, writes provisioned flag.
4. **Role Behavior**: Remote nodes disable WiFi; base/wifi nodes maintain connectivity.
5. **Ongoing Sync**: Devices periodically check in, fetch staged settings, poll commands.

## Quick Start

### Firmware Setup
1. Flash MicroPython to your ESP32/RP2040.
2. Upload firmware files from `micropython/`.
3. Configure `settings.py` with WiFi credentials and server URLs.
4. Power on; device auto-registers with TMON Admin.

### WordPress Setup
1. Install TMON Admin plugin on the admin WordPress site.
2. Install Unit Connector plugin on customer site(s).
3. Configure shared keys and API URLs.
4. Register devices via Admin dashboard.

See `micropython/README.md` for detailed firmware documentation.

## Development Layout

```
TMON/
├── micropython/           # Device firmware
│   ├── main.py           # Main event loop
│   ├── settings.py       # Configuration
│   ├── lora.py           # LoRa driver
│   ├── wifi.py           # WiFi management
│   ├── wprest.py         # WordPress REST client
│   ├── oled.py           # Display driver
│   ├── sampling.py       # Sensor sampling
│   ├── relay.py          # Relay control
│   ├── ota.py            # OTA updates
│   ├── lib/              # Third-party libraries
│   └── README.md         # Firmware documentation
├── tmon-admin/            # Admin WordPress plugin
├── unit-connector/        # Unit Connector WordPress plugin
├── TODO.md               # Outstanding tasks
├── CHANGELOG.md          # Version history
└── README.md             # This file
```

## Telemetry & Logs

### Device Telemetry (sdata)
- Temperature (°F/°C), humidity (%), barometric pressure
- System voltage, free memory, CPU temperature
- WiFi/LoRa signal strength (RSSI, SNR)
- Relay states and runtime counters
- GPS coordinates (when enabled)
- Error counts and last error

### Device Logs
- `/logs/field_data.log` — Pending telemetry
- `/logs/lora.log` — LoRa activity
- `/logs/lora_errors.log` — Error log
- `/logs/provisioning.log` — Provisioning events

## Security & Integrity

- **Authentication**: WordPress Application Passwords for REST API
- **LoRa Security**: Optional HMAC signatures and ChaCha20 encryption
- **OTA Integrity**: SHA256 hash verification, manifest signatures
- **Replay Protection**: Monotonic counters for LoRa frames

## Documentation

- **Firmware**: `micropython/README.md`
- **Changelog**: `CHANGELOG.md`
- **Tasks**: `TODO.md`

## License

See repository for license information.
