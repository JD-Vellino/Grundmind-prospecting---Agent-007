from __future__ import annotations

import json
import os

from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import OpenAI

from company_config import (
    CompanyConfig,
    SourcePolicy,
    get_company_config,
    normalize_name,
    save_company_config,
)
from fetch_source import fetch_source_text
from research_core import (
    clean_json,
    research,
)


load_dotenv()

client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.ai/v1",
)


SIGNALS = (
    "ai_hiring",
    "ai_deployment",
    "ai_value_roi",
    "organisational_fit",
    "commercial_opportunity",
    "account_brief",
)


def hostname_from_url(
    url: str,
) -> str:

    candidate = url.strip()

    if (
        candidate
        and "://" not in candidate
    ):
        candidate = (
            "https://" + candidate
        )

    return (
        (urlparse(candidate).hostname or "")
        .lower()
        .removeprefix("www.")
    )


def resolve_company_identity(
    query: str,
    website_hint: str | None = None,
) -> CompanyConfig:

    query = query.strip()

    if not query:
        raise ValueError(
            "Company name is required."
        )

    # -----------------------------------------------------
    # Explicit website identity
    #
    # When the user supplies a website, that domain is the
    # corporate identity boundary. Do not ask the LLM to
    # choose between similarly named companies.
    # -----------------------------------------------------

    if website_hint:

        website = website_hint.strip()

        if "://" not in website:
            website = (
                "https://" + website
            )

        official_domain = hostname_from_url(
            website
        )

        if not official_domain:
            raise ValueError(
                "Website hint does not contain "
                "a valid domain."
            )

        source_text = fetch_source_text(
            website
        )

        if not source_text.strip():
            raise ValueError(
                "Supplied company website returned "
                "no extractable source text."
            )

        research_identity = (
            f"{query}, whose official website is "
            f"{website}. Research only the corporate "
            f"entity operating at {official_domain}. "
            "Do not substitute similarly named companies."
        )

        policy = SourcePolicy(
            official_domains=(
                official_domain,
            ),
        )

        config = CompanyConfig(
            name=query,
            aliases=(
                query,
            ),
            research_identity=(
                research_identity
            ),
            excluded_domains=(),
            source_policies={
                signal: policy
                for signal in SIGNALS
            },
        )

        save_company_config(
            config
        )

        return config

    try:
        cached_config = get_company_config(
            query
        )

        # A short or ambiguous alias must not silently
        # select a previously resolved corporate entity.
        # Only an exact canonical-name request may bypass
        # fresh identity resolution.
        if (
            normalize_name(query)
            == normalize_name(
                cached_config.name
            )
        ):
            return cached_config

    except ValueError:
        pass

    hint_text = (
        f" The user supplied this possible website: "
        f"{website_hint}."
        if website_hint
        else ""
    )

    objective = (
        "Identify the exact corporate entity the user "
        f"means by the company query {query!r}."
        + hint_text
        + " Determine the canonical company name, its "
        "official corporate website/domain, headquarters "
        "country or location when available, and a short "
        "business description. Actively identify similarly "
        "named companies that could contaminate subsequent "
        "research. Prefer the company's own website and "
        "other direct corporate sources. Do not research AI "
        "activity yet. This step is only corporate identity "
        "resolution."
    )

    research_result = research(
        company=query,
        objective=objective,
        max_searches=3,
    )

    raw_research = json.dumps(
        research_result,
        indent=2,
    )

    response = client.chat.completions.create(
        model="kimi-k2.6",
        messages=[
            {
                "role": "system",
                "content": (
                    "You resolve corporate identities "
                    "from supplied web research. "
                    "Do not use outside knowledge. "
                    "Do not invent domains. "
                    "If multiple materially plausible "
                    "entities remain, mark the result "
                    "AMBIGUOUS. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
USER COMPANY QUERY:
{query}

WEBSITE HINT:
{website_hint or ""}

WEB RESEARCH:
{raw_research}

Return exactly:

{{
  "status": "RESOLVED|AMBIGUOUS|NOT_FOUND",
  "canonical_name": "",
  "official_website": "",
  "official_domain": "",
  "country_or_location": "",
  "business_description": "",
  "aliases": [],
  "excluded_domains": [],
  "reason": ""
}}

Rules:

- official_domain must belong to the resolved company.
- Do not use a similarly named company's domain.
- excluded_domains should contain domains belonging to
  confusing but different companies.
- A supplied website hint is an explicit identity constraint.
- If the research establishes that the supplied website belongs
  to one of several same-name companies, resolve to that company.
- Other same-name companies are not a reason to return AMBIGUOUS
  when the supplied website safely identifies one entity.
- If the supplied website cannot be established as belonging to
  the intended company, do not guess.
- If identity remains materially ambiguous after applying any
  website hint, return AMBIGUOUS.
""",
            },
        ],
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

    identity = clean_json(
        response.choices[0].message.content
        or ""
    )

    status = identity.get("status")

    if status != "RESOLVED":
        raise ValueError(
            "Company identity could not be safely "
            f"resolved: {status}. "
            f"{identity.get('reason', '')}"
        )

    canonical_name = (
        identity.get(
            "canonical_name",
            "",
        ).strip()
    )

    official_website = (
        identity.get(
            "official_website",
            "",
        ).strip()
    )

    official_domain = (
        identity.get(
            "official_domain",
            "",
        )
        .strip()
        .lower()
        .removeprefix("www.")
    )

    if not canonical_name:
        raise ValueError(
            "Identity resolver returned no "
            "canonical company name."
        )

    if not official_website:
        raise ValueError(
            "Identity resolver returned no "
            "official website."
        )

    derived_domain = hostname_from_url(
        official_website
    )

    if not official_domain:
        official_domain = derived_domain

    if (
        not derived_domain
        or derived_domain != official_domain
    ):
        raise ValueError(
            "Resolved official website and "
            "official domain do not agree."
        )

    # -----------------------------------------------------
    # User-supplied website identity gate
    #
    # A website hint is an explicit identity constraint,
    # not merely another suggestion to the LLM.
    # -----------------------------------------------------

    if website_hint:

        hint_domain = hostname_from_url(
            website_hint
        )

        if not hint_domain:
            raise ValueError(
                "Website hint does not contain "
                "a valid domain."
            )

        if hint_domain != official_domain:
            raise ValueError(
                "Resolved company domain does not "
                "match the supplied website: "
                f"{official_domain!r} != "
                f"{hint_domain!r}."
            )

    # Confirm that the proposed official website
    # actually yields source material.
    source_text = fetch_source_text(
        official_website
    )

    if not source_text.strip():
        raise ValueError(
            "Resolved official website returned "
            "no extractable source text."
        )

    aliases = {
        query,
        canonical_name,
        *identity.get(
            "aliases",
            [],
        ),
    }

    excluded_domains = tuple(
        sorted(
            {
                str(domain)
                .strip()
                .lower()
                .removeprefix("www.")
                for domain
                in identity.get(
                    "excluded_domains",
                    [],
                )
                if str(domain).strip()
                and str(domain)
                .strip()
                .lower()
                .removeprefix("www.")
                != official_domain
            }
        )
    )

    # -----------------------------------------------------
    # Deterministic ambiguity gate
    #
    # The resolver may identify a plausible entity while
    # also identifying another similarly named company.
    # A bare user query must not silently choose between
    # those entities.
    # -----------------------------------------------------

    if (
        excluded_domains
        and not website_hint
        and normalize_name(query)
        != normalize_name(
            canonical_name
        )
    ):
        raise ValueError(
            "AMBIGUOUS COMPANY IDENTITY: "
            f"{query!r} resolved provisionally to "
            f"{canonical_name!r}, but similarly named "
            "companies were also identified at: "
            + ", ".join(excluded_domains)
            + ". Provide the full company name or "
            "official website."
        )

    research_identity = (
        f"{canonical_name}, "
        f"{identity.get('business_description', '').strip()}, "
        f"{identity.get('country_or_location', '').strip()}, "
        f"whose official website is "
        f"{official_website}. "
    )

    if excluded_domains:
        research_identity += (
            "Do not confuse this company with "
            "different entities using these domains: "
            + ", ".join(excluded_domains)
            + "."
        )

    policy = SourcePolicy(
        official_domains=(
            official_domain,
        ),
    )

    config = CompanyConfig(
        name=canonical_name,
        aliases=tuple(
            sorted(
                alias.strip()
                for alias in aliases
                if alias.strip()
            )
        ),
        research_identity=(
            research_identity
        ),
        excluded_domains=(
            excluded_domains
        ),
        source_policies={
            signal: policy
            for signal in SIGNALS
        },
    )

    save_company_config(
        config
    )

    return config
