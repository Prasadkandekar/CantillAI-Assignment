"""Contract applicability, ceiling ledger, selection and debit."""
import copy
from datetime import date
from decimal import Decimal

from engine import build_preferred_list, load_policy
from tests.helpers import by_key, line, master_data, run


def test_pdf_contracts_loaded_at_zero_consumed():
    m = master_data()
    assert len(m.contracts) == 12
    for cid in ("RC-2026-031", "RC-2026-033"):
        c = m.contracts[cid]
        assert c.source == "PDF" and c.consumed_value == 0
    assert m.contracts["RC-2026-031"].value_cap == Decimal(2000000)


def test_ceiling_consumed_in_requirement_date_order(policy_doc):
    # RC-2026-002 (ITM-1022, rate 579.62) has 38000 left. The earlier requirement uses it even though
    # it comes later in the file; the later one no longer fits.
    lines = [line("PR-T-002", "2026-11-03 10:00", "CHK1", "ITM-1022", 10, "NOS", "2026-11-20"),
             line("PR-T-001", "2026-11-02 10:00", "PUN1", "ITM-1022", 60, "NOS", "2026-11-20")]
    r = by_key(run(policy_doc, lines, include_sample=False))
    assert r["PR-T-001/1"].route == "CONTRACT_PO" and r["PR-T-001/1"].supplier_id == "S013"
    assert r["PR-T-002/1"].route != "CONTRACT_PO"


def test_lowest_rate_that_fits(policy_doc):
    # ITM-1009: RC-2026-015 (6.45, 12000 left) beats RC-2026-013 (7.06) when it fits
    r = by_key(run(policy_doc, [line("PR-T-001", "2026-11-02 10:00", "PUN1", "ITM-1009", 1000, "NOS", "2026-11-20")],
                   include_sample=False))
    assert (r["PR-T-001/1"].supplier_id, r["PR-T-001/1"].unit_price) == ("S006", "6.45")
    r = by_key(run(policy_doc, [line("PR-T-001", "2026-11-02 10:00", "PUN1", "ITM-1009", 3000, "NOS", "2026-11-20")],
                   include_sample=False))
    assert (r["PR-T-001/1"].supplier_id, r["PR-T-001/1"].unit_price) == ("S007", "7.06")


def test_blocked_supplier_contract_skipped(baseline):
    d = baseline.decisions[by_key(baseline)["PR-26-00050/1"].group_id]
    assert {"contract_id": "RC-2026-005", "reason": "supplier S004 status Blocked"} in d.trace["contracts"]["skipped"]
    assert d.trace["contracts"]["applicable"] == []
    assert "RC-2026-005 skipped" in by_key(baseline)["PR-26-00050/1"].reason


def test_expired_contract_not_applicable_but_supplier_still_preferred(policy_doc):
    res = run(policy_doc, [line("PR-T-001", "2026-11-05 10:00", "PUN1", "ITM-1052", 1, "BRL", "2026-11-20")],
              include_sample=False)
    row = by_key(res)["PR-T-001/1"]
    d = res.decisions[row.group_id]
    assert d.trace["contracts"]["applicable"] == []
    assert any(s["contract_id"] == "RC-2025-020" and s["reason"].startswith("not valid")
               for s in d.trace["contracts"]["skipped"])
    pl = build_preferred_list("ITM-1052", date(2026, 11, 5), master_data(), load_policy(policy_doc).params)
    s033 = [r for r in pl if r.supplier_id == "S033"]
    assert s033 and s033[0].has_contract


def test_debit_uses_contract_rate(policy_doc):
    doc = copy.deepcopy(policy_doc)
    doc["parameters"]["valuation_ladder"] = ["last_po", "contract", "standard_price"]
    res = run(doc)
    row = by_key(res)["PR-26-00019/1"]
    d = res.decisions[row.group_id]
    assert row.route == "CONTRACT_PO" and row.unit_price == "9168.71"
    assert d.trace["valuation"]["source"] == "last_po"
    qty = sum(l.quantity for r in res.requirements if r.group_id == row.group_id for l in r.lines)
    assert d.debit == (qty * Decimal("9168.71")).quantize(Decimal("0.01"))
    assert Decimal(row.group_value_inr) != d.debit
    # the ledger moved by exactly the sum of the debits for this contract
    m = master_data()
    debits = sum(x.debit for x in res.decisions.values() if x.contract_id == "RC-2025-011")
    assert res.ledger["RC-2025-011"] == m.contracts["RC-2025-011"].consumed_value + debits
