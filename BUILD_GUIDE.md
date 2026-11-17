# BUILD_GUIDE.md: The Cantill Task, Explained Simply

A plain-English walkthrough of what you are building, how the pieces fit, and what order to build them in. Read this first, then `APPROACH.md` (the design) and `DECISIONS.md` (the judgment calls).

---

## 1. What are you building? (the 30-second version)

Imagine a factory called **Corvo**. Workers ask for things to be bought: "we need 200 gloves". Someone in the **Procurement** team must decide what to do:

- **Buy right now** because we already have a special price deal (a *rate contract*) with a supplier, or
- **Buy right now** from a supplier we already trust, or
- **Ask suppliers for quotes first** (an RFQ or RFP), because the amount is big or we have never bought this before.

Today people do this by hand, slowly and inconsistently. Your app does it **automatically by following a written policy**. Workers talk to it in a **chat**, and the policy can be **swapped for a new version without changing any code**.

> **Think of it like a smart vending machine for purchasing.** The worker types what they need. The machine looks at the rulebook and says "buy it from Supplier X at ₹Y" or "go get quotes". When the rulebook changes, you load the new rulebook; you do not rebuild the machine.

## 2. Words you need to know

| Word | Meaning |
|------|---------|
| **PR** (purchase requisition) | A request: "please buy this". One PR can have several lines. |
| **PO** (purchase order) | The actual order sent to a supplier. |
| **RFQ / RFP** | Asking suppliers for quotes (RFQ: smaller, RFP: bigger and more formal). |
| **Rate contract** | A pre-agreed price with a supplier for some items, valid for certain dates, with a **ceiling** (maximum total spend). |
| **Ceiling** | Like a prepaid card balance. Each order "uses up" some of it. When it is empty, the contract cannot be used. |
| **Requirement** | One or more PR lines that the policy treats as a single need (see clubbing). |
| **Clubbing** | Joining similar PR lines into one requirement so people cannot split a big purchase into small ones to dodge the quote limit. |
| **Preferred supplier list** | For each item, a ranked list of suppliers we trust, built from past orders and contracts. |
| **Consolidation** | Combining several orders to the same supplier into one PO to reduce paperwork. |
| **Capex** | Capital equipment, like cranes and forklifts. Always goes to sourcing. |
| **Blocked / Inactive supplier** | Must never get a PO or be suggested. Using one is penalised in scoring. |

## 3. The decision, step by step

Every PR line goes through the same journey:

```
PR line ──► 1. What item is it?  ──► 2. Group similar lines  ──► 3. How much is it worth?
                                                                        │
  PO or request  ◄── 5. Walk the rulebook, first match wins ◄── 4. Is there a usable contract?
        │
        ▼
  6. Combine POs that go to the same supplier
```

**Step 1: Identify the item.** If the line has an item code, use it. If it only has text like "brg 6308 ZZ", match it to the item master (`Ball bearing 6308-ZZ`). If nothing matches, it is a **new item**, which always goes to sourcing.

**Step 2: Club the lines.** Lines for the **same item and same plant**, created within **14 days** of the first line, with need-by dates within **7 days** of the first line's, are one requirement. This is how the policy stops splitting.

**Step 3: Value the requirement.** Total quantity × price, where the price is, in order: the contract rate, else the last PO price in the past year, else the item master's standard price.

**Step 4: Check contracts.** A contract works if it covers the item, the date is inside its validity, the supplier is Active, and there is enough ceiling left. If two contracts qualify, use the cheaper one.

**Step 5: Apply the rules in order. The first one that fits wins.**

| Order | If... | Then |
|-------|-------|------|
| 5.1 | Item is Capex | Sourcing request, suggest 5 suppliers |
| 5.2 | A contract can be used | PO to the contract supplier at the contract rate (any value) |
| 5.3 | Emergency, value up to ₹5 lakh, and bought from an Active supplier in the last year | PO to the top preferred supplier |
| 5.4 | Value under ₹2 lakh, and bought from an Active supplier in the last year | PO to the top preferred supplier |
| 5.5 | Value under ₹10 lakh | RFQ, suggest 3 suppliers |
| 5.6 | ₹10 lakh or more | RFP, suggest 5 suppliers |

(Plus: a new item is always `NEW_ITEM_SOURCING`, and Blocked or Inactive suppliers are never used.)

**Step 6: Consolidate.** POs with the same supplier, plant and route, created within 24 hours of the first one, become a single PO with several lines.

### A worked example, in plain words

Three separate PRs ask for hydraulic oil at Chakan: 270 L on 2 Nov, 190 L on 3 Nov, 300 L on 5 Nov. Each alone is under ₹50,000, which would look tiny. But they are the same item and plant, within 14 days, with need-by dates close together. So they club into **one requirement of 760 L**, worth about ₹1.26 lakh. No contract applies. It is not an emergency. ₹1.26 lakh is under ₹2 lakh and the oil was bought in the past year, so rule 5.4 fires: a **SPOT_PO** to the top preferred supplier.

## 4. The big idea: policy as data

Normal software: the rules are in the code (`if value < 200000: ...`). Changing a rule means a developer edits code and redeploys.

**Your app:** the rules are a **document stored in the database**, like a recipe card. The engine just *reads the card*. A new policy version is a new card.

```
   Policy v5.0 (card)         Policy v6.0 (card)
   ┌──────────────────┐       ┌──────────────────┐
   │ spot limit 2 L   │       │ spot limit 3 L   │
   │ rule 5.1 ...     │       │ rule 5.1 ...     │
   │ rule 5.2 ...     │       │ NEW rule: CHK1   │
   └────────┬─────────┘       └────────┬─────────┘
            └───────────┬──────────────┘
                        ▼
                  The same engine
```

