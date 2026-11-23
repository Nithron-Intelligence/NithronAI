"""
nAI Core Test Configuration
Pytest fixtures and configuration
"""

import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Generator

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

# Base environment for the whole session. Set before any app module is imported so the
# module-level `app = create_app()` in app.main never touches the real data directory.
_SESSION_DATA_DIR = tempfile.mkdtemp(prefix="nai-test-")
BASE_ENV = {
    "NAI_DEBUG": "true",
    "NAI_DATA_DIR": _SESSION_DATA_DIR,
    "NAI_LLM_ENABLED": "false",
    "NAI_EMBEDDINGS_ENABLED": "false",
    "NAI_EMBEDDINGS": "on",  # deterministic: no memory-based auto decision unless a test asks for it
    "NAI_AUTH_ENABLED": "false",
    "NAI_RATE_LIMIT_ENABLED": "false",
    # No background threads, model downloads or system binaries unless a test opts in
    "NAI_SOURCES_BACKGROUND": "false",
    "NAI_RERANKER": "false",
    "NAI_OCR_ENABLED": "false",
}
os.environ.update(BASE_ENV)


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_SESSION_DATA_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def test_data_dir() -> str:
    return _SESSION_DATA_DIR


@pytest.fixture(scope="session")
def app():
    """Shared application (auth disabled) using the session data directory."""
    from app.main import create_app
    from app.services import reset_services

    reset_services()
    return create_app()


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_client(tmp_path, monkeypatch) -> Generator[Callable[..., TestClient], None, None]:
    """
    Factory for an isolated app with its own data directory and settings overrides,
    e.g. ``make_client(NAI_AUTH_ENABLED="true")``. Services are reset afterwards so the
    shared ``client`` fixture is unaffected.
    """
    from app.main import create_app
    from app.services import reset_services

    clients: list[TestClient] = []

    def factory(**env: str) -> TestClient:
        monkeypatch.setenv("NAI_DATA_DIR", str(tmp_path / "data"))
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        reset_services()
        c = TestClient(create_app())
        c.__enter__()
        clients.append(c)
        return c

    yield factory

    for c in clients:
        c.__exit__(None, None, None)
    reset_services()


@pytest.fixture
def sample_text_file(test_data_dir) -> str:
    """Create a sample text file for testing."""
    content = """
    This is a sample document for testing nAI.

    It contains multiple paragraphs with different topics.
    The first topic is about artificial intelligence and machine learning.

    The second paragraph discusses document retrieval and search algorithms.
    BM25 is a popular ranking function used in information retrieval.

    Finally, we talk about natural language processing and embeddings.
    Vector representations help capture semantic meaning of text.
    """
    filepath = os.path.join(test_data_dir, "sample_test.txt")
    with open(filepath, "w") as f:
        f.write(content)
    return filepath


# ---------------------------------------------------------------------------
# Phase 1 helpers: fake embedding model and a fake NAS share
# ---------------------------------------------------------------------------

# Words in the same group get the same vector dimension, so "automobile" matches "car"
# semantically even though BM25 sees no shared term.
SYNONYM_GROUPS = [
    {"car", "automobile", "vehicle", "auto"},
    {"insurance", "policy", "coverage"},
    {"invoice", "bill", "receipt"},
    {"holiday", "vacation", "trip"},
    {"router", "network", "wifi"},
]


class FakeEmbeddingProvider:
    name = "fake"
    model = "fake-synonyms"

    def __init__(self, settings=None):
        pass

    def _vector(self, text: str):
        import numpy as np

        vec = np.zeros(len(SYNONYM_GROUPS) + 1, dtype=np.float32)
        for word in text.lower().replace(".", " ").replace(",", " ").split():
            for i, group in enumerate(SYNONYM_GROUPS):
                if word in group:
                    vec[i] += 1.0
        vec[-1] = 0.01  # never an all-zero vector
        return vec

    def embed_documents(self, texts):
        import numpy as np

        return np.stack([self._vector(t) for t in texts])

    def embed_query(self, text):
        return self._vector(text)


@pytest.fixture
def fake_embeddings() -> dict[str, str]:
    """Env overrides that enable semantic search with the fake provider."""
    from app.services.embeddings import register_provider

    register_provider("fake", FakeEmbeddingProvider)
    return {
        "NAI_EMBEDDINGS_ENABLED": "true",
        "NAI_EMBEDDINGS_PROVIDER": "fake",
        "NAI_EMBEDDINGS_MIN_SCORE": "0.3",
        "NAI_EMBEDDINGS_BACKGROUND": "false",  # tests call embed_pending() themselves
    }


@pytest.fixture
def share(tmp_path) -> tuple[str, dict[str, str]]:
    """A folder standing in for a NAS share, plus env that allows it as a source root."""
    import json

    root = tmp_path / "shares"
    (root / "Documents").mkdir(parents=True)
    return str(root), {"NAI_SOURCES_ALLOWED_ROOTS": json.dumps([str(root)])}
