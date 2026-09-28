"""
"From company list" discovery mode.

The news-search mode (discovery.py) asks the model to find
companies in AI news; it keeps resurfacing the same well-known
names and vendors. This mode flips the funnel: start from a
real list of companies, drop the ones already in the pool,
then run ONE focused search per company: "is X using AI in its
own operations?". Companies with a signal become candidates
for the normal qualification step.

Lists live in company_lists/*.csv with at least the columns
company,country. Register them in COMPANY_LISTS.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from discovery import (
    BLOCKED_DOMAINS,
    hostname,
    moonshot_chat_create,
)
from llm import (
    backend_for,
    local_chat_json,
)
from research_core import (
    WEB_SEARCH_TOOL,
    clean_json,
)


ROOT = Path(__file__).resolve().parent

LISTS_DIR = ROOT / "company_lists"

# Runtime state: which list companies were already checked,
# so the next run continues down the list instead of paying
# again for the same companies.
CHECKED_PATH = ROOT / "company_list_checked.json"

# A company with no AI signal today may have one later.
RECHECK_AFTER_DAYS = 180

LOCAL_NO_SIGNAL_RECHECK_DAYS = 90

MAX_COMPANIES_PER_RUN = 100

PARALLEL_CHECKS = 4


NASDAQ_NORDIC_SOURCE = (
    "Nasdaq Nordic main-market share list "
    "(api.nasdaq.com), downloaded 2026-09-25. Home-country "
    "companies only, share classes merged, Technology "
    "sector removed (mostly software vendors)."
)


COMPANY_LISTS = {
    "switzerland_six": {
        "label": "Switzerland · Swiss stock exchange (SIX)",
        "file": "switzerland_six.csv",
        "source": (
            "SIX Swiss Exchange equity issuers list "
            "(six-group.com), downloaded 2026-09-25. "
            "Swiss primary listings only, investment "
            "companies removed."
        ),
    },
    "sweden_stockholm": {
        "label": "Sweden · Nasdaq Stockholm",
        "file": "sweden_stockholm.csv",
        "source": NASDAQ_NORDIC_SOURCE,
    },
    "finland_helsinki": {
        "label": "Finland · Nasdaq Helsinki",
        "file": "finland_helsinki.csv",
        "source": NASDAQ_NORDIC_SOURCE,
    },
    "denmark_copenhagen": {
        "label": "Denmark · Nasdaq Copenhagen",
        "file": "denmark_copenhagen.csv",
        "source": NASDAQ_NORDIC_SOURCE,
    },
    "croatia_zagreb": {
        "label": "Croatia · Zagreb stock exchange",
        "file": "croatia_zagreb.csv",
        "source": (
            "Zagreb Stock Exchange list of issuers "
            "(zse.hr), downloaded 2026-09-25. State, city, "
            "investment funds, a company in liquidation and "
            "an IT-services firm removed; names shortened "
            "by hand."
        ),
    },
    "serbia_belgrade": {
        "label": "Serbia · Belgrade stock exchange",
        "file": "serbia_belgrade.csv",
        "source": (
            "Belgrade Stock Exchange share lists, Prime and "
            "Open Market (bgdx.rs), downloaded 2026-09-25. "
            "Issuers flagged BI or in bankruptcy removed. "
            "Mostly small companies."
        ),
    },
    "germany_frankfurt": {
        "label": "Germany · Frankfurt stock exchange",
        "file": "germany_frankfurt.csv",
        "source": (
            "Deutsche Börse 'Listed companies' report "
            "(Prime Standard, General Standard, Scale), "
            "downloaded 2026-09-25. German companies "
            "only; Software sector removed (vendors)."
        ),
    },
}


# Legal-form and group words that differ between a list's
# official name and the short names in the pool
# ("Julius Bär Gruppe AG" vs "Julius Baer").
NAME_NOISE = {
    "ag", "sa", "ltd", "limited", "inc", "plc", "se", "nv",
    "gmbh", "kgaa", "co", "company", "corp", "corporation",
    "holding", "holdings", "group", "gruppe", "groupe",
    "international", "the",
    "oyj", "abp", "ab", "publ", "asa",
}


def now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def name_tokens(value: str) -> list[str]:

    text = value.lower()

    for umlaut, plain in (
        ("ä", "ae"),
        ("ö", "oe"),
        ("ü", "ue"),
        ("æ", "ae"),
        ("ø", "o"),
    ):
        text = text.replace(umlaut, plain)

    text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )

    # "S.A." -> "sa", "N.V." -> "nv"
    text = text.replace(".", "")

    return [
        token
        for token in re.split(r"[^a-z0-9]+", text)
        if token and token not in NAME_NOISE
    ]


def same_company(
    list_tokens: list[str],
    pool_tokens: list[str],
) -> bool:
    """
    True when the pool name is the list name, or a run of
    at least two whole words inside it ("Lindt & Sprüngli"
    in "Chocoladefabriken Lindt & Sprüngli AG"). One-word
    names must match exactly: "Partners Group" would
    otherwise knock out "Molecular Partners AG". A missed
    match only costs one search; the website check after
    the search still removes it.
    """

    if not list_tokens or not pool_tokens:
        return False

    if list_tokens == pool_tokens:
        return True

    if len(pool_tokens) < 2:
        return False

    size = len(pool_tokens)

    return any(
        list_tokens[start:start + size] == pool_tokens
        for start in range(
            len(list_tokens) - size + 1
        )
    )


def list_path(list_id: str) -> Path:

    if list_id not in COMPANY_LISTS:
        raise ValueError(
            f"Unknown company list: {list_id}"
        )

    return LISTS_DIR / COMPANY_LISTS[list_id]["file"]


def load_list(list_id: str) -> list[dict]:

    with list_path(list_id).open(
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))

    return [
        row
        for row in rows
        if str(row.get("company", "")).strip()
    ]


def load_checked() -> dict:

    if not CHECKED_PATH.exists():
        return {}

    try:
        return json.loads(
            CHECKED_PATH.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def save_checked(checked: dict) -> None:

    temp = CHECKED_PATH.with_suffix(".json.tmp")

    temp.write_text(
        json.dumps(
            checked,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    temp.replace(CHECKED_PATH)


def recently_checked(
    entry: dict | None,
) -> bool:

    if not entry:
        return False

    try:
        checked_at = datetime.fromisoformat(
            entry["checked_at"]
        )
    except Exception:
        return False

    days = RECHECK_AFTER_DAYS

    # The local check has no second "confirm no signal" search
    # (it missed a bank in the 2026-09-28 test), so its misses
    # come back sooner.
    if (
        entry.get("backend") == "local"
        and not entry.get("ai_signal_found")
    ):
        days = LOCAL_NO_SIGNAL_RECHECK_DAYS

    return (
        datetime.now(timezone.utc) - checked_at
        < timedelta(days=days)
    )


def remaining_companies(
    list_id: str,
    exclude_companies: set[str] | None = None,
) -> tuple[list[dict], dict]:
    """
    List companies still worth checking, in list order,
    plus counts for the UI.
    """

    rows = load_list(list_id)

    pool_names = [
        tokens
        for tokens in (
            name_tokens(company)
            for company in exclude_companies or ()
        )
        if tokens
    ]

    checked = load_checked().get(list_id, {})

    remaining = []
    in_pool = 0
    already_checked = 0

    for row in rows:

        company = row["company"].strip()
        tokens = name_tokens(company)

        if any(
            same_company(tokens, pool)
            for pool in pool_names
        ):
            in_pool += 1
            continue

        if recently_checked(checked.get(company)):
            already_checked += 1
            continue

        remaining.append(row)

    return remaining, {
        "total": len(rows),
        "in_pool": in_pool,
        "checked": already_checked,
        "remaining": len(remaining),
    }


def list_summaries(
    exclude_companies: set[str] | None = None,
) -> list[dict]:

    summaries = []

    for list_id, meta in COMPANY_LISTS.items():

        _, counts = remaining_companies(
            list_id,
            exclude_companies,
        )

        summaries.append(
            {
                "id": list_id,
                "label": meta["label"],
                "source": meta["source"],
                **counts,
            }
        )

    return summaries


def check_company(
    company: str,
    country: str,
    target_description: str,
) -> dict:
    """
    One web search about one named company. Returns the
    model's JSON answer, or None if it never searched (an
    answer from memory is not a check).
    """

    messages = [
        {
            "role": "system",
            "content": (
                "You check ONE named company for public "
                "evidence that it adopts AI in its own "
                "operations. You must perform exactly ONE "
                "web search before answering. Do not "
                "answer from memory. Do not invent "
                "websites, signals or source URLs. Return "
                "only valid JSON after the search."
            ),
        },
        {
            "role": "user",
            "content": f"""
