"""Preferred supplier list, explainable ranking, reference price and suggestions with top-up."""
from __future__ import annotations

import math
from datetime import timedelta
from decimal import Decimal

from .eligibility import is_eligible
from .models import FactorContribution, RankedSupplier

RANKING_FACTORS = ("frequency", "recency", "contract", "on_time", "quality")
TOPUP_FACTORS = ("on_time", "quality")
TIE_BREAK_KEYS = RANKING_FACTORS + ("score", "supplier_id")
SCORE_PLACES = Decimal("0.000001")
SCORE_DIGITS = -SCORE_PLACES.as_tuple().exponent


def _dec(x: float) -> Decimal:
    return Decimal(repr(float(x))).quantize(SCORE_PLACES)


def _scaled_ratings(supplier, params: dict) -> tuple[float, float]:
    on_time = float(supplier.on_time_pct) / float(params["on_time_pct_scale"])
    quality = float(supplier.quality_rating) / float(params["quality_rating_scale"])
    return on_time, quality


def build_preferred_list(item_code: str, as_of, master, params: dict) -> list[RankedSupplier]:
    """Eligible suppliers with a PO for the item inside the preferred-history window, or a contract
    for the item that started on or before as_of (expiry ignored), ranked by weighted score."""
    lo = as_of - timedelta(days=params["preferred_history_days"])
    members: dict[str, dict] = {}

    def member(sid):
        return members.setdefault(sid, {"pos": [], "contracts": []})

    for po in master.po_by_item.get(item_code, ()):
        if lo <= po.po_date <= as_of and is_eligible(master.suppliers.get(po.supplier_id), params):
            member(po.supplier_id)["pos"].append(po)
    for c in master.contracts_by_item.get(item_code, ()):
        if c.start_date <= as_of and is_eligible(master.suppliers.get(c.supplier_id), params):
            member(c.supplier_id)["contracts"].append(c)
    if not members:
        return []

    weights = {k: float(v) for k, v in params["ranking_weights"].items()}
    decay = float(params["ranking_recency_decay_days"])
    max_count = max(len(m["pos"]) for m in members.values())
    rows = []
    for sid, m in members.items():
        sup = master.suppliers[sid]
        pos = m["pos"]
        last = max(pos, key=lambda p: (p.po_date, p.po_number)) if pos else None
        days = (as_of - last.po_date).days if last else None
        on_time, quality = _scaled_ratings(sup, params)
        scaled = {
            "frequency": (len(pos) / max_count) if max_count else 0.0,
            "recency": math.exp(-days / decay) if last else 0.0,
            "contract": 1.0 if m["contracts"] else 0.0,
            "on_time": on_time,
            "quality": quality,
        }
        raw = {
            "frequency": len(pos),
            "recency": None if days is None else days,
            "contract": bool(m["contracts"]),
            "on_time": str(sup.on_time_pct),
            "quality": str(sup.quality_rating),
        }
        score = sum(weights[f] * scaled[f] for f in RANKING_FACTORS)
        factors = {
            f: FactorContribution(raw[f], _dec(scaled[f]), Decimal(str(params["ranking_weights"][f])),
                                  _dec(weights[f] * scaled[f]))
            for f in RANKING_FACTORS
        }
        if last is not None:
            ref_price = last.unit_price
            reference = {"source": "po", "po_number": last.po_number, "po_date": last.po_date.isoformat()}
        else:
            c = max(m["contracts"], key=lambda k: (k.start_date, k.contract_id))
            ref_price = c.lines[item_code].rate
            reference = {"source": "contract", "contract_id": c.contract_id, "start_date": c.start_date.isoformat()}
        rows.append({"sid": sid, "score": round(score, SCORE_DIGITS), "scaled": scaled,
                     "factors": factors, "ref_price": ref_price, "reference": reference,
                     "count": len(pos), "last": last.po_date if last else None, "contract": bool(m["contracts"])})

    tie_break = [k for k in params.get("ranking_tie_break", []) if k != "supplier_id"]

    def sort_key(r):
        key = [-r["score"]]
        for k in tie_break:
            key.append(-r["score"] if k == "score" else -r["scaled"][k])
        key.append(r["sid"])
        return tuple(key)

    rows.sort(key=sort_key)
    return [
        RankedSupplier(r["sid"], i, _dec(r["score"]), r["factors"], r["ref_price"], r["reference"],
                       r["count"], r["last"], r["contract"])
        for i, r in enumerate(rows, start=1)
    ]


def topup_candidates(item_code: str, master, params: dict, exclude) -> list[str]:
    item = master.items.get(item_code)
    category = item.category if item else None
    if not category:
        return []
    tw = {k: float(v) for k, v in params["topup_weights"].items()}
    cands = []
    for sid, sup in master.suppliers.items():
        if sid in exclude or not is_eligible(sup, params) or category not in sup.categories:
            continue
        on_time, quality = _scaled_ratings(sup, params)
        cands.append((-(tw["on_time"] * on_time + tw["quality"] * quality), sid))
    cands.sort()
    return [sid for _, sid in cands]


def suggestions(item_code: str, as_of, master, params: dict, count: int, preferred=None) -> tuple[list[str], list[str]]:
    """Preferred list in rank order, then category top-up. Returns (ids, ids that came from top-up)."""
    if preferred is None:
        preferred = build_preferred_list(item_code, as_of, master, params)
    chosen = [r.supplier_id for r in preferred][:count]
    topped = []
    if len(chosen) < count:
        topped = topup_candidates(item_code, master, params, set(chosen))[: count - len(chosen)]
    return chosen + topped, topped
