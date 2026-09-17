# Network Device Configuration Backup Guide

Automated daily SFTP backups of running configs from Cisco switches/routers and Juniper SRX firewalls, plus a server-side cleanup script that retains one week of dailies, one month of weeklies, and twelve months of monthlies.

## Directory Layout on the SFTP Server

Each host delivers to its own folder. Under that folder are three subfolders:

```
/backups/
  <hostname>/
    daily/
    weekly/
    monthly/
```

Devices write only into `daily/`. The cleanup script promotes and prunes.

## Cisco Switches and Routers (IOS / IOS-XE)

Use **kron** — it supports a specific clock time (archive only does minute intervals, so it can't hit exactly 02:00).

```
configure terminal
!
archive
 logging size 200
!
! kron policy — the actual backup command
!
 kron policy-list ConfigBackup
  cli show running-config | redirect sftp://backupuser:backuppass@10.1.1.50//backups/$h/daily/$h_$t.cfg
 exit
!
! kron occurrence — runs every day at 02:00
!
 kron occurrence ConfigBackup at 2:00 recurring
  policy-list ConfigBackup
 exit
!
end
write memory
```

### Variables in the filename

- `$h` → hostname
- `$t` → timestamp (YYYY-MM-DD_HH-MM-SS)

Example output: `router1_2024-03-15_02-00-01.cfg`

### Verify

```
show kron schedule
show kron policy
```

### Notes

- The SFTP password sits in the running config in plain text. Use a dedicated low-privilege SFTP account.
- The redirect path uses `//backups/...` (double slash) so the absolute path is preserved on the server.
- Test the redirect manually first: `show running-config | redirect sftp://...`

## Juniper SRX Firewalls

The built-in `archival` feature only supports intervals up to 48 hours, so use **event-options** with a time-of-day trigger for a true 02:00 daily run.

```
set event-options generate-event daily-backup time-of-day "02:00:00 +0000"
set event-options policy daily-backup events daily-backup
set event-options policy daily-backup then upload filename /config/juniper.conf.gz destination sftp-server
set event-options destinations sftp-server archive-sites "sftp://backupuser@10.1.1.50/backups/$h/daily" password "backuppass"
commit
```

### Filename

The built-in archival names files automatically as:

`hostname_YYYYMMDD_HHMMSS`

Example: `srx1_20240315_020001`

### Verify

```
show event-options
show event-options policy daily-backup
```

### Notes

- Adjust the timezone offset (`+0000`) to match the device's local time.
- Password goes in quotes.
- The uploaded file is the compressed active config (`/config/juniper.conf.gz`).

## Server-Side Cleanup Script

Save as `/usr/local/bin/cleanup-backups.sh` on the SFTP server. It keeps:

- **7** daily backups
- **4** weekly backups (promoted Mondays)
- **12** monthly backups (promoted on the 1st)

```bash
#!/bin/bash
# cleanup-backups.sh — retain 7 dailies, 4 weeklies, 12 monthlies per host
# Run nightly at 03:00 via cron, after the 02:00 device backups land.

BASE="/backups"
KEEP_DAILY=7
KEEP_WEEKLY=4
KEEP_MONTHLY=12

cd "$BASE" || exit 1

for host in */; do
    host="${host%/}"
    d="$BASE/$host/daily"
    w="$BASE/$host/weekly"
    m="$BASE/$host/monthly"
    mkdir -p "$d" "$w" "$m"

    # Promote the oldest daily into weekly on Mondays
    if [ "$(date +%u)" -eq 1 ]; then
        oldest=$(ls -1t "$d" 2>/dev/null | tail -1)
        [ -n "$oldest" ] && mv "$d/$oldest" "$w/"
    fi

    # Promote the oldest weekly into monthly on the 1st
    if [ "$(date +%d)" -eq 01 ]; then
        oldest=$(ls -1t "$w" 2>/dev/null | tail -1)
        [ -n "$oldest" ] && mv "$w/$oldest" "$m/"
    fi

    # Prune: keep only the newest N in each folder
    ls -1t "$d" 2>/dev/null | tail -n +$((KEEP_DAILY + 1)) | xargs -r -I{} rm -f "$d/{}"
    ls -1t "$w" 2>/dev/null | tail -n +$((KEEP_WEEKLY + 1)) | xargs -r -I{} rm -f "$w/{}"
    ls -1t "$m" 2>/dev/null | tail -n +$((KEEP_MONTHLY + 1)) | xargs -r -I{} rm -f "$m/{}"
done
```

### Make it executable

```bash
chmod +x /usr/local/bin/cleanup-backups.sh
```

### Cron entry on the SFTP server

```cron
# Run cleanup at 03:00 every day (after 02:00 device backups)
0 3 * * * /usr/local/bin/cleanup-backups.sh >> /var/log/backup-cleanup.log 2>&1
```

Install with:

```bash
crontab -e
# paste the line above
```

## Quick Reference

| Platform | Mechanism | Schedule | Destination path |
|----------|-----------|----------|------------------|
| Cisco IOS/XE | kron | 02:00 daily | `sftp://user:pass@host//backups/$h/daily/$h_$t.cfg` |
| Juniper SRX | event-options | 02:00 daily | `sftp://user@host/backups/$h/daily` |
| SFTP server | cron + bash | 03:00 daily | `/backups/<host>/{daily,weekly,monthly}` |

## Security Reminders

- Use a dedicated, low-privilege SFTP account on the backup server.
- Restrict the SFTP user's home to `/backups` via `ForceCommand internal-sftp` and a `ChrootDirectory` in `sshd_config`.
- Rotate the SFTP password periodically; update it on every device.
- Consider key-based SFTP auth where supported to avoid plaintext passwords in configs.
