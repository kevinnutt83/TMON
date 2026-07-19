# TMON Testing & Deployment Checklist

**Last Updated:** July 18, 2026  
**Status:** Ready for Live Environment Testing  
**Version:** 2.00.1g

---

## Phase 1: Code Validation & Static Analysis

### Firmware (MicroPython)

- [x] **Syntax Validation**
  - All `.py` files parse without errors
  - Import statements resolve to available modules
  - No obvious type mismatches or undefined variables

- [x] **Module Import Checks**
  - `uasyncio` patterns used consistently throughout
  - MicroPython-specific imports (ujson, urequests, utime, ubinascii) wrapped with fallback for host testing
  - No circular import dependencies detected
  - Deferred lazy imports in main.py to avoid stack overflow

- [x] **Async/Await Patterns**
  - All blocking I/O replaced with async equivalents
  - Synchronous print() calls in boot/main/provision replaced with `provisioning_log()`
  - Task scheduler protects against duplicate task registration
  - Yielding (`await asyncio.sleep(...)`) present in long-running loops

- [x] **Error Handling**
  - Exception logging centralized via `log_exception()` in utils.py
  - All REST calls have try/except with diagnostics reporting
  - OLED output non-blocking and bounded (routed through `queue_oled_status()`)
  - Sensor read failures have retry logic with exponential backoff

### WordPress Plugins

- [x] **Static Analysis**
  - No obvious PHP syntax errors (warnings are expected WordPress global function warnings in non-WP environment)
  - All nonce checks present in form handlers
  - Database queries use wpdb prepared statements
  - Capability checks on all admin actions

- [x] **REST Endpoint Validation**
  - All routes registered with proper namespace (`/wp-json/tmon/v1/...`)
  - Authentication/authorization checks in place
  - Response formats consistent (JSON with `success`, `data`, `message` fields)
  - Error responses include HTTP status codes

---

## Phase 2: Functionality & End-to-End Testing

### Firmware Boot Sequence

**Test Steps:**
1. [ ] Device powers on, OLED displays "Firmware: X.XX.X" and "Booting TMON Device"
2. [ ] Device loads persisted UNIT_ID, UNIT_Name, NODE_TYPE from flash
3. [ ] WiFi connection (if enabled and not provisioned)
4. [ ] Provisioning check from Admin (if not yet provisioned)
5. [ ] MACHINE_ID generated on first boot and persisted
6. [ ] No hang or restart loop

**Expected Logs:**
- `[BOOT] Loaded persisted UNIT_ID: ...`
- `[BOOT] Loaded persisted UNIT_NAME: ...`
- `[INFO] Booting TMON Device`

### WiFi Device (wifi NODE_TYPE)

**Test Steps:**
1. [ ] Connects to WiFi SSID specified in settings
2. [ ] Fetches initial settings from Admin
3. [ ] Registers with Unit Connector
4. [ ] Enters normal sampling → field data upload → command poll cycle
5. [ ] No LoRa tasks started (LoRa disabled for WiFi nodes)

**Expected Behavior:**
- Field data uploads every FIELD_DATA_UPLOAD_INTERVAL_S (default 60s)
- Commands polled every COMMANDS_POLL_INTERVAL_S (default 30s)
- Diagnostics sent every DIAGNOSTICS_INTERVAL_S (default 300s)

### Base Node (base NODE_TYPE)

**Test Steps:**
1. [ ] Connects to WiFi (if ENABLE_WIFI=True)
2. [ ] Initializes LoRa radio
3. [ ] Accepts remote node registrations
4. [ ] Relays remote data to WordPress via HTTP
5. [ ] Processes commands from WordPress and relays to remotes via LoRa

**Expected Behavior:**
- LoRa radio initialized within 5 seconds
- ACK sent to remotes within 500ms
- HTTP endpoints respond with 200 OK

### Remote Node (remote NODE_TYPE)

**Test Steps:**
1. [ ] Disables WiFi (if configured)
2. [ ] Initializes LoRa radio
3. [ ] Registers with base node (within 30s of boot)
4. [ ] Sends field data to base on sync interval
5. [ ] Receives firmware/settings/commands via base station

**Expected Behavior:**
- Base registration succeeds
- Field data transmitted with CRC/HMAC integrity
- Replay protection prevents duplicate messages

### Sampling & Telemetry

