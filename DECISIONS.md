# DECISIONS.md

The policy (v5.0) does not cover every situation in the data. This file records what I noticed, what I decided, and why. Each entry: **Noticed**, **Decided**, **Why**.

Data findings quoted here come from checking the kit files (item master, supplier master, PO history, contract register and PDFs, and the 186-line sample batch).

**Contents**

- A. Dates, versions and reading the policy
- B. Cleaning and rejecting input (NOT_PROCESSED)
- C. Item matching
- D. Clubbing
- E. Valuation
- F. Contracts
- G. Decision rules
- H. Suppliers: preferred list, ranking, suggestions
- I. PO consolidation and IDs
- J. Chat, buyer actions and policy changes

---

## A. Dates, versions and reading the policy

### D1. Which policy version applies to a requirement
- **Noticed:** Policies have an effective date, but a batch is processed on a different day than the PRs were created. The brief's Run 2 says "reprocess the same batch" after approving an amendment.
- **Decided:** The version used is the latest one whose `effective_from` is on or before the **requirement date** (the creation date of the requirement's first line). The batch API also accepts an explicit `policy_version` to pin one version for the whole run.
- **Why:** The policy itself judges contracts and history "as of the requirement date", so a decision should follow the rules in force when the need arose. The pin option avoids surprises when someone wants "everything under v6" for a what-if. The impact preview shows how many lines would change.
- **Amended (design):** The version is chosen per line from its creation date, and a requirement uses the version of its first line. The clubbing windows come from the policy, so clubbing needs a version before the requirement exists. A line may only join a requirement under the same version, so a requirement never mixes versions. The batch API's `as_of` replaces the per-line date for version selection only. Contract validity and history are still checked at the requirement date (2.3). A pin wins over `as_of`. Selection considers every approved version (ACTIVE and SUPERSEDED); drafts never apply.

### D2. Time zone and "within N days"
- **Noticed:** Timestamps have no time zone. The policy says "within 14 calendar days" for creation, "within 7 days either side" for need-by, and "within 24 hours" for consolidation.
- **Decided:** All times are IST. The 14-day and 7-day tests use **calendar-date differences, inclusive** (day 14 qualifies, day 15 does not). The 24-hour test uses the **exact timestamp difference, inclusive** (up to 24h 00m).
- **Why:** The policy uses "calendar days" for the first two and "hours" for the third, so I mirrored the unit each time. Inclusive matches how "within" is normally read.
- **Amended (design):** The numbers are the policy parameters `club_created_days`, `club_needby_days` and `consolidation_hours`. Only the units and the inclusive reading are fixed in code. The strict policy-as-data rule forbids those numbers in engine code.

### D3. Sample batch has PRs dated after today
- **Noticed:** 37 lines are timestamped 17 to 20 Nov 2026, later than the date the kit was issued (16 Nov). Contract `RC-2026-033` starts on 20 Nov.
- **Decided:** Process every line by its own timestamp. Nothing is rejected for being "in the future".
- **Why:** The batch is simulated, and the policy is entirely driven by the creation timestamp, so the timestamp is the source of truth.

### D4. Boundary values
- **Noticed:** The policy mixes "below", "≤", and "or more".
- **Decided:** Exactly ₹2,00,000 is **not** a spot PO (it goes to RFQ); exactly ₹5,00,000 **is** still emergency-eligible; exactly ₹10,00,000 is RFP. Money is compared at paise precision with Decimal, never floats.
- **Why:** Matches the policy wording and Worked Example 9 ("at or above ₹2 lakh"). Decimal avoids rounding errors at the edges.
- **Amended (design):** The boundaries live in the policy JSON as the ops of each rule (`lt $spot_max_value`, `lte $emergency_max_value`, `gte $rfp_min_value`), not in code. An amendment can turn "below" into "up to" by changing an op.

---

## B. Cleaning and rejecting input (NOT_PROCESSED)

### D5. Unknown plant
- **Noticed:** One line (PR-26-00173) uses plant `PUN2`. The plants file has only PUN1 and CHK1, and the policy applies to those two.
- **Decided:** Output route `NOT_PROCESSED`, reason "Unknown plant PUN2; policy covers PUN1 and CHK1". The line is not clubbed or valued.
- **Why:** Plant drives clubbing and consolidation. Guessing a plant could merge it into the wrong requirement or place a PO for a site Corvo does not run.

### D6. Zero or negative quantity
- **Noticed:** PR-26-00172 has quantity 0.
- **Decided:** `NOT_PROCESSED`, reason "Quantity must be greater than zero". It does not join or affect any requirement.
- **Why:** A zero-quantity line has no value and could still extend a clubbing window or distort a requirement. A buyer should correct it at the source.

### D7. Bad rows never fail the whole batch
- **Noticed:** The brief says to give `NOT_PROCESSED` with a reason for lines I decide not to process.
- **Decided:** Row-level validation (missing PR number, unparseable date or quantity, need-by before creation, unknown UoM for a matched item, duplicate PR line in the file) yields `NOT_PROCESSED` for that row only. The rest of the batch runs. A missing required column rejects the file with a clear message.
- **Why:** One bad row should not block 185 good ones.

### D8. Duplicate PR lines
- **Noticed:** No duplicates in the sample, but a real batch might repeat a `pr_no, pr_line`.
- **Decided:** The first occurrence is processed. Later duplicates are `NOT_PROCESSED` with reason "Duplicate of PR line already in this batch". Re-uploading a file that was already processed warns the user instead of creating duplicates.
- **Why:** Processing twice would double the quantity and wrongly push requirements over the limits.

### D9. "Urgent" typed in the description while urgency says Normal
- **Noticed:** Four lines have text like "nitrile coated gloves - urgent" but the urgency column says Normal. Only six lines are flagged Emergency.
- **Decided:** The **urgency field** is the only thing that makes a requirement an emergency. The text is shown to the buyer as a warning in the reason ("description mentions urgent, urgency field is Normal"). In chat, the assistant asks the urgency question explicitly.
- **Why:** Emergency allows buying without quotes, so it must be a deliberate choice, not inferred from free text. Reading "urgent" from text would be an easy way to bypass sourcing.

### D10. Text notes such as "as per sample" and "(repeat)"
- **Noticed:** Some descriptions carry extra words ("as per sample", "(repeat)", "for maintenance").
- **Decided:** The matcher strips these note words before matching and keeps the original text on the line. "As per sample" lines are matched normally but flagged for the buyer, since the supplier needs the sample.
- **Why:** The words do not identify the item, but they carry buying information the buyer should not lose.

---

## C. Item matching

### D11. If a code is given, trust it
- **Noticed:** Every coded line in the sample exists in the item master and agrees with the master's description and UoM.
- **Decided:** A valid code wins (policy 1.1). An unknown code is `NOT_PROCESSED` ("unknown item code"); it is never silently turned into a new item. If the given description and code clearly disagree, the line is still processed by code and flagged.
- **Why:** The policy says to use the code. A mistyped code is a data error, not a new item.

### D12. How free-text lines are matched
- **Noticed:** 39 lines have no code, with short forms ("brg 6308 ZZ", "hyd hose 1/2 inch 2 wire", "pneu cylinder 50x100", "taper roller brg 32210").
- **Decided:** Normalise (lowercase, strip punctuation and note words), expand an abbreviation dictionary (brg → bearing, hyd → hydraulic, pneu → pneumatic and so on), then score by token overlap and fuzzy similarity against the item master. Rules:
  - best score above a high threshold **and** clearly ahead of the runner-up: match;
  - otherwise: in the **batch**, treat as NEW with a flag "low-confidence match, buyer to verify"; in **chat**, ask the user to choose.
  - Numbers and sizes (6308, 50x100, M12x100) must match exactly. A near miss on a size is not a match.
- **Why:** I prototyped this on the 39 no-code lines. A simple token match found a perfect match for 36 of them. Three more ("brg 6308 ZZ", "monitor 24\"", "hydraulic pump seal kit (hydrax) (repeat)") only fell short because of note words or spelling ("24 inch", "6308-ZZ", "(repeat)"), which the normalisation step handles. Exactly two have no counterpart in the master ("Drinking water purifier 50 LPH", "Ultrasonic thickness gauge"), which agrees with Worked Example 13. Requiring exact sizes avoids the worst mistake: ordering 6205 bearings when 6308 were asked for.
- **Amended (design):** The score is `rapidfuzz.fuzz.token_set_ratio`. The thresholds (auto-match 90, margin 8, candidate 60, up to 3 candidates), the abbreviations, phrase synonyms and note phrases live in `backend/engine/data/matching_dictionary.json`, so tuning needs no code change. Every size token in the request must appear exactly in the item. An item with an extra size the request lacks can be offered as a candidate but is never auto-matched.

### D13. Matching confidence vs inventing items
- **Noticed:** The brief scores "avoid inventing items".
- **Decided:** The system never creates an item code. A no-match becomes `resolved_item_code = NEW`. It does not guess the "closest" item when the match is weak.
- **Why:** A wrong match silently changes the supplier, price and route. NEW with a flag only costs the buyer a look.

### D14. Capex items typed without a code
- **Noticed:** "eot crane 5 ton" has no code, but the item master has `ITM-1071 EOT crane 5 ton` (Capex). Worked Example 12 shows it as CAPEX_SOURCING with five suggested suppliers.
- **Decided:** Match first, then apply rule 5.1. Capex status comes from the matched item's `item_type`.
- **Why:** Matching must come before every rule, because the item type decides the rule.

---

## D. Clubbing

### D15. What a line is compared to
- **Noticed:** Policy 2.2 says created "within 14 days of the requirement's first line" and need-by "within 7 days of the first line's need-by".
- **Decided:** Always compare to the **first line** of the requirement, never the latest line. Lines are processed in order of (created_at, pr_no, pr_line). A line joins the **earliest** open requirement it qualifies for.
- **Why:** This stops windows from "chaining" forward indefinitely. I checked it on the four hex-bolt lines in Worked Example 14: lines 34 and 32 form one requirement (value ₹32,547) and lines 31 and 35 form another (₹23,227), matching the examples' values exactly.

### D16. Emergency and normal lines together
- **Noticed:** Policy 2.3 says if any line is Emergency, the requirement is an emergency.
- **Decided:** Emergency and normal lines for the same item and plant club together under the same date rules, and the whole requirement becomes an emergency.
- **Why:** Straight reading of 2.3. Otherwise a single "Emergency" tick could be used to carve a requirement out of its group.

### D17. Different units of measure for the same item
- **Noticed:** None in the sample (UoM always matches the master).
- **Decided:** If a line's UoM differs from the item master UoM, it is `NOT_PROCESSED` instead of being converted.
- **Why:** There are no conversion factors in the data, so any conversion would be invented.

### D18. New items are never clubbed
- **Noticed:** Policy 1.2 says new items are never clubbed. In the sample, many lines have no item code (39), but nearly all of them still match a master item. Only two are truly new.
- **Decided:** Only lines that stay **NEW after matching** are never clubbed. A line that matched a master item clubs normally, even when typed without a code.
- **Why:** The never-clubbed rule is about items that are not in the master, not about missing codes.

---

## E. Valuation

### D19. Which past PO sets the price
- **Noticed:** Policy 3.1(b) says "the price on the most recent PO for the item in the 365 days before the requirement date". It does not say whether a Blocked or Inactive supplier's PO counts.
- **Decided:** Any PO for the item counts for **valuation**, regardless of supplier status. Only POs on or before the requirement date count. Ties on the date go to the higher PO number.
- **Why:** The valuation is a price estimate, not a purchase. A past price from a supplier we no longer use is still real market evidence. Excluding it would sometimes push valuation to the standard price, which can be stale. Supplier status matters only for **who we buy from**.

### D20. The estimated price on coded lines
- **Noticed:** 60 lines have no estimated price, and many coded lines do have one.
- **Decided:** Estimated price is used **only for new items** (1.2). For matched items it is ignored in valuation, as the policy's price ladder lists no role for it.
- **Why:** Following the written ladder keeps values consistent and stops requesters influencing the route by under-estimating.

### D21. New item with no estimate
- **Noticed:** A new item needs an estimate to be valued, but some lines may not have one.
- **Decided:** Still `NEW_ITEM_SOURCING`, with value shown as blank/0 and reason "no requester estimate; buyer to value". It does not block the line.
- **Why:** The route does not depend on value for new items (always sourcing), so there is no reason to reject.

### D22. Value vs the price actually paid on a PO
- **Noticed:** For SPOT_PO and EMERGENCY_PO the requirement is *valued* using the last PO price (any supplier, 3.1b) but the PO is placed with the first preferred supplier at **its own reference price** (6.3). These can differ.
- **Decided:** `group_value_inr` is always the policy valuation. `unit_price` is the supplier's reference price. Both are reported, and the reason text shows both when they differ.
- **Why:** The limits apply to the valuation (2.1, 3.1). The price on the PO is what we would really pay. Hiding either number would confuse a buyer.

---

## F. Contracts

### D23. A Blocked or Inactive supplier holding a contract
- **Noticed:** `RC-2026-005` (Metalink Alloys, S004) covers aluminium plate and MS flat, but S004 is **Blocked**.
- **Decided:** The contract is **not applicable** (4.1 requires an Active supplier) and S004 is excluded from preferred and suggestion lists (5.7). The decision is made as if there were no contract, and the reason notes "contract RC-2026-005 skipped: supplier Blocked".
- **Why:** 4.1 and 5.7 are explicit. Noting the skipped contract helps a buyer see why a "contract item" went to quotes.

### D24. Expired contracts and future contracts
- **Noticed:** `RC-2025-020` (Castrol) ended 30 Sep 2026. `RC-2026-033` starts 20 Nov 2026. `RC-2025-014` ends 30 Nov 2026.
- **Decided:** A contract applies only when the **requirement date** is between start and end (inclusive). An expired contract cannot be used, but still puts its supplier on the preferred list (6.1b). A future-dated contract is invisible to earlier requirements.
- **Why:** Straight reading of 4.1 and 6.1(b). The requirement date, not the processing date, is the test.

### D25. How the ceiling is consumed
- **Noticed:** The register's `consumed_value` is as at 31 Oct; PDF-only contracts start at 0; requirements consume in order of requirement date (4.2).
- **Decided:**
  - Start each contract at its register `consumed_value` (0 for PDF-only).
  - Process requirements in order of requirement date (ties: creation timestamp, then PR number).
  - For each applicable contract, test `consumed + (total qty × that contract's own rate) <= cap`.
  - Among contracts that fit, use the **lowest rate** (4.3).
  - A requirement that does **not** end as a contract PO does **not** consume ceiling. A buyer override of a contract PO to something else releases the amount.
  - If **no** contract fits, value at the **lowest applicable contract rate** (3.1a) and continue down the rules.
- **Amended (design review):** A contract PO debits the contract by `total qty × that contract's rate` (rounded to paise), the same amount the fit test used, never by the requirement value. The valuation ladder is editable (D65), so the requirement value may come from another price source. "An override releases the amount" has a narrow meaning: batch runs never see overrides (D44), so the release only means that an overridden contract PO writes no `contract_consumption` row when anything is approved.
- **Why:** This reproduces Worked Examples 3 and 4: bearings on `RC-2026-002` have only ₹38,000 left, so the requirement of about ₹2.2 lakh goes to RFQ; hex bolts skip the cheaper `RC-2026-015` (₹12,000 left) and use `RC-2026-013`.

### D26. Contracts that exist only as PDFs
- **Noticed:** Two signed contracts are missing from the register: `RC-2026-031` (Pneumatic Point, starts 15 Nov) and `RC-2026-033` (supplier S035, starts 20 Nov). I compared the other 10 PDFs to the register: supplier, dates and ceiling all match.
- **Decided:** Both are loaded as contracts with source `PDF` and consumed value 0. The PDF is treated as binding from its start date (4.4). If the PDF and the register ever disagree, the **signed PDF wins**, and the app shows a warning. Buyers can add more through the contracts screen (manual or extracted from the PDF, always with a confirm step).
- **Why:** The policy says PDF-only contracts are binding. A signed document outranks a monthly-updated register.

---

## G. Decision rules

### D27. Emergency without history, or above ₹5 lakh
- **Noticed:** 5.3 needs value ≤ ₹5,00,000 **and** a purchase in the last 365 days from an Active supplier.
- **Decided:** If either fails, the requirement is **not** blocked, it simply falls to 5.4, 5.5 and 5.6 in order. An emergency above ₹5 lakh therefore goes to RFQ or RFP, and the reason mentions it was an emergency.
- **Why:** "The first rule that fits decides." No rule says emergencies skip quotes beyond the limits.

### D28. "Bought from an Active supplier in the last 365 days"
- **Noticed:** Ambiguous: bought by whom, and active when?
- **Decided:** At least one PO for the item with `po_date` in the 365 days up to and including the requirement date, from a supplier whose **current** status is Active.
- **Why:** The master has only today's status, so "Active" means the status we have. A Blocked supplier's history does not prove a safe source.
- **Amended (design):** This is the fact `bought_from_active_365d`. The "365" is only in its name. The window is the parameter `bought_history_days` (365 in v5.0), and "Active" is the parameter `eligible_supplier_statuses`. It is a separate parameter from `price_history_days` (3.1b) so that an amendment can change one window without the other.

### D29. Services and Capex in the normal rules
- **Noticed:** 8 items are Services and 5 are Capex. The rules mention Capex only in 5.1.
- **Decided:** Services follow the same rules as materials (contract, then emergency, spot, RFQ, RFP). Capex lines are always sourcing, but are still **clubbed and valued** like any item, because the policy says "apply every limit to the requirement's total".
- **Why:** The policy has no special service rule, so I applied the general rules.

### D30. A PO route but no usable supplier
- **Noticed:** 5.3 and 5.4 name the "1st preferred supplier". If the list were somehow empty or all excluded, there is nobody to buy from.
- **Decided:** This cannot happen if the history test passes, because that test requires an Active supplier with a PO in 365 days (inside the 548-day list window). As a safety net, if it ever did, the engine falls to the next rule and records "no eligible preferred supplier".
- **Why:** The engine should never emit a PO without a supplier, and never a Blocked one.
- **Amended (design):** This is now generic (see D51). Any rule whose supplier strategy cannot be fulfilled lets the walk continue to the next rule, and the trace says why. The evaluator has no rule-specific code.

---

## H. Suppliers: preferred list, ranking, suggestions

### D31. Preferred list membership
- **Noticed:** 6.1 has two routes in: a PO in the last 548 days, or a contract that started on or before the date.
- **Decided:** Exactly as written, plus Active status only. POs after the "as of" date are ignored, so lists are recomputed as of each requirement date, as the opening of section 6 says.
- **Why:** Straight reading, and it matches the three example lists (the Inactive supplier S031 is excluded).

### D32. Ranking method
- **Noticed:** The policy lists four things to weigh (how often, how recently, contract held, on-time and quality) but leaves the weights to me.
- **Decided:** A weighted score, each part scaled 0 to 1:

| Factor | Weight | Definition |
|--------|--------|------------|
| Frequency | 0.30 | POs in the 548 days ÷ the most POs any candidate has for this item |
| Recency | 0.25 | `exp(−days since last PO ÷ 180)`; 0 if no PO |
| Contract | 0.15 | 1 if the supplier has had a contract covering the item, else 0 |
| On-time | 0.15 | supplier on-time % ÷ 100 |
| Quality | 0.15 | quality rating ÷ 5 |

  Ties: higher recency, then quality, then lower supplier ID. The weights are stored **in the policy** so a future version can change them.
- **Why each weight:**
  - **Frequency (highest):** repeated buying is the best proof that a supplier works for this item. Normalising by the best candidate keeps one-off items fair.
  - **Recency:** a supplier we bought from last month is more likely still able to supply than one from 15 months ago. An exponential decay is smooth, with no cliff at 90 or 365 days.
  - **Contract:** a negotiated rate is valuable but not decisive on its own (an expired contract still counts), so a moderate weight.
  - **On-time and quality:** these are supplier-wide, not item-specific, so they are tie-breakers rather than drivers.
- **Check:** I ran this on the three lists in the Worked Examples as at 1 Nov 2026. It reproduces all three orders: gloves (S029, then S030), cylinders (S023, S022, S024), MIG wire (S009, then S010). Scores for the cylinders were 0.74, 0.57, 0.43, so the order is not a near tie.
- **Amended (design):** The weights, the 180-day decay (`ranking_recency_decay_days`), the tie-break order (`ranking_tie_break`) and the rating scales (`on_time_pct_scale` 100, `quality_rating_scale` 5) are all policy parameters. The prototype re-check gives gloves 0.869/0.619, cylinders 0.737/0.569/0.434 and MIG wire 0.766/0.605.

### D33. On-time and quality: which numbers
- **Noticed:** The PO history has a per-PO `delivered_on_time`, and the supplier master has an overall on-time %.
- **Decided:** Use the supplier master's on-time % and quality rating. The per-PO flag is kept for the buyer screen only.
- **Why:** The worked example tables use the master's figures (81%, 72% and so on), and the per-item sample per supplier is often 1 or 2 POs, too small to trust.

### D34. Contract-only suppliers (no PO yet)
- **Noticed:** A supplier can qualify through 6.1(b) alone.
- **Decided:** They are on the list with frequency 0 and recency 0, but still earn the contract, on-time and quality points. Reference price is the latest contract rate (6.3).
- **Why:** The policy puts them on the list, so the ranking must be able to score them.

### D35. Suggestions when the list is too short (6.4)
- **Noticed:** Some items have fewer than 3 or 5 preferred suppliers, and one supplier lists two categories (`Electrical Spares;Capital Equipment`).
- **Decided:** After the preferred list, add other **Active** suppliers whose category list includes the item's category (split on `;`), ordered by `0.5 × on-time + 0.5 × quality` (each scaled 0 to 1), best first. If still short, return fewer rather than stretch to the wrong category. New items get none.
- **Why:** Follows 6.4. Unrelated suppliers would waste quote effort.
- **Amended (design):** The 0.5/0.5 weights are the policy parameter `topup_weights`, and the counts 3 and 5 are `rfq_suggestion_count`, `rfp_suggestion_count` and `capex_suggestion_count`, referenced from rule outcomes as `$param`.

### D36. Blocked and Inactive suppliers: a hard filter, everywhere
- **Noticed:** 3 Blocked (S004, S008, S011) and 2 Inactive (S031, S034). 58 historical POs are from non-Active suppliers.
- **Decided:** Status is checked in one place (the supplier-eligibility function) used by contracts, the preferred list, PO selection and suggestions. A test asserts no output ever contains one of them.
- **Why:** The brief penalises it, and a single check point is harder to bypass by accident.
- **Amended (design):** The allowed statuses are the policy parameter `eligible_supplier_statuses` (["Active"]), checked by `backend/engine/eligibility.py`. A second guard in the output builder raises an internal error if an ineligible supplier ever reaches a row. It is a bug check and never silently filters.

---

## I. PO consolidation and IDs

### D37. Consolidation
- **Noticed:** 7.1 requires the same supplier, plant and route, within 24 hours of the *first requirement on that PO*.
- **Decided:** Requirements that end in a PO are taken in order of creation time. Each joins the earliest open PO that matches supplier, plant and route and whose first requirement was created ≤ 24h earlier; else it opens a new PO. Sourcing requests are never combined. CONTRACT_PO, SPOT_PO and EMERGENCY_PO are different routes and never merge, even for the same supplier.
- **Why:** Exact reading of 7.1 and 7.2. In Worked Example 14, the two bolt requirements (created 2 Nov 14:05 and 3 Nov 10:30, under 24h apart) share one PO.

### D38. Same supplier, different contracts
- **Noticed:** Not in the data (each supplier has one contract), but it could happen after an amendment.
- **Decided:** Follow the policy literally (supplier, plant, route). The PO line records which contract each requirement used.
- **Why:** Not to invent an extra condition the policy does not state.

### D39. IDs
- **Noticed:** The output asks for `group_id` and `po_id` but gives no format. Example POs look like `PO-0011`.
- **Decided:** `group_id = REQ-0001…`, `po_id = PO-0001…`, both numbered in order of creation time of the first line, so the output is the same every run. Sourcing requests get `SRC-0001…` in the reason or id field, but `po_id` stays blank for them.
- **Why:** Stable, readable and deterministic IDs help a reviewer compare two runs.
- **Amended (design review):** The output has no SRC number. `po_id` is blank for sourcing requests, and the reason does not carry one. An `SRC-0001…` number is created only as an order number when a buyer approves a sourcing request (a per-run sequence). Order numbers are unique per run and shown as `R{run}/PO-0001`, because two runs both number from PO-0001.

---

## J. Chat, buyer actions and policy changes

### D40. The chat never invents
- **Decided:** If the item is unclear, the assistant shows up to three candidates and asks. If none fit, it offers to raise a new item with an estimated price. Required slots: item, quantity, plant, need-by, urgency. Plant words map to codes (Chakan to CHK1, Bhosari or Pune to PUN1); an unknown plant triggers a question. Relative dates are calculated in code in IST. Nothing is created until the user confirms.
- **Why:** The brief scores follow-up questions and not inventing items. Code, not the LLM, does date and plant arithmetic, so it is predictable.

### D41. What AI is and is not allowed to do
- **Decided:** AI extracts text into JSON (chat fields, policy changes, contract fields). The engine alone decides routes, values, suppliers and prices. Every AI output is schema-validated, and policy changes need human approval.
- **Why:** Money decisions must be repeatable and testable. An LLM may be wrong or vary between runs.

### D42. Policy updates always need approval, a date and a preview
- **Noticed:** An amendment may omit its effective date, may be ambiguous, or may use a rule type the engine lacks.
- **Decided:** The draft is never activated automatically. If the effective date is missing, the app asks. The screen shows a plain-language diff and a dry-run count of changed decisions. Unknown facts or routes are flagged, not ignored. A new version never edits an old one.
- **Why:** A wrong reading could change thousands of rupees of decisions silently. A diff and dry run make mistakes visible before they matter.

### D43. Overrides and approvals
- **Decided:** Approve creates the PO (or RFQ/RFP) with a record of who and when. Override needs a written comment and a new target decision, is stored beside the untouched original (policy 8.1), and appears in the audit log. Overriding to a supplier that is Blocked or Inactive is refused.
- **Why:** Keeps the system's decision and the human's change separately visible, and protects rule 5.7 even from overrides.
- **Amended (design review):** Statuses are PROPOSED, APPROVED and OVERRIDDEN. An override sets the previous decision's status to OVERRIDDEN, the only field that changes on it, and adds a new PROPOSED decision. Approve acts on the latest decision that is not OVERRIDDEN and is refused (409) only when that decision is already APPROVED, so an override can itself be approved. An approved override to a PO gets order number `PO-OVR-{decision id}`. Overrides carry no contract, so they never draw on a ceiling.

### D44. Do approved POs feed history?
- **Noticed:** After a buyer approves a PO, that is a real purchase, but the batch run must stay repeatable.
- **Decided:** A batch run uses the loaded PO history only. Approved POs are saved with their date and become part of the history for **later** runs, not for the run that created them.
- **Why:** Run 1 and Run 2 on the same batch must differ only because of the policy, not because earlier output changed the history.
- **Amended (design):** Batch runs never read approved orders, either for history or for ceilings. Approved orders are kept in `orders` and `contract_consumption` and shown in the workspace and on the contracts screen, but they enter the engine only through a re-import of PO history and the register. Otherwise approving Run 1's decisions before Run 2 would change Run 2 for reasons other than the policy.

### D45. Output file details
- **Decided:** One row per PR line, in input order. Clubbed lines repeat the requirement's value, route, supplier and `group_id`. `suggested_supplier_ids` are separated by `;`. `NOT_PROCESSED` rows have route `NOT_PROCESSED`, a reason, and blanks elsewhere. `reason` states the clause, policy version, and contract or PO used, for example `v5.0 §5.2 contract RC-2026-013 (rate 7.06, ceiling left ₹3,12,000)`.
- **Why:** Matches the required columns and the record-keeping rule (8.1).

---

## K. Policy as data: grammar, engine and lifecycle (added with the design)

These follow the brief's strict policy-as-data rules, which override APPROACH.md where they differ.

### D46. Condition grammar
- **Noticed:** APPROACH listed the ops eq, ne, lt, lte, gt, gte, in. The brief requires not_in and nesting.
- **Decided:** A condition is `{fact, op, value}` or `{all: [...]}` / `{any: [...]}`, nested to any depth. The ops are eq, ne, lt, lte, gt, gte, in and not_in. A value is a literal or `"$name"`, which points at `parameters` (`$$` escapes a literal dollar). Rules run in list order, first match wins, with no sorting.
- **Why:** The brief's grammar. `not_in` is what makes plant-only rules possible (D50).

### D47. New items are a rule, listed first
- **Decided:** Policy 1.2 is the rule `is_new_item eq true → SOURCING_REQUEST / NEW_ITEM_SOURCING / strategy none`, and it is first in the list. "Never clubbed" is the parameter `club_new_items: false`. "Valued at the estimate" is `new_item_valuation: "requester_estimate"`.
- **Why:** Nothing about new items is hard-coded, and "always goes to sourcing" holds whatever follows in the list.

### D48. Capex
- **Decided:** Rule 5.1 is `item_type eq Capex → CAPEX_SOURCING`, with `suggest` and count `$capex_suggestion_count`, and the outcome note "Needs capex approval." It sits after 1.2 and before 5.2.

### D49. Rule 5.7 is a filter, not a rule
- **Decided:** 5.7 is the parameter `eligible_supplier_statuses`, applied wherever a supplier is chosen or suggested and wherever a contract's applicability is checked (4.1).
- **Why:** As a first-match rule, any rule above it could still name a Blocked supplier. A filter applies to every outcome.

### D50. Plant-only parameters
- **Decided:** A plant-specific limit is expressed by inserting a rule with a `plant` condition and its own parameter (for example `chk1_emergency_max_value`) before the generic rule, and adding `plant not_in [CHK1]` to the generic rule. The fallback policy reader and the LLM prompt both produce this pair.
- **Why:** Without the exclusion, a lower CHK1 limit would be bypassed by the generic rule. With it, raising and lowering both work through JSON alone.

### D51. A rule whose supplier strategy cannot be fulfilled
- **Decided:** If a rule matches but its strategy finds no supplier (`contract` with no usable contract, `preferred_first` with an empty eligible list), the engine records this in the trace and moves on to the next rule.
- **Why:** This replaces D30's special case with a generic mechanism, and it never emits a PO without a supplier.

### D52. The trace evaluates every condition
- **Decided:** `all`/`any` do not short-circuit. Every leaf of every rule checked up to the fired rule is recorded with its fact value, the resolved parameter value and pass/fail.
- **Why:** The buyer can see why 5.4 did not fire, not only why 5.5 did. Facts are memoised, so the cost is negligible.

### D53. Missing fact values
- **Decided:** If a fact is null (no last PO, an empty preferred list), the ordering ops are false, `eq null` is true, `in` is false and `not_in` is true.
- **Why:** A missing number must never satisfy a limit by accident.

### D54. Fact registry and windows
- **Decided:** `backend/engine/facts.py` maps each name to one decorated function with a declared type and the parameters it needs. Windows are read only from parameters: `price_history_days` (3.1b), `bought_history_days` (5.3/5.4), `preferred_history_days` (6.1). The validator, the LLM prompt, the diff text and the UI fact list all read the registry.
- **Why:** Adding a fact is one function, as the brief requires.

### D55. What the validator rejects and what it only warns about
- **Decided:** It rejects unknown facts, ops and strategies, undefined `$param`s, schema errors, op/type mismatches, duplicate rule ids, missing or badly typed required parameters, and bad counts. It warns about decisions outside PO/SOURCING_REQUEST, new route names, weights that do not sum to 1, unreachable duplicate rules, unused parameters and a missing effective date. A draft with errors can be saved and edited but never approved.
- **Why:** Errors would make the engine guess. Warnings are legitimate but worth a second look.

### D56. Version lifecycle
- **Decided:** The statuses are DRAFT, ACTIVE, SUPERSEDED, plus DISCARDED for drafts thrown away (kept for audit). On approval, the previous ACTIVE becomes SUPERSEDED but still applies to requirement dates before the new effective date. The effective date must be on or after the current ACTIVE's. Approved documents are immutable, enforced by a DB-layer listener.
- **Also:** If an amendment's effective date is later than the batch's PR dates, D1 keeps v5.0 for those lines. The policy and batch screens state this count, and the batch screen offers an explicit pin for Run 2.
- **Why:** Keeps "activate from its effective date" literal while making the blind-test case visible.

### D57. What counts as a "changed line" in the dry run
- **Decided:** A line counts as changed when its decision, route, supplier, unit price, requirement value or suggestions differ, or when the set of lines in its requirement differs. Renumbered group IDs alone do not count. The preview reports N of M under date-based selection and also the count if the draft were pinned for every line.

### D58. Change summaries are generated from the diff, not by the LLM
- **Decided:** The plain-language bullets come from deterministic templates over the structural diff.
- **Why:** The summary the approver reads must describe exactly the JSON that will be activated. An LLM summary could misdescribe it.

### D59. Policy reading without the LLM
- **Decided:** When OpenRouter is unavailable, a rule-based reader handles the common amendment sentences: limit changes in ₹, lakh or crore; day and hour windows; suggestion counts; plant-only limits; category value rules; ranking weights; effective dates. It lists every sentence it could not express and never guesses. The user can edit the draft JSON directly.

### D60. PO numbers in the worked examples are offset by one
- **Noticed:** Following the policy, the examples' PO numbers come out one higher (PO-0002 where the example says PO-0001, and so on up to PO-0073 vs PO-0072). The extra PO is the PUN1 servo-drive requirement PR-26-00174 + 00175 (2 Nov 08:10, ₹1,31,675.78, spot PO to S020), which the examples apparently do not count. Nothing in the policy explains this.
- **Decided:** Follow the policy. The golden tests check PO numbering relative to Example 5, which verifies every consolidation in between, rather than absolute numbers. This is an open item.

### D61. Chat details
- **Decided:**
  - "by Friday" or "this Friday" means the next Friday on or after today. "Next Friday" means the Friday of next week (Monday-start). The card always shows the weekday so the user can correct it.
  - Chat PRs are numbered `CH-26-00001`.
  - The decision preview runs the engine over the latest uploaded batch plus all chat PRs, so clubbing and ceilings are realistic, and splitting across chat requests is still caught.

### D62. Approving a consolidated PO
- **Decided:** Approving any requirement on a PO approves the whole PO, and the dialog says how many requirements it covers.
- **Why:** A PO is one document to one supplier. Partial approval would make PO numbers meaningless.
- **Amended (design review):** The group covers only requirements whose current decision is still the engine decision carrying that PO number. A requirement that was overridden has left the engine's PO and is approved on its own; the dialog says how many were excluded.

### D63. Export shows the engine's decisions
- **Decided:** The run export is always the engine output of that run. Buyer overrides are shown in the workspace and audit log, not in the scored CSV.

### D64. PDF-only contracts in the seed
- **Decided:** RC-2026-031 and RC-2026-033 are seeded from `backend/seed/pdf_contracts.json` (values extracted by the app's own regex extractor and checked by hand), with consumed value 0. A test asserts the extractor still produces exactly these values. Buyers can add more on the contracts screen.
- **Why:** A fresh `docker compose up` or a hosted rerun gives the same decisions without a manual step.

### D65. The valuation ladder is data
- **Decided:** `valuation_ladder: ["contract", "last_po", "standard_price"]` names steps from a small price-source registry, so an amendment can reorder or drop steps.

### D66. .gitignore and the data folders
- **Noticed:** `.gitignore` lists `contracts`, `master_data` and `pr_batches`, although the kit files in them are tracked. A bare `contracts` pattern also matches any folder of that name anywhere.
- **Decided:** The kit files stay tracked and the Docker build copies them. No code folder is named `contracts`; the router is `contracts_api.py` and the page is `ContractsPage.jsx`. Recommend anchoring the patterns (`/contracts/pdf-uploads/`, for example) if uploads ever get stored on disk.

### D67. LLM client
- **Decided:** OpenRouter's OpenAI-compatible endpoint is called through `httpx`, with model `OPENROUTER_MODEL`, JSON mode, temperature 0, a 30 s timeout and one retry. The key comes only from the environment (gitignored `.env`) and is never logged. Any failure falls back to the rule-based path, and tests set `LLM_DISABLED=1`.
- **Amended (design review):** Run outside Docker, nothing would put the `.env` key into the environment, so the fallback would be used silently. `backend/api/main.py` therefore calls `load_dotenv(override=False)` once (python-dotenv), so real environment variables still win. The engine, services and tests never call it. The startup log, `/api/health` and a UI badge say whether the LLM is enabled and which model is used, never the key.

### D68. Rounding
- **Decided:** The requirement value is quantity × unit price, rounded to paise (half-up) before any limit comparison. Rates are kept at 4 decimal places.

### D69. Engine text never cites clause numbers
- **Noticed:** The brief's grep for 14, 7, 24 and so on would also hit comments such as "see 5.7" or "D7", and a rule-id check based on dotted numbers would flag `Decimal("0.01")`.
- **Decided:** Comments, docstrings and strings in `backend/engine/**/*.py` name policy sections by topic ("supplier eligibility filter"), never by clause number or decision id. Clause numbers come from the JSON at run time. The literal test checks number tokens and comment/string text. The rule-id test checks for strings equal to the policy file's rule ids or clauses, and for any comparison against `.id`, `.clause`, `["id"]` or `["clause"]`.
- **Why:** The grep then returns zero hits, as the brief asks, and the tests catch real special cases without false alarms.

### D70. `$param` values are checked like literals
- **Noticed:** A draft can hold `"chk1_emergency_max_value": "2.5 lakh"`. The parameter exists, so only the evaluator would notice, with a crash.
- **Decided:** For each condition that references `$name`, the validator resolves the parameter and checks it against the fact's type exactly as it checks a literal (a number that is not a bool, an ISO date, a bool, a string; a list for in/not_in). At load, the value is coerced per condition, the same as a literal.
- **Why:** The brief says never ignore silently and give a clear message. A crash during a batch is neither.

### D71. The parameter contract
- **Decided:** The validator holds a rule for every parameter the pipeline reads directly (clubbing keys and windows, history windows, urgency values, ladder, eligible statuses, ranking and top-up weights, tie-break, scales, export count, consolidation keys, decisions and hours). The limits and suggestion counts are not required: they are checked wherever a rule references them, so a policy without an emergency rule need not keep its limit. Any other parameter is allowed, and an unreferenced one gets a warning. A tie-break list without `supplier_id` gets it appended last, with a warning, so the order is always total.
- **Why:** The coder and the LLM prompt get one exact contract, and plant-only parameters stay possible.

### D72. Rows where no rule fired
- **Decided:** Route `NOT_PROCESSED` with the reason "No rule in policy vX matched". These rows keep the resolved item, group id, value and policy version, because the lines were clubbed and valued. Decision, PO, supplier, price and suggestions are blank.
- **Why:** A buyer can see what the requirement was and why it stopped. Rows rejected at input still have only the reason.

### D73. Consolidation stays within one policy version
- **Decided:** A requirement joins an open PO only if both use the same policy version.
- **Why:** The window and keys come from the PO's first requirement. Mixing versions would apply one version's window to another version's decision.

### D74. Canonical urgency
- **Decided:** Urgency is matched case-insensitively, then replaced by the policy's own spelling from `urgency_values` before facts are computed.
- **Why:** `is_emergency` is then an exact membership test, and the trace shows one spelling.

### D75. Proof tests assert exact change sets
- **Decided:** Each proof test asserts the exact set of changed lines (a 14, b 4, c none on the sample plus both synthetic lines, d 1 line, the d control 3 lines, d raise 1 synthetic line, e 11, f 2, h 38). Two independent prototypes reproduced these sets. If an implementation detail legitimately shifts a set, the test is updated and the reason is recorded here.
- **Why:** A lower bound would let a regression that changes extra lines pass.

---

## Things I noticed but chose not to act on

- **Requester estimates far from the real price** on matched items: ignored (D20). A future improvement is a flag when the gap is large.
- **Item usage patterns** (the same requester raising many small PRs): the clubbing rules already handle the policy's goal, so I did not add a separate "suspicious splitting" detector.
- **Supplier master is a point-in-time snapshot:** the status "as of requirement date" is unknown, so I use the current status (D28).
