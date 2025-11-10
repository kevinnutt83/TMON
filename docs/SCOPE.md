# TMON Project Scope

## Vision
Provide a resilient, modular platform for distributed environmental monitoring where low-power remote nodes transmit sensor and relay state to a coordinating base, enabling centralized analytics, control, and automation through standard web technologies.

## Core Goals (Phase 1–2)
- Reliable sensor sampling & reporting (temperature, humidity, pressure initially).
- Deterministic LoRa scheduling managed by the base station.
- Initial provisioning via Wi-Fi with persistent `UNIT_ID` + `MACHINE_ID`.
- OLED status pages for live operational feedback.
- Batched, memory-aware field data delivery via WordPress REST.
- Flag-based suspension & basic error telemetry.

## Extended Goals (Phase 3+)
- Secure LoRa network credential enforcement.
- Staged remote settings application with validation and rollback.
- OTA firmware delivery with backup & signature verification.
- Command queue with ACK/retry semantics.
- Relay runtime safety enforcement & audit trail.
- GPS augmentation (remote position fix propagation, override policies).
- Advanced environmental sensors (VOC, Lux, motion) gated by feature flags.

## Non-Goals (Current Planning)
- Real-time streaming (focus is periodic batch uplink).
- Proprietary closed protocols (favor open REST + documented payloads).
- Heavy on-device ML (light heuristic/error handling only for now).
- Cloud vendor lock-in (WordPress-based ingestion/admin, portable).

## Constraints
- MicroPython memory limitations: emphasize batching, minimal allocations.
- Intermittent link quality on LoRa: require retry and sync windows.
- Flash write wear: rotate logs and limit frequent rewrites.

## Key Artifacts
- Firmware (MicroPython): `mircopython/` directory.
- Admin Plugin: `tmon-admin/`.
- Unit Connector Plugin: `unit-connector/`.
- Persistence: flag/text/json files under `/logs/`.

## Phase Breakdown
| Phase | Focus | Completion Criteria |
|-------|-------|--------------------|
| 1 | Foundation | Provisioning, basic sampling, field-data batching, OLED minimal UI, suspension gating. |
| 2 | Visibility & Control | Enhanced OLED, RSSI telemetry, OTA version checks, improved error logging. |
| 3 | Security & Settings | LoRa credentials, staged settings apply, relay safety limits. |
| 4 | OTA & Recovery | Full firmware distribution, backup, hash-verified apply, rollback, watchdog improvements. |
| 5 | Advanced Sensors & GPS | Additional sensor integration and GPS override/broadcast. |
| 6 | Command & Automation | Command queue, scheduled actions, policy evaluation. |

## Success Metrics
- <250KB flash usage for logs (rotated & trimmed).
- <5% packet loss in controlled LoRa test environment under normal conditions.
- Provisioning success >95% on first attempt for new devices.
- Field data delivery success >98% with automatic retry.

## Future Considerations
- Optional encryption layer for LoRa payloads.
- Multi-tenant support in Admin for segmented device ownership.
- NATS or MQTT gateway adapter for external streaming integrations.

---
Document generated November 10, 2025.
