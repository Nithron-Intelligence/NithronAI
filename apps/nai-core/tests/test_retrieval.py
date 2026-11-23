"""
Hybrid retrieval (BM25 + vectors fused with RRF), embedding storage, reranking,
section-aware extraction and contextual chunk headers
"""

import io

import numpy as np
import pytest

from app.services.access import UPLOADS_SOURCE, AccessScope
from app.services.retriever import reciprocal_rank_fusion
from app.utils.extractors import Section, extract
from app.utils.text import build_context_header, chunk_sections


def _upload(client, name: str, text: str) -> dict:
    r = client.post("/ingest", files={"files": (name, io.BytesIO(text.encode()), "text/plain")})
    assert r.status_code == 200, r.text
    return r.json()["added"][0]


def _embed_all() -> int:
    from app.services import get_embedding_service

    return get_embedding_service().embed_pending()


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------


def test_rrf_rewards_items_ranked_well_by_both_lists():
    fused = reciprocal_rank_fusion([[1, 2, 3], [3, 1, 4]], k=60)
    order = [item for item, _ in fused]
    assert order[0] == 1  # 1st + 2nd beats 3rd + 1st
    assert set(order) == {1, 2, 3, 4}
    assert fused[0][1] == pytest.approx(1 / 61 + 1 / 62)


def test_access_scope_mask():
    sources = np.array([UPLOADS_SOURCE, 1, 2, 3], dtype=np.int64)
    assert AccessScope(all_sources=True).mask(sources) is None
    assert AccessScope(False, frozenset({2})).mask(sources).tolist() == [True, False, True, False]
    assert AccessScope(False, frozenset({2}), uploads=False).mask(sources).tolist() == [
        False,
        False,
        True,
        False,
    ]
    narrowed = AccessScope(False, frozenset({1, 2})).narrow([2, 3], include_uploads=False)
    assert narrowed.source_ids == frozenset({2}) and not narrowed.uploads


# ---------------------------------------------------------------------------
# Semantic + hybrid search
# ---------------------------------------------------------------------------


def test_semantic_search_finds_paraphrases_bm25_misses(make_client, fake_embeddings):
    c = make_client(**fake_embeddings)
    _upload(c, "car.txt", "My car insurance documents from the broker.")
    _upload(c, "food.txt", "Grandma's lasagne recipe with lots of cheese.")
    assert _embed_all() == 2

    # No shared words with the car document: BM25 alone finds nothing
    bm25 = c.post("/search", json={"query": "automobile coverage", "method": "bm25"}).json()
    assert bm25["results"] == []

    hybrid = c.post("/search", json={"query": "automobile coverage"}).json()
    assert hybrid["method"] == "hybrid"
    assert [r["filename"] for r in hybrid["results"]] == ["car.txt"]  # min score filters the recipe

    emb = c.post("/search", json={"query": "vehicle policy", "method": "embedding"}).json()
    assert emb["method"] == "embedding" and emb["results"][0]["filename"] == "car.txt"


def test_hybrid_keeps_exact_keyword_matches(make_client, fake_embeddings):
    c = make_client(**fake_embeddings)
    _upload(c, "error.txt", "Error code E1234 means the backup disk is full.")
    _upload(c, "car.txt", "Car insurance renewal letter.")
    _embed_all()
    results = c.post("/search", json={"query": "E1234"}).json()["results"]
    assert results[0]["filename"] == "error.txt"


def test_new_chunks_are_keyword_searchable_before_embedding(make_client, fake_embeddings):
    c = make_client(**fake_embeddings)
    _upload(c, "car.txt", "Car insurance renewal letter.")
    from app.services import get_embedding_service

    assert get_embedding_service().pending_count() == 1
    results = c.post("/search", json={"query": "renewal"}).json()["results"]
    assert [r["filename"] for r in results] == ["car.txt"]


def test_embeddings_follow_document_changes(make_client, fake_embeddings):
    from app.db import get_db

    c = make_client(**fake_embeddings)
    added = _upload(c, "car.txt", "Car insurance renewal letter.")
    _embed_all()
    with get_db().connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0] == 1
    c.delete(f"/documents/{added['doc_id']}")
    with get_db().connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0] == 0
    assert c.post("/search", json={"query": "automobile", "method": "embedding"}).json()["results"] == []