**Test Steps:**
1. [ ] BME280 (interior sensor) sampled every SAMPLE_INTERVAL_S
2. [ ] BME280 Probe (exterior sensor) sampled if present
3. [ ] Soil moisture sensor sampled if enabled
4. [ ] Engine relay status captured
5. [ ] Frost/heat watch computed from temperatures

**Expected Behavior:**
- Sensor reads logged with timestamp
- Failed reads retry 3 times before giving up
- Field data record includes: temp, humidity, pressure, soil, relay states, CPU temp
- No sensor read can block the event loop for >100ms

### OLED Display

**Test Steps:**
1. [ ] Header shows time, WiFi/LoRa status, voltage
2. [ ] Multi-page display cycles through: Summary, Runtime, Network, LoRa Diag, Health pages
3. [ ] Status banner appears for INFO/WARN/ERROR messages (non-blocking)
4. [ ] Page marker dots shown at bottom
5. [ ] Display times out after inactivity (DEBUG_DISPLAY=False)

**Expected Behavior:**
- Pages flip every `OLED_PAGE_FLIP_S` seconds
- Banners persist for configured duration, then clear
- OLED update loop doesn't block async tasks

### Observability & Exception Paths

**Test Steps:**
1. [ ] Trigger controlled failures for WiFi scan/connect, OTA pending-file read, and provisioning endpoint fallback.
2. [ ] Verify `sdata.error_count` increments and `sdata.last_error` updates with context-rich messages.
3. [ ] Confirm diagnostics payload includes system health, LoRa health, and transmission stats after error events.
4. [ ] Validate OLED Health/LoRa Diag pages reflect degraded states (missed syncs, RSSI/SNR, error metadata).
5. [ ] Confirm command/settings loops continue operating after recoverable exceptions.

**Expected Behavior:**
- Recoverable exceptions are captured via structured logging paths (async `log_exception` or sync `record_exception`).
- No silent task death in WiFi, settings-apply, OTA apply loop, provisioning helpers, relay runtime tracking, or user CLI polling.
- Device remains responsive and resumes normal loop cadence after transient failures.

### OTA Firmware Update

**Test Steps:**
1. [ ] Admin queues new firmware version
2. [ ] Device polls for OTA job
3. [ ] Manifest parsed correctly
4. [ ] Firmware downloaded to backup dir with CRC validation
5. [ ] File integrity verified before flash write
6. [ ] Device restarts with new firmware
7. [ ] Version acknowledged back to Admin

**Expected Behavior:**
- Download completes within timeout window (30 minutes)
- File writes are atomic (not corrupted on power loss)
- Fallback to previous version on checksum mismatch
- OTA status reported with timestamp

### Command Execution

**Test Steps:**
1. [ ] Admin sends `set_var` command to change a setting
2. [ ] Device polls for command
3. [ ] Command validated and executed
4. [ ] Result reported back to Admin within 5 seconds
5. [ ] Unsupported commands acknowledged as such

**Expected Behavior:**
- Settings persisted after `set_var`
- Command not re-delivered after acknowledged
- Failed commands logged with error message
- Device continues normal operation after command

### WordPress Admin UI

**Test Steps:**
1. [ ] Login to WordPress as admin
2. [ ] Navigate to TMON Admin → Dashboard (live stats)
3. [ ] Navigate to TMON Admin → Provisioning (form loads)
4. [ ] Fill in device details, click "Save & Provision"
5. [ ] Check Provisioning Activity page (shows queued item)
6. [ ] Navigate to Provisioned Devices → shows new device
7. [ ] Check Diagnostics → shows device health metrics

**Expected Behavior:**
- No PHP errors or warnings
- Nonces validate on form submission
- Database inserts succeed
- Pages load within 3 seconds
- Admin notices display status messages

### Unit Connector Integration

**Test Steps:**
1. [ ] UC paired with Admin hub (check-in endpoint)
2. [ ] Field data received from device → UC processes → stored
3. [ ] UC forwards to Admin for aggregation
4. [ ] Device data appears in UC Dashboard
5. [ ] Relay controls clickable and respond

**Expected Behavior:**
- UC check-in returns 200 OK with Hub config
- Field data POST accepted and queued
- Devices appear in Device list within 30 seconds
- Relay command succeeds within 2 seconds

---

## Phase 3: Security Review

- [x] **Credentials & API Keys**
  - No hard-coded passwords in source
  - Admin API URL persisted securely on device
  - UC-to-Admin shared key managed via options table
  - Device MACHINE_ID used for identity verification

