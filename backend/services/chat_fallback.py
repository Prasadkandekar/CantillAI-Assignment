"""Rule-based slot extraction for chat intake (used when the LLM is unavailable). No network."""
from __future__ import annotations

import re

from . import dates

UOM_WORDS = {
    "PAIR": ("pair", "pairs", "pr"), "NOS": ("nos", "no", "pcs", "pc", "piece", "pieces", "number", "numbers", "units",
                                              "unit"),
    "KG": ("kg", "kgs", "kilo", "kilos", "kilogram", "kilograms"), "LTR": ("l", "ltr", "ltrs", "litre", "litres", "liter",
                                                                          "liters"),
    "MTR": ("m", "mtr", "mtrs", "metre", "metres", "meter", "meters"), "BKT": ("bkt", "bkts", "bucket", "buckets"),
    "SET": ("set", "sets"), "ROL": ("rol", "roll", "rolls"), "REAM": ("ream", "reams"),
    "CYL": ("cylinders",), "BRL": ("brl", "barrel", "barrels"), "JOB": ("job", "jobs"),
    "MON": ("mon", "month", "months"), "QTR": ("qtr", "quarter", "quarters"),
}
_UOM_LOOKUP = {w: code for code, words in UOM_WORDS.items() for w in words}
_UOM_RX = "|".join(sorted((re.escape(w) for w in _UOM_LOOKUP), key=len, reverse=True))
_QTY_UOM = re.compile(r"\b(\d+(?:\.\d+)?)\s*(" + _UOM_RX + r")\b", re.I)
_LEADING_QTY = re.compile(r"^\s*(?:hi[,!]?\s+)?(?:i|we)?\s*(?:need|want|require|order|get|buy|please order|"
                          r"please get|raise a pr for|pr for)?\s*(\d+(?:\.\d+)?)\s+(?!mm\b|inch|in\b|ton|v\b|w\b|"
                          r"kw\b|hp\b|x\b)([a-z])", re.I)
_QTY_WORD = re.compile(r"\b(?:qty|quantity)\s*(?:of|:|=|is)?\s*(\d+(?:\.\d+)?)", re.I)
_ONLY_NUMBER = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*$")
_CODE = re.compile(r"\b([A-Z]{3}-\d{4})\b")
_ESTIMATE = re.compile(r"(?:₹|\brs\.?|\binr)\s*(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s*(?:rupees|each|per unit|/unit|"
                       r"a piece|per piece)", re.I)
_UNKNOWN = re.compile(r"\b(don'?t know|do not know|not sure|no idea|unknown|dunno)\b", re.I)
_URGENT = re.compile(r"\b(urgent|urgently|asap|immediately|rush)\b", re.I)
_NOT_EMERGENCY = re.compile(r"\b(not (?:an? )?emergency|no emergency|normal|routine|not urgent)\b", re.I)
_EMERGENCY = re.compile(r"\bemergency\b", re.I)
_YES = re.compile(r"^\s*(yes|y|yeah|yep|yup|sure|correct|confirm|confirmed|ok|okay|go ahead|place it)\b[\s.!]*$", re.I)
_NO = re.compile(r"^\s*(no|n|nope|nah)\b[\s.!]*$", re.I)
_CANCEL = re.compile(r"\b(cancel|start over|reset|forget it)\b", re.I)
_NONE_CHOICE = re.compile(r"\b(none|neither|new item|something else|not listed)\b", re.I)
_CHOICE = re.compile(r"^\s*(?:option|number|no\.?|#)?\s*(\d)\s*[.)]?\s*$", re.I)
_FILLER = {"i", "we", "need", "needs", "want", "require", "required", "please", "pls", "order", "get", "buy", "for",
           "at", "the", "plant", "by", "deliver", "delivered", "delivery", "some", "a", "an", "of", "to", "in", "on",
           "and", "it", "is", "this", "that", "be", "should", "hi", "hello", "raise", "pr", "before", "next", "week",
           "within", "days", "day", "qty", "quantity", "us", "me", "can", "you", "my", "our", "send", "dept",
           "department", "from", "with", "asap", "urgent", "urgently", "emergency", "normal", "yes", "no", "it's",
           "its", "also", "just", "kindly", "procure", "purchase", "supply", "coming"}
_DATE_PATTERNS = (dates._ISO, dates._DMY, dates._D_MON, dates._MON_D, dates._IN_N, dates._NEXT_WD,
                  re.compile(r"\b(day after tomorrow|tomorrow|today)\b", re.I),
                  re.compile(r"\b(?:by|this|on|before|coming)?\s*" + dates._WEEKDAY + r"\b", re.I))


