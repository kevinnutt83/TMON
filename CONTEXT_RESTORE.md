Context restore instructions

1. Ensure your context directory exists in the repo (default: ./context or ./context/unit-connector).
2. Deactivate the plugin on the site (recommended): wp plugin deactivate tmon-unit-connector
3. Run the script from the repo root:
   ./scripts/restore-from-context.sh [path/to/context] [path/to/target-plugin]
   Example: ./scripts/restore-from-context.sh ./context/unit-connector ./unit-connector
4. Optionally commit changes and push, then reactivate plugin:
   wp plugin activate tmon-unit-connector

The script will:
- Create a timestamped backup at ./backups/
- Copy files from the context into the plugin folder (rsync --delete)
- Optionally create a git commit
- Print validation steps and next actions

Examples:
  # Dry-run to preview:
  ./scripts/restore-from-context.sh --dry-run ./context/unit-connector ./unit-connector

  # Run non-interactively, auto-commit to git:
  ./scripts/restore-from-context.sh --yes --commit ./context/unit-connector ./unit-connector

Replace repository contents with your local TMON-main directory

Example (non-interactive, auto-commit):
  chmod +x ./scripts/replace-with-tmon-main.sh
  ./scripts/replace-with-tmon-main.sh --yes --commit ./TMON-main .

Dry-run:
  ./scripts/replace-with-tmon-main.sh --dry-run ./TMON-main .

Replace repo with TMON-main (non-interactive example):
  chmod +x ./scripts/replace-with-tmon-main.sh ./scripts/fix-permissions.sh
  # If you see permission denied, run:
  ./scripts/fix-permissions.sh
  # Then run replace (non-interactive, auto-commit):
  ./scripts/replace-with-tmon-main.sh --yes --commit ./TMON-main .
