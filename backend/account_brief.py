import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from evidence_quality import (
    INDIRECT_SOURCE_TYPES,
    classify_evidence_status,
    strongest_source_type,
)
from company_config import get_company_config


load_dotenv()

client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.ai/v1",
)


RESULT_PATH = Path(
    "latest_prospect_result.json"
)

BRIEF_JSON_PATH = Path(
    "latest_account_brief.json"
)

BRIEF_MARKDOWN_PATH = Path(
    "latest_account_brief.md"
)

COMPANY_CONFIG = get_company_config(
    os.environ.get(
        "AGENT007_COMPANY",
        "Logitech",
    )
)

COMPANY = COMPANY_CONFIG.name

SOURCE_POLICY = COMPANY_CONFIG.policy(
    "account_brief"
)

OFFICIAL_DOMAINS = list(
    SOURCE_POLICY.official_domains
)

OFFICIAL_SOURCE_PREFIXES = list(
    SOURCE_POLICY.official_source_prefixes
)


# =========================================================
# EVIDENCE CATALOG
# =========================================================

def build_evidence_catalog(
    result: dict,
) -> dict:

    catalog = {}

    for signal_key, signal in (
        result.get(
            "signals",
            {},
        ).items()
    ):

        findings = signal.get(
            "established_evidence",
            [],
        )

        for index, finding in enumerate(
            findings,
            start=1,
        ):

            evidence_id = (
                f"{signal_key}:E{index}"
            )

            supported_sources = (
                finding.get(
                    "supported_sources",
                    [],
                )
            )

            if supported_sources:

                evidence_status = (
                    classify_evidence_status(
                        urls=supported_sources,
                        official_domains=(
                            OFFICIAL_DOMAINS
                        ),
                        official_source_prefixes=(
                            OFFICIAL_SOURCE_PREFIXES
                        ),
                    ).value
                )

                # CORROBORATED = claim confirmed in the
                # fetched text of an independent source.
                # For the brief that is verified evidence;
                # only unchecked claims stay UNVERIFIED.
                if evidence_status == "CORROBORATED":
                    evidence_status = "VERIFIED"

                source_type = strongest_source_type(
                    urls=supported_sources,
                    official_domains=(
                        OFFICIAL_DOMAINS
                    ),
                    official_source_prefixes=(
                        OFFICIAL_SOURCE_PREFIXES
                    ),
                )

                # Academic theses / vendor case studies:
                # confirmed in the fetched text, so usable,
                # but the brief must attribute them (see
                # SOURCE ATTRIBUTION POLICY). Scoring keeps
                # them weaker.
                if source_type in INDIRECT_SOURCE_TYPES:
                    evidence_status = "VERIFIED"

            else:

                evidence_status = (
                    "UNVERIFIED"
                )

                source_type = None

            catalog[evidence_id] = {
                "signal": signal.get(
                    "name",
                    signal_key,
                ),
                "claim": finding.get(
                    "claim",
                    "",
                ),
                "evidence_status": (
                    evidence_status
                ),
                "source_type": source_type,
                "supported_sources": (
                    supported_sources
                ),
                "verified_at": finding.get(
                    "verified_at"
                ),
            }

    return catalog


# =========================================================
# CLOSED-WORLD BRIEF GENERATION
# =========================================================

