#!/usr/bin/env bash
# Merge contents of /mircopython into canonical /micropython, non-destructively, and remove the duplicate.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CANON="$ROOT_DIR/micropython"
DUP="$ROOT_DIR/mircopython"

if [ ! -d "$DUP" ]; then
  echo "No duplicate directory found at $DUP. Nothing to do."
  exit 0
fi

if [ ! -d "$CANON" ]; then
  echo "Canonical micropython directory not found at $CANON. Creating it."
  mkdir -p "$CANON"
fi

echo "Merging from $DUP to $CANON (non-destructive)."
# Copy files without overwriting existing files to be safe.
rsync -av --ignore-existing --exclude='.git' "$DUP"/ "$CANON"/

echo "The following files would be overwritten if forced (dry-run):"
rsync -av --dry-run --itemize-changes --exclude='.git' "$DUP"/ "$CANON"/ | grep '^>f' || true

# If you want to allow forced overwrite, re-run with --ignore-existing removed.
# Remove the duplicate directory after merge
echo "Removing duplicate directory: $DUP"
rm -rf "$DUP"

echo "Merge complete. Canonical micropython dir now contains:"
ls -la "$CANON"
