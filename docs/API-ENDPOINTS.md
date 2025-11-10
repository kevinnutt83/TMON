# API Endpoints Reference

This document enumerates REST endpoints used by firmware and WordPress plugins. Paths assume site root; adjust hostnames accordingly.

## Admin Plugin (tmon-admin)
| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/wp-json/tmon-admin/v1/device/check-in` | First-boot provisioning: returns canonical `unit_id` | Admin shared key / capability |
| GET  | `/wp-json/tmon-admin/v1/device/settings/{unit_id}` | Fetch staged settings for a unit | Auth key / nonce |
| POST | `/wp-json/tmon-admin/v1/device/command` | Queue a command for a device | Auth key / capability |
| GET  | `/wp-json/tmon-admin/v1/device/commands/{unit_id}` | Pending command poll | Auth key / nonce |
| POST | `/wp-json/tmon-admin/v1/device/ota/signal` | Register OTA pending / version acceptance | Auth key |

## Unit Connector Plugin (unit-connector)
| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/wp-json/tmon/v1/device/field-data` | Batched field data delivery from base node | JWT Bearer (token issued by plugin) |
| GET  | `/wp-json/tmon/v1/device/status/{unit_id}` | Device latest status snapshot | Public/secured optional |
| POST | `/wp-json/tmon/v1/device/command-complete` | Preferred command completion endpoint | JWT Bearer |
| POST | `/wp-json/tmon/v1/device/ack` | Legacy/simple command acknowledgment (fallback) | JWT Bearer |
| GET  | `/wp-json/tmon/v1/device/history/{unit_id}` | Historical data query (paged) | JWT Bearer / capability |

## Common Payload Shapes

### Provisioning Check-In (Firmware → Admin)
```
POST /wp-json/tmon-admin/v1/device/check-in
{
  "unit_id": "TEMP-CLIENT-ID",   // may be placeholder; Admin can assign canonical
  "machine_id": "abc123ef45",
  "firmware_version": "v2.00j",
  "node_type": "base" | "remote"
}
Response 200:
{
  "unit_id": "A1B2C3",           // canonical assigned
  "status": "ok",
  "provisioned": true
}
```

### Field Data Batch (Base → Unit Connector)
```
POST /wp-json/tmon/v1/device/field-data
Authorization: Bearer <jwt>
{
  "unit_id": "A1B2C3",
  "machine_id": "abc123ef45",
  "data": [
    {
      "timestamp": 1731200000,
      "cur_temp_f": 72.4,
      "cur_humid": 55.2,
      "cur_bar_pres": 1012.6,
      "sys_voltage": 4.87,
      "wifi_rssi": -62,
      "lora_SigStr": -98,
      "error_count": 0,
      "script_runtime": 3600
    },
    {
      "timestamp": 1731200030,
      "cur_temp_f": 72.3,
      "cur_humid": 55.3,
      "cur_bar_pres": 1012.5
    }
  ]
}
Response 200:
{
  "status": "ok",
  "received": 2,
  "unit_id": "A1B2C3"
}
```

### Command Poll (Firmware → Admin / Unit Connector)
```
GET /wp-json/tmon-admin/v1/device/commands/A1B2C3
Response 200:
{
  "status": "ok",
  "commands": [
     { "id": 15, "type": "relay", "relay": 1, "action": "on", "expires": 1731200500 },
     { "id": 16, "type": "suspend", "value": true }
  ]
}
```

### Command Acknowledge (Firmware/Base → Unit Connector)
```
POST /wp-json/tmon/v1/device/command-complete
Authorization: Bearer <jwt>
{
  "job_id": 15,
  "ok": true,
  "result": "executed"
}
Response 200:
{ "status": "ok" }
```

Legacy fallback:
```
POST /wp-json/tmon/v1/device/ack
Authorization: Bearer <jwt>
{
  "command_id": 15,
  "ok": true,
  "result": "executed"
}
Response 200:
{ "status": "ok" }
```

## Error Responses
| Status | Body Example | Meaning |
|--------|--------------|---------|
| 400 | `{ "error": "invalid payload" }` | JSON malformed or required fields missing |
| 401 | `{ "error": "auth failed" }` | Invalid/expired token or missing capability |
| 404 | `{ "error": "not found" }` | Unit ID or command unknown |
| 429 | `{ "error": "rate limit" }` | Excessive requests over threshold |
| 500 | `{ "error": "server error" }` | Unhandled server exception |

## Security Notes
- JWT tokens should be short-lived; refresh flows must avoid storing secrets in firmware plaintext (future secure storage TBD).
- Shared keys between plugins validated server-side; never transmitted by firmware after provisioning.
- Future enhancement: signing field data payloads with HMAC using a device-specific secret issued at provisioning.
- Current enhancement: LoRa frames optionally signed via HMAC (see `LORA_HMAC_ENABLED`).

---
Generated November 10, 2025.
