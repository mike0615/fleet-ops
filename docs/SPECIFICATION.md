# FleetOps software specification

Version 2.1.0. This document describes the packaged implementation and acceptance
criteria. It does not certify a deployment for a particular security baseline.

| ID | Requirement | Acceptance |
|---|---|---|
| F-001 | Product name is FleetOps | UI, launcher, service and RPM use FleetOps/fleetops |
| F-002 | Preserve MAC Ops operational features | Login, inventory, playbook validation/run, schedule persistence and reports pass smoke review |
| F-003 | Embedded Help and About | `/help` and `/about` render with no network access; F1 opens Help |
| F-004 | About matches suite information | Logo, version, purpose, author, copyright, links and MIT notice present |
| I-001 | Offline install | Complete bundle installs with DNF repos disabled and pip no-index |
| I-002 | Check Ansible before install | Installer reports existing/missing Ansible before RPM installation |
| I-003 | Install Ansible when absent | Bundled private ansible and ansible-playbook run after installation |
| I-004 | Preserve system Ansible | No global Ansible executable is overwritten |
| I-005 | Match target | Wrong OS/architecture or wrong dist-tag bundle is rejected |
| I-006 | Verify media | Every bundled RPM and installation control file passes SHA-256 validation |
| I-007 | Upgrades preserve data | Inventory, playbooks, accounts, schedules, configuration and keys survive upgrade |
| S-001 | Persistent secrets | Session and vault keys remain stable across restarts/upgrades |
| S-002 | Least privilege | Root-owned code, unprivileged service and dedicated writable state |
| S-003 | Login for operations | Anonymous operational HTTP API and SSH socket connections denied |
| S-004 | No default credential | Administrator created interactively after installation |
| D-001 | Full release documentation | Manuals, ICD, spec sheet, specification, validation and release notes shipped |
| R-001 | Reproducible release procedure | Build scripts and exact dependency locks accompany OS-specific bundles |

## Architecture

Browser -> local Flask/Socket.IO service -> Ansible/Paramiko -> managed hosts.
The service uses SQLite for identities, roles, audit records and encrypted secrets.
Playbooks, inventory, reports and logs are filesystem resources. APScheduler
restores schedule definitions from JSON at service start. The Python runtime is
isolated in `/opt/fleetops/venv`; system Ansible is not used by the service.

## Operating constraints

The server requires Linux systemd and local persistent storage. A single process
must own schedules. Parallel browser edits are not locked. Runtime network access
is limited by operator actions and configured internal integrations rather than
an application network sandbox. No public service is necessary for normal use.
An air gap does not eliminate the need to authorize automation targets.

## Exclusions and qualification

No high availability, database clustering, automated rollback, RPM signing,
central secret service, load certification or cross-architecture binary release
is claimed. Placeholder tool plugins are not implemented DNS/DHCP/PXE services.
Full acceptance includes install, restart, upgrade, removal and restore on a real
target host with networking disabled. Completed evidence is recorded separately.
