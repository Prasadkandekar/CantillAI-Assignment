"""Chat intake: a slot-filling state machine.

collecting -> awaiting_selection | awaiting_new_item_estimate -> awaiting_confirmation -> created

The LLM (or the rule-based fallback) only extracts what the user said. Item codes come from the
matcher or from the user's own choice; dates, plants and urgency are resolved in code.
"""
from __future__ import annotations

import copy
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select

from db import models as m
from engine import raw_line
from engine.matching import Matcher
from engine.models import NEW_ITEM

from . import audit, batch_service, chat_fallback, dates, llm
from .engine_adapter import master_from_db
from .errors import conflict, not_found, unprocessable

SLOT_ORDER = ("item", "quantity", "plant", "need_by", "urgency")
MAX_QUESTIONS = 2
URGENCY_QUESTION = "Is this an Emergency? (Emergency allows a PO without quotes)"
EMPTY_SLOTS = {"item_code": None, "item_text": None, "description": None, "is_new": False, "estimate": None,
               "estimate_answered": False, "quantity": None, "uom": None, "user_uom": None, "plant": None,
               "need_by": None, "urgency": None}
LLM_SCHEMA = ('{"item_text": str|null, "quantity": number|null, "uom": str|null, "plant_text": str|null, '
              '"need_by_text": str|null, "urgency": "Emergency"|"Normal"|null, "urgent_word": bool, '
              '"estimated_unit_price": number|null, "estimate_unknown": bool, '
              '"intent": "provide"|"select"|"confirm"|"edit"|"cancel", "selection": str|null}')


def new_state() -> dict:
    return {"stage": "collecting", "slots": dict(EMPTY_SLOTS), "candidates": [], "pending": None,
            "pr_no": None, "mode": None}


# --- extraction ---------------------------------------------------------------------

def _llm_extract(message: str, state: dict) -> dict:
    system = ("You extract purchase-request details from a chat message for an Indian engineering company. "
              "Copy the user's words; do not normalise dates or plants and never output item codes. "
              "urgency is 'Emergency' or 'Normal' only if the user says so explicitly; set urgent_word when they say "
              "urgent/asap. selection is the option number or code the user picked, or 'none'. "
              f"Conversation stage: {state['stage']}; pending question: {state.get('pending')}.")
    out = llm.complete_json(system, message, LLM_SCHEMA, max_tokens=400)
    clean = {"item_text": None, "item_code_typed": None, "quantity": None, "uom": None, "plant_text": None,
             "need_by_text": None, "urgency": None, "urgent_word": False, "estimated_unit_price": None,
             "estimate_unknown": False, "intent": "provide", "selection": None}
    for k in ("item_text", "plant_text", "need_by_text", "uom", "selection"):
        v = out.get(k)
        clean[k] = str(v).strip() if isinstance(v, (str, int)) and str(v).strip() else None
    for k in ("quantity", "estimated_unit_price"):
        v = out.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            clean[k] = str(v)
        elif isinstance(v, str) and re.fullmatch(r"\d+(?:\.\d+)?", v.strip()):
            clean[k] = v.strip()
    if out.get("urgency") in ("Emergency", "Normal"):
        clean["urgency"] = out["urgency"]
    clean["urgent_word"] = out.get("urgent_word") is True
    clean["estimate_unknown"] = out.get("estimate_unknown") is True
    if out.get("intent") in ("provide", "select", "confirm", "edit", "cancel"):
        clean["intent"] = out["intent"]
    if clean["uom"]:
        clean["uom"] = chat_fallback.uom_code(clean["uom"]) or clean["uom"].upper()
    # Item codes are only ever taken from the user's own words, never from the model.
    typed = re.search(r"\b([A-Z]{3}-\d{4})\b", message or "")
    clean["item_code_typed"] = typed.group(1) if typed else None
    if clean["item_text"] and re.search(r"\b[A-Z]{3}-\d{4}\b", clean["item_text"]) and not typed:
        clean["item_text"] = re.sub(r"\b[A-Z]{3}-\d{4}\b", " ", clean["item_text"]).strip() or None
    return clean


def extract(message: str, state: dict, plants: dict) -> tuple[dict, str]:
    try:
        return _llm_extract(message, state), "llm"
    except llm.LLMUnavailable:
        return chat_fallback.extract(message, plants, state.get("pending")), "fallback"


# --- helpers --------------------------------------------------------------------------

def _plants(session) -> dict:
    return {p.plant: p.name for p in session.scalars(select(m.Plant).order_by(m.Plant.plant))}


def _plant_question(plants: dict) -> str:
    return "Which plant is it for: " + " or ".join(f"{c} ({n})" for c, n in plants.items()) + "?"


