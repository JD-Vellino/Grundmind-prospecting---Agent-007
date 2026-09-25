import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from research_core import (
    clean_json,
    research,
    synthesize_research,
    verify_accepted_findings,
)

from prospect_score import (
    EvidenceStatus,
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
    "organisational_fit"
)

OFFICIAL_DOMAINS = list(
    _SOURCE_POLICY.official_domains
)

OFFICIAL_SOURCE_PREFIXES = list(
    _SOURCE_POLICY.official_source_prefixes
)


# =========================================================
# RESEARCH OBJECTIVE
# =========================================================

ORGANISATIONAL_FIT_OBJECTIVE = (
    f"TARGET COMPANY IDENTITY: {RESEARCH_IDENTITY}\n\n"
    "Establish the organisational characteristics needed to determine "
    f"whether {COMPANY} is a strong GrundMind prospect: current or recent "
    "employee count, evidence of a substantial knowledge-worker "
    "population, and evidence that the organisation operates across "
    "multiple distinct business functions or departments. "
    f"Prioritize PRIMARY SOURCES. Explicitly search {COMPANY} annual reports, "
    "Form 10-K or other SEC filings, official investor-relations material, "
    f"and official {COMPANY} documents before relying on company databases "
    "or third-party organisational profiles. Seek direct primary evidence "
    "for workforce size, workforce composition, and distinct internal "
    "business functions."
)


# =========================================================
# SIGNAL-SPECIFIC VALIDATION RULES
# =========================================================

ORGANISATIONAL_FIT_VALIDATION_RULES = """
Accept findings only when they materially establish one or more of
these organisational characteristics:

PRIMARY-SOURCE PRIORITY

When the same organisational characteristic is supported by both a
primary source and a third-party source, prefer the primary source.

Primary evidence includes:

- target-company annual reports
- target-company investor-relations documents
- target-company regulatory filings
- regulator-hosted target-company filings
- official target-company corporate material

Third-party company databases, organisational charts, mirrors, and
talent-data providers should be retained only when primary evidence
does not establish the characteristic or when they add a materially
different supported fact.


1. EMPLOYEE COUNT

Accept explicit current or recent workforce or employee-count evidence.

Prefer:

- company annual reports
- regulatory filings
- investor material
- official company pages
- attributable executive statements
- reputable company profiles when stronger evidence is unavailable

Preserve the actual number and date when available.

Do not convert revenue, customers, offices, countries, contractors,
users, partners, creators, suppliers, or community members into
employee count.


2. KNOWLEDGE-WORKER POPULATION

Accept evidence that materially establishes a substantial workforce
engaged in professional, technical, analytical, creative, managerial,
commercial, operational, or other knowledge-intensive work.

Relevant functions may include:

- engineering
- software
- product
- design
- research
- finance
- marketing
- sales
- legal
- HR
- IT
- data
- analytics
- operations
- management
- supply-chain planning
- other professional corporate functions

Do not infer a substantial knowledge-worker population merely because
the company is described as a technology company.

Evidence should establish meaningful organisational functions or
workforce composition.


3. MULTI-DEPARTMENT OPERATING ENVIRONMENT

Accept evidence showing the company operates across multiple distinct
internal business functions, departments, teams, or business units.

Examples include combinations of:

- product
- engineering
- finance
- marketing
- sales
- operations
- IT
- HR
- legal
- supply chain
- customer operations
- design
- corporate functions

Multiple countries alone do not establish multiple departments.

Multiple products alone do not establish multiple departments.

Customer segments alone do not establish multiple departments.


GENERAL BOUNDARY

This signal concerns organisational suitability for GrundMind.

Do not treat AI hiring, AI deployment, AI ROI, or AI strategy as
Organisational Fit evidence unless the same source independently
establishes one of the three organisational characteristics above.

Do not infer missing characteristics.

False negatives are preferable to false positives.
"""


# =========================================================
# EVIDENCE HELPERS
# =========================================================

EVIDENCE_STRENGTH = {
    EvidenceStatus.VERIFIED: 3,
    EvidenceStatus.CORROBORATED: 2,
    EvidenceStatus.UNVERIFIED: 1,
    EvidenceStatus.CONFLICTING: 0,
}