def _switch_to_other_model(make_client, fake_embeddings, **env):
    from app.services.embeddings import register_provider

    from .conftest import FakeEmbeddingProvider

    c = make_client(**fake_embeddings)
    _upload(c, "car.txt", "Car insurance renewal letter.")
    _upload(c, "bill.txt", "Electricity bill for October.")
    _embed_all()

    class OtherModel(FakeEmbeddingProvider):
        model = "fake-v2"

    register_provider("fake2", OtherModel)
    return make_client(NAI_EMBEDDINGS_PROVIDER="fake2", **env)


def test_model_change_waits_for_confirmation_and_never_mixes_vectors(make_client, fake_embeddings):
    from app.db import get_db
    from app.services import get_embedding_service

    c = _switch_to_other_model(make_client, fake_embeddings)
    service = get_embedding_service()
    assert service.is_available()  # load the new model (the background worker does this at start)

    # Nothing is re-embedded until an admin confirms, and the old vectors are never searched.
    assert service.reindex_required
    assert service.embed_pending() == 0
    # Searches keep working on keywords only; an explicit embedding search says why it can't run.
    r = c.post("/search", json={"query": "electricity", "method": "hybrid"}).json()
    assert r["method"] == "bm25" and r["results"][0]["filename"] == "bill.txt"
    paused = c.post("/search", json={"query": "receipt", "method": "embedding"})
    assert paused.status_code == 400 and "re-index" in paused.json()["detail"]
    stats = c.get("/system").json()["features"]["embeddings"]
    assert stats["reindex_required"] is True and stats["previous_models"] == {"fake:fake-synonyms": 2}

    r = c.post("/system/embeddings/reindex").json()
    assert r["reindexing"] is True and r["removed_vectors"] == 2
    assert not service.reindex_required
    assert service.embed_pending() == 2
    with get_db().connect() as conn:
        models = {row[0] for row in conn.execute("SELECT model FROM chunk_embeddings")}
    assert models == {"fake:fake-v2"}
    assert (
        c.post("/search", json={"query": "receipt", "method": "embedding"}).json()["results"][0]["filename"]
        == "bill.txt"
    )
    assert c.post("/system/embeddings/reindex").json()["reindexing"] is False


def test_auto_reindex_setting_re_embeds_without_asking(make_client, fake_embeddings):
    from app.services import get_embedding_service

    _switch_to_other_model(make_client, fake_embeddings, NAI_EMBEDDINGS_AUTO_REINDEX="true")
    service = get_embedding_service()
    assert not service.reindex_required
    assert service.embed_pending() == 2
    assert service.other_model_vectors() == {}


def test_unavailable_provider_falls_back_to_keyword_search(make_client):
    c = make_client(NAI_EMBEDDINGS_ENABLED="true", NAI_EMBEDDINGS_PROVIDER="does-not-exist")
    _upload(c, "car.txt", "Car insurance renewal letter.")
    r = c.post("/search", json={"query": "insurance"}).json()
    assert r["method"] == "bm25" and len(r["results"]) == 1
    assert c.post("/search", json={"query": "insurance", "method": "embedding"}).status_code == 400
    health = c.get("/health").json()
    assert health["status"] == "degraded" and health["components"]["embeddings"] is False


def test_reranker_reorders_candidates(make_client, monkeypatch):
    from app.services import get_reranker

    c = make_client(NAI_RERANKER="true")
    _upload(c, "a.txt", "Backup schedule: the backup runs nightly.")
    _upload(c, "b.txt", "Backup notes. The offsite backup copy is weekly.")

    reranker = get_reranker()
    monkeypatch.setattr(reranker, "_load", lambda: object())
    monkeypatch.setattr(
        reranker, "rerank", lambda query, docs: [10.0 if "offsite" in d else 1.0 for d in docs]
    )
    r = c.post("/search", json={"query": "backup"}).json()
    assert r["method"] == "bm25+rerank"
    assert r["results"][0]["filename"] == "b.txt"


# ---------------------------------------------------------------------------
# Extraction and contextual chunks
# ---------------------------------------------------------------------------


