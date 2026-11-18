"""A full replacement policy (Corvo v6.0 text) must yield a valid, activatable draft, whatever the LLM returns."""
import copy
from pathlib import Path

import pytest

from engine import validate
from services import llm, policy_reader
from services.policy_reader import _Full, is_full_policy, read
from engine import load_policy, run_batch
from tests.helpers import as_raw, changed, line, load_doc, master_data, run

FIXTURE = Path(__file__).parent / "fixtures" / "policy_v6_0.txt"
V6 = FIXTURE.read_text(encoding="utf-8")
PLANTS = {"PUN1": "Pune - Bhosari plant", "CHK1": "Chakan plant"}
# A row the deterministic reader cannot express, so the LLM path is exercised.
EXTRA_ROW = "\n5.9 Value above \u20b950,00,000 needs board sign-off: Sourcing request, route BOARD_REVIEW.\n"
V6_UNKNOWN_ROW = V6.replace("5.8 Blocked", EXTRA_ROW.strip() + "\n5.8 Blocked")
EXPECTED_PARAMS = {"spot_max_value": 300000, "rfp_min_value": 1500000, "service_rfq_min_value": 100000,
                   "pun1_emergency_max_value": 750000, "chk1_emergency_max_value": 300000,
                   "rfq_suggestion_count": 4, "rfp_suggestion_count": 5, "capex_suggestion_count": 5,
                   "club_created_days": 10, "club_needby_days": 5, "consolidation_hours": 48}
REFERENCED = ("spot_max_value", "rfp_min_value", "emergency_max_value", "rfp_suggestion_count", "rfq_suggestion_count")


def _read(text, mode="auto"):
    return read(text, load_doc(), label="5.1", plants=PLANTS, categories=[], mode=mode)


def _assert_clean(doc):
    result = validate(doc)
    assert result.errors == []
    orphans = [w.path for w in result.warnings if "never referenced" in w.message]
    assert orphans == []
    assert doc["schema_version"] == 1 and doc["version"] == "5.1"


def _mock(monkeypatch, reply):
    calls = []

    def fake(system, user, schema_hint="", **kw):
        calls.append(kw)
        return copy.deepcopy(reply)

    monkeypatch.setattr(llm, "complete_json", fake)
    return calls


def test_is_full_policy():
    assert is_full_policy(V6)
    assert not is_full_policy("The spot PO limit is raised from \u20b92 lakh to \u20b93 lakh. Effective from 1 December 2026.")


def test_deterministic_reader_alone_gives_valid_v6_draft():
    res = _read(V6, mode="fallback")
    doc = res.document
    assert res.kind == "full" and res.mode == "deterministic" and res.effective_from == "2026-11-01"
    _assert_clean(doc)
    for name, value in EXPECTED_PARAMS.items():
        assert doc["parameters"][name] == value, name
    assert "emergency_max_value" not in doc["parameters"]      # both plants have their own limit
    assert [r["id"] for r in doc["rules"]] == ["1.2", "5.1", "5.2", "5.3", "5.4-PUN1", "5.4-CHK1", "5.5", "5.6", "5.7"]
    assert res.unrecognised == []                               # prose clauses are informational, not errors
    assert any(p.startswith("5.8 ") for p in res.informational)
    assert any(p.startswith("9.1 ") for p in res.informational)


def test_llm_not_called_when_deterministic_reading_is_complete(monkeypatch):
    calls = _mock(monkeypatch, {"rules": []})
    res = _read(V6)
    assert calls == [] and res.mode == "deterministic"
    _assert_clean(res.document)


def _good_rules():
    return copy.deepcopy(_Full(load_doc(), PLANTS).run(V6_UNKNOWN_ROW).doc["rules"])


def test_flawed_llm_reply_without_schema_and_orphaned_parameters(monkeypatch):
    # The old policy-shaped reply: no schema_version, v5.0 rules that no longer reference the new parameters.
    bad = load_doc()
    del bad["schema_version"]
    _mock(monkeypatch, {"policy": bad, "unsupported": ["1.1 Every PR line must be matched to an item"]})
    res = _read(V6_UNKNOWN_ROW)
    _assert_clean(res.document)
    assert res.unrecognised and all("5.9" in u for u in res.unrecognised)
    assert res.document["parameters"]["spot_max_value"] == 300000


