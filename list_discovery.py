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

    return (
        datetime.now(timezone.utc) - checked_at
        < timedelta(days=RECHECK_AFTER_DAYS)
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


def signal_found(answer: dict) -> bool:

    value = answer.get("ai_signal_found")

    return (
        value is True
        or str(value).strip().lower() == "true"
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
        "confidence": str(
            answer.get("confidence", "LOW")
        ).strip().upper(),
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

    def check(row: dict) -> tuple[dict, dict | None]:

        def once() -> dict | None:
            return check_company(
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
        if answer is not None and not signal_found(answer):
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

    with ThreadPoolExecutor(
        max_workers=PARALLEL_CHECKS
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
