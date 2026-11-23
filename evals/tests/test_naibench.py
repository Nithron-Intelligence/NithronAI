"""Tests for the nai-bench dataset, its scoring helpers and the eval scripts' scoring."""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

EVALS = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(EVALS), str(EVALS / "retrieval"), str(EVALS / "answers")]

import eval_answers  # noqa: E402
import eval_retrieval  # noqa: E402
import naibench as nb  # noqa: E402


def _load_build_corpus() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_corpus", nb.BENCH_DIR / "build_corpus.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_corpus"] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


# --- dataset ---------------------------------------------------------------


def test_questions_are_valid_and_cover_every_category() -> None:
    items = nb.load_items()
    assert len(items) >= 50
    assert {i.category for i in items} == set(nb.CATEGORIES)
    assert sum(not i.answerable for i in items) >= nb.MIN_UNANSWERABLE


def test_every_item_is_marked_eval_only() -> None:
    for item in nb.load_items():
        assert item.provenance["use"] == "eval-only", item.id
        assert item.provenance["author"], item.id


def test_corpus_files_match_manifest(capsys: pytest.CaptureFixture[str]) -> None:
    assert _load_build_corpus().check() == 0, capsys.readouterr().out


def test_every_corpus_file_records_license_and_provenance() -> None:
    for entry in nb.load_manifest():
        assert entry["license"] and entry["source"] and entry["provenance"], entry["file"]


def test_validate_reports_broken_items() -> None:
    item = nb.load_items()[0]
    broken = [
        replace(item, category="trivia"),
        replace(item, id="x", gold_sources=(nb.GoldSource("missing.pdf"),)),
        replace(item, id="y", gold_sources=(nb.GoldSource(item.gold_sources[0].file, page=99),)),
    ]
    errors = nb.validate(broken)
    assert any("unknown category" in e for e in errors)
    assert any("not in the corpus manifest" in e for e in errors)
    assert any("has no page 99" in e for e in errors)
    assert any("unanswerable" in e for e in errors)


# --- text helpers ------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "fact", "expected"),
    [
        ("Die Heizkosten betrugen 1.012,40 EUR.", "1,012.40", True),
        ("Heating: EUR 1,012.40", "1.012,40|1012.40", True),
        ("Die Selbstbeteiligung beträgt 3000 €.", "300", False),
        ("Port 8096 is used", "8096", True),
        ("Kod: KV-2024-558213", "kv-2024-558213", True),
        ("check-in kl. 15.00", "15:00|15.00", True),
    ],
)
def test_contains_fact(answer: str, fact: str, expected: bool) -> None:
    assert nb.contains_fact(answer, fact) is expected


def test_answer_body_strips_sources_footer() -> None:
    text = "It is 300 €.\n\n**Sources:**\n- [1] nai-bench/a.pdf, page 2\n"
    assert nb.answer_body(text) == "It is 300 €."


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("The deductible for the car is 300 euros and it is in the policy.", "en"),
        ("Die Selbstbeteiligung ist 300 € und steht in der Police für das Auto.", "de"),
        ("Incheckningen är från kl. 15 och det är inte tillåtet att röka.", "sv"),
        ("Le ramonage est obligatoire deux fois par an pour le poêle.", "fr"),
        ("O prazo de entrega é de seis semanas para o projeto.", "pt"),
        ("300 €", None),
    ],
)
def test_detect_language(text: str, lang: str | None) -> None:
    assert nb.detect_language(text) == lang


@pytest.mark.parametrize(
    ("answer", "refused"),
    [
        ("The policy number of your health insurance is not provided in the context documents.", True),
        ("Die Dokumente enthalten keine Informationen zur Kfz-Steuer.", True),
        ("Det framgår inte av dokumenten.", True),
        ("The fishing licence is not included in the rent; buy it in the iFiske app.", False),
        ("The default IP address is 192.168.8.1.", False),
    ],
)
def test_is_refusal(answer: str, refused: bool) -> None:
    assert nb.is_refusal(answer) is refused


# --- retrieval metrics ---------------------------------------------------------


