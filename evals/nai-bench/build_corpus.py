"""
nai-bench corpus builder
========================

Renders the source texts in ``corpus-src/`` into the NAS-like files in ``corpus/``
(text PDFs, "scanned" image PDFs, photographed receipts, Word files, plain files)
and writes ``corpus-manifest.json`` with every file's language, kind, license,
provenance and SHA-256.

The rendered files are committed, so you only need this script when you change a
source text. Build-time dependencies (not used by nai-core): see
``requirements-build.txt`` (reportlab, python-docx, Pillow).

Usage:
    python build_corpus.py            # rebuild corpus/ and corpus-manifest.json
    python build_corpus.py --check    # verify committed files match the manifest
    python build_corpus.py --table    # print the corpus table for README.md

Source format (``corpus-src/*.src.md``)::

    ---
    out: Versicherungen/Kfz-Versicherung_2024.pdf
    format: pdf            # pdf | scan-pdf | scan-png | docx | text
    language: de
    kind: contract
    license: CC0-1.0
    source: written for nai-bench (fictional)
    provenance: claude-authored
    ---
    # Heading
    Paragraph text, **bold** allowed.
    | table | header |
    |---|---|
    | cell | cell |
    <<<PAGE>>>             # page break (pdf, scan-pdf, docx)

``format: text`` writes the body verbatim (Markdown, code, CSV, plain text).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
SRC_DIR = HERE / "corpus-src"
OUT_DIR = HERE / "corpus"
MANIFEST = HERE / "corpus-manifest.json"

PAGE_BREAK = "<<<PAGE>>>"
FORMATS = {"pdf", "scan-pdf", "scan-png", "docx", "text"}
REQUIRED_KEYS = {"out", "format", "language", "kind", "license", "source", "provenance"}
SCAN_DPI = 150
A4_PX = (1240, 1754)  # A4 at 150 dpi
RECEIPT_WIDTH_PX = 620
FONT_CANDIDATES = (  # any TTF with Latin-1 glyphs works (umlauts, å/ä/ö, accents)
    "/usr/share/fonts/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)
FIXED_EPOCH = 1704067200  # 2024-01-01T00:00:00Z, used as the date of every rendered scan


@dataclass(frozen=True)
class SourceDoc:
    """One parsed ``*.src.md`` file."""

    src: Path
    meta: dict[str, str]
    body: str

    @property
    def out(self) -> Path:
        return OUT_DIR / self.meta["out"]

    def pages(self) -> list[list[str]]:
        """Body split into pages, each a list of lines."""
        return [page.strip("\n").splitlines() for page in self.body.split(PAGE_BREAK)]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_source(path: Path) -> SourceDoc:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not match:
        raise ValueError(f"{path.name}: missing front matter")
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.split("#", 1)[0].strip() if key.strip() != "source" else value.strip()
    missing = REQUIRED_KEYS - meta.keys()
    if missing:
        raise ValueError(f"{path.name}: missing keys {sorted(missing)}")
    if meta["format"] not in FORMATS:
        raise ValueError(f"{path.name}: unknown format {meta['format']!r}")
    return SourceDoc(src=path, meta=meta, body=match.group(2))


def split_blocks(lines: list[str]) -> list[tuple[str, object]]:
    """Group lines into ("h1"|"h2"|"p", text) and ("table", rows) blocks."""
    blocks: list[tuple[str, object]] = []
    para: list[str] = []
    table: list[list[str]] = []

    def flush() -> None:
        if para:
            blocks.append(("p", " ".join(para)))
            para.clear()
        if table:
            blocks.append(("table", [row[:] for row in table]))
            table.clear()

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("|"):
            if para:
                blocks.append(("p", " ".join(para)))
                para.clear()
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                table.append(cells)
            continue
        if table:
            blocks.append(("table", [row[:] for row in table]))
            table.clear()
        if not line.strip():
            flush()
        elif line.startswith("## "):
            flush()
            blocks.append(("h2", line[3:].strip()))
        elif line.startswith("# "):
            flush()
            blocks.append(("h1", line[2:].strip()))
        else:
            para.append(line.strip())
    flush()
    return blocks


def plain(text: str) -> str:
    return text.replace("**", "")


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_text(doc: SourceDoc) -> None:
    doc.out.write_text(doc.body.lstrip("\n"), encoding="utf-8")


def render_pdf(doc: SourceDoc) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()

    def rich(text: str) -> str:
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(text))

    story: list[Any] = []
    for index, page in enumerate(doc.pages()):
        if index:
            story.append(PageBreak())
        for kind, value in split_blocks(page):
            if kind == "table":
                rows = [[Paragraph(rich(c), styles["BodyText"]) for c in row] for row in value]  # type: ignore[attr-defined]
                table = Table(rows, hAlign="LEFT")
                table.setStyle(
                    TableStyle(
                        [
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ]
                    )
                )
                story += [table, Spacer(1, 4 * mm)]
            else:
                style = {"h1": "Heading1", "h2": "Heading2", "p": "BodyText"}[kind]
                story.append(Paragraph(rich(str(value)), styles[style]))
    pdf = SimpleDocTemplate(
        str(doc.out),
        pagesize=A4,
        title=doc.meta.get("title", doc.out.stem),
        author="nai-bench",
        invariant=1,  # no timestamps or random IDs: byte-identical rebuilds
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    pdf.build(story)


def render_docx(doc: SourceDoc) -> None:
    import docx

    document = docx.Document()
    document.core_properties.author = "nai-bench"
    document.core_properties.title = doc.meta.get("title", doc.out.stem)
    for index, page in enumerate(doc.pages()):
        if index:
            document.add_page_break()
        for kind, value in split_blocks(page):
            if kind == "table":
                rows: list[list[str]] = value  # type: ignore[assignment]
                table = document.add_table(rows=len(rows), cols=len(rows[0]))
                table.style = "Table Grid"
                for r, row in enumerate(rows):
                    for c, cell in enumerate(row):
                        table.cell(r, c).text = plain(cell)
            elif kind == "h1":
                document.add_heading(plain(str(value)), level=1)
            elif kind == "h2":
                document.add_heading(plain(str(value)), level=2)
            else:
                document.add_paragraph(plain(str(value)))
    document.save(str(doc.out))
    _normalize_docx(doc.out)


def _normalize_docx(path: Path) -> None:
    """Rewrite the .docx zip with fixed timestamps so rebuilds are byte-identical."""
    import zipfile

    with zipfile.ZipFile(path) as zin:
        items = [(info.filename, zin.read(info.filename)) for info in zin.infolist()]
    fixed = []
    for name, data in items:
        if name == "docProps/core.xml":
            data = re.sub(
                rb"<dcterms:(created|modified)([^>]*)>[^<]*<", rb"<dcterms:\1\2>2024-01-01T00:00:00Z<", data
            )
        fixed.append((name, data))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in fixed:
            info = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(info, data)


def scan_font() -> str:
    """First available TTF from FONT_CANDIDATES (or $NAI_BENCH_FONT)."""
    import os

    for candidate in (os.environ.get("NAI_BENCH_FONT"), *FONT_CANDIDATES):
        if candidate and Path(candidate).is_file():
            return candidate
    raise FileNotFoundError("no TTF font with Latin-1 glyphs found; set NAI_BENCH_FONT=/path/to/font.ttf")


def _speckle(value: Any) -> Any:
    """Map Gaussian noise to light speckles."""
    return 246 if value > 40 else 200


def _scan_page(lines: list[str], width: int, seed: int, font_size: int = 24) -> object:
    """Render lines like a slightly crooked, grey, noisy scan."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    font_path = scan_font()
    font = ImageFont.truetype(font_path, font_size)
    bold = ImageFont.truetype(font_path, int(font_size * 1.35))
    margin = int(width * 0.08)
    line_h = int(font_size * 1.55)
    blocks = split_blocks(lines)

    # Measure height first (receipts are as long as their content).
    est_lines = 0
    for kind, value in blocks:
        est_lines += len(value) + 1 if kind == "table" else 2 + len(str(value)) // 60  # type: ignore[arg-type]
    height = A4_PX[1] if width == A4_PX[0] else max(900, margin * 2 + est_lines * line_h)

    img = Image.new("L", (width, height), 246)
    draw = ImageDraw.Draw(img)
    y = margin
    max_px = width - 2 * margin
    for kind, value in blocks:
        if kind == "table":
            rows = [[plain(c) for c in row] for row in value]  # type: ignore[attr-defined]
            cols = len(rows[0])
            widths = [max(font.getlength(r[c]) for r in rows if c < len(r)) + 24 for c in range(cols)]
            scale = min(1.0, max_px / sum(widths))
            xs = [margin + int(sum(widths[:c]) * scale) for c in range(cols)]
            for row in rows:
                for c, cell in enumerate(row):
                    draw.text((xs[c], y), cell, font=font, fill=35)
                y += line_h
            y += line_h // 2
            continue
        text = plain(str(value))
        use = bold if kind in ("h1", "h2") else font
        words, line = text.split(), ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if use.getlength(candidate) > max_px and line:
                draw.text((margin, y), line, font=use, fill=30)
                y += int(line_h * (1.3 if use is bold else 1))
                line = word
            else:
                line = candidate
        if line:
            draw.text((margin, y), line, font=use, fill=30)
            y += int(line_h * (1.3 if use is bold else 1))
        y += line_h // 2

    rng = random.Random(seed)
    img = img.rotate(rng.uniform(-0.8, 0.8), resample=Image.Resampling.BICUBIC, fillcolor=246)
    noise = Image.frombytes("L", img.size, rng.randbytes(img.size[0] * img.size[1]))
    img = Image.blend(img, noise.point(_speckle), 0.08)
    return img.filter(ImageFilter.GaussianBlur(0.6)).convert("L")


