"""
nai-bench shared library
========================

Loads and validates the nai-bench questions and corpus manifest, normalizes text for
fact matching, detects answer language and refusals, computes retrieval metrics, and
talks to a running nAI server. Used by ``retrieval/eval_retrieval.py``,
``answers/eval_answers.py`` and ``run_baseline.py``.

Only needs the standard library and ``httpx`` (already a nAI test dependency).
"""

from __future__ import annotations

import json
import math
import re
import time
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

EVALS_DIR = Path(__file__).resolve().parent
BENCH_DIR = EVALS_DIR / "nai-bench"
QUESTIONS_FILE = BENCH_DIR / "questions.jsonl"
MANIFEST_FILE = BENCH_DIR / "corpus-manifest.json"
CORPUS_DIR = BENCH_DIR / "corpus"

CATEGORIES = ("lookup", "multi-hop", "cross-lingual", "table/scan-OCR", "unanswerable")
DIFFICULTIES = ("easy", "medium", "hard")
LANGUAGES = ("en", "de", "sv", "fr", "pt")
MIN_UNANSWERABLE = 10
# Human review (V1_PLAN.md): only accepted or fixed items count toward published numbers.
REVIEW_STATUSES = ("unreviewed", "accepted", "fixed", "rejected")
REVIEWED = ("accepted", "fixed")
SOURCE_NAME = "nai-bench"


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldSource:
    file: str
    page: int | None = None
    section: str | None = None


@dataclass(frozen=True)
class BenchItem:
    id: str
    question: str
    language: str
    gold_answer: str | None
    gold_facts: tuple[str, ...]
    gold_sources: tuple[GoldSource, ...]
    category: str
    difficulty: str
    provenance: dict[str, Any]
    notes: str | None = None
    forbidden_facts: tuple[str, ...] = ()
    review_status: str = "unreviewed"
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    review_note: str | None = None

    @property
    def reviewed(self) -> bool:
        return self.review_status in REVIEWED

    @property
    def answerable(self) -> bool:
        return self.category != "unanswerable"

    @property
    def gold_files(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(s.file for s in self.gold_sources))


def _item_from_json(raw: dict[str, Any]) -> BenchItem:
    return BenchItem(
        id=raw["id"],
        question=raw["question"],
        language=raw["language"],
        gold_answer=raw.get("gold_answer"),
        gold_facts=tuple(raw.get("gold_facts", [])),
        gold_sources=tuple(GoldSource(**s) for s in raw.get("gold_sources", [])),
        category=raw["category"],
        difficulty=raw["difficulty"],
        provenance=raw.get("provenance", {}),
        notes=raw.get("notes"),
        forbidden_facts=tuple(raw.get("forbidden_facts", [])),
        review_status=raw.get("review_status", "unreviewed"),
        reviewed_by=raw.get("reviewed_by"),
        reviewed_at=raw.get("reviewed_at"),
        review_note=raw.get("review_note"),
    )


def load_all_items(path: Path = QUESTIONS_FILE) -> list[BenchItem]:
    """Every item in the file, including rejected ones (for the review tool). Raises if invalid."""
    raw_items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    items = [_item_from_json(raw) for raw in raw_items]
    errors = validate([i for i in items if i.review_status != "rejected"]) + validate_review(items)
    if errors:
        raise ValueError("invalid nai-bench questions:\n  " + "\n  ".join(errors))
    return items


def load_items(path: Path = QUESTIONS_FILE, reviewed_only: bool = False) -> list[BenchItem]:
    """Items to evaluate: rejected items are always dropped; ``reviewed_only`` keeps accepted/fixed ones."""
    items = [i for i in load_all_items(path) if i.review_status != "rejected"]
    return [i for i in items if i.reviewed] if reviewed_only else items


def review_summary(path: Path = QUESTIONS_FILE) -> dict[str, int]:
    """Counts per review status, plus 'total' and 'reviewed' (accepted + fixed)."""
    items = load_all_items(path)
    counts = {status: sum(1 for i in items if i.review_status == status) for status in REVIEW_STATUSES}
    counts["total"] = len(items)
    counts["reviewed"] = counts["accepted"] + counts["fixed"]
    return counts


def validate_review(items: list[BenchItem]) -> list[str]:
    """Review fields: known status; anything but 'unreviewed' names the reviewer and date."""
    errors = []
    for item in items:
        if item.review_status not in REVIEW_STATUSES:
            errors.append(f"{item.id}: unknown review_status {item.review_status!r}")
        elif item.review_status != "unreviewed" and not (item.reviewed_by and item.reviewed_at):
            errors.append(
                f"{item.id}: review_status {item.review_status!r} needs reviewed_by and reviewed_at"
            )
        if item.review_status == "rejected" and not item.review_note:
            errors.append(f"{item.id}: a rejected item needs a review_note saying why")
    return errors


