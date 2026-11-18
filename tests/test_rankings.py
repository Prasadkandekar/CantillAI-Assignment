"""Golden tests: the 3 preferred-supplier rankings of Worked_Examples.pdf, as of 2026-11-01."""
from datetime import date
from decimal import Decimal

import pytest

from engine import build_preferred_list, load_policy, suggestions
from tests.helpers import master_data

AS_OF = date(2026, 11, 1)

RANKINGS = [
    ("ITM-1048", ["S029", "S030"], [7, 4], [True, False], [0.869, 0.619]),
    ("ITM-1036", ["S023", "S022", "S024"], [2, 2, 1], [False, False, False], [0.737, 0.569, 0.434]),
    ("ITM-1016", ["S009", "S010"], [1, 1], [True, False], [0.766, 0.605]),
]


@pytest.fixture(scope="module")
def params(policy_doc):
    return load_policy(policy_doc).params


@pytest.mark.parametrize("item,order,counts,contract,scores", RANKINGS, ids=[r[0] for r in RANKINGS])
def test_ranking(params, item, order, counts, contract, scores):
    pl = build_preferred_list(item, AS_OF, master_data(), params)
    assert [r.supplier_id for r in pl] == order
    assert [r.po_count for r in pl] == counts
    assert [r.has_contract for r in pl] == contract
    assert [r.rank for r in pl] == list(range(1, len(order) + 1))
    for r, s in zip(pl, scores):
        assert float(r.score) == pytest.approx(s, abs=0.005)
        total = sum(f.contribution for f in r.factors.values())
        assert abs(total - r.score) <= Decimal("0.00001")
        for name, f in r.factors.items():
            assert f.weight == Decimal(str(params["ranking_weights"][name]))
            assert abs(f.contribution - f.weight * f.scaled) <= Decimal("0.000001")


def test_inactive_supplier_excluded(params):
    pl = build_preferred_list("ITM-1048", AS_OF, master_data(), params)
    assert "S031" not in [r.supplier_id for r in pl]


def test_reference_price_is_latest_po_else_contract(params):
    pl = build_preferred_list("ITM-1016", AS_OF, master_data(), params)
    for r in pl:
        assert r.reference["source"] in ("po", "contract")
        assert r.reference_price is not None


def test_suggestions_top_up_from_category(params):
    ids, topped = suggestions("ITM-1034", date(2026, 11, 4), master_data(), params, 5)
    assert ids == ["S020", "S017", "S019", "S018"]        # only 4 eligible Electrical suppliers exist
    ids, topped = suggestions("ITM-1006", date(2026, 11, 2), master_data(), params, 3)
    assert ids == ["S003", "S002", "S005"] and topped == ids