def _pdf_bytes(pages: list[str]) -> bytes:
    """A minimal valid PDF with one line of text per page (correct xref offsets)."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
    font_id = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET"
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        )
        objects.append(f"<< /Length {len(content)} >>\nstream\n{content}\nendstream")
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = b"%PDF-1.4\n"
    offsets = []
    for n, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{obj}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def test_pdf_pages_become_sections(tmp_path):
    path = tmp_path / "manual.pdf"
    path.write_bytes(
        _pdf_bytes(["Installing the router on the wall", "Resetting the router to factory defaults"])
    )
    result = extract(str(path), ocr=False)
    assert [s.page for s in result.sections] == [1, 2]
    assert "factory defaults" in result.sections[1].text
    assert result.metadata["pages"] == 2


def test_pdf_citation_has_page_number(make_client):
    c = make_client()
    r = c.post(
        "/ingest",
        files={
            "files": (
                "manual.pdf",
                io.BytesIO(_pdf_bytes(["Wall mounting guide", "Factory reset steps"])),
                "application/pdf",
            )
        },
    )
    assert r.json()["added"][0]["status"] == "success"
    citation = c.post("/ask", json={"question": "factory reset"}).json()["citations"][0]
    assert citation["page"] == 2
    assert c.get(f"/documents/{citation['doc_id']}/file").headers["content-type"] == "application/pdf"


def test_markdown_headings_become_section_paths(tmp_path):
    path = tmp_path / "setup.md"
    path.write_text(
        "# Home Server\n\nIntro text.\n\n## Network\n\nStatic IP 192.168.1.10.\n\n"
        "```\n# not a heading\n```\n\n### WiFi\n\nSSID is HomeNet.\n\n## Backup\n\nNightly."
    )
    result = extract(str(path))
    headings = [s.heading for s in result.sections]
    assert headings == [
        "Home Server",
        "Home Server > Network",
        "Home Server > Network > WiFi",
        "Home Server > Backup",
    ]
    assert result.metadata["title"] == "Home Server"
    assert "# not a heading" in result.sections[1].text


def test_html_headings_and_script_stripping(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(
        "<html><head><title>NAS Guide</title><script>var x = 'hidden';</script></head><body>"
        "<h1>Guide</h1><p>Welcome &amp; hello.</p><h2>Shares</h2><p>Create a share.</p></body></html>"
    )
    result = extract(str(path))
    assert result.metadata["title"] == "NAS Guide"
    assert [s.heading for s in result.sections] == ["Guide", "Guide > Shares"]
    assert "Welcome & hello." in result.text and "hidden" not in result.text


def test_docx_paragraphs_headings_and_tables(tmp_path):
    import docx

    document = docx.Document()
    document.add_heading("Lease Agreement", level=1)
    document.add_paragraph("The tenant pays rent monthly.")
    document.add_heading("Deposit", level=2)
    document.add_paragraph("The deposit is three months of rent.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Rent", "900 EUR"
    table.cell(1, 0).text, table.cell(1, 1).text = "Deposit", "2700 EUR"
    path = tmp_path / "lease.docx"
    document.save(str(path))

    result = extract(str(path))
    assert [s.heading for s in result.sections] == ["Lease Agreement", "Lease Agreement > Deposit", "Table"]
    assert "Deposit | 2700 EUR" in result.sections[2].text


def test_text_encodings_are_detected(tmp_path):
    path = tmp_path / "latin.txt"
    path.write_bytes("Größe und Maße".encode("cp1252"))
    result = extract(str(path))
    assert result.text == "Größe und Maße"


def test_chunks_carry_context_header_and_never_cross_sections():
    sections = [
        Section("First page text. " * 10, page=1),
        Section("Second page text.", page=2, heading="Summary"),
    ]
    drafts = chunk_sections(sections, display_path="Docs/report.pdf", title="Annual Report", max_chars=200)
    assert {d.page for d in drafts} == {1, 2}
    assert all(d.text.count("Second") == 0 for d in drafts if d.page == 1)
    last = drafts[-1]
    assert last.context == "Document: Docs/report.pdf | Title: Annual Report | Section: Summary | Page 2"
    # Title is left out when it just repeats the file name
    assert "Title" not in build_context_header("report.pdf", title="report")


def test_context_header_makes_folder_names_searchable(make_client):
    c = make_client()
    _upload(c, "2023-tax-return.txt", "Total refund: 412 EUR.")
    results = c.post("/search", json={"query": "tax return"}).json()["results"]
    assert [r["filename"] for r in results] == ["2023-tax-return.txt"]
    chunks = c.get(f"/documents/{results[0]['doc_id']}/chunks").json()["chunks"]
    assert chunks[0]["context"].startswith("Document: 2023-tax-return.txt")
    assert chunks[0]["text"] == "Total refund: 412 EUR."  # header is not part of the shown text


def test_new_formats_are_accepted_for_upload(make_client):
    c = make_client()
    for name, body in [
        ("script.py", b"def backup():\n    return 'nightly'\n"),
        ("data.csv", b"disk,size\nsda,4TB\n"),
    ]:
        assert _upload(c, name, body.decode())["status"] == "success"
    # Images need OCR, which is disabled in tests
    r = c.post("/ingest", files={"files": ("scan.png", io.BytesIO(b"\x89PNG"), "image/png")})
    assert r.json()["added"][0]["status"] == "error"


def test_slow_model_load_never_blocks_health_or_search(make_client, fake_embeddings):
    """First start downloads the model: requests must keep working (keyword-only) meanwhile."""
    import threading
    import time

    from app.services import get_embedding_service
    from app.services.embeddings import register_provider

    from .conftest import FakeEmbeddingProvider

    release = threading.Event()

    class SlowProvider(FakeEmbeddingProvider):
        def __init__(self, settings=None):
            release.wait(10)

    register_provider("slow", SlowProvider)
    c = make_client(**{**fake_embeddings, "NAI_EMBEDDINGS_PROVIDER": "slow"})
    _upload(c, "car.txt", "Car insurance renewal letter.")

    start = time.monotonic()
    health = c.get("/health").json()
    search = c.post("/search", json={"query": "insurance"}).json()
    system = c.get("/system").json()
    assert time.monotonic() - start < 3
    assert health["status"] == "ok" and health["components"]["embeddings"] is True
    assert search["method"] == "bm25" and len(search["results"]) == 1
    assert system["features"]["embeddings"]["state"] == "loading"

    release.set()
    service = get_embedding_service()
    for _ in range(100):
        if service.state == "ready":
            break
        time.sleep(0.05)
    assert service.state == "ready"
    service.embed_pending()
    assert c.post("/search", json={"query": "automobile coverage"}).json()["method"] == "hybrid"


def test_upgrade_from_the_old_default_model_asks_before_reindexing(make_client, fake_embeddings):
    """0.6.0 → 0.7.0: vectors made with paraphrase-multilingual-MiniLM-L12-v2 are kept but not searched, and
    nothing is re-embedded with the new default (granite 97m) until an admin confirms."""
    from app.config import Settings
    from app.services import get_embedding_service
    from app.services.embeddings import register_provider

    from .conftest import FakeEmbeddingProvider

    old_default = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    new_default = Settings.model_fields["embeddings_model"].default
    assert new_default == "ibm-granite/granite-embedding-97m-multilingual-r2"

    class OldDefault(FakeEmbeddingProvider):
        name = "fastembed"
        model = old_default

    class NewDefault(FakeEmbeddingProvider):
        name = "fastembed"
        model = new_default

    register_provider("fastembed", OldDefault)
    c = make_client(
        **{**fake_embeddings, "NAI_EMBEDDINGS_PROVIDER": "fastembed", "NAI_EMBEDDINGS_MODEL": old_default}
    )
    _upload(c, "car.txt", "Car insurance renewal letter.")
    _upload(c, "bill.txt", "Electricity bill for October.")
    _embed_all()

    register_provider("fastembed", NewDefault)  # the upgraded image, default settings
    env = {k: v for k, v in fake_embeddings.items() if k != "NAI_EMBEDDINGS_PROVIDER"}
    c = make_client(**{**env, "NAI_EMBEDDINGS_PROVIDER": "fastembed"})
    service = get_embedding_service()
    assert service.is_available()
    assert service.reindex_required
    assert service.embed_pending() == 0
    stats = c.get("/system").json()["features"]["embeddings"]
    assert stats["model"] == new_default
    assert stats["reindex_required"] is True and stats["previous_models"] == {f"fastembed:{old_default}": 2}
