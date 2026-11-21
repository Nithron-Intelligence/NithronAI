"""
nAI Core Text Processing Utilities
Chunking, normalization, tokenization
"""

import re
from dataclasses import dataclass

import nltk

# Ensure NLTK data is available
try:
    nltk.data.find("tokenizers/punkt")
except LookupError:
    nltk.download("punkt", quiet=True)
try:
    nltk.data.find("tokenizers/punkt_tab")
except LookupError:
    try:
        nltk.download("punkt_tab", quiet=True)
    except Exception:
        pass


def normalize_text(text: str) -> str:
    """
    Normalize text for consistent processing.
    - Normalizes line endings
    - Removes control characters
    - Collapses excessive whitespace
    """
    if not text:
        return ""

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove control characters (except newline, tab)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)

    # Replace tabs with spaces
    text = text.replace("\t", "    ")

    # Collapse multiple spaces (but preserve newlines)
    text = re.sub(r" +", " ", text)

    # Collapse more than 2 consecutive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def extract_sentences(text: str) -> list[str]:
    """
    Extract sentences from text using NLTK.
    Falls back to simple regex if NLTK fails.
    """
    if not text.strip():
        return []

    try:
        from nltk.tokenize import sent_tokenize

        sentences = sent_tokenize(text)
    except Exception:
        # Fallback: simple sentence splitting
        sentences = re.split(r"(?<=[.!?])\s+", text)

    return [s.strip() for s in sentences if s.strip()]