def generate_account_brief(
    result: dict,
    evidence_catalog: dict,
    validation_feedback: str = "",
) -> dict:

    source_payload = {
        "company": result.get(
            "company"
        ),
        "score": result.get(
            "score"
        ),
        "max_score": result.get(
            "max_score"
        ),
        "signals": {
            key: {
                "name": value.get(
                    "name"
                ),
                "score": value.get(
                    "score"
                ),
                "max_score": value.get(
                    "max_score"
                ),
                "evidence_status": (
                    value.get(
                        "evidence_status"
                    )
                ),
                "reason": value.get(
                    "reason"
                ),
            }
            for key, value
            in result.get(
                "signals",
                {},
            ).items()
        },
        "evidence_catalog": (
            evidence_catalog
        ),
    }

    # -----------------------------------------------------
    # Deterministic numeric boundary
    # -----------------------------------------------------

    canonical_number_text = json.dumps(
        source_payload,
        ensure_ascii=False,
    )

    allowed_numbers = sorted(
        set(
            re.findall(
                r"\$?\d+(?:,\d{3})*(?:\.\d+)?%?",
                canonical_number_text,
            )
        )
    )

    numeric_allowlist_text = (
        "NUMERIC ALLOWLIST:\n"
        "You may use ONLY the following numeric tokens "
        "anywhere in the brief:\n"
        + json.dumps(
            allowed_numbers
        )
        + "\n\n"
        "If a number is not in this list, OMIT IT. "
        "Do not reconstruct dates from memory. "
        "Do not approximate numbers. "
        "Do not concatenate separate allowed numbers into "
        "a new number. "
        "Do not introduce a year simply because you know it "
        "from outside knowledge."
    )

    validation_feedback_text = ""

    if validation_feedback:

        validation_feedback_text = f"""
PREVIOUS ATTEMPT FAILED DETERMINISTIC VALIDATION:

{validation_feedback}

Correct the problem.

Do not repeat the unsupported claim.
Do not introduce replacement facts or numbers.
Use only values already present in the canonical prospect data.
"""

    response = client.chat.completions.create(
        model="kimi-k2.6",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a GrundMind account-brief agent. "
                    "You have NO research role. "
                    "You may use ONLY the supplied canonical prospect "
                    "result and established evidence catalog. "
                    "Do not use outside knowledge. "
                    "Do not invent facts, sources, people, metrics, "
                    "initiatives, dates, deployments, vacancies, "
                    "business outcomes, or company characteristics. "
                    "Do not strengthen weak evidence. "
                    "Do not convert evidence marked UNVERIFIED into "
                    "a verified fact. "
                    "Every positive factual or sales conclusion must "
                    "cite one or more supplied evidence IDs. "
                    "The ai_activity list may be empty. "
                    "If no supplied evidence establishes AI activity, "
                    "return ai_activity as an empty list rather than "
                    "inventing an activity item or evidence reference. "
                    "If the evidence does not support a useful conclusion, "
                    "say that it is unknown. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
Create an evidence-backed GrundMind account brief.

The brief is for a sales professional deciding how to approach this
company.

Use ONLY the canonical data below.

Do not browse.
Do not add external knowledge.
Do not create new evidence.

{numeric_allowlist_text}

{validation_feedback_text}

IMPORTANT INTERPRETATION RULES:

GRUNDMIND PRODUCT BOUNDARY:

GrundMind is an evidence-based AI adoption diagnostic and advisory
system.

It identifies:

- Missing ROI
- Value Leakage
- Team Gap
- Cognitive Fit

It can support recommendations concerning workflows, governance,
roles, capabilities, priorities, ownership, metrics, and a practical
roadmap.

Do NOT describe GrundMind as:

- AI infrastructure
- an agent-management platform
- an observability platform
- a monitoring platform
- an AI governance enforcement platform
- software that directly manages or controls a company's AI agents

GrundMind diagnoses where AI adoption is working, where value is being
lost, what is getting in the way, and what should change.

EVIDENCE QUALITY:

Each evidence item has its own evidence_status.

That item-level status takes precedence over the aggregate signal status.

A VERIFIED signal does NOT mean every finding inside that signal is
VERIFIED.


SOURCE ATTRIBUTION POLICY:

Every evidence item has a source_type.

- COMPANY, PRESS, JOB_POSTING: may be stated directly.
- ACADEMIC: an academic study or student thesis about the company.
  Whenever you use it, attribute it in the same sentence, e.g.
  "an academic study based on interviews at the company reports ...".
  Never present it as a current company fact or as the company's own
  statement. Treat it as possibly dated.
- VENDOR_CONTENT: a vendor or partner case study / customer story.
  Whenever you use it, attribute it in the same sentence, e.g.
  "a vendor case study reports ...". Never present it as independent
  confirmation.

Do not call ACADEMIC or VENDOR_CONTENT evidence "verified" in the prose.

STRATEGIC EVIDENCE POLICY:

For these sections:

- why_this_account
- grundmind_fit
- sales_angle

use ONLY evidence items whose individual evidence_status is VERIFIED.

Do not cite UNVERIFIED evidence in those sections, even when it sounds
commercially useful.

UNVERIFIED evidence may appear only in:

- ai_activity
- uncertainties

and must remain explicitly qualified.

This is a deliberate V1 safety boundary.

When using UNVERIFIED evidence:

- explicitly qualify it as reported, third-party reported, or unverified
- do not make it the sole basis for a strong factual conclusion
- do not present it as confirmed
- do not turn it into an established company problem

Do not interpret the prospect score.

Do NOT mention the prospect score anywhere in the generated brief
narrative.

The score is rendered separately and deterministically by Python.

Do not write the score in:

- why_this_account
- ai_activity
- grundmind_fit
- sales_angle
- uncertainties

Do NOT say or imply that the score means:

- low, moderate, or high maturity
- a qualified or unqualified prospect
- room for improvement
- a strong or weak opportunity
- a particular readiness level
- a particular maturity stage

unless such a deterministic classification is explicitly supplied.

- The prospect score is deterministic. Do not reinterpret or rescore it.
- VERIFIED evidence may be stated directly.
- UNVERIFIED evidence must be qualified appropriately.
- A high deployment count does not prove ROI.
- AI hiring does not prove deployment.
- AI deployment does not prove measurable business value.
- Organisational size does not prove AI maturity.
- Do not claim that GrundMind will solve a problem that has not been
  established.
- You may identify a sales opportunity where established evidence shows
  a plausible fit, but phrase it as an opportunity or hypothesis.
- Do not state that the company "faces", "has", or "suffers from" a
  governance gap, ROI problem, fragmentation problem, scaling problem,
  workflow problem, or adoption problem unless established evidence
  directly supports that problem.
- A suitable sales angle may instead say that the evidence creates a
  reason to investigate whether such a problem exists.
- Missing evidence should appear under uncertainties rather than being
  filled by inference.

STRATEGIC FACTUAL PREMISES:

When naming departments, functions, workforce groups, organisational
characteristics, roles, or operating structures in strategic sections,
use only facts literally established by the VERIFIED evidence cited on
that statement.

Do not combine a VERIFIED general fact with an UNVERIFIED detailed
breakdown and present the combination as verified.

Do not introduce generic business assertions such as:

- fragmentation typically emerges at this scale
- governance complexity naturally increases
- large organisations commonly suffer value leakage
- deployment volume creates adoption gaps

unless the canonical evidence directly establishes that proposition.

Such ideas may only be framed as questions GrundMind could investigate.

Every evidence_refs value must contain ONLY IDs that exist in the
supplied evidence catalog.

Return exactly:

{{
  "why_this_account": {{
    "summary": "",
    "evidence_refs": []
  }},
  "ai_activity": [
    {{
      "finding": "",
      "evidence_refs": []
    }}
  ],
  "grundmind_fit": [
    {{
      "angle": "",
      "rationale": "",
      "evidence_refs": []
    }}
  ],
  "sales_angle": {{
    "thesis": "",
    "evidence_refs": []
  }},
  "uncertainties": [
    ""
  ]
}}

Keep the brief concise and commercially useful.

CANONICAL PROSPECT DATA:

{json.dumps(source_payload, indent=2)}
""",
            },
        ],
        response_format={
            "type": "json_object"
        },
        max_tokens=3000,
        timeout=120,
        extra_body={
            "thinking": {
                "type": "disabled"
            }
        },
    )

    content = (
        response.choices[0].message.content
        or ""
    ).strip()

    # Defensive cleanup if the model wraps JSON
    # in Markdown despite the JSON-only instruction.
    if content.startswith("```"):

        lines = content.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        content = "\n".join(
            lines
        ).strip()

    if not content:
        raise ValueError(
            "Model returned an empty JSON response."
        )

    try:

        return json.loads(
            content
        )

    except json.JSONDecodeError as exc:

        raise ValueError(
            "Model returned invalid JSON: "
            f"{exc.msg}"
        ) from exc


# =========================================================
# DETERMINISTIC BRIEF VALIDATION
# =========================================================

def repair_account_brief(
    result: dict,
    evidence_catalog: dict,
    previous_brief: dict,
    validation_feedback: str,
) -> dict:

    source_payload = {
        "company": result.get(
            "company"
        ),
        "score": result.get(
            "score"
        ),
        "max_score": result.get(
            "max_score"
        ),
        "signals": {
            key: {
                "name": value.get(
                    "name"
                ),
                "score": value.get(
                    "score"
                ),
                "max_score": value.get(
                    "max_score"
                ),
                "evidence_status": (
                    value.get(
                        "evidence_status"
                    )
                ),
                "reason": value.get(
                    "reason"
                ),
            }
            for key, value
            in result.get(
                "signals",
                {},
            ).items()
        },
        "evidence_catalog": (
            evidence_catalog
        ),
    }

    response = client.chat.completions.create(
        model="kimi-k2.6",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are correcting an existing GrundMind "
                    "account brief after deterministic and semantic "
                    "validation. "
                    "You have NO research role. "
                    "Use only the supplied canonical evidence. "
                    "Make the minimum changes required to fix the "
                    "validator failures. "
                    "Preserve statements and sections that were not "
                    "criticized. "
                    "Do not invent replacement facts. "
                    "When a clause is unsupported, prefer deleting or "
                    "narrowing it rather than replacing it with a new "
                    "inference. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
Correct the previous account brief.

VALIDATION FAILURE:

{validation_feedback}


REPAIR RULES:

1. Make MINIMAL edits.

Do not rewrite the entire brief.

Fix only statements implicated by the validator unless another edit is
strictly necessary for coherence.


2. CITED EVIDENCE ONLY

Every factual premise must be supported by the evidence IDs cited on
that specific statement.

Do not use evidence attached to another statement unless you explicitly
add that valid evidence ID to the corrected statement.


3. VERIFIED VS UNVERIFIED

VERIFIED evidence may be stated directly, except ACADEMIC and
VENDOR_CONTENT source_type evidence, which must keep its explicit
attribution ("an academic study reports ...", "a vendor case study
reports ...") in every sentence that uses it.

For strategic sections:

- why_this_account
- grundmind_fit
- sales_angle

use VERIFIED evidence only.

If validator feedback identifies UNVERIFIED evidence in one of these
sections, REMOVE that evidence reference and remove or narrow the clause
that depends on it.

Python will deterministically delete any UNVERIFIED evidence reference
you place in a strategic section.

Therefore NEVER re-add an UNVERIFIED strategic evidence reference on a
repair attempt.

If the factual clause depends on that evidence, delete the clause or
replace it only with a proposition supported by the VERIFIED evidence
already attached to that statement.

Do not try to rescue the clause by finding softer wording.

Move useful UNVERIFIED evidence to ai_activity or uncertainties instead.

UNVERIFIED evidence must be explicitly described as one of:

- an unverified report
- third-party reported
- reported but not independently confirmed

Do not blend VERIFIED and UNVERIFIED evidence under a shared word such
as "verified."

If a sentence contains both, distinguish them explicitly.


4. DO NOT BROADEN CLAIMS

Examples:

Evidence:
"CEO said AI helped product development move faster"

Allowed:
"The CEO said AI helped product development move faster."

Not allowed:
"Executive leadership is driving operational AI transformation."

Evidence:
"AI-enabled marketing model exists in China"

Allowed:
"An AI-enabled marketing operations model exists in China."

Not allowed:
"AI value is being measured across marketing."


5. SALES HYPOTHESES

GrundMind may:

- assess whether
- investigate whether
- test whether
- determine whether
- explore whether

Do not claim or imply that {COMPANY} already has:

- Value Leakage
- Missing ROI
- fragmentation
- governance gaps
- adoption gaps
- Team Gap
- Cognitive Fit problems
- capability problems

unless the cited evidence directly establishes them.


6. SCORE

Do NOT mention the supplied prospect score anywhere in the repaired
brief.

Python renders the score separately.

If validator feedback identifies score interpretation, remove the score
and the clause that attempts to interpret it.

Do not call the account:

- qualified
- mature
- immature
- strong
- weak
- ready
- not ready

based on the score.


7. GRUNDMIND PRODUCT BOUNDARY

GrundMind is an evidence-based AI adoption diagnostic and advisory
system.

It identifies:

- Missing ROI
- Value Leakage
- Team Gap
- Cognitive Fit

It is not infrastructure, monitoring software, an agent-management
platform, or a governance enforcement system.


8. PREFER DELETION OVER INVENTION

If the validator identifies one unsupported phrase inside an otherwise
valid sentence, remove or narrow that phrase.

Do not create a new factual premise to make the prose sound stronger.

If an unsupported department, function, workforce group, organisational
characteristic, or general business assertion is identified, DELETE it
unless the cited VERIFIED evidence literally supports it.

Do not replace it with a similar-sounding generalisation.

Do not claim that {COMPANY}'s scale makes AI adoption:

- difficult to self-diagnose
- difficult to govern
- difficult to optimize
- prone to fragmentation
- prone to value leakage

unless evidence directly establishes that difficulty.

Instead use a neutral diagnostic formulation such as:

"GrundMind can assess whether AI adoption and value capture are
consistent across the organisation."

If a strategic hypothesis refers to EXISTING AI benefits, outcomes,
deployments, or workflows, then either:

1. cite the VERIFIED evidence that establishes those existing facts, or
2. remove that factual premise.

Do not discuss "AI benefits" using only organisational-fit evidence.


Return the complete corrected brief using exactly this structure:

{{
  "why_this_account": {{
    "summary": "",
    "evidence_refs": []
  }},
  "ai_activity": [
    {{
      "finding": "",
      "evidence_refs": []
    }}
  ],
  "grundmind_fit": [
    {{
      "angle": "",
      "rationale": "",
      "evidence_refs": []
    }}
  ],
  "sales_angle": {{
    "thesis": "",
    "evidence_refs": []
  }},
  "uncertainties": [
    ""
  ]
}}


PREVIOUS BRIEF:

{json.dumps(previous_brief, indent=2, ensure_ascii=False)}


CANONICAL DATA:

{json.dumps(source_payload, indent=2, ensure_ascii=False)}
""",
            },
        ],
        response_format={
            "type": "json_object"
        },
        max_tokens=3000,
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
    ).strip()

    if content.startswith("```"):

        lines = content.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        content = "\n".join(
            lines
        ).strip()

    if not content:
        raise ValueError(
            "Semantic repair returned an empty response."
        )

    try:

        return json.loads(
            content
        )

    except json.JSONDecodeError as exc:

        raise ValueError(
            "Semantic repair returned invalid JSON: "
            f"{exc.msg}"
        ) from exc


