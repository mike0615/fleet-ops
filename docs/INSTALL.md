# FleetOps installation guide

Version 2.1.0. Supported packaging targets: Rocky Linux 9 and 10, x86_64.
Use the bundle matching the target OS major version. No Windows or macOS installer
is supplied. RPMs contain architecture-specific wheels and therefore use x86_64.

## Prerequisites

Root access, working DNF/RPM, systemd, 2 CPU cores, 2 GB RAM, and 10 GB free disk
are the initial sizing baseline. Allow more for inventory, reports and logs.
These are planning values, not load-tested capacity guarantees. Transfer through
your approved media process. Verify the release checksum against a trusted copy
obtained before crossing the air gap. Checksums detect corruption; they are not
publisher signatures. The initial RPMs are unsigned.

## Offline installation

1. Obtain `fleetops-2.1.0-el9-x86_64-offline.tar.gz` or the EL10 equivalent.
2. Create an empty extraction directory and unpack the archive into it.
3. Run `sha256sum --check --strict SHA256SUMS` from that directory.
4. Run `sudo bash install.sh`.
5. Create an administrator and start the service:

```bash
sudo runuser -u fleetops -- fleetops manage create-admin
sudo systemctl enable --now fleetops
curl --fail http://127.0.0.1:5000/healthz
```

The installer checks OS/architecture, checksums and existing Ansible. It installs
local OS dependency RPMs with all repositories disabled. The application RPM
creates the service account, persistent session/vault keys, a private virtual
environment, database, default roles, an SSH key and seed automation. Pip uses
only packaged wheels. Existing system Ansible remains in place. FleetOps uses
`/opt/fleetops/venv/bin/ansible-playbook` through the service PATH.

No default administrator password is shipped. The service is not started until
you complete account setup. `/etc/fleetops/fleetops.env` defaults to loopback.
Open http://127.0.0.1:5000 on the server. Help and About are available before login.

## Remote browser access

An SSH tunnel avoids exposing the application port:

```bash
ssh -L 5000:127.0.0.1:5000 operator@fleetops-server
```

Open http://127.0.0.1:5000 on the client. For shared browser access, configure
an internally trusted TLS reverse proxy with WebSocket forwarding to loopback
port 5000. Stage proxy packages and certificates separately. No public CA or
internet certificate automation is required. Set `HTTPS=true` in fleetops.env
when the application is accessed exclusively through HTTPS, then restart.
Do not publish plain HTTP with user credentials on an untrusted network.

## Managed hosts

The seed inventory is empty. Populate it with approved hosts. Add FleetOps'
public key at `/var/lib/fleetops/.ssh/id_ed25519.pub` to the appropriate remote
accounts. Populate verified `known_hosts` entries in `/var/lib/fleetops/.ssh/`
for Ansible, which has host-key checking enabled. Configure remote privilege
escalation explicitly in your playbooks and inventory. No global passwordless
sudo policy or wheel-group membership is installed for the service account.

## Upgrade and repair

Back up configuration, keys and data before upgrading. Pause schedules and stop
the service. Run the new bundle's installer. RPM preserves edited configuration
with `%config(noreplace)`; inspect any `.rpmnew` files. Seed automation is copied
only when its data directory does not exist. Existing data and keys are retained.
Verify `pip check`, Ansible version and health before restarting automation.
For a failed runtime setup, inspect RPM output and journal, correct the cause,
then run `/opt/fleetops/setup-runtime.sh` as root. Do not treat a failed `%post`
message as a successful installation.

## Uninstall

Stop and disable the service, then `sudo dnf remove fleetops`. Persistent data,
service account, generated keys and virtual environment may remain. Back them up
before deliberate deletion. Never delete only the vault key while retaining
encrypted secrets you still need to recover.
RPM retains edited packaged configuration as `.rpmsave` files on removal.
