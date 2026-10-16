"""Rules for the shape of the package. They keep it readable and closed as it grows.

`violations()` reads the source of a package and lists every broken rule. One test applies
it to the real package. The others plant one violation each in a copy and check that it is
found, so a rule that stops working is noticed.
"""

import ast
import pathlib
import re
import shutil
import sys
import tomllib

import pytest

import lighthouse

ROOT = pathlib.Path(__file__).parent.parent
SOURCE = ROOT / "lighthouse"
TESTS = ROOT / "tests"

MAX_LINES = 400
VAGUE_NAMES = {"utils", "util", "utilities", "helpers", "helper", "common", "misc", "core", "base"}
VAGUE_NAMES |= {"manager", "tools", "shared", "support", "lib", "internals", "service", "services"}
DRIVER_NAMES = {"driver", "drivers", "backend", "backends", "adapter", "adapters", "dialect"}
DRIVER_NAMES |= {
    "dialects",
    "queries",
    "neo4j",
    "kuzu",
    "neptune",
    "memgraph",
    "postgres",
    "sqlite",
}
SERVER_NAMES = {"server", "api", "app", "cli", "main", "__main__", "routes", "mcp"}

ALLOWED_PACKAGES = {"lighthouse", "falkordb", "redis"}
# The package talks to the graph it is given and to nothing else: no network, no process,
# no file, no environment, and no way to load code that the checks below cannot see.
CLOSED_MODULES = {"urllib", "http", "socket", "ssl", "subprocess", "smtplib", "ftplib", "xmlrpc"}
CLOSED_MODULES |= {"os", "sys", "dotenv", "webbrowser", "multiprocessing", "asyncio", "threading"}
CLOSED_MODULES |= {"importlib", "builtins", "ctypes", "pickle", "marshal", "shelve", "runpy"}
CLOSED_MODULES |= {"pathlib", "shutil", "tempfile", "glob", "io", "code", "pty", "signal"}
# Built-in functions that run text as code or reach past the checks, called by their name.
CLOSED_BUILTINS = {"eval", "exec", "compile", "__import__", "open", "input", "breakpoint"}
CLOSED_BUILTINS |= {"globals", "locals", "vars", "getattr", "setattr", "delattr"}
# Calls that open a database connection or send a raw command, by name or as a method.
CLOSED_CALLS = {"FalkorDB", "Redis", "StrictRedis", "from_url", "ConnectionPool", "Connection"}
CLOSED_CALLS |= {"execute_command", "import_module"}
CLOSED_NAMES = {"__builtins__", "__loader__", "__spec__"}

PRODUCT_WORDS = re.compile(
    r"vessel|berth|port.?call|locode|\bimo\b|digitraffic|\bports?\b|(?<!relation)ship",
    re.IGNORECASE,
)
MODEL_WORDS = re.compile(
    r"openai|anthropic|claude|\bgpt|gemini|llama|mistral|cohere|voyage|ollama|hugging.?face"
    r"|bedrock|vertex|sentence.?transformers|api.?key",
    re.IGNORECASE,
)
CYPHER = re.compile(
    r"\b(MATCH|MERGE|CREATE) \(|\bUNWIND \$|\bCALL db\.|\bRETURN \w|\bDETACH DELETE\b",
    re.IGNORECASE,
)


def docstrings(tree: ast.AST) -> set[int]:
    return {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }


