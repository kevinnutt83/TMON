#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CANON="$ROOT_DIR/micropython"
DUP="$ROOT_DIR/mircopython"

if [ ! -d "$CANON" ]; then
  echo "Canonical micropython directory not found at $CANON. Creating."
  mkdir -p "$CANON"
fi

if [ ! -d "$DUP" ]; then
  echo "No duplicate 'mircopython' directory found; nothing to do."
  exit 0
fi

echo "Merging contents from $DUP into canonical $CANON (non-destructive)"
rsync -av --ignore-existing --exclude='.git' "$DUP"/ "$CANON"/
echo "Removing duplicate directory: $DUP"
rm -rf "$DUP"
echo "Merge complete. Canonical micropython dir now contains:"
ls -la "$CANON"
exit 0
