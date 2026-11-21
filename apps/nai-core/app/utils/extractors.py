"""
nAI Core Text Extractors

Turns files into a list of *sections* (text + page number and/or heading) so chunks can
cite "page 3" or "Setup > Network", and so each chunk can carry a short contextual header.

Supported: PDF (pypdf, OCR fallback for scanned pages), DOCX, Markdown, HTML, plain
text / data / code files, and images (OCR). OCR needs ``pytesseract`` + the ``tesseract``
binary and, for PDFs, ``pypdfium2`` to render pages; it is skipped when unavailable.
"""

import hashlib
import re
import shutil
from dataclasses import dataclass, field
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .logging import get_logger

logger = get_logger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
HTML_EXTENSIONS = {".html", ".htm"}

# A PDF page with fewer extractable characters than this is treated as scanned.
SCANNED_PAGE_THRESHOLD = 25


@dataclass
class Section:
    text: str
    page: int | None = None
    heading: str | None = None


@dataclass
class Extracted:
    sections: list[Section] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(s.text for s in self.sections if s.text.strip())


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def ocr_available() -> bool:
    """True when pytesseract and the tesseract binary are installed."""
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return True


def supported_extensions(allowed: list[str], ocr_enabled: bool = True) -> set[str]:
    """Allowed extensions that can actually be extracted in this environment."""
    exts = {e.lower() for e in allowed}
    if not (ocr_enabled and ocr_available()):
        exts -= IMAGE_EXTENSIONS
    return exts