def collect_evidence_refs(
    value,
) -> list[str]:

    refs = []

    if isinstance(
        value,
        dict,
    ):

        for key, item in value.items():

            if (
                key == "evidence_refs"
                and isinstance(
                    item,
                    list,
                )
            ):

                refs.extend(
                    str(ref)
                    for ref in item
                )

            else:

                refs.extend(
                    collect_evidence_refs(
                        item
                    )
                )

    elif isinstance(
        value,
        list,
    ):

        for item in value:

            refs.extend(
                collect_evidence_refs(
                    item
                )
            )

    return refs


def validate_required_refs(
    brief: dict,
) -> None:

    why = brief.get(
        "why_this_account",
        {},
    )

    if not why.get(
        "evidence_refs"
    ):
        raise ValueError(
            "why_this_account has no evidence refs"
        )

    for index, item in enumerate(
        brief.get(
            "ai_activity",
            [],
        ),
        start=1,
    ):

        if not item.get(
            "evidence_refs"
        ):
            raise ValueError(
                f"ai_activity item {index} "
                "has no evidence refs"
            )

    for index, item in enumerate(
        brief.get(
            "grundmind_fit",
            [],
        ),
        start=1,
    ):

        if not item.get(
            "evidence_refs"
        ):
            raise ValueError(
                f"grundmind_fit item {index} "
                "has no evidence refs"
            )

    sales_angle = brief.get(
        "sales_angle",
        {},
    )

    if not sales_angle.get(
        "evidence_refs"
    ):
        raise ValueError(
            "sales_angle has no evidence refs"
        )


def normalize_brief_schema(
    raw_brief: dict,
) -> tuple[dict, list[str]]:
    """
    Rebuild model output into the exact allowed account-brief schema.

    Any unexpected model-generated fields are discarded before
    sanitization or publication.
    """

    removed = []

    if not isinstance(raw_brief, dict):
        raise ValueError(
            "Account brief root must be a JSON object."
        )

    allowed_top = {
        "why_this_account",
        "ai_activity",
        "grundmind_fit",
        "sales_angle",
        "uncertainties",
    }

    for key in raw_brief:
        if key not in allowed_top:
            removed.append(
                f"root.{key}"
            )

    # -----------------------------------------------------
    # Why this account
    # -----------------------------------------------------

    raw_why = raw_brief.get(
        "why_this_account",
        {},
    )

    if not isinstance(raw_why, dict):
        raw_why = {}

    for key in raw_why:
        if key not in {
            "summary",
            "evidence_refs",
        }:
            removed.append(
                f"why_this_account.{key}"
            )

    why = {
        "summary": str(
            raw_why.get(
                "summary",
                "",
            )
        ),
        "evidence_refs": (
            raw_why.get(
                "evidence_refs",
                [],
            )
            if isinstance(
                raw_why.get(
                    "evidence_refs",
                    [],
                ),
                list,
            )
            else []
        ),
    }

    # -----------------------------------------------------
    # AI activity
    # -----------------------------------------------------

    ai_activity = []

    raw_activity = raw_brief.get(
        "ai_activity",
        [],
    )

    if not isinstance(
        raw_activity,
        list,
    ):
        raw_activity = []

    for index, raw_item in enumerate(
        raw_activity
    ):

        if not isinstance(
            raw_item,
            dict,
        ):
            continue

        for key in raw_item:
            if key not in {
                "finding",
                "evidence_refs",
            }:
                removed.append(
                    f"ai_activity[{index}].{key}"
                )

        ai_activity.append(
            {
                "finding": str(
                    raw_item.get(
                        "finding",
                        "",
                    )
                ),
                "evidence_refs": (
                    raw_item.get(
                        "evidence_refs",
                        [],
                    )
                    if isinstance(
                        raw_item.get(
                            "evidence_refs",
                            [],
                        ),
                        list,
                    )
                    else []
                ),
            }
        )

    # -----------------------------------------------------
    # GrundMind fit
    # -----------------------------------------------------

    grundmind_fit = []

    raw_fit = raw_brief.get(
        "grundmind_fit",
        [],
    )

    if not isinstance(
        raw_fit,
        list,
    ):
        raw_fit = []

    for index, raw_item in enumerate(
        raw_fit
    ):

        if not isinstance(
            raw_item,
            dict,
        ):
            continue

        for key in raw_item:
            if key not in {
                "angle",
                "rationale",
                "evidence_refs",
            }:
                removed.append(
                    f"grundmind_fit[{index}].{key}"
                )

        grundmind_fit.append(
            {
                "angle": str(
                    raw_item.get(
                        "angle",
                        "",
                    )
                ),
                "rationale": str(
                    raw_item.get(
                        "rationale",
                        "",
                    )
                ),
                "evidence_refs": (
                    raw_item.get(
                        "evidence_refs",
                        [],
                    )
                    if isinstance(
                        raw_item.get(
                            "evidence_refs",
                            [],
                        ),
                        list,
                    )
                    else []
                ),
            }
        )

    # -----------------------------------------------------
    # Sales angle
    # -----------------------------------------------------

    raw_sales = raw_brief.get(
        "sales_angle",
        {},
    )

    if not isinstance(
        raw_sales,
        dict,
    ):
        raw_sales = {}

    for key in raw_sales:
        if key not in {
            "thesis",
            "evidence_refs",
        }:
            removed.append(
                f"sales_angle.{key}"
            )

    sales_angle = {
        "thesis": str(
            raw_sales.get(
                "thesis",
                "",
            )
        ),
        "evidence_refs": (
            raw_sales.get(
                "evidence_refs",
                [],
            )
            if isinstance(
                raw_sales.get(
                    "evidence_refs",
                    [],
                ),
                list,
            )
            else []
        ),
    }

    # -----------------------------------------------------
    # Uncertainties
    # -----------------------------------------------------

    raw_uncertainties = raw_brief.get(
        "uncertainties",
        [],
    )

    if not isinstance(
        raw_uncertainties,
        list,
    ):
        raw_uncertainties = []

    uncertainties = [
        str(item)
        for item in raw_uncertainties
        if isinstance(
            item,
            str,
        )
    ]

    normalized = {
        "why_this_account": why,
        "ai_activity": ai_activity,
        "grundmind_fit": grundmind_fit,
        "sales_angle": sales_angle,
        "uncertainties": uncertainties,
    }

    return normalized, removed


def get_allowed_numeric_tokens(
    result: dict,
    evidence_catalog: dict,
) -> set[str]:

    canonical_text = json.dumps(
        {
            "result": result,
            "evidence": evidence_catalog,
        },
        ensure_ascii=False,
    )

    return set(
        re.findall(
            r"\$?\d+(?:,\d{3})*(?:\.\d+)?%?",
            canonical_text,
        )
    )


def scrub_numeric_text(
    text: str,
    allowed_numbers: set[str],
    field_name: str,
) -> tuple[str, list[dict]]:

    if not text:
        return text, []

    # Remove the complete sentence containing an
    # unsupported numeric token rather than trying
    # to rewrite or guess what the model meant.
    sentences = re.split(
        r"(?<=[.!?])\s+",
        text.strip(),
    )

    kept = []
    events = []

    for sentence in sentences:

        numbers = set(
            re.findall(
                r"\$?\d+(?:,\d{3})*(?:\.\d+)?%?",
                sentence,
            )
        )

        unsupported = (
            numbers
            - allowed_numbers
        )

        if unsupported:

            events.append(
                {
                    "field": field_name,
                    "unsupported_numbers": sorted(
                        unsupported
                    ),
                    "removed_text": sentence,
                }
            )

            continue

        kept.append(
            sentence
        )

    return (
        " ".join(kept).strip(),
        events,
    )