def supported_urls(
    finding: dict,
) -> list[str]:

    urls = []

    for verification in finding.get(
        "source_verifications",
        [],
    ):

        if (
            verification.get(
                "verification_status"
            )
            != "SUPPORTED"
        ):
            continue

        url = verification.get(
            "source_url"
        )

        if url:
            urls.append(url)

    return list(
        dict.fromkeys(urls)
    )


def evidence_status_for_indices(
    findings: list[dict],
    indices: list[int],
) -> EvidenceStatus | None:

    urls = []

    for index in indices:

        if (
            not isinstance(index, int)
            or index < 0
            or index >= len(findings)
        ):
            continue

        urls.extend(
            supported_urls(
                findings[index]
            )
        )

    urls = list(
        dict.fromkeys(urls)
    )

    if not urls:
        return None

    return classify_evidence_status(
        urls=urls,
        official_domains=OFFICIAL_DOMAINS,
        official_source_prefixes=(
            OFFICIAL_SOURCE_PREFIXES
        ),
    )


# =========================================================
# ORGANISATIONAL CHARACTERISTIC CLASSIFIER
# =========================================================

def classify_organisational_fit(
    company: str,
    findings: list[dict],
) -> dict:

    if not findings:

        return {
            "employee_count": {
                "value": None,
                "evidence_indices": [],
            },
            "knowledge_worker_heavy": {
                "value": "UNKNOWN",
                "evidence_indices": [],
            },
            "multi_department": {
                "value": "UNKNOWN",
                "evidence_indices": [],
            },
        }

    evidence_input = []

    for index, finding in enumerate(
        findings
    ):

        evidence_input.append(
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
            }
        )

    response = client.chat.completions.create(
        model="kimi-k2.6",
        messages=[
            {
                "role": "system",
                "content": (
                    "You classify already verified organisational evidence. "
                    "Do not research. "
                    "Do not use outside knowledge. "
                    "Do not infer missing company characteristics. "
                    "Use only the supplied evidence. "
                    "Preserve evidence indices exactly. "
                    "Return only valid JSON."
                ),
            },
            {
                "role": "user",
                "content": f"""
Target company:
{company}

Determine exactly three organisational characteristics from the
established evidence below.


1. EMPLOYEE COUNT

Return the best supported current or recent employee count.

Use null if the evidence does not establish a usable count.

Do not count customers, users, contractors, offices, creators,
suppliers, partners, or countries as employees.


2. KNOWLEDGE-WORKER-HEAVY

Return TRUE only when the evidence establishes a substantial
knowledge-worker population through meaningful professional,
technical, analytical, creative, managerial, commercial,
operational, or corporate functions.

A technology-company label by itself is insufficient.

Return FALSE only when the evidence affirmatively establishes that
the organisation is not knowledge-worker-heavy.

Otherwise return UNKNOWN.


3. MULTI-DEPARTMENT

Return TRUE only when the evidence establishes multiple distinct
internal business functions, departments, or business units.

Multiple countries alone are insufficient.
Multiple products alone are insufficient.

Return FALSE only when evidence affirmatively establishes otherwise.

Otherwise return UNKNOWN.


For each characteristic include only the evidence indices that
materially support that classification.

Return exactly:

{{
  "employee_count": {{
    "value": 0,
    "evidence_indices": []
  }},
  "knowledge_worker_heavy": {{
    "value": "TRUE|FALSE|UNKNOWN",
    "evidence_indices": []
  }},
  "multi_department": {{
    "value": "TRUE|FALSE|UNKNOWN",
    "evidence_indices": []
  }}
}}


ESTABLISHED EVIDENCE:

{json.dumps(evidence_input, indent=2)}
""",
            },
        ],
        response_format={
            "type": "json_object"
        },
        max_tokens=1500,
        timeout=120,
        extra_body={
            "thinking": {
                "type": "disabled"
            }
        },
    )

    return clean_json(
        response.choices[0].message.content or ""
    )


# =========================================================
# MAIN SIGNAL PIPELINE
# =========================================================