COMPANY: {company}
COUNTRY: {country}

Search for recent public evidence that THIS company uses,
rolls out or invests in AI, generative AI or AI-driven
automation in its OWN business (employees, processes,
operations, customer service). Selling AI to others does
not count as adoption.

Prospect context (what counts as a useful signal and what
is excluded):

{target_description}

Rules:

- The evidence must be about this exact company (not a
  namesake, not a parent or subsidiary unless clearly the
  same group).
- Much evidence is published only in the company's
  local language (e.g. German, Swedish, Croatian,
  Serbian): search in that language when useful.
- If the search finds no such evidence, set
  "ai_signal_found" to false. That is a normal, useful
  answer; do not stretch weak evidence.
- "source_url" must be the page where you saw the
  evidence.

Return exactly:

{{
  "company": "{company}",
  "website": "",
  "country": "{country}",
  "primary_business": "",
  "ai_signal_found": true,
  "signal": "",
  "why_interesting": "",
  "source_url": "",
  "confidence": "HIGH|MEDIUM|LOW"
}}
""",
        },
    ]

    for attempt in range(1, 4):

        response = moonshot_chat_create(
            model="kimi-k2.6",
            messages=messages,
            tools=WEB_SEARCH_TOOL,
            tool_choice="auto",
            response_format={
                "type": "json_object"
            },
            max_tokens=2048,
            timeout=120,
            extra_body={
                "thinking": {
                    "type": "disabled"
                }
            },
        )

        choice = response.choices[0]

        if choice.finish_reason != "tool_calls":
            print(
                f"WARNING: {company}: model answered "
                f"without searching (attempt {attempt}/3).",
                flush=True,
            )

            # Repeating the identical request tends to get
            # the identical answer. Show the model its
            # answer and ask again for the search.
            messages = messages + [
                {
                    "role": "assistant",
                    "content": (
                        choice.message.content or ""
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "You answered without searching. "
                        "Call $web_search now, then "
                        "answer only from what it returns."
                    ),
                },
            ]
            continue

        tool_calls = choice.message.tool_calls or []

        final_messages = list(messages)
        final_messages.append(choice.message)

        for tool_call in tool_calls:
            arguments = json.loads(
                tool_call.function.arguments
            )

            print(
                f"Search for {company}:",
                arguments.get("query", ""),
                flush=True,
            )

            final_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": json.dumps(arguments),
                }
            )

        final_response = moonshot_chat_create(
            model="kimi-k2.6",
            messages=final_messages,
            tools=WEB_SEARCH_TOOL,
            tool_choice="none",
            response_format={
                "type": "json_object"
            },
            max_tokens=2048,
            timeout=120,
            extra_body={
                "thinking": {
                    "type": "disabled"
                }
            },
        )

        return clean_json(
            final_response.choices[0].message.content
            or ""
        )

    return None


# "Artificial intelligence" in the list countries' languages:
# much of the evidence is only published locally.
LOCAL_AI_TERMS = {
    "Switzerland": "künstliche Intelligenz",
    "Germany": "künstliche Intelligenz",
    "Sweden": "artificiell intelligens",
    "Finland": "tekoäly",
    "Denmark": "kunstig intelligens",
    "Croatia": "umjetna inteligencija",
    "Serbia": "veštačka inteligencija",
}

LOCAL_PAGES_TO_READ = 3
LOCAL_PAGE_CHARS = 3000


def local_sources(
    company: str,
    country: str,
) -> list[dict]:
    """SearXNG results for the company, top pages fetched."""

    from fetch_source import fetch_source_text
    from web_search import search

    # "Example a.d. (Beograd)" -> name + city terms.
    name = company.replace("(", " ").replace(")", " ")

    # Two searches per company: each one uses a search credit.
    queries = [
        f"{name} artificial intelligence",
        f"{name} "
        + LOCAL_AI_TERMS.get(country, "AI digital transformation"),
    ]

    per_query = [
        [
            item
            for item in search(query)
            if not any(
                hostname(item["url"]) == blocked
                or hostname(item["url"]).endswith("." + blocked)
                for blocked in BLOCKED_DOMAINS
            )
        ]
        for query in queries
    ]

    # Take the queries' results in turn: appending them let the
    # English search fill 8 of the 10 slots, so local-language
    # press (sometimes a company's only AI mention) was cut.
    sources: list[dict] = []
    seen: set[str] = set()

    for rank in range(max(map(len, per_query), default=0)):
        for results in per_query:
            if rank < len(results) and results[rank]["url"] not in seen:
                seen.add(results[rank]["url"])
                sources.append(results[rank])

    sources = sources[:10]

    for item in sources[:LOCAL_PAGES_TO_READ]:
        # Tavily already returns the page text.
        if item.get("page"):
            continue

        try:
            item["page"] = fetch_source_text(item["url"])[
                :LOCAL_PAGE_CHARS
            ]
        except Exception:
            item["page"] = ""

    # Only the top pages go to the model in full; the rest as
    # snippets, to keep the prompt within the model's context.
    for item in sources[LOCAL_PAGES_TO_READ:]:
        item.pop("page", None)

    return sources


def check_company_local(
    company: str,
    country: str,
    target_description: str,
) -> dict | None:
    """
    Same question as check_company, answered by the local model
    from SearXNG results. The model may only cite a URL it was
    given; anything else counts as no signal.
    """

    sources = local_sources(company, country)

    print(
        f"Local search for {company}: "
        f"{len(sources)} sources",
        flush=True,
    )

    if not sources:
        # Almost always the search engines behind SearXNG
        # blocking us (CAPTCHA / rate limit), not a real
        # "nothing found". Fail, so the company is retried on
        # the next run instead of being hidden for months.
        raise RuntimeError(
            "SearXNG returned no results (engines blocked or "
            "rate-limited?)."
        )

    source_block = "\n\n".join(
        f"[{index}] {item['title']}\n"
        f"URL: {item['url']}\n"
        f"Snippet: {item['content']}"
        + (
            f"\nPage excerpt: {item['page']}"
            if item.get("page")
            else ""
        )
        for index, item in enumerate(sources, start=1)
    )

    content = local_chat_json(
        [
            {
                "role": "system",
                "content": (
                    "You check ONE named company for public "
                    "evidence that it adopts AI in its own "
                    "operations, using ONLY the search results "
                    "provided. Do not use outside knowledge. "
                    "Do not invent websites, signals or URLs. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
COMPANY: {company}
COUNTRY: {country}

Does THIS company use, roll out or invest in AI, generative
AI or AI-driven automation in its OWN business (employees,
processes, operations, customer service)? Selling AI to
others does not count as adoption.

Prospect context (what counts as a useful signal and what
is excluded):

{target_description}

Rules:

- Use only the search results below. They may be in any
  language.
- The evidence must be about this exact company (not a
  namesake, not a different company in the results).
- If the results show no such evidence, set
  "ai_signal_found" to false. That is a normal, useful
  answer; do not stretch weak evidence.
- "source_url" must be copied exactly from one result below.
- "signal_date": when the cited evidence happened or was
  published, as YYYY-MM or YYYY, taken from the source. Empty
  if the source does not show it. Today is
  {datetime.now(timezone.utc):%Y-%m-%d}.
- "signal_stage": LIVE if the AI is in use, PILOT if it is
  being tested, PLAN if the company only says it plans or
  considers it.

SEARCH RESULTS:

{source_block}

Return exactly:

{{
  "company": "{company}",
  "website": "",
  "country": "{country}",
  "primary_business": "",
  "ai_signal_found": true,
  "signal": "",
  "why_interesting": "",
  "source_url": "",
  "signal_date": "",
  "signal_stage": "LIVE|PILOT|PLAN",
  "confidence": "HIGH|MEDIUM|LOW"
}}
""",
            },
        ],
        max_tokens=1500,
    )

    answer = clean_json(content)

    # Guard against invented evidence: the cited page must be
    # one the model was actually shown.
    if signal_found(answer) and str(
        answer.get("source_url", "")
    ).strip() not in {item["url"] for item in sources}:
        print(
            f"WARNING: {company}: local model cited a URL "
            "that was not in its search results; treated "
            "as no signal.",
            flush=True,
        )
        answer["ai_signal_found"] = False

    return answer