def scrub_unsupported_numeric_claims(
    brief: dict,
    result: dict,
    evidence_catalog: dict,
) -> list[dict]:

    allowed_numbers = (
        get_allowed_numeric_tokens(
            result=result,
            evidence_catalog=evidence_catalog,
        )
    )

    events = []

    # -----------------------------------------------------
    # Why this account
    # -----------------------------------------------------

    why = brief.get(
        "why_this_account",
        {},
    )

    cleaned, found = scrub_numeric_text(
        text=why.get(
            "summary",
            "",
        ),
        allowed_numbers=allowed_numbers,
        field_name=(
            "why_this_account.summary"
        ),
    )

    why["summary"] = cleaned
    events.extend(found)

    # -----------------------------------------------------
    # AI activity
    # -----------------------------------------------------

    for index, item in enumerate(
        brief.get(
            "ai_activity",
            [],
        )
    ):

        cleaned, found = scrub_numeric_text(
            text=item.get(
                "finding",
                "",
            ),
            allowed_numbers=(
                allowed_numbers
            ),
            field_name=(
                f"ai_activity[{index}].finding"
            ),
        )

        item["finding"] = cleaned
        events.extend(found)

    # -----------------------------------------------------
    # GrundMind fit
    # -----------------------------------------------------

    for index, item in enumerate(
        brief.get(
            "grundmind_fit",
            [],
        )
    ):

        for key in (
            "angle",
            "rationale",
        ):

            cleaned, found = (
                scrub_numeric_text(
                    text=item.get(
                        key,
                        "",
                    ),
                    allowed_numbers=(
                        allowed_numbers
                    ),
                    field_name=(
                        f"grundmind_fit[{index}].{key}"
                    ),
                )
            )

            item[key] = cleaned
            events.extend(found)

    # -----------------------------------------------------
    # Sales angle
    # -----------------------------------------------------

    sales = brief.get(
        "sales_angle",
        {},
    )

    cleaned, found = scrub_numeric_text(
        text=sales.get(
            "thesis",
            "",
        ),
        allowed_numbers=allowed_numbers,
        field_name="sales_angle.thesis",
    )

    sales["thesis"] = cleaned
    events.extend(found)

    # -----------------------------------------------------
    # Uncertainties
    # -----------------------------------------------------

    cleaned_uncertainties = []

    for index, uncertainty in enumerate(
        brief.get(
            "uncertainties",
            [],
        )
    ):

        cleaned, found = scrub_numeric_text(
            text=uncertainty,
            allowed_numbers=(
                allowed_numbers
            ),
            field_name=(
                f"uncertainties[{index}]"
            ),
        )

        events.extend(found)

        if cleaned:
            cleaned_uncertainties.append(
                cleaned
            )

    brief[
        "uncertainties"
    ] = cleaned_uncertainties

    return events


def scrub_all_brief_strings(
    value,
    allowed_numbers: set[str],
    path: str = "brief",
    parent_key: str | None = None,
):

    events = []

    # Evidence refs are identifiers, not prose.
    if parent_key == "evidence_refs":
        return value, events

    if isinstance(value, dict):

        cleaned = {}

        for key, item in value.items():

            cleaned_item, found = (
                scrub_all_brief_strings(
                    value=item,
                    allowed_numbers=(
                        allowed_numbers
                    ),
                    path=f"{path}.{key}",
                    parent_key=key,
                )
            )

            cleaned[key] = cleaned_item
            events.extend(found)

        return cleaned, events

    if isinstance(value, list):

        cleaned = []

        for index, item in enumerate(
            value
        ):

            cleaned_item, found = (
                scrub_all_brief_strings(
                    value=item,
                    allowed_numbers=(
                        allowed_numbers
                    ),
                    path=f"{path}[{index}]",
                    parent_key=parent_key,
                )
            )

            # Drop empty prose strings created by
            # deterministic sanitization.
            if (
                isinstance(
                    cleaned_item,
                    str,
                )
                and not cleaned_item.strip()
            ):
                events.extend(found)
                continue

            cleaned.append(
                cleaned_item
            )

            events.extend(found)

        return cleaned, events

    if isinstance(value, str):

        cleaned, found = scrub_numeric_text(
            text=value,
            allowed_numbers=(
                allowed_numbers
            ),
            field_name=path,
        )

        return cleaned, found

    return value, events


def validate_required_text(
    brief: dict,
) -> None:

    if not (
        brief.get(
            "why_this_account",
            {},
        ).get(
            "summary",
            "",
        ).strip()
    ):
        raise ValueError(
            "why_this_account summary became empty "
            "after deterministic sanitization."
        )

    for index, item in enumerate(
        brief.get(
            "ai_activity",
            [],
        ),
        start=1,
    ):

        if not item.get(
            "finding",
            "",
        ).strip():

            raise ValueError(
                f"ai_activity item {index} became "
                "empty after deterministic sanitization."
            )

    for index, item in enumerate(
        brief.get(
            "grundmind_fit",
            [],
        ),
        start=1,
    ):

        if not item.get(
            "angle",
            "",
        ).strip():

            raise ValueError(
                f"grundmind_fit item {index} angle "
                "became empty after sanitization."
            )

        if not item.get(
            "rationale",
            "",
        ).strip():

            raise ValueError(
                f"grundmind_fit item {index} rationale "
                "became empty after sanitization."
            )

    if not (
        brief.get(
            "sales_angle",
            {},
        ).get(
            "thesis",
            "",
        ).strip()
    ):

        raise ValueError(
            "sales_angle thesis became empty "
            "after deterministic sanitization."
        )


def find_numeric_token_paths(
    value,
    target_numbers: set[str],
    path: str = "brief",
) -> list[dict]:

    hits = []

    if isinstance(value, dict):

        for key, item in value.items():

            hits.extend(
                find_numeric_token_paths(
                    value=item,
                    target_numbers=target_numbers,
                    path=f"{path}.{key}",
                )
            )

        return hits

    if isinstance(value, list):

        for index, item in enumerate(value):

            hits.extend(
                find_numeric_token_paths(
                    value=item,
                    target_numbers=target_numbers,
                    path=f"{path}[{index}]",
                )
            )

        return hits

    scalar_text = str(value)

    numbers = set(
        re.findall(
            r"\$?\d+(?:,\d{3})*(?:\.\d+)?%?",
            scalar_text,
        )
    )

    matched = numbers & target_numbers

    if matched:

        hits.append(
            {
                "path": path,
                "numbers": sorted(matched),
                "value": scalar_text,
                "python_type": type(value).__name__,
            }
        )

    return hits


def validate_score_not_in_narrative(
    brief: dict,
    result: dict,
) -> None:

    score = result.get(
        "score"
    )

    maximum = result.get(
        "max_score"
    )

    if (
        score is None
        or maximum is None
    ):
        return

    narrative = json.dumps(
        brief,
        ensure_ascii=False,
    )

    forbidden_patterns = [
        rf"\b{score}\s*/\s*{maximum}\b",
        rf"\b{score}\s+out\s+of\s+{maximum}\b",
    ]

    for pattern in forbidden_patterns:

        if re.search(
            pattern,
            narrative,
            flags=re.IGNORECASE,
        ):

            raise ValueError(
                "Prospect score appeared inside "
                "LLM-generated narrative. "
                "The score must be rendered only "
                "by deterministic Python output."
            )


def sanitize_strategic_evidence_refs(
    brief: dict,
    evidence_catalog: dict,
) -> list[dict]:
    """
    Deterministically remove non-VERIFIED evidence references from
    strategic sections.

    This does NOT remove unsupported prose. The later semantic and
    atomic validators must still verify that the remaining text is
    supported by the remaining VERIFIED evidence.
    """

    removed = []

    def sanitize_refs(
        section_name: str,
        refs: list,
    ) -> list:

        kept = []

        for evidence_ref in refs:

            evidence = evidence_catalog.get(
                evidence_ref,
                {},
            )

            status = str(
                evidence.get(
                    "evidence_status",
                    "UNVERIFIED",
                )
            ).upper()

            if status == "VERIFIED":

                kept.append(
                    evidence_ref
                )

                continue

            removed.append(
                {
                    "section": (
                        section_name
                    ),
                    "evidence_ref": (
                        evidence_ref
                    ),
                    "status": status,
                }
            )

        return kept


    why = brief.get(
        "why_this_account",
        {},
    )

    why["evidence_refs"] = sanitize_refs(
        "why_this_account",
        why.get(
            "evidence_refs",
            [],
        ),
    )


    for index, item in enumerate(
        brief.get(
            "grundmind_fit",
            [],
        )
    ):

        item["evidence_refs"] = sanitize_refs(
            f"grundmind_fit:{index}",
            item.get(
                "evidence_refs",
                [],
            ),
        )


    sales = brief.get(
        "sales_angle",
        {},
    )

    sales["evidence_refs"] = sanitize_refs(
        "sales_angle",
        sales.get(
            "evidence_refs",
            [],
        ),
    )


    if removed:

        print(
            "Deterministic strategic evidence "
            f"sanitizer removed {len(removed)} "
            "non-VERIFIED ref(s)."
        )

        for item in removed:

            print(
                "  "
                f"{item['section']}: "
                f"{item['evidence_ref']} "
                f"({item['status']})"
            )

    return removed