def load_manifest(path: Path = MANIFEST_FILE) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return data


def validate(items: list[BenchItem], manifest: list[dict[str, Any]] | None = None) -> list[str]:
    """Schema and consistency checks; returns a list of problems (empty when valid)."""
    files = {e["file"]: e for e in (manifest if manifest is not None else load_manifest())}
    errors: list[str] = []
    seen: set[str] = set()
    for item in items:
        where = item.id
        if item.id in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(item.id)
        if item.category not in CATEGORIES:
            errors.append(f"{where}: unknown category {item.category!r}")
        if item.difficulty not in DIFFICULTIES:
            errors.append(f"{where}: unknown difficulty {item.difficulty!r}")
        if item.language not in LANGUAGES:
            errors.append(f"{where}: unknown language {item.language!r}")
        if not item.provenance.get("author") or not item.provenance.get("use"):
            errors.append(f"{where}: provenance needs at least 'author' and 'use'")
        if item.answerable:
            if not item.gold_answer or not item.gold_facts or not item.gold_sources:
                errors.append(f"{where}: answerable items need gold_answer, gold_facts and gold_sources")
        elif item.gold_answer or item.gold_facts or item.gold_sources or item.forbidden_facts:
            errors.append(f"{where}: unanswerable items must have no gold answer, facts or sources")
        for source in item.gold_sources:
            entry = files.get(source.file)
            if entry is None:
                errors.append(f"{where}: gold source {source.file!r} is not in the corpus manifest")
            elif source.page is not None and entry.get("pages") and source.page > entry["pages"]:
                errors.append(f"{where}: {source.file} has no page {source.page}")
        if item.category == "cross-lingual":
            langs = {files[s.file]["language"] for s in item.gold_sources if s.file in files}
            if item.language in langs:
                errors.append(f"{where}: cross-lingual question has the same language as its source")
    if items and sum(1 for i in items if not i.answerable) < MIN_UNANSWERABLE:
        errors.append(f"need at least {MIN_UNANSWERABLE} unanswerable items")
    return errors


# ---------------------------------------------------------------------------
# Text normalization, facts, language, refusals
# ---------------------------------------------------------------------------

# A number written with thousands groups: 1-3 digits, then groups of exactly 3 digits that all use
# the same separator, then optionally a decimal part with the *other* separator ("1.012,40",
# "1,012.40", "1 200", "18.500"). It must not start inside another number, so dates
# ("08.07.2024"), IP addresses and CSV rows ("89.00,267.00") are left alone.
_GROUPED = re.compile(
    r"(?<![\d.,])(\d{1,3})(?:([.,'\u2019\u00a0\u202f ])\d{3})(?:\2\d{3})*(?:(?!\2)[.,]\d{1,2})?(?![\d]|[.,]\d)"
)
_DECIMAL_COMMA = re.compile(r"(?<![\d.,])(\d+),(\d{1,2})(?![\d]|[.,]\d)")
_ZERO_CENTS = re.compile(r"(?<![\d.,])(\d+)\.00(?![\d]|[.,]\d)")
_ANY_ZERO_CENTS = re.compile(r"(?<=\d)[.,]00(?!\d)")


def _ungroup(match: re.Match[str]) -> str:
    text = match.group(0)
    sep = match.group(2)
    digits = text.replace(sep, "")
    return re.sub(r"[.,](\d{1,2})$", r".\1", digits)


SOURCES_FOOTER = re.compile(r"\n\s*\*\*(?:Sources|Quellen|Källor):?\*\*.*\Z", re.S | re.I)


def canonical_numbers(text: str) -> str:
    """Write numbers one way: no thousands separators, '.' as decimal point, no '.00'.

    '1.012,40' and '1,012.40' -> '1012.40'; '238,00 €' -> '238 €'; '1 200 kr' -> '1200 kr'.
    """
    text = _GROUPED.sub(_ungroup, text)
    text = _DECIMAL_COMMA.sub(r"\1.\2", text)
    return _ZERO_CENTS.sub(r"\1", text)


def normalize(text: str) -> str:
    """Lowercase, NFKC, canonical numbers and single spaces."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = canonical_numbers(text)
    return re.sub(r"\s+", " ", text).strip()


def contains_fact(answer: str, fact: str) -> bool:
    """True if any '|'-separated alternative of ``fact`` appears as a whole token run."""
    haystack = normalize(answer)
    # Also try with every ".00" dropped, so "267" matches a CSV cell "267.00".
    haystacks = (haystack, _ANY_ZERO_CENTS.sub("", haystack))
    for alt in fact.split("|"):
        needle = normalize(alt)
        # Token boundary; a following decimal part blocks the match, a following year does not
        # ("30.11" matches "30.11.2024", "300" does not match "300.50").
        pattern = rf"(?<![0-9a-zà-ÿ]){re.escape(needle)}(?![0-9a-zà-ÿ])(?![.,](?!\d{{4}}(?!\d))\d)"
        if needle and any(re.search(pattern, h) for h in haystacks):
            return True
    return False


def answer_body(answer: str) -> str:
    """The answer without nAI's appended '**Sources:**' list."""
    return SOURCES_FOOTER.sub("", answer).strip()