def signal_found(answer: dict) -> bool:

    value = answer.get("ai_signal_found")

    return (
        value is True
        or str(value).strip().lower() == "true"
    )


# Evidence older than this is not "current" AI activity.
SIGNAL_MAX_AGE_MONTHS = 12


def signal_is_old(signal_date: str) -> bool:
    """
    True when YYYY-MM / YYYY is more than SIGNAL_MAX_AGE_MONTHS
    ago. A bare year counts as December (benefit of the doubt);
    an empty or unreadable date is not "old", just unknown.
    """

    match = re.match(r"^\s*(\d{4})(?:-(\d{1,2}))?", signal_date)

    if not match:
        return False

    months = int(match.group(1)) * 12 + int(match.group(2) or 12)

    now = datetime.now(timezone.utc)

    return (
        now.year * 12 + now.month - months
        > SIGNAL_MAX_AGE_MONTHS
    )


def to_candidate(
    row: dict,
    answer: dict,
) -> dict | None:

    if not signal_found(answer):
        return None

    website = str(answer.get("website", "")).strip()
    domain = hostname(website)

    if (
        domain in BLOCKED_DOMAINS
        or any(
            domain.endswith("." + blocked)
            for blocked in BLOCKED_DOMAINS
        )
    ):
        domain = ""
        website = ""

    why = str(answer.get("why_interesting", "")).strip()
    business = str(
        answer.get("primary_business", "")
    ).strip()

    if business:
        # Lets qualification spot vendors/consultancies.
        why = f"{why} (Business: {business})".strip()

    signal_date = str(answer.get("signal_date", "")).strip()
    signal_stage = str(
        answer.get("signal_stage", "")
    ).strip().upper()

    if signal_stage not in {"LIVE", "PILOT", "PLAN"}:
        signal_stage = ""

    confidence = str(
        answer.get("confidence", "LOW")
    ).strip().upper()

    # The model rated a two-year-old one-line "plans to invest
    # in AI" HIGH; a plan or old evidence is never strong.
    if signal_stage == "PLAN" or signal_is_old(signal_date):
        confidence = "LOW"

    return {
        # Keep the official list name: it is how the
        # company is tracked in the checked-list state.
        "company": row["company"].strip(),
        "website": website,
        "domain": domain,
        "country": (
            str(row.get("country", "")).strip()
            or str(answer.get("country", "")).strip()
        ),
        "signal": str(answer.get("signal", "")).strip(),
        "why_interesting": why,
        "source_url": str(
            answer.get("source_url", "")
        ).strip(),
        "signal_date": signal_date,
        "signal_stage": signal_stage,
        "confidence": confidence,
    }


