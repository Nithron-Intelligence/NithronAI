---
out: Technik/homelab/backup.sh
format: text
language: en
kind: code
license: CC0-1.0
source: written for nai-bench
provenance: claude-authored
---
#!/usr/bin/env bash
# Nightly backup of the NAS shares to the external USB disk with restic.
# Runs from cron every night at 02:30:
#   30 2 * * * /srv/scripts/backup.sh >> /var/log/backup.log 2>&1
# The USB disk must be mounted at /mnt/usb-backup. Nothing is copied off-site.
set -euo pipefail

export RESTIC_REPOSITORY=/mnt/usb-backup/restic
export RESTIC_PASSWORD_FILE=/root/.restic-password

SOURCES=(/srv/nextcloud/data /srv/paperless/data /mnt/shares/Familie /mnt/shares/Nordlicht)

if ! mountpoint -q /mnt/usb-backup; then
    echo "$(date -Is) USB backup disk not mounted, skipping" >&2
    exit 1
fi

restic backup "${SOURCES[@]}" \
    --exclude '*/Downloads/*' \
    --exclude '*.tmp' \
    --tag nightly

# Keep 7 daily, 4 weekly and 6 monthly snapshots; delete the rest.
restic forget --prune --keep-daily 7 --keep-weekly 4 --keep-monthly 6

# Check 5 % of the repository data every Sunday.
if [ "$(date +%u)" -eq 7 ]; then
    restic check --read-data-subset=5%
fi

echo "$(date -Is) backup finished"
