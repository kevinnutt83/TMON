# Firmware Settings Reference

This document summarizes key variables in `mircopython/settings.py` and their intended usage. Only persist or remotely override a SAFE subset to reduce risk.

## Identity & Provisioning
| Setting | Description |
|---------|-------------|
| `UNIT_ID` | Logical device ID assigned by Admin; persisted to `/logs/unit_id.txt`. |
| `MACHINE_ID` | Hardware unique ID read from chipset; persisted at first boot. |
| `PROVISIONED_FLAG_FILE` | Presence indicates successful first-boot registration. |
| `TMON_ADMIN_API_URL` | Admin hub base URL for provisioning & control. |
| `REMOTE_SETTINGS_STAGED_FILE` | Incoming staged settings JSON awaiting validation. |
| `REMOTE_SETTINGS_APPLIED_FILE` | Snapshot of last applied remote settings. |

## Network & Connectivity
| Setting | Description |
|---------|-------------|
| `WIFI_SSID` / `WIFI_PASS` | Wi-Fi credentials for initial provisioning & base uplink. |
| `WIFI_CONN_RETRIES` | Immediate retry attempts per connection cycle. |
| `WIFI_BACKOFF_S` | Backoff between Wi-Fi connection attempts. |
| `WIFI_SIGNAL_SAMPLE_INTERVAL_S` | RSSI sampling interval for telemetry/OLED. |
| `WIFI_DISABLE_AFTER_PROVISION` | Disable Wi-Fi on remote nodes post provisioning. |
| `ENABLE_WIFI` | Global Wi-Fi enable/disable switch. |
| `ENABLE_LORA` | Enable LoRa radio operations. |
| `ENABLE_OLED` | Enable display tasks and visual feedback. |

## LoRa & Sync
| Setting | Description |
|---------|-------------|
| `nextLoraSync` | Absolute epoch for next remote sync slot. |
| `LORA_SYNC_WINDOW` | Minimum spacing between remote sync slot boundaries. |
| `POWER`, `SF`, `BW`, `CR` | Core LoRa radio PHY parameters (power, spread factor, bandwidth, coding rate). |
| `LORA_NETWORK_NAME` / `LORA_NETWORK_PASSWORD` | Basic handshake credentials for network admission (legacy). |
| `LORA_HMAC_ENABLED` | Enable HMAC signing and verification for LoRa payloads. |
| `LORA_HMAC_SECRET` | Per-device shared secret used to sign frames. |
| `LORA_HMAC_COUNTER_FILE` | Remote counter persistence for monotonic `ctr`. |
| `LORA_REMOTE_COUNTERS_FILE` | Base-side last seen counter table per unit. |
| `LORA_HMAC_REJECT_UNSIGNED` | When true, drop frames missing valid signatures. |
| `LORA_HMAC_REPLAY_PROTECT` | Enforce `ctr` strictly increasing to prevent replay. |
| `REMOTE_CHECKIN_INTERVAL_S` | Default periodic telemetry interval for remotes to base. |

## OTA & Update
| Setting | Description |
|---------|-------------|
| `FIRMWARE_VERSION` | Current firmware version string. |
| `OTA_ENABLED` | Enable periodic version check. |
| `OTA_VERSION_ENDPOINT` | Remote file with latest version identifier. |
| `OTA_PENDING_FILE` | Flag file indicating an update is pending verification/application. |
| `OTA_CHECK_INTERVAL_S` | Interval (seconds) between OTA version checks. |
| `OTA_FIRMWARE_BASE_URL` | Base URL for fetching updated firmware files. |
| `OTA_MANIFEST_URL` | URL to JSON manifest mapping files to SHA-256. |
| `OTA_FILES_ALLOWLIST` | List of files permitted to be updated via OTA. |
| `OTA_HASH_VERIFY` | Verify download hashes against manifest. |
| `OTA_BACKUP_ENABLED` / `OTA_BACKUP_DIR` | Backup current files before apply. |
| `OTA_RESTORE_ON_FAIL` | Restore backups if any apply step fails. |
| `OTA_APPLY_INTERVAL_S` | Background loop cadence to attempt apply when pending. |