- [x] **Input Validation**
  - All HTML form inputs sanitized (sanitize_text_field, esc_url_raw)
  - SQL queries use wpdb prepared statements
  - REST endpoints validate required parameters

- [x] **Replay Protection**
  - LoRa messages include CNT (counter) for replay detection
  - HMAC verifies message authenticity
  - CRC-16 validates transmission integrity
  - Firmware files verified with SHA256 checksum

- [x] **Async Blocking Mitigation**
  - No synchronous HTTP requests in event loop
  - Heavy I/O operations yield to event loop
  - Long loops have cooperative sleep points
  - No busy-wait loops

---

## Phase 4: Live Environment Deployment Steps

### Pre-Deployment

1. [ ] **Backup Data**
   - Export current tmon_devices table
   - Export current tmon_field_data_logs
   - Archive current WordPress uploads directory

2. [ ] **DNS & Certificates**
   - Verify tmonsystems.com SSL certificate valid
   - Check DNS resolution (A record)
   - Test HTTPS connectivity

3. [ ] **Database**
   - Run Admin migrate/sync script
   - Verify tmon_provisioned_devices table exists
   - Check indexes are created

### WordPress Plugin Deployment

1. [ ] **Backup Current**
   ```bash
   cd /var/www/html/wp-content/plugins
   cp -r tmon-admin tmon-admin.backup
   cp -r tmon-unit-connector tmon-unit-connector.backup
   ```

2. [ ] **Deploy New**
   ```bash
   # Copy admin plugin
   cp -r TMON/tmon-admin/* /var/www/html/wp-content/plugins/tmon-admin/
   
   # Copy UC plugin  
   cp -r TMON/unit-connector/* /var/www/html/wp-content/plugins/tmon-unit-connector/
   ```

3. [ ] **Activate Plugins**
   - Navigate to WordPress Plugins admin page
   - Activate TMON Admin (if not active)
   - Activate TMON Unit Connector (if not active)

4. [ ] **Verify Installation**
   - Check Admin dashboard loads
   - Check Provisioning page loads
   - Check Provisioned Devices page displays
   - Check Diagnostics page loads

### Firmware Deployment (OTA)

1. [ ] **Prepare Manifest**
   ```json
   {
     "version": "2.00.1g",
     "firmware_url": "https://tmonsystems.com/firmware/tmon-2.00.1g.bin",
     "sha256": "<hash>",
     "changelog": "Support async logging, multi-page OLED, diagnostics"
   }
   ```

2. [ ] **Generate Firmware Binary**
   - Compile MicroPython firmware
   - Generate checksum
   - Upload to server

3. [ ] **Queue OTA Job in Admin**
   - Go to TMON Admin → Firmware
   - Upload manifest
   - Target devices (all, or specific group)
   - Review and queue

4. [ ] **Monitor Device Updates**
   - Check OTA Jobs page
   - Watch device status transitions
   - Verify version acknowledgment logs

---

## Phase 5: Live Environment Testing

### Hour 1: Connectivity & Provisioning

**Smoke Test:**
- [ ] New WiFi device powers on → connects → provisions → uploads data
- [ ] Existing remote device boots → connects to base → syncs data
- [ ] Base station active and accepting remote registrations
- [ ] Admin dashboard shows all device statuses

**Verification:**
```bash
# Check device logs in /logs
curl -s https://tmonsystems.com/wp-json/tmon/v1/device/diagnostics?limit=10

# Check Unit Connector received data
curl -s https://customer-site.com/wp-json/tmon-uc/v1/field-data?limit=10
```

### Hour 2-4: Normal Operation

**Extended Test:**
- [ ] Field data uploads every ~60 seconds
- [ ] No OTA or firmware upgrade in progress
- [ ] Commands execute successfully
- [ ] Admin dashboard updates live
- [ ] No error logs accumulating

**Monitoring:**
```bash
# Watch device check-ins
tail -f /var/www/html/wp-content/uploads/tmon_logs/check-in.log

# Watch provisioning queue
SELECT * FROM wp_tmon_provisioned_devices ORDER BY updated_at DESC;

# Check diagnostics ingest rate
SELECT COUNT(*) as count, MAX(created_at) as latest 
FROM wp_tmon_diagnostics 
GROUP BY device_id;
```

### Hour 4-8: OTA Update Wave

