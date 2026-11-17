# FleetOps 2.1.0 validation record

Date: November 16, 2026. Build host: Windows with Ubuntu WSL and Podman.
Native Rocky Linux 9 and 10 x86_64 build containers generated each wheel set.
Installation tests used fresh Rocky containers with `--network none`.

| Check | Result |
|---|---|
| RPM builds, EL9 and EL10 | Passed |
| Resolved wheel installs and pip check | Passed on both OS versions |
| Fresh offline installation, Ansible initially absent | Passed on both OS versions |
| Existing usable Ansible detected by installer | Passed on both OS versions |
| Installed application smoke suite | 7 tests passed per OS |
| Service-account execution of smoke suite | Passed on both OS versions |
| Login, viewer/admin authorization and anonymous socket rejection | Passed |
| Localhost Ansible playbook execution | Passed on both OS versions |
| Schedule JSON persistence and vault-key reuse | Passed |
| Same-version RPM reinstall preserves state/configuration/keys | Passed on both OS versions |
| Live unprivileged server health endpoint | Passed on both OS versions |
| Removal preserves state/keys and edited configuration as rpmsave | Passed on both OS versions |
| Original auth/RBAC/vault unit suite | 6 tests passed |
| HTML resource audit | Passed; browser resources reference bundled local assets |
| Python syntax compilation | Passed |

The original unit fixture had duplicate module identities, a mismatched permission
name and local test users without required passwords. The fixture was corrected
without relaxing application password requirements. Dependency deprecation
warnings remain and do not prevent the tested behavior.

## Remaining target-host qualification

Container tests do not establish complete systemd boot behavior, SELinux-enforcing
policy behavior, desktop launcher integration, interactive browser SSH, LDAP with
your directory/CA, upgrade from a deployed MAC Ops database, encrypted backup
restoration, or performance capacity. Test these on a representative disconnected
Rocky host before production adoption. The package ships a migration procedure;
no live MAC Ops deployment was changed during this work.

The release is unsigned. Checksums verify artifact integrity, not publisher identity.
The EL9 Ansible baseline and all dependencies need lifecycle/security review under
your organization's patch policy. No compliance certification is claimed.

Vault acceptance: password/host/username absent from plaintext database contents; saved password absent from API and socket responses; other accounts denied; ciphertext decrypts in a new process using the persisted key; server-side SSH credential resolution tested with a mocked transport; missing-key startup fails. Real SSH authentication with saved credentials remains a site acceptance step.
