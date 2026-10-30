"""House rules for this repository, enforced so they stay true."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
EXAMPLE = ROOT / "examples" / "messages_api_agent.py"
# Spelled in pieces so this file does not trip its own check.
VENDOR_WORDS = ("anth" + "ropic", "cl" + "aude")
OTHER_LABS = ("open" + "ai", "deep" + "mind", "gem" + "ini", "chat" + "gpt", "mis" + "tral")
HYPE = ("revolution", "cutting-edge", "game-chang", "groundbreaking", "state-of-the-art")
EM_DASH = "—"


def repo_files():
    skipped = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "dist", "build"}
    for path in ROOT.rglob("*"):
        parts = set(path.relative_to(ROOT).parts)
        if not path.is_file() or parts & skipped:
            continue
        if any(part.endswith(".egg-info") for part in parts):
            continue
        if path.name != ".DS_Store" and path.suffix in {".py", ".md", ".toml", ".yml", ".yaml", ""}:
            yield path


def test_vendor_words_only_appear_in_the_example():
    for path in repo_files():
        if path == EXAMPLE:
            continue
        text = path.read_text(encoding="utf-8").casefold()
        for word in VENDOR_WORDS:
            assert word not in text, path


def test_example_uses_the_vendor_word_only_for_the_sdk():
    lines = [
        line.strip()
        for line in EXAMPLE.read_text(encoding="utf-8").splitlines()
        if VENDOR_WORDS[0] in line.casefold() or VENDOR_WORDS[1] in line.casefold()
    ]
    assert lines == [
        f"pip install {VENDOR_WORDS[0]}",
        f"import {VENDOR_WORDS[0]}",
        f"sdk = {VENDOR_WORDS[0]}.{VENDOR_WORDS[0].capitalize()}"
        '(api_key=_setting("OVERREACH_API_KEY"))',
    ]


def test_no_other_labs_are_named():
    for path in repo_files():
        text = path.read_text(encoding="utf-8").casefold()
        for word in OTHER_LABS:
            assert word not in text, path


def test_readme_says_no_live_model_has_run_and_has_no_placeholders():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "No live model has been run" in readme
    assert not re.search(r"\b(TODO|TBD|XX+%|coming soon)\b", readme, re.IGNORECASE)


def test_readme_prose_has_no_em_dashes_or_hype():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert EM_DASH not in readme
    for word in HYPE:
        assert word not in readme.casefold()


def test_readme_explains_the_three_decisions():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for needle in ("No judge model", "Paired conditions", "Honest statistics"):
        assert needle in readme


def test_readme_demo_tables_match_real_runs():
    """Every fenced demo block in the README is re-run and compared character by character."""
    import subprocess
    import sys

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```\n\$ overreach-bench ([^\n]+)\n(.*?)```", readme, re.DOTALL)
    assert len(blocks) >= 4
    for command, expected in blocks:
        real = subprocess.run(
            [sys.executable, "-m", "overreach_bench.cli", *command.split()],
            capture_output=True,
            text=True,
            check=False,
        )
        assert real.stdout.strip() == expected.strip(), command


def test_gitignore_covers_caches_and_venvs():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in ("__pycache__/", ".venv/", ".venvs/", ".pytest_cache/", ".ruff_cache/"):
        assert entry in ignored
