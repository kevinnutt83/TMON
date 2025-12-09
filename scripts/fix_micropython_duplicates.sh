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

# Also merge stray wp-content into tmon-admin
WP_SRC="$ROOT_DIR/wp-content"
WP_DEST="$ROOT_DIR/tmon-admin"
PLUGIN_SRC="$WP_SRC/plugins/tmon-admin"
if [ -d "$PLUGIN_SRC" ]; then
  echo "Merging plugin from $PLUGIN_SRC into $WP_DEST (non-destructive)"
  mkdir -p "$WP_DEST"
  rsync -av --ignore-existing --exclude='.git' "$PLUGIN_SRC"/ "$WP_DEST"/
  echo "Removing duplicate plugin directory: $PLUGIN_SRC"
  rm -rf "$PLUGIN_SRC"
fi
if [ -d "$WP_SRC" ]; then
  echo "Merging $WP_SRC into $WP_DEST (non-destructive)"
  mkdir -p "$WP_DEST"
  rsync -av --ignore-existing --exclude='.git' "$WP_SRC"/ "$WP_DEST"/
  echo "Removing duplicate directory: $WP_SRC"
  rm -rf "$WP_SRC"
fi

echo "Merge complete. Canonical micropython dir now contains:"
ls -la "$CANON"
exit 0
