# FleetOps 2.1.0 — November 16, 2026

First FleetOps release, based on MAC Ops 2.0.0.

- Renamed the application, RPM, service account, launcher and configuration paths.
- Added embedded Help, F1 navigation and About with suite-style author/license information.
- Replaced CDN dependencies with local browser assets.
- Added OS-specific RPM builds and complete offline installation bundles.
- Checks existing Ansible and installs a private bundled runtime, preserving system Ansible.
- Uses DNF with repositories disabled and pip with no-index during installation.
- Stores state under /var/lib/fleetops and preserves data/configuration on upgrades.
- Generates persistent session and vault keys; defaults the listener to loopback.
- Requires authentication for operational APIs and SSH socket connections.
- Includes user/admin/install manuals, ICD, specification, spec sheet and migration guide.

## Compatibility and limitations

Rocky Linux 9/10 x86_64 packages are distinct. RPM payloads contain native wheels.
EL9 uses the inherited Python-compatible ansible-core 2.15.13 baseline; evaluate
its lifecycle before production use. Custom roles and collections must be staged
separately. Existing MAC Ops data migration is explicit and operator-controlled.
No automatic destructive migration, external telemetry or update checks.

The SSH console retains automatic acceptance of new host keys. Use verified
Ansible known_hosts or a dedicated SSH client for strict host identity assurance.
The service remains a single-process Flask/Socket.IO application; use an internal
TLS reverse proxy for shared access. No high-availability or load rating is claimed.
The repository URL remains mac-ops until the remote rename is completed.

See docs/VALIDATION.md for evidence and remaining target-host acceptance checks.
