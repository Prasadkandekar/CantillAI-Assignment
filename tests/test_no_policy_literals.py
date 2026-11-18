"""No policy number (limit, window, count) appears in engine code, comments, docstrings or f-strings."""
from tests.static_checks import engine_files, literal_hits


def test_engine_has_no_policy_literals():
    files = engine_files()
    assert len(files) > 10
    hits = [h for f in files for h in literal_hits(f)]
    assert hits == [], "\n".join(hits)


def test_self_check_flags_fstrings_numbers_and_comments(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text('y = 1\nx = f"x 14 y {y}"\nz = 0x18  # within 7 days\nw = 365.0\n', encoding="utf-8")
    hits = literal_hits(bad)
    assert any("string" in h and "14" in h for h in hits)
    assert any("0x18" in h for h in hits)
    assert any("comment" in h for h in hits)
    assert any("365.0" in h for h in hits)
