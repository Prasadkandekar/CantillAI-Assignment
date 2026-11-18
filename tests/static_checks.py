"""Static checks over engine source: policy literals and rule-id comparisons."""
from __future__ import annotations

import ast
import io
import json
import re
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine"
POLICY_NUMBERS = {200000, 500000, 1000000, 14, 7, 24, 365, 548}
POLICY_NUMBER_RE = re.compile(r"\b(200000|500000|1000000|14|7|24|365|548)\b")


def engine_files():
    return sorted(ENGINE.rglob("*.py"))


def string_constants(tree):
    """Plain strings, docstrings and the literal parts of f-strings."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


def literal_hits(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    hits = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.NUMBER:
            try:
                value = ast.literal_eval(tok.string)
            except ValueError:
                continue
            if not isinstance(value, complex) and value in POLICY_NUMBERS:
                hits.append(f"{path.name}:{tok.start[0]}: number {tok.string}")
        elif tok.type == tokenize.COMMENT and POLICY_NUMBER_RE.search(tok.string):
            hits.append(f"{path.name}:{tok.start[0]}: comment {tok.string.strip()}")
    for lineno, text in string_constants(ast.parse(src)):
        if POLICY_NUMBER_RE.search(text):
            hits.append(f"{path.name}:{lineno}: string {text!r}")
    return hits


def rule_ids_and_clauses() -> set[str]:
    doc = json.loads((ENGINE / "policies" / "policy_v5_0.json").read_text(encoding="utf-8"))
    return {r["id"] for r in doc["rules"]} | {r["clause"] for r in doc["rules"]}


def _is_id_ref(node) -> bool:
    if isinstance(node, ast.Attribute) and node.attr in ("id", "clause"):
        return True
    if isinstance(node, ast.Subscript):
        key = node.slice
        return isinstance(key, ast.Constant) and key.value in ("id", "clause")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
        return bool(node.args) and isinstance(node.args[0], ast.Constant) and node.args[0].value in ("id", "clause")
    return False


def rule_id_hits(path: Path, ids: set[str]) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits = [f"{path.name}:{ln}: string {s!r} equals a rule id/clause" for ln, s in string_constants(tree) if s in ids]
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            sides = [node.left, *node.comparators]
            if any(_is_id_ref(s) for s in sides):
                hits.append(f"{path.name}:{node.lineno}: comparison on rule id/clause")
    return hits
