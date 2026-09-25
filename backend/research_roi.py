import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from research_core import (
    research,
    synthesize_research,
    verify_accepted_findings,
    clean_json,
)

from roi_score import (
    ROIValueEvidence,
    score_ai_value,
)

from prospect_score import (
    Evidence,
    EvidenceStatus,
    SignalScore,
    SourceTier,
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
# CONFIGURATION
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
    "ai_value_roi"
)

OFFICIAL_DOMAINS = list(
    _SOURCE_POLICY.official_domains
)

OFFICIAL_SOURCE_PREFIXES = list(
    _SOURCE_POLICY.official_source_prefixes
)

OBJECTIVE = (
    f"TARGET COMPANY IDENTITY: {RESEARCH_IDENTITY}\n\n"
    f"Find evidence that {COMPANY} measures or manages "
    "business value, ROI, productivity, efficiency, "
    "benefits realization, or measurable operational "
    "outcomes from internal AI adoption."
)

ROI_VALIDATION_RULES = """
Accept a finding only when it establishes at least one of:

- AI ROI or financial return
- measurable business value
- quantified productivity or efficiency
- measurable workflow improvement
- cost or time reduction
- benefits realization
- operational performance metrics
- an explicit process for measuring AI value or impact

Evidence of AI adoption, deployment, training, leadership, strategy,
employee participation, organisational scale, or AI hiring is not
enough by itself.

The objective concerns INTERNAL use of AI.

Reject:

- AI features in products sold to customers
- customer-facing AI product revenue
- generic AI market commentary
- investor questions that do not establish company activity
- AI industry trends
- unrelated financial performance

unless the finding independently establishes internal AI value,
productivity, efficiency, workflow impact, ROI, or measurement.

Do not infer financial ROI from operational improvements.

Do not claim that AI caused an improvement unless the evidence
explicitly makes that connection.

Vendor customer case studies may be retained when they contain
specific, attributable evidence about the target company.

However, vendor case studies are not equivalent to independent
primary company evidence.

False negatives are preferable to false positives.
"""

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
# ROI CLASSIFIER
# =========================================================

def classify_roi_findings(
    company: str,
    findings: list[dict],
) -> list[dict]:

    if not findings:
        return []

    classifier_input = []

    for index, finding in enumerate(findings):
        classifier_input.append(
            {
                "evidence_index": index,
                "claim": finding.get("claim", ""),
                "evidence_detail": finding.get(
                    "evidence_detail",
                    "",
                ),
                "source_verifications": finding.get(
                    "source_verifications",
                    [],
                ),
            }
        )

    response = client.chat.completions.create(
        model="kimi-k2.6",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an evidence classification agent. "
                    "Do not perform research. "
                    "Do not use outside knowledge. "
                    "The supplied findings have already passed "
                    "source fetching and claim verification. "
                    "Classify only what the supplied evidence establishes. "
                    "Do not strengthen claims or infer financial ROI from "
                    "operational improvements. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
Target company:
{company}

Classify each established evidence finding into exactly one status:

EXPLICIT_ROI
= Evidence explicitly establishes financial ROI, financial return,
benefits realization, or an operating formal value framework.

MEASURED_VALUE
= Evidence establishes concrete measured business value or business
outcomes, beyond merely reporting operational activity metrics.

OPERATIONAL_METRICS
= Evidence establishes measured productivity, efficiency, workflow,
automation, usage, adoption, time-saving, or other operational metrics.

ASPIRATIONAL
= Evidence establishes an explicit intention or framework for measuring
AI value or impact, but not realized measurement.

UNKNOWN
= Evidence does not establish any of the above.

Important:

- Do not classify operational metrics as EXPLICIT_ROI.
- Do not infer financial value from time savings or automation rates.
- Do not infer causation beyond the evidence.
- Use only the supplied established evidence.
- Preserve the supplied evidence_index exactly.

Return:

{{
  "classifications": [
    {{
      "evidence_index": 0,
      "value_status": "EXPLICIT_ROI|MEASURED_VALUE|OPERATIONAL_METRICS|ASPIRATIONAL|UNKNOWN",
      "description": ""
    }}
  ]
}}

ESTABLISHED EVIDENCE:

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
        "classifications",
        [],
    )


# =========================================================
# SUPPORTED SOURCE HELPERS
# =========================================================

def get_supported_source_urls(
    finding: dict,
) -> list[str]:

    urls = []

    for verification in finding.get(
        "source_verifications",
        [],
    ):
        if (
            verification.get("verification_status")
            == "SUPPORTED"
        ):
            source_url = verification.get(
                "source_url"
            )

            if source_url:
                urls.append(source_url)

    return list(dict.fromkeys(urls))


