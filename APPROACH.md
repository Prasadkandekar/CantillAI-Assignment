# APPROACH.md

How this PR-to-PO app is designed and built, and why. Judgment calls where the policy is silent are in `DECISIONS.md`.

> **Note:** the "AI tools used" section is a plan. Edit it so it matches what you actually used. The brief requires this to be honest.

---

## 1. The problem in one paragraph

Employees raise purchase requests (PRs). For each one, Procurement must decide: buy now against a rate contract, buy now from the preferred supplier, or ask for quotes first. The rules live in a policy document that changes over time. The app must (a) take requests by **chat**, (b) apply the **active policy** automatically, (c) let Procurement **change the policy without a code change**, and (d) give buyers a screen where they can **understand and act on** every decision.

## 2. Guiding principles

| # | Principle | What it means in practice |
|---|-----------|---------------------------|
| 1 | **The engine is deterministic; AI only translates.** | An LLM turns chat text into structured fields and a policy PDF into structured rules. It never decides a route, price or supplier. The same input always gives the same output, and every output can be tested. |
| 2 | **Policy is data.** | Limits, windows, rule order, conditions and outcomes live in a versioned JSON document in the database. The engine only interprets it. |
| 3 | **Every decision explains itself.** | Each decision stores the clause, policy version, contract or PO relied on, and the facts that made the rule fire. |
| 4 | **Never invent; ask or flag.** | Unknown item, missing quantity, ambiguous match: ask the user, or flag for the buyer. Never guess silently. |
| 5 | **Engine is separate from UI and API.** | The engine is a pure Python package with no web or DB imports. It takes data in and returns decisions. It is unit-tested alone. |
| 6 | **Nothing is hard-coded to the sample data.** | No PR numbers, item codes or supplier IDs in code. The blind batch is different from the sample. |

## 3. Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | **Python 3.12 + FastAPI** | Fast to build, automatic API docs, strong typing with Pydantic, good data tooling. |
| Database | **PostgreSQL** (SQLite for quick local tests) | Relational data (items, suppliers, contracts, POs) plus JSONB for policy documents. |
| ORM / migrations | SQLAlchemy + Alembic | Standard, readable schema. |
| Frontend | **React + Vite + Tailwind** | Quick to build a chat screen, buyer workspace and policy screen. |
| LLM | **OpenRouter** (OpenAI-compatible API, model set by `OPENROUTER_MODEL`) with JSON-schema outputs | Used for chat intake and policy reading only. Chat has a rule-based fallback if the API fails. |
| PDF reading | `pdfplumber` / `pdftotext`, then LLM to structure | Reads contract PDFs and policy documents. |
| Fuzzy matching | `rapidfuzz` + abbreviation dictionary | Cheap, explainable item matching with a confidence score. |
| Packaging | **Docker Compose** | One command: `docker compose up`. |
| Hosting | Render (or Railway) | Free tier, public link. A small keep-alive ping avoids cold starts during the blind test. |
| Tests | `pytest` | The worked examples become golden tests. |

## 4. Architecture

```
                     ┌──────────────────────────────────┐
                     │            React UI              │
                     │ Chat | Buyer workspace | Policy  │
                     │ Contracts | Preferred suppliers  │
                     └───────────────┬──────────────────┘
                                     │ REST / JSON
                     ┌───────────────▼──────────────────┐
                     │          FastAPI (api/)          │
                     │  routers, auth stub, validation  │
                     └───┬──────────┬──────────┬────────┘
                         │          │          │
          ┌──────────────▼──┐  ┌────▼─────┐  ┌─▼───────────────┐
          │ Chat service    │  │ Policy   │  │ Batch service   │
          │ (LLM + slot     │  │ service  │  │ (CSV in, rows   │
          │  filling)       │  │ (read,   │  │  out)           │
          │                 │  │  diff,   │  │                 │
          └───────┬─────────┘  │  approve)│  └───────┬─────────┘
                  │            └────┬─────┘          │
                  │                 │                │
          ┌───────▼─────────────────▼────────────────▼───────┐
          │         DECISION ENGINE  (engine/, pure Python)  │
          │ match → club → value → contracts → rules → POs   │
          │ + supplier ranking                               │
          └───────────────────────┬──────────────────────────┘
                                  │
                     ┌────────────▼─────────────┐
                     │        PostgreSQL        │
                     └──────────────────────────┘
```

