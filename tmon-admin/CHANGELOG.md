## v0.1.5 - 2025-11-29
- Admin: Added "assert-queue" WP-CLI command: wp tmon-admin assert-queue --key=<unit_or_machine_id> to quickly test for queued payloads.
- Admin: Provisioning UI now shows a provisioning queue diagnostic banner (queued count + last queued ts).
- Admin: Moved purge UI from Provisioning to Settings to reduce accidents; purge remains accessible for admins.
- Admin: Added more logging for "Save & Provision" and queue enqueue events to help debugging.
- Admin: Minor docs update to README and CHANGELOG regarding CLI tooling and purge relocation.

### v0.1.6 - 2025-11-29
- Admin: Added "Queue & Notify" quick action to Provisioning rows to enqueue and send settings push to paired Unit Connector.
- Admin: Introduced 'Queue Lifetime' and 'Max Pending Per Site' settings under Settings → Provisioning Queue.
- Admin: Enhanced enqueue logs to include requested_by_user and site context.
- Tests: Added PHPUnit test to assert enqueue behavior and requested_by_user logging.
