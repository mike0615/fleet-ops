# FleetOps

Fleet infrastructure automation, built from MAC Ops. Version **2.1.0**.
Author: Mike Anderson. License: MIT.

FleetOps runs as a local systemd service with a browser interface. It manages
Ansible playbooks, inventory, cron schedules, reports, execution logs, host
checks and SSH sessions. Local accounts, LDAP authentication, roles and an
encrypted secrets vault are retained from MAC Ops.

**Who it's for:** Administrators who run Ansible across a fleet and want a local browser interface for playbooks, inventory, schedules, reports and logs.

## Install

Use the OS-specific offline release under [releases/](releases/README.md).
The complete bundle includes the FleetOps RPM, the OS dependency RPMs, Python
wheels, a private Ansible runtime, release notes and SHA-256 checksums.

```bash
mkdir -p fleetops-release
tar -xzf fleetops-2.1.0-el9-x86_64-offline.tar.gz -C fleetops-release
cd fleetops-release
sudo bash install.sh
sudo runuser -u fleetops -- fleetops manage create-admin
sudo systemctl enable --now fleetops
```

Create the extraction directory first (`mkdir fleetops-release`). Choose the
EL10 archive for Rocky Linux 10. Open `http://127.0.0.1:5000` on the installed
host. The service listens on loopback by default. For access from another
machine, use an SSH tunnel or configure a TLS reverse proxy as described in
the installation guide.

The installer checks for Ansible before installation. FleetOps always uses
its bundled, tested private Ansible environment and leaves a pre-existing
system installation in place. Offline installation explicitly disables all
DNF repositories and uses pip's `--no-index` mode. No pip, Galaxy or CDN
download is performed by the installed application.

## Documentation

| Document | Contents |
|---|---|
| [Help](HELP.md) | Embedded help and common operator tasks |
| [Installation](docs/INSTALL.md) | Prerequisites, offline setup and verification |
| [User manual](docs/USER_MANUAL.md) | Playbooks, inventory, schedules, reports and tools |
| [Administration](docs/ADMIN_GUIDE.md) | Service, accounts, LDAP, backups and troubleshooting |
| [ICD](docs/ICD.md) | Interfaces, routes, formats, paths and integration constraints |
| [Specification](docs/SPECIFICATION.md) | Requirements, behavior and acceptance criteria |
| [Spec sheet](docs/SPEC_SHEET.md) | Concise technical product information |
| [Build and release](docs/BUILD_RELEASE.md) | Reproduce RPMs and offline bundles |
| [Migration](docs/MIGRATION.md) | Move data from MAC Ops without automatic destructive changes |
| [Validation](docs/VALIDATION.md) | Completed checks and remaining qualification |
| [Release notes](RELEASE_NOTES.md) | Changes and limitations |

Press **F1** or choose **Help** in the application. The About page follows the
companion apps: logo, name, version, purpose, author, copyright, links and MIT notice.
Project links on that page are optional external navigation; help itself is local.

## Repository layout

`backend/` contains the service; `frontend/` contains the interface and vendored
assets; `ansible/` contains seed automation; `bin/` contains the launcher;
`packaging/` contains RPM and systemd definitions; `docs/` contains manuals;
`tests/` contains checks; `releases/` contains installers and release artifacts.

## Build

```bash
bash build.sh 9 10
```

Requires Podman (or `CONTAINER_ENGINE=docker`), network access on the build
machine, and sufficient disk space. Target systems need no internet access.
See [build instructions](docs/BUILD_RELEASE.md) for validation and release rules.

MAC Ops remains the upstream GitHub repository URL until the remote repository
is renamed. Application, RPM, service and configuration names are `fleetops`.

Saved SSH credentials are optionally encrypted in the local vault, isolated by FleetOps account, and reused server-side without returning passwords to the browser. See Help for key backup requirements.

---

**Part of the Cyber Chief toolkit** by Anderson Computer. Sibling projects: [Flagship](https://github.com/mike0615/flagship) · [Flagship Web](https://github.com/mike0615/flagship-web) · [Porthole](https://github.com/mike0615/porthole) · [Skiff](https://github.com/mike0615/skiff) · [Sonar](https://github.com/mike0615/sonar) · [Helm RDP](https://github.com/mike0615/helm-rdp) · [Pathfinder](https://github.com/mike0615/pathfinder) · [Dockyard](https://github.com/mike0615/dockyard) · [CommShack](https://github.com/mike0615/commshack).