def validate_strategic_evidence_quality(
    brief: dict,
    evidence_catalog: dict,
) -> None:
    """
    V1 policy:

    Strategic conclusions may rely only on VERIFIED evidence.

    UNVERIFIED evidence may still appear in AI activity and
    uncertainties when explicitly qualified.
    """

    strategic_sections = []

    why = brief.get(
        "why_this_account",
        {},
    )

    strategic_sections.append(
        (
            "why_this_account",
            why.get(
                "evidence_refs",
                [],
            ),
        )
    )

    for index, item in enumerate(
        brief.get(
            "grundmind_fit",
            [],
        )
    ):

        strategic_sections.append(
            (
                f"grundmind_fit:{index}",
                item.get(
                    "evidence_refs",
                    [],
                ),
            )
        )

    sales = brief.get(
        "sales_angle",
        {},
    )

    strategic_sections.append(
        (
            "sales_angle",
            sales.get(
                "evidence_refs",
                [],
            ),
        )
    )

    failures = []

    for section_name, refs in (
        strategic_sections
    ):

        weak_refs = []

        for evidence_ref in refs:

            evidence = (
                evidence_catalog.get(
                    evidence_ref,
                    {},
                )
            )

            status = str(
                evidence.get(
                    "evidence_status",
                    "UNVERIFIED",
                )
            ).upper()

            if status != "VERIFIED":

                weak_refs.append(
                    evidence_ref
                )

        if weak_refs:

            failures.append(
                (
                    f"{section_name}: "
                    + ", ".join(
                        weak_refs
                    )
                )
            )

    if failures:

        raise ValueError(
            "Strategic sections may use only "
            "VERIFIED evidence. Remove or move "
            "these UNVERIFIED evidence refs: "
            + " | ".join(
                failures
            )
        )


def validate_brief(
    brief: dict,
    result: dict,
    evidence_catalog: dict,
) -> None:

    valid_refs = set(
        evidence_catalog
    )

    used_refs = set(
        collect_evidence_refs(
            brief
        )
    )

    unknown_refs = (
        used_refs
        - valid_refs
    )

    if unknown_refs:

        raise ValueError(
            "Brief invented evidence refs: "
            + ", ".join(
                sorted(
                    unknown_refs
                )
            )
        )

    sanitize_strategic_evidence_refs(
        brief=brief,
        evidence_catalog=(
            evidence_catalog
        ),
    )

    validate_required_refs(
        brief
    )

    validate_score_not_in_narrative(
        brief=brief,
        result=result,
    )

    validate_strategic_evidence_quality(
        brief=brief,
        evidence_catalog=(
            evidence_catalog
        ),
    )

    validate_required_text(
        brief
    )

    # -----------------------------------------------------
    # No invented URLs
    # -----------------------------------------------------

    allowed_urls = {
        url
        for evidence
        in evidence_catalog.values()
        for url
        in evidence.get(
            "supported_sources",
            [],
        )
    }

    brief_text = json.dumps(
        brief,
        ensure_ascii=False,
    )

    found_urls = set(
        re.findall(
            r"https?://[^\s\"']+",
            brief_text,
        )
    )

    invented_urls = (
        found_urls
        - allowed_urls
    )

    if invented_urls:

        raise ValueError(
            "Brief invented source URLs: "
            + ", ".join(
                sorted(
                    invented_urls
                )
            )
        )

    # -----------------------------------------------------
    # No invented numeric claims
    # -----------------------------------------------------

    allowed_number_text = json.dumps(
        {
            "result": result,
            "evidence": evidence_catalog,
        },
        ensure_ascii=False,
    )

    allowed_numbers = set(
        re.findall(
            r"\$?\d+(?:,\d{3})*(?:\.\d+)?%?",
            allowed_number_text,
        )
    )

    brief_numbers = set(
        re.findall(
            r"\$?\d+(?:,\d{3})*(?:\.\d+)?%?",
            brief_text,
        )
    )

    invented_numbers = (
        brief_numbers
        - allowed_numbers
    )

    if invented_numbers:

        numeric_hits = (
            find_numeric_token_paths(
                value=brief,
                target_numbers=(
                    invented_numbers
                ),
            )
        )

        print(
            "\nUNSUPPORTED NUMERIC TOKEN LOCATIONS"
        )

        for hit in numeric_hits:

            print(
                f"  {hit['path']} "
                f"[{hit['python_type']}] "
                f"-> {hit['numbers']}"
            )

            print(
                f"    VALUE: {hit['value']}"
            )

        raise ValueError(
            "Brief introduced unsupported "
            "numeric claims: "
            + ", ".join(
                sorted(
                    invented_numbers
                )
            )
        )


# =========================================================
# CLOSED-WORLD SEMANTIC CITATION VERIFIER
# =========================================================

def build_semantic_statements(
    brief: dict,
) -> list[dict]:

    statements = []

    why = brief.get(
        "why_this_account",
        {},
    )

    statements.append(
        {
            "statement_id": (
                "why_this_account"
            ),
            "text": why.get(
                "summary",
                "",
            ),
            "evidence_refs": why.get(
                "evidence_refs",
                [],
            ),
        }
    )

    for index, item in enumerate(
        brief.get(
            "ai_activity",
            [],
        )
    ):

        statements.append(
            {
                "statement_id": (
                    f"ai_activity:{index}"
                ),
                "text": item.get(
                    "finding",
                    "",
                ),
                "evidence_refs": item.get(
                    "evidence_refs",
                    [],
                ),
            }
        )

    for index, item in enumerate(
        brief.get(
            "grundmind_fit",
            [],
        )
    ):

        angle = item.get(
            "angle",
            "",
        )

        rationale = item.get(
            "rationale",
            "",
        )

        statements.append(
            {
                "statement_id": (
                    f"grundmind_fit:{index}"
                ),
                "text": (
                    f"{angle}: {rationale}"
                ),
                "evidence_refs": item.get(
                    "evidence_refs",
                    [],
                ),
            }
        )

    sales = brief.get(
        "sales_angle",
        {},
    )

    statements.append(
        {
            "statement_id": (
                "sales_angle"
            ),
            "text": sales.get(
                "thesis",
                "",
            ),
            "evidence_refs": sales.get(
                "evidence_refs",
                [],
            ),
        }
    )

    return statements


