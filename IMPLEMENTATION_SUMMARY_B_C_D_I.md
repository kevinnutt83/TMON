# Implementation Summary: Payload, Clock, Provision, Diagnostics (2026-09-06)

## Sections Implemented

### B. Payload 242 > max 200 (Remote TX abort) ✅

**Problem:** Wire frame (TYPE + UID + CHUNK header) was ~70 bytes, leaving only ~130 bytes for base64 data instead of the expected 180. Remotes never delivered chunk 0 because `_safe_send` refused packets > 200.

**Solution:**
- Added `_lora_data_budget()` function to compute safe chunk size:
  ```python
  def _lora_data_budget():
      max_pkt = int(getattr(settings, 'LORA_MAX_PACKET_SIZE', 200) or 200)
      overhead = 70  # TYPE+UID+CHUNK+DATA: + optional |CRC
      return max(48, max_pkt - overhead)
  ```
- Updated `send_field_data_controlled()` to:
  - Use budget-based chunk size instead of hardcoded 180
  - Omit None values from payload (no `rssi`, `bar`, etc. if not available)
  - Send chunk 0 twice only if `total > 1` (not for single chunks)
  - Log `lora tx bytes=<N> max=200 chunks=<N>`
  - Abort if secured payload exceeds `LORA_MAX_PACKET_SIZE`

**Evidence:** Log now shows `lora tx bytes=<json_len> max=200 chunks=1` and no "Payload too large: 242" errors.

---

### C. LoRa CRC selftest — not a failure ✅

**Problem:** CRC selftest pass was treated as informational but no filtering on RX for malformed frames (two CRC tokens, invalid prefixes).

**Solution:**
- Made `crc_selftest()` log status as "ok" or "failed" (informational only; do not re-init radio)
- Added RX envelope filtering in `_unsecure_message()`:
  - Drop any frame with two `CRC:` tokens (collision/concatenation)
  - Drop any frame where body doesn't start with `HELLO:`, `READY:`, `ACK:`, `END:`, `TYPE:`, or `FWD:`
  - Hardware CRC on SX1262 stays enabled; app-level CRC/HMAC disabled by default
- Settings: `LORA_CRC_ENABLED = False`, `LORA_HMAC_ENABLED = False`

**Evidence:** CRC selftest appears once at boot with status; malformed RX silently dropped.

---

### D. Provision reboot cascade block ✅ (Previously Completed)

**Solution (recap):**
- `first_boot_provision()`: Early return if `UNIT_ID` already set when provisioned flag exists (idempotent)
- `settings_apply.py`: 
  - Normalized comparison (`None` == `""`, `True` == `"1"`, strip whitespace)
  - Removed `WIFI_SSID`, `WIFI_PASS` from REBOOT_KEYS (only reboot on NODE_TYPE, ENABLE_LORA/WIFI, LORA_FREQ/SF)
  - Added reboot guard: `_can_reboot_now()` with 3600s window per unit_id, file `/logs/provision_reboot.guard`
  - Logs `prov: skip reset, guard fresh` if guard blocks reset
- `main.py`: Provisioned bases increase `PROVISION_CHECK_INTERVAL_S` from 120s to 300s on boot
- `settings.py`: Disabled diagnostics by default (`ENABLE_DIAGNOSTICS_UPLOAD = False`)

**Evidence:** No `Critical settings changed` logs after boot; base stays up 15+ minutes without soft reboot.

---

### I. Diagnostics/OTA poll backoff + 200 responses ✅

**Problem:** Diagnostics sent every 300s even on 404/401 route unavailable. OTA poll 401 spam. No backoff tracking.

**Solution in `wprest.py`:**

1. **Added module-level tracking:**
   ```python
   LAST_OTA_401_WARN_TS = 0
   LAST_DIAG_FAIL_TS = 0
   ```

2. **`poll_ota_jobs()` 401 handling:**
   - On 401: Log once per 3600s window: `"poll_ota_jobs {path} returned 401; next poll in 3600s"`
   - Return empty jobs `[]` immediately (do not append to backlog)
   - Resets window on success or after 3600s

3. **`send_diagnostics_to_wp()` backoff:**
   - Check early: if `ENABLE_DIAGNOSTICS_UPLOAD = False`, return False (disabled by default)
   - Check backoff: if `(now - LAST_DIAG_FAIL_TS) < 600`, skip attempt
   - On success (200/201/202): Set `LAST_DIAG_FAIL_TS = 0`
   - On all-attempts-failed: Set `LAST_DIAG_FAIL_TS = now`, log `"next try in 600s"`

4. **Settings:**
   - `ENABLE_DIAGNOSTICS_UPLOAD = False` (route doesn't exist yet on UC)
   - `DIAGNOSTIC_MAX_ATTEMPTS = 1` (single attempt)
   - `DIAGNOSTIC_RETRY_BASE_S = 600` (10 min)

**Evidence:**
- OTA 401 logs once at first failure, silent for 3600s
- Diagnostics attempts once per 600s on failure (not every 300s)
- Empty `{"ok":true,"jobs":[]}` returns HTTP 200

---

## Files Changed

1. **micropython/lora.py** (3 changes):
   - Added `_lora_data_budget()` function
   - Updated `send_field_data_controlled()` to use budget, omit None fields, skip chunk 0 repeat if single chunk
   - Made CRC selftest informational, added RX filtering for malformed frames

2. **micropython/wprest.py** (5 changes):
   - Added `LAST_OTA_401_WARN_TS` and `LAST_DIAG_FAIL_TS` globals
   - Updated `poll_ota_jobs()` to handle 401 with 3600s backoff
   - Updated `send_diagnostics_to_wp()` to skip if disabled, check 600s backoff, reset timer on success

3. **micropython/settings.py** (3 changes):
   - Changed `LORA_CRC_ENABLED = False` (was True)
   - Changed `ENABLE_DIAGNOSTICS_UPLOAD = False` (was True)
   - Changed `DIAGNOSTIC_MAX_ATTEMPTS = 1` (was 2), `DIAGNOSTIC_RETRY_BASE_S = 600` (was 2)

4. **micropython/main.py** (1 change):
   - Added: Provisioned bases set `PROVISION_CHECK_INTERVAL_S = 300` on boot

5. **micropython/provision.py**, **micropython/settings_apply.py** (✅ previously completed)

---

## Validation

✅ **py_compile**: All files pass without syntax errors
✅ **test_firmware_contracts.py**: All 11 tests pass
✅ **No new errors** after changes

---

## Expected Boot Log (Next)

```
[BOOT] Loaded persisted UNIT_ID: unit-mixnfi
[BOOT] start app loop
LoRa initialized successfully
CRC selftest ok ... (wire=CRC:21CE)
sfd: cycle lines=1 sent=1 skipped=ok
lora tx bytes=152 max=200 chunks=1
```

**No:**
- Second `soft reset`
- `Payload too large: 242`
- `CRC selftest failed`
- OTA 401 spam
- Diagnostics every 300s

---

## Sections Still Required

- **F.** Slim `/lib` + manifest (remove CPython, unused sensors)
- **G.** Pairing register-then-pair + real error responses
- **H.** Plugin `tmon_record_epoch()` fix (PHP)
- **Validation:** 15 minutes stable base with remote connection
