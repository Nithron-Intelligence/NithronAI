"""The web interface stays on the Nithron identity (nithron-site DESIGN-APPS.md, settled 2026-11-27).

nAI's interface is static files with no package manager, so there is no lint tool; this test is the lint rule.
Colours come only from the copied tokens file (nithron-tokens.css): anywhere else under web/ a hex value, a
colour function or a hue's name fails, and so does the main colour (the interface has no hue: it is ink).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
WEB = REPO / "apps" / "nai-docs" / "web"
TOKENS = WEB / "nithron-tokens.css"  # copied whole from @nithron/tokens, never edited
CHECKED_SUFFIXES = {".css", ".js", ".html", ".svg"}

HEX = re.compile(r"(?<![\w&])(?:#|%23)(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")
COLOUR_FUNCTION = re.compile(r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch)\(", re.IGNORECASE)
HUES = (
    "red|orange|yellow|green|blue|indigo|violet|purple|pink|magenta|fuchsia|cyan|aqua|teal|turquoise|lime|"
    "olive|amber|emerald|gold|golden|bronze|crimson|scarlet|navy|maroon|coral|salmon|brown|beige|khaki"
)
HUE_NAME = re.compile(rf"\b(?:{HUES})\b", re.IGNORECASE)
MAIN_COLOUR = re.compile(r"var\(\s*--main")


def _web_files() -> list[Path]:
    return sorted(p for p in WEB.rglob("*") if p.suffix in CHECKED_SUFFIXES and p != TOKENS)


def _findings(pattern: re.Pattern[str]) -> list[str]:
    found = []
    for path in _web_files():
        for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
            for match in pattern.finditer(line):
                found.append(f"{path.relative_to(WEB)}:{number}: {match.group(0)}")
    return found


def test_the_checked_files_exist() -> None:
    names = {p.name for p in _web_files()}
    assert {"index.html", "styles.css", "main.js", "icons.js"} <= names


@pytest.mark.parametrize(
    ("what", "pattern"),
    [
        ("hex colour", HEX),
        ("colour function", COLOUR_FUNCTION),
        ("hue name", HUE_NAME),
        ("main colour (use ink)", MAIN_COLOUR),
    ],
)
def test_no_colour_outside_the_tokens(what: str, pattern: re.Pattern[str]) -> None:
    assert _findings(pattern) == [], f"{what} outside nithron-tokens.css; map onto a token instead"


def test_the_guard_patterns_catch_what_they_should() -> None:
    assert HEX.search("color: #6366f1;") and HEX.search("stroke='%2322d3ee'") and HEX.search("#fff;")
    assert not HEX.search("getElementById('askBtn')") and not HEX.search("&#123;")
    assert COLOUR_FUNCTION.search("background: rgba(0, 0, 0, 0.6);")
    assert HUE_NAME.search("color: Teal;")
    assert not HUE_NAME.search("redirect, credentials, predicted, bluetooth, reddish")
    assert MAIN_COLOUR.search("border-color: var(--main-text);")


def test_tokens_are_a_whole_named_copy_linked_first() -> None:
    first_line = TOKENS.read_text("utf-8").splitlines()[0]
    assert re.match(r"/\* @nithron/tokens \d+\.\d+\.\d+ \(dist/line\.css\)", first_line)
    html = (WEB / "index.html").read_text("utf-8")
    assert (
        html.index('href="nithron-tokens.css"')
        < html.index('href="fonts/fonts.css"')
        < html.index('href="styles.css"')
    )


def test_fonts_ship_with_their_licences() -> None:
    fonts = WEB / "fonts"
    files = {p.name for p in fonts.iterdir()}
    assert any(n.startswith("mona-sans") for n in files) and any(
        n.startswith("monaspace-neon") for n in files
    )
    for family in ("mona-sans", "monaspace-neon"):
        licence = (fonts / f"OFL-{family}.txt").read_text("utf-8")
        assert "SIL Open Font License" in licence
    css = (fonts / "fonts.css").read_text("utf-8")
    for name in files - {"fonts.css", "OFL-mona-sans.txt", "OFL-monaspace-neon.txt"}:
        assert name in css, f"{name} is shipped but no @font-face uses it"


def test_icons_go_through_the_one_map() -> None:
    html = (WEB / "index.html").read_text("utf-8")
    script = (WEB / "main.js").read_text("utf-8")
    assert "<svg" not in html and "<svg" not in script, (
        "icons belong in icons.js (one place for the pixel set)"
    )


def test_destructive_actions_use_nai_dialog() -> None:
    script = (WEB / "main.js").read_text("utf-8")
    assert not re.search(r"(?<![\w.])confirm\(|window\.confirm\(", script), (
        "use confirmDialog() from dialog.js"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js to run the web UI's scanner")
def test_code_scanner_colours_only_what_it_can_read() -> None:
    script = (WEB / "markdown.js").read_text("utf-8") + (
        "\nconsole.log(JSON.stringify(["
        "scanCode('x = 42  # n', 'python'),"
        "scanCode('echo $# ${#a}', 'bash'),"
        "scanCode(\"It's 3\", ''),"
        "scanCode('<b>1</b>', 'html'),"
        "renderMarkdown('use `x = 1` here'),"
        "]));"
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True, timeout=30)
    python, shell, prose, html, inline = json.loads(result.stdout)
    assert '<span class="tok-number">42</span>' in python and '<span class="tok-comment"># n</span>' in python
    assert "tok-comment" not in shell  # $# and ${#a} are not comments
    assert "tok-string" not in prose  # an apostrophe in prose is not a string
    assert html is None  # a language the scanner cannot read stays plain
    assert "tok-" not in inline  # inline code stays ink