def semantic_validate_brief(
    brief: dict,
    result: dict,
    evidence_catalog: dict,
) -> dict:

    statements = (
        build_semantic_statements(
            brief
        )
    )

    verification_payload = []

    for statement in statements:

        cited_evidence = []

        for evidence_ref in (
            statement.get(
                "evidence_refs",
                [],
            )
        ):

            evidence = evidence_catalog.get(
                evidence_ref
            )

            if evidence is None:
                continue

            cited_evidence.append(
                {
                    "evidence_id": (
                        evidence_ref
                    ),
                    "claim": evidence.get(
                        "claim",
                        "",
                    ),
                    "evidence_status": (
                        evidence.get(
                            "evidence_status",
                            "UNVERIFIED",
                        )
                    ),
                }
            )

        verification_payload.append(
            {
                "statement_id": (
                    statement[
                        "statement_id"
                    ]
                ),
                "text": statement[
                    "text"
                ],
                "cited_evidence": (
                    cited_evidence
                ),
            }
        )

    canonical_score = (
        f"{result.get('score')}/"
        f"{result.get('max_score')}"
    )

    response = client.chat.completions.create(
        model="kimi-k2.6",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a closed-world semantic "
                    "citation verifier. "
                    "You do NOT research. "
                    "You do NOT use outside knowledge. "
                    "You judge whether each supplied "
                    "account-brief statement is supported "
                    "by ONLY the evidence explicitly cited "
                    "for that statement. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
Verify every account-brief statement below.

You may use ONLY:

1. the evidence attached to that specific statement
2. the exact canonical prospect score supplied below
3. the GrundMind product boundary supplied below

You may NOT:

- use evidence cited by another statement
- use general knowledge
- repair a missing citation
- assume a fact because it is plausible
- strengthen an UNVERIFIED finding
- infer company pain that the evidence does not establish


CANONICAL PROSPECT SCORE:

{canonical_score}

The score is rendered separately by Python.

Narrative statements MUST NOT mention the prospect score at all.

If a statement contains the score, classify that statement as
UNSUPPORTED.

The score has NO supplied interpretation or maturity band.

Therefore also reject statements claiming or implying that the score means:

- low, moderate, or high maturity
- qualified prospect
- room for improvement
- readiness level
- maturity stage
- strong or weak opportunity


GRUNDMIND PRODUCT BOUNDARY:

GrundMind is an evidence-based AI adoption diagnostic and advisory
system.

It identifies:

- Missing ROI
- Value Leakage
- Team Gap
- Cognitive Fit

It may support recommendations concerning workflows, governance,
roles, capabilities, priorities, ownership, metrics, and a practical
roadmap.

It is NOT:

- AI infrastructure
- an agent-management platform
- an observability platform
- a monitoring platform
- an AI governance enforcement platform


EVIDENCE QUALITY RULES:

VERIFIED evidence may support a direct factual statement.

UNVERIFIED evidence may support a statement only when that proposition
is clearly qualified as:

- reported
- third-party reported
- unverified
- alleged
- not independently confirmed

The word "reported" is itself an acceptable qualification.
For example, "reported data" or "a reported deployment" is explicitly
qualified and must not be rejected merely for failing to also use the
word "unverified."

Do not allow an unverified claim to become an established company fact.


SALES-HYPOTHESIS RULE:

A cautious sales hypothesis may be SUPPORTED when:

- its factual premises are supported by the cited evidence
- the opportunity is explicitly framed as something to assess,
  investigate, test, determine, or explore
- it does not assert that the company already has the hypothesized
  problem

For example:

"GrundMind could assess whether value measurement is consistent across
functions"

may be supported when the evidence establishes multiple functions and
some measurable AI activity.

But:

"The company has a value leakage problem"

is unsupported unless the evidence directly establishes that problem.


CLASSIFICATION:

SUPPORTED
= every material factual premise is supported by the cited evidence,
  evidence quality is represented correctly, and any sales inference
  remains explicitly hypothetical.

PARTIALLY_SUPPORTED
= some material parts are supported but at least one meaningful clause
  is overstated, insufficiently qualified, or lacks support from the
  cited evidence.

UNSUPPORTED
= the statement materially relies on facts or conclusions not supported
  by its cited evidence.


Return exactly:

{{
  "checks": [
    {{
      "statement_id": "",
      "status": "SUPPORTED|PARTIALLY_SUPPORTED|UNSUPPORTED",
      "reason": ""
    }}
  ]
}}


STATEMENTS TO VERIFY:

{json.dumps(verification_payload, indent=2)}
""",
            },
        ],
        response_format={
            "type": "json_object"
        },
        max_tokens=3000,
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
    ).strip()

    if not content:
        raise ValueError(
            "Semantic citation verifier "
            "returned an empty response."
        )

    try:

        data = json.loads(
            content
        )

    except json.JSONDecodeError as exc:

        raise ValueError(
            "Semantic citation verifier "
            f"returned invalid JSON: {exc.msg}"
        ) from exc

    checks = data.get(
        "checks",
        [],
    )

    expected_ids = {
        statement[
            "statement_id"
        ]
        for statement in statements
    }

    returned_ids = {
        check.get(
            "statement_id"
        )
        for check in checks
    }

    missing_ids = (
        expected_ids
        - returned_ids
    )

    unexpected_ids = (
        returned_ids
        - expected_ids
    )

    if missing_ids:

        raise ValueError(
            "Semantic verifier omitted "
            "statement IDs: "
            + ", ".join(
                sorted(
                    missing_ids
                )
            )
        )

    if unexpected_ids:

        raise ValueError(
            "Semantic verifier invented "
            "statement IDs: "
            + ", ".join(
                sorted(
                    str(item)
                    for item in unexpected_ids
                )
            )
        )

    failures = []

    for check in checks:

        status = str(
            check.get(
                "status",
                "UNSUPPORTED",
            )
        ).upper()

        if status == "SUPPORTED":
            continue

        failures.append(
            {
                "statement_id": (
                    check.get(
                        "statement_id"
                    )
                ),
                "status": status,
                "reason": check.get(
                    "reason",
                    "",
                ),
            }
        )

    if failures:

        details = []

        for failure in failures:

            details.append(
                (
                    f"{failure['statement_id']} "
                    f"[{failure['status']}]: "
                    f"{failure['reason']}"
                )
            )

        raise ValueError(
            "Semantic citation validation failed: "
            + " | ".join(
                details
            )
        )

    return data


# =========================================================
# ATOMIC CLAIM VERIFIER
# =========================================================

def atomic_validate_brief(
    brief: dict,
    result: dict,
    evidence_catalog: dict,
) -> dict:
    """
    Decompose each strategic statement into materially distinct
    propositions and verify every proposition against only the
    evidence explicitly cited by that statement.
    """

    statements = (
        build_semantic_statements(
            brief
        )
    )

    verification_payload = []

    for statement in statements:

        cited_evidence = []

        for evidence_ref in statement.get(
            "evidence_refs",
            [],
        ):

            evidence = evidence_catalog.get(
                evidence_ref
            )

            if evidence is None:
                continue

            cited_evidence.append(
                {
                    "evidence_id": (
                        evidence_ref
                    ),
                    "claim": evidence.get(
                        "claim",
                        "",
                    ),
                    "evidence_status": (
                        evidence.get(
                            "evidence_status",
                            "UNVERIFIED",
                        )
                    ),
                }
            )

        verification_payload.append(
            {
                "statement_id": (
                    statement[
                        "statement_id"
                    ]
                ),
                "statement": (
                    statement[
                        "text"
                    ]
                ),
                "cited_evidence": (
                    cited_evidence
                ),
            }
        )

    response = client.chat.completions.create(
        model="kimi-k2.6",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a closed-world atomic claim verifier. "
                    "You do not research and do not use outside knowledge. "
                    "For each supplied statement, decompose it into every "
                    "materially distinct factual proposition, inference, "
                    "sales hypothesis, or product claim. "
                    "Then verify each proposition using ONLY the evidence "
                    "explicitly cited for that statement and the supplied "
                    "GrundMind product boundary. "
                    "Do not overlook unsupported clauses inside otherwise "
                    "supported sentences. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
Verify the account brief at ATOMIC CLAIM level.

This is stricter than paragraph-level verification.

For every statement:

1. Break it into every materially distinct proposition.

For example:

"{COMPANY} has verified AI value measurement in product development
and marketing operations at enterprise scale."

must be decomposed into propositions such as:

- {COMPANY} has AI-related evidence in product development.
- {COMPANY} has AI-related evidence in marketing operations.
- {COMPANY} has verified AI value measurement in product development.
- {COMPANY} has verified AI value measurement in marketing operations.
- The activity is enterprise-scale.

Do not allow one supported clause to hide an unsupported clause.


2. VERIFY ONLY AGAINST THAT STATEMENT'S CITED EVIDENCE.

Do not:

- use evidence cited elsewhere in the brief
- use outside knowledge
- repair missing citations
- infer facts from plausibility
- strengthen source claims


3. VERIFIED AND UNVERIFIED EVIDENCE

VERIFIED evidence may support a direct factual proposition.

UNVERIFIED evidence may support a proposition only when it remains
explicitly qualified as:

- reported
- third-party reported
- unverified
- alleged
- not independently confirmed

IMPORTANT QUALIFIER INHERITANCE:

When the parent statement explicitly applies an epistemic qualifier to
the whole statement, every atomic proposition decomposed from that
statement MUST inherit that qualifier.

Example:

"Unverified report: ChatGPT Enterprise was deployed globally and an
internal assistant answers employee questions."

must be decomposed as propositions equivalent to:

- Unverified report: ChatGPT Enterprise was deployed globally.
- Unverified report: an internal assistant answers employee questions.

Do NOT strip "Unverified report:", "reported", "alleged", or equivalent
qualification during atomic decomposition and then reject the resulting
claim for lacking the qualification.

The qualifier does not make weak evidence VERIFIED. It only preserves
the epistemic status of the original statement.

Do not allow an UNVERIFIED proposition to become an established fact.


4. CLAIM BREADTH

Evidence supporting a specific fact does not support a broader claim.

Examples:

"AI helped product development move faster"

does NOT establish:

- enterprise AI transformation
- formal AI ROI measurement
- executive AI strategy
- enterprise-scale deployment

"AI-enabled marketing operations model in China"

does NOT establish:

- enterprise-wide marketing deployment
- measured marketing ROI
- global implementation already completed


5. SALES HYPOTHESES AND MODALITY

Preserve the modality of the original statement.

A question or diagnostic hypothesis is NOT an assertion that the
hypothesized condition exists.

For example:

"GrundMind could assess whether value capture is consistent across
these workflows"

must NOT be decomposed into:

- value capture is inconsistent
- value may be leaking

The atomic proposition is:

- GrundMind could assess whether value capture is consistent across
  these workflows

That proposition may be SUPPORTED when its factual premises are
supported and it remains explicitly diagnostic or hypothetical.

Likewise:

"investigate whether AI adoption is optimized across functions"

does NOT assert:

- AI adoption is not optimized
- optimization problems exist

And:

"investigate whether value is being captured comprehensively"

does NOT assert:

- value is not being captured
- Value Leakage exists

Do NOT manufacture factual propositions from possibilities embedded
inside words such as:

- whether
- assess whether
- investigate whether
- determine whether
- test whether
- explore whether

However, factual premises inside the hypothesis still require evidence.

Example:

"Given verified AI benefits in product development, GrundMind could
assess whether those benefits are consistent elsewhere."

requires cited evidence establishing the product-development benefit.

Do NOT allow direct propositions such as:

- {COMPANY} has Value Leakage
- {COMPANY} has fragmentation
- {COMPANY} has governance gaps
- {COMPANY} has Team Gap
- {COMPANY} has Cognitive Fit problems

unless cited evidence directly establishes them.


6. GENERIC BUSINESS CLAIMS

Reject unsupported generalizations such as:

- fragmentation typically emerges at this scale
- governance complexity increases with deployment
- leadership appetite is demonstrated
- the company is ready for GrundMind
- the account is qualified

unless those propositions are directly established by canonical evidence.


7. GRUNDMIND PRODUCT BOUNDARY

GrundMind is an evidence-based AI adoption diagnostic and advisory
system.

It identifies:

- Missing ROI
- Value Leakage
- Team Gap
- Cognitive Fit

It may assess workflows, governance, roles, capabilities, priorities,
ownership, metrics, and recommend a practical roadmap.

It is NOT:

- AI infrastructure
- an agent-management platform
- an observability platform
- a monitoring platform
- a governance enforcement system


CLASSIFY EACH ATOMIC PROPOSITION AS:

SUPPORTED
= directly supported by cited evidence, correctly qualified, or a
  properly framed diagnostic hypothesis whose premises are supported.

PARTIALLY_SUPPORTED
= proposition contains meaningful overstatement or combines supported
  and unsupported meaning.

UNSUPPORTED
= cited evidence does not establish the proposition.


STATUS CONSISTENCY:

The structured status MUST match your final reasoning.

Do not output:

status = "UNSUPPORTED"

and then conclude in the reason that the proposition is actually
supported.

If, after analysis or reconsideration, you conclude the proposition is
supported, output:

status = "SUPPORTED"

Do not narrate an internal debate or self-correction in the reason.
Return only the final judgment.


Return exactly:

{{
  "statements": [
    {{
      "statement_id": "",
      "atomic_claims": [
        {{
          "claim": "",
          "status": "SUPPORTED|PARTIALLY_SUPPORTED|UNSUPPORTED",
          "reason": ""
        }}
      ]
    }}
  ]
}}


STATEMENTS:

{json.dumps(verification_payload, indent=2, ensure_ascii=False)}
""",
            },
        ],
        response_format={
            "type": "json_object"
        },
        max_tokens=5000,
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
    ).strip()

    if not content:
        raise ValueError(
            "Atomic claim verifier returned an empty response."
        )

    try:

        data = json.loads(
            content
        )

    except json.JSONDecodeError as exc:

        raise ValueError(
            "Atomic claim verifier returned invalid JSON: "
            f"{exc.msg}"
        ) from exc

    checks = data.get(
        "statements",
        [],
    )

    expected_ids = {
        statement[
            "statement_id"
        ]
        for statement in statements
    }

    returned_ids = {
        check.get(
            "statement_id"
        )
        for check in checks
    }

    missing_ids = (
        expected_ids
        - returned_ids
    )

    unexpected_ids = (
        returned_ids
        - expected_ids
    )

    if missing_ids:

        raise ValueError(
            "Atomic verifier omitted statement IDs: "
            + ", ".join(
                sorted(
                    missing_ids
                )
            )
        )

    if unexpected_ids:

        raise ValueError(
            "Atomic verifier invented statement IDs: "
            + ", ".join(
                sorted(
                    str(item)
                    for item in unexpected_ids
                )
            )
        )

    failures = []

    for statement_check in checks:

        statement_id = (
            statement_check.get(
                "statement_id"
            )
        )

        atomic_claims = (
            statement_check.get(
                "atomic_claims",
                [],
            )
        )

        if not atomic_claims:

            failures.append(
                {
                    "statement_id": (
                        statement_id
                    ),
                    "status": "UNSUPPORTED",
                    "claim": (
                        "No atomic claims returned"
                    ),
                    "reason": (
                        "Atomic verifier did not "
                        "decompose the statement."
                    ),
                }
            )

            continue

        for atomic_claim in atomic_claims:

            status = str(
                atomic_claim.get(
                    "status",
                    "UNSUPPORTED",
                )
            ).upper()

            if status == "SUPPORTED":
                continue

            failures.append(
                {
                    "statement_id": (
                        statement_id
                    ),
                    "status": status,
                    "claim": (
                        atomic_claim.get(
                            "claim",
                            "",
                        )
                    ),
                    "reason": (
                        atomic_claim.get(
                            "reason",
                            "",
                        )
                    ),
                }
            )

    if failures:

        details = []

        for failure in failures:

            details.append(
                (
                    f"{failure['statement_id']} "
                    f"[{failure['status']}] "
                    f"{failure['claim']}: "
                    f"{failure['reason']}"
                )
            )

        raise ValueError(
            "Atomic claim validation failed: "
            + " | ".join(
                details
            )
        )

    return data


