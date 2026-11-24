"""Round 9 data pipeline: the quality filter, deduplication, negative picking and the guards around them."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

EMBED = Path(__file__).resolve().parent.parent / "embed"
sys.path.insert(0, str(EMBED))

import common  # noqa: E402
import data_manifest  # noqa: E402
import filter_pairs  # noqa: E402
import mine_negatives  # noqa: E402

PASSAGE = (
    "Invoice 2024-117 from Holm Plumbing. Replacement of the kitchen mixer tap and two angle valves, "
    "labour 2.5 hours at 68 EUR per hour, materials 143 EUR, VAT 19 percent. Payable within 14 days."
)


def pair(query: str, passage: str = PASSAGE, passage_id: str = "p1", **extra: Any) -> dict[str, Any]:
    return {
        "query": query,
        "query_language": "en",
        "passage_id": passage_id,
        "passage": passage,
        "passage_language": "en",
        "provenance": {"author": "mistral-small3.1", "use": "training"},
        **extra,
    }


def run(rows: list[dict[str, Any]], **kwargs: Any) -> tuple[list[dict[str, Any]], Counter[str]]:
    stats: Counter[str] = Counter()
    return list(filter_pairs.filter_rows(rows, stats, **kwargs)), stats


def test_good_pair_is_kept() -> None:
    kept, stats = run([pair("how much did the plumber charge per hour")])
    assert len(kept) == 1 and stats["kept"] == 1


@pytest.mark.parametrize(
    ("query", "reason"),
    [
        ("tap", "query_length"),
        ("x" * 201, "query_length"),
        ("Replacement of the kitchen mixer tap", "query_in_passage"),
        ("replacement kitchen mixer valves labour materials", "query_copied"),
    ],
)
def test_bad_queries_are_dropped_with_a_reason(query: str, reason: str) -> None:
    kept, stats = run([pair(query)])
    assert kept == [] and stats[reason] == 1


def test_language_label_must_match_the_detected_language() -> None:
    kept, stats = run([pair("wie viel hat der Klempner für die Arbeit pro Stunde berechnet")])
    assert kept == [] and stats["language_mismatch"] == 1


def test_rows_not_marked_for_training_are_dropped() -> None:
    row = pair("how much did the plumber charge per hour")
    row["provenance"] = {"author": "mistral-small3.1", "use": "eval"}
    kept, stats = run([row])
    assert kept == [] and stats["not_marked_training"] == 1


def test_short_passages_are_dropped() -> None:
    kept, stats = run([pair("what is the invoice number", passage="Invoice 2024-117.")])
    assert kept == [] and stats["passage_too_short"] == 1


def test_duplicate_queries_keep_the_first() -> None:
    kept, stats = run([pair("Plumber hourly rate?"), pair("plumber hourly rate", passage_id="p2")])
    assert [r["passage_id"] for r in kept] == ["p1"] and stats["duplicate_query"] == 1


def test_near_duplicate_passages_are_merged_onto_the_first_id() -> None:
    almost = PASSAGE.replace("Payable within 14 days.", "Payable within 14 days!")
    kept, stats = run([pair("plumber hourly rate"), pair("when is the plumbing invoice due", almost, "p2")])
    assert [r["passage_id"] for r in kept] == ["p1", "p1"]
    assert stats["near_duplicate_passage_merged"] == 1


def test_different_passages_stay_separate() -> None:
    other = "Minutes of the garden club meeting: the spring plant sale moves to the community hall in April."
    other = other + " Volunteers bring tables; the treasurer reports a surplus of 312 EUR from last year."
    kept, _ = run([pair("plumber hourly rate"), pair("where is the spring plant sale", other, "p2")])
    assert [r["passage_id"] for r in kept] == ["p1", "p2"]


def test_queries_per_passage_are_capped() -> None:
    rows = [pair(q) for q in ("plumber hourly rate", "plumbing invoice due date", "cost of the new tap")]
    kept, stats = run(rows, max_per_passage=2)
    assert len(kept) == 2 and stats["passage_cap"] == 1


def test_filter_cli_refuses_nai_bench_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="nai-bench"):
        list(common.read_training_rows(common.NAI_BENCH / "questions.jsonl"))


def test_filter_cli_refuses_claude_written_rows(tmp_path: Path) -> None:
    path = tmp_path / "pairs.jsonl"
    row = pair("plumber hourly rate")
    row["provenance"]["author"] = "claude-opus-5-5"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="principle 3"):
        list(common.read_training_rows(path))


RANKED = [
    ("pos", 0.90),
    ("dup", 0.89),
    ("a", 0.80),
    ("same-file", 0.79),
    ("b", 0.70),
    ("c", 0.60),
    ("d", 0.5),
]


def test_pick_negatives_skips_the_top_excluded_and_too_close_passages() -> None:
    picked = mine_negatives.pick_negatives(RANKED, 0.90, {"pos", "same-file"}, count=2, range_min=1)
    assert picked == ["a", "b"]  # "dup" scores >= 0.95 x positive: likely an unlabeled positive


def test_pick_negatives_respects_range_max() -> None:
    picked = mine_negatives.pick_negatives(RANKED, 0.90, {"pos"}, count=5, range_min=0, range_max=3)
    assert picked == ["a"]


def test_passage_file_prefers_the_recorded_source_document() -> None:
    assert (
        mine_negatives.passage_file({"passage_id": "p1", "passage_file": "eu:CELEX_1.html"})
        == "eu:CELEX_1.html"
    )
    assert mine_negatives.passage_file({"passage_id": "p1"}) == "p1"


def test_data_manifest_records_checksums_and_counts(tmp_path: Path) -> None:
    data = tmp_path / "vane1"
    data.mkdir()
    (data / "pairs.jsonl").write_text(json.dumps(pair("plumber hourly rate")) + "\n", encoding="utf-8")
    (data / "notes.txt").write_text("hello", encoding="utf-8")
    manifest = data_manifest.build(data)
    files = {f["path"]: f for f in manifest["files"]}
    assert files["pairs.jsonl"]["rows"] == 1 and len(files["pairs.jsonl"]["sha256"]) == 64
    assert files["notes.txt"]["rows"] is None and files["notes.txt"]["bytes"] == 5


def test_data_manifest_refuses_nai_bench() -> None:
    with pytest.raises(ValueError, match="nai-bench"):
        data_manifest.build(common.NAI_BENCH)


def test_holdout_is_stable_per_document_and_close_to_the_share() -> None:
    names = [f"eu/CELEX_{n}.html" for n in range(4000)]
    held = [n for n in names if common.is_holdout(n, 0.05)]
    assert 0.03 < len(held) / len(names) < 0.07
    assert held == [n for n in names if common.is_holdout(n, 0.05)]
    assert not any(common.is_holdout(n, 0.0) for n in names)


def test_fetch_refuses_documents_that_nai_bench_uses() -> None:
    import fetch_public

    urls = fetch_public.bench_source_urls()
    assert len(urls) > 30
    with pytest.raises(ValueError, match="nai-bench document"):
        fetch_public.refuse_bench_source("https://publications.europa.eu/resource/celex/32011L0083/", urls)
    with pytest.raises(ValueError, match="nai-bench document"):
        fetch_public.refuse_bench_source("https://gutenberg.pglaf.org/cache/epub/84/pg84.txt", urls)
    fetch_public.refuse_bench_source("http://publications.europa.eu/resource/celex/32016R0679", urls)


def test_fetch_refuses_any_page_of_a_law_nai_bench_lists_as_a_folder() -> None:
    import fetch_public

    urls = fetch_public.bench_source_urls()
    with pytest.raises(ValueError, match="nai-bench document"):
        fetch_public.refuse_bench_source("https://www.gesetze-im-internet.de/bgb/BJNR001950896.html", urls)
    fetch_public.refuse_bench_source("https://www.gesetze-im-internet.de/bgbeg/BJNR006049896.html", urls)


def test_holdout_keeps_all_language_versions_of_a_document_together() -> None:
    assert common.document_key("CELEX_32015L2366_DE.html") == "CELEX_32015L2366"
    assert common.document_key("Recht/EU/CELEX_32011L0083_EN_TXT.html") == "Recht/EU/CELEX_32011L0083"
    assert common.document_key("SFS_2003-862.txt") == "SFS_2003-862.txt"
    for n in range(400):
        versions = {common.is_holdout(f"CELEX_3{n:04d}R0001_{lang}.html", 0.2) for lang in ("EN", "DE", "SV")}
        assert len(versions) == 1


def test_train_uses_negatives_stored_by_mine_negatives() -> None:
    import train

    rows = [
        {"query": "q1", "passage": "p1", "negatives": ["n1", "n2", "n3"]},
        {"query": "q2", "passage": "p2", "negatives": ["n4"]},
        {"query": "q3", "passage": "p3"},
    ]
    columns = train.file_negative_columns(rows, 2)
    assert columns == {"anchor": ["q1"], "positive": ["p1"], "negative_1": ["n1"], "negative_2": ["n2"]}
