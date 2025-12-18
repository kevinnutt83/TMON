#!/usr/bin/env bash
set -euo pipefail

# Replace the repository contents with the contents of TMON-main.
# Usage:
#   ./scripts/replace-with-tmon-main.sh [options] [src-dir] [target-dir]
# Options:
#   -y, --yes       : run non-interactively (assume yes)
#   -n, --dry-run   : show rsync plan without making changes
#   -c, --commit    : auto-commit changes to git (if inside git repo)
#   -h, --help      : show help
#
# Defaults: src-dir=./TMON-main, target-dir=.

SRC="${1:-./TMON-main}"
TARGET="${2:-.}"
BACKUP_BASE="./backups"
TIMESTAMP="$(date +%Y%m%d%H%M%S)"
BACKUP_PATH="${BACKUP_BASE}/repo-backup-${TIMESTAMP}"

YES=false
DRYRUN=false
COMMIT=false

while [[ $# -gt 0 ]]; do
	case "$1" in
		-y|--yes) YES=true; shift ;;
		-n|--dry-run) DRYRUN=true; shift ;;
		-c|--commit) COMMIT=true; shift ;;
		-h|--help) 
			cat <<'USAGE'
Usage: ./scripts/replace-with-tmon-main.sh [options] [src-dir] [target-dir]

Options:
  -y, --yes       Run non-interactively (assume yes)
  -n, --dry-run   Show rsync plan without making changes
  -c, --commit    Auto-commit changes to git (if inside git repo)
USAGE
			exit 0
			;;
		--) shift; break ;;
		*) 
			if [ "${SRC}" = "./TMON-main" ]; then SRC="$1"; else TARGET="$1"; fi
			shift ;;
	esac
done

# Prereqs
if [ ! -d "$SRC" ]; then
	echo "Source not found: $SRC" >&2; exit 1
fi
if [ ! -d "$TARGET" ]; then
	echo "Target not found: $TARGET" >&2; exit 1
fi
if ! command -v rsync >/dev/null 2>&1; then
	echo "ERROR: 'rsync' is required. Install: sudo apt update && sudo apt install -y rsync" >&2; exit 1
fi

# Permission check: target must be writable
if [ ! -w "$TARGET" ]; then
	cat <<'MSG' >&2
ERROR: Permission denied writing to the target repository.
Run the helper to fix workspace ownership or run the following as appropriate:
  sudo chown -R $(id -u):$(id -g) /workspaces/TMON
Or run: ./scripts/fix-permissions.sh
MSG
	exit 1
fi

# Dry-run
if [ "$DRYRUN" = true ]; then
	echo "DRY-RUN: rsync -avhn --delete --exclude='.git' --exclude='${BACKUP_BASE}' \"${SRC%/}/\" \"${TARGET%/}/\""
	rsync -avhn --delete --exclude='.git' --exclude="${BACKUP_BASE}" "${SRC%/}/" "${TARGET%/}/"
	exit 0
fi

if [ "$YES" != true ]; then
	echo "This will overwrite files in ${TARGET} with files from ${SRC} (preserves .git)."
	read -p "Proceed? [y/N] " -r
	if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then echo "Aborted."; exit 0; fi
fi

mkdir -p "$BACKUP_BASE"
echo "Creating backup of current repo (excluding .git) -> ${BACKUP_PATH}"
rsync -a --delete --exclude='.git' --exclude="${BACKUP_BASE}" ./ "${BACKUP_PATH}/"

echo "Syncing ${SRC} -> ${TARGET} (rsync --delete)"
rsync -a --delete --exclude='.git' --exclude="${BACKUP_BASE}" "${SRC%/}/" "${TARGET%/}/"

chmod -R u+rwX,go+rX,go-w "${TARGET}"

echo "Replace complete; backup at: ${BACKUP_PATH}"

# Optional commit
if [ "$COMMIT" = true ] && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
	if [ -n "$(git status --porcelain)" ]; then
		git add -A
		git commit -m "Replace repo contents with TMON-main snapshot (${TIMESTAMP})"
		echo "Committed. Push when ready: git push"
	else
		echo "No changes detected to commit."
	fi
fi

echo "Done."