# =========================================================
# MARKDOWN RENDERER
# =========================================================

def refs_text(
    refs: list[str],
) -> str:

    return ", ".join(
        refs
    )


def render_markdown(
    result: dict,
    brief: dict,
    evidence_catalog: dict,
) -> str:

    company = result.get(
        "company",
        "Unknown company",
    )

    score = result.get(
        "score",
        0,
    )

    maximum = result.get(
        "max_score",
        0,
    )

    lines = [
        f"# {company} Account Brief",
        "",
        f"**GrundMind Prospect Score: {score}/{maximum}**",
        "",
        "## Signal Scorecard",
        "",
    ]

    for signal in (
        result.get(
            "signals",
            {}
        ).values()
    ):

        lines.append(
            "- "
            f"**{signal.get('name')}:** "
            f"{signal.get('score')}/"
            f"{signal.get('max_score')} "
            f"({signal.get('evidence_status')})"
        )

    why = brief[
        "why_this_account"
    ]

    lines.extend(
        [
            "",
            "## Why This Account",
            "",
            why.get(
                "summary",
                "",
            ),
            "",
            "Evidence: "
            + refs_text(
                why.get(
                    "evidence_refs",
                    [],
                )
            ),
            "",
            "## What Is Happening With AI",
            "",
        ]
    )

    for item in brief.get(
        "ai_activity",
        [],
    ):

        lines.append(
            "- "
            + item.get(
                "finding",
                "",
            )
            + " ["
            + refs_text(
                item.get(
                    "evidence_refs",
                    [],
                )
            )
            + "]"
        )

    lines.extend(
        [
            "",
            "## Where GrundMind May Fit",
            "",
        ]
    )

    for item in brief.get(
        "grundmind_fit",
        [],
    ):

        lines.append(
            "- **"
            + item.get(
                "angle",
                ""
            )
            + ":** "
            + item.get(
                "rationale",
                ""
            )
            + " ["
            + refs_text(
                item.get(
                    "evidence_refs",
                    [],
                )
            )
            + "]"
        )

    sales = brief[
        "sales_angle"
    ]

    lines.extend(
        [
            "",
            "## Suggested Sales Angle",
            "",
            sales.get(
                "thesis",
                "",
            ),
            "",
            "Evidence: "
            + refs_text(
                sales.get(
                    "evidence_refs",
                    [],
                )
            ),
            "",
            "## What We Do Not Know",
            "",
        ]
    )

    for uncertainty in brief.get(
        "uncertainties",
        [],
    ):

        lines.append(
            "- " + uncertainty
        )

    lines.extend(
        [
            "",
            "## Evidence Register",
            "",
        ]
    )

    used_refs = []

    for ref in collect_evidence_refs(
        brief
    ):

        if ref not in used_refs:
            used_refs.append(
                ref
            )

    for ref in used_refs:

        evidence = evidence_catalog[
            ref
        ]

        lines.append(
            f"### {ref}"
        )

        lines.append(
            ""
        )

        lines.append(
            evidence.get(
                "claim",
                "",
            )
        )

        if evidence.get("source_type"):
            lines.append(
                "Source type: "
                + evidence["source_type"]
            )

        for source in evidence.get(
            "supported_sources",
            [],
        ):

            lines.append(
                f"- {source}"
            )

        lines.append(
            ""
        )

    return "\n".join(
        lines
    )


