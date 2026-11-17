# Migrating MAC Ops to FleetOps

FleetOps uses a new service name, account, data location and persistent keys.
It intentionally does not stop, remove or overwrite an existing MAC Ops install.

1. Record the installed MAC Ops version, paths, service environment and database.
2. Pause schedules and stop `mac-ops` before copying mutable state.
3. Back up `/opt/mac-ops`, `/var/lib/mac-ops`, `/etc/mac-ops` and the original
   service account's SSH directory, including encryption/signing keys.
4. Install FleetOps with its complete offline bundle. Keep FleetOps stopped.
5. Copy operator playbooks, inventory, group variables and roles into
   `/var/lib/fleetops/ansible`. Copy reports, logs and schedules.json separately.
6. Copy the compatible SQLite database to `/var/lib/fleetops/fleetops.db`.
   The inherited schema is unchanged; test the copied database on a staging host.
7. To retain vault secrets, place the original Fernet key in
   `/etc/fleetops/vault.key`. If the old application used an ephemeral key and
   it was not retained, its existing ciphertext cannot be recovered.
8. Review absolute paths in playbooks, inventories and schedules; change
   `/opt/mac-ops` paths to the appropriate new state path. Review local report
   destinations. Do not blindly replace addresses or task values.
9. Restore state ownership to fleetops:fleetops and private permissions. Keys
   under /etc/fleetops must remain root:fleetops 0640.
10. Reconfigure LDAP and internal CA trust. Verify login and vault decryption,
    compare inventory and schedules, then run an approved harmless playbook.
11. Start FleetOps. Enable schedules only after validation. Keep the original
    backup and application stopped until your rollback period expires.

Rollback: stop FleetOps, restore the original MAC Ops state and keys as a
consistent set, then start its original service. Do not run both schedulers
against the same hosts during migration or rollback.
