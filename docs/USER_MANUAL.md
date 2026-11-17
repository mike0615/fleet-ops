# FleetOps user manual

Version 2.1.0. The embedded [Help](../HELP.md) is the task reference.

## Normal workflow

Log in, check inventory, edit and save a playbook, validate syntax, review its
target scope, run it and inspect the recap and detailed log. Report-generating
playbooks publish JSON reports for the Reports view. Dashboard counts summarize
server-side files and schedules rather than live host state.

## Files and templates

Playbooks are YAML under `/var/lib/fleetops/ansible/playbooks`; inventory files
are INI or YAML under the inventory directory. The editor supports subdirectories,
starter templates and upload. Avoid overlapping edits: the original application
does not provide revision locking. Maintain important automation in version control.
Deletion is immediate; use backups to recover deleted files.

## Supplied automation

System inventory, security audit and disk-space reporting collect host information.
User creation, password changes, SSH key deployment, FreeIPA enrollment, service
control, reboot and maintenance playbooks modify targets. Review every supplied
playbook and group variable before use. Enrollment values are examples and must
be replaced. Maintenance can update packages and reboot-related tasks can interrupt
services. The initial FleetOps inventory contains no production hosts.

## Scheduling and execution

Five-field schedules use server time and persist in `schedules.json`. Pausing
disables a future invocation; it does not terminate an already running command.
Each playbook subprocess times out after 900 seconds. Ad-hoc module execution
times out after 60 seconds. FleetOps is a single-process console; do not launch
multiple service workers against the same schedules file.

## Roles

Administrators manage accounts, roles, secrets and audit records. Operators can
run automation; viewers can read supported views. Operational APIs require login.
Retained MAC Ops permission names are listed in the source role definitions.
API authorization currently groups general operational writes under the
`ansible:execute_playbook` permission; it is not a per-file policy system.

## Reports and exports

Reporting playbooks determine the report schema. Review timestamps and host names
before making decisions. Host Checker CSV is a reachability snapshot. Logs and
reports can contain sensitive host and account details; use approved storage and
retention practices. There is no automatic central log shipping.

## Sessions

F1 opens local help from every page. Help and About links are also available in
the floating documentation controls. The SSH console uses the logged-in browser
session; close terminal windows and log out when work is complete. Browser
preferences such as theme are kept locally and are not configuration backups.
