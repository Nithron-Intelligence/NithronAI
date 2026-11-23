"""
Generate a synthetic NAS-like corpus for Vane 1 with an approved open-weight teacher (Ollama).

Fictional household and small-office documents (invoices, contracts, manuals, minutes, letters, ...) in the
five nai-bench languages. Everything is invented (names, companies, addresses with example domains, 555 phone
numbers). Each document is a Markdown file; provenance (teacher, its license, prompt version, seed, date,
``use: training``) goes into ``<out>.manifest.json`` beside the corpus folder, never into the text. Nothing from nai-bench
is shown to the teacher.

    python training/embed/generate_corpus.py --out training/data/vane1-pilot/synthetic --per-language 20 \
        --model mistral-small3.1 --seed 13
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
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
    args = parser.parse_args()

    license_id = teacher_license(args.model)  # refuses unapproved teachers
    refuse_bench_path(args.out)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out.with_name(args.out.name + ".manifest.json")  # beside the corpus, not indexed
    manifest: dict[str, Any] = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    started = time.monotonic()
    with httpx.Client(base_url=args.ollama, timeout=600) as client:
        for n, spec in enumerate(specs(args.per_language, args.seed), start=1):
            name = f"{spec['language']}/{n:03d}.md"
            if name in manifest:
                continue  # resume
            prompt = PROMPT.format(
                doc_type=spec["doc_type"], language=spec["language_name"], country=spec["country"]
            )
            text = generate(client, args.model, prompt, args.seed + n)
            path = args.out / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text + "\n", encoding="utf-8")
            manifest[name] = {
                **{k: spec[k] for k in ("language", "country", "doc_type")},
                "author": args.model,
                "teacher_license": license_id,
                "prompt_version": PROMPT_VERSION,
                "seed": args.seed + n,
                "created": date.today().isoformat(),
                "use": "training",
                "license": "CC0-1.0",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            manifest_path.write_text(
                json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            print(f"{n:>3} {name} {len(text.split())} words ({time.monotonic() - started:.0f} s)", flush=True)
    print(f"{len(manifest)} documents in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
