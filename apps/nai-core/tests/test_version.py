"""The version number agrees across the app, README, CHANGELOG and NithronOS template."""

from __future__ import annotations

import json
import re
from pathlib import Path

from app import __version__
from app.config import Settings

REPO = Path(__file__).resolve().parents[3]


def _semver(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def test_package_version_matches_settings() -> None:
    assert __version__ == Settings.model_fields["app_version"].default


def test_readme_badge_shows_app_version() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    badge = re.search(r"badge/nAI-v(\d+\.\d+\.\d+)-", readme)
    assert badge, "version badge not found in README.md"
    assert badge.group(1) == __version__


def test_changelog_has_section_for_app_version() -> None:
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(rf"^## \[{re.escape(__version__)}\]", changelog, re.M)


def test_nithronos_template_points_at_a_released_version_not_newer_than_app() -> None:
    schema = json.loads((REPO / "packaging/nithronos/nai/schema.json").read_text(encoding="utf-8"))
    compose = (REPO / "packaging/nithronos/nai/compose.yaml").read_text(encoding="utf-8")
    catalog = (REPO / "packaging/nithronos/catalog-entry.yaml").read_text(encoding="utf-8")
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")

    template_versions = set(re.findall(r"NAI_VERSION:-(\d+\.\d+\.\d+)", compose))
    template_versions |= set(re.findall(r'version:\s*"(\d+\.\d+\.\d+)"', catalog))
    template_versions.add(_find_default_version(schema))
    assert len(template_versions) == 1, f"template disagrees with itself: {sorted(template_versions)}"
    template_version = template_versions.pop()
    assert _semver(template_version) <= _semver(__version__)
    # Every version the template offers (default and the allowed list) must be a dated release.
    offered = set(re.findall(r'"(\d+\.\d+\.\d+)"', json.dumps(schema))) | {template_version}
    dated = set(re.findall(r"^## \[(\d+\.\d+\.\d+)\] [–-] \d{4}-\d{2}-\d{2}", changelog, re.M))
    assert offered <= dated, (
        f"template offers versions without a dated CHANGELOG release: {sorted(offered - dated)}"
    )


def _find_default_version(node: object) -> str:
    """The default of the first schema property whose default looks like a version."""
    if isinstance(node, dict):
        default = node.get("default")
        if isinstance(default, str) and re.fullmatch(r"\d+\.\d+\.\d+", default):
            return default
        for value in node.values():
            found = _find_default_version(value)
            if found:
                return found
    if isinstance(node, list):
        for value in node:
            found = _find_default_version(value)
            if found:
                return found
    return ""
