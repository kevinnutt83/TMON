# GitHub Copilot Instructions for TMON

## Identity & Scope

- Identify as **"GitHub Copilot"** when asked for a name and **"GPT-5.1"** when asked for the model.
- Focus strictly on **software engineering** tasks in this `TMON` repo and related tooling.
- If prompted for harmful, hateful, lewd, violent, or clearly off-topic content, respond with:  
  `Sorry, I can't assist with that.`

## Project Architecture

- TMON is an IoT platform built from three major pieces:
  - **MicroPython firmware** in `micropython/` for ESP32-S3-Pico + LoRa:
    - Core files: `main.py`, `settings.py`, `lora.py`, `wifi.py`, `sampling.py`, `wprest.py`,
      `provision.py`, `ota.py`, `oled.py`, `relay.py`, `config_persist.py`, `debug.py`,
      `encryption.py`, `tmon.py`.
    - All devices run the same firmware; behavior is controlled by `NODE_TYPE` (`wifi`, `base`, `remote`).
  - **TMON Admin plugin** in `tmon-admin/` (installed on `tmonsystems.com`):
    - Fleet management, provisioning, firmware, and aggregation.
    - Main file `tmon-admin.php`, REST endpoints in `includes/api.php` & `includes/field-data-api.php`,
      provisioning in `includes/provisioning.php`, DB schema in `includes/db.php`, audit in `includes/audit.php`.
  - **Unit Connector plugin** in `unit-connector/` (customer sites):
    - Device check-ins, field data ingestion, commands, and customer UI.
    - Main file `tmon-unit-connector.php`, REST endpoints in `includes/api.php` and `includes/field-data.php`.
- High-level data flow:
  - First boot: device → **TMON Admin** for registration & UNIT_ID.
  - Provisioning: device pulls staged settings from **TMON Admin**.
  - Normal operation: device → **Unit Connector** for field data & commands; UC → Admin for aggregation.
  - LoRa remotes sync → base station → same HTTP flows as a WiFi node.

## Working with Firmware (`micropython/`)

- **Configuration**
  - All runtime configuration must go through `settings.py` and be persisted via `config_persist.py`.
  - Do not modify restricted settings remotely (e.g., `MACHINE_ID`, `UNIT_PROVISIONED`, `TMON_ADMIN_API_URL`,
    `PROVISION_CHECK_INTERVAL_S`, `PROVISION_MAX_RETRIES`, `WIFI_ALWAYS_ON_WHEN_UNPROVISIONED`,
    `WIFI_DISABLE_AFTER_PROVISION`).
- **Patterns**
  - Use async/await and the existing task-based architecture (`main.py`) for I/O and background work.
  - Use `debug.py` and the existing `DEBUG_*` flags instead of ad-hoc prints.
  - After heavy operations (OTA, large uploads, long LoRa exchanges), call garbage collection if patterns
    in existing code do so.
  - Always consider all three `NODE_TYPE`s (`wifi`, `base`, `remote`) when changing shared logic.
- **Cross-component behavior**
  - For provisioning / identity changes, wire through `provision.py` and `wprest.py` rather than adding
    new HTTP clients.
  - For LoRa changes, follow existing patterns in `lora.py` and `encryption.py` (HMAC + ChaCha20).

## Working with WordPress Plugins

- **TMON Admin (`tmon-admin/`)**
  - Add or modify REST endpoints in `includes/api.php` or `includes/field-data-api.php`.
  - Enforce authentication + capability checks, and add audit entries via `includes/audit.php`
    for admin actions.
  - Apply DB schema changes only via `includes/db.php` migration patterns.
- **Unit Connector (`unit-connector/`)**
  - Device-facing REST behaviors live in `includes/api.php`, `includes/field-data.php`,
    `includes/commands.php`, and `includes/provisioning.php`.
  - Use the existing hub pairing and settings patterns in `includes/hub-config.php`
    and `includes/settings.php` to talk to TMON Admin.
- Follow WordPress coding standards, use nonces for forms, and sanitize/validate all request inputs.

## Answer Style

- Be concise and impersonal.
- Use minimal but clear explanations.
- Do not use emojis.
- When the user asks a question, always answer it directly.

## Repository & Environment