def violations(package: pathlib.Path, tests: pathlib.Path) -> list[str]:
    """Every broken rule in a package, as "rule: file: what"."""
    found = []
    for path in sorted(package.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        name = path.relative_to(package).as_posix()
        if path.stem in VAGUE_NAMES:
            found.append(f"vague name: {name}: name it after what it does")
        if path.stem in DRIVER_NAMES:
            found.append(f"driver layer: {name}: one database, no driver and no query store")
        if path.stem in SERVER_NAMES:
            found.append(f"server: {name}: a server is a separate project")
        if path.is_file() and path.suffix != ".py":
            found.append(f"not python: {name}: the package holds source files only")
        if path.suffix != ".py" or not path.is_file():
            continue

        text = path.read_text()
        tree = ast.parse(text)
        lines = len(text.splitlines())
        if lines > MAX_LINES:
            found.append(f"too long: {name}: {lines} lines, split it by what it does")
        if not text.lstrip().startswith('"""'):
            found.append(f"no docstring: {name}")
        if word := PRODUCT_WORDS.search(text):
            found.append(f"product word: {name}: {word[0]!r}")
        if word := MODEL_WORDS.search(text):
            found.append(f"model provider: {name}: {word[0]!r}")

        sends, holds = False, False
        skipped = docstrings(tree)
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                modules = [node.module.split(".")[0]]
            for module in modules:
                if module in CLOSED_MODULES:
                    found.append(f"closed module: {name}: imports {module}")
                elif module not in ALLOWED_PACKAGES and module not in sys.stdlib_module_names:
                    found.append(f"dependency: {name}: imports {module}")
            if isinstance(node, ast.Call):
                by_name = node.func.id if isinstance(node.func, ast.Name) else None
                called = by_name or getattr(node.func, "attr", None)
                if by_name in CLOSED_BUILTINS or called in CLOSED_CALLS:
                    found.append(f"closed call: {name}: calls {called}()")
                # pages() of read.py sends a read query a page at a time.
                if called in {"query", "ro_query", "pages"}:
                    sends = True
            if isinstance(node, ast.Name) and node.id in CLOSED_NAMES:
                found.append(f"closed name: {name}: uses {node.id}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                holds = holds or (id(node) not in skipped and bool(CYPHER.search(node.value)))
        if sends != holds:
            what = "sends a query it does not hold" if sends else "holds a query it does not send"
            found.append(f"query placement: {name}: {what}")

        if path.stem != "__init__":
            test = tests / f"test_{path.stem}.py"
            if not test.exists():
                found.append(f"no test file: {name}: tests/test_{path.stem}.py is missing")
            elif not re.search(r"^def test_\w+\(", test.read_text(), re.MULTILINE):
                found.append(f"empty test file: {name}: tests/test_{path.stem}.py has no test")
    return found


def test_package_follows_every_rule():
    assert violations(SOURCE, TESTS) == []
    assert len(list(SOURCE.glob("*.py"))) >= 9  # the check did look at the package


# Each case: the rule that must report it, the file to add or extend, and its content.
ADD, APPEND = "add", "append"
PLANTED = {
    "a module that only holds queries": (
        "driver layer",
        ADD,
        "queries.py",
        '"""Q."""\nFIND = "MATCH (n) RETURN n"\n',
    ),
    "a query nobody sends": (
        "query placement",
        APPEND,
        "kinds.py",
        '\nLOOK = "MATCH (n:Thing) RETURN n"\n',
    ),
    "a query in lower case nobody sends": (
        "query placement",
        APPEND,
        "kinds.py",
        '\nLOOK = "match (n:Thing) return n"\n',
    ),
    "a delete nobody sends": (
        "query placement",
        APPEND,
        "clock.py",
        '\nWIPE = "MATCH (n) DETACH DELETE n"\n',
    ),
    "a module that forwards queries": (
        "query placement",
        APPEND,
        "clock.py",
        "\n\ndef run(graph, text):\n    return graph.query(text)\n",
    ),
    "a driver folder": ("driver layer", ADD, "driver/__init__.py", '"""Driver."""\n'),
    "a module for another database": ("driver layer", ADD, "neo4j.py", '"""Other."""\n'),
    "a second database client": ("dependency", APPEND, "clock.py", "\nimport neo4j\n"),
    "a helpers module": ("vague name", ADD, "helpers.py", '"""Helpers."""\n'),
    "a utilities folder": ("vague name", ADD, "utilities/__init__.py", '"""Utilities."""\n'),
    "a module that is too long": ("too long", ADD, "long.py", '"""Long."""\n' + "X = 1\n" * 400),
    "a module without a docstring": ("no docstring", ADD, "bare.py", "X = 1\n"),
    "a network client": ("closed module", APPEND, "clock.py", "\nimport urllib.request\n"),
    "a socket": ("closed module", APPEND, "clock.py", "\nfrom socket import create_connection\n"),
    "an environment read": ("closed module", APPEND, "clock.py", "\nimport os\n"),
    "a process": ("closed module", APPEND, "clock.py", "\nimport subprocess\n"),
    "a file read": ("closed call", APPEND, "clock.py", '\nSECRET = open("/etc/passwd").read()\n'),
    "a file module": ("closed module", APPEND, "clock.py", "\nimport pathlib\n"),
    "an import by name": (
        "closed module",
        APPEND,
        "clock.py",
        '\nimport importlib\nM = importlib.import_module("o" + "s")\n',
    ),
    "an import by call": ("closed call", APPEND, "clock.py", '\nM = __import__("o" + "s")\n'),
    "an import through sys": (
        "closed module",
        APPEND,
        "clock.py",
        '\nimport sys\nM = sys.modules["os"]\n',
    ),
    "an import through builtins": (
        "closed name",
        APPEND,
        "clock.py",
        '\nM = __builtins__["__import__"]("os")\n',
    ),
    "evaluated text": (
        "closed call",
        APPEND,
        "clock.py",
        '\nM = eval("__imp" + "ort__(\'os\')")\n',
    ),
    "executed text": ("closed call", APPEND, "clock.py", '\nexec("import os")\n'),
    "an attribute by name": (
        "closed call",
        APPEND,
        "clock.py",
        '\nM = getattr(stamp, "__glob" + "als__")\n',
    ),
    "unsafe loading of data": ("closed module", APPEND, "clock.py", "\nimport pickle\n"),
    "a model sdk": (
        "dependency",
        APPEND,
        "clock.py",
        "\n\ndef embed(text):\n    import anthropic\n    return anthropic\n",
    ),
    "a provider name": (
        "model provider",
        APPEND,
        "clock.py",
        '\nDEFAULT_MODEL = "text-embedding by OpenAI"\n',
    ),
    "a key for a service": ("model provider", APPEND, "clock.py", '\nAPI_KEY = "sk-123"\n'),
    "a database client of its own": (
        "closed call",
        APPEND,
        "graphs.py",
        '\nOTHER = FalkorDB(host="203.0.113.7")\n',
    ),
    "a client from a url": (
        "closed call",
        APPEND,
        "graphs.py",
        '\n\ndef other(redis):\n    return redis.Redis.from_url("redis://203.0.113.7")\n',
    ),
    "a raw database command": (
        "closed call",
        APPEND,
        "graphs.py",
        '\n\ndef flush(graph):\n    return graph.execute_command("FLUSHALL")\n',
    ),
    "a server module": ("server", ADD, "server.py", '"""Server."""\n'),
    "a main module": ("server", ADD, "__main__.py", '"""Main."""\n'),
    "a command line": ("server", ADD, "cli.py", '"""Command line."""\n'),
    "a product word": ("product word", APPEND, "clock.py", "\n# the vessel arrives\n"),
    "an import from a product": ("dependency", APPEND, "clock.py", "\nfrom app import portcalls\n"),
    "a module without a test file": ("no test file", ADD, "extra.py", '"""Extra."""\n'),
    "a test file without a test": (
        "empty test file",
        ADD,
        "../tests/test_clock.py",
        '"""Nothing."""\n',
    ),
    "a data file": ("not python", ADD, "defaults.json", "{}\n"),
    "a compiled module": ("not python", ADD, "fast.so", "\x7fELF"),
}


@pytest.mark.parametrize("case", PLANTED)
def test_planted_violation_is_found(tmp_path, case):
    rule, how, file, content = PLANTED[case]
    ignore = shutil.ignore_patterns("__pycache__")
    package = shutil.copytree(SOURCE, tmp_path / "lighthouse", ignore=ignore)
    tests = shutil.copytree(TESTS, tmp_path / "tests", ignore=ignore)
    assert violations(package, tests) == []  # the copy is clean before the change
    target = package / file
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content if how == ADD else target.read_text() + content)
    found = violations(package, tests)
    assert any(line.startswith(f"{rule}:") for line in found), found


def test_every_folder_of_the_package_is_in_what_gets_built():
    # A folder that the build does not list works from the source and is missing when installed.
    built = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["setuptools"]["packages"]
    folders = {
        ".".join(path.parent.relative_to(ROOT).parts) for path in SOURCE.rglob("__init__.py")
    }
    assert set(built) == folders and len(built) == len(folders)


def test_name_that_the_database_gives_an_option_is_not_a_product_word():
    assert not PRODUCT_WORDS.search('{"relationshipTypes": types}')
    for text in ("the ship", "shipment", "relation ship", "RelationShips of the fleet, by ship"):
        assert PRODUCT_WORDS.search(text), text


def test_public_names_exist_and_are_documented():
    for name in lighthouse.__all__:
        thing = getattr(lighthouse, name)
        if callable(thing):
            assert thing.__doc__ or name == "now", f"{name} has no docstring"
    assert len(set(lighthouse.__all__)) == len(lighthouse.__all__)