Folder layout:

```
/engine        pure logic: matching, clubbing, valuation, contracts, rules, ranking, consolidation
/api           FastAPI routers and schemas
/services      chat, policy reading, batch processing, audit
/db            models and migrations
/frontend      React app
/tests         golden tests from Worked_Examples.pdf, plus unit tests
/seed          loader for master data, contracts, PO history
/submission    blind-test CSVs (pushed after 10:00 on Thu)
```

## 5. Data model (main tables)

| Table | Key columns |
|-------|-------------|
| `items` | item_code, description, uom, category, item_type, standard_price |
| `suppliers` | supplier_id, name, categories (list), status, on_time_pct, quality_rating |
| `plants` | plant, name |
| `po_history` | po_number, po_date, supplier_id, item_code, quantity, unit_price, plant, delivered_on_time |
| `contracts` | contract_id, supplier_id, supplier_name, start_date, end_date, value_cap, consumed_value, source (`REGISTER` or `PDF`), pdf_filename, warnings |
| `contract_lines` | contract_id, item_code, description, uom, rate |
| `policy_versions` | id, version_label, effective_from, status (`DRAFT`, `ACTIVE`, `SUPERSEDED`, `DISCARDED`), document (JSONB), source_text, source_filename, base_version_id, validation, created_by, approved_by, approved_at |
| `batches` | id, filename, source (`CSV` or `CHAT`), sha256, line_count, uploaded_by, uploaded_at |
| `pr_lines` | batch_id, row_index, pr_no, pr_line, created_at, plant, item_code (raw), description, quantity, uom, estimated_unit_price, need_by_date, urgency, requester, department |
| `runs` | id, batch_id, pin_version, as_of, kind (`BATCH`, `CHAT_PREVIEW`, `DRY_RUN`), versions_used, counts, created_by, created_at |
| `run_rows` | run_id, row_index, the 13 output columns (the export reads these verbatim) |
| `requirements` | run_id, group_id, item_code, plant, requirement_date, total_qty, value, is_emergency, policy_version_id |
| `decisions` | requirement_id, kind (`ENGINE` or `OVERRIDE`), overrides_decision_id, decision, route, supplier_id, unit_price, suggested, po_id, contract_id, reason, trace (JSONB), status (`PROPOSED`, `APPROVED`, `OVERRIDDEN`), comment |
| `orders` | run_id, order_no (`PO-0001`, `PO-OVR-{decision}`, `SRC-0001`), type (`PO` or `SOURCING`), route, supplier_id, plant; unique per run and order_no |
| `order_lines` | order_id, requirement_id, decision_id, quantity, unit_price, contract_id |
| `audit_log` | id, who, role, at, action, entity_type, entity_id, before (JSONB), after (JSONB), comment |
| `contract_consumption` | contract_id, requirement_id, value (qty × contract rate), requirement_date, order_id (written on approval, for display; batch runs never read it) |

## 6. Policy as data

### 6.1 What a policy document looks like

