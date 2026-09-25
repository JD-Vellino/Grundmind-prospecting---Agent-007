from __future__ import annotations

import json
import math
import os
import re
import sys
import time

from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import OpenAI

from research_core import (
    WEB_SEARCH_TOOL,
    clean_json,
)


load_dotenv()

client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.ai/v1",
)


def moonshot_chat_create(**kwargs):
    """Retry transient Moonshot/API failures."""

    delays = (2, 4, 8)

    for attempt in range(4):
        try:
            return client.chat.completions.create(
                **kwargs
            )

        except Exception as exc:
            status_code = getattr(
                exc,
                "status_code",
                None,
            )

            error_name = (
                exc.__class__.__name__
            )

            transient = (
                status_code in {
                    429,
                    500,
                    502,
                    503,
                    504,
                }
                or error_name in {
                    "APIConnectionError",
                    "APITimeoutError",
                    "InternalServerError",
                    "RateLimitError",
                }
            )

            if (
                not transient
                or attempt == 3
            ):
                raise

            delay = delays[attempt]

            print(
                "WARNING: transient Moonshot "
                f"error ({error_name}, "
                f"HTTP {status_code}). "
                f"Retrying in {delay}s..."
            )

            time.sleep(delay)

OUTPUT_PATH = Path("latest_discovery.json")


DISCOVERY_LENSES = (
    "enterprise AI adoption and generative AI rollouts",
    "workflow automation and digital transformation",
    "AI governance, enablement and internal adoption",
    "finance, reporting and planning automation",
    "operations, supply chain and customer-service automation",
    "vendor customer case studies showing measurable transformation",
    "AI-related hiring combined with broader business adoption",
    "multi-country organisations standardising processes and systems",
)


BLOCKED_DOMAINS = {
    "linkedin.com",
    "wikipedia.org",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "crunchbase.com",
    "bloomberg.com",
    "reuters.com",
}


def hostname(url: str) -> str:
    value = url.strip()

    if not value:
        return ""

    if "://" not in value:
        value = "https://" + value

    return (
        (urlparse(value).hostname or "")
        .lower()
        .removeprefix("www.")
    )


def normalize_company(value: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "",
        value.lower(),
    )


