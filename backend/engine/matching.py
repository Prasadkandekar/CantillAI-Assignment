"""Item matcher: a valid code wins; otherwise normalise the description and fuzzy-match it.

All thresholds, abbreviations and note phrases live in data/matching_dictionary.json.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz

from .models import MatchResult

DICTIONARY_PATH = Path(__file__).parent / "data" / "matching_dictionary.json"


@lru_cache(maxsize=None)
def load_dictionary(path: str | None = None) -> dict:
    return json.loads(Path(path or DICTIONARY_PATH).read_text(encoding="utf-8"))


_HYPHEN = re.compile(r"(?<=[a-z0-9])-(?=[a-z0-9])")
_PUNCT = re.compile(r"[(),]")
_DIGIT = re.compile(r"\d")


def normalise_text(text: str, dictionary: dict) -> tuple[list[str], tuple[str, ...]]:
    """Return normalised tokens and the note flags found in the text."""
    t = (text or "").lower().replace('"', " inch ")
    flags = []
    for phrase, flag in dictionary.get("note_phrases", {}).items():
        pattern = re.escape(phrase.lower())
        if phrase[:1].isalnum():
            pattern = r"\b" + pattern
        if phrase[-1:].isalnum():
            pattern = pattern + r"\b"
        if re.search(pattern, t):
            if flag and flag not in flags:
                flags.append(flag)
            t = re.sub(pattern, " ", t)
    t = _HYPHEN.sub(" ", t)
    t = _PUNCT.sub(" ", t)
    t = " " + " ".join(t.split()) + " "
    for phrase, repl in dictionary.get("phrase_synonyms", {}).items():
        t = t.replace(" " + phrase.lower() + " ", " " + repl.lower() + " ")
    abbr = dictionary.get("abbreviations", {})
    tokens = [abbr.get(tok, tok) for tok in t.split()]
    return tokens, tuple(flags)


def size_tokens(tokens) -> set[str]:
    return {t for t in tokens if _DIGIT.search(t)}


class Matcher:
    def __init__(self, items: dict, dictionary: dict | None = None):
        self.dictionary = dictionary or load_dictionary()
        th = self.dictionary["thresholds"]
        self.auto_min = th["auto_match_min"]
        self.margin = th["margin"]
        self.candidate_min = th["candidate_min"]
        self.max_candidates = th["max_candidates"]
        self.items = items
        self._norm = {}
        for code, item in items.items():
            toks, _ = normalise_text(item.description, self.dictionary)
            self._norm[code] = (" ".join(toks), size_tokens(toks))

    def note_flags(self, text: str) -> tuple[str, ...]:
        return normalise_text(text, self.dictionary)[1]

    def match(self, item_code: str | None, description: str) -> MatchResult:
        code = (item_code or "").strip()
        flags = self.note_flags(description)
        if code and code in self.items:
            return MatchResult(code=code, score=None, candidates=(), method="code", flags=flags)
        tokens, flags = normalise_text(description, self.dictionary)
        if not tokens:
            return MatchResult(code=None, method="none", flags=flags)
        query = " ".join(tokens)
        qsizes = size_tokens(tokens)
        scored = []
        for c, (text, csizes) in self._norm.items():
            if not qsizes <= csizes:
                continue
            scored.append((fuzz.token_set_ratio(query, text), c, csizes))
        scored.sort(key=lambda x: (-x[0], x[1]))
        candidates = tuple((c, Decimal(str(round(s, 2)))) for s, c, _ in scored
                           if s >= self.candidate_min)[: self.max_candidates]
        if scored:
            top, code, csizes = scored[0]
            second = scored[1][0] if len(scored) > 1 else 0
            if top >= self.auto_min and top - second >= self.margin and csizes <= qsizes:
                return MatchResult(code=code, score=Decimal(str(round(top, 2))), candidates=candidates,
                                   method="auto", flags=flags)
        return MatchResult(code=None, score=None, candidates=candidates, method="none", flags=flags)