```json
{
  "version": "5.0",
  "effective_from": "2026-04-01",
  "parameters": {
    "club_keys": ["item_code", "plant"], "club_created_days": 14, "club_needby_days": 7, "club_new_items": false,
    "urgency_values": ["Normal", "Emergency"], "emergency_urgency_values": ["Emergency"],
    "valuation_ladder": ["contract", "last_po", "standard_price"], "new_item_valuation": "requester_estimate",
    "price_history_days": 365, "bought_history_days": 365,
    "eligible_supplier_statuses": ["Active"],
    "emergency_max_value": 500000, "spot_max_value": 200000, "rfp_min_value": 1000000,
    "capex_suggestion_count": 5, "rfq_suggestion_count": 3, "rfp_suggestion_count": 5,
    "preferred_history_days": 548,
    "ranking_weights": {"frequency": 0.30, "recency": 0.25, "contract": 0.15, "on_time": 0.15, "quality": 0.15},
    "ranking_recency_decay_days": 180, "ranking_tie_break": ["recency", "quality", "supplier_id"],
    "on_time_pct_scale": 100, "quality_rating_scale": 5, "topup_weights": {"on_time": 0.5, "quality": 0.5},
    "preferred_export_count": 3,
    "consolidate_decisions": ["PO"], "consolidation_keys": ["supplier_id", "plant", "route"], "consolidation_hours": 24
  },
  "rules": [
    { "id": "1.2", "clause": "1.2", "text": "A line that matches no item master item is a new item ...",
      "when": { "all": [ {"fact": "is_new_item", "op": "eq", "value": true} ] },
      "outcome": { "decision": "SOURCING_REQUEST", "route": "NEW_ITEM_SOURCING", "supplier": {"strategy": "none"} } },
    { "id": "5.1", "clause": "5.1", "text": "The item type is Capex ... Needs capex approval.",
      "when": { "all": [ {"fact": "item_type", "op": "eq", "value": "Capex"} ] },
      "outcome": { "decision": "SOURCING_REQUEST", "route": "CAPEX_SOURCING", "supplier": {"strategy": "suggest", "count": "$capex_suggestion_count"} } },
    { "id": "5.2", "clause": "5.2",
      "when": { "all": [ {"fact": "contract_usable", "op": "eq", "value": true} ] },
      "outcome": { "decision": "PO", "route": "CONTRACT_PO", "supplier": {"strategy": "contract"} } },
    { "id": "5.3", "clause": "5.3",
      "when": { "all": [
        {"fact": "is_emergency", "op": "eq", "value": true},
        {"fact": "group_value", "op": "lte", "value": "$emergency_max_value"},
        {"fact": "bought_from_active_365d", "op": "eq", "value": true} ] },
      "outcome": { "decision": "PO", "route": "EMERGENCY_PO", "supplier": {"strategy": "preferred_first"} } }
  ]
}
```

Rules 5.4 to 5.6 follow the same shape, and each rule carries its clause text from the policy PDF. The complete file is `engine/policies/policy_v5_0.json`. New items (1.2) are the first rule. The order of the `rules` list is the rule order; nothing sorts by id. Every number the engine uses is in `parameters`, and the engine code contains none of them (a test scans every `engine/**/*.py`, including comments and docstrings, and fails on 200000, 500000, 1000000, 14, 7, 24, 365 or 548; engine comments name policy sections by topic, never by clause number, D69).

### 6.2 How the engine reads it

