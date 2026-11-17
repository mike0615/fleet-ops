#!/bin/bash
# Run inside the installed, network-disabled test container as root.
set -euo pipefail
major=${1:?OS major}
runuser -u fleetops -- /opt/fleetops/venv/bin/python /src/tests/runtime_smoke.py
mkdir -p /usr/local/bin
ln -s /opt/fleetops/venv/bin/ansible-playbook /usr/local/bin/ansible-playbook
echo preserve-me > /var/lib/fleetops/persistence-sentinel
echo '# retain this local setting' >> /etc/fleetops/fleetops.conf
sha256sum /etc/fleetops/session.key /etc/fleetops/vault.key /var/lib/fleetops/persistence-sentinel /etc/fleetops/fleetops.conf > /tmp/fleetops-before.sha256
cd "/src/releases/2.1.0/el$major"
bash install.sh
rpm -Uvh --replacepkgs "rpms/fleetops-2.1.0-2.el$major.x86_64.rpm"
sha256sum --check /tmp/fleetops-before.sha256
runuser -u fleetops -- /opt/fleetops/venv/bin/python /opt/fleetops/backend/app.py > /tmp/fleetops-live.log 2>&1 &
process=$!
trap 'kill "$process" 2>/dev/null || true' EXIT
for attempt in {1..20}; do
  if curl -fsS http://127.0.0.1:5000/healthz > /tmp/fleetops-health.json; then break; fi
  sleep 0.5
done
grep -q FleetOps /tmp/fleetops-health.json
kill "$process" 2>/dev/null || true
wait "$process" || true
trap - EXIT
rpm -e fleetops
sha256sum --check <(head -n 3 /tmp/fleetops-before.sha256)
[[ -f /etc/fleetops/fleetops.conf.rpmsave ]]
expected=$(tail -n 1 /tmp/fleetops-before.sha256 | cut -d ' ' -f 1)
actual=$(sha256sum /etc/fleetops/fleetops.conf.rpmsave | cut -d ' ' -f 1)
[[ $expected == "$actual" ]]
echo 'PASS: unprivileged runtime, Ansible-present installer, reinstall persistence, live server and uninstall retention'