def get_file_hash(file_path: str) -> str:
    """SHA256 of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_text(file_path: str) -> tuple[str, str]:
    """Read a text file, trying common encodings. Returns (content, encoding)."""
    raw = Path(file_path).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="replace"), "utf-16"
    for encoding in ("utf-8", "cp1252"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1"), "latin-1"


def _ocr_image(image: Any, languages: str) -> str:
    import pytesseract

    try:
        return pytesseract.image_to_string(image, lang=languages)
    except pytesseract.TesseractError:
        # Requested language pack missing: fall back to tesseract's default
        return pytesseract.image_to_string(image)


# ---------------------------------------------------------------------------
# Format extractors
# ---------------------------------------------------------------------------


def extract_pdf_document(file_path: str, ocr: bool = True, ocr_languages: str = "eng") -> Extracted:
    from pypdf import PdfReader

    meta: dict[str, Any] = {"format": "pdf"}
    reader = PdfReader(file_path)
    meta["pages"] = len(reader.pages)
    if reader.metadata:
        for key in ("title", "author", "subject"):
            value = getattr(reader.metadata, key, None)
            if value:
                meta[key] = str(value)

    texts = [(page.extract_text() or "") for page in reader.pages]

    scanned = [i for i, t in enumerate(texts) if len(t.strip()) < SCANNED_PAGE_THRESHOLD]
    if scanned and ocr and ocr_available():
        try:
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(file_path)
            for i in scanned:
                image = pdf[i].render(scale=300 / 72).to_pil()
                texts[i] = _ocr_image(image, ocr_languages)
            meta["ocr_pages"] = len(scanned)
        except ImportError:
            logger.info("pypdfium2 not installed; scanned PDF pages are skipped")
        except Exception as e:
            logger.warning(f"OCR failed for {file_path}: {e}")

    sections = [Section(text=t, page=i + 1) for i, t in enumerate(texts) if t.strip()]
    return Extracted(sections=sections, metadata=meta)


def extract_docx_document(file_path: str) -> Extracted:
    import docx

    document = docx.Document(file_path)
    meta: dict[str, Any] = {"format": "docx"}
    if document.core_properties.title:
        meta["title"] = document.core_properties.title

    sections: list[Section] = []
    headings: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            sections.append(Section(text="\n".join(buffer), heading=" > ".join(headings) or None))
            buffer.clear()

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name if paragraph.style is not None else "") or ""
        match = re.match(r"Heading (\d)", style)
        if match or style == "Title":
            flush()
            level = int(match.group(1)) if match else 1
            headings[:] = [*headings[: level - 1], text]
        else:
            buffer.append(text)
    flush()

    for table in document.tables:
        rows = [" | ".join(cell.text.strip() for cell in row.cells) for row in table.rows]
        table_text = "\n".join(r for r in rows if r.strip(" |"))
        if table_text:
            sections.append(Section(text=table_text, heading="Table"))

    return Extracted(sections=sections, metadata=meta)


def extract_markdown_document(file_path: str) -> Extracted:
    content, encoding = _read_text(file_path)
    meta: dict[str, Any] = {"format": "markdown", "encoding": encoding}

    h1 = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if h1:
        meta["title"] = h1.group(1).strip()

    sections: list[Section] = []
    headings: list[str] = []
    buffer: list[str] = []
    in_code = False
    header_count = 0

    def flush() -> None:
        text = "\n".join(buffer).strip()
        if text:
            sections.append(Section(text=text, heading=" > ".join(headings) or None))
        buffer.clear()

    for line in content.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        match = None if in_code else re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            flush()
            header_count += 1
            level = len(match.group(1))
            headings[:] = [*headings[: level - 1], match.group(2).strip()]
            buffer.append(line)  # keep the heading text searchable
        else:
            buffer.append(line)
    flush()

    meta["sections"] = header_count
    return Extracted(sections=sections, metadata=meta)


class _HTMLSectionParser(HTMLParser):
    BLOCK = frozenset(
        {"p", "div", "br", "li", "tr", "section", "article", "table", "ul", "ol", "pre", "blockquote"}
    )
    SKIP = frozenset({"script", "style", "noscript", "template", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.sections: list[Section] = []
        self._headings: list[str] = []
        self._buffer: list[str] = []
        self._heading_level: int | None = None
        self._heading_text: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def _flush(self) -> None:
        text = re.sub(r"[ \t]+", " ", "".join(self._buffer))
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
        if text:
            self.sections.append(Section(text=text, heading=" > ".join(self._headings) or None))
        self._buffer = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self._heading_level = int(tag[1])
            self._heading_text = []
        elif tag in self.BLOCK:
            self._buffer.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "title":
            self._in_title = False
        elif re.fullmatch(r"h[1-6]", tag) and self._heading_level is not None:
            heading = " ".join("".join(self._heading_text).split())
            level = self._heading_level
            self._headings[:] = [*self._headings[: level - 1], heading] if heading else self._headings
            self._buffer.append(heading + "\n")
            self._heading_level = None
        elif tag in self.BLOCK:
            self._buffer.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
        elif self._heading_level is not None:
            self._heading_text.append(data)
        else:
            self._buffer.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def extract_html_document(file_path: str) -> Extracted:
    content, encoding = _read_text(file_path)
    parser = _HTMLSectionParser()
    parser.feed(content)
    parser.close()
    meta: dict[str, Any] = {"format": "html", "encoding": encoding}
    if parser.title.strip():
        meta["title"] = " ".join(parser.title.split())
    return Extracted(sections=parser.sections, metadata=meta)


def extract_plain_document(file_path: str) -> Extracted:
    content, encoding = _read_text(file_path)
    meta = {"format": "text", "encoding": encoding, "lines": content.count("\n") + 1}
    return Extracted(sections=[Section(text=content)] if content.strip() else [], metadata=meta)


def extract_image_document(file_path: str, ocr_languages: str = "eng") -> Extracted:
    meta: dict[str, Any] = {"format": "image"}
    if not ocr_available():
        meta["error"] = "OCR not available"
        return Extracted(metadata=meta)
    from PIL import Image

    with Image.open(file_path) as image:
        text = _ocr_image(image, ocr_languages)
    meta["ocr_pages"] = 1
    return Extracted(sections=[Section(text=text)] if text.strip() else [], metadata=meta)


def extract(file_path: str, ocr: bool = True, ocr_languages: str = "eng") -> Extracted:
    """Extract sections and metadata from a file, dispatching on its extension."""
    path = Path(file_path)
    ext = path.suffix.lower()

    try:
        if ext == ".pdf":
            result = extract_pdf_document(file_path, ocr=ocr, ocr_languages=ocr_languages)
        elif ext == ".docx":
            result = extract_docx_document(file_path)
        elif ext in MARKDOWN_EXTENSIONS:
            result = extract_markdown_document(file_path)
        elif ext in HTML_EXTENSIONS:
            result = extract_html_document(file_path)
        elif ext in IMAGE_EXTENSIONS:
            result = extract_image_document(file_path, ocr_languages=ocr_languages) if ocr else Extracted()
        else:
            result = extract_plain_document(file_path)
    except Exception as e:
        logger.warning(f"Extraction failed for {path.name}: {e}")
        result = Extracted(metadata={"error": str(e)})

    result.metadata.update(
        {
            "filename": path.name,
            "extension": ext,
            "size_bytes": path.stat().st_size,
            "char_count": len(result.text),
        }
    )
    return result


# ---------------------------------------------------------------------------
# Backwards-compatible (text, metadata) helpers
# ---------------------------------------------------------------------------


def extract_text(file_path: str) -> tuple[str, dict[str, Any]]:
    result = extract(file_path)
    return result.text, result.metadata


def extract_markdown(file_path: str) -> tuple[str, dict[str, Any]]:
    result = extract_markdown_document(file_path)
    return result.text, result.metadata


def extract_html(file_path: str) -> tuple[str, dict[str, Any]]:
    result = extract_html_document(file_path)
    return result.text, result.metadata


def extract_pdf(file_path: str) -> tuple[str, dict[str, Any]]:
    result = extract_pdf_document(file_path)
    return result.text, result.metadata


def extract_text_file(file_path: str) -> tuple[str, dict[str, Any]]:
    result = extract_plain_document(file_path)
    return result.text, result.metadata
