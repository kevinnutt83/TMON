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

# Merge stray wp-content into tmon-admin (non-destructive)
WP_SRC="$ROOT_DIR/wp-content"
WP_DEST="$ROOT_DIR/tmon-admin"
PLUGIN_SRC="$WP_SRC/plugins/tmon-admin"
if [ -d "$PLUGIN_SRC" ]; then
  echo "Merging plugin from $PLUGIN_SRC into $WP_DEST (non-destructive)."
  mkdir -p "$WP_DEST"
  rsync -av --ignore-existing --exclude='.git' "$PLUGIN_SRC"/ "$WP_DEST"/
  echo "Removing duplicate plugin directory: $PLUGIN_SRC"
  rm -rf "$PLUGIN_SRC"
fi
if [ -d "$WP_SRC" ]; then
  echo "Merging from $WP_SRC into $WP_DEST (non-destructive)."
  mkdir -p "$WP_DEST"
  rsync -av --ignore-existing --exclude='.git' "$WP_SRC"/ "$WP_DEST"/
  echo "The following wp-content files would be overwritten if forced (dry-run):"
  rsync -av --dry-run --itemize-changes --exclude='.git' "$WP_SRC"/ "$WP_DEST"/ | grep '^>f' || true
  echo "Removing duplicate wp-content directory: $WP_SRC"
  rm -rf "$WP_SRC"
fi

# If you want to allow forced overwrite, re-run with --ignore-existing removed.
# Remove the duplicate directory after merge
echo "Removing duplicate directory: $DUP"
rm -rf "$DUP"

echo "Merge complete. Canonical micropython dir now contains:"
ls -la "$CANON"
