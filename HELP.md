# FleetOps Help

FleetOps 2.1.0 — fleet infrastructure automation. Author: Mike Anderson.

## Getting started

Install the offline release matching Rocky Linux 9 or 10 and your x86_64 host.
Create an administrator with `runuser -u fleetops -- fleetops manage create-admin`,
then start `systemctl enable --now fleetops`. Open http://127.0.0.1:5000 and log in.
F1 opens this help; About shows version, author and license information.

## Inventory

Open Inventory and add your own approved host addresses and connection variables.
The initial inventory is intentionally empty. Save before running a playbook.
Group names and host aliases can be used as Ansible target patterns.
Store sensitive credentials in Ansible Vault or another approved secret store;
do not put plain passwords into inventory files or extra variables.

## Playbooks

Select a playbook in the file browser, edit its YAML, and save. Validate syntax
before execution. Choose the inventory and review the host selection and tasks.
Run only against approved targets. Package updates, account changes, service
control, enrollment and reboot playbooks change remote systems.
Syntax validation does not establish that a playbook is safe to execute.
Additional Ansible collections and roles must be staged offline before use.

## Schedules

Choose a playbook and inventory and supply a five-field cron expression:
minute, hour, day of month, month, day of week. Example: `0 2 * * *` means daily
at 02:00 in the server's local time. APScheduler uses Monday=0 for numeric
weekdays; use names such as `mon` to avoid cron dialect ambiguity.
Schedules survive service restarts. Pause schedules before maintenance or migration.

## Reports and run logs

Dashboard shows counts and recent runs. Reports shows structured JSON outputs
created by reporting playbooks; Run Logs shows captured Ansible output and recap.
An unsuccessful task, unreachable host or 900-second execution timeout requires
operator review. Logs may contain sensitive task output; restrict access and
use `no_log: true` in tasks that handle secrets.

## Host Checker

Enter approved host addresses or load inventory hosts. The checker tests ICMP,
TCP port 22 and inventory membership. Failed ping alone does not prove a host is
down; firewalls may block ICMP. Results can be copied as CSV.

## Ad-hoc Runner

Select the inventory, host pattern and Ansible module, then review its arguments.
The `command` and `shell` modules run commands on managed systems and can make
changes. Ad-hoc execution has a 60-second timeout. Use a playbook for repeatable work.

## SSH Console

Open SSH Console and enter host, port and account credentials. The console uses
a browser WebSocket to the FleetOps server; the server makes the SSH connection.
Use TLS or an SSH tunnel for browser access. Current SSH console behavior accepts
new host keys automatically; use Ansible or a dedicated SSH client when verified
host-key trust is required. Close or disconnect the session when finished.

## Accounts and secrets

Administrators use `/admin/` for local users, roles, audit events and secrets.
Local authentication works without LDAP. LDAP needs an explicitly configured,
reachable internal directory. Secrets use a persistent encryption key at
`/etc/fleetops/vault.key`; protect it and include it in encrypted backups.

## Offline dependencies

The installer checks for an existing Ansible and installs FleetOps' private
runtime from bundled wheels. It never overwrites `/usr/bin/ansible`.
Do not use a bare application RPM on a minimal offline host without the matching
dependency RPMs. Use the full OS-specific release bundle and `install.sh`.

## Troubleshooting

Service: `systemctl status fleetops` and `journalctl -u fleetops -n 100`.
Dependency check: `/opt/fleetops/venv/bin/pip check`.
Ansible: `/opt/fleetops/venv/bin/ansible-playbook --version`.
Health: `curl http://127.0.0.1:5000/healthz`.
Connection failures: check inventory, SSH credentials, host keys, DNS and firewall.
Permission errors: writable state belongs to `fleetops` in `/var/lib/fleetops`;
application files in `/opt/fleetops` belong to root.

## Backup and removal

Stop FleetOps and back up `/var/lib/fleetops` and `/etc/fleetops` together.
Restore with original ownership and permissions, then start the service.
`dnf remove fleetops` removes the application. Accounts, keys and operational
data are retained for recovery; delete them only under your data retention policy.
Edited packaged configuration is retained by RPM as `.rpmsave` on removal.