def render_scan_pdf(doc: SourceDoc) -> None:
    seed = int(hashlib.sha256(doc.meta["out"].encode()).hexdigest()[:8], 16)
    pages = [_scan_page(lines, A4_PX[0], seed + i) for i, lines in enumerate(doc.pages())]
    first, rest = pages[0], pages[1:]
    fixed = time.gmtime(FIXED_EPOCH)  # byte-identical rebuilds
    first.save(  # type: ignore[attr-defined]
        str(doc.out),
        "PDF",
        resolution=SCAN_DPI,
        save_all=True,
        append_images=rest,
        title=doc.meta.get("title", doc.out.stem),
        author="nai-bench",
        creationDate=fixed,
        modDate=fixed,
    )


def render_scan_png(doc: SourceDoc) -> None:
    seed = int(hashlib.sha256(doc.meta["out"].encode()).hexdigest()[:8], 16)
    image = _scan_page(doc.pages()[0], RECEIPT_WIDTH_PX, seed, font_size=22)
    image.save(str(doc.out), "PNG", optimize=True)  # type: ignore[attr-defined]


RENDERERS = {
    "text": render_text,
    "pdf": render_pdf,
    "scan-pdf": render_scan_pdf,
    "scan-png": render_scan_png,
    "docx": render_docx,
}


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_entry(doc: SourceDoc) -> dict[str, object]:
    pages = len(doc.pages()) if doc.meta["format"] in ("pdf", "scan-pdf", "docx") else None
    return {
        "file": doc.meta["out"],
        "source_text": f"corpus-src/{doc.src.name}",
        "format": doc.meta["format"],
        "language": doc.meta["language"],
        "kind": doc.meta["kind"],
        "pages": pages,
        "license": doc.meta["license"],
        "source": doc.meta["source"],
        "source_url": doc.meta.get("source_url"),
        "provenance": doc.meta["provenance"],
        "sha256": sha256(doc.out),
    }


