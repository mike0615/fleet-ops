# FleetOps Interface Control Document

Version 2.1.0. Owner: Mike Anderson. Scope: FleetOps browser, service, automation,
local storage, identity integration, installer and companion application launch.

## Interface summary

| Interface | Protocol / direction | Default |
|---|---|---|
| Browser -> FleetOps | HTTP with JSON and static HTML/CSS/JS | loopback TCP 5000 |
| SSH terminal browser -> service | Socket.IO, namespace `/ssh` | same origin and port |
| Service -> managed host | SSH, Ansible or Paramiko | TCP 22, operator configured |
| Service -> optional directory | LDAP with configured TLS | TCP 389 by default |
| Launcher -> browser | `xdg-open` | http://127.0.0.1:5000/ |
| Management CLI -> SQLite | local SQLAlchemy | `/var/lib/fleetops/fleetops.db` |
| Installer -> RPM/DNF | local filesystem packages | repositories disabled |
| RPM setup -> pip | local wheels only | `--no-index` |

No public internet endpoint is part of a required runtime interface. Optional
About links open only after a user follows them. Custom playbooks may introduce
additional internal or external endpoints; review those independently.

## HTTP contract

JSON requests use `Content-Type: application/json`; responses use JSON except
document/static routes. Login uses session cookies (`HttpOnly`, `SameSite=Lax`;
`Secure` when HTTPS is configured). Return codes normally use 200 for success,
400 for invalid inputs, 401 for unauthenticated calls, 403 for denied permissions,
404 for missing files and 500 for execution/server errors. Some retained routes
return an error object with HTTP 200; clients must inspect payloads as well.

`GET /healthz` returns `{application:"FleetOps",version:"2.1.0",status:"ok"}`.
It reports process responsiveness, not managed-host readiness or LDAP health.
`POST /auth/login` takes username, password, optional auth_method and remember_me.
`POST /auth/logout` clears the session. `GET /auth/status` reports directory
configuration/connectivity. `GET /auth/me` returns the logged-in user.

The generated [route inventory](API_ROUTES.md) enumerates paths and methods.
Operational API authorization uses `ansible:view_playbooks` for reads and
`ansible:execute_playbook` for writes. Admin and vault routes use their own
permission decorators. The API is inherited from MAC Ops and is not a versioned
external integration standard; consumers must test against each release.

## Operational payloads

Playbook and inventory GET/PUT routes exchange `{content: "..."}`. A playbook
run takes `playbook`, `inventory` and optional `extra_vars`; YAML validation takes
`content` containing the YAML text. Execution returns success, returncode, stdout,
stderr, log_file and run_id where available. Schedules store id, name, playbook,
inventory, cron and enabled. Report bodies follow their producing playbooks.
Do not assume all reports share one schema. Logs are text with ANSI sequences.

## SSH socket contract

Connection to namespace `/ssh` requires an authenticated account with
`ansible:access_terminal`. Client events include `connect_ssh` (host, port,
username, password), `input` (data), `resize` (cols, rows), and disconnect.
Server events include output, connected, disconnected and error.
The browser never receives a server-side private key. The retained Paramiko
console accepts unknown host keys automatically; this is a known limitation.

## Filesystem contract

| Path | Owner / use |
|---|---|
| `/opt/fleetops` | root, packaged code, wheels and private runtime |
| `/etc/fleetops/fleetops.conf` | root:fleetops, INI configuration, preserve on upgrade |
| `/etc/fleetops/fleetops.env` | root:fleetops, systemd environment, preserve on upgrade |
| `/etc/fleetops/ansible.cfg` | root:fleetops, dedicated Ansible settings |
| `/etc/fleetops/session.key` | generated once, Flask session signing |
| `/etc/fleetops/vault.key` | generated once, Fernet key; required for recovery |
| `/var/lib/fleetops/fleetops.db` | SQLite identities, permissions, audit and vault ciphertext |
| `/var/lib/fleetops/ansible` | operator playbooks, inventory, group_vars, roles |
| `/var/lib/fleetops/schedules.json` | persistent cron definitions |
| `/var/lib/fleetops/reports` | generated JSON reports |
| `/var/lib/fleetops/logs` | application and execution logs |
| `/var/lib/fleetops/.ssh` | automation keypair and known_hosts |

State is not removed automatically on uninstall. Back up keys and database
together. Template playbooks may use configurable report destinations; align
them with the controller's reports path before production use.

## Configuration and compatibility

`FLEETOPS_HOST`, `FLEETOPS_PORT`, `FLEETOPS_DATA_DIR`, `FLEETOPS_CONFIG`,
`FLEETOPS_DATABASE_URL`, `FLEETOPS_SECRET_KEY`, `FLEETOPS_KEY_FILE`,
`FLEETOPS_SECRETS_KEY`, `FLEETOPS_VAULT_KEY_FILE` configure runtime behavior.
Do not expose secret values in diagnostics. `ANSIBLE_CONFIG` is supplied by
systemd. Existing `MAC_` environment names and `/opt/mac-ops` paths are not
automatically migrated. See MIGRATION.md.

## Release interface

Each dist-tagged RPM contains a matching wheel set and dependency lock. The
offline tar archive adds OS dependency RPMs, installer, documentation and
SHA256SUMS. Do not combine EL9/EL10 wheels or RPM closures. The release notes
identify changes; VALIDATION.md identifies qualification limits.