- **Condition grammar.** A condition is `{fact, op, value}`, combined with `all` / `any` and nested to any depth. The ops are `eq, ne, lt, lte, gt, gte, in, not_in`. A value is a literal or `"$param_name"`, resolved from `parameters` of the version that applies. Boundaries are ops: spot `lt`, emergency `lte`, RFP `gte`. A null fact never satisfies an ordering op.
- **Evaluator.** The rules are walked in list order and the first fulfilled match wins. There is no rule-id special case anywhere (a test checks for one). Every condition is evaluated without short-circuit, so the trace shows each fact value, resolved parameter and pass/fail. A rule that matches but whose supplier strategy finds nobody lets the walk continue to the next rule.
- **Fact registry (`engine/facts.py`).** A dict of name → one small decorated function, with a type and the parameters it needs. The initial set: item_code, item_type, category, uom, plant, urgency, is_emergency, group_value, total_quantity, line_count, requirement_date, need_by_lead_days, department, contract_exists, contract_usable, contract_remaining_ceiling, bought_from_active_365d, last_po_price, preferred_list_size, top_supplier_on_time_pct, top_supplier_quality, is_new_item, plus value_source and requester. Numbers in names are names only: `bought_from_active_365d` reads its window from `bought_history_days`. Adding a fact is one function. The validator, the LLM prompt, the diff text and the UI all read the registry.
- **Outcomes are data.** `{decision, route, supplier: {strategy, count}}`. `route` is a free string. Strategies form a small registry: `contract` (contract supplier at contract rate), `preferred_first` (rank-1 eligible preferred supplier at its reference price), `suggest` (count: preferred list, then category top-up by `topup_weights`), `none`. Counts may be `$param`.
- **Supplier eligibility (5.7).** This is the parameter `eligible_supplier_statuses`, applied in one function to contracts, history, preferred lists, top-up and overrides, with a final output guard. No Blocked or Inactive supplier can appear in a PO or a suggestion.
- **Validator (`engine/policy_validator.py`).** It rejects, with a JSON path and a clear message: unknown fact, unknown op, unknown strategy, undefined `$param`, a `$param` whose value has the wrong type for its fact (for example `"2.5 lakh"` for a value limit), schema errors, op/type mismatches, duplicate rule ids, and bad or missing required parameters (D70, D71). It warns about new routes, unusual decisions, weights not summing to 1, unreachable rules and a missing effective date. A policy that fails is never applied.
- **Every decision records** the fired rule's id, clause and text, the policy version, every evaluated fact and condition, the contract or PO relied on, and the ranking table.

### 6.3 Why this lets amendments work without code

| Amendment type | How it is handled |
|----------------|-------------------|
| Change a limit (₹2 lakh becomes ₹3 lakh) | Edit a `parameters` value. |
| Change a category rule ("Safety & PPE goes to RFQ above ₹1 lakh") | Insert a rule with a `category` condition. |
| Plant-only parameter ("CHK1 Emergency limit is ₹2.5 lakh") | Add a parameter `chk1_emergency_max_value`, insert a rule `plant eq CHK1 … group_value lte $chk1_emergency_max_value` before the generic emergency rule, and add `plant not_in ["CHK1"]` to the generic rule so that both raising and lowering work. |
| Change the order of rules | Reorder the list. |
| Change clubbing windows or the consolidation window | Edit `parameters` (`club_created_days`, `club_needby_days`, `consolidation_hours`). |
| Change ranking weights | Edit `parameters.ranking_weights`. |
| Change suggestion counts or eligible supplier statuses | Edit `*_suggestion_count` or `eligible_supplier_statuses`. |
| Needs a **fact the engine does not compute yet** | The one honest limit. Facts are a registry, so adding one is a small, isolated code change. The policy screen warns "unknown fact" instead of silently ignoring a condition. |

Proof tests (`tests/test_policy_changes.py`) edit only the JSON in memory and rerun the sample batch: spot limit to ₹3 lakh, a CHK1 Safety & PPE rule, emergency limit to ₹7.5 lakh, a CHK1-only emergency limit, clubbing window to 7 days, two rules swapped, an unknown fact rejected, and new ranking weights. None needs an engine change. Each test asserts the exact set of lines that change (D75).

### 6.4 Update flow (upload, preview, approve, activate)

