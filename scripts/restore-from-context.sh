#!/usr/bin/env bash
set -euo pipefail

# Usage:
# ./scripts/restore-from-context.sh [source-dir] [target-dir]
# Defaults:
SRC="${1:-./context/unit-connector}"
TARGET="${2:-./unit-connector}"
BACKUP_DIR="./backups"
TIMESTAMP="$(date +%Y%m%d%H%M%S)"
BACKUP_PATH="${BACKUP_DIR}/unit-connector-backup-${TIMESTAMP}"

# Add CLI flags
YES=false
DRYRUN=false
COMMIT=false

while [[ $# -gt 0 ]]; do
	case "$1" in
		-y|--yes|--force) YES=true; shift ;;
		-n|--dry-run) DRYRUN=true; shift ;;
		-c|--commit) COMMIT=true; shift ;;
		-h|--help)
			cat <<'USAGE'
Usage: ./scripts/restore-from-context.sh [options] [source-dir] [target-dir]

Options:
  -y, --yes, --force    Run non-interactively (assume yes to prompt)
  -n, --dry-run         Show rsync plan without making changes
  -c, --commit          Auto-commit changes to git (if repository)
  -h, --help            Show this help
USAGE
			exit 0
			;;
		--) shift; break ;;
		*) 
			# positional args
			if [ -z "${SRC:-}" ] || [ "${SRC}" == "./context/unit-connector" ]; then
				SRC="$1"
			elif [ -z "${TARGET:-}" ] || [ "${TARGET}" == "./unit-connector" ]; then
				TARGET="$1"
			else
				echo "Extra argument: $1"
			fi
			shift
			;;
	esac
done

# Basic checks
if [ ! -d "$SRC" ]; then
	echo "Source directory not found: $SRC"
	echo "Try: ./scripts/restore-from-context.sh ./context ./unit-connector"
	exit 1
fi
if [ ! -d "$TARGET" ]; then
	echo "Target directory not found: $TARGET"
	echo "Create target or adjust target-dir argument."
	exit 1
fi

# Add helper to print diagnostics for missing commands and a safe rsync fallback
check_cmd() {
	if ! command -v "$1" >/dev/null 2>&1; then
		echo "NOTICE: '$1' not found in PATH."
		return 1
	fi
	return 0
}

# Dry-run: preview rsync and exit
if [ "$DRYRUN" = true ]; then
	echo "Dry-run: plan to copy from ${SRC%/}/ -> ${TARGET%/}/"
	if check_cmd rsync; then
		echo "Using rsync for dry-run:"
		rsync -avhn --delete \
			--exclude='.git' \
			--exclude='node_modules' \
			--exclude='vendor' \
			"${SRC%/}/" "${TARGET%/}/"
	else
		echo "rsync not found; using cp -avn as a dry-run approximation:"
		cp -avn "${SRC%/}/." "${TARGET%/}/" || true
	fi
	echo "Dry-run complete."
	exit 0
fi

# Confirm prompt unless --yes
if [ "$YES" != true ]; then
	echo "This will overwrite files in ${TARGET} with files from ${SRC}."
	read -p "Proceed? [y/N] " -r
	if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
		echo "Aborted."
		exit 0
	fi
fi

# Attempt to deactivate plugin via WP-CLI if available (safe, best-effort)
if command -v wp >/dev/null 2>&1; then
	if wp plugin is-active tmon-unit-connector >/dev/null 2>&1; then
		echo "Deactivating tmon-unit-connector via WP-CLI..."
		wp plugin deactivate tmon-unit-connector || echo "WP-CLI deactivate failed or not in WP root; continue."
	fi
fi

mkdir -p "$BACKUP_DIR"
echo "Backing up ${TARGET} -> ${BACKUP_PATH}"
mv "$TARGET" "${BACKUP_PATH}"

echo "Restoring ${SRC} -> ${TARGET}"
# Use rsync when available, otherwise fall back to cp -a
if check_cmd rsync; then
	rsync -a --delete \
		--exclude='.git' \
		--exclude='node_modules' \
		--exclude='vendor' \
		"${SRC%/}/" "${TARGET%/}/"
else
	echo "Warning: rsync not found; falling back to 'cp -a'. This will copy files but will not remove stale files in target."
	mkdir -p "${TARGET%/}/"
	cp -a "${SRC%/}/." "${TARGET%/}/"
fi

# Make sure files are readable
chmod -R u+rwX,go+rX,go-w "${TARGET}"

echo "Restore complete."

# Optional: commit to git (auto if --commit)
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
	if [ -n "$(git status --porcelain -- ${TARGET})" ]; then
		echo
		echo "Changes are pending for ${TARGET}."
		if [ "$COMMIT" = true ] || { [ "$YES" = true ] && [ "$COMMIT" = false ]; }; then
			git add "${TARGET}"
			git commit -m "Restore ${TARGET} from context snapshot (${TIMESTAMP})"
			echo "Committed. You may push with: git push"
		else
			# Interactive prompt when not auto-commit
			if [ "$YES" != true ]; then
				read -p "Commit changes to git? [y/N] " -r
			fi
			if [[ "$REPLY" =~ ^[Yy]$ ]] || [ "$COMMIT" = true ]; then
				git add "${TARGET}"
				git commit -m "Restore ${TARGET} from context snapshot (${TIMESTAMP})"
				echo "Committed. You may push with: git push"
			else
				echo "Skipping git commit."
			fi
		fi
	else
		echo "No changes detected to commit."
	fi
else
	echo "Not a git repository. Skipping commit step."
fi

# Attempt to deactivate/reactivate plugin via WP-CLI only when available; otherwise print guidance
if ! check_cmd wp; then
	echo "NOTE: 'wp' (WP-CLI) not found. If you need to deactivate/reactivate the plugin automatically, install WP-CLI or perform that step manually in the admin UI."
fi

echo
echo "Recommended next steps:"
echo "  1) Deactivate plugin before restore (if not already): wp plugin deactivate tmon-unit-connector"
echo "  2) After restore, reactivate: wp plugin activate tmon-unit-connector"
echo "  3) Check site admin and PHP error logs for issues (tail /var/log/php*.log or server logs)."
echo "Backed up previous plugin at: ${BACKUP_PATH}"