def test_retrieval_metrics_are_document_level() -> None:
    ranked = nb.ranked_files(["src/a.pdf", "src/a.pdf", "src/b.md", "src/c.txt"])
    gold = ("a.pdf", "c.txt")
    assert ranked == ["src/a.pdf", "src/b.md", "src/c.txt"]
    assert nb.recall_at_k(ranked, gold, 1) == 0.5
    assert nb.recall_at_k(ranked, gold, 3) == 1.0
    assert nb.precision_at_k(ranked, gold, 2) == 0.5
    assert nb.hit_at_k(ranked, ("c.txt",), 2) == 0.0
    assert nb.reciprocal_rank(ranked, ("b.md",)) == 0.5
    assert nb.ndcg_at_k(ranked, ("a.pdf",), 5) == 1.0


def test_matches_gold_requires_whole_path_segments() -> None:
    assert nb.matches_gold("nai-bench/Rechnungen/scan_0042.pdf", "Rechnungen/scan_0042.pdf")
    assert not nb.matches_gold("Rechnungen/old_scan_0042.pdf", "scan_0042.pdf")


def test_score_item_page_hit() -> None:
    item = next(i for i in nb.load_items() if i.id == "nb-007")  # Kaution, Mietvertrag page 2
    results = [
        {"doc_path": "Wohnung/Mietvertrag_Ahornweg7.pdf", "page": 1},
        {"doc_path": "Wohnung/Mietvertrag_Ahornweg7.pdf", "page": 2},
    ]
    row = eval_retrieval.score_item(item, results, (1, 5))
    assert row["hit@1"] == 1.0
    assert row["page_hit@1"] == 1.0


# --- answer scoring --------------------------------------------------------------


def _run(answer: str, citations: list[dict[str, Any]]) -> dict[str, Any]:
    return {"answer": answer, "citations": citations}


def test_score_answerable() -> None:
    item = next(i for i in nb.load_items() if i.id == "nb-001")
    citation = {
        "doc_path": "nai-bench/Versicherungen/Kfz-Versicherung_2024.pdf",
        "text": "Vollkasko 300 € SF 12",
    }
    row = eval_answers.score(item, _run("Die Selbstbeteiligung beträgt 300 € und 999 €.", [citation]), [])
    assert row["correct"] is True
    assert row["citation_hit"] is True
    assert row["unsupported_numbers"] == ["999"]
    assert row["language_match"] is True
    assert row["false_refusal"] is False


def test_score_unanswerable() -> None:
    item = next(i for i in nb.load_items() if i.id == "nb-045")
    row = eval_answers.score(item, _run("The documents do not contain your health insurance.", []), [])
    assert row["correct_refusal"] is True
    made_up = eval_answers.score(item, _run("Your policy number is 12345.", []), [])
    assert made_up["correct_refusal"] is False


# --- regressions found in review (exact strings) --------------------------------


@pytest.mark.parametrize(
    ("answer", "fact", "expected"),
    [
        ("238,00 € brutto", "238", True),
        ("Die Kaution beträgt 3.450,00 €.", "3.450|3450", True),
        ("Wir kommen am 08.07.2024 an.", "08.07|8.7", True),
        ("Kündigung bis 30.11.2024", "30.11", True),
        ("Wandfarbe weiß 101 49,99", "49,99", True),  # OCR line: "10 l" read as "101"
        ("Software subscriptions,89.00,89.00,89.00,267.00", "267", True),
        ("Hyran är 1 200 kr", "1 200|1200", True),
        ("18.500 € netto", "18.500|18,500|18500", True),
        ("Die Selbstbeteiligung ist 300.50 €", "300", False),
        ("EUR 130.00", "30.00|30,00", False),
    ],
)
def test_contains_fact_number_formats(answer: str, fact: str, expected: bool) -> None:
    assert nb.contains_fact(answer, fact) is expected


def test_numbers_in_keeps_dates_and_csv_cells_apart() -> None:
    assert nb.numbers_in("rows 89.00,89.00,267.00 on 08.07.2024, total 1.012,40 EUR") == {
        "89.00",
        "267.00",
        "08.07.2024",
        "1012.40",
    }


