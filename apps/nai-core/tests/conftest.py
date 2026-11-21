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
    "NAI_AUTH_ENABLED": "false",
    "NAI_RATE_LIMIT_ENABLED": "false",
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