_STOPWORDS: dict[str, set[str]] = {
    "en": set(
        "the and is are was of to in for on with that this it you your not be by at from or an have".split()
    ),
    "de": set(
        "der die das und ist sind nicht ein eine mit für auf dem des zu im von bei auch wird ich sie es".split()
    ),
    "sv": set("och är att det som en ett på för med till inte av har de om vid kan ska från".split()),
    "fr": set(
        "de le la les et est sont un une des du pour dans pas que qui sur avec au par ce il vous".split()
    ),
    # No "a", "o", "e", "no": they are common English words.
    "pt": set(
        "de os as é são um uma do da dos das para com não que em na por se ao ou mas está foi pelo pela".split()
    ),
}


def detect_language(text: str) -> str | None:
    """Very small stopword-based detector for the bench languages (None if unsure)."""
    words = re.findall(r"[a-zà-ÿ]+", normalize(text))
    if len(words) < 3:
        return None
    scores = {lang: sum(w in stops for w in words) for lang, stops in _STOPWORDS.items()}
    best = max(scores, key=lambda k: scores[k])
    ranked = sorted(scores.values(), reverse=True)
    if ranked[0] == 0 or ranked[0] == ranked[1]:
        return None
    return best


REFUSAL_PATTERNS = (
    # en
    r"(does not|doesn't|do not|don't) (contain|mention|say|provide|specify)",
    r"(don't|do not|doesn't|does not) have (that|this|any|enough) (information|data|details)",
    r"(no|not enough|insufficient) (information|details|mention)",
    r"(couldn't|could not|can't|cannot|unable to) (find|answer|determine|tell)",
    r"\b(is|are|was|were) not (mentioned|specified|stated|provided|given|found)\b",
    r"\bnot (mentioned|specified|stated|listed|provided|given) (in|by) the\b",
    # de
    r"(keine|nicht genügend|nicht genug) (information|angaben|hinweise)",
    r"(nicht|kein\w*) (enthalten|erwähnt|angegeben|gefunden|aufgeführt)",
    r"steht (dazu )?nicht in",
    r"nichts (dazu )?(finden|gefunden)",
    r"(kann|konnte) ich (dazu )?(keine|nichts|nicht)",
    # sv
    r"(finns|framgår) (inte|ingen|ej)",
    r"(ingen|inga) (information|uppgift|uppgifter)",
    r"hittar (jag )?(inget|ingenting|inte)",
    # pt
    r"(não|nao) (contém|contem|menciona|há informação|encontrei|é possível|consegui)",
    # fr
    r"(ne|n') (contient|mentionne|précise|indique) pas",
    r"(aucune|pas d') ?information",
)
_REFUSAL = re.compile("|".join(REFUSAL_PATTERNS), re.I)


def is_refusal(answer: str) -> bool:
    """Heuristic: does the answer say the files don't contain the answer?"""
    return bool(_REFUSAL.search(answer_body(answer)))


_NUMBER = re.compile(r"\d+(?:\.\d+)*")


def numbers_in(text: str) -> set[str]:
    """Canonical numbers with at least 2 digits mentioned in a text (dates stay '08.07.2024')."""
    return {n for n in _NUMBER.findall(canonical_numbers(text)) if sum(c.isdigit() for c in n) >= 2}


# ---------------------------------------------------------------------------
# Retrieval metrics (document level; chunks of the same file count once)
# ---------------------------------------------------------------------------


def _norm_path(path: str) -> str:
    return unicodedata.normalize("NFC", path.replace("\\", "/")).strip("/").lower()


def matches_gold(doc_path: str, gold_file: str) -> bool:
    """True if a result path refers to a gold corpus file (nAI may prefix the source name)."""
    result, gold = _norm_path(doc_path), _norm_path(gold_file)
    return result == gold or result.endswith("/" + gold)


def ranked_files(doc_paths: list[str]) -> list[str]:
    """Result paths de-duplicated in rank order."""
    return list(dict.fromkeys(doc_paths))


def _relevant(path: str, gold: tuple[str, ...]) -> str | None:
    return next((g for g in gold if matches_gold(path, g)), None)


def recall_at_k(ranked: list[str], gold: tuple[str, ...], k: int) -> float:
    found = {_relevant(p, gold) for p in ranked[:k]} - {None}
    return len(found) / len(gold) if gold else 0.0