def test_flawed_llm_reply_with_literal_values_orphans_parameters(monkeypatch):
    rules = _good_rules()
    for r in rules:
        for leaf in policy_reader._leaves(r["when"]):
            if isinstance(leaf["value"], str) and leaf["value"].startswith("$"):
                leaf["value"] = 1
    _mock(monkeypatch, {"parameters": {"spot_max_value": 1}, "rules": rules})
    res = _read(V6_UNKNOWN_ROW)
    _assert_clean(res.document)
    assert res.document["parameters"]["spot_max_value"] == 300000
    for name in ("spot_max_value", "rfp_min_value", "rfq_suggestion_count", "rfp_suggestion_count"):
        assert name in policy_reader._referenced_params(res.document)


def test_invalid_outcome_and_invented_fact_rules_are_dropped(monkeypatch):
    rules = _good_rules()
    rules.append({"id": "9.9", "clause": "9.9", "text": "No PO ever", "when": {"all": [
        {"fact": "supplier_status", "op": "eq", "value": "Blocked"}]}, "outcome": {"decision": "NO_PO"}})
    rules.append({"id": "9.8", "clause": "9.8", "text": "Bad outcome", "when": {"all": [
        {"fact": "is_new_item", "op": "eq", "value": True}]}, "outcome": {"decision": "NO_PO"}})
    params = dict(EXPECTED_PARAMS)
    _mock(monkeypatch, {"parameters": params, "rules": rules, "unsupported": []})
    res = _read(V6_UNKNOWN_ROW)
    _assert_clean(res.document)
    assert res.mode == "llm"
    assert "9.9" not in [r["id"] for r in res.document["rules"]]
    assert any("No PO ever" in u for u in res.unrecognised)


def test_llm_unavailable_still_gives_valid_draft(monkeypatch):
    def boom(*a, **k):
        raise llm.LLMUnavailable("timeout")

    monkeypatch.setattr(llm, "complete_json", boom)
    res = _read(V6_UNKNOWN_ROW)
    _assert_clean(res.document)
    assert res.llm_error == "timeout" and any("5.9" in u for u in res.unrecognised)


def test_amendment_llm_reply_without_schema_version_is_stamped(monkeypatch):
    doc = load_doc()
    del doc["schema_version"]
    doc["parameters"]["spot_max_value"] = 300000
    _mock(monkeypatch, {"policy": doc, "effective_from": None, "unsupported": []})
    res = _read("The spot PO limit is raised to \u20b93 lakh.")
    assert res.kind == "amendment" and res.mode == "llm"
    assert validate(res.document).errors == [] and res.document["schema_version"] == 1


def test_v6_engine_behaviour():
    doc = _read(V6, mode="fallback").document
    doc["effective_from"] = load_doc()["effective_from"]
    extra = [line("PR-V6-S1", "2026-12-01 10:00", "PUN1", "ITM-1062", 1, "MON", "2026-12-20"),
             line("PR-V6-S2", "2026-12-01 10:00", "PUN1", "ITM-1063", 1, "QTR", "2026-12-20")]
    rows = {f"{r.pr_no}/{r.pr_line}": r for r in run(doc, extra).rows}
    service = rows["PR-V6-S1/1"]
    assert (service.route, service.decision) == ("RFQ", "SOURCING_REQUEST")
    assert len(service.suggested_supplier_ids.split(";")) == 4
    assert rows["PR-V6-S2/1"].route != "RFQ" or rows["PR-V6-S2/1"].group_value_inr < 100000


def test_v5_results_unchanged_for_requirements_before_effective_date():
    base = load_doc()
    v6 = _read(V6, mode="fallback").document      # effective 2026-11-01
    early = as_raw([line("PR-OCT-1", "2026-10-05 10:00", "PUN1", "ITM-1062", 1, "MON", "2026-10-20"),
                    line("PR-OCT-2", "2026-10-06 10:00", "CHK1", "ITM-1026", 6000, "NOS", "2026-10-20", "Emergency"),
                    line("PR-OCT-3", "2026-10-07 10:00", "PUN1", "ITM-1063", 1, "QTR", "2026-10-20")])
    with_v6 = run_batch(early, master_data(), [load_policy(copy.deepcopy(base)), load_policy(v6)])
    only_v5 = run_batch(early, master_data(), [load_policy(copy.deepcopy(base))])
    assert changed(only_v5, with_v6) == set()
    assert {r.policy_version for r in with_v6.rows} == {"5.0"}