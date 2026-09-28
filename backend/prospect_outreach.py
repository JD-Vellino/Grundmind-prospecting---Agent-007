from __future__ import annotations

import json
import os
import re

from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from llm import (
    backend_for,
    local_chat_json,
    moonshot_client,
)

from research_core import clean_json


ROOT = Path(__file__).resolve().parent
POOL_PATH = ROOT / "master_prospect_pool.json"

load_dotenv(
    ROOT / ".env"
)

# OUTREACH_BACKEND=local in .env drafts on the local model.
# Logged: see llm.py / llm_usage.jsonl.
LOCAL = backend_for("outreach") == "local"

client = None if LOCAL else moonshot_client()

BATCH_SIZE = 10

# Legal forms dropped from the name used in emails.
LEGAL_FORMS = re.compile(
    r"(?:[\s,]+(?:a\.?d\.?o?\.?|d\.?d\.?|d\.?o\.?o\.?|ag|se|sa|s\.a\.|"
    r"plc|n\.?v\.?|asa|ab|abp|oyj|a/s|gmbh|ltd\.?|inc\.?))+\s*$",
    re.IGNORECASE,
)


def display_name(company: str) -> str:
    """
    "Example a.d. (Beograd)" -> "Example". List names
    carry the legal form and the town; an email should not.
    """

    name = re.sub(r"\s*\([^)]*\)\s*$", "", company).strip()
    short = LEGAL_FORMS.sub("", name).strip()

    return short or name


def load_pool() -> dict:
    if not POOL_PATH.exists():
        return {
            "prospects": [],
        }

    return json.loads(
        POOL_PATH.read_text(
            encoding="utf-8"
        )
    )


