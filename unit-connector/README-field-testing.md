# Unit Connector Field-Testing Checklist

This checklist verifies the Device Data selector, shortcode behavior, and staging flow before hardware/site rollout.

## 1) Pre-flight (code-level)

Run:

```bash
cd /workspaces/TMON
scripts/validate_uc_field_testing_readiness.sh
```

Expected result:
- All checks show `[PASS]`
- Final line: `Unit Connector field-testing readiness validation passed`

## 2) Admin UI runtime smoke (wp-admin)

Open:
- `TMON Devices -> Device Data`

Checks:
1. Unit picker exists at top of page.
2. Selecting a unit updates:
- Applied JSON block
- Staged JSON block
- Machine ID and Last Seen fields
3. `Unit Name` input is editable and `Update name` persists without nonce errors.
4. `Stage & Push` accepts valid JSON and returns success message.
5. Invalid JSON produces `Invalid JSON` message and does not submit.

## 3) Shortcode compatibility checks

### A) On Device Data page (with page-level picker)
1. `[tmon_device_settings]` follows the top-level picker selection.
2. Local shortcode picker is hidden.
3. Boolean settings render as animated On/Off switches.

### B) Standalone shortcode page (no page-level picker)
1. `[tmon_device_settings]` shows its own unit dropdown.
2. Load + Stage controls remain enabled.
3. Stage action succeeds for selected unit.

## 4) Staging contract verification

For a successful stage action, verify in browser Network tab or logs:
- Request includes `unit_id`
- Request includes `settings_json`
- Request includes `nonce`
- Handler action: `tmon_uc_stage_settings`

## 5) Regression checks

1. `TMON Devices -> Settings` no longer contains a duplicate staged-settings form.
2. Settings page links to Device Data as canonical staging workflow.
3. No duplicate Device Data submenu entry appears under unexpected parent slugs.

## 6) Field deployment gate

Proceed to field tests only when:
- Pre-flight script is passing
- Runtime smoke checks pass for at least 2 units
- One staged setting round-trip is confirmed on a real device check-in

## 7) Automated wp-admin smoke harness

The repository includes a Playwright-based smoke harness for Device Data page checks:

Files:
- scripts/uc_admin_smoke_playwright.mjs
- scripts/run_uc_admin_smoke.sh

Environment variables:
- TMON_UC_ADMIN_URL
- TMON_UC_ADMIN_USER
- TMON_UC_ADMIN_PASS
- Optional: TMON_UC_SMOKE_HEADLESS=0 for visible browser run

Run:

```bash
cd /workspaces/TMON
chmod +x scripts/run_uc_admin_smoke.sh
TMON_UC_ADMIN_URL="https://example.com/wp-admin/" \
TMON_UC_ADMIN_USER="admin" \
TMON_UC_ADMIN_PASS="password" \
scripts/run_uc_admin_smoke.sh
```

The harness validates:
- Login + Device Data navigation
- Unit picker presence and data hydration
- Unit Name controls
- Stage action path (valid JSON submit + invalid JSON block)
- Animated bool switch presence in device settings editor