1. **Upload** an amendment (PDF, DOCX or text) or **describe** it in chat.
2. **Read:** the LLM produces a *proposed full policy document* in the JSON schema above, starting from the current active version.
3. **Validate:** the hand-written validator `engine/policy_validator.py` (no JSON-schema library) checks the document shape, unknown facts, ops and strategies, undefined `$param`s, the type of every literal and `$param` value against its fact, the required parameters, and warns about new routes, unreachable rules and a missing effective date (the app asks for it). A draft with errors can be edited but not approved.
4. **Diff:** a structural diff of old vs new (parameters changed, rules added, removed, moved or edited), then turned into **plain-language bullets**: "Emergency limit rises from ₹5,00,000 to ₹7,50,000", "New rule: for plant CHK1, Safety & PPE items above ₹1,00,000 go to RFQ".
5. **Impact preview:** a dry run over the latest batch: "37 of 186 lines would change decision". This catches wrong readings before approval.
6. **Approve:** a Procurement user approves, and the new version is saved as `ACTIVE` with its `effective_from`. The old version becomes `SUPERSEDED` and is never edited.
7. **Audit:** who uploaded, who approved, when, and the source text.

A human always approves. The LLM's reading is a draft.

### 6.5 Which version applies to a requirement

The version whose `effective_from` is on or before the **requirement date**, taking the latest such version. The caller can also pin a version explicitly (`policy_version`), or give `as_of` to select by that date instead. A requirement uses the version of its first line. Statuses are DRAFT → ACTIVE → SUPERSEDED (plus DISCARDED drafts), and approved versions are immutable. See Decisions D1 and D56.

## 7. The decision engine

Pure function: `decide(pr_lines, master_data, contracts, policy) -> decisions`.

```
Step 1  Choose policy version per line  latest approved version effective on the line's creation date (or the pin / as_of)
Step 2  Normalise & validate lines      bad rows become NOT_PROCESSED with a reason (uses that version's urgency values)
Step 3  Match items                     code first, then text; NEW if nothing fits
Step 4  Club lines into requirements    sort by (created_at, pr_no, pr_line); join earliest eligible requirement
                                        of the same version, using that version's windows; a requirement keeps
                                        the version of its first line
Step 5  Process requirements in order of requirement date:
          a. find applicable contracts   covers item, date in range, supplier Active
          b. value the requirement       contract rate, else last PO in 365d, else standard price
          c. check ceilings              consumed + value at contract rate <= cap; pick lowest rate that fits
          d. compute facts               value, emergency, bought-in-365d, etc.
          e. walk the rules in order     first match wins
          f. choose supplier / suggestions via the preferred list (section 8)
          g. if a contract PO: debit the ceiling by qty × that contract's rate
Step 6  Consolidate POs                 same supplier + plant + route and same policy version, within
                                        consolidation_hours of the PO's first requirement
Step 7  Write one output row per PR line
```

Key correctness points (all checked against the worked examples):

- Clubbing compares to the **first** line of a requirement, not the previous line, so windows do not "chain".
- The ceiling is consumed in order of **requirement date**, so earlier requirements get first call on a contract.
- Rule order matters: Capex (5.1) beats contracts (5.2), contracts beat value limits.
- Boundaries: `< ₹2,00,000` for spot, `<= ₹5,00,000` for emergency, `>= ₹10,00,000` for RFP.

## 8. Preferred supplier list and ranking

**Who is on the list (6.1):** Active suppliers with at least one PO for the item in the 548 days before the date, or a contract for the item that started on or before the date (even if expired).

**Score (all parts scaled 0 to 1, weights are in the policy so they are versioned):**

```
score = 0.30 * frequency   (POs in 548 days / the most POs of any candidate for this item)
      + 0.25 * recency     (exp(-days_since_last_PO / 180), 0 if no PO)
      + 0.15 * contract    (1 if the supplier has had a contract for this item, else 0)
      + 0.15 * on_time     (supplier on-time % / 100)
      + 0.15 * quality     (quality rating / 5)
```

Ties break on higher recency, then higher quality, then supplier ID. I tested this formula against the three ranked lists in the Worked Examples and it reproduces all three orders (gloves: S029 then S030; cylinders: S023, S022, S024; MIG wire: S009 then S010). The reasoning behind each weight is in `DECISIONS.md` (D32).

**Why a buyer can trust it:** the buyer screen shows, for each supplier, the raw numbers (POs, last PO date, contract yes/no, on-time %, quality), the weighted contribution of each, and the final score. A rank is never a black box.