def _dec(text) -> Decimal | None:
    if text in (None, ""):
        return None
    try:
        d = Decimal(str(text).replace(",", ""))
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _get_session(session, session_id: int | None, user: str) -> m.ChatSession:
    if session_id is None:
        row = m.ChatSession(user=user, state=new_state(), messages=[])
        session.add(row)
        session.flush()
        return row
    row = session.get(m.ChatSession, session_id)
    if row is None:
        raise not_found(f"Chat session {session_id} not found")
    return row


def _set_item(slots: dict, item) -> None:
    slots.update(item_code=item.item_code, description=item.description, is_new=False, estimate=None, uom=item.uom)


def _card(slots: dict) -> dict:
    need_by = date.fromisoformat(slots["need_by"]) if slots.get("need_by") else None
    return {"item_code": NEW_ITEM if slots["is_new"] else slots["item_code"],
            "description": slots["description"] or slots["item_text"], "quantity": slots["quantity"],
            "uom": slots["uom"], "plant": slots["plant"], "need_by": slots["need_by"],
            "need_by_display": dates.with_weekday(need_by), "urgency": slots["urgency"],
            "estimate": slots["estimate"] if slots["is_new"] else None}


def _missing(slots: dict) -> list[str]:
    out = []
    if not (slots["item_code"] or slots["is_new"]):
        out.append("item")
    if slots["is_new"] and not slots["uom"]:
        out.append("uom")
    if not slots["quantity"]:
        out.append("quantity")
    if not slots["plant"]:
        out.append("plant")
    if not slots["need_by"]:
        out.append("need_by")
    if not slots["urgency"]:
        out.append("urgency")
    return out


# --- the turn ---------------------------------------------------------------------------