The upload flow for a new policy:

1. Procurement uploads a document (or types the change in chat).
2. AI reads it and writes a **draft** new card.
3. The app shows a **plain-language list of what changes** ("spot limit goes from ₹2 lakh to ₹3 lakh") and how many past decisions would change.
4. A human clicks **Approve**. The version is dated and activated from its effective date.
5. The old version is kept forever, so nothing is lost.

## 5. Where AI is used (and where it is not)

| AI **does** | AI does **not** |
|-------------|-----------------|
| Turn chat text into fields (item, quantity, plant, date) | Decide PO vs sourcing |
| Turn a policy document into a draft rule card | Pick a supplier or a price |
| Read contract PDFs into fields (with a human check) | Activate a policy without approval |

**Why:** money decisions must be the same every time and testable. The engine is plain code. AI is only a *translator* at the edges.

## 6. The screens you will build

| Screen | Purpose | Its one obvious action |
|--------|---------|------------------------|
| **Chat** | A worker types a need. The assistant matches the item, asks what is missing, shows a summary. | **Confirm** |
| **Batch upload** | Upload a PR CSV and see decisions. | **Process** |
| **Buyer workspace** | List of requirements with decision, supplier, value and *why*. | **Approve** (creates the PO or RFQ) |
| **Policy** | Versions, upload, plain-language diff, activation. | **Approve and activate** |
| **Contracts** | Register plus a "add from PDF" option. | **Save contract** |
| **Preferred suppliers** | Ranked list per item with the reasons, export CSV. | **Export** |

## 7. Your build order (do these in this sequence)

1. **Load the data** (items, suppliers, PO history, contracts) into the database.
2. **Item matching.** Test it on the 39 no-code lines.
3. **Clubbing.** Check it against Worked Example 5 (the hydraulic oil one) and 14 (the hex bolts).
4. **Valuation and contracts, including ceilings.** Check Examples 1 to 4.
5. **Rules from a JSON policy.** Check Examples 7 to 13.
6. **Preferred supplier ranking.** Check the three example lists.
7. **PO consolidation.** Check Example 14.
8. **Batch API and CSV export** in the exact output format.
9. **Policy versions, diff and approval.**
10. **Chat intake.**
11. **Buyer workspace and audit log.**
12. **README, docker compose, deploy.**

> **Why engine first, UI last?** 40% of the score is the automated check on your decision CSVs, and the blind test needs the engine and policy update to work flawlessly. The screens can be simple as long as each has one obvious next action.

## 8. Test against the worked examples

The kit's `Worked_Examples.pdf` is your free test suite. Turn each example into an automated test. Verified by hand while preparing these documents:

| Check | Result |
|-------|--------|
| Bearing contract `RC-2026-002`: ceiling ₹12,00,000, consumed ₹11,62,000 | About ₹38,000 left, matching Example 3 |
| Hex bolt requirement from lines 34 and 32: 4,610 × ₹7.06 | ₹32,547, matching Example 4 |
| Hex bolt requirement from lines 31 and 35: 3,290 × ₹7.06 | ₹23,227, matching Example 14 |
| Those two requirements are created under 24 hours apart | They share one PO, matching Example 14 |
| My ranking formula on the three supplier lists | Reproduces all three orders |

## 9. Traps in the data (things the policy does not tell you)

These are the "deliberate gaps". Each one is decided in `DECISIONS.md`.

| Trap | What I found |
|------|--------------|
| Unknown plant | One line uses `PUN2`, which does not exist |
| Zero quantity | One line has quantity 0 |
| Blocked supplier with a contract | `RC-2026-005` belongs to Blocked supplier S004 |
| Expired contract | `RC-2025-020` ended 30 Sep 2026 |
| Contracts only in PDFs | `RC-2026-031` and `RC-2026-033` are not in the register |
| Future-dated contract | `RC-2026-033` starts 20 Nov 2026 |
| "Urgent" in text, but urgency says Normal | 4 lines |
| Text that is not part of the item name | "as per sample", "(repeat)", "for maintenance" |
| Lines with no price estimate | 60 lines |
| Past POs from Blocked or Inactive suppliers | 58 historical POs |
| Item with two categories on a supplier | One supplier lists `Electrical Spares;Capital Equipment` |

## 10. The blind test (Thursday 10:00 to 12:00)

You get a new PR batch and a policy amendment. You cannot change any code. Practice this until it is routine:

1. Process the batch under policy v5.0, export the CSV.
2. Upload the amendment. Check the plain-language diff, confirm the effective date, approve.
3. Reprocess the same batch, export the second CSV.
4. Export the preferred supplier lists for the date they give you.
5. Put all three CSVs in a `submission/` folder in the repo and push before 12:00.

**Tips:** write your own fake amendments beforehand (change a limit, add a plant-only rule, add a category rule) and make sure the app handles each. Keep the hosted app awake. Do not wait until 11:55 to push.

## 11. Pre-submission checklist

- [ ] `docker compose up` works from a clean clone
- [ ] Hosted link works and stays up
- [ ] Repo is public
- [ ] `APPROACH.md` and `DECISIONS.md` are in the repo root, and the AI-tools section is honest
- [ ] All 14 worked examples pass as tests
- [ ] No Blocked or Inactive supplier ever appears (there is a test)
- [ ] No hard-coded PR numbers, items or suppliers anywhere
- [ ] `POST /api/process-batch` returns decisions
- [ ] You can explain every file. In Round 2 you will be asked to change something live.
- [ ] Last commit before Thu 19 Nov, 10:00 AM IST, then submit the form
