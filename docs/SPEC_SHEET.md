# FleetOps specification sheet

| Item | Specification |
|---|---|
| Product / version | FleetOps 2.1.0 |
| Author / license | Mike Anderson / MIT |
| Purpose | Fleet infrastructure automation and operations console |
| Packaging targets | Rocky Linux 9 and 10, x86_64; separate RPMs and offline bundles |
| Interface | Browser UI, HTTP/JSON API, Socket.IO SSH terminal, management CLI |
| Service | `fleetops.service`, one process, unprivileged `fleetops` account |
| Default listener | 127.0.0.1:5000; remote access by SSH tunnel or TLS proxy |
| Automation | Private bundled ansible-core; existing system Ansible preserved |
| Initial Ansible selection | EL9: 2.15.13; EL10: 2.19.x; exact build lock accompanies release |
| Application stack | Python, Flask, Flask-SocketIO, SQLAlchemy, APScheduler, Paramiko |
| Storage | SQLite, local YAML/INI/JSON/text files |
| Features | Playbook and inventory editing, execution, schedules, reports, logs, host checks, SSH |
| Authentication | Local accounts, optional internal LDAP/FreeIPA, roles |
| Secret storage | Fernet encryption, persistent local vault key |
| Offline contents | OS RPM dependency closure, Python wheels, local browser assets, Help and About |
| Documentation | Embedded Help, installation, user/admin manuals, ICD, specification, release notes |
| Initial sizing | 2 CPU cores, 2 GB RAM, 10 GB free disk; planning baseline |
| Execution limits | Playbook: 900 seconds; ad-hoc: 60 seconds |
| Internet at runtime | None required; external About links are optional |
| Additional staging | Custom roles/collections, internal certificates and target credentials |
| Qualification | See VALIDATION.md; capacity and full physical air-gap tests are separate |

EL9 retains the upstream Python-compatible Ansible baseline. Evaluate its support
lifecycle against your environment's policy before production deployment.
