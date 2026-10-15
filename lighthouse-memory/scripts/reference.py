"""The API reference of the documentation site, read from the package: every public name of
`lighthouse`, grouped by the module it is defined in, with its signature and docstring.

    python scripts/reference.py ../docs-site/app/reference.json

tests/test_reference.py fails when the file is not what this script writes now.
"""

import inspect
import json
import sys
from pathlib import Path

import lighthouse

# The modules in the order the package docstring names them; a module not here comes last.
ORDER = [
    "kinds", "graphs", "write", "read", "recall", "episodes", "extraction", "handoffs",
    "lessons", "playbooks", "promotion", "algorithms", "conversation", "tasks", "clock",
]  # fmt: skip


def _section(module: str) -> str:
    """The part of the package a name belongs to: lighthouse.write.batches is "write"."""
    return module.split(".")[1]


def reference() -> dict:
    sections: dict[str, list] = {}
    for name in sorted(lighthouse.__all__):
        thing = getattr(lighthouse, name)
        module = getattr(thing, "__module__", None) if callable(thing) else None
        if callable(thing):
            kind = "class" if inspect.isclass(thing) else "function"
            signature = str(inspect.signature(thing))
            doc = inspect.getdoc(thing) or ""
        else:
            kind, signature, doc = "constant", "", f"= {thing!r}"
            module = "lighthouse.kinds" if name == "SELF" else "lighthouse.graphs"
        sections.setdefault(_section(module), []).append(
            {"name": name, "kind": kind, "signature": signature, "doc": doc}
        )
    order = {part: n for n, part in enumerate(ORDER)}
    return {
        "package": "lighthouse",
        "sections": [
            {
                "part": part,
                "about": (inspect.getdoc(sys.modules[f"lighthouse.{part}"]) or "").split("\n\n")[0],
                "names": names,
            }
            for part, names in sorted(sections.items(), key=lambda kv: order.get(kv[0], 99))
        ],
    }


def text() -> str:
    return json.dumps(reference(), indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    Path(sys.argv[1]).write_text(text())