**Update Test (on subset of devices first):**
1. [ ] Queue firmware to 3-5 test devices
2. [ ] Monitor update progress via Admin
3. [ ] Verify devices restart with new firmware version
4. [ ] Confirm field data uploads resume after restart
5. [ ] No device lost or unresponsive

**Verification:**
```bash
# Check firmware version reported
SELECT DISTINCT firmware_version FROM wp_tmon_devices 
ORDER BY created_at DESC;

# Monitor OTA job status
SELECT * FROM wp_tmon_ota_jobs 
WHERE status IN ('queued', 'downloading', 'applying');
```

### Hour 8+: Sustained Operation

**Stability Test:**
- [ ] Run for 24+ hours without manual intervention
- [ ] Monitor error/warning log growth
- [ ] Check database query performance
- [ ] Verify backup/retention policies working

**Key Metrics:**
- Field data ingest rate: 5-100 records/minute (depending on device count)
- Command execution success rate: >99%
- Device connectivity uptime: >98% (accounting for reboots)
- Admin dashboard response time: <1 second
- REST response time (p99): <500ms

---

## Phase 6: Issue Handling & Rollback

### If Issues Detected

1. [ ] **Isolate**
   - Disable OTA jobs (pause in settings)
   - Stop new provisioning if database issue
   - Note exact error message & telemetry

2. [ ] **Investigate**
   - Check error logs
   - Review recent code changes
   - Query database for anomalies

3. [ ] **Communicate**
   - Notify stakeholders via Slack/email
   - Estimate time to resolution
   - Document the issue

### Rollback Procedure

**If Firmware Update Fails:**
```bash
# Device will retry with previous version on manifest fail
# Or manually trigger via command: run_func("boot")
```

**If Plugin Causes Issues:**
1. [ ] Restore from backup
   ```bash
   cp -r tmon-admin.backup/* /var/www/html/wp-content/plugins/tmon-admin/
   ```

2. [ ] Deactivate plugin
   ```bash
   wp plugin deactivate tmon-admin
   ```

3. [ ] Clear WordPress cache
   ```bash
   wp cache flush
   ```

**If Database Corruption:**
1. [ ] Restore from backup
2. [ ] Run schema migration
3. [ ] Re-sync devices

---

## Phase 7: Post-Deployment Maintenance

### Daily

- [ ] Check Admin dashboard for error spikes
- [ ] Monitor device provisioning queue
- [ ] Review error logs for patterns
- [ ] Backup database (automatic)

### Weekly

- [ ] Review OTA update logs
- [ ] Check database size & query performance  
- [ ] Analyze device connectivity patterns
- [ ] Review command execution success rate

### Monthly

- [ ] Archive old logs to cold storage
- [ ] Review security audit logs
- [ ] Check certificate expiration dates
- [ ] Run performance baseline tests

---

## Success Criteria

Deployment is successful when:

- ✅ **Connectivity**: 95%+ devices check in within monitoring interval
- ✅ **Data Ingestion**: Field data received for 90%+ of provisioned devices  
- ✅ **Uptime**: Admin dashboard/REST endpoints up 99.9%
- ✅ **Commands**: 99%+ command execution success rate
- ✅ **OTA**: Firmware updates deploy to 95%+ target devices
- ✅ **Errors**: <0.1% error rate in device logs
- ✅ **Performance**: p95 REST response time <500ms

---

## Rollout Strategy

### Week 1: Test Fleet (5-10 devices)
- External test devices on WiFi
- Monitor 24/7 for stability issues
- Collect baseline metrics

### Week 2: Early Adopter (50-100 devices)
- Mix of WiFi, base, and remote nodes
- Monitor for edge case issues
- Optimize settings based on real telemetry

### Week 3: Full Production
- Roll out to all provisioned devices via OTA
- Gradual rollout (20% per day) to catch issues early
- Monitor all metrics continuously

### Ongoing: Continuous Improvement
- Collect performance telemetry
- Request user feedback
- Schedule future enhancements (see TODO.md)

---

## Contact & Escalation

**Issues During Deployment:**
- [ ] Document issue timestamp and details
- [ ] Check #tmon-support Slack channel
- [ ] Contact on-call engineer (see runbook)

**Post-Deployment Questions:**
- User provisioning guide: docs/PROVISIONING.md
- Admin troubleshooting: docs/ADMIN_GUIDE.md
- Device debugging: docs/FIRMWARE_DEBUG.md

---

**END OF TESTING & DEPLOYMENT CHECKLIST**
