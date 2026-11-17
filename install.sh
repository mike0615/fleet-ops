#!/bin/bash
# Offline by design: run from the expanded, OS-specific release bundle.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo bash install.sh' >&2; exit 1; }
cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")"
source /etc/os-release
major=${VERSION_ID%%.*}
[[ ${ID:-} == rocky && ( $major == 9 || $major == 10 ) ]] || { echo 'Supported targets: Rocky Linux 9 or 10, x86_64.' >&2; exit 1; }
[[ $(uname -m) == x86_64 ]] || { echo 'This bundle requires x86_64.' >&2; exit 1; }
[[ -f SHA256SUMS ]] || { echo 'Missing release checksums.' >&2; exit 1; }
sha256sum --check --strict SHA256SUMS
shopt -s nullglob
app=(rpms/fleetops-*.el"$major".x86_64.rpm)
[[ ${#app[@]} == 1 ]] || { echo "Expected one FleetOps EL$major RPM; use the matching release bundle." >&2; exit 1; }
if command -v ansible-playbook >/dev/null 2>&1 && ansible-playbook --version >/dev/null 2>&1; then
  echo 'Existing Ansible detected. FleetOps installs its tested private runtime alongside it.'
else
  echo 'Ansible not found or unusable. Installing bundled Ansible with FleetOps.'
fi
[[ -d rpms/dependencies ]] || { echo 'Missing offline OS dependency bundle.' >&2; exit 1; }
deps=(rpms/dependencies/*.rpm)
[[ ${#deps[@]} -gt 0 ]] || { echo 'Offline dependency bundle is empty.' >&2; exit 1; }
[[ -f rpms/dependencies/repodata/repomd.xml ]] || { echo 'Missing offline repository metadata.' >&2; exit 1; }
# No configured repositories may be contacted, even when dependencies are missing.
dnf -y --disablerepo='*' --repofrompath="fleetops-offline,file://$PWD/rpms/dependencies" --enablerepo=fleetops-offline --setopt=fleetops-offline.gpgcheck=1 --setopt=fleetops-offline.gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-Rocky-$major --setopt=install_weak_deps=False install "${app[@]}"
[[ -x /opt/fleetops/venv/bin/ansible-playbook ]] || { echo 'Private Ansible runtime was not installed.' >&2; exit 1; }
/opt/fleetops/venv/bin/pip check
/opt/fleetops/venv/bin/ansible-playbook --version
echo 'FleetOps ready. Create an administrator and start the service as documented in INSTALL.md.'
