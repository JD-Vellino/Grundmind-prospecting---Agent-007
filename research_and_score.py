import json
import os

from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI

from research_core import (
    clean_json,
    research,
    synthesize_research,
    verify_accepted_findings,
)

from verify_claim import verify_claim

from prospect_score import (
    Evidence,
    EvidenceStatus,
    SourceTier,
    print_score,
    score_ai_hiring,
    score_organisational_fit,
)

from evidence_quality import (
    classify_evidence_status,
    classify_source_tier,
)

from company_config import get_company_config


load_dotenv()

client = OpenAI(
    api_key=os.environ["MOONSHOT_API_KEY"],
    base_url="https://api.moonshot.ai/v1",
)


# =========================================================
# COMPANY CONFIGURATION
# =========================================================

COMPANY_CONFIG = get_company_config(
    os.environ.get(
        "AGENT007_COMPANY",
        "Logitech",
    )
)
COMPANY = COMPANY_CONFIG.name
RESEARCH_IDENTITY = COMPANY_CONFIG.research_identity

_SOURCE_POLICY = COMPANY_CONFIG.policy(
    "ai_hiring"
)

OFFICIAL_DOMAINS = list(
    _SOURCE_POLICY.official_domains
)

OFFICIAL_SOURCE_PREFIXES = list(
    _SOURCE_POLICY.official_source_prefixes
)


# =========================================================
# HIRING RESEARCH OBJECTIVE
# =========================================================

HIRING_OBJECTIVE = (
    f"TARGET COMPANY IDENTITY: {RESEARCH_IDENTITY}\n\n"
    "Find current or recent public evidence of AI-related hiring "
    f"at {COMPANY}, including organisational AI adoption, transformation, "
    "governance, enablement, responsible AI, GenAI, Copilot, AI leadership, "
    "technical AI/ML roles, or broader roles with meaningful AI responsibilities."
)


# =========================================================
# HIRING-SPECIFIC VALIDATION RULES
# =========================================================

HIRING_VALIDATION_RULES = """
Accept findings only when they establish a specific AI-related role,
vacancy, or hiring activity connected to the target company.

Relevant evidence may include:

- AI adoption
- AI transformation
- AI governance
- responsible AI
- AI enablement
- GenAI
- generative AI
- Copilot
- AI leadership
- AI programme or program management
- technical AI / ML roles
- broader roles with substantial AI responsibilities

A finding should preserve, where available:

- role title
- role responsibilities
- location
- evidence concerning whether the vacancy is currently open
- source supporting that specific role

IMPORTANT VACANCY RULES:

OPEN requires evidence that the company is currently recruiting for
the role.

A current employee holding a position is NOT evidence that the
position is an open vacancy.

A profile describing someone's existing job is not an OPEN vacancy.

If evidence shows that the role existed previously but no longer
appears to be recruiting, preserve that fact rather than presenting
it as current.

If vacancy status cannot be established, preserve the uncertainty.

Do not transform:

"Person X is Head of AI"

into:

"Company is hiring a Head of AI."

A finding is relevant only if it establishes a specific vacancy,
recruitment activity, or identifiable hiring opportunity.

AI strategy, governance activity, executive commentary, deployment,
or organisational AI initiatives without recruitment evidence must
be rejected, even when highly relevant to AI generally.

Reject:

- roles belonging to another company
- generic AI hiring commentary
- employee profiles presented as vacancies
- speculative vacancies
- roles where the AI connection is invented
- search snippets that do not establish the underlying role
- duplicate descriptions of the same vacancy

Technical AI/ML vacancies may be retained even though they are weaker
GrundMind adoption signals. The deterministic scoring layer will decide
their value.

For accepted findings, phrase the claim conservatively.

Only use wording such as "currently recruiting", "open vacancy",
or "currently hiring" when the supplied evidence actually establishes
current recruitment.

False negatives are preferable to false positives.
"""


