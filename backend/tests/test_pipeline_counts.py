"""Sanity counts for the sample batch under v5.0 and the output format."""
import subprocess
import sys

from engine import rows_to_csv
from tests.helpers import BACKEND, BATCH_PATH, POLICY_PATH

COLUMNS = ["pr_no", "pr_line", "resolved_item_code", "group_id", "po_id", "decision", "route", "supplier_id",
           "unit_price", "group_value_inr", "suggested_supplier_ids", "policy_version", "reason"]


def test_counts(baseline):
    assert len(baseline.rows) == 186
    assert baseline.counts == {"SPOT_PO": 72, "RFQ": 53, "CONTRACT_PO": 33, "CAPEX_SOURCING": 10, "RFP": 8,
                               "EMERGENCY_PO": 6, "NEW_ITEM_SOURCING": 2, "NOT_PROCESSED": 2}
    assert len(baseline.requirements) == 149
    assert sum(1 for r in baseline.requirements if len(r.lines) > 1) == 23
    assert baseline.requirement_counts == {"SPOT_PO": 58, "RFQ": 39, "CONTRACT_PO": 30, "CAPEX_SOURCING": 10,
                                           "EMERGENCY_PO": 6, "RFP": 4, "NEW_ITEM_SOURCING": 2}
    assert len({r.po_id for r in baseline.rows if r.po_id}) == 82
    assert baseline.versions_used == {"5.0": 186}


def test_rows_in_input_order(baseline, raw_lines):
    assert [(r.pr_no, r.pr_line) for r in baseline.rows] == [(l.values["pr_no"], l.values["pr_line"]) for l in raw_lines]


def test_csv_header_and_format(baseline):
    text = rows_to_csv(baseline.rows)
    lines = text.splitlines()
    assert lines[0].split(",") == COLUMNS
    assert len(lines) == 187


def test_sourcing_and_not_processed_have_no_po(baseline):
    for r in baseline.rows:
        if r.decision != "PO":
            assert r.po_id == "" and r.supplier_id == ""
        else:
            assert r.supplier_id and r.unit_price and r.po_id


def test_every_decision_records_rule_and_facts(baseline):
    for d in baseline.decisions.values():
        assert d.fired_rule and {"id", "clause", "text"} <= set(d.fired_rule)
        assert d.trace["fired"] == d.fired_rule
        assert d.trace["facts"] and d.trace["rules_checked"]
        assert d.trace["rules_checked"][-1]["id"] == d.fired_rule["id"]


def test_cli_run(tmp_path):
    out = tmp_path / "out.csv"
    proc = subprocess.run([sys.executable, "-m", "engine", "run", "--batch", str(BATCH_PATH), "--policy",
                           str(POLICY_PATH), "--out", str(out)], cwd=BACKEND, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert len(out.read_text(encoding="utf-8").splitlines()) == 187


def test_cli_validate():
    proc = subprocess.run([sys.executable, "-m", "engine", "validate", str(POLICY_PATH)], cwd=BACKEND,
                          capture_output=True, text=True)
    assert proc.returncode == 0
    assert "0 errors, 0 warnings" in proc.stdout