def get_supported_source_names(
    finding: dict,
    supported_urls: list[str],
) -> list[str]:

    names = []

    for source in finding.get(
        "sources",
        [],
    ):
        if source.get("source_url") in supported_urls:
            name = source.get(
                "source_name",
                "Unknown source",
            )

            names.append(name)

    return names


# =========================================================
# RESEARCH
# =========================================================

research_result = research(
    company=COMPANY,
    objective=OBJECTIVE,
    max_searches=3,
)

validated = synthesize_research(
    company=COMPANY,
    objective=OBJECTIVE,
    research_result=research_result,
    validation_rules=ROI_VALIDATION_RULES,
)

verified = verify_accepted_findings(
    validated,
    signal="ai_value_roi",
)


# =========================================================
# DURABLE EVIDENCE
# =========================================================

durable_findings = verified.get(
    "stored_verified_findings",
    [],
)

print(
    f"\nEstablished durable ROI evidence: "
    f"{len(durable_findings)}"
)


# =========================================================
# CLASSIFY ESTABLISHED EVIDENCE
# =========================================================

classifications = classify_roi_findings(
    company=COMPANY,
    findings=durable_findings,
)

classification_by_index = {
    item["evidence_index"]: item
    for item in classifications
    if "evidence_index" in item
}


# =========================================================
# DETERMINISTIC SCORING
# =========================================================

value_results = []


for index, finding in enumerate(
    durable_findings
):

    classification = classification_by_index.get(
        index
    )

    if not classification:
        continue

    value_status = classification.get(
        "value_status",
        "UNKNOWN",
    ).upper()

    if value_status == "UNKNOWN":
        continue

    supported_urls = get_supported_source_urls(
        finding
    )

    if not supported_urls:
        continue

    evidence_status = classify_evidence_status(
        urls=supported_urls,
        official_domains=OFFICIAL_DOMAINS,
        official_source_prefixes=OFFICIAL_SOURCE_PREFIXES,
    )

    source_tiers = [
        classify_source_tier(
            url=url,
            official_domains=OFFICIAL_DOMAINS,
            official_source_prefixes=OFFICIAL_SOURCE_PREFIXES,
        )
        for url in supported_urls
    ]

    best_source_tier = min(
        source_tiers,
        key=lambda tier: TIER_PRIORITY[tier],
    )

    supported_names = get_supported_source_names(
        finding,
        supported_urls,
    )

    evidence = Evidence(
        source_name=(
            ", ".join(supported_names)
            or "Verified public source"
        ),
        source_tier=best_source_tier,
        status=evidence_status,
        finding=finding.get(
            "claim",
            "",
        ),
    )

    value_evidence = ROIValueEvidence(
        value_status=value_status,
        description=classification.get(
            "description",
            "",
        ),
        evidence=evidence,
    )

    signal_score = score_ai_value(
        value_evidence
    )

    value_results.append(
        {
            "finding": finding,
            "classification": classification,
            "evidence": evidence,
            "score": signal_score,
        }
    )


# =========================================================
# SELECT STRONGEST DEFENSIBLE SIGNAL
# =========================================================

if value_results:

    best_value = max(
        value_results,
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

    value_score = best_value["score"]

    print(
        "\nSELECTED AI VALUE / ROI SIGNAL"
    )

    print(
        f"Claim: "
        f"{best_value['finding']['claim']}"
    )

    print(
        f"Status: "
        f"{best_value['classification']['value_status']}"
    )

    print(
        f"Source quality: "
        f"{best_value['evidence'].status.value}"
    )

    print(
        f"Score: "
        f"{value_score.score}/"
        f"{value_score.max_score}"
    )

else:

    evidence = Evidence(
        source_name="No qualifying evidence found",
        source_tier=SourceTier.D,
        status=EvidenceStatus.UNVERIFIED,
        finding=(
            "No meaningful AI value or ROI evidence "
            "was established."
        ),
    )

    value_evidence = ROIValueEvidence(
        value_status="UNKNOWN",
        description="",
        evidence=evidence,
    )

    value_score = score_ai_value(
        value_evidence
    )


# =========================================================
# FINAL RESULT
# =========================================================

print(
    "\n\nDETERMINISTIC AI VALUE / ROI SCORE"
)

print(
    f"Company: {COMPANY}"
)

print(
    f"AI Value / ROI: "
    f"{value_score.score}/"
    f"{value_score.max_score}"
)

print(
    f"Evidence: "
    f"{value_score.evidence_status.value}"
)

print(
    f"Reason: "
    f"{value_score.reason}"
)