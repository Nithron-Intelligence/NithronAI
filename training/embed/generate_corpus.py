"""
Generate a synthetic NAS-like corpus for Vane 1 with an approved open-weight teacher (Ollama).

Fictional household and small-office documents (invoices, contracts, manuals, minutes, letters, ...) in the
five nai-bench languages. Everything is invented (names, companies, addresses with example domains, 555 phone
numbers). Each document is a Markdown file; provenance (teacher, its license, prompt version, seed, date,
``use: training``) goes into ``<out>.manifest.json`` beside the corpus folder, never into the text. Nothing from nai-bench
is shown to the teacher.

    python training/embed/generate_corpus.py --out training/data/vane1-pilot/synthetic --per-language 20 \
        --model mistral-small3.1 --seed 13

``--prompt-version corpus-v2`` (round 9) draws each document from a much wider space so the corpus does not
resemble nai-bench v1's fictional files: ~60 document types across household, small office, hobbies, health,
school, technical and admin life, crossed with a file format (email, chat export, Markdown notes, CSV,
plain letter, checklist, README, minutes ...), a writer, a length band and a year. ``--concurrency N`` keeps
N requests in flight; every finished document is written and recorded in the manifest at once (resumable).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from common import refuse_bench_path, teacher_license

PROMPT_VERSION = "corpus-v1"
LANGUAGES = {
    "en": ("English", ["the United Kingdom", "Ireland", "the United States"]),
    "de": ("German", ["Germany", "Austria", "Switzerland"]),
    "sv": ("Swedish", ["Sweden"]),
    "fr": ("French", ["France", "Belgium"]),
    "pt": ("Portuguese", ["Portugal", "Brazil"]),
}
DOC_TYPES = [
    "utility bill (electricity or water) with a table of charges",
    "excerpt of a residential rental contract",
    "letter from a home insurance company about a claim",
    "section of an appliance user manual with technical data",
    "minutes of a homeowners' association meeting",
    "invoice from a small craft business with line items and VAT",
    "car service record with mileage and parts",
    "letter from the tax office about a refund",
    "travel booking confirmation with dates and cancellation terms",
    "warranty claim letter written by a customer",
    "school or kindergarten newsletter with dates",
    "notes from a freelancer's project kickoff meeting",
    "bank statement summary with a few transactions",
    "subscription cancellation confirmation",
    "home network and NAS setup notes",
    "garden plan with a planting calendar",
    "moving checklist with deadlines",
    "receipt from a hardware store",
    "employment contract excerpt with working hours and salary",
    "quote from a roofer or plumber with a price breakdown",
]
# corpus-v2 (round 9): wider, deliberately unlike nai-bench v1's household-paperwork style.
DOC_TYPES_V2 = [
    "family recipe with ingredient quantities and oven settings",
    "weekly meal plan with a shopping list",
    "dog or cat vet visit summary with vaccination dates",
    "fictional medical appointment notes (no real diagnosis)",
    "pharmacy receipt with dosage instructions",
    "children's sports club training schedule",
    "parent-teacher meeting notes",
    "university course reading list with deadlines",
    "thesis chapter outline",
    "lab notebook entry from a hobby electronics project",
    "3D printer settings log",
    "home solar panel monthly yield report",
    "heat pump maintenance log",
    "car insurance renewal comparison",
    "used car purchase agreement",
    "bicycle repair notes with part numbers",
    "router and Wi-Fi configuration notes",
    "backup and RAID rebuild runbook for a home server",
    "README for a family photo archive folder",
    "software license inventory of a small office",
    "IT onboarding checklist for a new employee",
    "small business price list",
    "customer complaint email thread",
    "supplier order confirmation",
    "quarterly VAT summary of a sole trader",
    "freelance service agreement",
    "non-disclosure agreement excerpt",
    "job application cover letter",
    "reference letter from a former employer",
    "volunteer club membership list with fees",
    "church or community choir rehearsal plan",
    "band setlist with song keys and tempos",
    "wedding planning budget",
    "birthday party guest list and menu",
    "holiday packing list",
    "road trip itinerary with distances",
    "camping gear inventory",
    "hiking route description with elevation",
    "language course homework",
    "personal reading log with ratings",
    "board game rules summary written by a player",
    "aquarium water test log",
    "beekeeping hive inspection notes",
    "vegetable garden harvest log",
    "allotment association rules",
    "apartment handover protocol with meter readings",
    "neighbour dispute letter about noise",
    "building renovation timeline with contractors",
    "kitchen renovation quote comparison",
    "furniture assembly notes",
    "electricity tariff comparison table",
    "household budget spreadsheet for one month",
    "loan repayment schedule",
    "pension statement summary",
    "donation receipt from a charity",
    "notes from a tax adviser meeting",
    "power of attorney template filled in",
    "estate inventory after a relative's death",
    "insurance list of valuables with serial numbers",
    "photography exposure notes from a trip",
    "podcast episode show notes",
    "minutes of a startup board meeting",
    "product requirements notes for a small app",
    "bug report and fix log",
    "meeting room booking rules",
]
FORMATS_V2 = [
    "an email (with From/To/Subject/Date lines)",
    "an exported chat conversation with timestamps",
    "terse personal Markdown notes with bullet points",
    "a CSV file with a header row (only the CSV)",
    "a formal letter",
    "a checklist",
    "a README-style text file",
    "a table-heavy Markdown document",
    "a scanned-form style text with labelled fields",
    "a short report with numbered sections",
]
WRITERS_V2 = [
    "a retired teacher",
    "a student",
    "a busy parent",
    "a self-employed electrician",
    "an office manager",
    "a nurse working shifts",
    "a software developer",
    "a farmer",
    "a small shop owner",
    "a pensioner couple",
    "a hobby photographer",
    "an association treasurer",
]
LENGTHS_V2 = ["80 to 150 words", "150 to 300 words", "300 to 500 words", "500 to 800 words"]
PROMPT_V2 = (
    "Write {doc_type} as {format}, in {language}, written by {writer} in {country} around {year}. "
    "Length: {length}. It is a file on a private home or small-office NAS. Invent every name, company, address, "
    "amount, date and reference number; use example.org or .example domains and 555 phone numbers; no real "
    "people or companies. Keep the writer's own voice and typical mistakes of the format. Write only the file's "
    "content, with no introduction or comment."
)

PROMPT = (
    "Write a realistic but entirely fictional {doc_type} in {language}, as it would be stored on a family's or a "
    "small office's NAS in {country}. Length: 250 to 450 words. Invent every name, company, address, amount, "
    "date and reference number; use example.org or .example domains and 555 phone numbers; no real people or "
    "companies. Use plain text or simple Markdown (headings, lists, a table if natural). Write only the document, "
    "with no introduction or comment."
)


def specs(per_language: int, seed: int) -> list[dict[str, str]]:
    """Deterministic (language, country, doc type) combinations, ``per_language`` for each language."""
    rng = random.Random(seed)
    out = []
    for lang, (name, countries) in LANGUAGES.items():
        types = rng.sample(DOC_TYPES, k=min(per_language, len(DOC_TYPES)))
        for i, doc_type in enumerate(types):
            out.append(
                {
                    "language": lang,
                    "language_name": name,
                    "country": countries[i % len(countries)],
                    "doc_type": doc_type,
                }
            )
    return out


def specs_v2(per_language: int, seed: int, languages: list[str]) -> list[dict[str, str]]:
    """Deterministic corpus-v2 specs: random (type, format, writer, length, year) per document."""
    rng = random.Random(seed)
    out = []
    for lang in languages:
        name, countries = LANGUAGES[lang]
        for _ in range(per_language):
            out.append(
                {
                    "language": lang,
                    "language_name": name,
                    "country": rng.choice(countries),
                    "doc_type": rng.choice(DOC_TYPES_V2),
                    "format": rng.choice(FORMATS_V2),
                    "writer": rng.choice(WRITERS_V2),
                    "length": rng.choice(LENGTHS_V2),
                    "year": str(rng.randint(2012, 2026)),
                }
            )
    return out


def generate(client: httpx.Client, model: str, prompt: str, seed: int) -> str:
    response = client.post(
        "/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.8, "seed": seed, "num_ctx": 8192},
        },
    )
    response.raise_for_status()
    text: str = response.json()["message"]["content"].strip()
    return text


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--per-language", type=int, default=20)
    parser.add_argument("--model", default="mistral-small3.1")
    parser.add_argument("--ollama", default="http://localhost:11434")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--prompt-version", choices=("corpus-v1", "corpus-v2"), default=PROMPT_VERSION)
    parser.add_argument("--languages", default=",".join(LANGUAGES), help="corpus-v2 only")
    parser.add_argument("--concurrency", type=int, default=1, help="requests in flight")
    args = parser.parse_args()

    license_id = teacher_license(args.model)  # refuses unapproved teachers
    refuse_bench_path(args.out)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out.with_name(args.out.name + ".manifest.json")  # beside the corpus, not indexed
    manifest: dict[str, Any] = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    started = time.monotonic()
    v2 = args.prompt_version == "corpus-v2"
    all_specs = (
        specs_v2(args.per_language, args.seed, args.languages.split(","))
        if v2
        else specs(args.per_language, args.seed)
    )
    prefix = "v2-" if v2 else ""
    todo = [
        (n, spec, f"{spec['language']}/{prefix}{n:05d}.md" if v2 else f"{spec['language']}/{n:03d}.md")
        for n, spec in enumerate(all_specs, start=1)
    ]
    todo = [job for job in todo if job[2] not in manifest]  # resume

    def make(job: tuple[int, dict[str, str], str]) -> tuple[int, dict[str, str], str, str]:
        n, spec, name = job
        template = PROMPT_V2 if v2 else PROMPT
        prompt = template.format(
            **{k: v for k, v in spec.items() if k != "language"}, language=spec["language_name"]
        )
        return n, spec, name, generate(client, args.model, prompt, args.seed + n)

    with (
        httpx.Client(base_url=args.ollama, timeout=600) as client,
        ThreadPoolExecutor(args.concurrency) as pool,
    ):
        for done, (n, spec, name, text) in enumerate(pool.map(make, todo), start=1):
            path = args.out / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text + "\n", encoding="utf-8")
            keys = ("language", "country", "doc_type", "format", "writer", "length", "year")
            manifest[name] = {
                **{k: spec[k] for k in keys if k in spec},
                "author": args.model,
                "teacher_license": license_id,
                "prompt_version": args.prompt_version,
                "seed": args.seed + n,
                "created": date.today().isoformat(),
                "use": "training",
                "license": "CC0-1.0",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            manifest_path.write_text(
                json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            elapsed = time.monotonic() - started
            print(f"{done:>5}/{len(todo)} {name} {len(text.split())} words ({elapsed:.0f} s)", flush=True)
    print(f"{len(manifest)} documents in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
