#!/usr/bin/env bash
set -euo pipefail
echo "Checking required commands..."
for cmd in rsync wp git mv cp chmod; do
	if command -v "$cmd" >/dev/null 2>&1; then
		printf "  %-8s : OK (%s)\n" "$cmd" "$(command -v $cmd)"
	else
		printf "  %-8s : MISSING\n" "$cmd"
	fi
done
echo
echo "If 'rsync' is missing, install it on Ubuntu: sudo apt update && sudo apt install -y rsync"
echo "If 'wp' (WP-CLI) is missing, see https://wp-cli.org/#installing"
