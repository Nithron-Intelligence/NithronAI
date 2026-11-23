# Contributing to nAI

Thanks for helping. This file covers setup, checks, conventions and the licensing rules every change must
follow. How the code works: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Known problems and ideas:
[docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md).

## Handoff rule

Work here is shared between people and AI agents across sessions. **Every agent session must update
[docs/HANDOFF.md](docs/HANDOFF.md) before it ends**: Status (including half-finished work and the next
command), History, and Waiting on the human. Start every session by reading it.

## Development setup

```bash
cd apps/nai-core
uv venv -p 3.11 .venv && source .venv/bin/activate
uv pip install -r requirements-full.txt pytest pytest-asyncio httpx ruff==0.17.6 mypy
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"
uvicorn app.main:app --reload --port 8000               # UI + API on http://localhost:8000
```

Don't use `uv run` inside `apps/nai-core`: uv treats the folder as a project, re-syncs `.venv` (removing
packages) and creates a `uv.lock`. Use `uv venv` + `uv pip install` as above.

Docker image (build context is the repo root; about 1.3 GB with the default `INSTALL_FULL=true`,
`INSTALL_FULL=false` gives a smaller search-only image):

```bash
docker build -f apps/nai-core/Dockerfile -t nai-core .
```

## Checks (all blocking in CI)

```bash
cd apps/nai-core
pytest -q                                                    # no model downloads: tests use fake providers
ruff check app tests && ruff format --check app tests && mypy app

cd ../..                                                     # evals and training code
pytest evals/tests training/tests
ruff check --config apps/nai-core/pyproject.toml evals training
```

If your change affects retrieval or answers, run nai-bench too ([evals/README.md](evals/README.md)) and
include the numbers in the pull request.

## Conventions

- A module docstring at the top of every file. Modern typing (`list[str]`, `X | None`).
- Pydantic response models live in `app/models/schemas.py`. Ingest reports a per-file
  `status: success | skipped | error` instead of raising.
- Sync DB or CPU work called from async routes goes through `run_in_threadpool`. Background work runs in
  daemon threads started in the lifespan.
- New settings that start threads, download models or need binaries get a test default in
  `tests/conftest.py` (`BASE_ENV`).
- Don't name a class method `list`: inside the class body it shadows the builtin and breaks `list[str]`
  annotations.
- Commits: short imperative subject line, a body that says why. Work on a branch; maintainers merge to
  `main`.

## Licensing rules

- nAI is under the **Nithron Community License (NCL) v1.0**
  (SPDX `LicenseRef-Nithron-Community-License-1.0`). `LICENSE` is shared by all Nithron products and must
  stay **byte-identical** to NithronOS's `LICENSE`; product-specific text goes in `NOTICE`. See also
  `COMMERCIAL.md`, `TRADEMARK_POLICY.md` and `BINARIES-EULA.md`. Versions up to `66fa142` were
  AGPL-3.0-only (see `NOTICE`).
- **No AGPL or GPL dependencies** in anything nAI ships. PyMuPDF (AGPL) was rejected: nAI uses pypdf and
  pypdfium2. poppler (GPL, e.g. via pdf2image) must not be added.
- Models, datasets and ML tools: record them in
  [docs/lab/MODEL_AND_DATA_LICENSES.md](docs/lab/MODEL_AND_DATA_LICENSES.md) before use, and follow the
  [lab principles](docs/lab/ROADMAP.md#principles), including: no training data generated with services
  whose terms forbid it, and nothing from `evals/nai-bench/` in training data.

## Releases

See [docs/RELEASING.md](docs/RELEASING.md).