def load_sources() -> list[SourceDoc]:
    docs = [parse_source(p) for p in sorted(SRC_DIR.glob("*.src.md"))]
    outs = [d.meta["out"] for d in docs]
    dupes = {o for o in outs if outs.count(o) > 1}
    if dupes:
        raise ValueError(f"duplicate output paths: {sorted(dupes)}")
    return docs


def build() -> None:
    docs = load_sources()
    for doc in docs:
        doc.out.parent.mkdir(parents=True, exist_ok=True)
        RENDERERS[doc.meta["format"]](doc)
        print(f"built {doc.meta['out']}")
    expected = {d.out.resolve() for d in docs}
    stale = [p for p in OUT_DIR.rglob("*") if p.is_file() and p.resolve() not in expected]
    for path in stale:
        print(f"warning: {path.relative_to(OUT_DIR)} has no source text", file=sys.stderr)
    entries = [manifest_entry(d) for d in docs]
    MANIFEST.write_text(json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST.name} ({len(entries)} files)")


def check() -> int:
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    problems = 0
    for entry in entries:
        path = OUT_DIR / entry["file"]
        if not path.is_file():
            print(f"missing: {entry['file']}")
            problems += 1
        elif sha256(path) != entry["sha256"]:
            print(f"changed: {entry['file']}")
            problems += 1
    listed = {e["file"] for e in entries}
    for path in OUT_DIR.rglob("*"):
        if path.is_file() and str(path.relative_to(OUT_DIR)) not in listed:
            print(f"not in manifest: {path.relative_to(OUT_DIR)}")
            problems += 1
    print("corpus OK" if not problems else f"{problems} problem(s)")
    return 1 if problems else 0


def table() -> None:
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print("| File | Lang | Kind | Format | License | Source |")
    print("|---|---|---|---|---|---|")
    for e in sorted(entries, key=lambda entry: entry["file"]):
        source = e["source"] if not e["source_url"] else f"[{e['source']}]({e['source_url']})"
        print(
            f"| `{e['file']}` | {e['language']} | {e['kind']} | {e['format']} | {e['license']} | {source} |"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or check the nai-bench corpus")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="verify corpus/ against the manifest")
    group.add_argument("--table", action="store_true", help="print the README corpus table")
    args = parser.parse_args()
    if args.check:
        return check()
    if args.table:
        table()
        return 0
    build()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