@pytest.mark.parametrize(
    ("answer", "refused"),
    [
        ("Ein Hund kann nicht in den Schlafzimmern sein.", False),
        ("The standard warranty does not include labour.", False),
        ("Ich kann dazu leider nichts finden.", True),
        ("Das steht nicht in den Unterlagen.", True),
        ("I don't have that information.", True),
        ("Tyvärr hittar jag inget om detta.", True),
        ("Não consegui encontrar essa informação.", True),
    ],
)
def test_is_refusal_review_cases(answer: str, refused: bool) -> None:
    assert nb.is_refusal(answer) is refused


def test_english_with_a_and_no_is_not_portuguese() -> None:
    assert nb.detect_language("A dog is allowed in a cabin but no pets in a bed") == "en"


def test_forbidden_fact_makes_answer_wrong() -> None:
    item = next(i for i in nb.load_items() if i.id == "nb-027")
    citation = {"doc_path": "Sverige/hyresavtal_stuga_Bjorkudden.docx", "text": "En hund är tillåten"}
    good = eval_answers.score(item, _run("Ja, ein Hund ist erlaubt, aber nicht im Bett.", [citation]), [])
    bad = eval_answers.score(item, _run("Nein, ein Hund ist nicht erlaubt.", [citation]), [])
    assert good["correct"] is True
    assert bad["correct"] is False


def test_refusal_words_next_to_the_right_facts_are_not_a_false_refusal() -> None:
    item = next(i for i in nb.load_items() if i.id == "nb-041")
    row = eval_answers.score(item, _run("It is not included; buy it in the iFiske app.", []), [])
    assert row["false_refusal"] is False


def test_precision_counts_missing_results_as_misses() -> None:
    assert nb.precision_at_k(["a.pdf"], ("a.pdf",), 5) == 0.2


def test_cross_lingual_flag_uses_source_language() -> None:
    items = {i.id: i for i in nb.load_items()}
    manifest = nb.load_manifest()
    assert nb.is_cross_lingual(items["nb-020"], manifest)  # en question, de scan
    assert not nb.is_cross_lingual(items["nb-001"], manifest)


# --- human review workflow ---------------------------------------------------------


def _review_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("nai_review", nb.BENCH_DIR / "review.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["nai_review"] = module
    spec.loader.exec_module(module)
    return module


def _copy_questions(tmp_path: Path) -> Path:
    path = tmp_path / "questions.jsonl"
    path.write_text(nb.QUESTIONS_FILE.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def test_all_v0_items_start_unreviewed() -> None:
    counts = nb.review_summary()
    assert counts["unreviewed"] == counts["total"] and counts["reviewed"] == 0


def test_review_tool_records_accept_fix_reject(tmp_path: Path) -> None:
    review = _review_module()
    path = _copy_questions(tmp_path)
    answers = iter(
        [
            "a",
            "",  # nb-001: accept, no note
            "f",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "typo fixed",  # nb-002: fix (field by field, keep all), note
            "r",
            "duplicate of nb-030",  # nb-003: reject with reason
            "q",
        ]
    )
    done = review.run(
        path, "Test Reviewer", None, ask=lambda _: next(answers), out=lambda _: None, use_editor=False
    )

    assert done == {"accepted": 1, "fixed": 1, "rejected": 1, "skipped": 0}
    rows = {r["id"]: r for r in review.read_rows(path)}
    assert rows["nb-001"]["review_status"] == "accepted" and rows["nb-001"]["reviewed_by"] == "Test Reviewer"
    assert rows["nb-002"]["review_status"] == "fixed" and rows["nb-002"]["review_note"] == "typo fixed"
    assert rows["nb-003"]["review_status"] == "rejected"
    assert [i.id for i in nb.load_items(path, reviewed_only=True)] == ["nb-001", "nb-002"]
    assert "nb-003" not in {i.id for i in nb.load_items(path)}
    assert nb.review_summary(path)["reviewed"] == 2


def test_review_fields_are_validated(tmp_path: Path) -> None:
    path = _copy_questions(tmp_path)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["review_status"] = "accepted"  # no reviewer, no date
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="needs reviewed_by"):
        nb.load_items(path)
