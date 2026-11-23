---
out: Technik/nas/NAS_maintenance_log_2025.md
format: text
language: en
kind: notes
license: CC-BY-4.0
source: written for nai-bench (fictional)
provenance: claude-authored
author: claude (claude-opus-5-5)
created: 2026-11-23
use: eval-only
---
# Home NAS maintenance log 2025

NAS: four-bay box in the hallway closet, RAID 5 over 4 × 4 TB disks, pool "tank".

| Date | What | Notes |
|---|---|---|
| 2025-01-12 | Monthly scrub | 0 errors, 6 h 40 min |
| 2025-02-09 | Monthly scrub | 0 errors |
| 2025-03-16 | Firmware update | NAS OS 3.4.2, reboot took 4 min |
| 2025-04-13 | Monthly scrub | 2 checksum errors on disk 3, repaired |
| 2025-05-04 | SMART test | disk 3 (serial ZX4K-9921) reallocated sectors: 48 |
| 2025-06-02 | Disk replaced | disk 3 replaced by Strata HDX 8 TB (serial SH8-55120), resilver 9 h 15 min |
| 2025-07-13 | Monthly scrub | 0 errors |
| 2025-08-21 | UPS battery | replaced, the UPS now holds 18 minutes at the NAS's load |

The backup to the USB disk still runs nightly at 02:30 (see backup.sh). The old disk 3 was wiped with
three passes and taken to the recycling center on 2025-06-07.