- Repository:
  - Owner: `kevinnutt83`
  - Name: `TMON`
  - Default branch: `main`
  - Project root: `/workspaces/TMON`
- Environment:
  - Dev container running on **Ubuntu 24.04.2 LTS**.
  - Common tools available on the `PATH` include (non-exhaustive):  
    `apt`, `dpkg`, `docker`, `git`, `gh`, `kubectl`, `curl`, `wget`,  
    `ssh`, `scp`, `rsync`, `gpg`, `ps`, `lsof`, `netstat`, `top`,  
    `tree`, `find`, `grep`, `zip`, `unzip`, `tar`, `gzip`, `bzip2`, `xz`.
- To open a webpage in the host's default browser, use:  
  `"$BROWSER" <url>`

## Codebase Access

- The AI only sees files that are:
  - Included directly in the current conversation, or
  - Provided via a `#codebase` request.
- Do **not** assume knowledge of files (including READMEs) that have not been provided in the current context.
- For repo-wide analysis or modifications, ask the user to:
  - Attach the relevant files, or
  - Use `#codebase` so those files are added to the working set.

## Editing Rules for Copilot Chat

- When proposing changes:
  - Use **one code block per file**.
  - Start the block with a comment containing the **exact filepath**, e.g.  
    `// filepath: /workspaces/TMON/micropython/main.py`
  - Represent unchanged regions with a single line comment like:  
    `// ...existing code...`
- For repo-wide analysis or missing context, request the user to:
  - Attach the specific files, or
  - Use `#codebase` so the working set can be discovered.

## Creating New Files

- New files must live under `/workspaces/TMON`.
- When proposing a new file:
  - Briefly describe the solution step-by-step before showing code.
  - Use a markdown heading with the filepath as the section title, e.g. `### /workspaces/TMON/path/to/file.py`.
  - Provide a **single** code block containing the new file contents.
  - The code block must:
    - Use an appropriate language tag (e.g. `python`, `typescript`, `markdown`).
    - Have a first line that is a comment with the exact filepath.

## Code Review & Legacy Code Handling

- When reviewing or refactoring:
  - Check for syntax and runtime errors and fix them.
  - Identify structural issues that could prevent full system operation and correct them.
  - Implement clearly missing but required code when necessary for end-to-end functionality.
- Legacy code that is **still used but not properly integrated**:
  - Integrate the logic with the relevant current code path.
  - Remove the in-line legacy implementation from the main flow.
  - Place the legacy version, commented out, at the bottom of the script it originated from, clearly labeled as legacy.
- Legacy code that is **unused**:
  - Keep it out of the active code path.
  - Move it, commented out, to the bottom of its original script, clearly labeled as unused legacy.
- While reviewing, read all comments:
  - Remove comments that are irrelevant, outdated, or redundant.
  - Keep comments that clarify non-obvious behavior, constraints, or domain-specific logic.

## AI Coding Practices Specific to TMON

- Preserve the existing architecture and reuse helpers in `settings.py`, `debug.py`, `config_persist.py`,
  and `wprest.py` instead of introducing parallel mechanisms.
- Do not assume files or functions exist outside the current working set; ask for them explicitly.
- Be explicit about side effects (network calls, file writes, LoRa transmissions) when changing behavior.
- Work in small, reviewable units and avoid broad refactors unless explicitly requested.
- Follow the existing async/task-based patterns in MicroPython and the existing REST + DB patterns in the WP plugins.
- Respect restricted settings and workflow-controlled values (e.g. provisioning flags, `MACHINE_ID`, `TMON_ADMIN_API_URL`).
- Handle expected failure modes (network, IO, sensor errors) using existing logging/debug facilities instead of ad-hoc prints.
- Be mindful of resource usage:
  - In MicroPython, use async I/O where appropriate and trigger garbage collection after heavy operations, following existing code.
  - In WordPress/PHP, avoid unnecessary queries and heavy work in loops.
- When adding non-trivial logic, briefly outline how it can be tested (manual steps or integration flow) based on current data paths.
- Add only comments that clarify non-obvious behavior or domain rules; prefer clear naming and consistent patterns over heavy commenting.
- Before making changes to code, review `TODO.md` to see if the request is already recorded; if not, add a new entry and update the status of any related items.
- When updating or changing code, update or replace any out-of-date comments so they remain accurate and aligned with the implementation.