def discover_from_list(
    list_id: str,
    company_count: int,
    target_description: str,
    exclude_companies: set[str] | None = None,
    on_progress: Callable[[int, int, int], None]
    | None = None,
) -> dict:
    """
    Check the next `company_count` unchecked list companies.
    on_progress(done, total, with_signal) is called after
    each company.
    """

    remaining, counts = remaining_companies(
        list_id,
        exclude_companies,
    )

    batch = remaining[
        :max(1, min(company_count, MAX_COMPANIES_PER_RUN))
    ]

    print(
        f"Company list {list_id}: {counts}. "
        f"Checking {len(batch)} companies.",
        flush=True,
    )

    candidates: list[dict] = []
    outcomes: dict[str, dict] = {}
    failed = 0
    done = 0

    local = backend_for("check") == "local"

    def check(row: dict) -> tuple[dict, dict | None]:

        def once() -> dict | None:
            return (
                check_company_local if local else check_company
            )(
                company=row["company"].strip(),
                country=str(
                    row.get("country", "")
                ).strip(),
                target_description=target_description,
            )

        answer = once()

        # One search sometimes misses evidence that a
        # second search finds (seen on Adval Tech). A miss
        # hides the company for RECHECK_AFTER_DAYS, so
        # confirm "no signal" once before accepting it.
        # Not locally: SearXNG returns the same pages again.
        if (
            not local
            and answer is not None
            and not signal_found(answer)
        ):
            second = once()

            if second is not None:
                answer = second

        return row, answer

    def safe_check(row: dict):
        # One failed company must not end the run.
        try:
            return check(row)
        except Exception as exc:
            print(
                f"WARNING: check failed for "
                f"{row['company']} "
                f"({exc.__class__.__name__}: {exc})",
                flush=True,
            )
            return row, None

    # Locally the GPU runs one model call at a time; two
    # workers let one search/fetch while the other waits.
    with ThreadPoolExecutor(
        max_workers=2 if local else PARALLEL_CHECKS
    ) as pool:

        for row, answer in pool.map(safe_check, batch):

            done += 1
            company = row["company"].strip()

            if answer is None:
                # Not recorded as checked: retry next run.
                failed += 1

            else:
                candidate = to_candidate(row, answer)

                if candidate:
                    candidates.append(candidate)

                outcomes[company] = {
                    "checked_at": now_iso(),
                    "backend": "local" if local else "kimi",
                    "ai_signal_found": bool(candidate),
                    "source_url": str(
                        answer.get("source_url", "")
                    ).strip(),
                }

            if on_progress:
                on_progress(
                    done,
                    len(batch),
                    len(candidates),
                )

    if batch and failed == len(batch):
        raise RuntimeError(
            "All company checks failed."
        )

    checked = load_checked()
    checked.setdefault(list_id, {}).update(outcomes)
    save_checked(checked)

    return {
        "mode": "company_list",
        "company_list": list_id,
        "target": target_description,
        "checked_count": len(batch) - failed,
        "failed_count": failed,
        "list_counts": counts,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
