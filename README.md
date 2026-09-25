# Agent 007 — AI prospecting agent for B2B sales

Agent 007 finds and researches companies that are likely buyers for
[GrundMind](https://grundmind.com), an AI-adoption diagnostics service.
It looks for organisations that are **adopting AI in their own operations**
and shows signs of commercial pain (unclear ROI, adoption friction, scaling,
governance), then helps a human write and send a short, evidence-based
first email.

It is a working internal tool, built product-first: the owner defines the
sales process, acceptance criteria and QA; the code is written with AI coding
assistants and reviewed against real runs.

## What it does

| Stage | What happens |
|---|---|
| **Discovery** | Finds candidate companies — either by searching AI news, or by checking a real company list one company at a time (see below). |
| **Qualification** | An LLM classifies each candidate (operating company vs. AI vendor, consultancy, investor…), rates AI investment and pain signals, and sets a priority. Vendors and consultancies are rejected. |
| **Deep search** | For one company: several focused research workers (AI hiring, deployment, ROI/value, commercial pain, organisational fit) collect sourced evidence and produce a scored account brief. |
| **Contacts** | Looks up likely contacts and emails via Hunter.io. |
| **Outreach** | Drafts a personalised first email per prospect; a human reviews and edits before anything is sent (SMTP). |

## Design choices worth noting

- **Evidence over eloquence.** Every claim keeps its source URL. Sources are
  tagged by type (company site, press, job posting, academic, vendor content).
  A claim confirmed in an independent source counts as corroborated; academic
  or vendor-only claims score lower and must be attributed in the brief.
- **Buyer-side signals.** "AI investment" is defined as *the company spending
  on AI for its own operations* — not AI startups raising money. This one
  definition removed most vendors and investors from discovery results.
- **Human in the loop.** The agent drafts; a person decides what is sent.
- **Hard limits against model failure modes.** Per-search result caps (long
  outputs got truncated into broken JSON), one failed search never kills a run,
  a model answer without a web search is not accepted as a check.

## A lesson from real runs: flip the funnel

The first discovery mode asked the model to search AI news for matching
companies. After several fixes it hit a ceiling: runs returned 100–150
companies, but almost all were already known, and the new ones were mostly AI
vendors. News search keeps surfacing the same well-known names.

The **company-list mode** reverses it: start from an official list of listed
companies (SIX Swiss Exchange, Deutsche Börse, Nasdaq Nordic), drop those
already in the pool, and run one focused search per company: *"is this company
using AI in its own operations?"*

| Run (same day) | Companies returned | New | Qualified |
|---|---|---|---|
| News search, Europe, 100 | 106 | 6 | 3 |
| News search, Europe, 100 | 156 | 2 | 2 |
| Company list, Switzerland, 25 checked | 25 | 12 with an AI signal | **11** |

The list run also finished in under two minutes and surfaced small and
mid-caps that news search never reached.

## Stack

- **Backend:** Python, FastAPI, background jobs as subprocesses, JSON files as
  storage (local, single user).
- **LLM:** Kimi (Moonshot API) with its built-in `$web_search` tool.
- **Frontend:** React + TypeScript + Vite.
- **Integrations:** Hunter.io (contacts), SMTP (sending).

## Run it locally

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # fill in your keys

cd frontend && npm install && npm run build && cd ..
.venv/bin/uvicorn api:app --host 127.0.0.1 --port 8707
```

Then open http://127.0.0.1:8707.

The API has no authentication and can send real email: keep it bound to
`127.0.0.1`.

## Data and privacy

Runtime data (the prospect pool, contacts, research runs, logs) is
git-ignored and never committed: it contains personal contact details.
The company lists in `company_lists/` are public stock-exchange data.

Cold email is regulated differently across Europe (e.g. stricter consent rules
in Germany); check local rules before sending.

## Status

Personal project, in active use. No test suite yet; changes are validated
against saved real runs.
