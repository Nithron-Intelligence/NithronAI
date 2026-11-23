"""Sort photos from the phone upload folder into Fotos/YYYY/MM by their EXIF date.

Photos without an EXIF date go to Fotos/unsorted. Files smaller than 50 KB
(thumbnails, messenger previews) are skipped. Duplicates (same name and size)
are not copied again.
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

UPLOADS = Path("/mnt/shares/Familie/Handy-Upload")
TARGET = Path("/mnt/shares/Familie/Fotos")
MIN_SIZE_BYTES = 50 * 1024
EXIF_DATETIME_ORIGINAL = 36867
EXTENSIONS = {".jpg", ".jpeg", ".heic", ".png"}


def taken_at(path: Path) -> datetime | None:
    try:
        with Image.open(path) as img:
            raw = img.getexif().get_ifd(0x8769).get(EXIF_DATETIME_ORIGINAL)
    except OSError:
        return None
    if not raw:
        return None
    return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")


def destination(path: Path) -> Path:
    when = taken_at(path)
    folder = TARGET / "unsorted" if when is None else TARGET / f"{when:%Y}" / f"{when:%m}"
    return folder / path.name


def main() -> int:
    moved = 0
    for path in sorted(UPLOADS.iterdir()):
        if path.suffix.lower() not in EXTENSIONS or path.stat().st_size < MIN_SIZE_BYTES:
            continue
        target = destination(path)
        if target.exists() and target.stat().st_size == path.stat().st_size:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        moved += 1
    print(f"sorted {moved} photos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
