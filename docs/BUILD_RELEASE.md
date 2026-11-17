# Building and releasing FleetOps

Use `bash build.sh 9 10` with Podman; set CONTAINER_ENGINE=docker for Docker.
The connected build host downloads dependencies. Installation and operation on
the disconnected target never download dependencies.

Each Rocky container builds wheels using its native Python and OpenLDAP headers,
installs them into a clean verification venv with no-index, records a resolved
requirements.lock and runs pip check. It builds the RPM with rpmbuild and stages
an OS dependency closure using `dnf download --resolve --alldeps`. The application
RPM requires openldap, Python, SSH clients, ping, systemd and account tools.

The current dependency policy retains ansible-core 2.15.13 for Rocky 9's Python
3.9 compatibility; Rocky 10 uses the 2.19 minor series. Exact resolved versions
are recorded per release. Rebuild and review lifecycle/security policy before
production use. Current source ranges do not guarantee bit-for-bit reproduction
at a later date; retain the supplied source archives, wheels and locks.

Outputs: `releases/2.1.0/el9`, `el10`, matching full offline tar archives,
OS-specific source archives and SHA-256 checksums. Keep application RPMs and full
offline bundles together in the release section. A bare RPM alone cannot install
missing OS packages offline. Release notes must state qualification limits.

Before publishing, run unit/API smoke tests and network-disabled container
install tests, then complete a real systemd-host acceptance test: clean install
with Ansible absent, install with Ansible present, account creation, login,
Help/About, a harmless localhost playbook, service restart, schedule persistence,
upgrade preserving state, backup/restore and uninstall preserving data. SELinux
enforcing, desktop launch, LDAP and interactive SSH require target-host tests.

No signing key is bundled. Sign RPMs using the organization's approved release
key if required, publish its fingerprint through a trusted channel and update
the offline verification procedure. GitHub release publication and repository
rename require authenticated GitHub write access; the local release directory
does not by itself publish a remote release.