def turn(session, *, user: str, role: str, department: str = "", session_id: int | None = None,
         message: str | None = None, action: str | None = None, choice: str | None = None,
         fields: dict | None = None, today=None) -> dict:
    chat = _get_session(session, session_id, user)
    state = copy.deepcopy(chat.state or new_state())
    if state["stage"] == "created":
        state = new_state()
    slots = state["slots"]
    plants = _plants(session)
    today = today or dates.today_ist()
    master = master_from_db(session)
    replies: list[str] = []
    message = (message or "").strip()

    if action == "select":
        ext = {"selection": choice, "intent": "select"}
        mode = "action"
    elif action == "edit":
        ext = {"intent": "edit"}
        mode = "action"
        f = fields or {}
        if f.get("quantity") not in (None, ""):
            ext["quantity"] = str(f["quantity"])
        if f.get("uom"):
            ext["uom"] = chat_fallback.uom_code(f["uom"]) or str(f["uom"]).upper()
        if f.get("plant"):
            ext["plant_text"] = str(f["plant"])
        if f.get("need_by"):
            ext["need_by_text"] = str(f["need_by"])
        if f.get("urgency"):
            ext["urgency"] = str(f["urgency"]).capitalize()
        if f.get("item_text"):
            ext["item_text"] = str(f["item_text"])
            slots.update(item_code=None, is_new=False, description=None, estimate=None, estimate_answered=False)
            state["stage"] = "collecting"
        if f.get("estimate") not in (None, ""):
            ext["estimated_unit_price"] = str(f["estimate"])
    else:
        if not message:
            raise unprocessable("message is required")
        ext, mode = extract(message, state, plants)
    state["mode"] = mode
    chat.messages = list(chat.messages or []) + ([{"role": "user", "text": message, "at": m.utcnow().isoformat() + "Z"}]
                                                 if message else [])

    if ext.get("intent") == "cancel":
        state = new_state()
        return _save(session, chat, state, "Cancelled. What do you need?", None)

    if ext.get("intent") == "confirm" and state["stage"] == "awaiting_confirmation":
        result = confirm(session, chat.id, user=user, role=role, department=department, _state=state)
        return {"session_id": chat.id, "reply": result["reply"], "state": result["state"], "card": None,
                "candidates": [], "result": result}

    # selection among candidates
    if state["stage"] == "awaiting_selection":
        sel = ext.get("selection") or ext.get("item_code_typed")
        codes = [c["item_code"] for c in state["candidates"]]
        if sel and sel.isdigit() and 1 <= int(sel) <= len(codes):
            sel = codes[int(sel) - 1]
        if sel in codes:
            _set_item(slots, master.items[sel])
            state["candidates"], state["stage"], state["pending"] = [], "collecting", None
            replies.append(f"OK, {sel} {master.items[sel].description} ({master.items[sel].uom}).")
        elif sel == "none":
            state["candidates"], state["stage"] = [], "awaiting_new_item_estimate"
            slots["is_new"] = True
        elif ext.get("item_text"):
            state["candidates"], state["stage"] = [], "collecting"
        elif sel:
            replies.append("Please pick one of the listed options (1-%d) or say 'none'." % len(codes))

    # new item estimate
    if state["stage"] == "awaiting_new_item_estimate":
        est = _dec(ext.get("estimated_unit_price"))
        if est is not None or ext.get("estimate_unknown"):
            slots.update(is_new=True, item_code=None, estimate=None if est is None else str(est), estimate_answered=True)
            slots["description"] = slots["item_text"]
            state["stage"], state["pending"] = "collecting", None
            replies.append("Noted as a new item" + (f" at an estimated ₹{est} per unit." if est is not None else
                                                    " without a price estimate."))

    # other slots
    if ext.get("uom"):
        slots["user_uom"] = ext["uom"]
        if slots["is_new"] and not slots["item_code"]:
            slots["uom"] = ext["uom"]
    qty = _dec(ext.get("quantity"))
    if qty is not None:
        if qty <= 0:
            replies.append("The quantity must be greater than zero.")
        else:
            slots["quantity"] = str(qty)
    if ext.get("plant_text"):
        code = chat_fallback.plant_from_text(ext["plant_text"], plants)
        if code:
            slots["plant"] = code
        else:
            replies.append(f"I don't know the plant '{ext['plant_text']}'. " + _plant_question(plants))
    if ext.get("need_by_text"):
        d = dates.resolve(ext["need_by_text"], today)
        if d is None:
            replies.append(f"I could not read the date '{ext['need_by_text']}'. By when do you need it?")
        elif d < today:
            replies.append(f"{dates.with_weekday(d)} is in the past. By when do you need it?")
        else:
            slots["need_by"] = d.isoformat()
    if ext.get("urgency") in ("Emergency", "Normal"):
        slots["urgency"] = ext["urgency"]
    elif ext.get("urgent_word") and not slots["urgency"]:
        state["pending"] = "urgency"

    # item matching
    typed = ext.get("item_code_typed")
    if not (slots["item_code"] or slots["is_new"]) and state["stage"] == "collecting":
        if typed and typed in master.items:
            _set_item(slots, master.items[typed])
            replies.append(f"I matched {typed} {master.items[typed].description} ({master.items[typed].uom}).")
        elif ext.get("item_text"):
            slots["item_text"] = ext["item_text"]
            res = Matcher(master.items).match(None, ext["item_text"])
            if res.code:
                _set_item(slots, master.items[res.code])
                it = master.items[res.code]
                replies.append(f"I matched {it.item_code} {it.description} ({it.uom}).")
            elif res.candidates:
                state["candidates"] = [{"item_code": c, "description": master.items[c].description,
                                        "uom": master.items[c].uom, "score": str(s)} for c, s in res.candidates]
                state["stage"], state["pending"] = "awaiting_selection", "selection"
            else:
                state["stage"], state["pending"] = "awaiting_new_item_estimate", "estimate"
                slots["is_new"] = True

    # UoM must be the item master unit
    if slots["item_code"] and slots.get("user_uom") and slots["user_uom"].upper() != (slots["uom"] or "").upper():
        replies.append(f"The item master unit for {slots['item_code']} is {slots['uom']}. "
                       f"Please give the quantity in {slots['uom']}.")
        slots["quantity"], slots["user_uom"] = None, None
    if slots["is_new"] and not slots["uom"] and slots.get("user_uom"):
        slots["uom"] = slots["user_uom"]

    reply, card, candidates = _next_prompt(state, slots, plants, replies)
    return _save(session, chat, state, reply, card, candidates)


def _next_prompt(state, slots, plants, replies):
    if state["stage"] == "awaiting_selection":
        opts = "; ".join(f"{i}. {c['item_code']} {c['description']} ({c['uom']})"
                         for i, c in enumerate(state["candidates"], start=1))
        replies.append(f"I found several possible items: {opts}. Which one? (or say 'none')")
        return " ".join(replies), None, state["candidates"]
    if state["stage"] == "awaiting_new_item_estimate":
        state["pending"] = "estimate"
        replies.append("I can't find this in the item master. Raise it as a new item? "
                       "What's your estimated unit price (or 'don't know')?")
        return " ".join(replies), None, []
    missing = _missing(slots)
    if not missing:
        state["stage"], state["pending"] = "awaiting_confirmation", None
        card = _card(slots)
        replies.append("Please check the request and press Confirm (or tell me what to change).")
        return " ".join(replies), card, []
    state["stage"] = "collecting"
    if state.get("pending") == "urgency" and "urgency" in missing:
        missing = ["urgency"] + [x for x in missing if x != "urgency"]
    texts = {"item": "What item do you need?", "uom": "What unit of measure (for example NOS, KG, PAIR)?",
             "quantity": f"How many {slots['uom']}?" if slots["uom"] else "What quantity?",
             "plant": _plant_question(plants), "need_by": "By when do you need it?", "urgency": URGENCY_QUESTION}
    asked = missing[:MAX_QUESTIONS]
    # The pending slot tells the extractor how to read a bare answer such as "yes" or "50".
    state["pending"] = next((s for s in asked if s in ("urgency", "quantity")), None)
    replies.extend(texts[s] for s in asked)
    return " ".join(replies), None, []


