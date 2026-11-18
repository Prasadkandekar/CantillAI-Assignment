"""The engine package imports only the standard library and rapidfuzz."""
import ast
import sys

from tests.static_checks import engine_files

ALLOWED_THIRD_PARTY = {"rapidfuzz"}
FORBIDDEN = {"fastapi", "starlette", "sqlalchemy", "pydantic", "httpx", "requests", "psycopg", "alembic",
             "api", "services", "db", "seed", "socket", "urllib", "http"}


def imported_roots(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def test_engine_imports_are_pure():
    bad = []
    for f in engine_files():
        for root in imported_roots(f):
            if root in FORBIDDEN:
                bad.append(f"{f.name}: {root}")
            elif root not in sys.stdlib_module_names and root not in ALLOWED_THIRD_PARTY:
                bad.append(f"{f.name}: {root} (not stdlib)")
    assert bad == []
