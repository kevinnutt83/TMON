# TMON – Environmental Monitoring System

TMON is a modular, multi-component system for remote environmental monitoring, data aggregation, and device management. It combines MicroPython firmware for sensor nodes with WordPress plugins for data ingestion, device provisioning, and centralized administration.

## Architecture Overview

- **Firmware (MicroPython)**: Located in `tmonCore/mircopython/v1-0-0`. Supports base and remote nodes, LoRa mesh networking, Wi-Fi provisioning, and sensor sampling. Data is relayed to WordPress via REST endpoints.
- **Unit Connector (WordPress Plugin)**: Located in `tmonCore/unit-connector/v1-0-0`. Receives device data, normalizes and stores records, exports CSV/JSON, and forwards to Admin.
- **TMON Admin (WordPress Plugin)**: Located in `tmonCore/tmon-admin/v1-0-0`. Handles device provisioning, claims, hierarchy management, security, and centralized data aggregation.

## Data Flow

1. **Remote nodes** sample sensors and send data to the base via LoRa. The base schedules remotes using absolute epochs.
2. **Base node** (or device) POSTs data to Unit Connector at `/wp-json/tmon/v1/device/field-data`.
3. **Unit Connector** normalizes, stores, and forwards records to Admin for aggregation and authorization.
4. **Admin** provides dashboards, exports, and device management. First-boot provisioning is handled via Wi-Fi POST to `/wp-json/tmon-admin/v1/device/check-in`.

## Quick Start

1. **Firmware**: Flash MicroPython firmware, configure `settings.py` (UNIT_ID, NODE_TYPE, API URLs, Wi-Fi, pins, LoRa params). Power on device; it auto-registers with WordPress.
2. **WordPress Plugins**: Install and activate both Unit Connector and TMON Admin. Configure shared keys (`tmon_uc_admin_key`, `tmon_admin_uc_key`) in plugin settings. Ensure permalinks and REST API are enabled.
3. **Provision Devices**: Use Admin > Provisioning to claim, assign roles, and associate devices. Push configuration to Unit Connector as needed.
4. **Monitor & Export**: Use dashboards and CSV export endpoints for analytics and reporting.

## Key Files & Directories

- Firmware: `main.py`, `settings.py`, `lora.py`, `wprest.py`, `sdata.py`, `/logs/`
- Unit Connector: `tmon-unit-connector.php`, `includes/field-data-api.php`, `includes/api.php`, `includes/settings.php`
- Admin: `tmon-admin.php`, `includes/provisioning.php`, `includes/field-data-api.php`, `includes/api.php`, `templates/`

## Developer Notes

- All source and documentation files are tracked (see `.gitignore` for exclusions).
- No nested git repositories; only one `.git` directory at the root.
- For AI agent instructions, see `.github/copilot-instructions.md`.

## License

Add a license file if you intend to open source this project.
<<<<<<< HEAD
# TMON
TMON is a Python-based environmental monitoring program that relays data back to a WordPress website for viewing. 
=======

# TMON – Environmental Monitoring System

TMON is a modular, multi-component system for remote environmental monitoring, data aggregation, and device management. It combines MicroPython firmware for sensor nodes with WordPress plugins for data ingestion, device provisioning, and centralized administration.

## Architecture Overview

- **Firmware (MicroPython)**: Located in `tmonCore/mircopython/v1-0-0`. Supports base and remote nodes, LoRa mesh networking, Wi-Fi provisioning, and sensor sampling. Data is relayed to WordPress via REST endpoints.
- **Unit Connector (WordPress Plugin)**: Located in `tmonCore/unit-connector/v1-0-0`. Receives device data, normalizes and stores records, exports CSV/JSON, and forwards to Admin.
- **TMON Admin (WordPress Plugin)**: Located in `tmonCore/tmon-admin/v1-0-0`. Handles device provisioning, claims, hierarchy management, security, and centralized data aggregation.

## Data Flow

1. **Remote nodes** sample sensors and send data to the base via LoRa. The base schedules remotes using absolute epochs.
2. **Base node** (or device) POSTs data to Unit Connector at `/wp-json/tmon/v1/device/field-data`.
3. **Unit Connector** normalizes, stores, and forwards records to Admin for aggregation and authorization.
4. **Admin** provides dashboards, exports, and device management. First-boot provisioning is handled via Wi-Fi POST to `/wp-json/tmon-admin/v1/device/check-in`.

## Quick Start

1. **Firmware**: Flash MicroPython firmware, configure `settings.py` (UNIT_ID, NODE_TYPE, API URLs, Wi-Fi, pins, LoRa params). Power on device; it auto-registers with WordPress.
2. **WordPress Plugins**: Install and activate both Unit Connector and TMON Admin. Configure shared keys (`tmon_uc_admin_key`, `tmon_admin_uc_key`) in plugin settings. Ensure permalinks and REST API are enabled.
3. **Provision Devices**: Use Admin > Provisioning to claim, assign roles, and associate devices. Push configuration to Unit Connector as needed.
4. **Monitor & Export**: Use dashboards and CSV export endpoints for analytics and reporting.

## Key Files & Directories

- Firmware: `main.py`, `settings.py`, `lora.py`, `wprest.py`, `sdata.py`, `/logs/`
- Unit Connector: `tmon-unit-connector.php`, `includes/field-data-api.php`, `includes/api.php`, `includes/settings.php`
- Admin: `tmon-admin.php`, `includes/provisioning.php`, `includes/field-data-api.php`, `includes/api.php`, `templates/`

## Developer Notes

- All source and documentation files are tracked (see `.gitignore` for exclusions).
- No nested git repositories; only one `.git` directory at the root.
- For AI agent instructions, see `.github/copilot-instructions.md`.

## License

Add a license file if you intend to open source this project.
>>>>>>> 20b3d01 (Update README.md to enhance project description and structure)
