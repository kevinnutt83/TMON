#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v node >/dev/null 2>&1; then
  echo "[FAIL] Node.js is required to run Playwright smoke tests." >&2
  exit 2
fi

if [[ -z "${TMON_UC_ADMIN_URL:-}" || -z "${TMON_UC_ADMIN_USER:-}" || -z "${TMON_UC_ADMIN_PASS:-}" ]]; then
  echo "[FAIL] Set TMON_UC_ADMIN_URL, TMON_UC_ADMIN_USER, and TMON_UC_ADMIN_PASS before running." >&2
  exit 2
fi

exec node scripts/uc_admin_smoke_playwright.mjs
