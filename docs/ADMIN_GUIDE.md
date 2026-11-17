# FleetOps administration guide

## Service and configuration

Use `systemctl status|start|stop|restart fleetops` and `journalctl -u fleetops`.
Service configuration is `/etc/fleetops/fleetops.env`; authentication and LDAP
configuration is `/etc/fleetops/fleetops.conf`; Ansible configuration is
`/etc/fleetops/ansible.cfg`. Restart after changes. A single service process owns
the schedule loader. Do not run `fleetops serve` concurrently with systemd.

Application files and Python runtime reside in `/opt/fleetops` and are root-owned.
Writable state resides in `/var/lib/fleetops`, owned by the service account.
Session and vault keys are root-owned, group-readable by fleetops (0640), under
a 0750 configuration directory. The state directory is 0700. The service has
an unprivileged account, private temporary directory and read-only system paths.

## Accounts

Run `runuser -u fleetops -- fleetops manage create-admin` for initial setup.
Other CLI commands: `create-user`, `list-users`, `disable-user`, `enable-user`,
`reset-password`, `init-db`. Use `/admin/` for web administration. Administrative
APIs require the matching `admin` permission. Password validation follows the
inherited minimum of eight characters with uppercase, lowercase and digits.
Use longer unique passwords according to your organization's policy.

## LDAP / FreeIPA

Local authentication is the default. Configure the directory under `[ldap]`,
including server, port, TLS, base DN, bind DN/password and DN templates where
needed. Use a trusted internal CA and verify the directory using a test account.
Directory access is an internal network dependency; FleetOps does not bundle an
LDAP server. Keep a local administrator available for directory outages.

## Backup and restoration

Pause schedules and stop the service. Back up `/var/lib/fleetops` and
`/etc/fleetops` as one consistent set, preserving ownership and permissions.
Encrypt the archive because it contains database records, SSH keys and the vault
encryption key. Restore to the same FleetOps version before upgrading. Verify
database login, vault decryption, inventory, schedules and a harmless approved
playbook before re-enabling scheduling. Losing the vault key prevents decryption.

## Maintenance

Monitor disk use in logs and reports; retention is operator-managed in this
release. Obtain dependency updates on a connected build host, rebuild each OS
bundle, retest, and transfer through the approved process. Never run online pip
upgrades on an air-gapped host. No automatic update check or telemetry is present.

## Troubleshooting

If the service fails, inspect the journal and run the private pip dependency check.
Verify configuration readability by the service account and state ownership.
If Ansible fails, inspect the execution log, inventory, known_hosts and remote
permissions. A missing collection needs a separately staged offline collection.
For LDAP failures, test DNS, certificate trust and bind/search settings.
For SSH console errors, check browser WebSocket forwarding and internal TCP 22.

The current SSH console retains automatic acceptance of new host keys. Do not use
it when strict identity verification is required. Systemd hardening does not
constrain tasks you explicitly authorize against remote hosts.


## Saved SSH credentials

SSH Console supports optional encrypted saving. Enter a label, host, port,
username and password, then choose **Save encrypted credentials**. Choose that
entry from the saved-credentials list on later visits and press Connect. Select
manual entry to make a one-time connection without saving. To rotate a saved
password, delete the old entry and save a replacement.

Connection details, including the password, host, port and username, are encrypted
with Fernet before insertion into the local SQLite database. Labels and ownership
metadata remain readable; never put a password into a label. Each entry belongs
to the FleetOps account that created it. Other accounts cannot list, delete or
connect using that entry. Saved passwords are decrypted only on the server when
connecting and are never returned to the browser. Credentials are not kept in
browser local storage. SSH access permission is required.

The persistent key is `/etc/fleetops/vault.key`, separate from the database and
readable by root and the FleetOps service group. An explicit environment-key
override is also supported. Startup fails if a persistent key is missing or
invalid; it never silently substitutes a temporary key. Keep the key and database
together in encrypted backups. Local encryption protects stored data but does
not protect against root or compromise of the running service. Use the SSH tunnel
or HTTPS to protect credential entry in transit.