# =========================================================
# PRIORITIES
# =========================================================

TIER_PRIORITY = {
    SourceTier.A: 1,
    SourceTier.B: 2,
    SourceTier.C: 3,
    SourceTier.D: 4,
}

STATUS_PRIORITY = {
    EvidenceStatus.VERIFIED: 4,
    EvidenceStatus.CORROBORATED: 3,
    EvidenceStatus.UNVERIFIED: 2,
    EvidenceStatus.CONFLICTING: 1,
}


# =========================================================
# CURRENT-STATE REFRESH
# =========================================================

def refresh_hiring_findings(
    findings: list[dict],
) -> list[dict]:
    """
    Re-fetch persisted hiring evidence before allowing it
    to influence a CURRENT hiring score.

    The evidence that a vacancy once existed may remain durable.
    The statement that it is OPEN is transient and must survive
    current source verification.
    """

    refreshed = []

    for finding in findings:

        claim = finding.get(
            "claim",
            "",
        )

        sources = finding.get(
            "sources",
            [],
        )

        current_verifications = []

        print(
            f"\nREFRESHING STORED HIRING CLAIM:\n"
            f"{claim}"
        )

        for source in sources:

            source_url = source.get(
                "source_url"
            )

            if not source_url:
                continue

            try:

                verification = verify_claim(
                    claim=claim,
                    source_url=source_url,
                )

            except Exception as exc:

                verification = {
                    "verification_status": "ERROR",
                    "reason": str(exc),
                    "source_url": source_url,
                }

            current_verifications.append(
                verification
            )

            print(
                f"  {source_url}"
            )

            print(
                "  → "
                f"{verification.get('verification_status')}"
            )

        statuses = {
            verification.get(
                "verification_status"
            )
            for verification
            in current_verifications
        }

        # For a CURRENT hiring score we stay conservative.
        # At least one source must still fully support the
        # established claim.
        if "SUPPORTED" not in statuses:
            print(
                "  CURRENT RESULT: SKIPPED"
            )
            continue

        refreshed.append(
            {
                **finding,
                "current_source_verifications": (
                    current_verifications
                ),
            }
        )

    return refreshed


# =========================================================
# HIRING STRUCTURE CLASSIFIER
# =========================================================

