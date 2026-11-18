"""Row checks: each bad row is NOT_PROCESSED with a reason; the rest of the batch continues."""
from datetime import date

import pytest

from engine import PolicyNotFound, load_policy, run_batch
from tests.helpers import as_raw, by_key, line, load_doc, master_data


def test_sample_rejections(baseline):
    r = by_key(baseline)
    assert r["PR-26-00172/1"].route == "NOT_PROCESSED"
    assert r["PR-26-00172/1"].reason == "Quantity must be greater than zero"
    assert r["PR-26-00173/1"].route == "NOT_PROCESSED"
    assert r["PR-26-00173/1"].reason == "Unknown plant PUN2; policy covers PUN1 and CHK1"
    assert r["PR-26-00173/1"].policy_version == "5.0"
    assert r["PR-26-00173/1"].group_id == "" and r["PR-26-00173/1"].decision == ""


GOOD = dict(pr_no="PR-T-1", created_at="2026-11-02 10:00", plant="PUN1", item_code="ITM-1044", quantity=10,
            uom="NOS", need_by="2026-11-20")


def one(**over):
    args = dict(GOOD)
    args.update(over)
    return line(args.pop("pr_no"), args.pop("created_at"), args.pop("plant"), args.pop("item_code"),
                args.pop("quantity"), args.pop("uom"), args.pop("need_by"), **args)


CASES = [
    (dict(pr_no=""), "Missing PR number"),
    (dict(pr_line="x"), "PR line must be a positive whole number"),
    (dict(pr_line=0), "PR line must be a positive whole number"),
    (dict(created_at="02/11/2026"), "Unparseable created_at '02/11/2026'"),
    (dict(need_by="soon"), "Unparseable need_by_date 'soon'"),
    (dict(need_by="2026-11-01"), "Need-by date is before creation date"),
    (dict(plant="PUN2"), "Unknown plant PUN2; policy covers PUN1 and CHK1"),
    (dict(quantity="-5"), "Quantity must be greater than zero"),
    (dict(quantity="ten"), "Quantity 'ten' is not a number"),
    (dict(urgency="Critical"), "Unknown urgency 'Critical'"),
    (dict(estimated_unit_price="abc"), "estimated_unit_price is not a valid amount"),
    (dict(item_code="ITM-9999"), "Unknown item code 'ITM-9999'"),
    (dict(item_code="", description=""), "No item code or description"),
    (dict(uom="KG"), "UoM KG differs from item master UoM NOS"),
    (dict(created_at="2026-01-02 10:00", need_by="2026-01-20"), "No policy version effective on 2026-01-02"),
]


@pytest.mark.parametrize("over,reason", CASES, ids=[c[1] for c in CASES])
def test_row_checks(over, reason):
    res = run_batch(as_raw([one(**over), one(pr_no="PR-T-OK")]), master_data(), [load_policy(load_doc())])
    bad, ok = res.rows
    assert (bad.route, bad.reason) == ("NOT_PROCESSED", reason)
    assert ok.route != "NOT_PROCESSED"


def test_duplicate_line():
    res = run_batch(as_raw([one(), one()]), master_data(), [load_policy(load_doc())])
    assert res.rows[0].route != "NOT_PROCESSED"
    assert res.rows[1].reason == "Duplicate of PR line already in this batch"


def test_urgency_canonicalised():
    res = run_batch(as_raw([one(urgency="emergency"), one(pr_no="PR-T-2", urgency="")]), master_data(),
                    [load_policy(load_doc())])
    facts = {r.pr_no: res.decisions[r.group_id].trace["facts"] for r in res.rows}
    assert facts["PR-T-1"]["is_emergency"] is True


def test_pin_and_unknown_pin():
    policy = load_policy(load_doc())
    res = run_batch(as_raw([one(created_at="2026-01-02 10:00", need_by="2026-01-20")]), master_data(), [policy],
                    pin="5.0")
    assert res.rows[0].route != "NOT_PROCESSED" and res.rows[0].policy_version == "5.0"
    with pytest.raises(PolicyNotFound):
        run_batch(as_raw([one()]), master_data(), [policy], pin="9.9")


def test_version_selected_per_line_by_date():
    v5 = load_doc()
    v6 = load_doc()
    v6["version"], v6["effective_from"] = "6.0", "2026-11-10"
    v6["parameters"]["spot_max_value"] = 300000
    res = run_batch(as_raw([one(), one(pr_no="PR-T-2", created_at="2026-11-12 10:00", need_by="2026-11-30")]),
                    master_data(), [load_policy(v5), load_policy(v6)])
    assert [r.policy_version for r in res.rows] == ["5.0", "6.0"]
    assert res.rows[0].group_id != res.rows[1].group_id       # never mix versions in one requirement
    res = run_batch(as_raw([one()]), master_data(), [load_policy(v5), load_policy(v6)],
                    as_of=date(2026, 11, 15))
    assert res.rows[0].policy_version == "6.0"