def precision_at_k(ranked: list[str], gold: tuple[str, ...], k: int) -> float:
    """Relevant files in the top k, divided by k (fewer than k results count as misses)."""
    return sum(1 for p in ranked[:k] if _relevant(p, gold)) / k if k else 0.0


def hit_at_k(ranked: list[str], gold: tuple[str, ...], k: int) -> float:
    return 1.0 if any(_relevant(p, gold) for p in ranked[:k]) else 0.0


def reciprocal_rank(ranked: list[str], gold: tuple[str, ...]) -> float:
    for rank, path in enumerate(ranked, 1):
        if _relevant(path, gold):
            return 1.0 / rank
    return 0.0


def ndcg_at_k(ranked: list[str], gold: tuple[str, ...], k: int) -> float:
    seen: set[str] = set()
    dcg = 0.0
    for rank, path in enumerate(ranked[:k], 1):
        g = _relevant(path, gold)
        if g and g not in seen:
            seen.add(g)
            dcg += 1.0 / math.log2(rank + 1)
    ideal = sum(1.0 / math.log2(r + 1) for r in range(1, min(len(gold), k) + 1))
    return dcg / ideal if ideal else 0.0


def is_cross_lingual(item: BenchItem, manifest: list[dict[str, Any]]) -> bool:
    """True if the question's language differs from every gold source's language."""
    langs = {e["language"] for e in manifest if e["file"] in item.gold_files}
    return bool(langs) and item.language not in langs


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# ---------------------------------------------------------------------------
# nAI API client
# ---------------------------------------------------------------------------


@dataclass
class NaiClient:
    """Minimal client for a running nAI server (auth off, or an API key)."""

    base_url: str = "http://localhost:8000"
    api_key: str | None = None
    timeout: float = 300.0
    _http: httpx.Client = field(init=False, repr=False)

    def __post_init__(self) -> None:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        self._http = httpx.Client(base_url=self.base_url.rstrip("/"), headers=headers, timeout=self.timeout)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._http.post(path, json=payload)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    def _get(self, path: str) -> Any:
        response = self._http.get(path)
        response.raise_for_status()
        return response.json()

    def search(self, query: str, top_k: int, method: str = "auto") -> dict[str, Any]:
        return self._post("/search", {"query": query, "top_k": top_k, "method": method})

    def ask(self, question: str, top_k: int = 5, use_llm: bool = True) -> dict[str, Any]:
        return self._post("/ask", {"question": question, "top_k": top_k, "use_llm": use_llm})

    def ask_stream(self, question: str, top_k: int = 5, use_llm: bool = True) -> Iterator[tuple[str, Any]]:
        """Yield (event, data) pairs from /ask/stream."""
        payload = {"question": question, "top_k": top_k, "use_llm": use_llm}
        with self._http.stream("POST", "/ask/stream", json=payload) as response:
            response.raise_for_status()
            event = "message"
            for line in response.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    yield event, json.loads(line[5:].strip())
                    event = "message"

    def health(self) -> dict[str, Any]:
        data: dict[str, Any] = self._get("/health")
        return data

    def detailed_health(self) -> dict[str, Any]:
        data: dict[str, Any] = self._get("/health/detailed")
        return data

    def wait_until_up(self, timeout: float = 180.0, poll: float = 2.0) -> None:
        """Block until /health answers (the server may still be starting)."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                self.health()
                return
            except httpx.HTTPError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(poll)

    def ensure_source(self, path: str, name: str = SOURCE_NAME) -> int:
        """Return the id of the source for ``path``, creating it (and its first scan) if needed."""
        for source in self._get("/sources"):
            if source["name"] == name:
                if source.get("path") not in (None, path):
                    raise ValueError(f"source {name!r} already exists for {source['path']!r}, not {path!r}")
                return int(source["id"])
        created = self._post("/sources", {"name": name, "path": path})
        return int(created["id"])

    def wait_until_indexed(self, source_id: int, timeout: float = 900.0, poll: float = 2.0) -> dict[str, Any]:
        """Block until the source's scan has finished and no chunk is waiting for an embedding."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            source = next(s for s in self._get("/sources") if s["id"] == source_id)
            health = self.detailed_health()
            emb = health.get("embeddings") or {}
            if source["last_scan_status"] == "error":
                raise RuntimeError(f"scan of source {source_id} failed: {source.get('last_error')}")
            scanned = not source["scanning"] and source["last_scan_status"] not in ("never", "scanning")
            if emb.get("state") == "error":
                raise RuntimeError(f"embedding model failed to load: {emb.get('error')}")
            disabled = not emb or emb.get("enabled") is False or emb.get("state") == "disabled"
            embedded = disabled or (emb.get("state") == "ready" and emb.get("pending") == 0)
            if scanned and embedded:
                return {"source": source, "health": health}
            time.sleep(poll)
        raise TimeoutError(f"source {source_id} was not fully indexed within {timeout:.0f} s")
