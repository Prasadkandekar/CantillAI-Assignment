"""Rule-based amendment reader: sample texts -> expected JSON edits, validated, never guessing."""
from engine import validate
from services.policy_reader import next_label, read, sentences
from tests.helpers import changed, load_doc, run

PLANTS = {"PUN1": "Pune - Bhosari plant", "CHK1": "Chakan plant"}
CATEGORIES = ["Safety & PPE", "Lubricants", "Fasteners", "Office & IT"]


def _read(text):
    return read(text, load_doc(), label="5.1", plants=PLANTS, categories=CATEGORIES, mode="fallback")


def test_spot_limit_lakh():
    res = _read("Amendment 1. The spot PO limit is raised from ₹2 lakh to ₹3 lakh. Effective from 1 December 2026.")
    assert res.mode == "fallback"
    assert res.document["parameters"]["spot_max_value"] == 300000
    assert res.effective_from == "2026-12-01" and res.document["effective_from"] == "2026-12-01"
    assert res.document["version"] == "5.1"
    assert validate(res.document).errors == []


def test_emergency_and_windows_and_counts():
    res = _read("Emergency purchases up to Rs. 7,50,000 are allowed. The clubbing window becomes 7 days. "
                "Consolidation window: 48 hours. Suggest 4 suppliers for RFQ.")
    p = res.document["parameters"]
    assert (p["emergency_max_value"], p["club_created_days"], p["consolidation_hours"], p["rfq_suggestion_count"]) \
        == (750000, 7, 48, 4)
    assert res.unrecognised == []


def test_plant_only_limit_matches_proof_d():
    res = _read("For plant CHK1, the emergency limit is ₹2,50,000.")
    doc = res.document
    assert doc["parameters"]["chk1_emergency_max_value"] == 250000
    ids = [r["id"] for r in doc["rules"]]
    assert ids.index("5.3-CHK1") == ids.index("5.3") - 1
    assert validate(doc).errors == []
    doc["effective_from"] = load_doc()["effective_from"]
    assert changed(run(load_doc()), run(doc)) == {"PR-26-00058/1"}


def test_category_rule_matches_proof_b():
    res = _read("At plant CHK1, Safety & PPE items of ₹1,00,000 or more go to RFQ.")
    doc = res.document
    new_rule = next(r for r in doc["rules"] if r["id"] not in {x["id"] for x in load_doc()["rules"]})
    ids = [r["id"] for r in doc["rules"]]
    assert ids.index(new_rule["id"]) == ids.index("5.4") - 1
    assert new_rule["outcome"]["route"] == "RFQ"
    assert validate(doc).errors == []
    doc["effective_from"] = load_doc()["effective_from"]
    assert changed(run(load_doc()), run(doc)) == {"PR-26-00136/1", "PR-26-00137/1", "PR-26-00138/1", "PR-26-00139/1"}


def test_ranking_weights():
    res = _read("Ranking weights: frequency 0.40, recency 0.15, contract 0.15, on-time 0.15, quality 0.15.")
    w = res.document["parameters"]["ranking_weights"]
    assert (w["frequency"], w["recency"]) == (0.4, 0.15)
    assert validate(res.document).errors == []


def test_unrecognised_sentences_are_listed_not_guessed():
    res = _read("Buyers must wear blue hats on Mondays. The spot limit is ₹2.5 lakh.")
    assert res.document["parameters"]["spot_max_value"] == 250000
    assert res.unrecognised == ["Buyers must wear blue hats on Mondays."]
    assert res.effective_from is None


def test_helpers():
    assert next_label("5.0", ["5.0", "5.1"]) == "5.2"
    assert sentences("Rs. 3 lakh limit. Next one;\nthird") == ["Rs 3 lakh limit.", "Next one;", "third"]