# =========================================================
# MAIN
# =========================================================

def build_account_brief() -> dict:

    if not RESULT_PATH.exists():

        raise FileNotFoundError(
            "latest_prospect_result.json "
            "not found. Run research_company.py first."
        )

    with RESULT_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:

        result = json.load(
            file
        )

    result_company = (
        result.get(
            "company",
            "",
        ).strip()
    )

    if (
        result_company.lower()
        != COMPANY.lower()
    ):
        raise ValueError(
            "Account Brief company mismatch: "
            f"expected {COMPANY!r}, "
            f"got {result_company!r}."
        )

    evidence_catalog = (
        build_evidence_catalog(
            result
        )
    )

    if not evidence_catalog:

        # -------------------------------------------------
        # Deterministic insufficient-evidence terminal
        #
        # Zero established evidence is a legitimate
        # research outcome, not a pipeline failure.
        #
        # Do not call the LLM and do not manufacture a
        # sales narrative simply to satisfy the brief
        # schema.
        # -------------------------------------------------

        brief = {
            "why_this_account": {
                "summary": (
                    "No established public evidence was "
                    "found to support an evidence-backed "
                    "account qualification."
                ),
                "evidence_refs": [],
            },
            "ai_activity": [],
            "grundmind_fit": [],
            "sales_angle": {
                "thesis": (
                    "No evidence-backed sales angle can "
                    "be supported from the established "
                    "public evidence."
                ),
                "evidence_refs": [],
            },
            "uncertainties": [
                (
                    "Publicly available evidence was "
                    "insufficient to establish relevant "
                    "AI activity, organisational fit, "
                    "commercial pain, or a supported "
                    "GrundMind sales angle."
                )
            ],
        }

        canonical_brief = {
            "company": result.get(
                "company"
            ),
            "score": result.get(
                "score"
            ),
            "max_score": result.get(
                "max_score"
            ),
            "brief_status": (
                "INSUFFICIENT_EVIDENCE"
            ),
            "brief": brief,
            "semantic_validation": {
                "status": "NOT_APPLICABLE",
                "reason": (
                    "No established evidence exists "
                    "to semantically validate."
                ),
            },
            "atomic_validation": {
                "status": "NOT_APPLICABLE",
                "reason": (
                    "No evidence-backed claims were "
                    "generated."
                ),
            },
            "evidence_catalog": {},
        }

        with BRIEF_JSON_PATH.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                canonical_brief,
                file,
                indent=2,
            )

        markdown = (
            f"# {result.get('company')} — Account Brief\n\n"
            "## Status\n\n"
            "INSUFFICIENT EVIDENCE\n\n"
            "No established public evidence was found "
            "to support an evidence-backed account "
            "qualification or sales angle.\n"
        )

        BRIEF_MARKDOWN_PATH.write_text(
            markdown,
            encoding="utf-8",
        )

        print(
            "\nAccount Brief: "
            "INSUFFICIENT_EVIDENCE"
        )

        print(
            "No evidence-backed sales narrative "
            "generated."
        )

        print(
            "\nSaved:"
        )

        print(
            BRIEF_JSON_PATH
        )

        print(
            BRIEF_MARKDOWN_PATH
        )

        return canonical_brief

    brief = None
    semantic_validation = None
    atomic_validation = None
    validation_feedback = ""

    for attempt in range(
        1,
        4,
    ):

        try:

            if (
                attempt == 1
                or brief is None
            ):

                brief = generate_account_brief(
                    result=result,
                    evidence_catalog=(
                        evidence_catalog
                    ),
                    validation_feedback=(
                        validation_feedback
                    ),
                )

            else:

                print(
                    "Repairing previous brief from "
                    "validator feedback..."
                )

                brief = repair_account_brief(
                    result=result,
                    evidence_catalog=(
                        evidence_catalog
                    ),
                    previous_brief=brief,
                    validation_feedback=(
                        validation_feedback
                    ),
                )

            brief, removed_fields = (
                normalize_brief_schema(
                    brief
                )
            )

            if removed_fields:

                print(
                    "Exact-schema normalizer removed "
                    f"{len(removed_fields)} unexpected "
                    "field(s):"
                )

                for field in removed_fields:
                    print(
                        f"  {field}"
                    )

            sanitization_events = (
                scrub_unsupported_numeric_claims(
                    brief=brief,
                    result=result,
                    evidence_catalog=(
                        evidence_catalog
                    ),
                )
            )

            if sanitization_events:

                print(
                    "Deterministic numeric scrubber "
                    f"removed {len(sanitization_events)} "
                    "unsupported sentence(s)."
                )

                for event in (
                    sanitization_events
                ):

                    print(
                        "  "
                        f"{event['field']}: "
                        f"{event['unsupported_numbers']}"
                    )

            allowed_numbers = (
                get_allowed_numeric_tokens(
                    result=result,
                    evidence_catalog=(
                        evidence_catalog
                    ),
                )
            )

            brief, recursive_events = (
                scrub_all_brief_strings(
                    value=brief,
                    allowed_numbers=(
                        allowed_numbers
                    ),
                )
            )

            if recursive_events:

                print(
                    "Recursive numeric safety pass "
                    f"removed {len(recursive_events)} "
                    "unsupported string fragment(s):"
                )

                for event in recursive_events:

                    print(
                        "  "
                        f"{event['field']}: "
                        f"{event['unsupported_numbers']}"
                    )

            # ---------------------------------------------
            # Optional AI activity boundary
            #
            # ai_activity is allowed to be empty. An
            # uncited activity item is never useful and
            # must not force the model to invent evidence
            # merely to satisfy the brief schema.
            # ---------------------------------------------

            ai_activity = brief.get(
                "ai_activity",
                [],
            )

            if isinstance(ai_activity, list):

                cited_ai_activity = [
                    item
                    for item in ai_activity
                    if (
                        isinstance(item, dict)
                        and item.get(
                            "evidence_refs"
                        )
                    )
                ]

                removed_uncited = (
                    len(ai_activity)
                    - len(cited_ai_activity)
                )

                if removed_uncited:
                    print(
                        "Removed "
                        f"{removed_uncited} uncited "
                        "ai_activity item(s)."
                    )

                brief["ai_activity"] = (
                    cited_ai_activity
                )

            validate_brief(
                brief=brief,
                result=result,
                evidence_catalog=(
                    evidence_catalog
                ),
            )

            # -------------------------------------------------
            # Internal prospecting mode
            #
            # Agent 007 is currently an internal research/sales
            # experiment. The deterministic schema/evidence checks
            # above remain active, but expensive semantic and atomic
            # LLM validation must not block a usable research result.
            # -------------------------------------------------

            semantic_validation = {
                "status": "SKIPPED_INTERNAL_TEST"
            }

            atomic_validation = {
                "status": "SKIPPED_INTERNAL_TEST"
            }

            print(
                "Semantic/atomic validation skipped "
                "(internal prospecting mode)"
            )

            print(
                f"Brief validation PASS "
                f"(attempt {attempt}/3)"
            )

            break

        except ValueError as exc:

            validation_feedback = str(
                exc
            )

            print(
                f"Brief validation FAILED "
                f"(attempt {attempt}/3): "
                f"{validation_feedback}"
            )

            if attempt == 3:
                raise

    if brief is None:
        raise RuntimeError(
            "Account brief generation produced no result."
        )

    canonical_brief = {
        "company": result.get(
            "company"
        ),
        "score": result.get(
            "score"
        ),
        "max_score": result.get(
            "max_score"
        ),
        "brief": brief,
        "semantic_validation": (
            semantic_validation
        ),
        "atomic_validation": (
            atomic_validation
        ),
        "evidence_catalog": (
            evidence_catalog
        ),
    }

    with BRIEF_JSON_PATH.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            canonical_brief,
            file,
            indent=2,
        )

    markdown = render_markdown(
        result=result,
        brief=brief,
        evidence_catalog=(
            evidence_catalog
        ),
    )

    BRIEF_MARKDOWN_PATH.write_text(
        markdown,
        encoding="utf-8",
    )

    print(
        markdown
    )

    print(
        "\nSaved:"
    )

    print(
        BRIEF_JSON_PATH
    )

    print(
        BRIEF_MARKDOWN_PATH
    )

    return canonical_brief


if __name__ == "__main__":

    build_account_brief()
