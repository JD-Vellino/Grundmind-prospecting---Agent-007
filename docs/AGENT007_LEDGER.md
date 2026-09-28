# Agent 007 Ledger

Last updated: 2026-09-28

What is done, what was proven, the decisions taken and the backlog for
Agent 007, GrundMind's prospecting agent. Update it when work closes or a
decision is made, ideally in the same commit. This repo is public: no
prospect names, contacts or run data here (those stay in local runtime files).

## Status vocabulary

- **CLOSED**: implemented and proven in a real run.
- **CLOSED (UNPROVEN)**: implemented and unit-tested, not yet proven in a
  real run.
- **BACKLOG**: agreed, not started.
- **PROPOSED**: idea, not agreed yet.
- **PARKED**: deliberately stopped.

---

## Decisions

- **2026-09-25: list first, not news first.** Searching AI news for
  companies kept returning the same well-known names and AI vendors. The
  news mode was judged exhausted, not the market; the "check a company list"
  mode replaced it as the main source.
- **2026-09-28: run locally.** Kimi (Moonshot) cost about $45 in total, most
  of it on search-result text billed as input. The everyday flow now runs on
  a local Qwen 27B model (Ollama) with Tavily web search. Slower runs are
  accepted.
- **2026-09-28: list + sending is the product.** Deep search is parked;
  deep dives on interested prospects are done by hand.
- **2026-09-28: judge results by their sources.** Agreement between two
  models is not accuracy; runs are checked against the cited pages.

---

## Discovery

### Company-list mode: CLOSED (2026-09-25)

- Official exchange lists in `backend/company_lists/`: Switzerland (SIX),
  Germany (Frankfurt), Sweden, Finland, Denmark (Nasdaq Nordic), Croatia
  (Zagreb), Serbia (Belgrade).
- Pool companies are skipped; checked companies are remembered so the next
  run continues down the list.
- A company whose search failed is retried; it is never recorded as
  "no signal".
- Proof: first Swiss run, 25 checked: 11 qualified, vs 2–3 for the news
  mode the same day.

### News-search fixes: CLOSED (2026-09-25)

- Known pool companies removed before the per-search cap (they had pushed
  new ones out).
- Buyer-side AI signal definitions; exclusions are hard rules.
- At most 25 companies per search; a single failed search no longer fails
  the run. Cause of every failed 100-company run: truncated model output.

### Local list check: CLOSED (2026-09-28)

- `CHECK_BACKEND=local`: two Tavily searches per company (English and a
  local-language AI term) + Qwen 27B. The model may only cite a URL it was
  shown; anything else counts as no signal.
- Local "no signal" is rechecked after 90 days (Kimi: 180).
- Proof: Serbian list, 25 companies in about 12 min including
  qualification, no Kimi calls.

### Fact-check of the first local run: CLOSED (2026-09-28)

2 kept companies and 5 "no signal" companies checked by hand against real
sources (small sample, not a rate):

- Kept 1: real evidence, but a two-year-old one-line plan rated HIGH.
- Kept 2: real AI project, but run by the airport's concession operator,
  not the listed company (wrong entity).
- "No signal": 1 clear miss (a large company with an AI/ML lab since 2020);
  the other 4 checked were right.
- Misses came from the local-language results being cut (fixed below) and
  from ambiguous short list names (backlog).

### Local-language sources get fair room: CLOSED (UNPROVEN) (2026-09-28)

- The English search used to fill up to 8 of the 10 source slots. Results
  now alternate between the two searches.
- Retest: the missed company above is now found, and a stronger, verified
  signal was found for another one. A full run is still to come.

### Signal age and stage: CLOSED (UNPROVEN) (2026-09-28)

- The check records `signal_date` and `signal_stage` (LIVE / PILOT / PLAN).
- Code rule: a PLAN, or evidence older than 12 months, is capped at LOW
  confidence. An unknown date is not penalised.

---

## Qualification

### Local qualification: CLOSED (2026-09-28)

- `QUALIFY_BACKEND=local`, batches of 10.
- Test on 60 pool companies: same keep/reject as Kimi on 54. A 9B model
  was too lenient (kept vendors and consultancies) and was rejected.

---

## Outreach

### Local email drafts: CLOSED (2026-09-28)

- `OUTREACH_BACKEND=local`, about 30 s per draft.

### Email wording rules: CLOSED (UNPROVEN) (2026-09-28)

- Short company name in emails (no legal form or town).
- A plan, or an old or undated signal, is not presented as current: it is
  mentioned with its year or left out.

---

## Platform

### Model call log: CLOSED (2026-09-28)

- `backend/llm.py`: every Kimi and local call is logged to
  `llm_usage.jsonl` (step, tokens, web searches, seconds).
- `<STEP>_BACKEND=kimi|local` switches in `.env`.

### Repo hygiene: CLOSED (2026-09-25)

- Public repo; history scrubbed of personal names and researched-company
  configs; runtime data gitignored; Python backend in `backend/`.
- Service bound to 127.0.0.1:8707.

---

## Deep search: PARKED (2026-09-28)

- Fixed 2026-09-25: claims confirmed in an independent source count as
  evidence (they used to be capped as "unverified").
- Implemented, never proven: source-type tags (company, press, job
  posting, academic, vendor content); academic- and vendor-only claims
  weigh less and must be attributed.
- Open if revived: the search worker retries an identical request when the
  model skips web search; about 23 stacked anti-hallucination patches in
  `account_brief.py`.
- Still runs on Kimi, as do news mode and company identity.

---

## Backlog

### P0: before the next outreach batch

- **Prove today's fixes in a real run.** Next list run: date/stage fields
  filled, local-language sources used. BACKLOG
- **Wrong-entity guard.** A concession, subsidiary or parent can be
  matched instead of the listed company. At minimum, the check should say
  who ran the AI project. BACKLOG
- **Email template fit.** A pitch about rework in existing AI workflows
  doesn't fit a company that only plans AI; use a readiness angle for PLAN
  signals. Unsourced figures should be backed or removed. PROPOSED (owner:
  product)
- **Cold-email rules** per country (e.g. Germany consent) before bulk
  sending. BACKLOG
- **Sanctions check** before contacting a company (one found company is
  majority-owned by a sanctioned group). PROPOSED

### P1: yield and quality

- **Search name.** Short or ambiguous list names (e.g. a three-letter name
  that is also a city) make searches miss. Add a search alias per list
  row. BACKLOG
- **Contact enrichment.** Hunter found an email for 1 of 5 qualified
  prospects. BACKLOG
- **Norway list** (Euronext). BACKLOG
- **Name matching.** A company was wrongly matched to a different pool
  company with a similar name; another wasn't matched across spellings.
  BACKLOG

### P2: UI and docs

- Note under the list form: "one web search per company" is now two;
  "checked in the last 6 months" is 90 days for local checks. BACKLOG
- Run history shows geography instead of the list name. BACKLOG
- Deep Search tab: hide or keep? Decision pending (product).
- README: call deep search "experimental". BACKLOG
