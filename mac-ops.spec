%define name mac-ops
%define version 2.0.0
%define release 1
%define summary Maytag Admin Console - Enterprise Infrastructure Management Platform
%define license MIT

Summary: %{summary}
Name: %{name}
Version: %{version}
Release: %{release}%{?dist}
License: %{license}
URL: https://github.com/your-org/mac-ops
BuildArch: noarch

Source0: %{name}-%{version}.tar.gz

# Build requirements
BuildRequires: python3 >= 3.9
BuildRequires: python3-pip

# Runtime requirements (RPM packages)
Requires: python3 >= 3.9
Requires: python3-pyyaml
Requires: python3-cryptography
Requires: ansible-core >= 2.15
Requires: openldap-clients
Requires: openssh-clients
Requires(pre): /usr/sbin/useradd
Requires(postun): /usr/sbin/userdel
Requires(post): systemd

%description
Maytag Admin Console (MAC) is a unified infrastructure management platform with 
enterprise-grade authentication and a pluggable tool architecture. It provides 
comprehensive admin interface with built-in tools for infrastructure automation, 
system administration, and cloud operations.

Features:
- Enterprise authentication (local users, LDAP/FreeIPA, RBAC)
- Secrets vault with fine-grained access control
- Pluggable tool framework for extensibility
- Comprehensive audit logging
- Beautiful web-based admin dashboard
- Secure Ansible playbook execution and scheduling
- Web-based SSH terminal
- Host reachability audits

%prep
%setup -q -n mac-ops

%build
# No build needed for Python application
# Just verify requirements can be resolved
python3 -m pip install --dry-run -r backend/requirements.txt 2>&1 | head -20 || true

%install
# Create directory structure
mkdir -p %{buildroot}/opt/mac-ops/backend
mkdir -p %{buildroot}/opt/mac-ops/frontend
mkdir -p %{buildroot}/opt/mac-ops/ansible/{playbooks,inventory}
mkdir -p %{buildroot}/opt/mac-ops/reports
mkdir -p %{buildroot}/opt/mac-ops/logs
mkdir -p %{buildroot}/opt/mac-ops/pip-packages
mkdir -p %{buildroot}/var/lib/mac-ops
mkdir -p %{buildroot}/etc/mac-ops
mkdir -p %{buildroot}/usr/lib/systemd/system
mkdir -p %{buildroot}/usr/local/bin

# Copy application files
cp -r backend/* %{buildroot}/opt/mac-ops/backend/
cp -r frontend/* %{buildroot}/opt/mac-ops/frontend/
cp -r ansible/* %{buildroot}/opt/mac-ops/ansible/
cp -r docs %{buildroot}/opt/mac-ops/ || true
cp install.sh %{buildroot}/opt/mac-ops/ || true
cp prep-airgap.sh %{buildroot}/opt/mac-ops/ || true
cp LICENSE %{buildroot}/opt/mac-ops/ || true
cp README.md %{buildroot}/opt/mac-ops/ || true
cp DEPLOYMENT.md %{buildroot}/opt/mac-ops/ || true

# Copy systemd service file
install -m 0644 mac-ops.service %{buildroot}/usr/lib/systemd/system/ || echo "Service file not yet created"

# Create launcher script
install -m 0755 /dev/stdin %{buildroot}/usr/local/bin/mac-ops << 'EOF'
#!/bin/bash
exec /home/macops/.venv/bin/python /opt/mac-ops/backend/app.py "$@"
EOF

%pre
# Create service user if not exists
getent passwd macops > /dev/null 2>&1 || \
  useradd -r -m -d /home/macops -s /bin/bash -c "MAC Ops Service Account" macops

%post
# Set permissions
chown -R macops:macops /opt/mac-ops
chown -R macops:macops /var/lib/mac-ops

# Create virtual environment
sudo -u macops python3 -m venv /home/macops/.venv || true

# Install Python dependencies
sudo -u macops /home/macops/.venv/bin/pip install --upgrade pip setuptools wheel
sudo -u macops /home/macops/.venv/bin/pip install -r /opt/mac-ops/backend/requirements.txt

# Enable and start service
%systemd_post mac-ops.service

%preun
# Stop service before uninstall
%systemd_preun mac-ops.service

%postun
# Clean up user on complete removal
if [ $1 -eq 0 ]; then
  userdel -r macops 2>/dev/null || true
fi
%systemd_postun_with_restart mac-ops.service

%files
%defattr(-, macops, macops, 0755)

/opt/mac-ops/
/var/lib/mac-ops/

%defattr(-, root, root, 0755)
/usr/lib/systemd/system/mac-ops.service
/usr/local/bin/mac-ops

%dir /etc/mac-ops

%doc
/opt/mac-ops/README.md
/opt/mac-ops/DEPLOYMENT.md
/opt/mac-ops/LICENSE

%changelog
* Sat Apr 05 2026 Mike Anderson <mike@example.com> - 2.0.0-1
- Initial RPM package release
- Enterprise authentication with LDAP/FreeIPA support
- Secrets vault with encrypted storage
- Web-based SSH terminal and admin dashboard
- Comprehensive audit logging
