"""Docs stay true: exported OpenAPI matches the app; relative links in docs point to existing files."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT / "scripts"))

from export_openapi import build_spec  # noqa: E402


def test_exported_openapi_is_up_to_date():
    exported = json.loads((DOCS / "openapi.json").read_text(encoding="utf-8"))
    assert exported == build_spec(), "run: uv run python scripts/export_openapi.py"


@pytest.mark.parametrize("doc", sorted(DOCS.glob("*.md")), ids=lambda p: p.name)
def test_relative_links_exist(doc):
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", doc.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        assert (doc.parent / target).exists(), f"{doc.name}: broken link {target}"
