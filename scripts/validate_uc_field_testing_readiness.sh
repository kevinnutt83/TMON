#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

pass() { printf '[PASS] %s\n' "$1"; }
fail() { printf '[FAIL] %s\n' "$1"; }

status=0

check_contains() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if grep -qE "$pattern" "$file"; then
    pass "$label"
  else
    fail "$label"
    status=1
  fi
}

check_not_contains() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if grep -qE "$pattern" "$file"; then
    fail "$label"
    status=1
  else
    pass "$label"
  fi
}

check_contains_literal() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if grep -qF "$pattern" "$file"; then
    pass "$label"
  else
    fail "$label"
    status=1
  fi
}

printf '== PHP syntax checks ==\n'
php -l unit-connector/admin/menu.php >/dev/null && pass 'admin/menu.php syntax'
php -l unit-connector/admin/device-data.php >/dev/null && pass 'admin/device-data.php syntax'
php -l unit-connector/includes/shortcodes.php >/dev/null && pass 'includes/shortcodes.php syntax'
php -l unit-connector/templates/device-data.php >/dev/null && pass 'templates/device-data.php syntax'
php -l unit-connector/templates/settings.php >/dev/null && pass 'templates/settings.php syntax'

printf '\n== Canonical UI path checks ==\n'
check_contains unit-connector/admin/menu.php "include __DIR__ \. '/\.\./templates/device-data\.php';" "Device Data menu uses template path"
check_not_contains unit-connector/admin/menu.php "tmon_uc_device_data_page\(" "Device Data menu does not bypass template"
check_not_contains unit-connector/admin/device-data.php "tmon_uc_register_device_data_menu|add_submenu_page\(" "No duplicate Device Data submenu registration in admin/device-data.php"

printf '\n== Selector + staging contract checks ==\n'
check_contains unit-connector/templates/device-data.php "id=\"tmon-unit-picker\"" "Top-level unit picker present"
check_contains unit-connector/templates/device-data.php "settings_json" "Template stages settings with settings_json"
check_contains unit-connector/templates/device-data.php "body\.append\('nonce'" "Template stages settings with nonce"
check_contains unit-connector/admin/device-data.php "check_ajax_referer\('tmon_uc_device_data', 'nonce'\)" "Stage handler validates expected nonce field"
check_contains_literal unit-connector/admin/device-data.php "isset(\$_POST['settings_json'])" "Stage handler reads settings_json"

printf '\n== Shortcode compatibility checks ==\n'
check_contains unit-connector/includes/shortcodes.php "id=\"tmon_ds_unit\"" "Shortcode local picker exists"
check_contains unit-connector/includes/shortcodes.php "activeSelect = external \|\| local" "Shortcode supports external or local picker"
check_contains unit-connector/includes/shortcodes.php "add_shortcode\('tmon_frost_heat_watch'" "Frost/heat watch shortcode is registered"
check_contains unit-connector/includes/shortcodes.php "lowest_temp_f|highest_temp_f|lowest_bar|highest_bar|lowest_humid|highest_humid" "Frost/heat watch shortcode references required min/max fields"

printf '\n== History chart checks ==\n'
check_contains unit-connector/includes/shortcodes.php "Lowest Temp \(F\)|Highest Temp \(F\)|Lowest Pressure \(hPa\)|Highest Pressure \(hPa\)|Lowest Humidity \(%\)|Highest Humidity \(%\)" "History chart includes low/high traces in datasets"
check_contains unit-connector/includes/shortcodes.php "document\.cookie|setCookie\(|getCookie\(" "History legend persistence includes cookie support"
check_contains unit-connector/includes/shortcodes.php "collectLegendState\(|saveLegendState\(ci\)|saveLegendState\(chart\)" "History legend persistence saves actual chart visibility"

update_count=$(grep -c "wp_ajax_tmon_uc_update_unit_name" unit-connector/includes/shortcodes.php || true)
if [[ "$update_count" == "1" ]]; then
  pass "Single tmon_uc_update_unit_name AJAX handler"
else
  fail "Expected 1 tmon_uc_update_unit_name handler, found $update_count"
  status=1
fi

printf '\n== Settings page dedupe checks ==\n'
check_contains unit-connector/templates/settings.php "Open Device Data" "Settings page links to Device Data"
check_not_contains unit-connector/templates/settings.php "name=\"RAW_SETTINGS_JSON\"|name=\"tmon_uc_stage_settings_nonce\"|action=\"tmon_uc_stage_settings\"" "Legacy staged-settings form removed from Settings page"

printf '\n== Asset loading checks ==\n'
check_contains_literal unit-connector/tmon-unit-connector.php "'tmon-hierarchy') !== false" "Hierarchy assets are conditionally loaded by admin hook"

printf '\n== Automation harness checks ==\n'
check_contains scripts/uc_admin_smoke_playwright.mjs "playwright|tmon-device-data|Invalid JSON|tmon_unit_name_input|tmon-settings-applied" "Automated wp-admin smoke harness includes key Device Data checks"
check_contains scripts/run_uc_admin_smoke.sh "TMON_UC_ADMIN_URL|TMON_UC_ADMIN_USER|TMON_UC_ADMIN_PASS" "Smoke harness runner enforces required environment variables"

printf '\n== Result ==\n'
if [[ $status -eq 0 ]]; then
  pass "Unit Connector field-testing readiness validation passed"
else
  fail "Unit Connector field-testing readiness validation failed"
fi

exit $status