def uom_code(word: str | None) -> str | None:
    if not word:
        return None
    w = word.strip().lower().rstrip(".")
    return _UOM_LOOKUP.get(w) or (word.strip().upper() if word.strip().upper() in UOM_WORDS else None)


def plant_from_text(text: str, plants: dict) -> str | None:
    low = (text or "").lower()
    for code in plants:
        if re.search(r"\b" + re.escape(code.lower()) + r"\b", low):
            return code
    for code, name in plants.items():
        for word in re.findall(r"[a-z]+", name.lower()):
            if word in ("plant", "the") or len(word) < 4:
                continue
            if re.search(r"\b" + re.escape(word) + r"\b", low):
                return code
    return None


def _plant_words(plants: dict) -> set[str]:
    words = {c.lower() for c in plants}
    for name in plants.values():
        words |= {w for w in re.findall(r"[a-z]+", name.lower()) if len(w) >= 4}
    return words


def extract(message: str, plants: dict, pending: str | None = None) -> dict:
    text = message or ""
    out = {"item_text": None, "item_code_typed": None, "quantity": None, "uom": None, "plant_text": None,
           "need_by_text": None, "urgency": None, "urgent_word": False, "estimated_unit_price": None,
           "estimate_unknown": False, "intent": "provide", "selection": None}
    if _CANCEL.search(text):
        out["intent"] = "cancel"
        return out
    if _YES.match(text):
        if pending == "urgency":
            out["urgency"] = "Emergency"
        else:
            out["intent"] = "confirm"
        return out
    if _NO.match(text):
        if pending == "urgency":
            out["urgency"] = "Normal"
        return out
    if mt := _CHOICE.match(text):
        if pending == "selection":
            out["selection"] = mt.group(1)
            return out
    if pending == "selection" and _NONE_CHOICE.search(text):
        out["selection"] = "none"
        return out
    if mt := _CODE.search(text):
        out["item_code_typed"] = mt.group(1)
        if pending == "selection":
            out["selection"] = mt.group(1)
    work = text
    if pending == "estimate" or pending is None:
        if _UNKNOWN.search(text):
            out["estimate_unknown"] = True
        elif mt := _ESTIMATE.search(work):
            out["estimated_unit_price"] = (mt.group(1) or mt.group(2)).replace(",", "")
            work = work[:mt.start()] + " " + work[mt.end():]
        elif pending == "estimate" and (mt := _ONLY_NUMBER.match(text)):
            out["estimated_unit_price"] = mt.group(1)
            work = ""
    if mt := _QTY_UOM.search(work):
        out["quantity"], out["uom"] = mt.group(1), uom_code(mt.group(2))
        work = work[:mt.start()] + " " + work[mt.end():]
    elif mt := _QTY_WORD.search(work):
        out["quantity"] = mt.group(1)
        work = work[:mt.start()] + " " + work[mt.end():]
    elif mt := _LEADING_QTY.search(work):
        out["quantity"] = mt.group(1)
        work = work[:mt.start(1)] + " " + work[mt.end(1):]
    elif pending == "quantity" and (mt := _ONLY_NUMBER.match(work)):
        out["quantity"] = mt.group(1)
        work = ""
    if out["uom"] is None and uom_code(text.strip()):
        out["uom"] = uom_code(text.strip())
        work = ""
    plant = plant_from_text(work, plants)
    if plant:
        out["plant_text"] = plant
    for rx in _DATE_PATTERNS:
        if mt := rx.search(work):
            out["need_by_text"] = mt.group(0)
            break
    if _NOT_EMERGENCY.search(text):
        out["urgency"] = "Normal"
    elif _EMERGENCY.search(text):
        out["urgency"] = "Emergency"
    elif _URGENT.search(text):
        out["urgent_word"] = True
    for rx in _DATE_PATTERNS:
        work = rx.sub(" ", work)
    if out["item_code_typed"]:
        work = work.replace(out["item_code_typed"], " ")
    words = [w for w in re.findall(r"[A-Za-z0-9\"/.\-]+", work)]
    plant_words = _plant_words(plants)
    kept = [w for w in words if w.lower().strip(".") not in _FILLER and w.lower() not in plant_words]
    item_text = " ".join(kept).strip(" .-")
    if re.search(r"[A-Za-z]{3}", item_text) and pending not in ("urgency", "estimate"):
        out["item_text"] = item_text
    return out