def run_discovery_search(
    target_description: str,
    lens: str,
    limit: int,
    known_companies: list[str] | None = None,
) -> dict:
    """
    Broad top-of-funnel search.

    Unlike Agent 007 forensic research, this worker is
    deliberately NOT tied to one target company.
    """

    known_block = ""

    if known_companies:
        # Without this the worker keeps resurfacing the
        # same well-known names, which are then discarded
        # as duplicates of the existing pool.
        known_block = (
            "\nALREADY KNOWN COMPANIES (do NOT return any "
            "of these, or their subsidiaries/brands; spend "
            "the search on companies not in this list):\n\n"
            + "; ".join(known_companies)
            + "\n"
        )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a broad B2B prospect discovery "
                "agent. You are NOT researching one target "
                "company. Find multiple distinct operating "
                "companies matching the supplied market "
                "criteria. You must perform exactly ONE "
                "web search. Do not answer from memory. "
                "Do not invent companies, websites, "
                "signals, or source URLs. Return only "
                "valid JSON after the search."
            ),
        },
        {
            "role": "user",
            "content": f"""
PROSPECT TARGET:

{target_description}

DISCOVERY LENS:

{lens}

Find up to {limit} distinct companies.
{known_block}
This is broad prospect discovery, not forensic research.

Useful reasons for surfacing a company include:

- AI adoption
- generative AI deployment
- workflow automation
- digital transformation
- process standardisation
- finance or operational automation
- AI governance or enablement
- measurable technology transformation
- relevant vendor/customer case studies
- AI-related hiring tied to business adoption

HARD EXCLUSIONS (never return these, not even as LOW
confidence):

- every category in the "Exclude:" line of the prospect
  target above, if present
- investors, venture funds, accelerators, incubators and
  "portfolio companies of X" groupings
- entries that are not a single named operating company

If a source is a vendor case study or customer story,
return the CUSTOMER company that adopted the technology,
never the vendor that sells it.

For every candidate, preserve the source that caused the
company to surface.

Return exactly:

{{
  "candidates": [
    {{
      "company": "",
      "website": "",
      "country": "",
      "signal": "",
      "why_interesting": "",
      "source_url": "",
      "confidence": "HIGH|MEDIUM|LOW"
    }}
  ]
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
            max_tokens=4096,
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
                "WARNING: discovery worker did not "
                f"search (attempt {attempt}/3)."
            )
            continue

        tool_calls = (
            choice.message.tool_calls
            or []
        )

        if len(tool_calls) != 1:
            raise RuntimeError(
                "Discovery worker must request "
                "exactly one web search."
            )

        tool_call = tool_calls[0]

        if (
            tool_call.function.name
            != "$web_search"
        ):
            raise RuntimeError(
                "Unexpected discovery tool: "
                f"{tool_call.function.name}"
            )

        arguments = json.loads(
            tool_call.function.arguments
        )

        actual_query = arguments.get(
            "query",
            "",
        )

        print(
            "Actual discovery search:",
            actual_query,
        )

        final_messages = list(messages)

        final_messages.append(
            choice.message
        )

        final_messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": (
                    tool_call.function.name
                ),
                "content": json.dumps(
                    arguments
                ),
            }
        )

        final_response = (
            moonshot_chat_create(
                model="kimi-k2.6",
                messages=final_messages,
                tools=WEB_SEARCH_TOOL,
                tool_choice="none",
                response_format={
                    "type": "json_object"
                },
                max_tokens=6000,
                timeout=120,
                extra_body={
                    "thinking": {
                        "type": "disabled"
                    }
                },
            )
        )

        return clean_json(
            final_response
            .choices[0]
            .message.content
            or ""
        )

    return {
        "candidates": []
    }


def discover(
    target_description: str,
    target_count: int,
    exclude_domains: set[str] | None = None,
    exclude_companies: set[str] | None = None,
) -> dict:
    """
    exclude_domains / exclude_companies: already-known
    prospects. They are named to the search workers and
    removed before the target_count cap is applied, so
    net-new companies are not cut off by known ones.
    """

    known_companies = sorted(
        {
            company.strip()
            for company in exclude_companies or ()
            if company.strip()
        },
        key=str.lower,
    )

    exclude_domains = {
        domain.strip().lower()
        for domain in exclude_domains or ()
        if domain.strip()
    }

    exclude_keys = {
        normalize_company(company)
        for company in known_companies
    } - {""}

    target_count = max(
        1,
        min(target_count, 500),
    )

    # Search more broadly than the final requested count
    # because consolidation and deduplication will remove
    # many candidates.
    per_lens = max(
        8,
        math.ceil(
            target_count
            / len(DISCOVERY_LENSES)
        )
        * 2,
    )

    research_batches = []

    for index, lens in enumerate(
        DISCOVERY_LENSES,
        start=1,
    ):
        print(
            f"\nDISCOVERY SEARCH "
            f"{index}/{len(DISCOVERY_LENSES)}"
        )
        print(lens)

        result = run_discovery_search(
            target_description=(
                target_description
            ),
            lens=lens,
            limit=per_lens,
            known_companies=known_companies,
        )

        research_batches.append(
            {
                "lens": lens,
                "research": result,
            }
        )

    # -----------------------------------------------------
    # Fast deterministic merge
    #
    # Each discovery worker already returns structured
    # candidates. Do not send all eight large search results
    # through another expensive LLM consolidation call.
    # -----------------------------------------------------

    print(
        "\nMerging discovery results..."
    )

    candidates = []

    for batch in research_batches:

        result = batch.get(
            "research",
            {},
        )

        batch_candidates = result.get(
            "candidates",
            [],
        )

        if not isinstance(
            batch_candidates,
            list,
        ):
            continue

        candidates.extend(
            candidate
            for candidate in batch_candidates
            if isinstance(
                candidate,
                dict,
            )
        )

    print(
        "Raw candidates before dedupe:",
        len(candidates),
    )

    cleaned = []
    seen_domains = set()
    seen_companies = set()

    for candidate in candidates:

        if not isinstance(candidate, dict):
            continue

        company = str(
            candidate.get(
                "company",
                "",
            )
        ).strip()

        website = str(
            candidate.get(
                "website",
                "",
            )
        ).strip()

        source_url = str(
            candidate.get(
                "source_url",
                "",
            )
        ).strip()

        if not company:
            continue

        domain = hostname(website)

        if (
            domain in BLOCKED_DOMAINS
            or any(
                domain.endswith(
                    "." + blocked
                )
                for blocked
                in BLOCKED_DOMAINS
            )
        ):
            domain = ""
            website = ""

        company_key = normalize_company(
            company
        )

        # Already in the prospect pool.
        if (
            (domain and domain in exclude_domains)
            or company_key in exclude_keys
        ):
            continue

        if domain:
            if domain in seen_domains:
                continue
        elif company_key in seen_companies:
            continue

        if domain:
            seen_domains.add(domain)

        seen_companies.add(
            company_key
        )

        cleaned.append(
            {
                "company": company,
                "website": website,
                "domain": domain,
                "country": str(
                    candidate.get(
                        "country",
                        "",
                    )
                ).strip(),
                "signal": str(
                    candidate.get(
                        "signal",
                        "",
                    )
                ).strip(),
                "why_interesting": str(
                    candidate.get(
                        "why_interesting",
                        "",
                    )
                ).strip(),
                "source_url": source_url,
                "confidence": str(
                    candidate.get(
                        "confidence",
                        "LOW",
                    )
                ).strip().upper(),
            }
        )

        if len(cleaned) >= target_count:
            break

    output = {
        "target": target_description,
        "requested_count": target_count,
        "candidate_count": len(cleaned),
        "candidates": cleaned,
    }

    OUTPUT_PATH.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return output


def main() -> None:

    if len(sys.argv) < 2:
        raise SystemExit(
            'Usage: discovery.py '
            '"prospect description" [count]'
        )

    target = sys.argv[1]

    count = (
        int(sys.argv[2])
        if len(sys.argv) >= 3
        else 25
    )

    result = discover(
        target_description=target,
        target_count=count,
    )

    print()
    print("=" * 72)
    print(
        "DISCOVERY COMPLETE:",
        result["candidate_count"],
        "candidates",
    )
    print("=" * 72)

    for index, item in enumerate(
        result["candidates"],
        start=1,
    ):
        print()
        print(
            f"{index:03d}. "
            f"{item['company']}"
        )
        print(
            "     Website:",
            item["website"] or "UNKNOWN",
        )
        print(
            "     Country:",
            item["country"] or "UNKNOWN",
        )
        print(
            "     Signal:",
            item["signal"],
        )
        print(
            "     Source:",
            item["source_url"],
        )

    print()
    print(
        "Saved:",
        OUTPUT_PATH,
    )


if __name__ == "__main__":
    main()