def save_pool(pool: dict) -> None:
    temp = POOL_PATH.with_suffix(
        ".json.tmp"
    )

    temp.write_text(
        json.dumps(
            pool,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    temp.replace(
        POOL_PATH
    )


def generate_batch(
    prospects: list[dict],
    subject_template: str,
    body_template: str,
    use_ai_signal: bool,
    use_pain_signal: bool,
    use_role: bool,
) -> list[dict]:

    compact = []

    for prospect in prospects:

        contact = (
            prospect.get("contact")
            or {}
        )

        compact.append(
            {
                "company": display_name(
                    str(prospect.get("company", ""))
                ),
                "domain": prospect.get(
                    "domain",
                    "",
                ),
                "first_name": str(
                    contact.get(
                        "name",
                        "",
                    )
                ).split(" ")[0],
                "contact_name": contact.get(
                    "name",
                    "",
                ),
                "contact_title": contact.get(
                    "title",
                    "",
                ),
                "likely_team": prospect.get(
                    "likely_team",
                    "",
                ),
                "ai_investment": prospect.get(
                    "ai_investment",
                    "",
                ),
                "pain_signal": prospect.get(
                    "pain_signal",
                    "",
                ),
                "signal": prospect.get(
                    "signal",
                    "",
                ),
                "signal_date": prospect.get(
                    "signal_date",
                    "",
                ),
                "signal_stage": prospect.get(
                    "signal_stage",
                    "",
                ),
                "why_interesting": (
                    prospect.get(
                        "why_interesting",
                        "",
                    )
                ),
                "email": prospect.get(
                    "email",
                    "",
                ),
            }
        )

    messages = [
            {
                "role": "system",
                "content": (
                    "You write concise B2B outreach "
                    "emails for GrundMind. "
                    "Personalize each email using only "
                    "the supplied prospect information. "
                    "Do not invent precise facts. "
                    "Do not claim a company has a problem "
                    "unless the supplied evidence supports "
                    "that claim. Indirect pain signals may "
                    "be framed cautiously as a relevant "
                    "challenge or question. "
                    "Keep the user's underlying message "
                    "and intent. Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
BASE SUBJECT:

{subject_template}

BASE BODY:

{body_template}


PERSONALISATION SETTINGS

Use AI activity: {use_ai_signal}
Use pain/opportunity: {use_pain_signal}
Use recipient role: {use_role}


PROSPECTS

{json.dumps(compact, indent=2, ensure_ascii=False)}


Create one individual email for every prospect.

Requirements:

- replace placeholders such as {{{{company}}}},
  {{{{first_name}}}} and {{{{role}}}}
- write company names in normal capitalisation, not all
  caps (ADIDAS -> Adidas)
- preserve the basic purpose and tone of the base email
- make the opening relevant to that company
- use company AI evidence when enabled
- today is {datetime.now(timezone.utc):%Y-%m-%d}. Only present
  a signal as current ("you are rolling out...") when
  signal_stage is LIVE or PILOT and signal_date is within the
  last 12 months. If signal_stage is PLAN, or signal_date is
  older or empty, either mention it with its year ("in 2024,
  you announced plans to invest in AI") or leave it out.
  Never turn a plan into an achievement.
- use pain/opportunity context when enabled
- adapt wording to the recipient role when enabled
- avoid fake familiarity
- avoid exaggerated claims
- keep each email concise
- no markdown inside the email
- no em dashes

Return exactly:

{{
  "drafts": [
    {{
      "domain": "",
      "subject": "",
      "body": ""
    }}
  ]
}}
""",
            },
    ]

    if LOCAL:
        content = local_chat_json(
            messages,
            max_tokens=7000,
        )

    else:
        response = client.chat.completions.create(
            model="kimi-k2.6",
            messages=messages,
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

        content = (
            response.choices[0]
            .message.content
            or ""
        )

    result = clean_json(content)

    drafts = result.get(
        "drafts",
        [],
    )

    if not isinstance(
        drafts,
        list,
    ):
        return []

    return [
        draft
        for draft in drafts
        if isinstance(
            draft,
            dict,
        )
    ]


def generate_drafts(
    domains: list[str],
    subject: str,
    body: str,
    use_ai_signal: bool = True,
    use_pain_signal: bool = True,
    use_role: bool = True,
) -> dict:

    wanted = {
        str(domain)
        .strip()
        .lower()
        for domain in domains
        if str(domain).strip()
    }

    if not wanted:
        raise ValueError(
            "Select at least one prospect."
        )

    if not subject.strip():
        raise ValueError(
            "Subject cannot be empty."
        )

    if not body.strip():
        raise ValueError(
            "Email body cannot be empty."
        )

    pool = load_pool()

    prospects = pool.get(
        "prospects",
        [],
    )

    selected = [
        prospect
        for prospect in prospects
        if str(
            prospect.get(
                "domain",
                "",
            )
        ).strip().lower()
        in wanted
        and prospect.get("email")
    ]

    skipped = (
        len(wanted)
        - len(selected)
    )

    generated = []

    for start in range(
        0,
        len(selected),
        BATCH_SIZE,
    ):
        batch = selected[
            start:start + BATCH_SIZE
        ]

        generated.extend(
            generate_batch(
                prospects=batch,
                subject_template=subject,
                body_template=body,
                use_ai_signal=(
                    use_ai_signal
                ),
                use_pain_signal=(
                    use_pain_signal
                ),
                use_role=use_role,
            )
        )

    by_domain = {
        str(
            draft.get(
                "domain",
                "",
            )
        ).strip().lower(): draft
        for draft in generated
    }

    saved = 0

    for prospect in prospects:

        domain = str(
            prospect.get(
                "domain",
                "",
            )
        ).strip().lower()

        draft = by_domain.get(
            domain
        )

        if not draft:
            continue

        prospect[
            "draft_subject"
        ] = str(
            draft.get(
                "subject",
                "",
            )
        ).strip()

        prospect[
            "draft_body"
        ] = str(
            draft.get(
                "body",
                "",
            )
        ).strip()

        prospect[
            "outreach_status"
        ] = "DRAFTED"

        saved += 1

    save_pool(pool)

    return {
        "requested": len(wanted),
        "eligible": len(selected),
        "generated": saved,
        "skipped_no_email": skipped,
    }
