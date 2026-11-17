%global debug_package %{nil}
%global __os_install_post %{nil}
Name: fleetops
Version: 2.1.0
Release: 2%{?dist}
Summary: Fleet infrastructure automation and Ansible operations console
License: MIT
URL: https://github.com/mike0615/mac-ops
Source0: %{name}-%{version}.tar.gz
BuildArch: x86_64
Requires: python3
Requires: python3-pip
Requires: openssh-clients
Requires: iputils
Requires: openldap
Requires: systemd
Requires: util-linux
Requires(pre): shadow-utils
Requires(post): /usr/sbin/runuser
Recommends: xdg-utils

%description
FleetOps provides a locally hosted interface for Ansible playbooks, inventory,
schedules, reports, host checks, SSH access, accounts and encrypted secrets.
Python dependencies and a private Ansible runtime are bundled for offline setup.
Help and About pages are embedded. No internet access is needed to operate.

%prep
%setup -q

%build
# Wheels and the resolved requirements lock were prepared on the matching OS.
test -s requirements.lock
test -d wheels

%install
install -d %{buildroot}/opt/fleetops
cp -a backend frontend ansible docs wheels requirements.lock VERSION HELP.md LICENSE README.md RELEASE_NOTES.md %{buildroot}/opt/fleetops/
install -m 0755 packaging/setup-runtime.sh %{buildroot}/opt/fleetops/setup-runtime.sh
install -D -m 0755 bin/fleetops %{buildroot}/usr/bin/fleetops
install -D -m 0644 packaging/fleetops.service %{buildroot}/usr/lib/systemd/system/fleetops.service
install -d %{buildroot}/etc/fleetops
install -m 0640 packaging/fleetops.env packaging/fleetops.conf packaging/ansible.cfg %{buildroot}/etc/fleetops/
install -D -m 0644 packaging/fleetops.desktop %{buildroot}/usr/share/applications/fleetops.desktop
install -D -m 0644 frontend/vendor/fleetops.svg %{buildroot}/usr/share/icons/hicolor/scalable/apps/fleetops.svg
find %{buildroot}/opt/fleetops -type f -exec chmod 0644 {} +
chmod 0755 %{buildroot}/opt/fleetops/setup-runtime.sh

%pre
getent group fleetops >/dev/null || groupadd -r fleetops
getent passwd fleetops >/dev/null || useradd -r -g fleetops -d /var/lib/fleetops -s /sbin/nologin -c 'FleetOps service' fleetops

%post
/opt/fleetops/setup-runtime.sh || exit 1
systemctl daemon-reload >/dev/null 2>&1 || :
echo 'FleetOps installed. Create an administrator: runuser -u fleetops -- fleetops manage create-admin'
echo 'Then enable the service: systemctl enable --now fleetops'

%preun
if [ "$1" -eq 0 ]; then
    systemctl disable --now fleetops.service >/dev/null 2>&1 || :
fi

%postun
systemctl daemon-reload >/dev/null 2>&1 || :
if [ "$1" -ge 1 ]; then
    systemctl try-restart fleetops.service >/dev/null 2>&1 || :
fi

%files
%license LICENSE
/opt/fleetops/
/usr/bin/fleetops
/usr/lib/systemd/system/fleetops.service
/usr/share/applications/fleetops.desktop
/usr/share/icons/hicolor/scalable/apps/fleetops.svg
%dir %attr(0750,root,fleetops) /etc/fleetops
%config(noreplace) %attr(0640,root,fleetops) /etc/fleetops/fleetops.conf
%config(noreplace) %attr(0640,root,fleetops) /etc/fleetops/fleetops.env
%config(noreplace) %attr(0640,root,fleetops) /etc/fleetops/ansible.cfg

%changelog
* Mon Nov 16 2026 Mike Anderson <mike@andersoncomputer.us> - 2.1.0-2
- Complete encrypted local SSH credentials, ownership checks and persistent vault initialization
* Mon Nov 16 2026 Mike Anderson <mike@andersoncomputer.us> - 2.1.0-1
- Rename MAC Ops to FleetOps; embedded Help and About
- Bundle offline Python and Ansible runtime; preserve writable data on upgrades
