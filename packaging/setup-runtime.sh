#!/bin/bash
# Called by the RPM after dependency resolution; never accesses a network.
set -euo pipefail
APP=/opt/fleetops
DATA=/var/lib/fleetops
install -d -m 0750 -o root -g fleetops /etc/fleetops
install -d -m 0700 -o fleetops -g fleetops "$DATA"
for name in session vault; do
  if [[ ! -s /etc/fleetops/$name.key ]]; then
    if [[ $name == vault && -f "$DATA/fleetops.db" ]]; then
      python3 - "$DATA/fleetops.db" <<'PY'
import sqlite3, sys
connection = sqlite3.connect('file:' + sys.argv[1] + '?mode=ro', uri=True)
for table in ('secret', 'ssh_credential'):
    exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if exists and connection.execute('SELECT 1 FROM ' + table + ' LIMIT 1').fetchone():
        sys.exit('Vault key missing with saved secrets present. Restore the original key before upgrading.')
PY
    fi
    umask 077
    if [[ $name == session ]]; then
      python3 -c 'import secrets; print(secrets.token_hex(32))' > /etc/fleetops/session.key
    else
      python3 -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())' > /etc/fleetops/vault.key
    fi
  fi
  chown root:fleetops "/etc/fleetops/$name.key"
  chmod 0640 "/etc/fleetops/$name.key"
done
umask 022
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --no-index --only-binary=:all: --find-links="$APP/wheels" -r "$APP/requirements.lock"
"$APP/venv/bin/pip" check
"$APP/venv/bin/ansible" --version > /dev/null
"$APP/venv/bin/ansible-playbook" --version > /dev/null
install -d -m 0700 -o fleetops -g fleetops "$DATA/ansible" "$DATA/ansible/roles" "$DATA/reports" "$DATA/logs" "$DATA/.ssh"
for kind in playbooks inventory group_vars; do
  # Only seed a new install; upgrades never replace operator data.
  if [[ ! -d "$DATA/ansible/$kind" ]]; then
    cp -a "$APP/ansible/$kind" "$DATA/ansible/$kind"
    chown -R fleetops:fleetops "$DATA/ansible/$kind"
    chmod -R go-rwx "$DATA/ansible/$kind"
  fi
done
runuser -u fleetops -- env HOME="$DATA" "$APP/venv/bin/python" "$APP/backend/manage.py" init-db
if [[ ! -f "$DATA/.ssh/id_ed25519" ]]; then
  runuser -u fleetops -- ssh-keygen -q -t ed25519 -N '' -f "$DATA/.ssh/id_ed25519" -C 'FleetOps automation'
fi
