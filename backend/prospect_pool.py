from __future__ import annotations

import json
import os
import re
import time

from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from research_core import clean_json


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

DISCOVERY_PATH = Path("latest_discovery.json")
POOL_PATH = Path("master_prospect_pool.json")

BATCH_SIZE = 20


def now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def normalize_company(value: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "",
        value.lower(),
    )


def prospect_key(item: dict) -> str:

    domain = str(
        item.get("domain", "")
    ).strip().lower()

    if domain:
        return f"domain:{domain}"

    return (
        "company:"
        + normalize_company(
            str(
                item.get(
                    "company",
                    "",
                )
            )
        )
    )


def load_pool() -> dict:

    if not POOL_PATH.exists():
        return {
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "prospects": [],
        }

    return json.loads(
        POOL_PATH.read_text(
            encoding="utf-8"
        )
    )


def classify_batch(
    candidates: list[dict],
) -> list[dict]:

    response = moonshot_chat_create(
        model="kimi-k2.6",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a fast internal B2B prospect "
                    "qualification agent for GrundMind. "
                    "This is NOT forensic research. "
                    "Do not browse. "
                    "Use the supplied discovery evidence. "
                    "High-level business classification and "
                    "reasonable team inference are allowed. "
                    "Do not invent precise facts or metrics. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
GRUNDMIND PROSPECTING GOAL

We want companies that are investing in or deploying AI,
generative AI, automation or substantial digital transformation.

Company size is NOT a reason to reject a prospect.

Large enterprises are attractive because GrundMind may enter through
one department or business unit.

The strongest prospects have:

- visible AI investment or deployment
- AI adoption across real workflows
- measurable transformation activity
- evidence of ROI/value uncertainty
- deployment friction
- quality problems
- scaling problems
- governance issues
- workflow problems
- remediation after AI deployment

Regulated organisations such as banks, insurers and pharmaceutical
companies are valid prospects.

Regulation/procurement/compliance should affect SALES FRICTION,
not automatically reject the company.

REJECT primarily when:

- AI/software/automation is the company's core product
- it is primarily a software consultancy
- it is primarily an IT services company
- it primarily sells AI/digital-transformation consulting
- it is primarily a research/media/training organisation
- the supplied signal is about industry research rather than the
  company's own AI adoption/investment
- it is clearly stale/non-operating

CANDIDATES:

{json.dumps(candidates, indent=2, ensure_ascii=False)}

For every candidate return:

{{
  "candidates": [
    {{
      "company": "",
      "prospect_type": "OPERATING_COMPANY|AI_VENDOR|CONSULTANCY|IT_SERVICES|RESEARCH_MEDIA|STALE_ENTITY|OTHER",
      "ai_investment": "STRONG|SOME|UNCLEAR",
      "pain_signal": "STRONG|SOME|NONE_FOUND",
      "likely_team": "",
      "sales_friction": "LOW|MEDIUM|HIGH",
      "decision": "KEEP|REJECT",
      "reason": ""
    }}
  ]
}}

Guidance:

AI INVESTMENT

STRONG
= clear meaningful AI/GenAI/automation deployment or investment.

SOME
= relevant transformation or automation signal, but AI depth is less
clear.

UNCLEAR
= supplied evidence does not establish meaningful internal/company AI
activity.

PAIN SIGNAL

STRONG
= supplied evidence indicates actual ROI/value problems, deployment
friction, remediation, quality issues, adoption problems, governance
issues or scaling difficulty.

SOME
= evidence hints at a relevant challenge but does not strongly establish
one.

NONE_FOUND
= no pain evidence in the supplied discovery result.

LIKELY TEAM

Infer the most plausible entry point from the supplied signal, such as:

- Digital Transformation
- Operations
- Customer Experience
- Finance
- Supply Chain
- Marketing
- HR / People
- IT / AI
- R&D
- Innovation

SALES FRICTION

LOW
= comparatively straightforward commercial environment.

MEDIUM
= normal large-enterprise procurement/security complexity.

HIGH
= heavily regulated or likely to involve substantial compliance,
validation, procurement or security overhead.

Do not reject solely because SALES FRICTION is HIGH.
""",
            },
        ],
        response_format={
            "type": "json_object"
        },
        max_tokens=7000,
        timeout=120,
        extra_body={
            "thinking": {
                "type": "disabled"
            }
        },
    )

    data = clean_json(
        response.choices[0]
        .message.content
        or ""
    )

    result = data.get(
        "candidates",
        [],
    )

    if not isinstance(result, list):
        return []

    return [
        item
        for item in result
        if isinstance(item, dict)
    ]


def calculate_priority(
    qualification: dict,
) -> str:

    if (
        qualification.get("decision")
        == "REJECT"
    ):
        return "REJECT"

    ai_points = {
        "STRONG": 3,
        "SOME": 2,
        "UNCLEAR": 0,
    }.get(
        qualification.get(
            "ai_investment"
        ),
        0,
    )

    pain_points = {
        "STRONG": 4,
        "SOME": 2,
        "NONE_FOUND": 0,
    }.get(
        qualification.get(
            "pain_signal"
        ),
        0,
    )

    friction_points = {
        "LOW": 2,
        "MEDIUM": 1,
        "HIGH": 0,
    }.get(
        qualification.get(
            "sales_friction"
        ),
        0,
    )

    total = (
        ai_points
        + pain_points
        + friction_points
    )

    if total >= 7:
        return "HIGH"

    if total >= 4:
        return "MEDIUM"

    return "LOW"


def qualify_discovery(
    run_id: str | None = None,
) -> dict:

    discovery = json.loads(
        DISCOVERY_PATH.read_text(
            encoding="utf-8"
        )
    )

    candidates = discovery.get(
        "candidates",
        [],
    )

    classifications = {}

    for start in range(
        0,
        len(candidates),
        BATCH_SIZE,
    ):

        batch = candidates[
            start:start + BATCH_SIZE
        ]

        print(
            "Qualifying",
            start + 1,
            "to",
            min(
                start + BATCH_SIZE,
                len(candidates),
            ),
        )

        results = classify_batch(
            batch
        )

        for result in results:

            key = normalize_company(
                str(
                    result.get(
                        "company",
                        "",
                    )
                )
            )

            if key:
                classifications[key] = (
                    result
                )

    pool = load_pool()

    existing = {
        prospect_key(item): item
        for item in pool.get(
            "prospects",
            [],
        )
    }

    added = 0
    updated = 0
    rejected = 0
    run_keys = []

    for candidate in candidates:

        company = str(
            candidate.get(
                "company",
                "",
            )
        ).strip()

        if not company:
            continue

        qualification = (
            classifications.get(
                normalize_company(company),
                {
                    "company": company,
                    "prospect_type": "OTHER",
                    "ai_investment": "UNCLEAR",
                    "pain_signal": "NONE_FOUND",
                    "likely_team": "",
                    "sales_friction": "MEDIUM",
                    "decision": "KEEP",
                    "reason": (
                        "Qualification result "
                        "was unavailable."
                    ),
                },
            )
        )

        priority = calculate_priority(
            qualification
        )

        if priority == "REJECT":
            rejected += 1

        record = {
            "company": company,
            "website": candidate.get(
                "website",
                "",
            ),
            "domain": candidate.get(
                "domain",
                "",
            ),
            "country": candidate.get(
                "country",
                "",
            ),
            "signal": candidate.get(
                "signal",
                "",
            ),
            "why_interesting": candidate.get(
                "why_interesting",
                "",
            ),
            "source_url": candidate.get(
                "source_url",
                "",
            ),
            "discovery_confidence": (
                candidate.get(
                    "confidence",
                    "",
                )
            ),
            "prospect_type": (
                qualification.get(
                    "prospect_type",
                    "OTHER",
                )
            ),
            "ai_investment": (
                qualification.get(
                    "ai_investment",
                    "UNCLEAR",
                )
            ),
            "pain_signal": (
                qualification.get(
                    "pain_signal",
                    "NONE_FOUND",
                )
            ),
            "likely_team": (
                qualification.get(
                    "likely_team",
                    "",
                )
            ),
            "sales_friction": (
                qualification.get(
                    "sales_friction",
                    "MEDIUM",
                )
            ),
            "priority": priority,
            "qualification_reason": (
                qualification.get(
                    "reason",
                    "",
                )
            ),
            "status": "NEW",
            "contact": None,
            "email": None,
            "email_status": "NOT_ENRICHED",
            "outreach_status": "NOT_STARTED",
            "first_seen_at": now_iso(),
            "last_seen_at": now_iso(),
            "discovery_count": 1,
            "last_run_id": run_id,
        }

        key = prospect_key(
            record
        )

        if key:
            run_keys.append(
                key
            )

        if key in existing:

            old = existing[key]

            # Preserve durable contact / send history,
            # but do not carry stale transient errors
            # into a newly rediscovered run.
            for field in (
                "contact",
                "email",
                "status",
                "first_seen_at",
            ):
                if field in old:
                    record[field] = (
                        old[field]
                    )

            if record.get("email"):
                record[
                    "email_status"
                ] = old.get(
                    "email_status",
                    "FOUND",
                )
            else:
                record[
                    "email_status"
                ] = "NOT_ENRICHED"

            if (
                old.get(
                    "outreach_status"
                )
                == "SENT"
            ):
                record[
                    "outreach_status"
                ] = "SENT"

                if old.get(
                    "sent_at"
                ):
                    record[
                        "sent_at"
                    ] = old[
                        "sent_at"
                    ]
            else:
                record[
                    "outreach_status"
                ] = "NOT_STARTED"

                record[
                    "send_error"
                ] = None

            record[
                "discovery_count"
            ] = (
                int(
                    old.get(
                        "discovery_count",
                        1,
                    )
                )
                + 1
            )

            existing[key] = record
            updated += 1

        else:
            existing[key] = record
            added += 1

    prospects = list(
        existing.values()
    )

    priority_order = {
        "HIGH": 0,
        "MEDIUM": 1,
        "LOW": 2,
        "REJECT": 3,
    }

    prospects.sort(
        key=lambda item: (
            priority_order.get(
                item.get(
                    "priority",
                    "LOW",
                ),
                9,
            ),
            item.get(
                "company",
                "",
            ).lower(),
        )
    )

    pool["updated_at"] = now_iso()
    pool["prospects"] = prospects

    POOL_PATH.write_text(
        json.dumps(
            pool,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "discovered": len(candidates),
        "added": added,
        "updated": updated,
        "rejected_this_run": rejected,
        "run_keys": run_keys,
        "pool_size": len(prospects),
        "high": sum(
            1
            for item in prospects
            if item.get("priority")
            == "HIGH"
        ),
        "medium": sum(
            1
            for item in prospects
            if item.get("priority")
            == "MEDIUM"
        ),
        "low": sum(
            1
            for item in prospects
            if item.get("priority")
            == "LOW"
        ),
        "reject": sum(
            1
            for item in prospects
            if item.get("priority")
            == "REJECT"
        ),
    }


def main() -> None:

    result = qualify_discovery()

    print()
    print("=" * 70)
    print("MASTER PROSPECT POOL")
    print("=" * 70)

    for key, value in result.items():
        print(
            f"{key}: {value}"
        )

    print()
    print(
        "Saved:",
        POOL_PATH,
    )


if __name__ == "__main__":
    main()
