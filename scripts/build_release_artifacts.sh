#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

TAG="${1:-}"
if [[ -z "$TAG" ]]; then
  if command -v git >/dev/null 2>&1; then
    SHORT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo nogit)"
  else
    SHORT_SHA="nogit"
  fi
  TAG="$(date +%Y%m%d)-${SHORT_SHA}"
fi

DIST_DIR="$ROOT_DIR/dist/$TAG"
STAGE_DIR="$ROOT_DIR/.dist-stage/$TAG"

rm -rf "$DIST_DIR" "$STAGE_DIR"
mkdir -p "$DIST_DIR" "$STAGE_DIR"

cleanup() {
  rm -rf "$STAGE_DIR"
}
trap cleanup EXIT

printf '== Preflight ==\n'
php -l unit-connector/tmon-unit-connector.php >/dev/null
php -l tmon-admin/tmon-admin.php >/dev/null
php -l unit-connector/includes/shortcodes.php >/dev/null
php -l unit-connector/templates/device-data.php >/dev/null
php -l tmon-admin/includes/api.php >/dev/null
scripts/validate_uc_field_testing_readiness.sh

copy_tree() {
  local src="$1"
  local dst="$2"
  mkdir -p "$dst"
  rsync -a \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '.pytest_cache' \
    --exclude '.DS_Store' \
    --exclude 'node_modules' \
    --exclude '*.pyc' \
    --exclude '*.pyo' \
    --exclude '*.log' \
    "$src/" "$dst/"
}

printf '\n== Packaging plugins ==\n'
copy_tree "$ROOT_DIR/unit-connector" "$STAGE_DIR/unit-connector"
copy_tree "$ROOT_DIR/tmon-admin" "$STAGE_DIR/tmon-admin"

(
  cd "$STAGE_DIR"
  zip -rq "$DIST_DIR/unit-connector-$TAG.zip" unit-connector
  zip -rq "$DIST_DIR/tmon-admin-$TAG.zip" tmon-admin
)

printf '\n== Packaging firmware ==\n'
copy_tree "$ROOT_DIR/micropython" "$STAGE_DIR/micropython"
(
  cd "$STAGE_DIR"
  zip -rq "$DIST_DIR/micropython-$TAG.zip" micropython
)

printf '\n== Checksums ==\n'
(
  cd "$DIST_DIR"
  sha256sum ./*.zip > SHA256SUMS.txt
)

printf '\nArtifacts created in: %s\n' "$DIST_DIR"
ls -1 "$DIST_DIR"