**Reference price (6.3):** the supplier's most recent PO price in 548 days, else its latest contract rate.

**Suggestions for sourcing (6.4):** preferred list in order, then top up from other Active suppliers listing the item's category, ordered by an on-time and quality composite. New items get none.

**Export:** `item_code, rank, supplier_id, reference_price` for the top 3, as of a chosen date.

## 9. Chat intake

The chat is a **slot-filling conversation**:

1. The user types free text ("need 200 nitrile gloves for Chakan by next Friday").
2. The LLM extracts `{item_text, quantity, uom, plant, need_by, urgency}` as structured JSON. Relative dates ("next Friday") are resolved against today's date in IST in code, not by the LLM.
3. The backend (not the LLM) runs the **item matcher** on `item_text`:
   - one clear match: confirm it;
   - two or three close matches: ask the user to pick;
   - nothing close: say so and offer to raise it as a **new item** with an estimated price. It never invents a code.
4. The assistant asks only for what is **still missing**, one or two things at a time: quantity, plant, need-by, urgency.
5. It shows a **confirmation card** (item, quantity, plant, date, urgency) with Confirm and Edit.
6. On confirm it creates the PR line, then runs the engine so the user can see "this will be placed as a PO" or "this will go to quotes".

Safeguards: the LLM output is validated against a schema; if the LLM is unavailable, a rules-based parser still handles the common patterns; the user always confirms before anything is created.

## 10. Buyer workspace

One list of **requirements** (not PR lines). Each row shows: item, plant, value, decision, route, supplier and price (or suggested suppliers), status. Opening a row shows:

- the **PR lines** that were clubbed (with dates, so the user sees *why* they were clubbed);
- the **why-panel**: the clause, policy version, facts that triggered it, the contract (with remaining ceiling) or the PO relied on, and the preferred-supplier ranking table;
- one obvious primary button: **Approve** (creates the PO or RFQ/RFP), and a secondary **Override**, which requires a comment.

Every action writes to `audit_log` with who, when, before and after. An override creates a new PROPOSED decision linked to the original. The original's status becomes OVERRIDDEN, and nothing else on it changes (policy 8.1). Approve acts on the latest decision, so an override can be approved too (order `PO-OVR-…` or `SRC-…`). Approving an engine PO approves every requirement still on that PO; overridden ones are excluded. See D43, D62.

## 11. API

| Method and path | Purpose |
|-----------------|---------|
| `POST /api/process-batch` | Body: PR batch CSV (optional `policy_version`, `as_of`). Returns decisions as JSON (`?format=csv` returns the output CSV). |
| `GET /api/runs/{id}/export` | Download decisions in the required column format. |
| `GET /api/health` | DB status, active policy, whether the LLM is enabled (never the key). |
| `GET /api/runs`, `GET /api/runs/{id}` | Run list and summary. |
| `POST /api/chat` | Chat turn: returns assistant reply and conversation state. |
| `POST /api/chat/{session_id}/confirm` | Creates a PR from a confirmed chat and returns the engine decision. |
| `GET /api/requirements` | Buyer workspace list. |
| `GET /api/requirements/{id}` | Detail with why-panel. |
| `POST /api/requirements/{id}/approve` | Creates the PO or sourcing order for the current decision. |
| `POST /api/requirements/{id}/override` | Needs `comment`. |
| `GET /api/audit` | Audit rows for an entity. |
| `GET /api/policy`, `GET /api/policy/{id}` | List versions; one version with validation and diff. |
| `POST /api/policy/drafts/upload` | Upload an amendment (PDF, DOCX, text), returns a draft with diff. |
| `POST /api/policy/drafts/from-chat` | Describe a change in chat, returns a draft with diff. |
| `PUT /api/policy/{id}` | Edit a draft's JSON or effective date directly. |
| `POST /api/policy/{id}/dry-run` | "N of M lines change" on the latest batch. |
| `POST /api/policy/{id}/approve`, `POST /api/policy/{id}/discard` | Activate from its effective date; discard a draft. |
| `GET /api/preferred-suppliers?as_of=` | Preferred lists (JSON, or CSV via `/export`). |
| `GET /api/contracts`, `POST /api/contracts`, `POST /api/contracts/extract-pdf` | List contracts; add one (manual or extracted from a PDF, always with a human confirm step). |
| `GET /api/items`, `/api/suppliers`, `/api/plants` | Master data. |