def _save(session, chat, state, reply, card, candidates=None) -> dict:
    chat.state = state
    chat.messages = list(chat.messages or []) + [{"role": "assistant", "text": reply, "card": card,
                                                  "at": m.utcnow().isoformat() + "Z"}]
    chat.updated_at = m.utcnow()
    session.commit()
    return {"session_id": chat.id, "reply": reply, "state": state, "card": card, "candidates": candidates or [],
            "mode": state.get("mode")}


def get_session(session, session_id: int) -> dict:
    chat = session.get(m.ChatSession, session_id)
    if chat is None:
        raise not_found(f"Chat session {session_id} not found")
    return {"session_id": chat.id, "state": chat.state, "messages": chat.messages}


# --- confirmation -----------------------------------------------------------------------

def _created_at() -> str:
    now = dates.now_ist()
    when = datetime.combine(dates.today_ist(), now.time())
    return when.strftime("%Y-%m-%d %H:%M")


def _summary(row, req_detail) -> str:
    if row.route == "NOT_PROCESSED":
        return f"The PR was saved but could not be processed: {row.reason}"
    clause = ""
    if req_detail and req_detail.get("fired"):
        clause = f" (v{row.policy_version} §{req_detail['fired']['clause']})"
    if row.decision == "PO":
        return f"This will be placed as {row.route} with {row.supplier_id} at ₹{row.unit_price}{clause}."
    if row.suggested_supplier_ids:
        return f"This goes to quotes ({row.route}). Suggested: {row.suggested_supplier_ids.replace(';', ', ')}{clause}."
    return f"This goes to sourcing ({row.route}); a buyer will find suppliers{clause}."


def confirm(session, session_id: int, *, user: str, role: str, department: str = "", _state: dict | None = None) -> dict:
    chat = session.get(m.ChatSession, session_id)
    if chat is None:
        raise not_found(f"Chat session {session_id} not found")
    state = copy.deepcopy(_state or chat.state)
    if state.get("stage") != "awaiting_confirmation":
        raise conflict("Nothing to confirm yet; the request is not complete")
    slots = state["slots"]
    today = dates.today_ist()
    seq = batch_service.chat_line_count(session) + 1
    pr_no = f"CH-{today:%y}-{seq:05d}"
    values = {"pr_no": pr_no, "pr_line": "1", "created_at": _created_at(), "requester": user,
              "department": department or "", "plant": slots["plant"],
              "item_code": "" if slots["is_new"] else slots["item_code"],
              "description": slots["description"] or slots["item_text"] or "", "quantity": slots["quantity"],
              "uom": slots["uom"] or "", "estimated_unit_price": slots["estimate"] or "",
              "need_by_date": slots["need_by"], "urgency": slots["urgency"]}
    chat_batch = batch_service.store_batch(session, [raw_line(values, 0)], f"chat session {chat.id}", "CHAT", "", user)
    session.flush()
    batch_ids = [b.id for b in session.scalars(select(m.Batch).where(m.Batch.source == "CHAT"))]
    csv_batch = batch_service.latest_csv_batch(session)
    ids = ([csv_batch.id] if csv_batch else []) + batch_ids
    raw = batch_service.raw_lines_for_batches(session, ids)
    result = batch_service.execute(session, raw)
    run = batch_service.store_run(session, chat_batch, result, user, None, None, "CHAT_PREVIEW")
    session.flush()
    row = next(r for r in result.rows if r.pr_no == pr_no)
    req_row = None
    req_detail = None
    if row.group_id:
        req_row = session.scalar(select(m.Requirement).where(m.Requirement.run_id == run.id,
                                                             m.Requirement.group_id == row.group_id))
        req_detail = result.decisions[row.group_id].trace if row.group_id in result.decisions else None
    summary = _summary(row, req_detail)
    audit.record(session, user, role, "chat_pr_created", "pr_line", pr_no, None,
                 {"values": values, "run_id": run.id, "route": row.route, "requirement_id": req_row.id if req_row else None},
                 None)
    state["stage"], state["pr_no"] = "created", pr_no
    chat.state = state
    chat.messages = list(chat.messages or []) + [{"role": "assistant", "text": f"Created {pr_no}. {summary}",
                                                  "at": m.utcnow().isoformat() + "Z"}]
    session.commit()
    return {"pr_no": pr_no, "decision_summary": summary, "reply": f"Created {pr_no}. {summary}", "state": state,
            "row": row.as_dict(), "run_id": run.id,
            "requirement": None if req_row is None else {"id": req_row.id, "run_id": run.id, "group_id": req_row.group_id,
                                                         "lines": req_row.line_ids}}