## Logging & Telemetry
| Setting | Description |
|---------|-------------|
| `LOG_DIR` | Root directory for firmware logs. |
| `FIELD_DATA_LOG` | Accumulating unsent field data records. |
| `DATA_HISTORY_LOG` | Rotated historical field data. |
| `FIELD_DATA_SEND_INTERVAL` | Interval between batched field data sends. |
| `FIELD_DATA_MAX_BATCH` | Maximum records per POST payload. |
| `ERROR_LOG_FILE` | Error log persistent file. |
| `DEVICE_SUSPENDED` | In-memory suspension flag (persisted via `DEVICE_SUSPENDED_FILE`). |
| `DEVICE_SUSPENDED_FILE` | Flag file that halts active tasks when present. |

## Sensors & Sampling
| Setting | Description |
|---------|-------------|
| `SAMPLE_TEMP`, `SAMPLE_BAR`, `SAMPLE_HUMID` | Enable primary environmental sampling categories. |
| `ENABLE_sensorBME280` | Enable BME280 sensor integration. |
| `SYS_VOLTAGE_PIN` / `SYS_VOLTAGE_MAX` | ADC pin and scaling for system voltage sampling. |
| `SYS_VOLTAGE_SAMPLE_INTERVAL_S` | Interval for voltage telemetry refresh. |

## GPS
| Setting | Description |
|---------|-------------|
| `GPS_ENABLED` | Enable GPS-related data fields. |
| `GPS_SOURCE` | Source: `manual`, `module`, or `network`. |
| `GPS_LAT`, `GPS_LNG` | Manual coordinates or last fix. |
| `GPS_OVERRIDE_ALLOWED` | Permit remote override from Admin or base station. |

## Display (OLED)
| Setting | Description |
|---------|-------------|
| `OLED_UPDATE_INTERVAL_S` | Background update loop interval. |
| `OLED_PAGE_ROTATE_INTERVAL_S` | Interval for page rotation when scrolling enabled. |
| `OLED_SCROLL_ENABLED` | Enable multi-page rotation. |

## Debug Flags
| Setting | Description |
|---------|-------------|
| `DEBUG` | Global debug enable. |
| `DEBUG_TEMP`, `DEBUG_BAR`, `DEBUG_HUMID` | Feature-specific debug categories. |
| `DEBUG_LORA`, `DEBUG_WIFI`, `DEBUG_OTA` | Radio/network/OTA debug toggles. |

## Frost & Heat Watch
| Setting | Description |
|---------|-------------|
| `ENABLE_FROSTWATCH` | Activate frost monitoring thresholds. |
| `FROSTWATCH_ALERT_TEMP` / `ACTION_TEMP` / `STANDDOWN_TEMP` | Temperature thresholds controlling frost states. |
| `ENABLE_HEATWATCH` | Activate heat monitoring thresholds. |
| `HEATWATCH_ALERT_TEMP` / `ACTION_TEMP` / `STANDDOWN_TEMP` | Heat states thresholds. |

## Persistence Strategy
Only persist a conservative subset of settings to avoid bricking devices:
- Identity: `UNIT_ID`, `MACHINE_ID` (already persisted).
- Operational flags: `DEVICE_SUSPENDED`.
- Select telemetry intervals: `FIELD_DATA_SEND_INTERVAL`, `OLED_UPDATE_INTERVAL_S`.
- Wi-Fi creds ONLY after secure provisioning handshake.
- Staged settings file is validated then merged; invalid entries discarded.
- On error, previous snapshot (`remote_settings.prev.json`) is restored automatically.

## Applying Staged Settings (Planned)
1. Detect `REMOTE_SETTINGS_STAGED_FILE` presence.
2. Load JSON; validate keys against an allowlist.
3. Write applied snapshot to `REMOTE_SETTINGS_APPLIED_FILE`.
4. Remove staged file; set banner / log success.
5. Optionally soft-reset if critical radio params changed.

---
Generated November 10, 2025.
