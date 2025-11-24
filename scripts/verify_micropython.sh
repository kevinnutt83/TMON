#!/usr/bin/env bash
# List and verify the canonical micropython dir contents
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CANON="$ROOT_DIR/micropython"

if [ ! -d "$CANON" ]; then
  echo "Canonical micropython directory not found: $CANON"
  exit 1
fi

echo "Contents of $CANON:"
ls -la "$CANON"
echo
echo "Python scripts and sizes:"
find "$CANON" -maxdepth 1 -type f -name '*.py' -print -exec stat -c '%n %s bytes' {} \;
