# TMON Security Overview

## Objectives
Protect provisioning, command, and telemetry flows across constrained MicroPython firmware and WordPress ingestion while enabling incremental hardening (HMAC for LoRa, hash-verified OTA, relay safety enforcement).

## Secrets & Identity
| Item | Location | Purpose | Rotation Strategy |
|------|----------|---------|-------------------|
| `WORDPRESS_USERNAME` / `WORDPRESS_PASSWORD` | `settings.py` | JWT token acquisition (temporary) | Migrate to application passwords / short-lived tokens; rotate quarterly |
| `LORA_NETWORK_PASSWORD` | `settings.py` | Basic LoRa admission (legacy) | Replace with HMAC secret; rotate via staged settings |
| `LORA_HMAC_SECRET` | `settings.py` | Payload integrity and replay protection | Issue unique per device at provisioning; rotate annually or on compromise |
| Device Counter (`lora_ctr.json`) | `/logs/` | Monotonic counter for LoRa HMAC | Reset only on secret rotation (with base reset of remote_ctr.json) |
| JWT Token | RAM | Auth to Unit Connector endpoints | Short-lived (<24h) refresh; never persisted to disk |

## LoRa HMAC & Replay Protection
When `LORA_HMAC_ENABLED=True`:
1. Remote includes `ctr` and `sig` (SHA-256(secret|unit_id|ts|ctr)) truncated to 32 hex chars.
2. Base validates signature and ensures `ctr` > last seen (stored in `remote_ctr.json`).
3. If `LORA_HMAC_REJECT_UNSIGNED=True`, frames lacking valid signature are ignored.

Recommended: Unique `LORA_HMAC_SECRET` per device (not shared across fleet) to reduce blast radius.

## OTA Integrity
Phase 2 OTA flow downloads only files listed in `OTA_FILES_ALLOWLIST` and verifies SHA-256 hashes from `manifest.json` when `OTA_HASH_VERIFY=True`.
Backups stored under `OTA_BACKUP_DIR`; restore attempted if any hash/apply step fails and `OTA_RESTORE_ON_FAIL=True`.

Hardening roadmap:
- Add manifest signature (HMAC or Ed25519) stored in repo and verified on device.
- Enforce version monotonicity to prevent downgrade attacks.

## Settings Apply & Rollback
Staged settings validated against allowlist; previous snapshot saved to `remote_settings.prev.json` prior to apply. On failure, rollback restores previous values.

## Relay Safety
`RELAY_RUNTIME_LIMITS` and `RELAY_SAFETY_MAX_RUNTIME_MIN` cap activations. Runtime counters (`relayN_runtime_s`) tracked and included in telemetry (future field data enrichment) for audit.

## Data Minimization
Telemetry is curated; removal of bulk dumps reduces exposure of sensitive config. GPS overrides controlled by `GPS_OVERRIDE_ALLOWED`.

## Future Enhancements
- Field data HMAC signing with canonical payload string (implemented; enable via FIELD_DATA_HMAC_ENABLED).
- Encrypted LoRa payloads with ChaCha20 stream cipher (implemented; enable via LORA_ENCRYPT_ENABLED). Consider migrating to AEAD (ChaCha20-Poly1305) for authentication.
- Secure element / hardware unique key derivation for HMAC secret storage.
- Secure erase routine on device decommission.

## Incident Response
1. Compromise suspected (e.g., unexpected relay activations): Suspend device (`DEVICE_SUSPENDED` via settings) to halt tasks.
2. Rotate `LORA_HMAC_SECRET` and `FIELD_DATA_HMAC_SECRET`; reset LoRa counter files.
3. Force OTA of hardened firmware (manifest with new hashes).
4. Review logs in `lora.log` / `lora_errors.log` for anomalous frames.

---
Document generated: 2025-11-10