def chunk_text(text: str, max_chars: int = 1000, overlap: int = 150) -> list[str]:
    """
    Character-based chunking with overlap.
    Simple but fast approach for basic use cases.
    """
    text = normalize_text(text)
    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = min(len(text), start + max_chars)

        # Try to break at a sentence or word boundary
        if end < len(text):
            # Look for sentence boundary
            last_period = text.rfind(". ", start, end)
            last_newline = text.rfind("\n", start, end)
            break_point = max(last_period, last_newline)

            if break_point > start + (max_chars // 2):
                end = break_point + 1
            else:
                # Fall back to word boundary
                last_space = text.rfind(" ", start + (max_chars // 2), end)
                if last_space > start:
                    end = last_space

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Next chunk starts `overlap` chars back; always move forward to avoid an infinite loop
        next_start = end - overlap if end < len(text) else end
        start = next_start if next_start > start else end

    return chunks


def chunk_text_semantic(
    text: str, max_chars: int = 1000, min_chars: int = 100, overlap_sentences: int = 1
) -> list[str]:
    """
    Semantic chunking that respects sentence boundaries.
    Creates more coherent chunks for better retrieval.
    """
    text = normalize_text(text)
    if not text:
        return []

    sentences = extract_sentences(text)
    if not sentences:
        return [text] if len(text) >= min_chars else []

    chunks = []
    current_chunk: list[str] = []
    current_length = 0

    for sentence in sentences:
        sentence_len = len(sentence)

        # If single sentence exceeds max, split it
        if sentence_len > max_chars:
            # Flush current chunk first
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_length = 0

            # Split long sentence
            sub_chunks = chunk_text(sentence, max_chars=max_chars, overlap=50)
            chunks.extend(sub_chunks)
            continue

        # Check if adding this sentence exceeds limit
        if current_length + sentence_len + 1 > max_chars and current_chunk:
            # Save current chunk
            chunks.append(" ".join(current_chunk))

            # Start new chunk with overlap
            if overlap_sentences > 0 and len(current_chunk) >= overlap_sentences:
                current_chunk = current_chunk[-overlap_sentences:]
                current_length = sum(len(s) for s in current_chunk) + len(current_chunk) - 1
            else:
                current_chunk = []
                current_length = 0

        current_chunk.append(sentence)
        current_length += sentence_len + 1

    # Don't forget the last chunk
    if current_chunk:
        chunk_text_final = " ".join(current_chunk)
        if len(chunk_text_final) >= min_chars:
            chunks.append(chunk_text_final)
        elif chunks:
            # Merge with previous chunk if too small
            chunks[-1] = chunks[-1] + " " + chunk_text_final
        else:
            chunks.append(chunk_text_final)

    return chunks


def tokenize(text: str) -> list[str]:
    """
    Tokenize text for BM25 and search. Returns lowercase word tokens.

    Compounds joined by ``-`` or ``_`` (file names like ``car_insurance_2024``,
    ``2023-tax-return``) yield the whole compound *and* its parts, so both the exact
    name and its individual words match.
    """
    if not text:
        return []
    tokens: list[str] = []
    for token in re.findall(r"[\w\-]+", text.lower()):
        token = token.strip("-_")
        if not token:
            continue
        tokens.append(token)
        if "-" in token or "_" in token:
            tokens.extend(part for part in re.split(r"[-_]+", token) if part)
    return tokens


# Function words that carry no meaning for keyword ranking (English, German, Portuguese).
# Without this, "the contract for the car" ranks any chunk full of "the"/"for" highly.
STOPWORDS = frozenset(
    """
    a an and are as at be been but by can could did do does for from had has have how i if in into is it
    its me my no not of on or our so than that the their them then there these they this to was we were
    what when where which who why will with would you your
    aber als am an auch auf aus bei bin bis bist da damit dann das dass dem den der des die dies diese
    dieser du durch ein eine einem einen einer es für hat hatte ich ihr im in ist ja kann mein mit nach
    nicht noch nur oder sich sie sind so über um und uns von vor war was wie wir wird wo zu zum zur
    ao aos as com como da das de do dos e ela ele em entre era essa este eu foi isso mais mas me na nas
    no nos o os ou para pela pelo por qual que se sem seu sua são também um uma você
    """.split()
)


def index_tokens(text: str) -> list[str]:
    """Tokens used for BM25 (``tokenize`` without stopwords)."""
    return [t for t in tokenize(text) if t not in STOPWORDS]


def highlight_matches(text: str, query: str, max_length: int = 300, context_chars: int = 50) -> str:
    """
    Create a highlighted snippet showing query matches.
    Returns the most relevant portion of text with context.
    """
    if not text or not query:
        return text[:max_length] if text else ""

    query_tokens = set(tokenize(query))
    text_lower = text.lower()

    # Find best match position
    best_pos = 0
    best_score = 0

    for token in query_tokens:
        pos = text_lower.find(token)
        if pos != -1:
            # Score based on how many query tokens are nearby
            window = text_lower[max(0, pos - 100) : pos + 100]
            score = sum(1 for t in query_tokens if t in window)
            if score > best_score:
                best_score = score
                best_pos = pos

    # Extract snippet around best position
    start = max(0, best_pos - context_chars)
    end = min(len(text), start + max_length)

    # Adjust to word boundaries
    if start > 0:
        space_pos = text.find(" ", start)
        if space_pos != -1 and space_pos < start + 20:
            start = space_pos + 1

    if end < len(text):
        space_pos = text.rfind(" ", end - 20, end)
        if space_pos != -1:
            end = space_pos

    snippet = text[start:end].strip()

    # Add ellipsis
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    return snippet


# ---------------------------------------------------------------------------
# Section-aware chunking with contextual headers
# ---------------------------------------------------------------------------


@dataclass
class ChunkDraft:
    text: str
    context: str
    page: int | None = None
    heading: str | None = None


def build_context_header(
    display_path: str,
    title: str | None = None,
    heading: str | None = None,
    page: int | None = None,
) -> str:
    """
    Short header prepended to each chunk for indexing (not shown as the chunk text).
    It tells BM25 and the embedding model which document and section a passage
    belongs to: a cheap, deterministic form of "contextual retrieval".
    """
    parts = [f"Document: {display_path}"]
    if title and title.strip() and title.strip().lower() not in display_path.lower():
        parts.append(f"Title: {title.strip()}")
    if heading:
        parts.append(f"Section: {heading}")
    if page is not None:
        parts.append(f"Page {page}")
    return " | ".join(parts)


def chunk_sections(
    sections: list,
    display_path: str,
    title: str | None = None,
    max_chars: int = 1000,
    overlap_sentences: int = 1,
) -> list[ChunkDraft]:
    """Chunk each section separately so chunks never straddle pages or headings."""
    drafts: list[ChunkDraft] = []
    for section in sections:
        for piece in chunk_text_semantic(
            section.text, max_chars=max_chars, overlap_sentences=overlap_sentences
        ):
            drafts.append(
                ChunkDraft(
                    text=piece,
                    context=build_context_header(display_path, title, section.heading, section.page),
                    page=section.page,
                    heading=section.heading,
                )
            )
    return drafts