def run_organisational_fit(
    company: str = COMPANY,
):

    research_result = research(
        company=company,
        objective=(
            ORGANISATIONAL_FIT_OBJECTIVE
        ),
        max_searches=3,
    )

    validated = synthesize_research(
        company=company,
        objective=(
            ORGANISATIONAL_FIT_OBJECTIVE
        ),
        research_result=research_result,
        validation_rules=(
            ORGANISATIONAL_FIT_VALIDATION_RULES
        ),
    )

    verified = verify_accepted_findings(
        validated,
        signal="organisational_fit",
    )

    durable_findings = verified.get(
        "stored_verified_findings",
        [],
    )

    print(
        "\nEstablished durable organisational "
        f"evidence: {len(durable_findings)}"
    )

    classification = (
        classify_organisational_fit(
            company=company,
            findings=durable_findings,
        )
    )

    employee_data = classification.get(
        "employee_count",
        {},
    )

    knowledge_data = classification.get(
        "knowledge_worker_heavy",
        {},
    )

    department_data = classification.get(
        "multi_department",
        {},
    )

    employee_count = employee_data.get(
        "value"
    )

    if not isinstance(
        employee_count,
        int,
    ):
        employee_count = 0

    knowledge_value = str(
        knowledge_data.get(
            "value",
            "UNKNOWN",
        )
    ).upper()

    department_value = str(
        department_data.get(
            "value",
            "UNKNOWN",
        )
    ).upper()

    knowledge_worker_heavy = (
        knowledge_value == "TRUE"
    )

    multi_department = (
        department_value == "TRUE"
    )

    criterion_statuses = []

    employee_status = (
        evidence_status_for_indices(
            durable_findings,
            employee_data.get(
                "evidence_indices",
                [],
            ),
        )
    )

    knowledge_status = (
        evidence_status_for_indices(
            durable_findings,
            knowledge_data.get(
                "evidence_indices",
                [],
            ),
        )
    )

    department_status = (
        evidence_status_for_indices(
            durable_findings,
            department_data.get(
                "evidence_indices",
                [],
            ),
        )
    )

    for status in (
        employee_status,
        knowledge_status,
        department_status,
    ):

        if status is not None:
            criterion_statuses.append(
                status
            )

    if criterion_statuses:

        overall_status = min(
            criterion_statuses,
            key=lambda status: (
                EVIDENCE_STRENGTH[
                    status
                ]
            ),
        )

    else:

        overall_status = (
            EvidenceStatus.UNVERIFIED
        )

    print(
        "\nORGANISATIONAL FIT EVIDENCE CHECK"
    )

    print(
        f"Employee count: {employee_count}"
    )

    print(
        "Knowledge-worker-heavy: "
        f"{knowledge_value}"
    )

    print(
        "Multi-department: "
        f"{department_value}"
    )

    print(
        "Evidence status: "
        f"{overall_status.value}"
    )

    print(
        "\nEVIDENCE SOURCES"
    )

    used_indices = set(
        employee_data.get(
            "evidence_indices",
            [],
        )
        + knowledge_data.get(
            "evidence_indices",
            [],
        )
        + department_data.get(
            "evidence_indices",
            [],
        )
    )

    for index in sorted(
        used_indices
    ):

        if (
            not isinstance(index, int)
            or index < 0
            or index >= len(
                durable_findings
            )
        ):
            continue

        finding = durable_findings[
            index
        ]

        print(
            f"\n- {finding.get('claim', '')}"
        )

        for url in supported_urls(
            finding
        ):

            tier = classify_source_tier(
                url=url,
                official_domains=(
                    OFFICIAL_DOMAINS
                ),
                official_source_prefixes=(
                    OFFICIAL_SOURCE_PREFIXES
                ),
            )

            print(
                f"  {tier.value} | {url}"
            )

    signal_score = (
        score_organisational_fit(
            employee_count=employee_count,
            knowledge_worker_heavy=(
                knowledge_worker_heavy
            ),
            multi_department=(
                multi_department
            ),
            evidence_status=(
                overall_status
            ),
        )
    )

    print(
        "\nDETERMINISTIC ORGANISATIONAL "
        "FIT SCORE"
    )

    print(
        f"Company: {company}"
    )

    print(
        f"Organisational Fit: "
        f"{signal_score.score}/"
        f"{signal_score.max_score}"
    )

    print(
        f"Evidence: "
        f"{signal_score.evidence_status.value}"
    )

    print(
        f"Reason: "
        f"{signal_score.reason}"
    )

    return signal_score


if __name__ == "__main__":

    run_organisational_fit()