## 12. Contracts

- Load the register and the lines (as at 31 Oct).
- The two contracts that exist only as PDFs (`RC-2026-031`, `RC-2026-033`) are seeded from `seed/pdf_contracts.json` with consumed value 0, so a fresh start gives the same decisions (D64). Those values were produced by the app's own extractor and checked by hand, and a test asserts the extractor still reproduces them.
- Further PDF contracts are added through **Extract from PDF**: text is read from the PDF, parsed with regular expressions (contract number, supplier ID, dates, ceiling, schedule table), the LLM is the fallback for fields the regex misses, and the buyer **confirms** the extracted values before saving. They start with consumed value 0.
- I cross-checked the 10 register contracts against their signed PDFs: supplier, dates and ceiling all match.

## 13. Testing

- **Golden tests** from `Worked_Examples.pdf`: all 14 decisions, including the numbers I can verify by hand (₹32,547 and ₹23,227 for the two bolt requirements, ceiling left of ~₹38,000 on the bearing contract).
- **Unit tests:** clubbing boundaries (exactly 14 days, exactly 7 days), valuation fallbacks, ceiling order, rule order, consolidation window, ranking on the three example lists.
- **Policy tests:** apply a sample amendment (change a limit, add a plant-only rule) and assert decisions change.
- **Property check:** no decision ever names a Blocked or Inactive supplier.

## 14. Build plan (Mon 16 Nov to Thu 19 Nov, 10:00 IST)

| When | Goal |
|------|------|
| Mon | Seed data, schema, engine skeleton: matching, clubbing, valuation, contracts. Golden tests 1 to 8 passing. |
| Tue | Rules from JSON, ranking, consolidation, batch API and CSV export. All 14 golden tests passing. Policy versioning and the diff. |
| Wed | Chat intake, policy upload and chat-change, buyer workspace, contracts screen. Deploy to Render, test the hosted link. |
| Thu before 10:00 | README, docker compose check, final DECISIONS.md and APPROACH.md, tag the final commit, submit the form. **Freeze: no code changes after 10:00.** |

## 15. Blind-test playbook (Thu 10:00 to 12:00)

1. Run 1: upload the new batch, process under v5.0 (pin `policy_version=5.0`), export.
2. Read the amendment. Upload it in the Policy screen, review the plain-language diff, set or confirm the effective date, approve.
3. Run 2: reprocess the same batch under the new version, export.
4. Export the preferred supplier lists as of the date given.
5. Copy the three CSVs into `submission/`, push before 12:00. Nothing else changes.

## 16. AI tools used (edit to match reality)

- **Coding help:** an AI coding assistant for boilerplate, tests and refactors. I reviewed every part, and I can explain and change any of it.
- **Inside the app:** an LLM accessed through **OpenRouter** (model set by `OPENROUTER_MODEL`) for (a) chat intake, extracting structured fields, and (b) reading policy and contract documents into structured JSON. It never decides routes, prices or suppliers.
- **Fallbacks:** rule-based parsing for chat, regex parsing for contracts, so the app still works if the API is down.

## 17. Known limitations

- A truly new kind of **fact** (something the engine does not compute) needs a small code addition; the policy screen warns instead of ignoring it.
- Item matching is token- and fuzzy-based, so very short or unusual descriptions may be flagged for the buyer instead of matched.
- Authentication is a simple user selector (name stored with each action), enough for the audit trail but not real security.
