#!/bin/bash
set -euo pipefail
major=$1
dnf -y install rpm-build python3 python3-pip python3-devel gcc openldap-devel cyrus-sasl-devel openssl-devel dnf-plugins-core tar gzip findutils git createrepo_c
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
src="$work/fleetops-2.1.0"
mkdir -p "$src"
for item in backend frontend ansible docs packaging bin tests .github .gitignore build.sh install.sh VERSION HELP.md LICENSE README.md RELEASE_NOTES.md; do cp -a "/src/$item" "$src/"; done
find "$src" -type d -name __pycache__ -prune -exec rm -rf {} +
python3 -m venv "$work/buildenv"
pip="$work/buildenv/bin/pip"
"$pip" install --upgrade pip wheel setuptools
if [[ $major == 9 ]]; then ansible='ansible-core==2.15.13'; else ansible='ansible-core>=2.19,<2.20'; fi
mkdir "$src/wheels"
"$pip" wheel --wheel-dir "$src/wheels" -r "$src/backend/requirements.txt" "$ansible"
python3 -m venv "$work/verify"
"$work/verify/bin/pip" install --no-index --find-links="$src/wheels" -r "$src/backend/requirements.txt" "$ansible"
"$work/verify/bin/pip" check
"$work/verify/bin/pip" freeze > "$src/requirements.lock"
mkdir -p "/src/releases/2.1.0/el$major/dependency-sources"
python3 /src/packaging/collect-sources.py "$src/requirements.lock" "/src/releases/2.1.0/el$major/dependency-sources"
"$work/verify/bin/ansible-playbook" --version
rpmbuild="$work/rpmbuild"
mkdir -p "$rpmbuild"/{SOURCES,SPECS,BUILD,BUILDROOT,RPMS,SRPMS}
tar -C "$work" -czf "$rpmbuild/SOURCES/fleetops-2.1.0.tar.gz" fleetops-2.1.0
rpmbuild -bb --define "_topdir $rpmbuild" --define "dist .el$major" "$src/packaging/fleetops.spec"
release="/src/releases/2.1.0/el$major"
mkdir -p "$release/rpms/dependencies"
cp "$rpmbuild"/RPMS/x86_64/*.rpm "$release/rpms/"
dnf download -y --resolve --alldeps --destdir "$release/rpms/dependencies" python3 python3-pip openssh-clients iputils openldap systemd util-linux shadow-utils rpm-plugin-syslog
createrepo_c "$release/rpms/dependencies"
cp /src/install.sh "$release/"
cp /src/docs/INSTALL.md "$release/INSTALL.md"
cp /src/RELEASE_NOTES.md "$release/RELEASE_NOTES.md"
cp "$src/requirements.lock" "$release/requirements.lock"
cp "$rpmbuild/SOURCES/fleetops-2.1.0.tar.gz" "/src/releases/2.1.0/fleetops-2.1.0-el$major-source.tar.gz"
(cd "$release"; find rpms -type f -print0 | sort -z | xargs -0 sha256sum; sha256sum install.sh INSTALL.md RELEASE_NOTES.md requirements.lock) > "$release/SHA256SUMS"
tar -C "$release" -czf "/src/releases/2.1.0/fleetops-2.1.0-el$major-x86_64-offline.tar.gz" .
tar -C "$release" -czf "/src/releases/2.1.0/fleetops-2.1.0-el$major-python-sources.tar.gz" dependency-sources
echo "Built FleetOps for Rocky Linux $major"
