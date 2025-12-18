#!/usr/bin/env bash
set -euo pipefail
ME_UID=$(id -u)
ME_GID=$(id -g)
WORKDIR="/workspaces/TMON"

if [ ! -d "$WORKDIR" ]; then
	echo "Workspace not found: $WORKDIR" >&2; exit 1
fi

echo "Attempting to set ownership of ${WORKDIR} to $(id -u -n):$(id -g -n) (may require sudo)..."
if [ "$(id -u)" -eq 0 ]; then
	chown -R "${ME_UID}:${ME_GID}" "${WORKDIR}"
else
	echo "Running: sudo chown -R ${ME_UID}:${ME_GID} ${WORKDIR}"
	sudo chown -R "${ME_UID}:${ME_GID}" "${WORKDIR}"
fi

echo "Making scripts executable in ${WORKDIR}/scripts"
chmod +x "${WORKDIR}/scripts/"*.sh || true

echo "Permissions updated. Re-run the replace script."
