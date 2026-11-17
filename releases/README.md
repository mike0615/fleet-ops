# FleetOps releases

Version **2.1.0**. Choose your Rocky Linux major version and x86_64 bundle.

| Target | Complete offline installer | Application RPM directory |
|---|---|---|
| Rocky 9 | [EL9 offline archive](2.1.0/fleetops-2.1.0-el9-x86_64-offline.tar.gz) | [EL9 RPMs](2.1.0/el9/rpms/) |
| Rocky 10 | [EL10 offline archive](2.1.0/fleetops-2.1.0-el10-x86_64-offline.tar.gz) | [EL10 RPMs](2.1.0/el10/rpms/) |

Use the complete archive on air-gapped hosts. Its `rpms/dependencies` directory
contains required OS packages, and each application RPM includes its Python
wheels and Ansible runtime dependencies. Extract, verify SHA256SUMS and run
`sudo bash install.sh`. See [installation](../docs/INSTALL.md),
[release notes](../RELEASE_NOTES.md) and [validation](../docs/VALIDATION.md).

This is the local release section. Remote GitHub Releases are separate and must
be published through an authenticated account. Initial packages are unsigned.