def classify_hiring_findings(
    company: str,
    findings: list[dict],
) -> list[dict]:

    if not findings:
        return []

    current_date = datetime.now(
        timezone.utc
    ).date().isoformat()

    classifier_input = []

    for index, finding in enumerate(
        findings
    ):

        classifier_input.append(
            {
                "evidence_index": index,
                "claim": finding.get(
                    "claim",
                    "",
                ),
                "evidence_detail": finding.get(
                    "evidence_detail",
                    "",
                ),
                "current_source_verifications": (
                    finding.get(
                        "current_source_verifications",
                        [],
                    )
                ),
            }
        )

    response = client.chat.completions.create(
        model="kimi-k2.6",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a hiring-evidence classification agent. "
                    "Do not perform research. "
                    "Do not use outside knowledge. "
                    "The supplied evidence has already passed source fetching "
                    "and claim verification. "
                    "Your task is only to structure what the supplied evidence "
                    "establishes. "
                    "Do not invent vacancy status, dates, locations, job titles, "
                    "or responsibilities. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
Target company:
{company}

Current date:
{current_date}

Use this date when interpreting current, historical, or future vacancy
information.

Classify each established hiring finding.

For every finding return:

- role_title
- role_description
- location
- vacancy_status

vacancy_status must be exactly one of:

OPEN
FILLED
HISTORICAL
UNKNOWN


STRICT STATUS RULES:

OPEN
= the supplied currently verified evidence establishes that the company
  is actively recruiting for this role.

FILLED
= evidence establishes that the role is currently occupied rather than
  being recruited.

HISTORICAL
= evidence establishes that the vacancy or role existed previously but
  is no longer a current recruitment opportunity.

UNKNOWN
= the supplied evidence does not establish current recruitment status.


IMPORTANT:

- A current employee profile is not an OPEN vacancy.
- A job title existing inside a company is not an OPEN vacancy.
- "Present" employment means the person currently holds the role, not
  that the company is recruiting for it.
- Do not infer OPEN from a job-board-style URL alone.
- Do not infer OPEN merely because a vacancy once existed.
- If current recruitment is ambiguous, use UNKNOWN.
- Preserve the evidence_index exactly.
- Use only the supplied evidence.


Return exactly:

{{
  "roles": [
    {{
      "evidence_index": 0,
      "role_title": "",
      "role_description": "",
      "location": "",
      "vacancy_status": "OPEN|FILLED|HISTORICAL|UNKNOWN"
    }}
  ]
}}


ESTABLISHED HIRING EVIDENCE:

{json.dumps(classifier_input, indent=2)}
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

    data = clean_json(
        response.choices[0].message.content or ""
    )

    return data.get(
        "roles",
        [],
    )


# =========================================================
# SUPPORTED SOURCE HELPERS
# =========================================================

def get_current_supported_urls(
    finding: dict,
) -> list[str]:

    urls = []

    for verification in finding.get(
        "current_source_verifications",
        [],
    ):

        if (
            verification.get(
                "verification_status"
            )
            == "SUPPORTED"
        ):

            source_url = verification.get(
                "source_url"
            )

            if source_url:
                urls.append(
                    source_url
                )

    return list(
        dict.fromkeys(
            urls
        )
    )


def get_source_names(
    finding: dict,
    supported_urls: list[str],
) -> list[str]:

    names = []

    for source in finding.get(
        "sources",
        [],
    ):

        if source.get(
            "source_url"
        ) not in supported_urls:
            continue

        names.append(
            source.get(
                "source_name",
                "Unknown source",
            )
        )

    return names


# =========================================================
# 1. RESEARCH
# =========================================================

research_result = research(
    company=COMPANY,
    objective=HIRING_OBJECTIVE,
    max_searches=3,
)


# =========================================================
# 2. SEMANTIC VALIDATION
# =========================================================

validated = synthesize_research(
    company=COMPANY,
    objective=HIRING_OBJECTIVE,
    research_result=research_result,
    validation_rules=HIRING_VALIDATION_RULES,
)


# =========================================================
# 3. ACTUAL-SOURCE VERIFICATION + PERSISTENCE
# =========================================================

verified = verify_accepted_findings(
    validated,
    signal="ai_hiring",
)


stored_hiring_findings = verified.get(
    "stored_verified_findings",
    [],
)

print(
    f"\nEstablished durable hiring evidence: "
    f"{len(stored_hiring_findings)}"
)


# =========================================================
# 4. REFRESH CURRENT VACANCY EVIDENCE
# =========================================================

current_hiring_findings = (
    refresh_hiring_findings(
        stored_hiring_findings
    )
)

print(
    f"\nCurrently source-supported hiring findings: "
    f"{len(current_hiring_findings)}"
)


# =========================================================
# 5. STRUCTURE CURRENT FINDINGS
# =========================================================

classified_roles = classify_hiring_findings(
    company=COMPANY,
    findings=current_hiring_findings,
)

role_by_index = {
    role["evidence_index"]: role
    for role in classified_roles
    if "evidence_index" in role
}


# =========================================================
# 6. DETERMINISTIC EVIDENCE QUALITY + SCORE
# =========================================================

role_results = []


print(
    "\nROLE-BY-ROLE EVIDENCE CHECK"
)


for index, finding in enumerate(
    current_hiring_findings
):

    role = role_by_index.get(
        index
    )

    if not role:
        continue

    role_title = role.get(
        "role_title",
        "Unknown role",
    )

    vacancy_status = role.get(
        "vacancy_status",
        "UNKNOWN",
    ).upper()

    print(
        f"\nRole: {role_title}"
    )

    print(
        f"Vacancy status: "
        f"{vacancy_status}"
    )

    # Only currently OPEN vacancies influence
    # the current prospect score.
    if vacancy_status != "OPEN":

        print(
            "Result: SKIPPED - "
            "not established as currently open"
        )

        continue

    supported_urls = get_current_supported_urls(
        finding
    )

    if not supported_urls:

        print(
            "Result: SKIPPED - "
            "no currently supported sources"
        )

        continue

    evidence_status = classify_evidence_status(
        urls=supported_urls,
        official_domains=OFFICIAL_DOMAINS,
        official_source_prefixes=(
            OFFICIAL_SOURCE_PREFIXES
        ),
    )

    source_tiers = [
        classify_source_tier(
            url=url,
            official_domains=OFFICIAL_DOMAINS,
            official_source_prefixes=(
                OFFICIAL_SOURCE_PREFIXES
            ),
        )
        for url in supported_urls
    ]

    best_source_tier = min(
        source_tiers,
        key=lambda tier: (
            TIER_PRIORITY[tier]
        ),
    )

    source_names = get_source_names(
        finding,
        supported_urls,
    )

    for url, tier in zip(
        supported_urls,
        source_tiers,
    ):

        print(
            f"  - {tier.value} | {url}"
        )

    print(
        f"Evidence status: "
        f"{evidence_status.value}"
    )

    evidence = Evidence(
        source_name=(
            ", ".join(source_names)
            or "Verified public source"
        ),
        source_tier=best_source_tier,
        status=evidence_status,
        finding=finding.get(
            "claim",
            "",
        ),
    )

    signal_score = score_ai_hiring(
        role_title=role_title,
        role_description=role.get(
            "role_description",
            "",
        ),
        evidence=evidence,
    )

    print(
        f"Role score: "
        f"{signal_score.score}/"
        f"{signal_score.max_score}"
    )

    role_results.append(
        {
            "role": role,
            "finding": finding,
            "score": signal_score,
            "evidence": evidence,
        }
    )


# =========================================================
# 7. SELECT STRONGEST CURRENT HIRING SIGNAL
# =========================================================

if role_results:

    best_role_result = max(
        role_results,
        key=lambda item: (
            item["score"].score,
            STATUS_PRIORITY[
                item["evidence"].status
            ],
            -TIER_PRIORITY[
                item["evidence"].source_tier
            ],
        ),
    )

    ai_hiring_score = (
        best_role_result["score"]
    )

    print(
        "\nSELECTED AI HIRING SIGNAL"
    )

    print(
        f"Role: "
        f"{best_role_result['role']['role_title']}"
    )

    print(
        f"Status: "
        f"{best_role_result['role']['vacancy_status']}"
    )

    print(
        f"Evidence: "
        f"{best_role_result['evidence'].status.value}"
    )

    print(
        f"Score: "
        f"{ai_hiring_score.score}/"
        f"{ai_hiring_score.max_score}"
    )

else:

    evidence = Evidence(
        source_name=(
            "No qualifying current evidence found"
        ),
        source_tier=SourceTier.D,
        status=EvidenceStatus.UNVERIFIED,
        finding=(
            "No meaningful currently open AI hiring "
            "evidence was established."
        ),
    )

    ai_hiring_score = score_ai_hiring(
        role_title="",
        role_description="",
        evidence=evidence,
    )


# =========================================================
# ORGANISATIONAL FIT
# Still hard-coded for this test.
# =========================================================

organisational_fit_score = (
    score_organisational_fit(
        employee_count=7000,
        knowledge_worker_heavy=True,
        multi_department=True,
    )
)


# =========================================================
# FINAL RESULT
# =========================================================

print(
    "\n\nDETERMINISTIC GRUNDMIND SCORE"
)

print_score(
    company=COMPANY,
    signals=[
        ai_hiring_score,
        organisational_fit_score,
    ],
)