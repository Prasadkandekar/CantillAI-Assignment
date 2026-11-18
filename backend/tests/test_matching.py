"""The 39 sample lines without an item code."""
import pytest

from engine.matching import Matcher
from tests.helpers import master_data, sample_lines

EXPECTED = {
    "PR-26-00002": "ITM-1024", "PR-26-00004": "ITM-1022", "PR-26-00008": "ITM-1016", "PR-26-00018": "ITM-1013",
    "PR-26-00020": "ITM-1015", "PR-26-00023": "ITM-1048", "PR-26-00030": "ITM-1023", "PR-26-00036": "ITM-1039",
    "PR-26-00039": "ITM-1057", "PR-26-00042": "ITM-1036", "PR-26-00047": "ITM-1071", "PR-26-00052": "ITM-1025",
    "PR-26-00058": "ITM-1020", "PR-26-00060": "ITM-1050", "PR-26-00063": "ITM-1043", "PR-26-00066": "ITM-1008",
    "PR-26-00075": "ITM-1030", "PR-26-00083": "ITM-1050", "PR-26-00088": "ITM-1035", "PR-26-00089": "ITM-1066",
    "PR-26-00097": "ITM-1066", "PR-26-00098": "ITM-1008", "PR-26-00103": "ITM-1044", "PR-26-00109": "ITM-1044",
    "PR-26-00114": "ITM-1034", "PR-26-00117": "ITM-1030", "PR-26-00119": "ITM-1028", "PR-26-00124": "ITM-1004",
    "PR-26-00139": "ITM-1051", "PR-26-00141": "ITM-1040", "PR-26-00142": "ITM-1040", "PR-26-00150": "ITM-1058",
    "PR-26-00161": "ITM-1010", "PR-26-00163": "ITM-1013", "PR-26-00165": "ITM-1055", "PR-26-00167": "ITM-1073",
    "PR-26-00169": "ITM-1063", "PR-26-00170": None, "PR-26-00171": None,
}


@pytest.fixture(scope="module")
def matcher():
    return Matcher(master_data().items)


def test_all_no_code_lines(matcher):
    no_code = [l.values for l in sample_lines() if not l.values["item_code"]]
    assert len(no_code) == 39
    got = {v["pr_no"]: matcher.match("", v["description"]).code for v in no_code}
    assert got == EXPECTED


def test_size_tokens_must_match_exactly(matcher):
    assert matcher.match("", "grinding wheel 14 inch").code is None     # only 4 inch exists
    assert matcher.match("", "Drinking water purifier 50 LPH").code is None


def test_ambiguous_text_offers_candidates(matcher):
    res = matcher.match("", "gloves")
    assert res.code is None
    assert {c for c, _ in res.candidates} >= {"ITM-1047", "ITM-1048"}


def test_code_wins(matcher):
    res = matcher.match("ITM-1001", "something else")
    assert (res.code, res.method) == ("ITM-1001", "code")


def test_note_flags(matcher):
    assert "as_per_sample" in matcher.match("", "FRL unit 1/2 inch as per sample").flags
    assert "urgent_in_text" in matcher.match("", "nitrile coated gloves - urgent").flags
