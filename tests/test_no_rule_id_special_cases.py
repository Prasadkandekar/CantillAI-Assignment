"""The engine never special-cases a rule id or clause."""
from tests.static_checks import engine_files, rule_id_hits, rule_ids_and_clauses


def test_engine_has_no_rule_id_special_cases():
    ids = rule_ids_and_clauses()
    assert {"1.2", "5.1", "5.2", "5.3", "5.4", "5.5", "5.6"} <= ids
    hits = [h for f in engine_files() for h in rule_id_hits(f, ids)]
    assert hits == [], "\n".join(hits)


def test_self_check_flags_fstring_and_comparisons(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text('a = f"5.3"\nif rule.id == x: pass\nif r["clause"] != y: pass\nif r.get("id") in z: pass\n',
                   encoding="utf-8")
    hits = rule_id_hits(bad, rule_ids_and_clauses())
    assert any("'5.3'" in h for h in hits)
    assert sum("comparison" in h for h in hits) == 3
