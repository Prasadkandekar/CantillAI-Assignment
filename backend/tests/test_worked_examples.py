"""Golden tests: the 14 worked examples of Worked_Examples.pdf under policy v5.0."""
import re
from decimal import Decimal

import pytest

from tests.helpers import by_key, fired_rule

# (example, lines, item, decision, route, supplier, unit_price, group_value, suggestions, pdf value, rule)
EXAMPLES = [
    (1, ["PR-26-00019/1"], "ITM-1002", "PO", "CONTRACT_PO", "S001", "9168.71", "137530.65", "", 137531, "5.2"),
    (2, ["PR-26-00045/1"], "ITM-1037", "PO", "CONTRACT_PO", "S021", "2439.01", "26829.11", "", 26829, "5.2"),
    (3, ["PR-26-00004/1", "PR-26-00026/1"], "ITM-1022", "SOURCING_REQUEST", "RFQ", "", "", "220255.60",
     "S014;S013;S016", 220256, "5.5"),
    (4, ["PR-26-00034/1", "PR-26-00032/1"], "ITM-1009", "PO", "CONTRACT_PO", "S007", "7.06", "32546.60", "", 32547, "5.2"),
    (5, ["PR-26-00146/1", "PR-26-00144/1", "PR-26-00145/1"], "ITM-1038", "PO", "SPOT_PO", "S024", "166.41",
     "126471.60", "", 126472, "5.4"),
    (6, ["PR-26-00106/1"], "ITM-1044", "PO", "SPOT_PO", "S027", "21.59", "156170.30", "", 156170, "5.4"),
    (6, ["PR-26-00103/1"], "ITM-1044", "PO", "SPOT_PO", "S027", "21.59", "137311.20", "", 137311, "5.4"),
    (7, ["PR-26-00088/1"], "ITM-1035", "PO", "SPOT_PO", "S023", "391.82", "97955.00", "", 97955, "5.4"),
    (8, ["PR-26-00059/1"], "ITM-1026", "PO", "EMERGENCY_PO", "S014", "106.38", "253184.40", "", 253184, "5.3"),
    (9, ["PR-26-00089/1"], "ITM-1066", "SOURCING_REQUEST", "RFQ", "", "", "336562.15", "S043;S044;S042", 336562, "5.5"),
    (10, ["PR-26-00050/1"], "ITM-1006", "SOURCING_REQUEST", "RFQ", "", "", "80300.00", "S003;S002;S005", 80300, "5.5"),
    (11, ["PR-26-00100/1"], "ITM-1034", "SOURCING_REQUEST", "RFP", "", "", "2070780.00", "S020;S017;S019;S018",
     2070780, "5.6"),
    (12, ["PR-26-00047/1"], "ITM-1071", "SOURCING_REQUEST", "CAPEX_SOURCING", "", "", "6036704.08",
     "S045;S047;S020;S048;S046", 6036704, "5.1"),
    (13, ["PR-26-00170/1"], "NEW", "SOURCING_REQUEST", "NEW_ITEM_SOURCING", "", "", "141100.00", "", 141100, "1.2"),
    (14, ["PR-26-00031/1", "PR-26-00035/1"], "ITM-1009", "PO", "CONTRACT_PO", "S007", "7.06", "23227.40", "", 23227, "5.2"),
]


@pytest.mark.parametrize("ex,lines,item,decision,route,supplier,price,value,sugg,pdf_value,rule", EXAMPLES,
                         ids=[f"ex{e[0]}-{e[1][0]}" for e in EXAMPLES])
def test_worked_example(baseline, ex, lines, item, decision, route, supplier, price, value, sugg, pdf_value, rule):
    rows = by_key(baseline)
    group_ids = {rows[k].group_id for k in lines}
    assert len(group_ids) == 1, "all lines of the example form one requirement"
    group_size = sum(1 for r in baseline.rows if r.group_id in group_ids)
    assert group_size == len(lines)
    for k in lines:
        r = rows[k]
        assert (r.resolved_item_code, r.decision, r.route, r.supplier_id, r.unit_price, r.group_value_inr,
                r.suggested_supplier_ids, r.policy_version) == (item, decision, route, supplier, price, value, sugg, "5.0")
        assert round(Decimal(r.group_value_inr)) == pdf_value
        assert fired_rule(baseline, k) == rule
        assert r.reason.startswith(f"v5.0 \u00a7{rule}")
        if decision == "PO":
            assert re.fullmatch(r"PO-\d{4}", r.po_id)
        else:
            assert r.po_id == ""


def _decision(baseline, k):
    return baseline.decisions[by_key(baseline)[k].group_id]


def test_ex1_reason_names_contract(baseline):
    assert "RC-2025-011" in by_key(baseline)["PR-26-00019/1"].reason


def test_ex2_pdf_only_contract(baseline):
    assert _decision(baseline, "PR-26-00045/1").contract_id == "RC-2026-031"


def test_ex3_ceiling_nearly_used_up(baseline):
    d = _decision(baseline, "PR-26-00004/1")
    assert d.trace["facts"]["contract_exists"] is True
    assert d.trace["facts"]["contract_usable"] is False
    assert d.trace["facts"]["contract_remaining_ceiling"] == "38000.00"
    assert d.trace["valuation"]["source"] == "contract" and d.trace["valuation"]["unit_price"] == "579.62"


def test_ex4_lowest_rate_that_fits(baseline):
    d = _decision(baseline, "PR-26-00034/1")
    assert d.contract_id == "RC-2026-013"
    assert "RC-2026-015" in d.trace["contracts"]["applicable"]
    assert "RC-2026-015" not in d.trace["contracts"]["fitting"]


def test_ex5_three_lines_clubbed(baseline):
    assert _decision(baseline, "PR-26-00146/1").trace["facts"]["line_count"] == 3


def test_ex6_different_plants_not_clubbed(baseline):
    rows = by_key(baseline)
    assert rows["PR-26-00106/1"].group_id != rows["PR-26-00103/1"].group_id


def test_ex10_never_bought(baseline):
    d = _decision(baseline, "PR-26-00050/1")
    assert d.trace["facts"]["bought_from_active_365d"] is False
    assert d.trace["valuation"]["source"] == "standard_price"


def test_ex14_shares_po_with_ex4(baseline):
    rows = by_key(baseline)
    assert rows["PR-26-00031/1"].group_id != rows["PR-26-00034/1"].group_id
    assert rows["PR-26-00031/1"].po_id == rows["PR-26-00034/1"].po_id


# Relative PO numbering (the absolute numbers differ by a constant offset, an open item).
PDF_PO_NUMBERS = {"PR-26-00146/1": 1, "PR-26-00106/1": 2, "PR-26-00034/1": 3, "PR-26-00031/1": 3,
                  "PR-26-00019/1": 11, "PR-26-00088/1": 23, "PR-26-00059/1": 24, "PR-26-00045/1": 72}


def test_relative_po_numbering(baseline):
    rows = by_key(baseline)
    num = {k: int(rows[k].po_id.split("-")[1]) for k in PDF_PO_NUMBERS}
    anchor = num["PR-26-00146/1"]
    for k, pdf in PDF_PO_NUMBERS.items():
        assert num[k] - anchor == pdf - PDF_PO_NUMBERS["PR-26-00146/1"], k
