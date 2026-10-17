"""Every Python example of the documentation site runs as it is written, in reading order,
and what a comment says a read gives is what it gives."""

import ast
import os
import re
import uuid
from pathlib import Path

import pytest

DOCS = Path(__file__).parents[2] / "docs-site" / "app"
# The pages in the order the site's navigation gives them; each builds on the ones before.
ORDER = [
    "library",
    "history",
    "episodes",
    "learning",
    "coordination",
    "conversations",
    "audit",
    "recall",
    "algorithms",
    "tenants",
    "integrations",
]
# Pages whose examples need more than the library: the MCP server needs the MCP SDK.
ELSEWHERE = {"mcp"}
# A comment after a write says what the first call gave; a second call gives another answer.
WRITES = {"accept", "record", "remember", "update", "say", "hand_off", "learn", "ran", "claim"}
COMMENTED = re.compile(r"^([^=#][^#]*?)\s+#\s*(.+)$")


def blocks(page: str) -> list[str]:
    return re.findall(
        r"```python\n(.*?)```", (DOCS / page / "page.mdx").read_text(encoding="utf-8"), re.DOTALL
    )


def promised(comment: str):
    """The Python value a comment starts with, or None when it starts with words."""
    for end in range(len(comment), 0, -1):
        try:
            return ast.literal_eval(comment[:end])
        except (ValueError, SyntaxError):
            continue
    return None


pytestmark = pytest.mark.skipif(not DOCS.exists(), reason="the documentation site is not here")


def test_every_page_with_examples_is_run():
    pages = {path.parent.name for path in DOCS.glob("*/page.mdx") if blocks(path.parent.name)}
    assert pages == set(ORDER) | ELSEWHERE


def test_the_examples_run_and_say_what_they_give(db):
    name = f"test_docs_{uuid.uuid4().hex}"
    port = os.environ.get("FALKORDB_PORT", "26379")
    space: dict = {"__name__": "docs_examples"}
    try:
        for page in ORDER:
            for n, block in enumerate(blocks(page), 1):
                code = block.replace("port=6379", f"port={port}")
                code = code.replace('select_graph("world")', f'select_graph("{name}")')
                # The code is this repository's own documentation, run as a reader would.
                exec(compile(code, f"{page} example {n}", "exec"), space)  # noqa: S102
                for line in code.splitlines():
                    found = COMMENTED.match(line)
                    if not found or "(" not in found.group(1):
                        continue
                    expression = found.group(1).strip()
                    call = re.match(r"(\w+)\(", expression)
                    if expression.startswith(("from ", "import ", "def ", "for ")) or (
                        call and call.group(1) in WRITES
                    ):
                        continue
                    said = promised(found.group(2))
                    if said is not None:
                        assert eval(expression, space) == said, f"{page} example {n}: {line}"
    finally:
        db.select_graph(name).delete()
